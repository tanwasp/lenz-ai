
import os
from crewai import Agent, Task, Crew, Process
from crewai.tools import BaseTool
import subprocess
import json
import time
import asyncio

# Set up OpenAI API key
os.environ["OPENAI_API_KEY"] = ""

class ScreenPipeTool(BaseTool):
    """CrewAI Tool that proxies requests to the ScreenPipe MCP server.

    The constructor launches the Node-based MCP server (`server.js`) once and keeps
    the process alive. Subsequent tool invocations communicate with the server
    over stdio using the official JSON-RPC 2.0 messages defined by MCP.  Each
    `_run` call accepts a **command string** in the form:

        "tool_name"               – e.g. ``get_current_window``
        "tool_name {json_args}"   – e.g. ``search_window_history {\"query\": \"chrome\"}``

    Where *tool_name* is any of the tools exposed by the server (see
    `server.js → setupToolHandlers`) and *json_args* is an **optional** JSON
    object containing the arguments for that tool.  The response from the MCP
    server is returned to CrewAI as a JSON string so that the agent can parse
    it further if desired.
    """

    name: str = "ScreenPipe"
    description: str = (
        "Interact with the ScreenPipe Model Context Protocol (MCP) server to "
        "retrieve OCR, screenshots, and historical window data."
    )

    def __init__(self, server_cwd: str | None = None):  # noqa: D401
        """Launch the MCP server and prepare for JSON-RPC communication."""
        super().__init__()

        # Directory that contains server.js – default to this file's folder.
        self._cwd = (
            server_cwd or os.path.join(os.path.dirname(__file__))
        )

        self._server_proc: subprocess.Popen | None = None
        self._next_id: int = 1

        self._start_server()
        # Perform MCP initialization handshake once
        self._initialized = False
        self._initialize()

    # ------------------------------------------------------------------
    # MCP initialization
    # ------------------------------------------------------------------

    def _initialize(self) -> None:
        """Send initialize + initialized handshake to the MCP server."""
        if self._initialized:
            return

        init_request = {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "ScreenPipeTool", "version": "0.1.0"},
        }

        # 1. initialize request
        _ = self._send_rpc_raw("initialize", init_request)

        # 2. initialized notification (no id)
        self._send_notification("notifications/initialized", {})

        self._initialized = True

    # ---------------------------------------------------------------------
    # Private helpers
    # ---------------------------------------------------------------------

    def _start_server(self) -> None:
        """Spawn the Node MCP server if it is not already running."""
        if self._server_proc is not None and self._server_proc.poll() is None:
            return  # Already running

        # Launch the *Python* FastMCP implementation (fast_server.py) in stdio mode
        # so we can communicate via JSON-RPC.  Make sure fast_server.py is in the
        # same directory as this file.
        self._server_proc = subprocess.Popen(
            ["python", "fast_server.py"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=self._cwd,
            bufsize=1,  # line-buffered for interactive reads
        )

        # Give the server a moment to initialize.
        time.sleep(2)

    def _send_rpc(self, method: str, params: dict | None = None) -> dict:
        """Send a JSON-RPC request and synchronously wait for the response."""

        if not self._server_proc or self._server_proc.poll() is not None:
            raise RuntimeError("MCP server is not running")

        request = {
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": method,
            "params": params or {},
        }
        self._next_id += 1

        # Write request
        assert self._server_proc.stdin is not None  # for mypy
        self._server_proc.stdin.write(json.dumps(request) + "\n")
        self._server_proc.stdin.flush()

        # Read a single line response (all MCP responses are delimited by newline)
        assert self._server_proc.stdout is not None  # for mypy
        response_line = self._server_proc.stdout.readline()
        if response_line == "":
            # Check for server errors captured on stderr
            stderr = self._server_proc.stderr.read() if self._server_proc.stderr else ""
            raise RuntimeError(f"No response from MCP server. Stderr: {stderr}")

        try:
            response: dict = json.loads(response_line.strip())
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON from MCP server: {response_line}") from exc

        if "error" in response:
            raise RuntimeError(f"MCP Error: {response['error']}")

        return response

    def _send_rpc_raw(self, method: str, params: dict | None = None) -> dict:
        """Lower-level RPC helper bypassing initialization guard."""
        if not self._server_proc or self._server_proc.poll() is not None:
            raise RuntimeError("MCP server is not running")

        request = {
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": method,
            "params": params or {},
        }
        self._next_id += 1

        assert self._server_proc.stdin is not None
        self._server_proc.stdin.write(json.dumps(request) + "\n")
        self._server_proc.stdin.flush()

        assert self._server_proc.stdout is not None
        line = self._server_proc.stdout.readline()
        if line == "":
            raise RuntimeError("No response during initialization")
        return json.loads(line.strip())

    def _send_notification(self, method: str, params: dict | None = None) -> None:
        if not self._server_proc or self._server_proc.poll() is not None:
            raise RuntimeError("MCP server is not running")

        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
        }
        assert self._server_proc.stdin is not None
        self._server_proc.stdin.write(json.dumps(notification) + "\n")
        self._server_proc.stdin.flush()

    # ------------------------------------------------------------------
    # BaseTool API
    # ------------------------------------------------------------------

    def _run(self, command: str) -> str:  # noqa: D401
        """Execute a ScreenPipe MCP tool call.

        Parameters
        ----------
        command: str
            Either the tool name (e.g. ``get_current_window``) or the tool name
            followed by a JSON object of arguments. Whitespace separates the two
            parts. Examples::

                get_current_window
                search_window_history {"query": "gmail", "limit": 5}
        """

        # ------------------------------------------------------------------
        # Parse input
        # ------------------------------------------------------------------
        cmd_parts = command.strip().split(" ", 1)
        tool_name = cmd_parts[0]
        try:
            arguments = json.loads(cmd_parts[1]) if len(cmd_parts) > 1 else {}
        except json.JSONDecodeError as exc:
            raise ValueError(
                "Arguments must be a valid JSON object, e.g."
                "  'search_window_history {\"query\": \"foo\"}'"
            ) from exc

        # ------------------------------------------------------------------
        # Send request via JSON-RPC
        # ------------------------------------------------------------------
        response = self._send_rpc(
            "tools/call",
            {
                "name": tool_name,
                "arguments": arguments,
            },
        )

        # Return the raw JSON so the CrewAI agent can decide how to parse it.
        return json.dumps(response["result"], ensure_ascii=False)

    # ------------------------------------------------------------------
    # Cleanup helpers (optional)
    # ------------------------------------------------------------------

    def _shutdown(self) -> None:
        """Terminate the underlying Node process cleanly."""
        if self._server_proc and self._server_proc.poll() is None:
            self._server_proc.terminate()
            self._server_proc.wait()

# Create a ScreenPipe tool instance – the server launches automatically
screenpipe_tool = ScreenPipeTool()


# Create a CrewAI agent
screen_observer_agent = Agent(
    role='Screen Observer',
    goal='Observe the computer screen and report what is visible.',
    llm="gpt-4o-mini",
    backstory=(
        "An AI agent that can see the screen and understand what is on it. You are an educational agent specialized in recognizing learning, questioning and confusion in a user's actions. "
        "You have access to the `ScreenPipe` tool which exposes the following methods:\n"
        "• get_current_window – returns OCR text, appName, windowName (without screenshot)\n"
        "• get_current_window_with_screenshot – same as above but also returns a base-64 PNG `screenshot` field\n"
        "• start_window_monitoring / stop_window_monitoring – begin or end realtime capture\n"
        "• search_window_history – search past OCR frames\n"
        "Call the `ScreenPipe` tool once and pass the desired MCP command in its **`command`** argument.\n"
        "Examples:\n"
        "   {\"command\": \"get_current_window_with_screenshot\"}\n"
        "   {\"command\": \"search_window_history {\\\"query\\\": \\\"gmail\\\"}\"}\n"
        "Note the inner JSON when arguments are needed.  The only field you ever send to ScreenPipe is `command`.\n"
    ),
    verbose=True,
    tools=[screenpipe_tool],
    allow_delegation=False
)

# # Create a task for the agent
# task = Task(
#     description=(
#         "Step 1 → Call `get_current_window_with_screenshot` (no arguments).\n"
#         "Step 2 → Inspect `text`, `appName`, `windowName`.\n"
#         "Step 3 → Use both the OCR text *and* the screenshot to determine what the user is doing. Understand what the user has learned by recognizing what questions they have asked or what educational content they are reading/watching (like \"Learned about: agents in Python or Existentialism in Philosophy\"). Produce a list of phrases or concepts that the user will have associated with this experience. For example: [prior distributions, variational inference, agents, etc.]\n"
#         "Step 4 → Finish."
#     ),
#     expected_output='A list of phrases or concepts that the user will have associated with the possible learning experience. For example: [prior distributions, variational inference, agents, etc.])"',
#     agent=screen_observer_agent
# )

# # Create a crew and run the task
# crew = Crew(
#     agents=[screen_observer_agent],
#     tasks=[task],
#     process=Process.sequential
# )

# result = crew.kickoff()

# print(result)

# For now, let's just test the tool directly
# # result = screenpipe_tool._run('get_current_window')
# print(result)

# ---------------- Intervention Agent ----------------

# Create a second agent that calls show_tooltip when learning context detected

intervention_agent = Agent(
    role="Intervention Agent",
    goal="Provide timely explanations via on-screen tooltip",
    backstory=(
        "Use ScreenPipe to inspect the current window. If the user appears to be reading educational "
        "material or coding docs, surface a 1-sentence helpful explanation using the show_tooltip command.\n"
         "You have access to the `ScreenPipe` tool which exposes the following methods:\n"
        "• get_current_window – returns OCR text, appName, windowName (without screenshot)\n"
        "• get_current_window_with_screenshot – same as above but also returns a base-64 PNG `screenshot` field\n"
        "• start_window_monitoring / stop_window_monitoring – begin or end realtime capture\n"
        "• search_window_history – search past OCR frames\n"
        "Call the `ScreenPipe` tool once and pass the desired MCP command in its **`command`** argument.\n"
        "Examples:\n"
        "   {\"command\": \"get_current_window_with_screenshot\"}\n"
        "   {\"command\": \"search_window_history {\\\"query\\\": \\\"gmail\\\"}\"}\n"
        "Note the inner JSON when arguments are needed.  The only field you ever send to ScreenPipe is `command`.\n"
    ),
    tools=[screenpipe_tool],
    allow_delegation=False,
    verbose=True,
    llm="gpt-4o-mini",
)

intervention_task = Task(
    description=(
        "Detect if the user is learning something.\n"
        "1. Call get_current_window_with_screenshot.\n"
        "2. If OCR text suggests a tutorial, cursor, docs, stackoverflow, etc., call show_tooltip explaining the most difficult concept the user is looking at (≤25 words).\n"
        "3. Otherwise, do nothing."
    ),
    expected_output="Either 'No help needed' or confirmation of tooltip sent",
    agent=intervention_agent,
)

# Run both tasks concurrently
crew2 = Crew(
    agents=[intervention_agent],
    tasks=[intervention_task],
    process=Process.sequential,
)

crew2.kickoff()

import os
from crewai import Agent, Task, Crew, Process
from crewai.tools import BaseTool
import subprocess
import json
import time
import argparse
import asyncio
import sys
import traceback
from copy import deepcopy


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
            [sys.executable, "fast_server.py"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,   # <- restore PIPE for JSON-RPC replies
            stderr=None,              # inherit parent stderr -> logging visible
            text=True,
            cwd=self._cwd,
        )

        # Give the server a moment to initialize.
        time.sleep(2)

    def _send_rpc(self, method: str, params: dict | None = None) -> dict:
        """Send a JSON-RPC request and synchronously wait for the response."""

        if not self._server_proc or self._server_proc.poll() is not None:
            if self._server_proc and self._server_proc.stderr:
                err = self._server_proc.stderr.read().strip()
                if err:
                    print("\n=== fast_server stderr ===\n" + err + "\n=== end ===")
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
            if self._server_proc and self._server_proc.stderr:
                err = self._server_proc.stderr.read().strip()
                if err:
                    print("\n=== fast_server stderr ===\n" + err + "\n=== end ===")
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
    role="Screen Observer",
    goal="Detect user questions on screen & log confusion topics",
    llm="gpt-4o-mini",
    backstory=(
        "You watch the live OCR feed and look for explicit questions the user types or reads—e.g. Google searches, ChatGPT queries, YouTube 'How do I …' titles.\n"
        "Your mission: extract short phrase(s) that reflect what the user is confused about and log each via the ScreenPipe *log_confusion* tool.\n\n"
        "Available ScreenPipe methods:\n"
        "• get_current_window_with_screenshot – OCR + screenshot\n"
        "• search_window_history – query previous OCR text\n"
        "• log_confusion – <NEW> record a confusion event (arguments: {text})\n\n"
        "Usage rules are identical: pass a single field `command` that contains the tool name and JSON arguments if needed.\n"
        "Example to log confusion about 'variational autoencoders':\n"
        "   {\"command\": \"log_confusion {\\\"concept\\\": \\\"variational autoencoders\\\"}\"}\n"
        "Return a final answer listing the phrases you logged."
    ),
    verbose=True,
    tools=[screenpipe_tool],
    allow_delegation=False,
)

# Create a task for the observer agent
observe_task = Task(
    description=(
        "1. Capture current window with `get_current_window_with_screenshot`.\n"
        "2. Look for any sentence or query that ends with a '?' or begins with words like 'how', 'what', 'why', 'explain', etc. These indicate the user is asking a question.\n"
        "3. From the OCR text, extract concise concept phrases (≤4 words each) that summarise the user's uncertainty.\n"
        "4. For each phrase call `log_confusion` via ScreenPipe to record it.\n"
        "5. After one log finish"
    ),
    expected_output="A JSON list of phrases that were logged via log_confusion.",
    agent=screen_observer_agent,
)

# # Create a crew runner for this observer (optionally invoked elsewhere)
# try:
#     Crew(
#         agents=[screen_observer_agent],
#         tasks=[observe_task],   # fresh Task copy
#         process=Process.sequential,
#     ).kickoff()
# except Exception:
#     traceback.print_exc()
# For now, let's just test the tool directly
# result = screenpipe_tool._run('get_current_window')
# print(result)

# ---------------- Intervention Agent ----------------

# Create a second agent that calls show_tooltip when learning context detected

intervention_agent = Agent(
    role="Intervention Agent",
    goal="Provide timely explanations via on-screen tooltip",
    backstory=(
        "Use ScreenPipe to inspect the current window. If the user appears to be reading educational "
        "material or coding docs, surface a 1-sentence helpful explanation using the show_tooltip command.\n"
        "Available ScreenPipe methods (use exactly one per Action):\n"
        "• get_current_window_with_screenshot – OCR + screenshot\n"
        "• classify_mastery – POST phrases to backend and get weak/strong/neutral\n"
        "• show_tooltip – render a 1-sentence tooltip on screen\n\n"
        "Calling convention: send a single JSON field `command` whose value is the tool name plus JSON args if needed.\n"
        "Example: {\"command\": \"classify_mastery {\\\"phrases\\\": [\\\"posterior\\\", \\\"vae\\\"]}\"}.\n\n"
        "IMPORTANT: When you output Action Input it MUST be exactly {\"command\": \"<tool-name><space>{JSON-args-if-any}\"}. No other keys are allowed."
        "Workflow:\n"
        "1. Capture window with get_current_window_with_screenshot.\n"
        "2. Extract up to 8 candidate phrases (n-grams ≤3 words) from the OCR text.\n"
        "3. classify_mastery with that list.\n"
        "4. If 'weak' is not empty → choose one phrase and call show_tooltip \n"
        "   with ≤25-word clarification of that concept relevant to the context. \n"
        "5. Otherwise, do nothing. Return 'No help needed'."
    ),
    tools=[screenpipe_tool],
    allow_delegation=False,
    verbose=True,
    llm="gpt-4o-mini",
)

intervention_task = Task(
    description=(
        "Identify difficult concepts in the current window and optionally display a tooltip.\n"
        "Step-by-step:\n"
        "1. get_current_window_with_screenshot (no args).\n"
        "2. Parse the OCR text → build an array `phrases` (≤8 meaningful tokens/short phrases).\n"
        "3. classify_mastery with that list.\n"
        "4. If 'weak' is not empty → choose one phrase and call show_tooltip with a ≤25-word explanation.\n"
        "5. Return either 'No help needed' or 'Tooltip sent: <phrase>'."
    ),
    expected_output="Either 'No help needed' or confirmation of tooltip sent",
    agent=intervention_agent,
)

# # Run both tasks concurrently
# crew2 = Crew(
#     agents=[intervention_agent],
#     tasks=[intervention_task],
#     process=Process.sequential,
# )


# ─── Continuous loop --------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run ScreenPipe agents")
    parser.add_argument("mode", choices=["observer", "intervention", "both"], nargs="?", default="both")
    parser.add_argument("--delay", type=int, default=10, help="Seconds between cycles")
    args = parser.parse_args()

    try:
        while True:
            if args.mode in ("observer", "both"):
                print("\n=== Observer cycle ===")
                # fresh crew each time
                Crew(agents=[screen_observer_agent], tasks=[observe_task], process=Process.sequential).kickoff()

            if args.mode in ("intervention", "both"):
                print("\n=== Intervention cycle ===")
                Crew(agents=[intervention_agent], tasks=[intervention_task], process=Process.sequential).kickoff()

            time.sleep(args.delay)
    except KeyboardInterrupt:
        print("\nStopping agent loop…")
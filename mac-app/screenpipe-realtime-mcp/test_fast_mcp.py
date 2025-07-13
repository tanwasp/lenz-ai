#!/usr/bin/env python3
"""Minimal integration test for fast_server.py.

Launches the FastMCP server as a subprocess (stdio transport) and performs:
1. initialize / initialized handshake
2. tools/list request to enumerate available tools
3. tools/call → get_current_window to ensure the server responds

Run with:

    python test_fast_mcp.py
"""

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Helper to send/recv jsonrpc over stdio
# ---------------------------------------------------------------------------

class JsonRpcProcess:
    def __init__(self, cmd):
        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            cwd=str(ROOT),
            bufsize=1,
        )
        self._id = 1

    def request(self, method: str, params=None):
        msg = {
            "jsonrpc": "2.0",
            "id": self._id,
            "method": method,
            "params": params or {},
        }
        self._id += 1
        self._write(msg)
        return self._read()

    def notify(self, method: str, params=None):
        msg = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        self._write(msg)

    # ------------------------- internals -------------------------
    def _write(self, obj):
        assert self.proc.stdin
        self.proc.stdin.write(json.dumps(obj) + "\n")
        self.proc.stdin.flush()

    def _read(self):
        assert self.proc.stdout
        line = self.proc.stdout.readline()
        if line == "":
            raise RuntimeError("Server terminated unexpectedly")
        return json.loads(line.strip())

    def close(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()


if __name__ == "__main__":
    server = JsonRpcProcess([sys.executable, "fast_server.py"])
    try:
        time.sleep(1)  # give server a sec to boot
        # 1. initialize
        init_result = server.request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "fast_mcp_tester", "version": "0.0.1"},
            },
        )
        print("initialize →", init_result["result"]["serverInfo"])

        # 2. initialized notification
        server.notify("notifications/initialized")

        # 3. list tools
        tool_list = server.request("tools/list")
        print("tools/list →", [t["name"] for t in tool_list["result"]["tools"]])

        # 4. get_current_window
        gcw = server.request(
            "tools/call",
            {"name": "get_current_window", "arguments": {"include_screenshot": False}},
        )
        print("get_current_window →", gcw["result"][:100] if isinstance(gcw["result"], str) else gcw["result"])

    finally:
        server.close() 
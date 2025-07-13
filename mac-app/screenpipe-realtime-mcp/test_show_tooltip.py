#!/usr/bin/env python3
"""Quick manual test for the `show_tooltip` MCP tool.

Usage:
    python test_show_tooltip.py "Your message here"

If `fast_server.py` is not already running the script will launch it in the
background (stdio) and send the JSON-RPC initialize handshake automatically,
then call the tool.  Look for a macOS banner notification to verify success.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Minimal JSON-RPC helper (same as in test_fast_mcp)
# ---------------------------------------------------------------------------


class RpcProc:
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

    def req(self, method: str, params=None):
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
        self._write({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def _write(self, obj):
        assert self.proc.stdin
        self.proc.stdin.write(json.dumps(obj) + "\n")
        self.proc.stdin.flush()

    def _read(self):
        assert self.proc.stdout
        line = self.proc.stdout.readline()
        if line == "":
            raise RuntimeError("Server terminated")
        return json.loads(line.strip())

    def close(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()


if __name__ == "__main__":
    text = sys.argv[1] if len(sys.argv) > 1 else "Hello from ScreenPipe tooltip!"

    server = RpcProc([sys.executable, "fast_server.py"])
    try:
        # give server a moment to start
        time.sleep(1)
        server.req(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "tooltip-tester", "version": "1.0"},
            },
        )
        server.notify("notifications/initialized")

        result = server.req(
            "tools/call",
            {
                "name": "show_tooltip",
                "arguments": {"text": text},
            },
        )
        print("Response:", result["result"])
        print("If you saw a macOS notification, the tool works!")
    finally:
        server.close() 
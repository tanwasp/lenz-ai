#!/usr/bin/env python3
# """ScreenPipe Real-time MCP Server (Python FastMCP)
#
# Mirrors the behaviour of `server.js` but is implemented with the official
# **Python FastMCP SDK**.  The server exposes five tools:
#
# 1. ``get_current_window``        – Return OCR text + optional screenshot.
# 2. ``start_window_monitoring``   – Begin polling ScreenPipe every 2 s.
# 3. ``stop_window_monitoring``    – Stop the polling loop.
# 4. ``search_window_history``     – Query historical OCR frames.
# 5. ``get_screenpipe_status``     – Health/status check of ScreenPipe.
#
# Run locally with:
#
#     uv run mcp dev fast_server.py   # hot-reload dev server
#     # or
#     python fast_server.py           # production
#
# The ScreenPipe desktop app must already be running on http://localhost:3030.
# """
import asyncio
import contextlib
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests
from mcp.server.fastmcp import FastMCP  # type: ignore
from pydantic import BaseModel, Field

# --- ensure repo-root/backend is on PYTHONPATH --------------------------------
import subprocess, socket, os, json
from pathlib import Path
import sys

# Add ../../backend to sys.path so we can import mastery.py
ROOT_DIR = Path(__file__).resolve().parents[2]  # repo root
BACKEND_DIR = ROOT_DIR / "backend"
if BACKEND_DIR.exists() and str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

import mastery  # now resolvable

# Consistent user identifier across backend & MCP
USER_ID = "browser_user"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("screenpipe-fastmcp")

# ---------------------------------------------------------------------------
# Helper class that talks to the ScreenPipe HTTP API
# ---------------------------------------------------------------------------


class WindowState(BaseModel):
    """Structured return type for `get_current_window`."""

    timestamp: datetime
    app_name: str = Field(alias="appName")
    window_name: str = Field(alias="windowName")
    text: str
    focused: bool
    screenshot: Optional[str] = None  # base64 PNG


class ScreenPipeRealtime:
    """Thin Python port of the realtime logic in server.js."""

    def __init__(self) -> None:
        self.current_window_state: Optional[WindowState] = None
        self.is_streaming: bool = False
        self._poll_task: Optional[asyncio.Task] = None
        self._last_update: Optional[str] = None  # ISO string timestamp

    # --------------------------- public helpers ---------------------------

    async def get_latest_window_content(self, include_screenshot: bool = True) -> Optional[WindowState]:
        five_seconds_ago = (
            (datetime.utcnow() - timedelta(seconds=5))
            .isoformat(timespec="milliseconds") + "Z"
        )
        base_url = "http://localhost:3030/search"
        params = {
            "limit": 1,
            "content_type": "ocr",
            "start_time": five_seconds_ago,
            "focused": "true",
        }

        try:
            resp = requests.get(base_url, params=params, timeout=3)
            if resp.status_code != 200:
                logger.warning("ScreenPipe /search %s → %s", resp.url, resp.status_code)
                logger.warning("Response: %s", resp.text[:300])
            resp.raise_for_status()
        except requests.RequestException as exc:
            # Retry *without* start_time, as ScreenPipe sometimes rejects ISO strings with ms
            if "start_time" in params:
                params.pop("start_time")
                try:
                    resp = requests.get(base_url, params=params, timeout=3)
                    resp.raise_for_status()
                except requests.RequestException:
                    logger.error("HTTP error querying ScreenPipe: %s", exc)
                    return None
            else:
                logger.error("HTTP error querying ScreenPipe: %s", exc)
                return None

        data = resp.json().get("data", [])
        if not data:
            return None

        content = data[0]["content"]
        window_state: Dict[str, Any] = {
            "timestamp": content["timestamp"],
            "appName": content.get("app_name", "Unknown"),
            "windowName": content.get("window_name", "Unknown"),
            "text": content.get("text", ""),
            "focused": bool(content.get("focused", False)),
            "screenshot": None,
        }

        if include_screenshot:
            if frame := content.get("frame"):
                window_state["screenshot"] = frame
            else:
                # Fallback query asking for frames
                try:
                    params_with_frames = {
                        **params,
                        "include_frames": "true",
                    }
                    r2 = requests.get(base_url, params=params_with_frames, timeout=3)
                    r2.raise_for_status()
                    d2 = r2.json().get("data", [])
                    if d2 and d2[0]["content"].get("frame"):
                        window_state["screenshot"] = d2[0]["content"]["frame"]
                except requests.RequestException:
                    pass

        return WindowState.parse_obj(window_state)

    async def start_realtime_monitoring(self) -> None:
        if self.is_streaming:
            return
        self.is_streaming = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("📡 Started realtime monitoring loop")

    async def stop_realtime_monitoring(self) -> None:
        self.is_streaming = False
        if self._poll_task:
            self._poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._poll_task
            self._poll_task = None
        logger.info("🛑 Stopped realtime monitoring loop")

    async def search_window_history(
        self,
        query: Optional[str] = None,
        app_name: Optional[str] = None,
        window_name: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 10,
        include_screenshots: bool = False,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {
            "content_type": "ocr",
            "limit": limit,
        }
        if query:
            params["q"] = query
        if app_name:
            params["app_name"] = app_name
        if window_name:
            params["window_name"] = window_name
        if start_time:
            params["start_time"] = start_time
        if end_time:
            params["end_time"] = end_time
        if include_screenshots:
            params["include_frames"] = "true"

        try:
            # Ensure datetime params have Z and no microseconds to avoid 400 errors
            if "start_time" in params:
                params["start_time"] = params["start_time"].replace("Z", "")
            if "end_time" in params:
                params["end_time"] = params["end_time"].replace("Z", "")
            r = requests.get("http://localhost:3030/search", params=params, timeout=5)
            r.raise_for_status()
            return r.json().get("data", [])
        except requests.RequestException as exc:
            logger.error("Search failed: %s", exc)
            return []

    async def check_health(self) -> bool:
        try:
            r = requests.get("http://localhost:3030/health", timeout=3)
            r.raise_for_status()
            return True
        except requests.RequestException:
            return False

    # --------------------------- internal ---------------------------

    async def _poll_loop(self) -> None:
        while self.is_streaming:
            try:
                state = await self.get_latest_window_content(include_screenshot=True)
                if state and state.timestamp.isoformat() != self._last_update:
                    self.current_window_state = state
                    self._last_update = state.timestamp.isoformat()
                    self._notify_subscribers(state)
            except Exception as exc:
                logger.error("Polling error: %s", exc)
            await asyncio.sleep(2)

    def _notify_subscribers(self, state: WindowState) -> None:
        # Placeholder – real implementation would push over MCP notifications.
        logger.info("📱 New window: %s – %s", state.app_name, state.window_name)


# ---------------------------------------------------------------------------
# FastMCP server definition
# ---------------------------------------------------------------------------

mcp = FastMCP("screenpipe-realtime")
_realtime = ScreenPipeRealtime()


@mcp.tool(name="get_current_window")
async def get_current_window(
    include_screenshot: bool = True,
    include_text: bool = True,
) -> Dict[str, Any]:
    """Return the most recent focused window captured by ScreenPipe."""
    logger.info("🛠️  get_current_window(include_screenshot=%s, include_text=%s)", include_screenshot, include_text)
    state = await _realtime.get_latest_window_content(include_screenshot)
    if state is None:
        return {
            "error": "No current window content. Is ScreenPipe running?",
        }
    # Convert to dict and optionally strip text
    result = state.dict(by_alias=True)
    if include_text and "text" in result:
        words = result["text"].split()
        if len(words) > 200:
            result["text"] = " ".join(words[:200]) + " …"
    if not include_text:
        result.pop("text", None)
    return result


# Convenience wrapper so LLMs don’t need to remember arguments
# ---------------------------------------------------------------------------


@mcp.tool(name="get_current_window_with_screenshot")
async def get_current_window_with_screenshot() -> Dict[str, Any]:  # noqa: D401
    """Return appName, windowName, OCR text *and* a base-64 PNG screenshot.

    This is equivalent to calling `get_current_window` with
    `include_screenshot=True`.  The screenshot is returned in the `screenshot`
    field of the structured result.
    """
    logger.info("🛠️  get_current_window_with_screenshot()")
    return await get_current_window(include_screenshot=True, include_text=True)


# ---------------------------------------------------------------------------
# UI Intervention: show_tooltip (macOS Notification as lightweight tooltip)
# ---------------------------------------------------------------------------

SOCK_PATH = "/tmp/screenpipe_tooltip.sock"
HELPER = Path(__file__).with_name("tooltip_helper.py")


# Register as MCP tool
@mcp.tool(name="show_tooltip")
async def show_tooltip(text: str, duration: int | None = 5) -> str:
    """Display a transient tooltip/notification on macOS.

    Parameters
    ----------
    text: str
        The text to display (max ~200 chars).
    duration: int | None
        Seconds to keep the notification visible. macOS notifications are
        managed by the system; *duration* is best-effort (ignored if None).
    """
    logger.info("🛠️  show_tooltip text='%s' duration=%s", text[:60], duration)

    payload = json.dumps({"text": text[:200], "duration": duration})

    # 1) Try unix domain socket to Electron overlay
    if os.path.exists(SOCK_PATH):
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.connect(SOCK_PATH)
                s.sendall(payload.encode())
            return "Tooltip sent via Electron socket"
        except Exception as exc:
            logger.warning("Socket tooltip delivery failed: %s", exc)

    # 2) Fallback: launch native helper script (requires pyobjc)
    if HELPER.exists():
        subprocess.Popen([sys.executable, str(HELPER), text[:200], str(duration or 4)])
        return "Tooltip shown via native helper"

    # 3) Final fallback: macOS banner
    try:
        subprocess.Popen([
            "osascript",
            "-e",
            f'display notification {json.dumps(text[:200])} with title "ScreenPipe"',
        ])
        return "Tooltip sent via macOS banner"
    except FileNotFoundError:
        logger.error("No tooltip mechanism available")
        return "Failed: no delivery mechanism"


@mcp.tool(name="start_window_monitoring")
async def start_window_monitoring(auto_screenshots: bool = True) -> str:  # noqa: D401
    """Begin polling ScreenPipe every 2 seconds."""
    logger.info("🛠️  start_window_monitoring(auto_screenshots=%s)", auto_screenshots)
    await _realtime.start_realtime_monitoring()
    return "Started realtime monitoring"


@mcp.tool(name="stop_window_monitoring")
async def stop_window_monitoring() -> str:  # noqa: D401
    logger.info("🛠️  stop_window_monitoring()")
    await _realtime.stop_realtime_monitoring()
    return "Stopped realtime monitoring"


@mcp.tool(name="search_window_history")
async def search_window_history(
    query: Optional[str] = None,
    app_name: Optional[str] = None,
    window_name: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 10,
    include_screenshots: bool = False,
) -> List[Dict[str, Any]]:
    logger.info("🛠️  search_window_history query='%s' app=%s window=%s limit=%s", query, app_name, window_name, limit)
    return await _realtime.search_window_history(
        query=query,
        app_name=app_name,
        window_name=window_name,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        include_screenshots=include_screenshots,
    )


@mcp.tool(name="get_screenpipe_status")
async def get_screenpipe_status() -> Dict[str, Any]:
    logger.info("🛠️  get_screenpipe_status()")
    if not await _realtime.check_health():
        return {"status": "unreachable"}
    data = requests.get("http://localhost:3030/health", timeout=3).json()
    return {"status": "healthy", **data, "monitoring": _realtime.is_streaming}


# ---------------------------------------------------------------------------
# Mastery classification proxy
# ---------------------------------------------------------------------------


@mcp.tool(name="classify_mastery")
async def classify_mastery(phrases: List[str]) -> Dict[str, List[str]]:  # noqa: D401
    """Return weak/strong/neutral lists for the given phrases via backend."""

    BACKEND = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
    try:
        resp = requests.post(f"{BACKEND}/mastery_classify", json={"phrases": phrases})
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        return {"error": str(exc)}


@mcp.tool(name="log_confusion")
async def log_confusion(concept: str | None = None, text: str | None = None) -> str:  # noqa: D401
    """Record a confusion event via mastery.add_event.

    Accepts either *concept* **or** *text* as the phrase to log so that
    callers can pass `{concept: "foo"}` or `{text: "foo"}`.
    """

    phrase = (concept or text or "").strip()
    if not phrase:
        return "No concept given"

    BACKEND = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
    resp = requests.post(f"{BACKEND}/log_confusion", json={"concept": phrase})
    return f"Logged: {phrase}" if resp.ok else f"Failed: {resp.text}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # When run directly, start a production-style server (stdio transport).
    mcp.run() 
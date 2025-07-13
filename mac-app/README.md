# Window Text Streamer

A JavaScript script that streams active window text content from ScreenPipe in real-time.

## What it does

- ✅ Automatically streams text from whatever window you have active
- ✅ Updates every ~1 second
- ✅ Shows app name, window title, timestamp, and extracted text
- ✅ No button presses needed - starts streaming immediately
- ✅ Only shows focused windows with meaningful text (>10 characters)

## Prerequisites

1. **ScreenPipe must be running** on `localhost:3030`
   - Install from: https://screenpi.pe/
   - Or run: `curl -fsSL get.screenpi.pe/cli | sh && screenpipe`

2. **Node.js** (version 18+)

## Setup

```bash
# Install dependencies
npm install

# Run the streamer
npm start
```

## Available Commands

- `npm start` - Run the polling-based streamer (recommended)
- `npm run websocket` - Run the WebSocket-based streamer (may have connection issues)
- `npm run test` - Test WebSocket connectivity

## Example Output

```
📊 ScreenPipe Status:
   Frame Status: ok
   Audio Status: ok
   UI Status: disabled
   Last Frame: 7/13/2025, 5:52:22 AM

🚀 Window Text Streamer (Polling Mode) Starting...
✅ ScreenPipe is running and healthy
⚡ Polling every 1 second for active window text...

[5:52:15 AM] 🎯 Cursor - my-file.tsx
📝 const myFunction = () => {
  console.log("Hello world");
}
────────────────────────────────────────────────────────────

[5:52:17 AM] 🎯 ChatGPT - ChatGPT  
📝 How can I improve my JavaScript code performance?
────────────────────────────────────────────────────────────
```

## How it Works

### Polling Mode (Recommended)
- Queries ScreenPipe's REST API every 1 second
- Fetches recent OCR data from `http://localhost:3030/search`
- Filters for focused windows with meaningful text
- Reliable and works consistently

### WebSocket Mode (Experimental)
- Connects to `ws://localhost:3030/ws/events`
- Should stream real-time vision events
- May have connection issues depending on ScreenPipe configuration

## Troubleshooting

### "Cannot connect to ScreenPipe"
- Make sure ScreenPipe is running: `curl http://localhost:3030/health`
- Check if the process is running: `ps aux | grep screenpipe`
- Restart ScreenPipe if needed

### "No text appearing"
- Make sure you have windows with text content open
- ScreenPipe needs screen recording permissions on macOS
- Try switching between different apps to trigger OCR

### WebSocket Issues
- The polling mode is more reliable
- WebSocket may not stream events depending on ScreenPipe version/config
- Use `npm run test` to diagnose WebSocket connectivity

## Files

- `window-text-streamer-polling.js` - Main polling-based implementation
- `window-text-streamer.js` - WebSocket-based implementation  
- `test-websocket.js` - WebSocket connectivity tester
- `package.json` - Dependencies and scripts

## Use Cases

- Monitor what you're reading/working on
- Create activity logs
- Build awareness tools
- Debug screen capture workflows
- Develop ScreenPipe-based applications

Press `Ctrl+C` to stop the streamer at any time.
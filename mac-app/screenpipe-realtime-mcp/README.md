# ScreenPipe Real-time MCP Server

A Model Context Protocol (MCP) server that provides AI agents with real-time access to window content via ScreenPipe, including OCR text extraction and screenshots.

## Features

🎯 **Real-time Window Monitoring**
- Streams active window content every 2 seconds
- OCR text extraction from focused windows  
- Optional screenshot capture
- Automatic change detection

📊 **Rich Context for AI Agents**
- Current window state (app name, title, text content)
- Historical window content search
- Base64-encoded screenshots for visual context
- Focused window detection

🔍 **Powerful Search Capabilities**
- Search through historical screen recordings
- Filter by app name, window title, time range
- Full-text search across OCR content
- Include screenshots in search results

⚡ **MCP Integration**
- Works with Claude Desktop and other MCP clients
- Standard MCP tool interface
- Real-time status monitoring
- Error handling and reconnection

## Prerequisites

1. **ScreenPipe** must be running on `localhost:3030`
   - Install: `curl -fsSL get.screenpi.pe/cli | sh && screenpipe`
   - Or download from: https://screenpi.pe/

2. **Node.js** 18+ 

3. **MCP-compatible client** (Claude Desktop, etc.)

## Installation

```bash
cd screenpipe-realtime-mcp
npm install
```

## Testing the Server Standalone

```bash
# Test the MCP server directly
npm start

# Or with the MCP Inspector
npx @modelcontextprotocol/inspector node server.js
```

## Claude Desktop Integration

### 1. Configure Claude Desktop

Edit the Claude Desktop configuration file:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\\Claude\\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "screenpipe-realtime": {
      "command": "node",
      "args": ["/absolute/path/to/screenpipe-realtime-mcp/server.js"],
      "env": {}
    }
  }
}
```

### 2. Restart Claude Desktop

After making changes, restart Claude Desktop completely.

### 3. Verify Integration

In Claude Desktop, the server should appear in the MCP section. You can test with:

- "What's currently on my screen?"
- "Start monitoring my window changes"
- "Search for 'authentication' in my recent screen activity"

## Available Tools

### `get_current_window`
Get the current active window content including OCR text and optional screenshot.

**Parameters:**
- `include_screenshot` (boolean): Include base64 screenshot (default: true)
- `include_text` (boolean): Include OCR extracted text (default: true)

### `start_window_monitoring`
Start real-time monitoring of window changes (updates every 2 seconds).

**Parameters:**
- `auto_screenshots` (boolean): Auto-capture screenshots (default: true)

### `stop_window_monitoring`
Stop real-time window monitoring.

### `search_window_history`
Search through historical window content with advanced filtering.

**Parameters:**
- `query` (string): Text to search for
- `app_name` (string): Filter by application name
- `window_name` (string): Filter by window title  
- `start_time` (string): ISO timestamp for start of search
- `end_time` (string): ISO timestamp for end of search
- `limit` (number): Max results (default: 10)
- `include_screenshots` (boolean): Include screenshots (default: false)

### `get_screenpipe_status`
Check ScreenPipe health and system status.

## Example Usage with Claude

```
User: "What's currently on my screen?"
Claude: [calls get_current_window] 

User: "Start monitoring my window changes and let me know when I switch to VS Code"
Claude: [calls start_window_monitoring, then monitors for VS Code]

User: "Find any mentions of 'API key' from the last hour"
Claude: [calls search_window_history with time filter and query]

User: "Show me what I was working on in Chrome yesterday"
Claude: [calls search_window_history with app_name="Chrome" and date filter]
```

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   AI Agent      │◄──►│ MCP Server       │◄──►│ ScreenPipe API  │
│ (Claude, etc.)  │    │ (this project)   │    │ localhost:3030  │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │
                                ▼
                       ┌──────────────────┐
                       │ Real-time        │
                       │ Window Polling   │
                       │ (every 2s)       │
                       └──────────────────┘
```

## Data Flow

1. **Real-time Monitoring**: Server polls ScreenPipe API every 2 seconds for window changes
2. **OCR Extraction**: Gets text content from focused windows via ScreenPipe's OCR
3. **Screenshot Capture**: Retrieves base64-encoded screenshots when requested
4. **MCP Interface**: Exposes data to AI agents via standardized MCP tools
5. **Agent Interaction**: AI agents can query current state or search history

## Output Examples

### Current Window
```
🎯 Current Window: Cursor - my-file.tsx
🕒 Timestamp: 7/13/2025, 1:30:45 PM
🎯 Focused: Yes

📝 Extracted Text:
const myFunction = () => {
  console.log("Hello world");
}
```

### Search Results
```
🔍 Search Results (3 found):

1. Chrome - GitHub Repository
⏰ 7/13/2025, 1:25:30 PM  
📝 API authentication methods for OAuth2...

2. Terminal - bash
⏰ 7/13/2025, 1:20:15 PM
📝 npm install @auth/core...

3. VS Code - config.ts
⏰ 7/13/2025, 1:15:00 PM
📝 const API_KEY = process.env.OPENAI_API_KEY...
```

## Troubleshooting

### "ScreenPipe not running"
- Check: `curl http://localhost:3030/health`
- Start ScreenPipe: `screenpipe`
- Verify process: `ps aux | grep screenpipe`

### "No MCP tools visible in Claude"
- Verify the config file path is correct
- Use absolute paths in the configuration
- Restart Claude Desktop completely
- Check Claude's MCP section for error messages

### "No window content detected"
- Make sure ScreenPipe has screen recording permissions (macOS)
- Try switching between different applications
- Check if ScreenPipe is actually capturing: visit `http://localhost:3030/search?limit=1`

### "Screenshots not appearing"
- Screenshots are base64-encoded in MCP responses
- Some MCP clients may not display images
- Use `include_screenshot: false` for text-only responses

## Development

```bash
# Development with auto-restart
npm run dev

# Test MCP interface
npm test

# Debug with MCP Inspector
npx @modelcontextprotocol/inspector node server.js
```

## Use Cases

- **Productivity Monitoring**: Track what applications you're using
- **Context-Aware AI**: Provide AI with visual context of your work
- **Activity Logging**: Search through your screen activity history  
- **Focus Tracking**: Monitor window switches and time spent
- **Development Assistance**: AI can see your code and provide contextual help
- **Meeting Notes**: OCR text from video calls and presentations

## Security Notes

- All data stays local (ScreenPipe doesn't send data externally)
- Screenshots are processed locally and only sent to your chosen AI agent
- The MCP server only exposes data that ScreenPipe has already captured
- No data leaves your machine without explicit AI agent requests
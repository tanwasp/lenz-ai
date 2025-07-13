#!/usr/bin/env node

/**
 * ScreenPipe Real-time MCP Server
 * 
 * Provides real-time window content streaming with OCR and screenshots
 * for AI agents via the Model Context Protocol (MCP)
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';
import fetch from 'node-fetch';
import WebSocket from 'ws';

/**
 * ScreenPipe integration for real-time window monitoring
 */
class ScreenPipeRealtime {
  constructor() {
    this.currentWindowState = null;
    this.isStreaming = false;
    this.ws = null;
    this.lastUpdate = null;
    this.subscribers = new Set();
  }

  async getLatestWindowContent(includeScreenshot = true) {
    try {
      // Get recent OCR data (last 5 seconds)
      const fiveSecondsAgo = new Date(Date.now() - 5000).toISOString();
      const response = await fetch(
        `http://localhost:3030/search?limit=1&content_type=ocr&start_time=${fiveSecondsAgo}&focused=true`
      );
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      const results = data.data || [];
      
      if (results.length === 0) {
        return null;
      }

      const latestResult = results[0];
      const content = latestResult.content;
      
      // Build window state object
      const windowState = {
        timestamp: content.timestamp,
        appName: content.app_name || 'Unknown',
        windowName: content.window_name || 'Unknown',
        text: content.text || '',
        focused: content.focused || false,
        screenshot: null
      };

      // Get screenshot if requested and available
      if (includeScreenshot && content.frame) {
        windowState.screenshot = content.frame;
      } else if (includeScreenshot) {
        // Try to get latest screenshot from search with frames
        try {
          const frameResponse = await fetch(
            `http://localhost:3030/search?limit=1&content_type=ocr&include_frames=true&start_time=${fiveSecondsAgo}`
          );
          const frameData = await frameResponse.json();
          if (frameData.data && frameData.data[0] && frameData.data[0].content.frame) {
            windowState.screenshot = frameData.data[0].content.frame;
          }
        } catch (error) {
          console.error('Failed to get screenshot:', error.message);
        }
      }

      return windowState;
    } catch (error) {
      console.error('Error getting latest window content:', error.message);
      return null;
    }
  }

  async startRealtimeMonitoring() {
    if (this.isStreaming) return;
    
    console.error('📡 Starting real-time window monitoring...');
    this.isStreaming = true;
    
    // Poll every 2 seconds for updates
    const pollInterval = setInterval(async () => {
      if (!this.isStreaming) {
        clearInterval(pollInterval);
        return;
      }
      
      try {
        const windowState = await this.getLatestWindowContent(true);
        if (windowState && windowState.timestamp !== this.lastUpdate) {
          this.currentWindowState = windowState;
          this.lastUpdate = windowState.timestamp;
          
          // Notify subscribers
          this.notifySubscribers(windowState);
        }
      } catch (error) {
        console.error('Error in polling loop:', error.message);
      }
    }, 2000);
  }

  stopRealtimeMonitoring() {
    console.error('🛑 Stopping real-time window monitoring...');
    this.isStreaming = false;
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  notifySubscribers(windowState) {
    console.error(`📱 New window update: ${windowState.appName} - ${windowState.windowName}`);
    // In a full implementation, this would notify MCP clients
    // For now, we just log the update
  }

  async checkHealth() {
    try {
      const response = await fetch('http://localhost:3030/health');
      return response.ok;
    } catch (error) {
      return false;
    }
  }
}

/**
 * MCP Server implementation
 */
class ScreenPipeMCPServer {
  constructor() {
    this.server = new Server(
      {
        name: 'screenpipe-realtime',
        version: '1.0.0',
      },
      {
        capabilities: {
          tools: {},
        },
      }
    );

    this.screenpipe = new ScreenPipeRealtime();
    this.setupToolHandlers();
  }

  setupToolHandlers() {
    // List available tools
    this.server.setRequestHandler(ListToolsRequestSchema, async () => {
      return {
        tools: [
          {
            name: 'get_current_window',
            description: 'Get the current active window content including OCR text and optional screenshot',
            inputSchema: {
              type: 'object',
              properties: {
                include_screenshot: {
                  type: 'boolean',
                  description: 'Whether to include a base64-encoded screenshot of the window',
                  default: true,
                },
                include_text: {
                  type: 'boolean', 
                  description: 'Whether to include OCR extracted text',
                  default: true,
                },
              },
            },
          },
          {
            name: 'start_window_monitoring',
            description: 'Start real-time monitoring of window changes (OCR + screenshots every 2 seconds)',
            inputSchema: {
              type: 'object',
              properties: {
                auto_screenshots: {
                  type: 'boolean',
                  description: 'Whether to automatically capture screenshots with each update',
                  default: true,
                },
              },
            },
          },
          {
            name: 'stop_window_monitoring', 
            description: 'Stop real-time window monitoring',
            inputSchema: {
              type: 'object',
              properties: {},
            },
          },
          {
            name: 'search_window_history',
            description: 'Search through historical window content (OCR text) with time range and filters',
            inputSchema: {
              type: 'object',
              properties: {
                query: {
                  type: 'string',
                  description: 'Text to search for in window content',
                },
                app_name: {
                  type: 'string', 
                  description: 'Filter by application name (e.g., "Chrome", "Terminal")',
                },
                window_name: {
                  type: 'string',
                  description: 'Filter by window title',
                },
                start_time: {
                  type: 'string',
                  description: 'Start time in ISO format (e.g., "2024-01-01T00:00:00Z")',
                },
                end_time: {
                  type: 'string', 
                  description: 'End time in ISO format',
                },
                limit: {
                  type: 'number',
                  description: 'Maximum number of results to return',
                  default: 10,
                },
                include_screenshots: {
                  type: 'boolean',
                  description: 'Whether to include screenshots in results',
                  default: false,
                },
              },
            },
          },
          {
            name: 'get_screenpipe_status',
            description: 'Check if ScreenPipe is running and get system status',
            inputSchema: {
              type: 'object',
              properties: {},
            },
          },
        ],
      };
    });

    // Handle tool calls
    this.server.setRequestHandler(CallToolRequestSchema, async (request) => {
      try {
        return await this.handleToolCall(request.params.name, request.params.arguments || {});
      } catch (error) {
        return {
          content: [
            {
              type: 'text',
              text: `Error executing tool ${request.params.name}: ${error.message}`,
            },
          ],
        };
      }
    });
  }

  async handleToolCall(name, args) {
    switch (name) {
      case 'get_current_window':
        return await this.getCurrentWindow(args);
      
      case 'start_window_monitoring':
        return await this.startWindowMonitoring(args);
        
      case 'stop_window_monitoring':
        return await this.stopWindowMonitoring(args);
        
      case 'search_window_history':
        return await this.searchWindowHistory(args);
        
      case 'get_screenpipe_status':
        return await this.getScreenPipeStatus(args);
        
      default:
        throw new Error(`Unknown tool: ${name}`);
    }
  }

  async getCurrentWindow(args) {
    const includeScreenshot = args.include_screenshot !== false;
    const includeText = args.include_text !== false;
    
    const windowState = await this.screenpipe.getLatestWindowContent(includeScreenshot);
    
    if (!windowState) {
      return {
        content: [
          {
            type: 'text',
            text: 'No current window content available. Make sure ScreenPipe is running and capturing data.',
          },
        ],
      };
    }

    const content = [];
    
    // Add text content
    if (includeText) {
      const textContent = [
        `🎯 **Current Window**: ${windowState.appName} - ${windowState.windowName}`,
        `🕒 **Timestamp**: ${new Date(windowState.timestamp).toLocaleString()}`,
        `🎯 **Focused**: ${windowState.focused ? 'Yes' : 'No'}`,
        '',
        '📝 **Extracted Text**:',
        windowState.text || '(No text detected)',
      ].join('\n');

      content.push({
        type: 'text',
        text: textContent,
      });
    }

    // Add screenshot if available
    if (includeScreenshot && windowState.screenshot) {
      content.push({
        type: 'image',
        data: windowState.screenshot,
        mimeType: 'image/png',
      });
    }

    return { content };
  }

  async startWindowMonitoring(args) {
    await this.screenpipe.startRealtimeMonitoring();
    
    return {
      content: [
        {
          type: 'text',
          text: '🚀 Started real-time window monitoring. The system will now track window changes every 2 seconds.\n\nUse `get_current_window` to see the latest captured content, or `stop_window_monitoring` to stop.',
        },
      ],
    };
  }

  async stopWindowMonitoring(args) {
    this.screenpipe.stopRealtimeMonitoring();
    
    return {
      content: [
        {
          type: 'text',
          text: '🛑 Stopped real-time window monitoring.',
        },
      ],
    };
  }

  async searchWindowHistory(args) {
    try {
      // Build search parameters
      const params = new URLSearchParams();
      
      if (args.query) params.append('q', args.query);
      if (args.app_name) params.append('app_name', args.app_name);
      if (args.window_name) params.append('window_name', args.window_name);
      if (args.start_time) params.append('start_time', args.start_time);
      if (args.end_time) params.append('end_time', args.end_time);
      if (args.include_screenshots) params.append('include_frames', 'true');
      
      params.append('content_type', 'ocr');
      params.append('limit', (args.limit || 10).toString());

      const response = await fetch(`http://localhost:3030/search?${params}`);
      
      if (!response.ok) {
        throw new Error(`Search failed: ${response.status}`);
      }

      const data = await response.json();
      const results = data.data || [];

      if (results.length === 0) {
        return {
          content: [
            {
              type: 'text',
              text: 'No matching window content found in the specified time range.',
            },
          ],
        };
      }

      const content = [];
      
      // Format search results
      let textResults = `🔍 **Search Results** (${results.length} found):\n\n`;
      
      results.forEach((result, index) => {
        const c = result.content;
        textResults += [
          `**${index + 1}. ${c.app_name || 'Unknown'} - ${c.window_name || 'Unknown'}**`,
          `⏰ ${new Date(c.timestamp).toLocaleString()}`,
          `📝 ${(c.text || '').substring(0, 200)}${c.text && c.text.length > 200 ? '...' : ''}`,
          '',
        ].join('\n');
      });

      content.push({
        type: 'text', 
        text: textResults,
      });

      // Add screenshots if requested and available
      if (args.include_screenshots) {
        results.forEach((result, index) => {
          if (result.content.frame) {
            content.push({
              type: 'image',
              data: result.content.frame,
              mimeType: 'image/png',
            });
          }
        });
      }

      return { content };
    } catch (error) {
      throw new Error(`Search failed: ${error.message}`);
    }
  }

  async getScreenPipeStatus(args) {
    try {
      const isHealthy = await this.screenpipe.checkHealth();
      
      if (!isHealthy) {
        return {
          content: [
            {
              type: 'text',
              text: '❌ **ScreenPipe Status**: Not running or not accessible\n\nPlease make sure ScreenPipe is running on localhost:3030',
            },
          ],
        };
      }

      const response = await fetch('http://localhost:3030/health');
      const status = await response.json();
      
      const statusText = [
        '✅ **ScreenPipe Status**: Running and healthy',
        '',
        `📊 **System Status**:`,
        `• Frame Status: ${status.frame_status}`,
        `• Audio Status: ${status.audio_status}`, 
        `• UI Status: ${status.ui_status}`,
        `• Last Frame: ${new Date(status.last_frame_timestamp).toLocaleString()}`,
        `• Last Audio: ${status.last_audio_timestamp ? new Date(status.last_audio_timestamp).toLocaleString() : 'N/A'}`,
        '',
        `💻 **Device Details**:`,
        `${status.device_status_details || 'No device details available'}`,
        '',
        `📈 **Real-time Monitoring**: ${this.screenpipe.isStreaming ? 'Active' : 'Stopped'}`,
      ].join('\n');

      return {
        content: [
          {
            type: 'text',
            text: statusText,
          },
        ],
      };
    } catch (error) {
      throw new Error(`Status check failed: ${error.message}`);
    }
  }

  async run() {
    const transport = new StdioServerTransport();
    await this.server.connect(transport);
    console.error('🚀 ScreenPipe Real-time MCP Server running...');
  }
}

// Main execution
async function main() {
  const server = new ScreenPipeMCPServer();
  await server.run();
}

// Handle graceful shutdown
process.on('SIGINT', () => {
  console.error('\n🛑 Shutting down MCP server...');
  process.exit(0);
});

// Only run if this file is executed directly
if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch(console.error);
}

export { ScreenPipeMCPServer };
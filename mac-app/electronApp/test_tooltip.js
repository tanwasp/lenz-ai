#!/usr/bin/env node
/**
 * test_tooltip.js — quick manual check that the overlay tooltip works.
 *
 * Usage:
 *    node test_tooltip.js "Your message" 5
 *
 * Sends JSON {text, duration} to /tmp/screenpipe_tooltip.sock.  If the
 * Electron app is running with the socket code, you should see the bubble.
 */

const net = require('net');
const fs  = require('fs');

const SOCK = '/tmp/screenpipe_tooltip.sock';
if (!fs.existsSync(SOCK)) {
  console.error('Socket not found:', SOCK);
  process.exit(1);
}

const text = process.argv[2] || 'Hello from test_tooltip.js';
const duration = parseInt(process.argv[3] || '5', 10);
const payload = JSON.stringify({ text, duration });

const client = net.createConnection(SOCK, () => {
  client.write(payload, () => {
    console.log('Sent payload:', payload);
    client.end();
  });
});

client.on('error', err => {
  console.error('Socket error:', err.message);
  process.exit(1);
}); 
#!/usr/bin/env node
/**
 * Launch the Electron app with a one-off tooltip via CLI flag.
 *
 * Usage:
 *    node test_tooltip_cli.js "Some tip" 4
 */

const { spawn } = require('child_process');
const path = require('path');
const text = process.argv[2] || 'Hello from CLI tooltip';
const duration = parseInt(process.argv[3] || '5', 10);

const payload = Buffer.from(JSON.stringify({ text, duration }), 'utf8').toString('base64');
const electron = require('electron');

const child = spawn(electron, ['.', `--tooltip=${encodeURIComponent(payload)}`], {
  stdio: 'inherit',
  cwd: __dirname,
});

child.on('exit', code => process.exit(code)); 
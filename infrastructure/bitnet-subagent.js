#!/usr/bin/env node

/**
 * BitNet Sub-Agent Wrapper
 * 
 * Runs BitNet inference server locally and exposes via HTTP API.
 * Communicates with main agent via sessions_send.
 * Posts results to Telegram.
 * 
 * Usage: node bitnet-subagent.js
 */

const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');

const BITNET_DIR = '/home/brad/BitNet';
const MODEL_PATH = `${BITNET_DIR}/models/BitNet-b1.58-2B-4T/ggml-model-i2_s.gguf`;
const PORT = 8888;
const VENV = `${BITNET_DIR}/bitnet-env/bin/python`;

console.log('[BitNet] Starting inference server...');

// Spawn BitNet inference server
const server = spawn(VENV, [
  `${BITNET_DIR}/inference.py`,
  '--model', MODEL_PATH,
  '--port', PORT.toString(),
], {
  cwd: BITNET_DIR,
  env: {
    ...process.env,
    VIRTUAL_ENV: `${BITNET_DIR}/bitnet-env`,
    PATH: `${BITNET_DIR}/bitnet-env/bin:${process.env.PATH}`,
  },
  stdio: ['pipe', 'pipe', 'pipe'],
});

server.stdout.on('data', (data) => {
  console.log(`[BitNet STDOUT] ${data}`);
});

server.stderr.on('data', (data) => {
  console.error(`[BitNet STDERR] ${data}`);
});

server.on('error', (err) => {
  console.error('[BitNet] Server spawn error:', err);
  process.exit(1);
});

server.on('exit', (code, signal) => {
  console.log(`[BitNet] Server exited with code ${code}, signal ${signal}`);
  process.exit(code);
});

// Simple HTTP wrapper for task routing
const wrapper = http.createServer((req, res) => {
  if (req.method === 'POST' && req.url === '/infer') {
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', () => {
      try {
        const payload = JSON.parse(body);
        const { prompt, max_tokens = 256 } = payload;

        // Forward to BitNet server
        const options = {
          hostname: 'localhost',
          port: PORT,
          path: '/infer',
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
        };

        const bitnetReq = http.request(options, (bitnetRes) => {
          let data = '';
          bitnetRes.on('data', chunk => data += chunk);
          bitnetRes.on('end', () => {
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(data);
          });
        });

        bitnetReq.write(JSON.stringify({ prompt, max_tokens }));
        bitnetReq.end();
      } catch (e) {
        res.writeHead(400, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: e.message }));
      }
    });
  } else if (req.url === '/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: 'ok' }));
  } else {
    res.writeHead(404);
    res.end();
  }
});

wrapper.listen(9999, '127.0.0.1', () => {
  console.log('[BitNet Wrapper] HTTP API listening on http://127.0.0.1:9999');
});

process.on('SIGTERM', () => {
  console.log('[BitNet] SIGTERM received, shutting down...');
  server.kill();
  wrapper.close();
});

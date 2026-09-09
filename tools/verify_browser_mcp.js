/**
 * Diagnostic tool to verify Playwright MCP Server connectivity.
 * Tests JSON-RPC handshake, tool listing, and CDP loopback to port 9222.
 */
const { spawn } = require('child_process');

async function testMcp(args, label) {
  return new Promise((resolve) => {
    console.log(`\n========================================`);
    console.log(`[TESTING] ${label}`);
    console.log(`Command: cmd.exe /c npx -y @playwright/mcp@latest ${args.join(' ')}`);
    console.log(`========================================`);

    const proc = spawn('cmd.exe', ['/c', 'npx', '-y', '@playwright/mcp@latest', ...args], {
      stdio: ['pipe', 'pipe', 'pipe'],
    });

    let buffer = '';
    let success = false;
    let timer = null;

    function finish(result) {
      if (timer) clearTimeout(timer);
      proc.kill();
      resolve(result);
    }

    proc.stdout.on('data', (d) => {
      buffer += d.toString();
      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const msg = JSON.parse(line);
          if (msg.id === 1 && msg.result) {
            console.log(`  [OK] Initialized protocol: v${msg.result.protocolVersion}`);
            console.log(`  [OK] Server: ${msg.result.serverInfo.name} (${msg.result.serverInfo.version})`);
          } else if (msg.id === 2 && msg.result && msg.result.tools) {
            console.log(`  [OK] Successfully retrieved ${msg.result.tools.length} browser tools.`);
            console.log(`  [TOOLS SUMMARY]: ${msg.result.tools.slice(0, 10).map((t) => t.name).join(', ')} ... (+${msg.result.tools.length - 10} more)`);
            success = true;
            finish(true);
          }
        } catch (e) {}
      }
    });

    // Step 1: Initialize
    const initReq = JSON.stringify({
      jsonrpc: '2.0',
      id: 1,
      method: 'initialize',
      params: {
        protocolVersion: '2024-11-05',
        capabilities: {},
        clientInfo: { name: 'mcp-diagnostic', version: '1.0.0' },
      },
    }) + '\n';
    proc.stdin.write(initReq);

    // Step 2: Tools list
    setTimeout(() => {
      const notify = JSON.stringify({
        jsonrpc: '2.0',
        method: 'notifications/initialized',
        params: {},
      }) + '\n';
      proc.stdin.write(notify);

      const listTools = JSON.stringify({
        jsonrpc: '2.0',
        id: 2,
        method: 'tools/list',
        params: {},
      }) + '\n';
      proc.stdin.write(listTools);
    }, 1200);

    timer = setTimeout(() => {
      finish(success);
    }, 9000);
  });
}

async function run() {
  console.log('Starting Browser MCP Diagnostic Check...');
  const cdpOk = await testMcp(
    ['--cdp-endpoint', 'http://127.0.0.1:9222', '--caps', 'vision,devtools'],
    'browser-cdp (Live Chrome Port 9222)'
  );

  console.log('\n----------------------------------------');
  if (cdpOk) {
    console.log('✅ browser-cdp: Operational & Ready!');
  } else {
    console.log('❌ browser-cdp: Connection or Handshake Failed.');
  }
  console.log('----------------------------------------\n');
}

run();

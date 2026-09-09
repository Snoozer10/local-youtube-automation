Install and configure lean-ctx on my machine. Follow these exact steps:

1. INSTALL THE BINARY:
   cargo install lean-ctx

2. VERIFY:
   lean-ctx --version
   (Expected: lean-ctx 3.x or newer)

3. CONNECT ALL AI TOOLS (shell hooks + editor config):
   lean-ctx onboard
   # Restart PowerShell after this
   lean-ctx init --agent opencode   # optional: re-run to force a mode

   OpenCode uses ~/.config/opencode/opencode.json with an "mcp" root key.

4. MANUAL FALLBACK (only if step 3 did not configure OpenCode):
   Run: lean-ctx init --agent opencode (writes config + installs rules).

5. INSTALL AGENT INSTRUCTIONS:
   lean-ctx init --agent opencode

6. RESTART:
   Restart OpenCode.

7. VERIFY EVERYTHING:
   lean-ctx doctor
   All checks should show green.
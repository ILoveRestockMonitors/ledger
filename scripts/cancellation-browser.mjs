#!/usr/bin/env node
/* Stdio bridge to the pinned Playwright MCP CLI, one profile per Ledger job. */
import { appendFileSync, mkdirSync } from "node:fs";
import { spawn } from "node:child_process";
import { resolve } from "node:path";

const jobId = process.env.LEDGER_BROWSER_JOB_ID || "interactive";
const workspace = resolve(process.env.LEDGER_BROWSER_WORKSPACE || `/tmp/ledger-cancellation-${jobId}`);
const profile = resolve(process.env.LEDGER_BROWSER_PROFILE || `${workspace}/browser-profile`);
const receiptPath = resolve(workspace, "browser-receipts.jsonl");
const mcpCli = resolve(process.env.LEDGER_PLAYWRIGHT_MCP_CLI || "/app/node_modules/@playwright/mcp/cli.js");
if (workspace === "/" || profile === "/" || !profile.startsWith(`${workspace}/`)) {
  console.error("Ledger browser bridge requires a job-scoped profile inside its workspace");
  process.exit(2);
}
mkdirSync(workspace, { recursive: true, mode: 0o700 });
mkdirSync(profile, { recursive: true, mode: 0o700 });

const origins = (process.env.LEDGER_BROWSER_ALLOWED_ORIGINS || "").split(";").map((v) => v.trim()).filter(Boolean);
const hosts = (process.env.LEDGER_BROWSER_ALLOWED_HOSTS || "").split(",").map((v) => v.trim()).filter(Boolean);
if (!origins.length || !hosts.length) {
  console.error("Ledger browser bridge requires explicit provider origin and host allowlists");
  process.exit(2);
}
const args = [mcpCli, "--browser", "chromium", "--user-data-dir", profile,
  "--allowed-hosts", hosts.join(","), "--allowed-origins", origins.join(";")];
if (process.env.LEDGER_BROWSER_HEADLESS === "1") args.push("--headless");

const child = spawn(process.execPath, args, {
  cwd: workspace,
  env: {
    PATH: process.env.PATH || "", HOME: process.env.HOME || workspace,
    USER: process.env.USER || "ledger", LOGNAME: process.env.LOGNAME || "ledger",
    LANG: process.env.LANG || "C.UTF-8", CODEX_HOME: process.env.CODEX_HOME || "",
    DISPLAY: process.env.DISPLAY || "", WAYLAND_DISPLAY: process.env.WAYLAND_DISPLAY || "",
    XDG_RUNTIME_DIR: process.env.XDG_RUNTIME_DIR || "",
    PLAYWRIGHT_BROWSERS_PATH: process.env.PLAYWRIGHT_BROWSERS_PATH || "",
    LEDGER_BROWSER_JOB_ID: jobId, PLAYWRIGHT_MCP_USER_DATA_DIR: profile,
  },
  stdio: ["pipe", "pipe", "inherit"], shell: false,
});

// Keep the MCP protocol lossless while recording only public provider URLs,
// visible text, and capture date. The backend cross-checks completion claims
// against this private receipt file before changing subscription state.
const requests = new Map();
let stdinBuffer = "";
let stdoutBuffer = "";
function record(line) {
  try {
    const response = JSON.parse(line);
    const request = requests.get(response.id);
    if (!response.result || !request) return;
    const serialized = JSON.stringify(response.result);
    const urls = [...serialized.matchAll(/https:\/\/[^"\s\\]+/g)].map((m) => m[0]);
    const text = serialized.replace(/\\n/g, " ").slice(0, 20000);
    if (!urls.length && !text) return;
    appendFileSync(receiptPath, JSON.stringify({ rpc_id: response.id, tool: request.name,
      urls, text, date: new Date().toISOString().slice(0, 10) }) + "\n", { mode: 0o600 });
  } catch { /* protocol output remains untouched */ }
}
process.stdin.on("data", (chunk) => {
  stdinBuffer += chunk.toString();
  const lines = stdinBuffer.split("\n");
  stdinBuffer = lines.pop() || "";
  for (const line of lines) {
    if (!line.trim()) continue;
    try { const req = JSON.parse(line); if (req.method === "tools/call") requests.set(req.id, req.params || {}); } catch { /* child reports protocol errors */ }
    child.stdin.write(line + "\n");
  }
});
child.stdout.on("data", (chunk) => {
  stdoutBuffer += chunk.toString();
  const lines = stdoutBuffer.split("\n"); stdoutBuffer = lines.pop() || "";
  for (const line of lines) { if (line.trim()) record(line); process.stdout.write(line + "\n"); }
});
process.stdin.on("end", () => child.stdin.end());
child.on("error", (error) => { console.error(`Unable to start pinned @playwright/mcp: ${error.message}`); process.exitCode = 1; });
child.on("exit", (code, signal) => { if (signal) process.kill(process.pid, signal); else process.exitCode = code ?? 1; });

#!/usr/bin/env node
/* Minimal read-only MCP server backed directly by Playwright. */
import { appendFileSync, mkdirSync, statSync } from "node:fs";
import { resolve } from "node:path";

const jobId = process.env.LEDGER_RECEIPT_JOB_ID || "interactive";
const workspace = resolve(process.env.LEDGER_RECEIPT_WORKSPACE || `/tmp/ledger-receipt-${jobId}`);
const profile = resolve(process.env.LEDGER_RECEIPT_PROFILE || `${workspace}/browser-profile`);
const capturePath = resolve(workspace, "receipt-captures.jsonl");
const hosts = (process.env.LEDGER_RECEIPT_ALLOWED_HOSTS || "").split(",").map((v) => v.trim().toLowerCase()).filter(Boolean);
const MAX_INPUT_BYTES = 256 * 1024;
const MAX_CAPTURE_BYTES = 2 * 1024 * 1024;
const MAX_TOOL_CALLS = 80;
const MUTATION_URL = /(?:^|[\/_?=&-])(cart|add-to-cart|buy-now|checkout|refund|cancel|delete|subscribe|signout|sign-out|logout|remove|pay|purchase)(?:$|[\/_?=&-])/i;
if (workspace === "/" || profile === "/" || (!profile.startsWith(`${workspace}/`) && !profile.includes("/profiles/")) || !hosts.length) {
  console.error("Receipt bridge requires a private workspace, profile, and selected-provider allowlist");
  process.exit(2);
}
mkdirSync(workspace, { recursive: true, mode: 0o700 });
mkdirSync(profile, { recursive: true, mode: 0o700 });

let page = null;
let context = null;
const fake = process.env.LEDGER_RECEIPT_FAKE_BROWSER === "1";
let sequence = 0;
let chain = Promise.resolve();
let toolCalls = 0;
let captureBytes = (() => { try { return statSync(capturePath).size; } catch { return 0; } })();

function parsedAllowed(value, preserveQuery = false) {
  try {
    const u = new URL(String(value));
    if (u.protocol !== "https:" || !u.hostname || u.username || u.password) return "";
    const host = u.hostname.toLowerCase().replace(/\.$/, "");
    if (!hosts.some((root) => host === root || host.endsWith(`.${root}`))) return "";
    const path = u.pathname || "/";
    let routeText = path + (preserveQuery ? u.search : "");
    try { routeText += " " + decodeURIComponent(routeText); } catch { return ""; }
    if (MUTATION_URL.test(routeText)) return "";
    return `https://${host}${path}${preserveQuery ? u.search : ""}`;
  } catch { return ""; }
}
function captureUrl(value) { return parsedAllowed(value, false); }
function navUrl(value) { return parsedAllowed(value, true); }

async function ensurePage() {
  if (page) return page;
  if (fake) {
    let current = "https://www.amazon.com/gp/order/123";
    page = { url: () => current, title: async () => "Amazon order",
      goto: async (url) => { current = navUrl(url); },
      bodyText: async () => "Order 123-4567890-1234567 Widget USD Total $12.34 Purchased August 31, 2026 Card ending in 4242",
      links: async () => [] };
    return page;
  }
  let chromium;
  try { ({ chromium } = await import("playwright")); }
  catch { throw new Error("The pinned Playwright dependency is not installed"); }
  context = await chromium.launchPersistentContext(profile, {
    // The container installs full Chromium with --no-shell.
    channel: "chromium",
    headless: process.env.LEDGER_RECEIPT_HEADLESS !== "0",
    viewport: { width: 1280, height: 900 },
  });
  context.on("close", () => { if (!process.stdin.readableEnded) process.exitCode = 0; });
  await context.route("**/*", async (route) => {
    const request = route.request();
    if (request.isNavigationRequest()) {
      let main = false;
      try { main = request.frame() === request.frame().page().mainFrame(); } catch { main = true; }
      if (main && !navUrl(request.url())) { await route.abort(); return; }
    }
    await route.continue();
  });
  page = context.pages()[0] || await context.newPage();
  return page;
}

async function visibleText(current) {
  if (current.bodyText) return String(await current.bodyText()).replace(/\s+/g, " ").trim().slice(0, 30000);
  return String(await current.locator("body").innerText({ timeout: 5000 })).replace(/\s+/g, " ").trim().slice(0, 30000);
}

async function pageLinks(current) {
  if (current.links) return await current.links();
  return await current.locator("a").evaluateAll((rows) => rows.map((a) => ({ text: (a.innerText || a.textContent || "").trim(), href: a.href })));
}

function capture(current, tool, text, actualUrl) {
  const url = captureUrl(actualUrl);
  if (!url || !text) throw new Error("Current page is outside the selected provider or has no visible text");
  const id = `capture_${Date.now()}_${sequence++}`;
  const line = JSON.stringify({ id, tool, url, text, captured_at: new Date().toISOString() }) + "\n";
  if (captureBytes + Buffer.byteLength(line) > MAX_CAPTURE_BYTES) throw new Error("receipt capture limit reached");
  appendFileSync(capturePath, line, { mode: 0o600 }); captureBytes += Buffer.byteLength(line);
  return id;
}

function send(value) { process.stdout.write(JSON.stringify(value) + "\n"); }
function response(id, result) { return { jsonrpc: "2.0", id, result }; }
function error(id, message, code = -32602) { return { jsonrpc: "2.0", id, error: { code, message } }; }

async function callTool(request) {
  const id = request.id; const name = request.params?.name; const args = request.params?.arguments || {};
  if (++toolCalls > MAX_TOOL_CALLS) { send(error(id, "Receipt lookup tool-call limit reached")); return; }
  if (!["browser_navigate", "browser_snapshot", "browser_links", "browser_wait_for"].includes(name)) {
    send(error(id, "Only read-only purchase-history tools are available")); return;
  }
  const current = await ensurePage();
  if (name === "browser_navigate") {
    const target = navUrl(args.url);
    if (!target) { send(error(id, "Navigation is limited to the selected provider HTTPS host")); return; }
    await current.goto(target, { waitUntil: "domcontentloaded", timeout: 30000 });
    const actual = navUrl(current.url());
    if (!actual) { send(error(id, "Provider navigation redirected outside the selected host")); return; }
    const text = await visibleText(current);
    const receiptId = capture(current, name, text, actual);
    const output = `receipt_capture_id=${receiptId} page_url=${actual}\n${text}`;
    send(response(id, { content: [{ type: "text", text: output }], structuredContent: { receipt_id: receiptId, url: actual, text }, url: actual, title: await current.title(), receipt_id: receiptId })); return;
  }
  if (name === "browser_snapshot") {
    const actual = navUrl(current.url()); const text = await visibleText(current);
    const receiptId = capture(current, name, text, actual);
    const output = `receipt_capture_id=${receiptId} page_url=${actual}\n${text}`;
    send(response(id, { content: [{ type: "text", text: output }], structuredContent: { receipt_id: receiptId, url: actual, text }, url: actual, title: await current.title(), receipt_id: receiptId })); return;
  }
  if (name === "browser_links") {
    const actual = navUrl(current.url());
    const rows = (await pageLinks(current)).map((row) => ({ text: String(row.text || "").replace(/\s+/g, " ").trim().slice(0, 300), href: navUrl(row.href) }))
      .filter((row) => row.href && row.text).slice(0, 200);
    send(response(id, { content: [{ type: "text", text: JSON.stringify(rows) }], url: actual })); return;
  }
  const ms = Math.max(0, Math.min(5000, Number(args.milliseconds || 500)));
  await new Promise((resolveWait) => setTimeout(resolveWait, Number.isFinite(ms) ? ms : 500));
  send(response(id, { content: [{ type: "text", text: "wait complete" }], url: navUrl(current.url()) }));
}

async function handle(request) {
  if (request.method === "initialize") {
    send(response(request.id, { protocolVersion: "2024-11-05", capabilities: { tools: { listChanged: false } }, serverInfo: { name: "ledger-receipt-browser", version: "1.0" } })); return;
  }
  if (request.method === "notifications/initialized") return;
  if (request.method === "tools/list") {
    send(response(request.id, { tools: [
      { name: "browser_navigate", description: "Navigate to an allowed provider purchase-history URL.", inputSchema: { type: "object", properties: { url: { type: "string" } }, required: ["url"], additionalProperties: false } },
      { name: "browser_snapshot", description: "Read visible text from the current provider page.", inputSchema: { type: "object", properties: {}, additionalProperties: false } },
      { name: "browser_links", description: "List visible same-provider links for finding order details.", inputSchema: { type: "object", properties: {}, additionalProperties: false } },
      { name: "browser_wait_for", description: "Wait briefly for a page to settle.", inputSchema: { type: "object", properties: { milliseconds: { type: "integer", minimum: 0, maximum: 5000 } }, additionalProperties: false } },
    ] })); return;
  }
  if (request.method === "tools/call") await callTool(request);
  else if (request.id !== undefined) send(error(request.id, "Method not supported", -32601));
}

let buffer = "";
process.stdin.on("data", (chunk) => {
  buffer += chunk.toString();
  if (Buffer.byteLength(buffer) > MAX_INPUT_BYTES) { console.error("Receipt browser input limit reached"); process.exit(2); }
  const lines = buffer.split("\n"); buffer = lines.pop() || "";
  for (const line of lines) {
    if (!line.trim()) continue;
    let request; try { request = JSON.parse(line); } catch { continue; }
    chain = chain.then(() => handle(request)).catch(() => { if (request.id !== undefined) send(error(request.id, "Receipt browser operation failed", -32000)); });
  }
});
process.stdin.on("end", async () => { await chain; if (context) await context.close(); });

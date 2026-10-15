#!/usr/bin/env node
// NextraAxisVM MCP bridge: stdio JSON-RPC (MCP) <-> Python worker (PyAxisVM) <-> AxisVM (COM, via the NextraAxisVM add-on).
// Zero dependencies (runs on any Node >= 18). The worker is one long-lived Python process; calls are serialized.
// First use without a Python environment: runs setup/setup.ps1 in the background and says so (no terminal needed).
// NEXTRA_MODE=ask exposes only view + query (read-only).
"use strict";
const fs = require("fs");
const path = require("path");
const os = require("os");
const { spawn } = require("child_process");
const readline = require("readline");

const VERSION = "0.1.0";
const MODE = (process.env.NEXTRA_MODE || "full").toLowerCase();
const APPDATA = process.env.APPDATA || path.join(os.homedir(), "AppData", "Roaming");
const LOCAL = process.env.LOCALAPPDATA || path.join(os.homedir(), "AppData", "Local");
const BASE = path.join(LOCAL, "NextraAxisVM");
const first = list => list.find(p => { try { return fs.existsSync(p); } catch { return false; } });
const ENGINE = first([path.join(__dirname, "engine"), path.join(__dirname, "..", "..", "engine")]);
const SETUP = first([path.join(__dirname, "setup", "setup.ps1"), path.join(__dirname, "..", "..", "setup", "setup.ps1")]);

function config() { try { return JSON.parse(fs.readFileSync(path.join(APPDATA, "NextraAxisVM", "config.json"), "utf8").replace(/^﻿/, "")); } catch { return {}; } }
function pythonPath() { return config().python || path.join(BASE, "venv", "Scripts", "python.exe"); }

const TOOLS = [
  {
    name: "view",
    description: "Image of the AxisVM model with an 8x8 grid (A-H x 1-8) and handle tags (n5 node, l12 line, d3 domain). Crowded → per-cell counts, then focus:'C3:E5'. focus also takes handles 'l3 d1' or a filter 'type:beam' (isolate hides the rest). Results: case|combo + result:'deformed'|'Nx'|'Vz'|'My'|'Mz'. target:'axisvm' = screenshot of AxisVM's own window (its result displays).",
    inputSchema: { type: "object", properties: {
      target: { type: "string", enum: ["model", "axisvm"] },
      view: { type: "string", description: "iso|top|front|back|left|right (axisvm: front|top|side|persp)" },
      focus: { type: "string", description: "cells 'C3:E5' of the last image | handles 'l3 d1' | filter 'type:beam'" },
      isolate: { type: "boolean" }, tags: { type: "string", enum: ["auto", "on", "off", "nodes"] },
      case: { type: "string" }, combo: { type: "string" }, result: { type: "string" }, scale: { type: "number" },
      size: { type: "array", items: { type: "number" }, description: "[w,h] px, default 800x600" },
    } },
  },
  {
    name: "query",
    description: "Text, cheapest first. model: summary → list (filter 'type:beam' 'l3 d1' 'section:IPE*' 'vertical' 'sel' 'bbox:…') → level:'detail'. loads: cases, loads per case (filter 'case:G'), combinations. results: case|combo, kind summary|displacements|reactions|forces|surface. catalog: 'IPE 3*' | 'material C30*'. api: installed AxisVM COM type library ('line load', 'IAxisVMLoads.AddBeamDistributed', 'RSurfaceAttr'). docs, library, status (works while AxisVM is busy; shows dialogs with a screenshot; answer:'<button>' presses it), instances.",
    inputSchema: { type: "object", properties: {
      scope: { type: "string", enum: ["model", "loads", "results", "catalog", "api", "docs", "library", "status", "instances"] },
      instance: { type: "string", description: "bind this session to the AxisVM with this file open (or pid); sticky; accepted by every tool" },
      filter: { type: "string" }, level: { type: "string", enum: ["summary", "list", "detail"] },
      case: { type: "string" }, combo: { type: "string" }, kind: { type: "string" },
      limit: { type: "integer" }, offset: { type: "integer" }, name: { type: "string" },
      answer: { type: "string", description: "status only: press this button in AxisVM's dialog (only if safe / user agreed)" },
    } },
  },
  {
    name: "edit",
    description: "Change the model with NextraAxisVM shorthand (one action per line, applied independently, per-line errors; grammar: query {scope:'docs', filter:'shorthand'}), e.g. 'column 0,0,0 0,0,3.5 sec=HEB 200 mat=S 235 @ x=0:6:12'. One AxisVM undo step + checkpoint; replies with the model delta. Also analyze:'linear' (meshes unmeshed domains), import (.dxf .ifc .axs .pdf, Rhino AxisBridge .json), export (.dxf .ifc), open/save/new, launch (start AxisVM).",
    inputSchema: { type: "object", properties: {
      ops: { type: "string" }, atomic: { type: "boolean" }, dry_run: { type: "boolean" }, label: { type: "string" },
      analyze: { type: "string", enum: ["linear"] }, mesh: { type: "string", description: "'all' | 'd1 d2' | 'all size=0.5'" }, mesh_size: { type: "number" },
      import: { type: "string" }, import_options: { type: "object" }, export: { type: "string" },
      open: { type: "string" }, save: { type: "string" }, new: { type: "boolean" }, launch: { type: "boolean" },
    } },
  },
  {
    name: "run",
    description: "Run Python on the bound AxisVM (one undo step + checkpoint + model delta). Names: app, model (raw COM), ax (enums/records), pyax (PyAxisVM), kit (verified helpers), h('l3'), q('type:beam') → (nodes, lines, domains), snap(), args. Errors come back with the failing lines; fix with patch instead of resending.",
    inputSchema: { type: "object", properties: {
      code: { type: "string" },
      patch: { type: "array", items: { type: "object", properties: { find: { type: "string" }, replace: { type: "string" } }, required: ["find", "replace"] } },
      lib: { type: "string" }, file: { type: "string" }, args: { type: "object" }, save_as: { type: "string" }, doc: { type: "string" }, label: { type: "string" },
    } },
  },
  {
    name: "undo",
    description: "Revert to before a checkpoint (from edit/run replies) or the last N steps, through AxisVM's own undo. Refuses if the model was changed in AxisVM after the checkpoint unless force:true.",
    inputSchema: { type: "object", properties: { checkpoint: { type: "string" }, steps: { type: "integer" }, list: { type: "boolean" }, force: { type: "boolean" } } },
  },
  {
    name: "memory",
    description: "User memory outside the plugin. list (call at session start: preferences, workflows, learned rules, script library) | save_pref {text:'key: value'} | set_prefs | save_workflow {name, when, text} | log_mistake {text, fix} | compact (show proposal to user) → set_rules | save_script {name, code, doc} | read_script {name} | delete_script.",
    inputSchema: { type: "object", properties: {
      action: { type: "string", enum: ["list", "save_pref", "set_prefs", "save_workflow", "log_mistake", "compact", "set_rules", "save_script", "read_script", "delete_script"] },
      text: { type: "string" }, fix: { type: "string" }, name: { type: "string" }, code: { type: "string" }, doc: { type: "string" }, when: { type: "string" },
    } },
  },
].filter(t => MODE !== "ask" || t.name === "view" || t.name === "query");

// ---------------------------------------------------------------- setup state
function setupStatus() { try { return JSON.parse(fs.readFileSync(path.join(BASE, "setup-status.json"), "utf8").replace(/^﻿/, "")); } catch { return null; } }
let setupProc = null, setupFailed = false;
const envReady = () => fs.existsSync(pythonPath()) && (config().python || fs.existsSync(path.join(BASE, "venv.lock.sha")));
function ensureEnvironment() {
  const st = setupStatus();
  const running = setupProc || (st && st.state === "running" && Date.now() - Date.parse(st.time) < 15 * 60 * 1000);
  if (running) return `NextraAxisVM is installing its Python environment (first use, about 1-4 minutes): ${st ? "step " + st.step + "/5: " + st.message : "starting"}. Tell the user, wait about a minute, then retry.`;
  if (envReady()) return null;
  if (setupFailed) return `NextraAxisVM setup failed: ${(st && st.message) || "unknown error"}. Ask the user to double-click Setup.bat (in the NextraAxisVM download) and read its message.`;
  if (!SETUP) return "NextraAxisVM's Python environment is missing. Ask the user to run Setup.bat from the NextraAxisVM download.";
  setupProc = spawn("powershell.exe", ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", SETUP, "-Quiet"], { windowsHide: true, stdio: "ignore" });
  setupProc.on("exit", code => { setupProc = null; setupFailed = code !== 0; });
  return "First use: NextraAxisVM is installing its Python environment and the AxisVM add-on in the background (about 1-4 minutes, nothing to click). Tell the user and retry in a minute. When it is done, AxisVM must be restarted once so the add-on connects.";
}

// ---------------------------------------------------------------- worker
let worker = null, ready = null, nextId = 1;
const pending = new Map();
let lateNotes = [];

function startWorker() {
  if (worker) return ready;
  const py = pythonPath();
  if (!ENGINE) throw new Error("engine folder not found next to the bridge");
  worker = spawn(py, ["-X", "utf8", "-u", path.join(ENGINE, "worker.py")], { windowsHide: true, stdio: ["pipe", "pipe", "pipe"], env: { ...process.env, PYTHONIOENCODING: "utf-8" } });
  let resolveReady, rejectReady;
  ready = new Promise((res, rej) => { resolveReady = res; rejectReady = rej; });
  const rl = readline.createInterface({ input: worker.stdout });
  rl.on("line", line => {
    let msg; try { msg = JSON.parse(line); } catch { return; }
    if (msg.id === 0) { resolveReady(); return; }
    const p = pending.get(msg.id);
    if (p) { pending.delete(msg.id); p.resolve(msg); }
    else if (msg.text) lateNotes.push(msg);                                  // reply of a call that already timed out
  });
  let errTail = "";
  worker.stderr.on("data", d => { errTail = (errTail + d.toString()).slice(-4000); });
  worker.on("exit", code => {
    const err = new Error(`worker exited (${code}). ${errTail.split("\n").slice(-6).join("\n")}`);
    for (const p of pending.values()) p.reject(err);
    pending.clear();
    worker = null; ready = null;
    rejectReady(err);
  });
  const t = setTimeout(() => rejectReady(new Error("worker did not start within 60 s")), 60000);
  ready.then(() => clearTimeout(t), () => clearTimeout(t));
  return ready;
}

function send(tool, args, timeoutMs) {
  const id = nextId++;
  return new Promise((resolve, reject) => {
    const timer = timeoutMs ? setTimeout(() => { if (pending.has(id)) { pending.get(id).timedOut = true; pending.delete(id); resolve({ id, timeout: true }); } }, timeoutMs) : null;
    pending.set(id, { resolve: m => { if (timer) clearTimeout(timer); resolve(m); }, reject: e => { if (timer) clearTimeout(timer); reject(e); } });
    worker.stdin.write(JSON.stringify({ id, tool, args }) + "\n");
  });
}

function toContent(msg, prefix) {
  const content = [{ type: "text", text: (prefix || "") + (msg.text || "") }];
  for (const img of msg.images || []) {
    try { content.push({ type: "image", data: fs.readFileSync(img).toString("base64"), mimeType: "image/png" }); }
    catch { content[0].text += `\n(image unreadable: ${img})`; }
  }
  return content;
}

const LONG = { edit: 900, run: 600 };

async function callTool(name, args) {
  args = args || {};
  if (!TOOLS.some(t => t.name === name)) return { content: [{ type: "text", text: `Tool '${name}' is not available in ${MODE} mode.` }], isError: true };
  if (MODE === "ask" && args.answer) return { content: [{ type: "text", text: "answer is not available in ask mode" }], isError: true };
  const envMsg = ensureEnvironment();
  if (envMsg) return { content: [{ type: "text", text: envMsg }], isError: true };
  try { await startWorker(); }
  catch (e) { return { content: [{ type: "text", text: "NextraAxisVM worker could not start: " + e.message + "\nAsk the user to run Setup.bat again." }], isError: true }; }
  const timeoutS = Math.min(Math.max(Number(args.timeout) || (args.analyze || args.import ? 900 : LONG[name] || 120), 5), 3600);
  delete args.timeout;
  let prefix = "";
  if (lateNotes.length) { prefix = lateNotes.map(m => "(late result of an earlier call)\n" + m.text).join("\n") + "\n---\n"; lateNotes = []; }
  try {
    if (name === "query" && args.scope === "status") {                 // answered by the worker's reader thread: works while busy
      const msg = await send("__status", args, 30000);
      return { content: toContent(msg, prefix) };
    }
    const msg = await send(name, args, timeoutS * 1000);
    if (msg.timeout) {
      const st = await send("__status", {}, 20000);
      return { content: toContent(st, `${prefix}Still running after ${timeoutS}s; the result will be attached to the next reply.\n`), isError: true };
    }
    return { content: toContent(msg, prefix), isError: msg.ok === false };
  } catch (e) {
    return { content: [{ type: "text", text: prefix + "NextraAxisVM worker error: " + e.message + " (it restarts on the next call)" }], isError: true };
  }
}

// ---------------------------------------------------------------- MCP stdio
function out(msg) { process.stdout.write(JSON.stringify(msg) + "\n"); }
const rl = readline.createInterface({ input: process.stdin });
rl.on("line", async line => {
  if (!line.trim()) return;
  let msg; try { msg = JSON.parse(line); } catch { return; }
  if (!msg || typeof msg !== "object" || Array.isArray(msg)) return;
  const { id, method, params } = msg;
  try {
    if (method === "initialize") {
      out({ jsonrpc: "2.0", id, result: {
        protocolVersion: (params && params.protocolVersion) || "2025-06-18",
        capabilities: { tools: {} },
        serverInfo: { name: "nextra-axisvm", version: VERSION },
        instructions: "AxisVM via 6 tools. Start with memory {action:'list'}, then query (text) before view/edit. Model edits: edit ops shorthand (query {scope:'docs', filter:'shorthand'}) > library script > run code. Units m, kN. Several AxisVM windows: query {scope:'instances'} then instance:'file.axs' once (sticky). AxisVM busy/dialog: query {scope:'status'}.",
      } });
    } else if (method === "tools/list") {
      out({ jsonrpc: "2.0", id, result: { tools: TOOLS } });
    } else if (method === "tools/call") {
      out({ jsonrpc: "2.0", id, result: await callTool(params.name, params.arguments || {}) });
    } else if (method === "ping") {
      out({ jsonrpc: "2.0", id, result: {} });
    } else if (id !== undefined) {
      out({ jsonrpc: "2.0", id, error: { code: -32601, message: "method not found: " + method } });
    }
  } catch (e) {
    if (id !== undefined) out({ jsonrpc: "2.0", id, error: { code: -32603, message: String(e && e.message || e) } });
  }
});
rl.on("close", () => { if (worker) try { worker.stdin.end(); } catch {} setTimeout(() => process.exit(0), 300); });

---
name: nextra-axisvm
description: Drive AxisVM (structural finite element software) through the NextraAxisVM MCP tools (view, query, edit, run, undo, memory). Use for any AxisVM task: reading or checking the open model, building frames/slabs/walls, sections and materials, supports, loads, combinations, linear analysis, results (displacements, reactions, internal forces), DXF/IFC/AXS import, importing Rhino geometry, PyAxisVM / COM scripting. The tools run on the user's computer: in the Claude app, check the computer link (get_device_info) and tool-search "nextra" before concluding they are missing.
---

# NextraAxisVM: AxisVM

Six tools. The engine guarantees correctness (node merging, catalog lookups, undo steps, per-line errors). You decide *what* and *where*. Units are always **m, kN, kNm** (displacements are reported in mm).

## Step 0: connect first, every session
The tools (`view`, `query`, `edit`, `run`, `undo`, `memory`) run on the user's computer.
1. **Check the computer link** in the Claude app: tool search `get_device_info` (or `device`, `remote-devices`) and call it. Skip this in local apps (Claude Code, Codex, ChatGPT Work).
2. **Load the tools:** tool search `nextra` (names may be prefixed, e.g. `mcp__…nextra-axisvm…__query`).
3. **First call:** `memory {action:'list'}`.
4. Still no tools? Repeat 1–3 once. Then tell the user in one message that the AxisVM tools did not attach, and ask them to keep the Claude desktop app running and reply "retry".
- "installing its Python environment": first use. Setup runs in the background for 1–4 minutes. Tell the user and retry later. AxisVM needs one restart afterwards.
- "AxisVM is running but the add-on is not loaded": ask the user to run **Setup.bat** and restart AxisVM. "not running": ask them to open AxisVM and their model. Work only in the AxisVM the user opened; never start another one.

## Several AxisVM windows
The session binds to one AxisVM. With several open, call `query {scope:'instances'}`, then `query {instance:'house.axs'}` (file name or pid; sticky). It never switches on its own.

## Session start
1. `memory {action:'list'}` returns the user's preferences, workflows, learned rules and scripts. **Follow them; they override this skill.** If a workflow's `when:` matches the request, read it: `query {scope:'docs', filter:'workflows/<name>'}`.
2. Look before you edit. `query {}` (summary) is cheap. Use `view` when position or shape matters.
3. When the user states a lasting preference (design code, sections, naming, report style), save it: `memory {action:'save_pref', text:'key: value'}`. After a reusable procedure succeeds, `save_workflow`.

## Priority (always)
1. **Model changes → `edit {ops}` shorthand** (`shorthand.md`). It handles element definition, catalog sections and materials, supports, loads, combinations, delete/set/select. Repeats with `@ x=0:6:24 y=0,5` keep it short.
2. **A library script fits → `run {lib:'name', args}`** (`query {scope:'library'}`).
3. **Otherwise → `run` Python** with `model`, `ax`, `kit`, `pyax`, `h()`, `q()`. Fix errors with `patch:[{find,replace}]`, never a full resend. Unsure of a call? `query {scope:'api', filter:'line load'}` → `filter:'IAxisVMLoads.AddBeamDistributed'` (exact signature and record fields of the installed AxisVM). Cheat sheet: `api/axisvm-com.md`.

## Handles and pictures
- `n5` node, `l12` line (beam/rib/truss/plain), `d3` domain (plate/shell/membrane). These are AxisVM's own numbers, as shown in AxisVM. **AxisVM renumbers after deletes and after meshing splits lines**, so re-query before reusing old handles.
- `view` draws the model with an 8×8 grid (A–H, 1–8) and tags. A crowded view returns per-cell counts. Zoom with `view {focus:'C3:E5'}`, or frame elements with `focus:'type:beam'` / `'l3 d1'`. Never compute coordinates from images; use handles or `query`.
- Results in pictures: `view {combo:'ULS', result:'deformed'}` or `result:'My'` (members coloured). `view {target:'axisvm'}` is a screenshot of AxisVM itself (its own result displays and contours).

## Reading the model, step by step
`query {}` summary → `query {filter:'type:beam'}` (one line per element: section, material, nodes, length, orientation) → `level:'detail'` (releases, loads on it, contour). Filters: `l3 d1 n5`, `type:beam|rib|truss|plate|shell|column|slab|wall`, `section:IPE*`, `material:C30*`, `vertical`, `horizontal`, `sel` (selected in AxisVM), `bbox:x0,y0,z0,x1,y1,z1`, `member:m5`, `supports`, `nodes`.
Loads: `query {scope:'loads'}` and `filter:'case:G'`. Catalog: `query {scope:'catalog', filter:'HEB 2*'}` or `'material C30*'` (the first call builds an index, ~45 s once).

## Analysis and results
`edit {analyze:'linear'}` meshes unmeshed domains first (auto size; `mesh_size` overrides). Then `query {scope:'results', combo:'ULS'}` gives max displacements, reaction sum per support, member force extremes, and surface force extremes. `kind:'reactions'|'forces'|'displacements'|'surface'` lists per element (with `filter`). Check equilibrium: the reaction sum should match the applied loads. Mention it when it does not.
Nonlinear, vibration and buckling analyses and design checks go through `run` (see `api/axisvm-com.md`).

## Every edit returns
`ok|partial|FAILED: n/m lines applied`, per-line results, `model delta` (`+` added, `~` changed, `-` removed), `checkpoint cN`. On partial, resend **only** the failed lines. `undo {checkpoint:'cN'}` reverts through AxisVM's own undo (also Ctrl+Z in AxisVM). If the user edited in AxisVM meanwhile, undo refuses; ask before `force:true`.

## Import
- DXF / IFC / AXS / PDF: `edit {import:'C:/…/plan.dxf', import_options:{unit:'mm', plane:'xy'}}` (AxisVM's own importers).
- **Rhino:** export with `rhino/rhino_export.py` inside Rhino (NextraRhinoGh `run {file:…}`, or Rhino's ScriptEditor), then `edit {import:'…/nextra_rhino_export.json'}`. AxisBridge `Ax_*` user texts become sections, materials, supports, releases and loads. See workflows.md#Rhino.

## When things go wrong
- A call is slow or "still running": `query {scope:'status'}`. It shows AxisVM dialogs **with a screenshot** and their buttons. Tell the user what the dialog says. Press a button with `query {scope:'status', answer:'Yes'}` only when the choice is clearly safe or the user agreed.
- Meshing reports overlapping or unconnected lines: `edit {ops:'intersect'}`, then analyze again.
- Same error twice: change approach (another shorthand action, `run`, a different AxisVM call). Do not loop.
- After you solve an error: `memory {action:'log_mistake', text, fix}`. When the tool says "recurring mistake", do it.

## Docs (read only what you need: `query {scope:'docs', filter:'<name>'}`)
- `shorthand.md`: edit grammar and examples. Read it before the first edit of a session.
- `workflows.md`: recipes for a new model, checking an existing model, Rhino/DXF import, analysis and results, scripting.
- `api/axisvm-com.md`: COM / PyAxisVM cheat sheet (ids, out-params, records, error codes).

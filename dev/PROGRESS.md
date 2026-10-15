# NextraAxisVM build progress (handoff)

Read dev/PLAN.md first (architecture, the 6 tools, possible / not possible).

## Done and verified
- `addon/NextraAxisVM` (C# net48): registers `!NextraAxisVM.Host.<pid>` in the ROT at AxisVM start-up (Addon_Init) and
  writes `%APPDATA%\NextraAxisVM\instances\axisvm-<pid>.json`. `Host.GetApplication()` returns the live
  IAxisVMApplication; `Host.Ping()`, `Host.RhinoImport(jsonPath, optionsJson)` (vendored AxisModelBuilder from plugin
  dev 02 in `RhinoImport/`). Build: `cd addon/NextraAxisVM && dotnet build -c Release` → `addon/bin/NextraAxisVM.dll`.
  Verified: a separate Python process attaches to a running AxisVM repeatedly (~1.5 ms/call), PyAxisVM wrapping works.
  Lesson: never register AxisVM's own app object in the ROT (AxisVM disconnects it -> weak entry dies).
  Host is .NET AutoDispatch → call with raw GetIDsOfNames/Invoke (`conn.Late`), comtypes lazybind fails.
- `setup/setup.ps1` + `Setup.bat`: uv → Python 3.10 venv `%LOCALAPPDATA%\NextraAxisVM\venv` from
  `requirements.lock.txt` (UV_LINK_MODE=copy needed) → tlb wrapper → add-on copy → Node check. Verified OK (~1 min).
- Engine: worker, core, win, conn, memory, apidocs (typelib index+search, verified), comkit (verified live: nodes, catalog material/section, beam/rib, plate domain, supports, releases, cases, self-weight, line/area/nodal loads, combo; LinearAnalysis(3) ok). Beams on slab edges become ribs (use RLoadRibDistributed).

- Engine modules all written and tested live: apidocs, comkit, modeldata (snapshot+delta), query (model/loads/results/
  catalog[cached on disk]/api/docs/library/status/instances), edit (shorthand w/ @ repeats, split at nodes, import/export,
  mesh, analyze), runtool (lazy pyax), undo (AxisVM undo stack, verified), view (Pillow render + grid/tags/focus/deformed/
  force colours; AxisVM window capture), status with dialog screenshot + answer (PrintWindow, BM_CLICK).
  Verified numbers: 2-bay frame + slab G reactions 323 kN, ULS 706 kN (hand check ok).

## Next steps
1. bridge/server/index.js (Node, spawns venv python engine/worker.py; routes query scope status -> __status;
   timeouts; auto-run setup when venv missing).
2. skill/nextra-axisvm (SKILL.md, shorthand.md, workflows.md, api/axisvm-com.md, library/rhino_export.py for Rhino side).
3. tools/make_plugin.py (+ codex/claude manifests, marketplaces, zips, mcpb), README install guide, test/regress.py.
4. Ask user before creating/pushing GitHub repo nextra-studio/nextra-axisvm.

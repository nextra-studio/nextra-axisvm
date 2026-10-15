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

- Bridge (auto setup on first use verified), skill docs, Rhino exporter, packaging (plugin/, marketplaces, dist zips,
  mcpb, Setup zip), README install guide. Regression: 34/34 with --launch and --instance (hand-calc checks).

## Open items
- Publish: create GitHub repo nextra-studio/nextra-axisvm, push, gh release with dist/ files (ask the user first).
- rhino/rhino_export.py not yet run inside Rhino (needs Rhino 8 open); the JSON import side is tested.
- Not yet observed: whether AxisVM asks anything on close while the add-on is loaded (registration is weak, expected no).
- Nonlinear/vibration/buckling and design checks only via run (no shorthand).

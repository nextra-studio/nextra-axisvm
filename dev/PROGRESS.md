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

## Next steps
1. `engine/nextra_axisvm/__init__.py`, `apidocs.py` (typelib index via comtypes.typeinfo LoadTypeLibEx(gen.AxisVM.typelib_path):
   interfaces (kind 4 dispatch), records (1), enums (0); `enum_constants()` used by conn.error_name; search + cache).
2. `modeldata.py` (bulk snapshot: Nodes.BulkGetCoord, Lines.BulkGetLineData/BulkGetAttr_V161, Domains.BulkGetDomains),
   `query.py` (model/loads/results/catalog/api/docs/library/status/instances), `edit.py` (shorthand, see PLAN),
   `runtool.py` (exec with helpers, patch, lib, delta, checkpoint), `undo.py` (model.SaveUndo/Undo), `view.py`
   (Pillow render with grid + tags; target 'axisvm' = Windows.SaveWindowToBitmap).
3. `bridge/server/index.js` (from RhinoGh bridge: spawn venv python engine/worker.py, JSON lines, timeouts, auto-setup).
4. skill/nextra-axisvm (SKILL.md, shorthand.md, workflows.md, api/axisvm-com.md, library/rhino_export.py),
   tools/make_plugin.py, marketplaces, README with install guide, test client, regression test.
5. git commit; ask user before creating/pushing GitHub repo nextra-studio/nextra-axisvm.

Test AxisVM: launch a separate instance with a script (CreateObject + CloseOnLastReleased=0); never modify the
user's own AxisVM. Engine python: `%LOCALAPPDATA%\NextraAxisVM\venv\Scripts\python.exe`.

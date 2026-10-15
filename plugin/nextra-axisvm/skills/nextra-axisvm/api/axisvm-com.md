---
description: AxisVM COM / PyAxisVM cheat sheet for run (ids, out-params, records, errors, common calls)
---
# AxisVM COM in `run`: cheat sheet

Exact signatures of the **installed** AxisVM: `query {scope:'api', filter:'Interface.Member'}`. Records and enums by name (`'RLoadBeamDistributed'`, `'ELineType'`). Free words search everything (`'support force'`).

## Rules that prevent most errors
- **1-based ids** everywhere (`model.Nodes.Item`, `Lines.Item[i]`, `LoadCases.Name[i]`). Collections: `.Count`.
- **Units:** m, kN, kNm, kN/m, kN/m². Stiffness kN/m and kNm/rad. AxisVM's "rigid" support stiffness is 1e10.
- **Return values:** most methods return a code or the new id. **> 0 = ok, ≤ 0 = error** (a negative error code). Check it with `kit.check(rc, 'what')`, which raises with the AxisVM error name.
- **Out-parameters come back as a tuple**, the code last: `vals, rc = model.Results.Displacements.GetAllNodalDisplacementsByLoadCaseId(case, 0, ax.atLinearStatic, ax.lbFalse)`.
- **Records** (`R…`) are created empty and filled: `st = ax.RStiffnesses(); st.x = 1e10`. Pass them positionally.
- **Enums** live on `ax`: `ax.ltBeam`, `ax.lbTrue`, `ax.sysGlobal`, `ax.cuiNoUserInteractionWithAutoCorrectNoShow`.
- `_V161`/`_V153` variants are newer versions of a call (more fields). Prefer the plain one unless you need the extras.
- Bulk calls are much faster than loops: `Nodes.BulkGetCoord(ids)`, `Lines.BulkGetLineData(ids)`, `Lines.BulkGetAttr_V161(ids)`, `Domains.BulkGetDomains(ids)`.
- The `run` call is already wrapped in SaveUndo + BeginUpdate/EndUpdate (one undo step). Do not call them yourself.

## Common calls
| task | call |
|---|---|
| node | `model.Nodes.Add(x, y, z)` → id · `kit.NodeIndex(model).get((x,y,z))` reuses existing |
| line | `model.Lines.Add(n1, n2, ax.lgtStraightLine, ax.RLineGeomData())` · `kit.chain(model, ni, n1, n2)` splits at nodes |
| beam / rib / truss | `model.Lines.Item[l].DefineAsBeam(mat, sec, sec, ax.RPoint3d(), ax.RPoint3d())` · `DefineAsRib(...)` · `DefineAsTruss(mat, sec, ax.lnlTensionAndCompression, 0.0)` |
| material | `model.Materials.AddFromCatalog(ax.ndcEuroCode, 'S 235')` · `kit.material(model, 'C30/37')` |
| section | `model.CrossSections.AddFromCatalog_V161(ax.csseI, 'IPE 300')` · `AddRectangular(name, b, h, ax.cspOther)` · `kit.section(model, 'rect 300x500')` |
| domain | `a = ax.RSurfaceAttr(); a.SurfaceType = ax.stPlate; a.Thickness = 0.2; a.MaterialId = m` → `model.Domains.Add([line ids], a)` |
| nodal support | `model.NodalSupports.AddNodalGlobal(kit.stiffness('pinned'), ax.RNonLinearity(), ax.RResistances(), node)` |
| line support | `model.LineSupports.AddEdgeGlobal(stiff, ax.RNonLinearity(), ax.RResistances(), line, 0, 0, 0, 0)` |
| release | `r = ln.GetStartReleases()[0]; r.yy.ReleaseType = ax.rtHinged; ln.SetStartReleases(r)` · `kit.releases(model, l, start='hinge')` |
| load case | `model.LoadCases.Add('G', ax.lctStandard)` |
| loads | `kit.nodal_force(model, case, node, (fx,fy,fz,mx,my,mz))` · `kit.beam_load(model, case, line, (qx,qy,qz))` (rib-aware) · `kit.area_load(model, case, domain, (0,0,-3))` · `kit.self_weight(model, case)` |
| combination | `model.LoadCombinations.Add('ULS', ax.ctULS1, [1.35, 1.5], [g, q])` |
| analysis | `model.Calculation.LinearAnalysis(ax.cuiNoUserInteractionWithAutoCorrectNoShow)` (mesh domains first: `edit {mesh:'all'}`) |
| results valid? | `model.Results.GetResultsValid(ax.atLinearStatic, case)` |
| displacements | `Results.Displacements.GetAllNodalDisplacementsByLoadCaseId / …ByLoadCombinationId(id, 0, ax.atLinearStatic, ax.lbFalse)` → records ex, ey, ez [m] |
| reactions | `Results.Forces.GetAllNodalSupportForcesByLoadCaseId(id, 0, ax.atLinearStatic)` → Rx … Rzz (index = support id) |
| line forces | `Results.Forces.GetAllLineForcesByLoadCaseId(id, 0, ax.atLinearStatic)` → (SectionCounts, Forces, PosX, rc); fields lfvNx lfvVy lfvVz lfvTx lfvMy lfvMz |
| surface forces | `Results.Forces.GetAllSurfaceForcesByLoadCaseId(id, 0, ax.atLinearStatic)` → per element `sfvCenterPoint.sfvMx` … |
| save | `model.SaveToFile(path, ax.lbTrue)` (with results) |
| selection | `model.Lines.GetSelectedItemIds()` · `model.Lines.Selected[i] = ax.lbTrue` |

## Gotchas
- A beam on a domain edge becomes a **rib**. Rib loads need `AddRibDistributed` with `RLoadRibDistributed`; `kit.beam_load` picks the right one.
- **Meshing splits lines** and adds `edge` lines, so ids change. Query again after `analyze`.
- Model changes **invalidate results**. Analyze again before reading results.
- A modal dialog in AxisVM blocks every COM call. `query {scope:'status'}` shows it.
- PyAxisVM (`pyax`) is imported on first use (~30 s cold). Raw `model` calls are enough for most tasks. PyAxisVM adds conveniences such as `pyax.model.Lines[i]`, `pyax.model.coordinates()`, `pyax.model.Domains[i].plot()`.

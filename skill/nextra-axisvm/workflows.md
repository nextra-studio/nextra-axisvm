---
description: recipes for new models, checking models, Rhino/DXF import, analysis and results, scripting
---
# NextraAxisVM workflows

## New model from a description
1. `memory {action:'list'}` (preferences: design code, default sections, units of reporting).
2. Plan the grid and levels in text first (axes, spans, storey heights). Ask only when something essential is missing (spans, use, material). Otherwise choose sensible defaults and say which.
3. `query {scope:'catalog', filter:'HEB 2*'}` only if unsure of a profile name.
4. One `edit {ops}` for geometry, sections and supports (use `@` repeats). Then a second one for cases, loads and combinations.
5. `view {}` once to confirm the shape. Check `query {}`: counts as expected, no stray lines.
6. `edit {analyze:'linear'}` → `query {scope:'results', combo:'ULS'}`. Check that the reaction sum equals the applied vertical load (self-weight + area loads × areas).
7. Report the main numbers (max deflection, max moments, reactions) and the assumptions. Offer `edit {save:'…axs'}`.

## Check or explain an existing model (the user's open file)
1. `query {}`: the summary tells you counts, sections, cases, combinations, and whether results are valid.
2. `view {}` (and `focus`) to understand the layout. Then `query {filter:'type:beam'}` / `'type:slab'` lists.
3. Look for typical problems: unsupported or free nodes (`query {filter:'supports'}`), members without sections (`type:line`), domains without loads, combinations missing a case, mechanism risks (pinned everywhere).
4. Never change the user's model unless asked. To try a variant, ask first, or explain that `undo` reverts it.

## Change sections / sizes after a check
`edit {ops:'set l3-l8 sec=IPE 360'}` → `edit {analyze:'linear'}` → compare results. Undo with the checkpoint if the user prefers the old state.

## Rhino → AxisVM {#Rhino}
1. In Rhino (NextraRhinoGh session, or the user runs it in Rhino's ScriptEditor). The exporter's full path is printed by `query {scope:'docs'}`:
   `run {file:'<skill folder>/rhino/rhino_export.py', args:{selected:true, material:'S 235', section:'IPE 300', thickness:'200', surface_type:'Plate'}}`
   - Curves become lines (linear → line, arc → arc, polyline → one member), planar surfaces and polysurface faces become domains with openings.
   - AxisBridge `Ax_*` user texts are kept: `Ax_Type` (Beam/Rib/Truss/Simple…), `Ax_Section`, `Ax_Material`, `Ax_Release`, `Ax_Support` on points, `Ax_FEType`+`Ax_Thickness` on surfaces, loads `Ax_DistLoad` "LC=Dead; q=0,0,-5".
   - `layer_rules` assigns attributes by layer: `{'Columns':{'Ax_Section':'HEB 240'}, 'Slabs':{'Ax_FEType':'Plate','Ax_Thickness':'250','Ax_Material':'C30/37'}}`.
   - Use a model in mm or m (other Rhino units are read as mm).
2. In AxisVM: `edit {import:'C:/…/nextra_rhino_export.json', import_options:{tol_mm:1, dry_run:false}}`. This is the same builder as the "N. Rhino Import" add-on: node merging, intersections, catalog resolution, one undo step. Read the notes in the reply (substitutions, attribute errors).
3. `view {}` + `query {}` to verify, then supports, loads and analysis as usual.

## DXF / IFC
- DXF plan: `edit {import:'plan.dxf', import_options:{unit:'mm', plane:'xy', as:'nodes'}}`. Lines arrive as plain lines; define them: `edit {ops:'beam l1-l20 sec=IPE 300 mat=S 235'}`. `as:'background'` imports a background layer only.
- IFC: `import_options:{method:'static'}` (analysis model) or `'architectural'`.
- Export: `edit {export:'model.dxf'}` / `'model.ifc'`.

## Results reporting
- `query {scope:'results', combo:'ULS'}` (summary) → `kind:'forces', filter:'type:beam'` (per member extremes) → `kind:'reactions'`.
- Pictures: `view {combo:'ULS', result:'deformed'}`, `view {combo:'ULS', result:'My', view:'front'}`. AxisVM's own contours: set the display in AxisVM (or via run), then `view {target:'axisvm'}`.
- Units: kN, kNm, mm. State the case or combination for every number.

## Scripting (run)
```python
n, l, d = q('type:beam vertical')            # ids
S = kit.material(model, 'S 355'); sec = kit.section(model, 'HEB 300')
for i in l:
    kit.define_line(model, i, 'beam', S, sec)
print(len(l), 'columns updated')
```
- Out-parameters come back as return values: `coords, rc = model.Nodes.BulkGetCoord([1, 2, 3])`.
- Records: `r = ax.RLoadNodalForce(); r.LoadCaseId = 2; …; model.Loads.AddNodalForce(r)`.
- Save a script that worked and will be reused: `run {…, save_as:'columns_to_s355', doc:'Set all columns to S355 HEB300'}`.

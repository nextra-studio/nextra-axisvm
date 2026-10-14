# NextraAxisVM: plan, scope and limits

Goal: a reliable AxisVM tool for AI agents with the same structure as NextraRhinoGh. It has a few token-lean tools, one
skill, and plugins for Claude and ChatGPT/Codex. It works on the model the user already has open.

## Architecture

```
AI app ──stdio MCP──> bridge/server/index.js (Node, zero-dependency, same role as NextraRhinoGh's bridge)
                         │ spawns and supervises one worker (timeouts, restart, setup on first use)
                         ▼
                 engine/ (Python 3.11 worker, PyAxisVM + comtypes, venv in %LOCALAPPDATA%\NextraAxisVM\venv)
                         │ COM, cross-process
                         ▼
   AxisVM.exe ◄── addon/NextraAxisVM.dll (C# add-on in AxisVM\AddOns): at AxisVM start-up it registers a host object
                  in the Running Object Table as !NextraAxisVM.Host.<pid>. The host hands out the live
                  IAxisVMApplication and runs C# jobs in-process (the Rhino import).
```

Why the add-on: an AxisVM started by the user is **not** in the Running Object Table, so `GetActiveObject` /
PyAxisVM `start_AxisVM(join=True)` cannot find it. Without the add-on, a COM client can only start a new, empty
AxisVM. This was verified on AxisVM X8 r1o. The add-on registers only its own .NET host, never AxisVM's application object.
AxisVM disconnects its app object when the last COM client leaves, which would kill a weak entry. A strong entry would
count as a connected client and change how AxisVM closes.

## Tools (6, same names and roles as NextraRhinoGh where they apply)

| tool | role |
|---|---|
| `view` | Image with an A–H × 1–8 grid and handle tags (`n12` node, `l4` line, `d2` domain). `target:'model'` is Nextra's own drawing: deterministic, with exact tags, crowded → per-cell counts → `focus`. `target:'axisvm'` captures AxisVM's own window, including result displays. |
| `query` | Text, cheapest first. `model` summary → list (one line per element) → detail. `loads`, `results` (displacements, reactions, member forces, after analysis), `catalog` (materials and sections), `api` (installed type library search), `docs`, `library`, `status`, `instances`. |
| `edit` | A compact model **shorthand** (one line = one action, applied independently with per-line errors) for materials, sections, beams/columns/ribs/trusses, plates/shells/membranes, holes, supports, releases, load cases, loads, and combinations. Also delete/set/select, open/new/save, import (DXF, IFC, AXS, PDF, Rhino AxisBridge JSON), export (DXF, IFC), and analysis. |
| `run` | Python with PyAxisVM and helpers (`model`, `ax`, `h('l4')`, `q('type:beam')`, …). It supports patch edits and a script library, and reports the model delta and a checkpoint. |
| `undo` | Revert to a checkpoint using AxisVM's own undo (each edit/run is one undo step). |
| `memory` | Preferences, workflows, learned rules, mistake log, script library, all in `%APPDATA%\NextraAxisVM\user`. |

The full AxisVM COM API has 204 interfaces and about 5,000 methods. It is not exposed as tools. The skill and
`query {scope:'api'}` lead the model to the right call. `edit` covers the common modelling path in one call, and `run`
covers the rest.

## Possible, and planned (v0.1)

- Work on the **already open** AxisVM, including several instances (bind by file name or pid; sticky, like NextraRhinoGh).
- Start AxisVM, open/new/save `.axs`.
- Read the model compactly from bulk COM calls (nodes, lines with element types, sections, materials, domains, supports, loads, cases, combinations).
- Build and change models through the shorthand: catalog materials and sections (Eurocode catalog names), parametric sections, element definition, domains with holes, supports, end releases, self-weight, nodal/line/area loads, combinations.
- Import DXF / IFC / AXS / PDF through AxisVM's own importers, and export DXF / IFC.
- **Rhino import:** the existing AxisModelBuilder from *plugin dev 02* (the "N. Rhino Import" add-on) runs headless inside the add-on. It reads the AxisBridge JSON (schema 2) without a dialog and returns a JSON report. A Rhino-side exporter script (no AxisBridge plug-in needed for plain geometry) is shipped for NextraRhinoGh `run`.
- Linear static analysis, and also nonlinear, vibration and buckling when the model is set up for them.
- Results as text: nodal displacements, support reactions, line/member internal forces (extremes), domain internal forces (extremes).
- Vision: Nextra drawing with tags, plus captures of AxisVM's window.
- Undo through AxisVM's undo stack. One edit/run is one step.
- Setup without a terminal: `Setup.bat` (or the bridge on first use) installs uv, Python 3.11, PyAxisVM, the add-on, and checks.
- Plugins: Claude Code / Desktop (marketplace + ZIP), ChatGPT/Codex (marketplace + ZIP), an agent kit, and `.mcpb`.

## Not possible, or deliberately out of scope

- **No add-on, no attach.** Attaching to an AxisVM that was already open needs the add-on loaded at AxisVM start. After setup, AxisVM must be restarted once. Without it, the tools can still start their own AxisVM.
- **Elevation mismatch.** If AxisVM runs "as administrator" and the AI app does not (or the reverse), Windows hides the ROT entry. Both must run at the same level.
- **Modal dialogs block COM.** While AxisVM shows a dialog, COM calls wait. The worker reports the dialog title (`query {scope:'status'}`). It does not click dialogs.
- **Only one model per AxisVM.** COM exposes `Models.Item[1]` only. Use separate AxisVM instances for several models.
- **Undo is AxisVM's stack.** Manual edits made after an AI edit sit on top of it. `undo` detects that the model changed since the checkpoint and asks for `force`.
- **Element numbers renumber after deletes** (AxisVM behaviour). Handles are AxisVM's own numbers, as shown in AxisVM. After a delete the reply says so.
- **Design checks** (steel/RC/timber design, reinforcement) are reachable through `run` and `query {scope:'api'}`. They have no shorthand in v0.1.
- **Direct .3dm reading** without Rhino is not included. Rhino geometry goes through the exporter script (Rhino open, NextraRhinoGh or the Rhino script editor) or the AxisBridge plug-in.
- **Result contour images** come from AxisVM's own window (`view {target:'axisvm'}`). Nextra's drawing shows the model, not contours.
- AxisVM licence, modules (DXF/IFC import need the corresponding AxisVM modules) and versions: tested on **AxisVM X8 r1o** (COM type library 18.100). Other versions load their own type library through comtypes. Features that are missing there return an error.

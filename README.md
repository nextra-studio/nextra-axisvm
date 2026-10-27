# NextraAxisVM: AxisVM for AI agents

Six token-lean tools let an LLM read, build, analyse and change AxisVM models, including **the model you already have open**. It works from ChatGPT desktop / Codex, Claude Desktop, Claude Code, or any MCP client. It is built on [PyAxisVM](https://axisvm.github.io/pyaxisvm-docs/) and has the same structure as [NextraRhinoGh](https://github.com/nextra-studio/nextra-rhinogh). Replies state what changed, pictures carry tags the model can point at, and every change is one AxisVM undo step.

**[Install guide](#install)** · **[Download AxisVM setup](https://github.com/nextra-studio/nextra-axisvm/releases/latest/download/NextraAxisVM-Setup.zip)** · **[Download Claude ZIP](https://github.com/nextra-studio/nextra-axisvm/releases/latest/download/nextra-axisvm-plugin.zip)** · **[Download ChatGPT/Codex ZIP](https://github.com/nextra-studio/nextra-axisvm/releases/latest/download/nextra-axisvm-gpt-plugin.zip)**

## Install

You need **Windows**, **AxisVM X7 or newer**, an **internet connection for setup**, and your AI desktop app.

There are two parts: **add the plug-in to your AI app**, then **set up the AxisVM connection**. Installing the AI plug-in alone does not finish the AxisVM side.

1. Follow **Your AI app** below. Choose either marketplace installation or its ZIP.
2. Click **Download AxisVM setup**, extract the ZIP and run **Setup.bat**. Setup installs the connection and supporting files for you.
3. Open AxisVM yourself, go to **Elements** and click the **green Nextra “N” icon** to start linking. Then send the example request under **Try it**.

### 1. Your AI app

Choose your AI app below. For ChatGPT/Codex and Claude, **install from this GitHub marketplace** for the easiest update path, or **download the ZIP**. Both install the same plugin; pick one.

```text
https://github.com/nextra-studio/nextra-axisvm
```

The pictures are simplified guides of the app menus. Labels can vary by version.

<details open>
<summary><strong>ChatGPT / Codex desktop</strong></summary>

**Find Plugins:** click the **Plugins icon** in the far-left navigation rail, then click **Add** at the top right.

![OpenAI: click the Plugins icon in the far-left rail, then Add](docs/img/install/openai-plugins.svg)

<details open>
<summary><strong>Install from marketplace (recommended)</strong></summary>

1. Open **Add → Create plugin → Add a marketplace** where available.
2. Fill in **Add plugin marketplace** exactly as below, then click **Add marketplace**:

   | Field | Enter |
   |---|---|
   | **Source** | `https://github.com/nextra-studio/nextra-axisvm` |
   | **Git ref** | `main` |
   | **Sparse paths** | Leave empty |

3. Open **NextraAxisVM**, select **NextraAxisVM**, and click **Install** (or **+**).

![ChatGPT Desktop marketplace setup](docs/img/install/openai-marketplace.svg)

If your app has no **Add a marketplace**, run `codex plugin marketplace add nextra-studio/nextra-axisvm` in a terminal, restart the app, then install **NextraAxisVM** from the Plugins Directory.

</details>

<details>
<summary><strong>Download and upload ZIP</strong></summary>

1. **[Download the ChatGPT/Codex plugin ZIP](https://github.com/nextra-studio/nextra-axisvm/releases/latest/download/nextra-axisvm-gpt-plugin.zip)**. Keep it zipped.
2. From **Add**, open **Create plugin → Upload plugin archive** (or **Upload plugin**).
3. Select `nextra-axisvm-gpt-plugin.zip` and finish the installation.

![OpenAI ZIP installation](docs/img/install/openai-upload.svg)

</details>

Start a new session in **Work** (or Codex) on the desktop app. **Use Work, not Chat**: plugin tools do not run in Chat. Type `@NextraAxisVM` and your request.

![ChatGPT desktop: switch the top toggle from Chat to Work](docs/img/install/openai-work.png)

</details>

<details>
<summary><strong>Claude Desktop</strong></summary>

**Find Plugins:** **Customize** in the left sidebar → **Plugins** → **+ Add**.

![Claude: Customize, Plugins, Add](docs/img/install/claude-plugins.svg)

<details open>
<summary><strong>Install from marketplace (recommended)</strong></summary>

1. Choose **+ Add → Add marketplace → Add from a repository**.
2. Enter `nextra-studio/nextra-axisvm` in **URL**, then click **Sync**.
3. Open the **NextraAxisVM** marketplace, select **nextra-axisvm**, and click **Install**.

![Claude marketplace installation](docs/img/install/claude-marketplace.svg)

</details>

<details>
<summary><strong>Download and upload ZIP</strong></summary>

1. **[Download the Claude plugin ZIP](https://github.com/nextra-studio/nextra-axisvm/releases/latest/download/nextra-axisvm-plugin.zip)**. Keep it zipped.
2. Choose **+ Add → Upload plugin**, select `nextra-axisvm-plugin.zip`, then **Upload**.

![Claude ZIP installation](docs/img/install/claude-upload.svg)

</details>

Start a new **Cowork** session. In the first message of each session, start with `/nextra-axisvm`.

</details>

<details>
<summary><strong>Claude Code</strong></summary>

```text
claude plugin marketplace add nextra-studio/nextra-axisvm
claude plugin install nextra-axisvm@nextra-axisvm
```

Or download the Claude ZIP, extract it, and start `claude --plugin-dir PATH_TO_EXTRACTED_PLUGIN`.

</details>

<details>
<summary><strong>Other AI agents</strong></summary>

**[Download the agent kit ZIP](https://github.com/nextra-studio/nextra-axisvm/releases/latest/download/nextra-axisvm-agent-kit.zip)** (skill, MCP server, Setup.bat, workspace configuration). Extract it, run `Setup.bat`, and open the folder as your agent's workspace. Details are in `AGENTS.md`.

</details>

### 2. Set up the AxisVM connection

**[Download AxisVM setup (NextraAxisVM-Setup.zip)](https://github.com/nextra-studio/nextra-axisvm/releases/latest/download/NextraAxisVM-Setup.zip)**

[![AxisVM setup: download the ZIP, Extract All, run Setup.bat, then click the green Nextra N icon in Elements](docs/img/install/axisvm-setup.svg)](https://github.com/nextra-studio/nextra-axisvm/releases/latest/download/NextraAxisVM-Setup.zip)

1. **Save your model and close AxisVM.**
2. **Download the setup ZIP** using the link above.
3. Right-click `NextraAxisVM-Setup.zip` → **Extract All**. Open the extracted folder.
4. **Double-click `Setup.bat`**. Setup installs the AxisVM add-on and supporting files for you. Allow **1–4 minutes** with an internet connection. Follow any prompts; administrator approval is only requested if the AxisVM folder needs it.
5. When setup finishes, **open AxisVM yourself** and open your model (or an empty model). Restart your AI app too if setup installed supporting software.
6. In AxisVM, go to the **Elements** tab and click the **green Nextra “N” icon**. This starts linking AxisVM to the AI tools.
7. Keep AxisVM open and send the example request below. **Repeat Elements → Nextra “N” after restarting AxisVM.**

**What does “automatic setup” mean?**

You can also let the AI plug-in start setup. After installing the plug-in, open AxisVM and send the **Try it** message below. The **first tool call** starts the setup script in the background; downloading the plug-in alone does not start it.

Wait **1–4 minutes**, **restart AxisVM once**, go to **Elements** and click the **green Nextra “N” icon**, then **repeat your request**. If setup cannot finish or needs administrator approval, use **Download AxisVM setup** above and run `Setup.bat` to see the progress and follow its prompts.

<details>
<summary>What setup installs</summary>

- A separate Python 3.10 environment with PyAxisVM in `%LOCALAPPDATA%\NextraAxisVM\venv`. Your own Python installation is not changed.
- The NextraAxisVM add-on in AxisVM's `AddOns` folder.
- Checks for the supporting software and AxisVM registration.

Setup installs the add-on. To start linking, open AxisVM yourself, go to **Elements** and click the **green Nextra “N” icon**. Repeat this after restarting AxisVM.

</details>

### Try it

Open AxisVM yourself (any model, or an empty one), go to **Elements**, and click the **green Nextra “N” icon** to start linking. Keep AxisVM open, then:

| App | Message |
|---|---|
| ChatGPT / Codex desktop (**Work**) | `@NextraAxisVM Build a two-bay steel frame with a concrete slab in AxisVM and analyse it` |
| Claude Desktop (Cowork) / Claude Code | `/nextra-axisvm Check the model I have open in AxisVM and summarise the results` |

<details>
<summary>Troubleshooting</summary>

| Problem | Fix |
|---|---|
| "installing its Python environment" | First use. Wait 1–4 minutes, restart AxisVM, then go to **Elements** and click the **green Nextra “N” icon** before asking again. |
| "AxisVM is running but the add-on is not loaded" | Go to **Elements** and click the **green Nextra “N” icon**, then retry. If the icon is missing, run `Setup.bat`, restart AxisVM, and click the icon in **Elements**. |
| "not reachable" although AxisVM is open | First click the **green Nextra “N” icon** in **Elements** and retry. If it still fails, start AxisVM and the AI app at the same privilege level, normally both without administrator rights. |
| A call hangs | AxisVM is showing a dialog. The AI sees it with `query {scope:'status'}` (with a screenshot). Answer the dialog in AxisVM. |
| No tools in the AI app | Confirm the plugin is installed, restart the app, start a new session (ChatGPT: **Work**, not Chat). |
| Several AxisVM windows | Name the file: "Use bridge.axs." |
| Setup failed | Double-click `Setup.bat` and read the message. Log: `%LOCALAPPDATA%\NextraAxisVM\setup.log`. |

</details>

## Tools

| tool | what it does |
|---|---|
| `view` | Picture of the model with an 8×8 grid and short handle tags (`n5` node, `l12` line, `d3` domain). Crowded views return per-cell counts, then `focus:'C3:E5'` zooms in. Results as pictures: deformed shape, members coloured by `Nx/Vz/My/Mz`. `target:'axisvm'` captures AxisVM's own window (its contours and result displays). |
| `query` | Text, cheapest first. **Model:** summary → one line per element (section, material, nodes, length, orientation) → detail (releases, loads, contour). **Loads**, **results** (displacements, reactions with sum, member and surface force extremes), **catalog** (sections/materials), **api** (exact signatures, records and enums of *your* AxisVM's COM type library), docs, library, **status** (dialogs with screenshots, even while AxisVM is busy), instances. |
| `edit` | A compact **shorthand**: one line per action for members, slabs/walls/shells, holes, supports, releases, load cases, loads, combinations, set/delete/select. `@ x=0:6:24` repeats lines. Members are split at shared nodes so the structure connects. Also analysis, DXF/IFC/AXS/PDF import, **Rhino import**, DXF/IFC export, open/save. |
| `run` | Python with PyAxisVM on the open model, with helpers (`kit`, `h('l3')`, `q('type:beam')`). Supports patch edits, reports the model delta, and adds a checkpoint. |
| `undo` | Revert to a checkpoint through AxisVM's own undo (also Ctrl+Z in AxisVM). It refuses if you changed the model in AxisVM meanwhile. |
| `memory` | Your preferences and workflows, learned rules (user-approved), mistake log, script library. |

Example `edit`, a complete frame in 12 lines:

```text
use mat=S 235
sec COL = HEB 200
sec BM = IPE 300
column 0,0,0 0,0,3.5 sec=COL @ x=0:6:12 y=0,5
beam 0,0,3.5 12,0,3.5 sec=BM @ y=0,5
beam 0,0,3.5 0,5,3.5 sec=BM @ x=0:6:12
slab 0,0,3.5 12,0,3.5 12,5,3.5 0,5,3.5 t=0.2 mat=C30/37
support z=0 fixed
case G self
case Q
load Q d1 pz=-3
combo ULS = 1.35 G + 1.5 Q
```

The full AxisVM COM API (204 interfaces, ~5,000 methods) is **not** turned into tools: too many tools confuse a model and cost tokens on every request. The common modelling path is one `edit`. Everything else goes through `run`, guided by `query {scope:'api'}`, which serves exact signatures from the installed version.

### Rhino → AxisVM

`skill/nextra-axisvm/rhino/rhino_export.py` runs inside Rhino 8 (with [NextraRhinoGh](https://github.com/nextra-studio/nextra-rhinogh) or Rhino's ScriptEditor). It writes the AxisBridge JSON. `edit {import:'…json'}` builds the model with the same AxisModelBuilder as the *N. Rhino Import* add-on, now running headless inside the NextraAxisVM add-on (node merging, intersections, catalog lookups, supports, releases and loads from `Ax_*` user texts, one undo step).

### What is possible, and what is not

See [dev/PLAN.md](dev/PLAN.md). In short:
- **Possible:** the open model, several instances, modelling, loads, linear analysis, results, import/export, Rhino import, undo, pictures, setup without a terminal.
- **Not possible / out of scope:** attaching without the add-on (AxisVM does not register itself for COM clients), answering AxisVM dialogs silently, more than one model per AxisVM window, and shorthand for design checks (use `run`).

## Testing

`python test/regress.py --launch` starts a separate AxisVM and runs the regression suite through the MCP bridge, the same path an AI app uses. It has **34 steps, all passing**, including hand-calculation checks: frame + slab self-weight (323 kN), ULS combination (706.2 kN = 1.35 G + 1.5 Q), and a simply supported beam (reactions 90 kN, max moment PL/4 + qL²/8 = 140 kNm).

## Your own instructions

The folder `%APPDATA%\NextraAxisVM\user` holds `preferences.md` (read every session), `workflows/*.md` (index at session start, opened when the request matches), and `scripts/` (run by name). The AI saves lasting preferences and verified workflows there. Plugin updates never touch it.

**Config** (`%APPDATA%\NextraAxisVM\config.json`, optional): `python` (interpreter), `user_dir`, `memory_dir`, `library_dirs`, `mesh_size` (default mesh size in m), `api_text` (path to a text export of the AxisVM COM PDF; its paragraphs are appended to API answers), `skill_dir`.

## Repository

```
addon/NextraAxisVM   C# add-on (.NET 4.8): registers AxisVM for the tools at start-up (ROT); headless Rhino import
addon/bin            built NextraAxisVM.dll (committed; setup copies it into AxisVM\AddOns)
engine/              Python worker: conn (attach/instances), query, edit (shorthand), run, undo, view, memory, apidocs, comkit
bridge/              MCP stdio server (zero-dependency Node) + .mcpb manifest; supervises the worker, runs setup on first use
setup/               setup.ps1 + pinned requirements (Setup.bat at the root)
skill/nextra-axisvm  SKILL.md, shorthand.md, workflows.md, api/axisvm-com.md, rhino/rhino_export.py
plugin/              generated by tools/make_plugin.py: one plugin for Claude Code/Desktop and Codex/ChatGPT
.claude-plugin/      Claude marketplace catalog · .agents/plugins/  OpenAI marketplace catalog
tools/               make_plugin.py (plugin + dist/ releases), nx.py (MCP test client), install_diagrams.py
test/                regress.py (live regression suite)
dev/                 PLAN.md (architecture, scope, limits), PROGRESS.md
```

<details>
<summary>Maintainers: build and publish</summary>

1. Add-on: `cd addon/NextraAxisVM && dotnet build -c Release` (output `addon/bin/NextraAxisVM.dll`, needs AxisVM installed for the interface DLL; override with `-p:AxisVMDir=…`).
2. Bump the version in `bridge/manifest.json`, `bridge/server/index.js`, `engine/nextra_axisvm/core.py` and `addon/NextraAxisVM/Host.cs` + `.csproj`.
3. `python tools/make_plugin.py`. Commit `plugin/`, `.claude-plugin/` and `.agents/`.
4. `python test/regress.py --launch`.
5. `gh release create v<ver> dist/nextra-axisvm-plugin.zip dist/nextra-axisvm-gpt-plugin.zip dist/nextra-axisvm-agent-kit.zip dist/nextra-axisvm-<ver>.mcpb dist/nextra-axisvm-skill.zip dist/NextraAxisVM-Setup.zip`

Keep the ZIP file names stable so the download links keep working.

</details>

## License

[Apache License 2.0](LICENSE). PyAxisVM is MIT-licensed by InterCAD. AxisVM is a product of InterCAD; NextraAxisVM is an independent project.

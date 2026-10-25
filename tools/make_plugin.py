"""Build plugin/nextra-axisvm/ (committed, so the GitHub repo works as a marketplace) and the release files in dist/.

plugin/nextra-axisvm/                one folder = MCP server + skill, for Claude Code / Desktop and Codex / ChatGPT desktop
  .claude-plugin/plugin.json, .mcp.json         Claude
  .codex-plugin/plugin.json, codex.mcp.json     OpenAI
  server/index.js                               MCP bridge (Node)
  server/engine/                                Python worker (PyAxisVM)
  server/setup/                                 setup.ps1 + pinned requirements (the bridge runs it on first use)
  server/addon/bin/NextraAxisVM.dll             AxisVM add-on (setup copies it into AxisVM's AddOns folder)
  skills/nextra-axisvm/                         the skill
dist/  nextra-axisvm-plugin.zip · nextra-axisvm-gpt-plugin.zip · nextra-axisvm-agent-kit.zip · nextra-axisvm-<ver>.mcpb
       nextra-axisvm-skill.zip · NextraAxisVM-Setup.zip (Setup.bat for users who prefer to install the environment first)
"""
import json
import os
import shutil
import sys
import zipfile

repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
man = json.load(open(os.path.join(repo, "bridge", "manifest.json"), encoding="utf-8"))
ver, desc = man["version"], man["description"]
name = "nextra-axisvm"
url = "https://github.com/nextra-studio/nextra-axisvm"
home = "https://nextra.studio/"
author = {"name": "Tatsuki", "url": url}
keywords = ["axisvm", "structural", "fem", "mcp", "pyaxisvm"]
root = os.path.join(repo, "plugin", name)
dist = os.path.join(repo, "dist")
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "obj", "*.user")


def write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        if isinstance(obj, str):
            f.write(obj)
        else:
            json.dump(obj, f, indent=2)
            f.write("\n")


def zipdir(src, out, prefix=""):
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for d, dirs, files in os.walk(src):
            dirs[:] = [x for x in dirs if x != "__pycache__"]
            for f in sorted(files):
                full = os.path.join(d, f)
                z.write(full, prefix + os.path.relpath(full, src).replace(os.sep, "/"))
    return out


def server_into(dst):
    """bridge + engine + setup + add-on DLL: everything the MCP server needs."""
    shutil.copytree(os.path.join(repo, "bridge", "server"), dst, dirs_exist_ok=True, ignore=IGNORE)
    shutil.copytree(os.path.join(repo, "engine"), os.path.join(dst, "engine"), dirs_exist_ok=True, ignore=IGNORE)
    shutil.copytree(os.path.join(repo, "setup"), os.path.join(dst, "setup"), dirs_exist_ok=True, ignore=IGNORE)
    os.makedirs(os.path.join(dst, "addon", "bin"), exist_ok=True)
    shutil.copy(os.path.join(repo, "addon", "bin", "NextraAxisVM.dll"), os.path.join(dst, "addon", "bin", "NextraAxisVM.dll"))


# ---------------------------------------------------------------- plugin folder
shutil.rmtree(root, ignore_errors=True)
shutil.copytree(os.path.join(repo, "skill", name), os.path.join(root, "skills", name), dirs_exist_ok=True, ignore=IGNORE)
server_into(os.path.join(root, "server"))
os.makedirs(os.path.join(root, "assets"), exist_ok=True)
shutil.copy(os.path.join(repo, "docs", "img", "icon.svg"), os.path.join(root, "assets", "icon.svg"))

write(os.path.join(root, ".claude-plugin", "plugin.json"), {
    "name": name, "version": ver, "description": desc, "author": author, "homepage": home, "repository": url,
    "license": "Apache-2.0", "keywords": keywords})
write(os.path.join(root, ".mcp.json"), {"mcpServers": {name: {"command": "node", "args": ["${CLAUDE_PLUGIN_ROOT}/server/index.js"],
                                                             "env": {"NEXTRA_MODE": "full"}}}})
write(os.path.join(repo, ".claude-plugin", "marketplace.json"), {
    "name": name, "owner": {"name": "Tatsuki"}, "description": "NextraAxisVM: AxisVM tools and skill for AI agents",
    "plugins": [{"name": name, "displayName": "NextraAxisVM", "description": desc, "version": ver, "category": "engineering",
                 "source": "./plugin/" + name, "homepage": home}]})
write(os.path.join(root, "codex.mcp.json"), {"mcpServers": {name: {"command": "node", "args": ["server/index.js"], "cwd": ".",
                                                                 "env": {"NEXTRA_MODE": "full"}, "startup_timeout_sec": 30,
                                                                 "tool_timeout_sec": 1200}}})
write(os.path.join(root, ".codex-plugin", "plugin.json"), {
    "name": name, "version": ver, "description": desc, "author": author, "homepage": home, "repository": url,
    "license": "Apache-2.0", "keywords": keywords, "skills": "./skills/", "mcpServers": "./codex.mcp.json",
    "interface": {
        "displayName": "NextraAxisVM", "shortDescription": "AxisVM structural analysis tools",
        "longDescription": desc + " Works on the AxisVM model you have open (NextraAxisVM add-on, installed automatically on first use).",
        "developerName": "Tatsuki", "category": "Engineering", "capabilities": ["Read", "Write"], "websiteURL": home,
        "defaultPrompt": ["Build a two-bay steel frame with a concrete slab in AxisVM and analyse it",
                          "Check the model I have open in AxisVM and summarise the results"],
        "brandColor": "#1A7F37", "composerIcon": "./assets/icon.svg", "logo": "./assets/icon.svg"}})
write(os.path.join(repo, ".agents", "plugins", "marketplace.json"), {
    "name": name, "interface": {"displayName": "NextraAxisVM"},
    "plugins": [{"name": name, "source": {"source": "local", "path": "./plugin/" + name},
                 "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}, "category": "Engineering"}]})

# ---------------------------------------------------------------- release files
os.makedirs(dist, exist_ok=True)
zp = zipdir(root, os.path.join(dist, name + "-plugin.zip"))
shutil.copyfile(zp, os.path.join(dist, name + "-gpt-plugin.zip"))
print("plugin %s -> %s (+ gpt copy)" % (ver, zp))

zipdir(os.path.join(repo, "skill", name), os.path.join(dist, name + "-skill.zip"), name + "/")

stage = os.path.join(dist, "_mcpb")
shutil.rmtree(stage, ignore_errors=True)
shutil.copy2(os.path.join(repo, "bridge", "manifest.json"), os.path.join(dist, "manifest.tmp.json"))
os.makedirs(stage, exist_ok=True)     # OneDrive can keep a just-deleted folder alive
shutil.move(os.path.join(dist, "manifest.tmp.json"), os.path.join(stage, "manifest.json"))
server_into(os.path.join(stage, "server"))
shutil.copytree(os.path.join(repo, "skill", name), os.path.join(stage, "skills", name), ignore=IGNORE, dirs_exist_ok=True)
zipdir(stage, os.path.join(dist, "%s-%s.mcpb" % (name, ver)))
shutil.rmtree(stage, ignore_errors=True)

setup_stage = os.path.join(dist, "_setup", "NextraAxisVM-Setup")
shutil.rmtree(os.path.join(dist, "_setup"), ignore_errors=True)
os.makedirs(setup_stage, exist_ok=True)
shutil.copy(os.path.join(repo, "Setup.bat"), setup_stage)
shutil.copytree(os.path.join(repo, "setup"), os.path.join(setup_stage, "setup"), ignore=IGNORE, dirs_exist_ok=True)
os.makedirs(os.path.join(setup_stage, "addon", "bin"), exist_ok=True)
shutil.copy(os.path.join(repo, "addon", "bin", "NextraAxisVM.dll"), os.path.join(setup_stage, "addon", "bin"))
zipdir(os.path.join(dist, "_setup"), os.path.join(dist, "NextraAxisVM-Setup.zip"))
shutil.rmtree(os.path.join(dist, "_setup"), ignore_errors=True)

# agent kit: one folder for any agent (Codex project, Claude Code folder, others)
KIT = name + "-kit"
kit = os.path.join(dist, KIT)
shutil.rmtree(kit, ignore_errors=True)
for rel in (".agents/skills/" + name, ".claude/skills/" + name, "skills/" + name):
    shutil.copytree(os.path.join(repo, "skill", name), os.path.join(kit, rel), dirs_exist_ok=True, ignore=IGNORE)
server_into(os.path.join(kit, "server"))
shutil.copytree(root, os.path.join(kit, "plugin", name), dirs_exist_ok=True)
for rel in (".claude-plugin/marketplace.json", ".agents/plugins/marketplace.json"):
    os.makedirs(os.path.dirname(os.path.join(kit, rel)), exist_ok=True)
    shutil.copy(os.path.join(repo, rel), os.path.join(kit, rel))
shutil.copy(os.path.join(repo, "Setup.bat"), kit)
shutil.copytree(os.path.join(repo, "setup"), os.path.join(kit, "setup"), dirs_exist_ok=True, ignore=IGNORE)
os.makedirs(os.path.join(kit, "addon", "bin"), exist_ok=True)
shutil.copy(os.path.join(repo, "addon", "bin", "NextraAxisVM.dll"), os.path.join(kit, "addon", "bin"))
write(os.path.join(kit, ".mcp.json"), json.dumps({"mcpServers": {name: {"command": "node", "args": ["server/index.js"], "env": {"NEXTRA_MODE": "full"}}}}, indent=2) + "\n")
write(os.path.join(kit, ".codex", "config.toml"), '[mcp_servers.%s]\ncommand = "node"\nargs = ["server/index.js"]\ntool_timeout_sec = 1200\n\n[mcp_servers.%s.env]\nNEXTRA_MODE = "full"\n' % (name, name))
write(os.path.join(kit, "AGENTS.md"), """# NextraAxisVM for AxisVM (agent kit %s)

This folder lets an AI agent work in AxisVM. Everything is here.

1. **Setup (once):** double-click `Setup.bat`. It installs Python + PyAxisVM in %%LOCALAPPDATA%%\\NextraAxisVM and the
   NextraAxisVM add-on into AxisVM. Restart AxisVM once afterwards. Node.js 18+ must be installed.
2. **Tools (MCP server):** `node server/index.js` over stdio, from this folder. It is already registered for Claude Code
   (`.mcp.json`) and Codex (`.codex/config.toml`). For other clients register command `node` with argument
   `<this folder>/server/index.js`.
3. **Skill:** read `skills/%s/SKILL.md` before using the tools (also in `.agents/skills/` and `.claude/skills/`).
4. Six tools: view, query, edit, run, undo, memory. Start with `memory {action:'list'}`, then `query {}`.
""" % (ver, name))
write(os.path.join(kit, "CLAUDE.md"), "@AGENTS.md\n")
zipdir(kit, os.path.join(dist, name + "-agent-kit.zip"), KIT + "/")
shutil.rmtree(kit, ignore_errors=True)
for f in sorted(os.listdir(dist)):
    p = os.path.join(dist, f)
    if os.path.isfile(p):
        print("  %-40s %8.1f kB" % (f, os.path.getsize(p) / 1024))
sys.exit(0)

"""User memory (same contract as NextraRhinoGh), stored in %APPDATA%/NextraAxisVM:

  user/preferences.md     standing instructions, shown at every session start (memory list)
  user/workflows/*.md     index (name + `when:`) at session start, full text on demand (query docs)
  user/scripts/           the user's Python scripts for `run {lib:'name'}`
  memory/rules.md         learned rules, only written after the user approved them (compact -> set_rules)
  memory/mistakes.log     raw error log (auto + manual)
  memory/library/         scripts saved by the AI (run save_as / memory save_script)
Nothing here is overwritten by plugin updates. Files starting with "_" are templates.
"""
import glob
import json
import os
import re
import shutil
import time
from collections import Counter

from .core import APPDIR, ENGINE_DIR, STATE, NxError, cfg, like, trunc

PREFS_CAP, RULES_CAP = 1500, 2000


def user_dir():
    d = cfg("user_dir") or os.path.join(APPDIR, "user")
    for sub in ("workflows", "scripts"):
        os.makedirs(os.path.join(d, sub), exist_ok=True)
    _seed(d)
    return d


def mem_dir():
    d = cfg("memory_dir") or os.path.join(APPDIR, "memory")
    os.makedirs(os.path.join(d, "library"), exist_ok=True)
    return d


def _p(f):
    return os.path.join(mem_dir(), f)


def _read(p):
    try:
        with open(p, encoding="utf-8-sig") as f:
            return f.read()
    except OSError:
        return ""


def _write(p, text):
    existed = os.path.exists(p)
    if existed:
        shutil.copyfile(p, p + ".bak")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return ("updated " if existed else "saved ") + p + (" (previous version: .bak)" if existed else "")


# ------------------------------------------------------------------ mistakes
def autolog(kind, sig, fix=None):
    try:
        sig = trunc(re.sub(r"\s+", " ", sig), 160)
        with open(_p("mistakes.log"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": kind, "sig": sig, "fix": fix}) + "\n")
        STATE["mem.lastsig"] = sig
    except Exception:
        pass


def _mistakes():
    out = []
    for line in _read(_p("mistakes.log")).splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out


def recurring_hint():
    sig = STATE.pop("mem.lastsig", None)
    if not sig or STATE.get("mem.hinted." + sig):
        return None
    n = sum(1 for m in _mistakes() if m.get("sig") == sig)
    if n < 3:
        return None
    STATE["mem.hinted." + sig] = True
    return ("recurring mistake (%dx): %s. After fixing, record the lesson: memory {action:'log_mistake', text, fix}; "
            "later memory {action:'compact'}." % (n, sig))


# ------------------------------------------------------------------ preferences / workflows
def _pref_key(line):
    m = re.match(r"^([\w \-/]{1,30}):", line.lstrip("- ").strip())
    return m.group(1).strip().lower() if m else None


def _active(text):
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    lines = [l for l in text.splitlines() if not l.lstrip().startswith("//") and not l.startswith("# ")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def save_pref(text):
    text = text.strip().lstrip("- ").strip()
    key = _pref_key(text)
    if not key:
        raise NxError("a preference is one short `key: value` line", "example: units: kN and m, report forces in kN")
    p = os.path.join(user_dir(), "preferences.md")
    lines = _read(p).replace("\r", "").rstrip("\n").split("\n")
    idx = next((i for i, l in enumerate(lines) if _pref_key(l) == key), -1)
    if idx >= 0:
        lines[idx] = "- " + text
    else:
        lines.append("- " + text)
    new = "\n".join(lines).rstrip() + "\n"
    if len(_active(new)) > PREFS_CAP:
        raise NxError("preferences would exceed %d chars" % PREFS_CAP, "merge them: memory {action:'set_prefs', text:'…all…'}")
    _write(p, new)
    return ("pref updated in " if idx >= 0 else "pref added to ") + p


def set_prefs(text):
    new = (text or "").strip() + "\n"
    if len(_active(new)) > PREFS_CAP:
        raise NxError("preferences would exceed %d chars" % PREFS_CAP, "drop stale lines, one rule per line")
    return _write(os.path.join(user_dir(), "preferences.md"), new)


def meta(text, key):
    for l in text.replace("\r", "").split("\n")[:12]:
        m = re.match(r"^\s*" + re.escape(key) + r"\s*:\s*(.+?)\s*$", l, re.I)
        if m:
            return m.group(1)
    return None


def _slug(s):
    s = re.sub(r"[^\w\-]+", "_", (s or "").strip()).strip("_")
    if not s:
        raise NxError("name required")
    return s


def save_workflow(name, text, when):
    text = (text or "").replace("\r\n", "\n").strip()
    if not meta(text, "when"):
        if not when:
            raise NxError("a workflow needs `when` (one sentence: when should it be used?)", "memory {action:'save_workflow', name, when, text}")
        text = "---\nwhen: %s\n---\n%s" % (when.strip(), text)
    if len(text) > 4000:
        raise NxError("workflow exceeds 4000 chars", "keep steps and checks concise; long code belongs in a library script")
    return _write(os.path.join(user_dir(), "workflows", _slug(name) + ".md"), text + "\n")


def workflow_files():
    return sorted(f for f in glob.glob(os.path.join(user_dir(), "workflows", "*.md")) if not os.path.basename(f).startswith("_"))


# ------------------------------------------------------------------ library
def lib_dirs():
    dirs = [os.path.join(mem_dir(), "library"), os.path.join(user_dir(), "scripts"), os.path.join(skill_dir() or "", "library")]
    dirs += list(cfg("library_dirs") or [])
    seen, out = set(), []
    for d in dirs:
        if d and os.path.isdir(d) and d.lower() not in seen:
            seen.add(d.lower())
            out.append(d)
    return out


def lib_files():
    for d in lib_dirs():
        for f in sorted(glob.glob(os.path.join(d, "**", "*.py"), recursive=True))[:400]:
            yield f


def lib_summary(path):
    for l in _read(path).splitlines()[:25]:
        t = l.strip().strip("\"'#/* ")
        if len(t) > 3 and not t.startswith(("import", "from ", "!", "r:")):
            return trunc(t, 90)
    return ""


def lib_index(filt=None, cap=40):
    out = []
    for f in lib_files():
        name = os.path.splitext(os.path.basename(f))[0]
        s = lib_summary(f)
        if filt and filt.lower() not in (name + " " + s).lower():
            continue
        if len(out) >= cap:
            out.append("…")
            break
        out.append("- %s: %s" % (name, s))
    return "\n".join(out) if out else "(empty)"


def lib_find(name):
    if os.path.isfile(name):
        return name
    n = os.path.splitext(os.path.basename(name))[0].lower()
    hits = [f for f in lib_files() if os.path.splitext(os.path.basename(f))[0].lower() == n]
    if not hits:
        near = [os.path.splitext(os.path.basename(f))[0] for f in lib_files() if n in f.lower()][:5]
        raise NxError("library script '%s' not found" % name, "similar: %s · list: query {scope:'library'}" % ", ".join(near))
    return hits[0]


def lib_save(name, code, doc=None):
    name = _slug(name)
    if doc and not code.lstrip().startswith(('"""', "'''", "#")):
        code = '"""%s"""\n%s' % (doc, code)
    return _write(os.path.join(mem_dir(), "library", name + ".py"), code)


# ------------------------------------------------------------------ docs (skill files served through query docs)
def skill_dir():
    d = cfg("skill_dir")
    if d and os.path.isdir(d):
        return d
    for rel in ("../skill/nextra-axisvm", "../skills/nextra-axisvm", "../../skills/nextra-axisvm", "skill"):
        p = os.path.normpath(os.path.join(ENGINE_DIR, rel))
        if os.path.isfile(os.path.join(p, "SKILL.md")):
            return p
    return None


def docs(topic, r):
    sd = skill_dir()
    files = []
    pref = os.path.join(user_dir(), "preferences.md")
    user = [(pref, "preferences.md")] + [(f, "workflows/" + os.path.basename(f)) for f in workflow_files()]
    rel = {f: rr for f, rr in user}
    files += [f for f, _ in user]
    if sd:
        for f in sorted(glob.glob(os.path.join(sd, "**", "*.md"), recursive=True)):
            files.append(f)
            rel[f] = os.path.relpath(f, sd).replace("\\", "/")
    if not topic:
        for f in files:
            if os.path.basename(f).startswith("_"):
                continue
            t = _read(f)
            head = meta(t, "description") or meta(t, "when") or next((l for l in t.splitlines() if l.startswith("# ")), "")
            r.line("- %s%s: %s" % (rel[f], " (yours)" if f in dict(user) else "", trunc(head.lstrip("# "), 100)))
        r.line("read: query {scope:'docs', filter:'shorthand'} · a section: 'shorthand#loads' · a keyword")
        return
    section = None
    if "#" in topic:
        topic, section = topic.split("#", 1)
    want = topic if topic.endswith(".md") else topic + ".md"
    hit = next((f for f in files if rel[f].lower() == want.lower()), None) or \
        next((f for f in files if os.path.splitext(os.path.basename(f))[0].lower() == topic.lower()), None)
    if hit and not section:
        r.line(_read(hit).rstrip())
        return
    kw = (section or topic).lower()
    n = 0
    for f in ([hit] if hit else files):
        lines = _read(f).splitlines()
        for i, l in enumerate(lines):
            if not l.startswith("#") or kw not in l.lower():
                continue
            lvl = len(l) - len(l.lstrip("#"))
            j = i + 1
            while j < len(lines) and not (lines[j].startswith("#") and len(lines[j]) - len(lines[j].lstrip("#")) <= lvl):
                j += 1
            r.line("[%s]\n%s" % (rel[f], "\n".join(lines[i:min(j, i + 80)])))
            n += 1
            if n >= 3:
                return
    if n == 0:
        r.line("no doc section matches '%s'. Files: %s" % (kw, ", ".join(rel[f] for f in files)))


# ------------------------------------------------------------------ session + tool
def session_text():
    ud = user_dir()
    out = ["user folder: %s (persistent; plugin updates never touch it)" % ud]
    prefs = _active(_read(os.path.join(ud, "preferences.md")))
    out.append("## your preferences")
    out.append(prefs[:PREFS_CAP] if prefs else "(none yet)")
    wf = workflow_files()
    if wf:
        out.append("## your workflows (follow the matching one; read: query {scope:'docs', filter:'workflows/<name>'})")
        for f in wf[:40]:
            t = _read(f)
            out.append("- %s: %s" % (os.path.splitext(os.path.basename(f))[0], trunc(meta(t, "when") or "", 110)))
    rules = _read(_p("rules.md")).strip()
    out.append("## rules (learned, user-approved)")
    out.append(rules or "(none)")
    out.append("## script library")
    out.append(lib_index(None, 40))
    groups = Counter(m.get("sig") for m in _mistakes())
    rec = [(s, n) for s, n in groups.most_common(5) if n >= 2 and s and s not in rules]
    if rec:
        out.append("## recurring mistakes not yet in rules")
        out += ["- %dx %s" % (n, s) for s, n in rec]
    return "\n".join(out)


def compact():
    ms = _mistakes()
    out = ["mistakes.log: %d entries. Grouped (count · signature · latest fix):" % len(ms)]
    by = {}
    for m in ms:
        by.setdefault(m.get("sig"), []).append(m)
    for sig, items in sorted(by.items(), key=lambda kv: -len(kv[1]))[:25]:
        fix = items[-1].get("fix")
        out.append("- %dx [%s] %s%s" % (len(items), items[-1].get("kind"), sig, (" → " + trunc(fix, 120)) if fix else ""))
    out.append("current rules.md:\n" + (_read(_p("rules.md")).strip() or "(empty)"))
    out.append("Next: draft ≤ %d chars of short imperative rules (merge with the current ones), SHOW them to the user, and "
               "only after approval call memory {action:'set_rules', text}." % RULES_CAP)
    return "\n".join(out)


def run(a, r):
    action = (a.str("action", "list") or "list").lower()
    req = lambda k: a.str(k) or (_ for _ in ()).throw(NxError("'%s' is required for memory %s" % (k, action)))
    if action in ("list", "session"):
        r.line(session_text())
    elif action == "save_pref":
        r.line(save_pref(req("text")))
    elif action == "set_prefs":
        r.line(set_prefs(req("text")))
    elif action == "set_rules":
        t = req("text").strip() + "\n"
        if len(t) > RULES_CAP:
            raise NxError("rules would be %d chars (cap %d)" % (len(t), RULES_CAP), "merge similar rules")
        r.line(_write(_p("rules.md"), t))
    elif action == "log_mistake":
        autolog("manual", req("text"), a.str("fix"))
        STATE.pop("mem.lastsig", None)
        r.line("logged")
    elif action == "compact":
        r.line(compact())
    elif action == "save_workflow":
        r.line(save_workflow(req("name"), req("text"), a.str("when")))
    elif action == "save_script":
        r.line(lib_save(req("name"), req("code"), a.str("doc")))
    elif action in ("read_script", "read"):
        p = lib_find(req("name"))
        lines = _read(p).splitlines()
        r.line("%s (%d lines)" % (p, len(lines)))
        for i, l in enumerate(lines, 1):
            r.line("%4d| %s" % (i, l))
    elif action == "delete_script":
        p = lib_find(req("name"))
        if not os.path.abspath(p).lower().startswith(os.path.abspath(mem_dir()).lower()):
            raise NxError("only scripts in the AI's memory library can be deleted", p)
        os.remove(p)
        r.line("deleted " + p)
    else:
        raise NxError("memory action '%s' unknown" % action,
                      "list | save_pref | set_prefs | log_mistake | compact | set_rules | save_script | read_script | delete_script | save_workflow")


README = """# NextraAxisVM: your folder

Everything here is **yours**. The NextraAxisVM tools read it and pass it to the AI. Plugin updates never touch it.
Files whose names start with `_` are templates and are ignored.

| file / folder | what the AI does with it |
|---|---|
| `preferences.md` | read at the start of every session as standing instructions (units, naming, design code, report style) |
| `workflows/*.md` | the list (name and `when:` line) is shown at session start; the AI opens one when your request matches |
| `scripts/` | your Python scripts; the AI can list and run them (`run {lib:'name'}`). Put a one-line docstring at the top. |

A workflow starts with a `when:` line ("when the user asks for a timber floor check"), then short numbered steps.
"""


def _seed(d):
    for rel, text in (("README.md", README), ("preferences.md", "# Preferences (one `key: value` per line)\n"),
                      (os.path.join("workflows", "_TEMPLATE.md"), "---\nwhen: <one sentence: when to use this>\n---\n1. step\n2. step\nChecks: …\n")):
        p = os.path.join(d, rel)
        if not os.path.exists(p):
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)

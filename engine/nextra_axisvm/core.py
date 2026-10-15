"""Shared plumbing: replies, errors, argument access, paths, config, tool dispatch, status."""
import json
import os
import re
import time

VERSION = "0.1.0"
APPDIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "NextraAxisVM")
LOCALDIR = os.path.join(os.environ.get("LOCALAPPDATA") or APPDIR, "NextraAxisVM")
ENGINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUSY = {"tool": None, "since": None}
STATE = {}          # per-session state (binding, last code, last image, checkpoints, ...)


class NxError(Exception):
    """An error the LLM can act on: what went wrong + what to do instead."""

    def __init__(self, msg, hint=None):
        super().__init__(msg)
        self.hint = hint


class Reply:
    def __init__(self):
        self.lines = []
        self.images = []
        self.ok = True

    def line(self, s=""):
        self.lines.append(str(s))
        return self

    def text(self):
        return "\n".join(self.lines).rstrip()


class Args:
    """Typed access to tool arguments; remembers which keys were read so unknown ones can be reported."""

    def __init__(self, d):
        self.d = dict(d or {})
        self.used = set()

    def has(self, k):
        return k in self.d and self.d[k] is not None

    def get(self, k, default=None):
        self.used.add(k)
        v = self.d.get(k)
        return default if v is None else v

    def str(self, k, default=None):
        v = self.get(k, default)
        return default if v is None else str(v)

    def int(self, k, default=None):
        v = self.get(k, default)
        try:
            return int(v)
        except (TypeError, ValueError):
            raise NxError("'%s' must be an integer, got %r" % (k, v))

    def float(self, k, default=None):
        v = self.get(k, default)
        try:
            return float(v)
        except (TypeError, ValueError):
            raise NxError("'%s' must be a number, got %r" % (k, v))

    def bool(self, k, default=False):
        v = self.get(k, default)
        if isinstance(v, str):
            return v.strip().lower() in ("1", "true", "yes", "on")
        return bool(v)

    def unused(self):
        return [k for k in self.d if k not in self.used and k not in ("instance", "timeout")]


# ------------------------------------------------------------------ config
def config():
    p = os.path.join(APPDIR, "config.json")
    try:
        with open(p, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return {}


def cfg(key, default=None):
    v = config().get(key)
    return default if v is None else v


# ------------------------------------------------------------------ formatting
def num(v, nd=3):
    """Compact number: 6.000 -> 6, 0.12345 -> 0.123, 1e-12 -> 0."""
    if v is None:
        return "?"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return str(v)
    if abs(v) < 10 ** -(nd + 2):
        return "0"
    if abs(v) >= 1e6 or (abs(v) < 1e-3):
        return "%.*g" % (nd + 1, v)
    s = "%.*f" % (nd, v)
    return s.rstrip("0").rstrip(".") if "." in s else s


def xyz(p, nd=3):
    return "(%s,%s,%s)" % (num(p[0], nd), num(p[1], nd), num(p[2], nd))


def trunc(s, n):
    s = str(s)
    return s if len(s) <= n else s[: n - 1] + "…"


def like(text, pattern):
    """Case-insensitive match: exact unless the pattern has * or ?; then a glob."""
    text, pattern = str(text).lower(), str(pattern).lower()
    if "*" in pattern or "?" in pattern:
        rx = "^" + re.escape(pattern).replace(r"\*", ".*").replace(r"\?", ".") + "$"
        return re.match(rx, text) is not None
    return text == pattern


def ranges(nums, prefix=""):
    """[1,2,3,7,9,10] -> 'l1-l3 l7 l9-l10'."""
    nums = sorted(set(nums))
    out, i = [], 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        out.append("%s%d" % (prefix, nums[i]) if i == j else "%s%d-%s%d" % (prefix, nums[i], prefix, nums[j]))
        i = j + 1
    return " ".join(out)


# ------------------------------------------------------------------ dispatch
TOOLS = ("view", "query", "run", "edit", "undo", "memory")


def dispatch(tool, args):
    from . import conn, memory
    r = Reply()
    a = Args(args)
    t0 = time.time()
    try:
        if a.has("instance"):
            conn.bind(str(a.get("instance")))
        if tool == "query":
            from . import query
            query.run(a, r)
        elif tool == "view":
            from . import view
            view.run(a, r)
        elif tool == "edit":
            from . import edit
            edit.run(a, r)
        elif tool == "run":
            from . import runtool
            runtool.run(a, r)
        elif tool == "undo":
            from . import undo
            undo.run(a, r)
        elif tool == "memory":
            memory.run(a, r)
        else:
            raise NxError("unknown tool '%s'" % tool, "tools: " + ", ".join(TOOLS))
        bad = a.unused()
        if bad:
            r.line("(ignored args: %s)" % ", ".join(bad))
        hint = memory.recurring_hint()
        if hint:
            r.line(hint)
    except NxError as e:
        r.ok = False
        r.line("ERROR: %s" % e)
        if e.hint:
            r.line("hint: %s" % e.hint)
        memory.autolog(tool, str(e))
    except Exception as e:
        r.ok = False
        msg = conn.explain_com_error(e)
        r.line("ERROR: %s" % msg)
        memory.autolog(tool, msg)
        if conn.is_disconnect(e):
            conn.drop()
            r.line("hint: AxisVM was closed or restarted; the next call reconnects (query {scope:'instances'}).")
    dt = time.time() - t0
    if dt > 20:
        r.line("(%.0fs)" % dt)
    return r


def status_text(args=None):
    return status(args)[0]


def status(args=None):
    """Runs on the reader thread: no COM. Busy state, bound instance, AxisVM dialogs (with screenshots);
    args {answer:'Yes'} presses that button in AxisVM's dialog. Returns (text, images)."""
    from . import conn, win
    args = args or {}
    out, imgs = [], []
    if BUSY.get("tool"):
        out.append("busy: %s for %.0fs" % (BUSY["tool"], time.time() - (BUSY.get("since") or time.time())))
    else:
        out.append("idle")
    pid = (STATE.get("bound") or {}).get("pid")
    if pid:
        out.append("bound: AxisVM pid %s %s" % (pid, os.path.basename((STATE.get("bound") or {}).get("file") or "")))
        if args.get("answer"):
            res = win.click(int(pid), str(args["answer"]))
            out.append(res or "no dialog button '%s' found" % args["answer"])
            time.sleep(1.0)
        dlg = win.dialog_details(int(pid))
        for i, (hwnd, title, cls, buttons, texts) in enumerate(dlg):
            out.append("AxisVM dialog '%s' buttons [%s]%s (screenshot attached)" % (title, ", ".join(buttons),
                                                                                  (" text: " + " / ".join(texts)) if texts else ""))
            try:
                os.makedirs(os.path.join(LOCALDIR, "captures"), exist_ok=True)
                p = win.capture(hwnd, os.path.join(LOCALDIR, "captures", "dialog_%d_%d.png" % (int(time.time()), i)))
                if p:
                    imgs.append(p)
            except Exception as e:
                out.append("(capture failed: %s)" % e)
        if dlg:
            out.append("COM calls wait until it closes. Tell the user what it says. Press a button only when the choice is "
                       "clearly safe or the user agreed: query {scope:'status', answer:'<button>'}.")
    for i in conn.instances(quick=True):
        out.append("instance pid %s (add-on %s)" % (i.get("pid"), i.get("addon")))
    return "\n".join(out), imgs

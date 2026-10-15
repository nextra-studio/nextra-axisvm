"""Finding and attaching to AxisVM.

Each AxisVM with the NextraAxisVM add-on registers a host object in the Running Object Table as
!NextraAxisVM.Host.<pid> and writes %APPDATA%/NextraAxisVM/instances/axisvm-<pid>.json. The worker binds a session to
ONE instance (like NextraRhinoGh): NEXTRA_AXISVM_FILE / NEXTRA_AXISVM_PID, or `instance:'file.axs'|'<pid>'` on any call
(sticky). With several instances and no binding it refuses and lists them; a bound instance that is gone is an error,
never a silent switch to another AxisVM.
"""
import ctypes
import glob
import json
import os
import time
from ctypes import POINTER, byref, c_ulong

import comtypes
from comtypes import COMMETHOD, GUID, HRESULT, IUnknown
from comtypes.automation import IDispatch

from . import win
from .core import APPDIR, STATE, NxError

INSTANCES = os.path.join(APPDIR, "instances")


class IRunningObjectTable(IUnknown):
    _iid_ = GUID("{00000010-0000-0000-C000-000000000046}")
    _methods_ = [
        COMMETHOD([], HRESULT, "Register", (["in"], c_ulong, "f"), (["in"], POINTER(IUnknown), "p"),
                  (["in"], POINTER(IUnknown), "m"), (["out"], POINTER(c_ulong), "c")),
        COMMETHOD([], HRESULT, "Revoke", (["in"], c_ulong, "c")),
        COMMETHOD([], HRESULT, "IsRunning", (["in"], POINTER(IUnknown), "m")),
        COMMETHOD([], HRESULT, "GetObject", (["in"], POINTER(IUnknown), "m"), (["out"], POINTER(POINTER(IUnknown)), "o")),
    ]


_ole32 = ctypes.oledll.ole32


def rot_get(name):
    rot = POINTER(IRunningObjectTable)()
    _ole32.GetRunningObjectTable(0, byref(rot))
    mk = POINTER(IUnknown)()
    _ole32.CreateItemMoniker("!", name, byref(mk))
    return rot.GetObject(mk)


class Late:
    """Late-bound IDispatch caller (the .NET host publishes no type info, so names are resolved per call)."""

    def __init__(self, unk):
        self._d = unk.QueryInterface(IDispatch)
        self._ids = {}

    def call(self, name, *args):
        if name not in self._ids:
            self._ids[name] = self._d.GetIDsOfNames(name)[0]
        return self._d.Invoke(self._ids[name], *args)


def ax():
    import axisvm.com.tlb as t        # comtypes wrapper of the installed AxisVM type library
    return t


class Session:
    def __init__(self, app, host, pid, file=""):
        self.app, self.host, self.pid, self.file = app, host, pid, file
        self._py = None

    @property
    def model(self):
        return self.app.Models.Item[1]

    @property
    def pyapp(self):
        """PyAxisVM wrapper of the same application (axisvm.com.axapp.IAxisVMApplication)."""
        if self._py is None:
            from axisvm.com.axapp import IAxisVMApplication
            self._py = IAxisVMApplication(wrap=self.app)
        return self._py

    def alive(self):
        try:
            return self.app.Models.Count >= 0
        except Exception:
            return False


_session = None


def instances(quick=False):
    """Published AxisVM instances that are still running; with quick=False also their open file."""
    out = []
    for f in glob.glob(os.path.join(INSTANCES, "axisvm-*.json")):
        try:
            with open(f, encoding="utf-8-sig") as fh:
                c = json.load(fh)
        except Exception:
            continue
        if not win.alive(c.get("pid", 0)):
            try:
                os.remove(f)
            except OSError:
                pass
            continue
        out.append(c)
    if not quick:
        for c in out:
            try:
                host = Late(rot_get(c.get("host_moniker") or "NextraAxisVM.Host.%s" % c["pid"]))
                c["file"] = json.loads(host.call("Ping")).get("file", "")
                c["reachable"] = True
            except Exception as e:
                c["reachable"] = False
                c["why"] = explain_com_error(e)
    return sorted(out, key=lambda c: str(c.get("started", "")), reverse=True)


def describe(cs):
    return "; ".join("pid %s: %s%s" % (c["pid"], os.path.basename(c.get("file") or "") or "untitled",
                                       "" if c.get("reachable", True) else " (not reachable: %s)" % c.get("why", ""))
                     for c in cs)


def bind(spec):
    """instance:'house.axs' | '1234' — sticky for this session."""
    global _session
    spec = str(spec).strip()
    STATE["bound"] = {"pid": int(spec)} if spec.isdigit() else {"file": spec}
    _session = None


def _initial_binding():
    if "bound" in STATE:
        return
    if os.environ.get("NEXTRA_AXISVM_PID"):
        STATE["bound"] = {"pid": int(os.environ["NEXTRA_AXISVM_PID"])}
    elif os.environ.get("NEXTRA_AXISVM_FILE"):
        STATE["bound"] = {"file": os.environ["NEXTRA_AXISVM_FILE"]}


def _file_match(c, f):
    f = f.lower()
    full = (c.get("file") or "").lower()
    return os.path.basename(full) == f or f in full


def launch_allowed():
    """Starting a separate AxisVM is for development and tests (regress.py), not for AI clients: the tools work on the
    AxisVM the user opened. Enable with NEXTRA_AXISVM_ALLOW_LAUNCH=1 or "allow_launch": true in config.json."""
    from .core import cfg
    return os.environ.get("NEXTRA_AXISVM_ALLOW_LAUNCH") == "1" or bool(cfg("allow_launch"))


def not_found_message():
    running = win.axisvm_pids()
    if running:
        return ("AxisVM is running (pid %s) but the NextraAxisVM add-on is not loaded in it. Ask the user to run Setup.bat "
                "(installs the add-on) and restart AxisVM once; the add-on then connects automatically."
                % ", ".join(map(str, running)))
    return "AxisVM is not running. Ask the user to open AxisVM (with the NextraAxisVM add-on) and their model."


def get():
    """The bound, live AxisVM session. Attaches on first use; reconnects if AxisVM restarted with the same file."""
    global _session
    _initial_binding()
    if _session is not None and _session.alive():
        return _session
    _session = None
    b = STATE.get("bound")
    allc = instances()
    reach = [c for c in allc if c.get("reachable")]
    if b:
        if b.get("pid"):
            hit = [c for c in reach if int(c["pid"]) == int(b["pid"])]
            if not hit and b.get("file"):
                hit = [c for c in reach if _file_match(c, b["file"])]   # AxisVM restarted with the same file
        else:
            hit = [c for c in reach if _file_match(c, b["file"])]
        if len(hit) > 1:
            raise NxError("'%s' matches several AxisVM instances (%s)" % (b.get("file"), describe(hit)), "pass instance:'<pid>'")
        if not hit:
            what = b.get("file") or "pid %s" % b.get("pid")
            raise NxError("the bound AxisVM (%s) is not running or not reachable. Open instances: %s"
                          % (what, describe(allc) or "none"), "pass instance:'<file or pid>' to rebind; " + not_found_message())
        c = hit[0]
    else:
        if not reach:
            if allc:
                raise NxError("AxisVM instance(s) found but not reachable: %s" % describe(allc),
                              "AxisVM and the AI app must run at the same privilege level (both normal or both as administrator).")
            raise NxError(not_found_message())
        if len(reach) > 1:
            raise NxError("%d AxisVM instances are open: %s" % (len(reach), describe(reach)),
                          "choose one with instance:'<file name or pid>' (sticky for this session)")
        c = reach[0]
    _session = attach(int(c["pid"]), c.get("host_moniker"))
    STATE["bound"] = {"pid": _session.pid, "file": c.get("file") or STATE.get("bound", {}).get("file")}
    return _session


def attach(pid, moniker=None):
    host = Late(rot_get(moniker or "NextraAxisVM.Host.%d" % pid))
    unk = host.call("GetApplication")
    app = unk.QueryInterface(ax().IAxisVMApplication)
    s = Session(app, host, pid)
    try:
        s.file = s.model.FileName
    except Exception:
        pass
    return s


def drop():
    global _session
    _session = None


def launch(path=None, visible=True, timeout=180):
    """Start a new AxisVM (it loads the add-on and publishes itself), bind to it, optionally open a file."""
    global _session
    from comtypes.client import CreateObject
    before = {int(c["pid"]) for c in instances(quick=True)}
    raw = CreateObject("AxisVM.AxisVMApplication", interface=ax().IAxisVMApplication)
    t = time.time()
    while not raw.Loaded:
        if time.time() - t > timeout:
            raise NxError("AxisVM did not finish starting within %ds" % timeout)
        time.sleep(0.25)
    raw.CloseOnLastReleased = 0        # stays open for the user after the tools disconnect
    raw.AskCloseOnLastReleased = 0
    raw.AskSaveOnLastReleased = 0
    if visible:
        raw.Visible = 1
    pid = None
    t = time.time()
    while time.time() - t < 30:
        new = [c for c in instances(quick=True) if int(c["pid"]) not in before]
        if new:
            pid = int(new[0]["pid"])
            break
        time.sleep(0.3)
    if pid:
        _session = attach(pid)
        note = "AxisVM started (pid %d), connected through the add-on" % pid
    else:
        _session = Session(raw, None, 0)
        note = ("AxisVM started without the NextraAxisVM add-on (run Setup.bat); connected directly, but other "
                "sessions cannot find this instance")
    STATE["bound"] = {"pid": pid or 0}
    if path:
        open_file(_session, path)
        note += "; opened " + path
    return _session, note


def open_file(s, path):
    path = os.path.abspath(path)
    if not os.path.exists(path):
        raise NxError("file not found: " + path)
    rc = s.model.LoadFromFile(path)
    if rc is not None and rc < 0:
        raise NxError("AxisVM could not open %s (%s)" % (path, error_name(rc)))
    s.file = path
    STATE.setdefault("bound", {})["file"] = os.path.basename(path)


# ------------------------------------------------------------------ errors
DISCONNECT = {-2147417848, -2147023174, -2147220995, -2147023170, -2147417836}
BUSY_CODES = {-2147418111: "AxisVM rejected the call (busy)", -2147417846: "AxisVM is busy and asked to retry later"}
_errnames = None


def error_name(code):
    """AxisVM methods return negative error codes; map them to the enum names of the type library."""
    global _errnames
    if _errnames is None:
        _errnames = {}
        try:
            from . import apidocs
            for name, val in apidocs.enum_constants():
                if isinstance(val, int) and val < 0:
                    _errnames.setdefault(val, []).append(name)
        except Exception:
            pass
    names = _errnames.get(int(code), [])
    return "%d%s" % (code, " = " + " / ".join(names[:4]) if names else "")


def hresult(e):
    if isinstance(e, comtypes.COMError):
        return e.hresult
    if isinstance(e, OSError) and getattr(e, "winerror", None):
        return e.winerror
    return None


def is_disconnect(e):
    return hresult(e) in DISCONNECT


def explain_com_error(e):
    h = hresult(e)
    if h in DISCONNECT:
        return "AxisVM is no longer reachable (closed or crashed)"
    if h in BUSY_CODES:
        d = []
        try:
            pid = (STATE.get("bound") or {}).get("pid")
            d = win.dialogs(int(pid)) if pid else []
        except Exception:
            pass
        return BUSY_CODES[h] + (": dialog open: " + "; ".join("'%s'" % t for t, _ in d) if d else "")
    if h == -2147221021:
        return "AxisVM instance not found in the Running Object Table (add-on not loaded, or different privilege level)"
    if isinstance(e, comtypes.COMError):
        return "COM error %s: %s" % (h, e.text or (e.details and e.details[0]) or "")
    return "%s: %s" % (type(e).__name__, e)

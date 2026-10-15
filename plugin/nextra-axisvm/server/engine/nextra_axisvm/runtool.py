"""run: Python in the NextraAxisVM worker, on the bound AxisVM, as one undo step with a model delta.

Names available in the code:
  app, model      raw COM IAxisVMApplication / IAxisVMModel (comtypes; out-params come back as return values)
  ax              the AxisVM type library: enums (ax.ltBeam, ax.lbTrue) and records (ax.RStiffnesses())
  pyax            PyAxisVM wrapper of the same app (pyax.model.Nodes …, PyAxisVM helpers)
  kit             verified helpers: kit.NodeIndex, kit.chain, kit.material, kit.section, kit.define_line,
                  kit.domain, kit.nodal_support, kit.line_support, kit.releases, kit.load_case, kit.nodal_force,
                  kit.beam_load, kit.area_load, kit.self_weight, kit.combination, kit.check, kit.rec
  h('l3')         COM object of line 3 / domain 'd2' (node 'n5' -> (x,y,z))
  q('type:beam')  (node ids, line ids, domain ids) with the same filter language as query
  snap()          fresh modeldata.Snapshot (nodes, lines, domains, supports, names)
  args            dict passed with run {args:{…}}
"""
import contextlib
import io
import os
import re
import traceback

from . import comkit, conn, memory, undo
from .core import STATE, NxError, trunc
from .modeldata import Snapshot


def run(a, r):
    s = conn.get()
    code = None
    if a.has("lib"):
        p = memory.lib_find(a.str("lib"))
        code = open(p, encoding="utf-8").read()
        src = "lib:" + os.path.basename(p)
    elif a.has("file"):
        p = a.str("file")
        if not os.path.exists(p):
            raise NxError("file not found: " + p)
        code = open(p, encoding="utf-8").read()
        src = p
    elif a.has("patch"):
        prev = STATE.get("last_code")
        if not prev:
            raise NxError("no previous code to patch in this session", "send code first")
        code = prev
        for i, pt in enumerate(a.get("patch") or []):
            f, rep = pt.get("find", ""), pt.get("replace", "")
            n = code.count(f)
            if n != 1:
                near = _closest(code, f)
                raise NxError("patch %d: 'find' matches %d times (must be exactly 1)" % (i + 1, n),
                              ("closest text: %r" % near) if near else "copy the exact text from the previous code")
            code = code.replace(f, rep)
        src = "patched"
    elif a.has("code"):
        code = a.str("code")
        src = "code"
    else:
        raise NxError("run needs code, patch, lib or file")
    STATE["last_code"] = code
    out = io.StringIO()
    ns = namespace(s, a.get("args") or {})
    ok = True
    with undo.step(s, a.str("label") or "Nextra run", r) as cid:
        try:
            with contextlib.redirect_stdout(out):
                exec(compile(code, "<run>", "exec"), ns)
        except NxError:
            ok = False
            raise
        except Exception as e:
            ok = False
            err = _error_report(code, e)
            text = out.getvalue()
            if text:
                r.line("stdout:\n" + trunc(text, 4000))
            r.line(err)
            r.ok = False
            from . import memory as mem
            mem.autolog("run", err.splitlines()[0])
    if ok:
        text = out.getvalue()
        r.lines.insert(0, "ok (%s)" % src)
        if text:
            r.lines.insert(1, "stdout:\n" + trunc(text, 6000))
        if a.has("save_as"):
            r.line(memory.lib_save(a.str("save_as"), code, a.str("doc")))


def namespace(s, args):
    from . import query as qmod
    model = s.model

    def h(handle):
        m = re.fullmatch(r"([nld])(\d+)", handle.strip())
        if not m:
            raise NxError("handle '%s' not understood" % handle, "n5 · l3 · d2")
        k, i = m.group(1), int(m.group(2))
        if k == "l":
            return model.Lines.Item[i]
        if k == "d":
            return model.Domains.Item[i]
        p = model.Nodes.GetNodeCoord(i)
        return p

    def q(filt=""):
        return qmod.select(Snapshot(model, loads=False), filt, model)

    class _LazyPyAx:            # PyAxisVM imports numba/sigmaepsilon (~30 s cold): load only when used
        def __getattr__(self, name):
            return getattr(s.pyapp, name)

    return {"__name__": "__nextra_run__", "app": s.app, "model": model, "ax": conn.ax(), "kit": comkit,
            "pyax": _LazyPyAx(), "h": h, "q": q, "snap": lambda: Snapshot(model), "args": args, "print": print}


def _error_report(code, e):
    tb = traceback.extract_tb(e.__traceback__)
    frames = [f for f in tb if f.filename == "<run>"]
    lines = code.splitlines()
    msg = conn.explain_com_error(e) if not isinstance(e, (SyntaxError,)) else "%s: %s" % (type(e).__name__, e)
    out = ["ERROR %s" % msg]
    ln = frames[-1].lineno if frames else getattr(e, "lineno", None)
    if ln:
        for i in range(max(1, ln - 2), min(len(lines), ln + 1) + 1):
            out.append("%s%4d| %s" % (">" if i == ln else " ", i, lines[i - 1]))
    out.append("fix with run {patch:[{find, replace}]} (no full resend). API: query {scope:'api', filter:'…'}")
    return "\n".join(out)


def _closest(code, f):
    f = f.strip().splitlines()[0] if f.strip() else ""
    if not f:
        return None
    for l in code.splitlines():
        if f[:20] and f[:20] in l:
            return l.strip()
    return None

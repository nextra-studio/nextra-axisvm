"""Checkpoints on top of AxisVM's own undo stack.

Every edit/run is wrapped as: snapshot → model.SaveUndo('Nextra cN …') → BeginUpdate … EndUpdate → snapshot. That is one
AxisVM undo step (the user can also press Ctrl+Z in AxisVM). `undo` calls model.Undo() once per checkpoint, newest first,
and verifies after each step that the model matches the snapshot taken before that checkpoint. If the model changed
after the last checkpoint (a manual edit in AxisVM sits on top of the stack), it refuses unless force:true.
"""
import contextlib

from .core import STATE, NxError
from .modeldata import Snapshot, delta


def _cps():
    return STATE.setdefault("checkpoints", [])


def reset():
    """Model replaced (open/new): old checkpoints no longer apply."""
    STATE["checkpoints"] = []


@contextlib.contextmanager
def step(s, label, r, quiet=False, report=True):
    m = s.model
    before = Snapshot(m, loads=False)
    n = STATE.get("cp_counter", 0) + 1
    STATE["cp_counter"] = n
    cid = "c%d" % n
    m.SaveUndo("%s %s" % (label, cid))
    m.BeginUpdate()
    failed = False
    try:
        yield cid
    except BaseException:
        failed = True
        raise
    finally:
        try:
            m.EndUpdate()
        except Exception:
            pass
        if failed:
            try:
                m.Undo()            # atomic / crash: back to the state before this step
                r.line("reverted (AxisVM undo)")
            except Exception:
                r.line("WARNING: could not revert; check the model or press Ctrl+Z in AxisVM")
        else:
            try:
                m.Refresh()
            except Exception:
                pass
    after = Snapshot(m, loads=False)
    if after.signature() == before.signature():
        # nothing changed: drop the undo point by not recording a checkpoint (AxisVM keeps an empty undo entry)
        _cps().append({"id": cid, "label": label, "before": before.signature(), "after": after.signature(), "empty": True})
        if report and not quiet:
            r.line("no model change")
        return
    _cps().append({"id": cid, "label": label, "before": before.signature(), "after": after.signature()})
    STATE["snap"] = after
    if report:
        d = delta(before, after)
        if d:
            r.line("model delta:")
            for x in d:
                r.line("  " + x)
        r.line("checkpoint %s (undo {checkpoint:'%s'} or Ctrl+Z in AxisVM)" % (cid, cid))


def run(a, r):
    from . import conn
    s = conn.get()
    m = s.model
    cps = _cps()
    if a.bool("list") or not (a.has("checkpoint") or a.has("steps")):
        if not cps:
            r.line("no checkpoints in this session")
        for c in cps:
            r.line("%s %s%s" % (c["id"], c["label"], " (no change)" if c.get("empty") else ""))
        return
    if a.has("checkpoint"):
        cid = a.str("checkpoint")
        idx = next((i for i, c in enumerate(cps) if c["id"] == cid), None)
        if idx is None:
            raise NxError("checkpoint %s not found" % cid, "undo {list:true}")
        todo = cps[idx:]
    else:
        todo = cps[-a.int("steps", 1):]
    cur = Snapshot(m, loads=False).signature()
    if cur != todo[-1]["after"] and not a.bool("force"):
        raise NxError("the model changed after checkpoint %s (edited in AxisVM?)" % todo[-1]["id"],
                      "undo would first revert those manual changes. Ask the user; then undo {…, force:true}, or Ctrl+Z in AxisVM")
    for c in reversed(todo):
        m.Undo()
        now = Snapshot(m, loads=False).signature()
        ok = now == c["before"]
        r.line("%s: %s %s" % (c["id"], "reverted" if ok else "undo applied, but the model differs from the snapshot", c["label"]))
        cps.remove(c)
    try:
        m.Refresh()
    except Exception:
        pass

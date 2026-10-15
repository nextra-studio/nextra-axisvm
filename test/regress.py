"""NextraAxisVM regression suite: drives a real AxisVM through the MCP bridge (same path as an AI app) and checks results.

  python test/regress.py                 # uses the only open AxisVM with the add-on (its model is REPLACED: use a test instance)
  python test/regress.py --instance 1234
  python test/regress.py --launch        # starts a separate AxisVM for the test

Every step prints PASS/FAIL; the exit code is the number of failures. Outputs go to test/out/.
"""
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from nx import Client  # noqa: E402

OUT = os.path.join(ROOT, "test", "out")
os.makedirs(OUT, exist_ok=True)
fails, steps, log = 0, 0, []


def check(name, cond, text=""):
    global fails, steps
    steps += 1
    ok = bool(cond)
    fails += 0 if ok else 1
    line = "%s %s" % ("PASS" if ok else "FAIL", name)
    print(line + ("" if ok else "\n      " + text.replace("\n", "\n      ")[:1500]), flush=True)
    log.append({"step": name, "ok": ok, "text": text[:4000]})


def num(pattern, text):
    m = re.search(pattern, text)
    return float(m.group(1)) if m else None


def main():
    c = Client()
    call = lambda tool, args=None: c.call(tool, args or {})
    if "--launch" in sys.argv:
        t, _, e = call("edit", {"launch": True})
        check("launch AxisVM", not e and "pid" in t, t)
    elif "--instance" in sys.argv:
        t, _, e = call("query", {"instance": sys.argv[sys.argv.index("--instance") + 1], "scope": "instances"})
        check("bind instance", not e, t)
    t, _, e = call("edit", {"new": True})
    check("new model", not e, t)

    # ---- the shorthand example from shorthand.md
    ops = """use mat=S 235
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
combo ULS = 1.35 G + 1.5 Q"""
    t, _, e = call("edit", {"ops": ops})
    check("frame shorthand applies fully", "ok: 12/12" in t, t)
    check("delta + checkpoint reported", "model delta" in t and "checkpoint c" in t, t)
    t, _, _ = call("query", {})
    check("summary counts", "nodal 6" in t and "plate 1" in t and "combinations 1" in t, t)
    t, _, _ = call("query", {"filter": "type:beam vertical"})
    check("filter columns", len([l for l in t.splitlines() if l.startswith("l")]) == 6, t)
    t, imgs, _ = call("view", {})
    check("view returns image with tags", imgs and "tagged:" in t, t)
    open(os.path.join(OUT, "view_frame.png"), "wb").write(imgs[0]) if imgs else None
    t, imgs, _ = call("view", {"focus": "C3:E5"})
    check("view zoom by cells", imgs and "focus C3:E5" in t, t)

    # ---- analysis and equilibrium
    t, _, e = call("edit", {"analyze": "linear"})
    check("linear analysis (auto mesh)", not e and "analysis done" in t, t)
    t, _, _ = call("query", {"scope": "results", "case": "G", "kind": "reactions"})
    rz = num(r"Rz (-?[\d.]+) kN", t)
    check("G reactions ≈ slab 294 + steel 29 kN", rz is not None and 300 < abs(rz) < 345, t)
    t, _, _ = call("query", {"scope": "results", "combo": "ULS"})
    rz = num(r"Rz (-?[\d.]+) kN", t)
    check("ULS reactions = 1.35 G + 1.5 x 3 x 60", rz is not None and abs(abs(rz) - 706.2) < 8, t)
    check("member + surface extremes", "max |My|" in t and "surface max |Mx|" in t, t)
    t, imgs, _ = call("view", {"combo": "ULS", "result": "deformed"})
    check("deformed shape image", imgs and "deformed shape" in t, t)
    open(os.path.join(OUT, "view_deformed.png"), "wb").write(imgs[0]) if imgs else None
    t, imgs, _ = call("view", {"target": "axisvm"})
    check("AxisVM window capture", bool(imgs), t)

    # ---- changes, partial failure, undo
    t, _, _ = call("edit", {"ops": "set l1 l2 sec=HEB 240\nbogus line"})
    check("partial apply reports failed line only", t.startswith("partial: 1/2") and "L2" in t, t)
    cp = re.search(r"checkpoint (c\d+)", t)
    t, _, _ = call("query", {"filter": "l1", "level": "list"})
    check("set changed section", "HEB 240" in t, t)
    t, _, e = call("undo", {"checkpoint": cp.group(1) if cp else "c1"})
    check("undo reverts", not e and "reverted" in t, t)
    t, _, _ = call("query", {"filter": "l1"})
    check("section back after undo", "HEB 200" in t, t)

    # ---- second model: releases, hole, nodal/line loads, line support, points
    call("edit", {"new": True})
    ops2 = """units mm
use mat=S 355 sec=rect 200x400
beam 0,0,0 8000,0,0 start=hinge end=hinge
support 0,0,0 8000,0,0 pinned
case P
load P 4000,0,0 fz=-50
load P l1 l2 qz=-5"""
    t, _, e = call("edit", {"ops": ops2})
    check("mm units, parametric section, point load splits beam", "ok:" in t and "split" in t, t)
    t, _, e = call("edit", {"analyze": "linear"})
    t, _, _ = call("query", {"scope": "results", "case": "P", "kind": "reactions"})
    rz = num(r"Rz (-?[\d.]+) kN", t)
    check("simply supported: 50 + 5x8 = 90 kN", rz is not None and abs(abs(rz) - 90) < 0.5, t)
    t, _, _ = call("query", {"scope": "results", "case": "P", "kind": "forces"})
    my = num(r"max \|My\| = (-?[\d.]+)", t)
    check("max moment = PL/4 + qL²/8 = 100 + 40 = 140 kNm", my is not None and abs(abs(my) - 140) < 1.5, t)

    call("edit", {"new": True})
    t, _, _ = call("edit", {"ops": "shell 0,0,0 6,0,0 6,4,0 0,4,0 t=0.25 mat=C25/30\nhole d1 2,1,0 3,1,0 3,2,0 2,2,0\nsupport l1 l2 l3 l4 pinned\ncase G self"})
    check("shell with hole + line supports", t.startswith("ok:") and "ls" in t, t)
    t, _, _ = call("query", {"filter": "d1", "level": "detail"})
    check("hole detected", "holes: 1" in t, t)

    # ---- catalog, api, docs, status, memory, run
    t, _, _ = call("query", {"scope": "catalog", "filter": "IPE 3*"})
    check("catalog search", "IPE 300" in t, t)
    t, _, _ = call("query", {"scope": "api", "filter": "IAxisVMLoads.AddNodalForce"})
    check("api exact signature + record", "RLoadNodalForce" in t and "Fz" in t, t)
    t, _, _ = call("query", {"scope": "docs", "filter": "shorthand#supports"})
    check("docs section", "support" in t.lower(), t)
    t, _, _ = call("query", {"scope": "status"})
    check("status", "idle" in t or "busy" in t, t)
    t, _, _ = call("memory", {"action": "list"})
    check("memory list", "your preferences" in t, t)
    t, _, e = call("run", {"code": "n, l, d = q('type:shell')\nprint('domains', d)\nprint(model.Domains.Item[d[0]].Area)"})
    check("run with helpers", not e and "domains [1]" in t, t)
    t, _, e = call("run", {"code": "x = model.Nodes.Count\ny = model.Nope"})
    check("run error shows failing line", e and ">   2|" in t, t)
    t, _, e = call("run", {"patch": [{"find": "model.Nope", "replace": "model.Lines.Count"}]})
    check("run patch fixes", not e, t)

    # ---- export / import round trip
    dxf = os.path.join(OUT, "roundtrip.dxf")
    t, _, e = call("edit", {"export": dxf})
    check("export dxf", not e and os.path.exists(dxf), t)
    call("edit", {"new": True})
    t, _, e = call("edit", {"import": dxf, "import_options": {"unit": "m"}})
    check("import dxf", not e, t)
    t, _, _ = call("query", {})
    check("dxf geometry arrived", re.search(r"lines [1-9]", t) is not None, t)

    c.close()
    with open(os.path.join(OUT, "regress.json"), "w", encoding="utf-8") as f:
        json.dump({"time": time.strftime("%Y-%m-%d %H:%M"), "steps": steps, "fails": fails, "log": log}, f, indent=1)
    print("\n%d/%d passed" % (steps - fails, steps))
    sys.exit(fails)


if __name__ == "__main__":
    main()

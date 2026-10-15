"""Export Rhino geometry to the AxisBridge JSON (schema 2) that NextraAxisVM imports: edit {import:'<path>.json'}.

Runs INSIDE Rhino 8 (Python 3): with NextraRhinoGh `run {file:'<this file>', args:{...}}`, or in Rhino's ScriptEditor.
No AxisBridge plug-in needed. Ax_* user texts on objects (written by AxisBridge or by hand) are passed through as the
element attributes; objects without them get the defaults below.

args (all optional):
  path            output file (default %TEMP%/nextra_rhino_export.json)
  selected        True = only selected objects (default: all visible, unlocked objects)
  layers          list of layer names (with sublayers) to export
  line_type       default Ax_Type for curves without one: Beam | Rib | Truss | Simple   (default Beam)
  surface_type    default Ax_FEType for surfaces without one: Shell | Plate | Membrane  (default Shell)
  material, section, thickness   defaults for untagged objects (e.g. 'S 235', 'IPE 300', '200' in model units)
  layer_rules     {'Columns': {'Ax_Type':'Beam','Ax_Section':'HEB 240'}, 'Slabs': {'Ax_FEType':'Plate', ...}}
                  attributes for objects on a layer (substring match, case-insensitive) that lack them
"""
import json
import os
import tempfile

import Rhino
import scriptcontext as sc
import System

A = globals().get("args") or {}
doc = sc.doc
tol = doc.ModelAbsoluteTolerance
out = {"schema": 2,
       "source": {"file": doc.Name or "", "unitSystem": str(doc.ModelUnitSystem), "tolerance": tol},
       "library": {}, "points": [], "lines": [], "domains": [], "warnings": []}


def xyz(p):
    return [round(p.X, 6), round(p.Y, 6), round(p.Z, 6)]


def layer_path(obj):
    return doc.Layers[obj.Attributes.LayerIndex].FullPath


def attrs_of(obj, kind):
    a = {}
    us = obj.Attributes.GetUserStrings()
    for k in us.AllKeys:
        if k.startswith("Ax_"):
            a[k] = us[k]
    lp = layer_path(obj).lower()
    for name, rule in (A.get("layer_rules") or {}).items():
        if name.lower() in lp:
            for k, v in rule.items():
                a.setdefault(k, str(v))
    if kind == "line":
        a.setdefault("Ax_Type", A.get("line_type", "Beam"))
        if a["Ax_Type"] in ("Beam", "Rib", "Truss"):
            if A.get("material"):
                a.setdefault("Ax_Material", A["material"])
            if A.get("section"):
                a.setdefault("Ax_Section", A["section"])
    elif kind == "surface":
        a.setdefault("Ax_FEType", A.get("surface_type", "Shell"))
        if A.get("material"):
            a.setdefault("Ax_Material", A["material"])
        if A.get("thickness"):
            a.setdefault("Ax_Thickness", str(A["thickness"]))
    return a


def loop_points(loop):
    crv = loop.To3dCurve()
    ok, pl = crv.TryGetPolyline()
    if ok:
        pts = list(pl)
    else:
        ts = crv.DivideByCount(32, True)
        pts = [crv.PointAt(t) for t in ts] if ts else []
    if len(pts) > 1 and pts[0].DistanceTo(pts[-1]) <= tol:
        pts = pts[:-1]
    return [xyz(p) for p in pts]


def add_curve(obj, crv, gid):
    a = attrs_of(obj, "line")
    if crv.IsLinear(tol):
        out["lines"].append({"guid": gid, "geom": "line", "start": xyz(crv.PointAtStart), "end": xyz(crv.PointAtEnd), "attrs": a})
        return
    ok, arc = crv.TryGetArc(tol)
    if ok and not crv.IsClosed:
        out["lines"].append({"guid": gid, "geom": "arc", "start": xyz(crv.PointAtStart), "end": xyz(crv.PointAtEnd),
                             "arcMid": xyz(crv.PointAt(crv.Domain.Mid)), "attrs": a})
        return
    ok, pl = crv.TryGetPolyline()
    if not ok:
        ts = crv.DivideByCount(16, True)
        pts = [crv.PointAt(t) for t in ts]
        out["warnings"].append("%s: free-form curve approximated by %d segments" % (gid, len(pts) - 1))
    else:
        pts = list(pl)
    out["lines"].append({"guid": gid, "geom": "polyline", "start": xyz(pts[0]), "end": xyz(pts[-1]),
                         "points": [xyz(p) for p in pts], "attrs": a})


def add_brep(obj, brep, gid):
    a = attrs_of(obj, "surface")
    for i, face in enumerate(brep.Faces):
        if not face.IsPlanar(tol * 10):
            out["warnings"].append("%s face %d is not planar: skipped (AxisVM domains are planar)" % (gid, i))
            continue
        holes = [loop_points(l) for l in face.Loops if l.LoopType == Rhino.Geometry.BrepLoopType.Inner]
        d = {"guid": gid if brep.Faces.Count == 1 else "%s_f%d" % (gid, i), "contour": loop_points(face.OuterLoop), "attrs": a}
        if holes:
            d["holes"] = holes
        out["domains"].append(d)


layers = [l.lower() for l in (A.get("layers") or [])]
objs = doc.Objects.GetSelectedObjects(False, False) if A.get("selected") else doc.Objects.GetObjectList(Rhino.DocObjects.ObjectEnumeratorSettings())
n_skip = 0
for obj in objs:
    if obj.IsHidden or obj.IsLocked:
        continue
    if layers and not any(layer_path(obj).lower().startswith(l) for l in layers):
        continue
    gid = str(obj.Id)
    g = obj.Geometry
    if isinstance(g, Rhino.Geometry.Point):
        out["points"].append({"guid": gid, "xyz": xyz(g.Location), "attrs": attrs_of(obj, "point")})
    elif isinstance(g, Rhino.Geometry.Curve):
        if g.IsClosed and g.IsPlanar(tol) and obj.Attributes.GetUserString("Ax_FEType"):   # tagged outline = domain
            b = Rhino.Geometry.Brep.CreatePlanarBreps(g, tol)
            if b:
                add_brep(obj, b[0], gid)
                continue
        add_curve(obj, g, gid)
    elif isinstance(g, (Rhino.Geometry.Brep, Rhino.Geometry.Extrusion, Rhino.Geometry.Surface)):
        b = g if isinstance(g, Rhino.Geometry.Brep) else (g.ToBrep() if hasattr(g, "ToBrep") else Rhino.Geometry.Brep.CreateFromSurface(g))
        if b:
            add_brep(obj, b, gid)
    else:
        n_skip += 1

if n_skip:
    out["warnings"].append("%d object(s) of other types skipped (meshes, text, blocks...)" % n_skip)
path = A.get("path") or os.path.join(tempfile.gettempdir(), "nextra_rhino_export.json")
with open(path, "w", encoding="utf-8") as f:
    json.dump(out, f)
print("exported %d point(s), %d curve(s), %d surface(s) in %s -> %s" % (
    len(out["points"]), len(out["lines"]), len(out["domains"]), out["source"]["unitSystem"], path))
for w in out["warnings"][:10]:
    print("warning:", w)
print("next (NextraAxisVM): edit {import:'%s'}" % path.replace("\\", "/"))

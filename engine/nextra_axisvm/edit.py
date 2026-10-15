"""edit: change the model with the NextraAxisVM shorthand, plus file actions and analysis.

One line = one action; lines apply independently (failures are reported per line, the rest stays applied unless
atomic:true). The whole call is ONE AxisVM undo step and one checkpoint. Grammar: skill/nextra-axisvm/shorthand.md.
"""
import os
import re

from . import comkit as k
from . import conn, undo
from .core import STATE, NxError, num, ranges, trunc
from .modeldata import Snapshot, delta

KV = re.compile(r"(?:^|\s)([A-Za-z_][\w]*)=")
ELEMENTS = {"beam": "beam", "column": "beam", "rib": "rib", "truss": "truss", "bar": "truss", "line": None}
SURFACES = {"plate", "slab", "shell", "wall", "membrane"}


def run(a, r):
    if a.bool("launch"):
        s, note = conn.launch(a.str("open"))
        r.line(note)
        a.used.add("open")
    s = conn.get()
    m = s.model
    did = False
    if a.has("open") and not a.bool("launch"):
        conn.open_file(s, a.str("open"))
        r.line("opened %s" % a.str("open"))
        undo.reset()
        did = True
    if a.bool("new"):
        rc = s.app.Models.New()
        r.line("new model (%s)" % rc)
        undo.reset()
        did = True
    if a.has("ops") or a.has("import") or a.has("mesh"):
        with undo.step(s, a.str("label") or "Nextra edit", r):
            if a.has("import"):
                do_import(s, a.str("import"), a.get("import_options") or {}, r)
            if a.has("ops"):
                apply_ops(s, a.str("ops"), r, atomic=a.bool("atomic"), dry=a.bool("dry_run"))
            if a.has("mesh"):
                mesh(s, a.get("mesh"), r)
        did = True
    if a.has("analyze"):
        analyze(s, a.str("analyze"), a.get("mesh_size"), r)
        did = True
    if a.has("export"):
        export(s, a.str("export"), r)
        did = True
    if a.has("save"):
        p = os.path.abspath(a.str("save"))
        rc = m.SaveToFile(p, conn.ax().lbTrue if a.bool("save_results", True) else conn.ax().lbFalse)
        if k.code(rc) in (0, None) or (isinstance(k.code(rc), int) and k.code(rc) < 0):
            raise NxError("AxisVM could not save %s (%s)" % (p, rc))
        s.file = p
        r.line("saved %s" % p)
        did = True
    if not did:
        raise NxError("nothing to do", "edit {ops:'…'} | {analyze:'linear'} | {open|save|import|export:'path'} | {new:true} | {launch:true}")


# ------------------------------------------------------------------ shorthand
class Ctx:
    def __init__(self, s, r):
        self.s, self.m, self.r = s, s.model, r
        self.unit = 1.0
        self.tol = 0.001
        self.alias_mat, self.alias_sec = {}, {}
        self.default = {}
        self.nodes = None
        self.created = {"l": [], "d": [], "n": []}

    @property
    def ni(self):
        if self.nodes is None:
            self.nodes = k.NodeIndex(self.m, self.tol)
        return self.nodes

    def mat(self, name):
        name = name or self.default.get("mat")
        if not name:
            raise NxError("no material given", "add mat=S 235 (or set defaults: use mat=S 235 sec=IPE 300)")
        name = self.alias_mat.get(name, name)
        return k.material(self.m, name)

    def sec(self, name):
        name = name or self.default.get("sec")
        if not name:
            raise NxError("no cross-section given", "add sec=IPE 300 (or set defaults: use sec=IPE 300)")
        name = self.alias_sec.get(name, name)
        return k.section(self.m, name)


def split_kv(rest):
    """'0,0,0 6,0,0 sec=IPE 300 mat=S 235' -> (['0,0,0','6,0,0'], {'sec':'IPE 300','mat':'S 235'})."""
    ms = list(KV.finditer(rest))
    pos = rest[: ms[0].start()] if ms else rest
    kv = {}
    for i, mm in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(rest)
        kv[mm.group(1).lower()] = rest[mm.end():end].strip()
    return pos.split(), kv


def parse_list(v):
    """'0,6,12' or '0:6:24' (start:step:end) -> floats."""
    v = v.strip()
    if ":" in v:
        a, st, b = [float(x) for x in v.split(":")]
        n = int(round((b - a) / st)) if st else 0
        return [a + i * st for i in range(n + 1)]
    return [float(x) for x in re.split(r"[,\s]+", v) if x]


def apply_ops(s, text, r, atomic=False, dry=False):
    ctx = Ctx(s, r)
    lines = [l for l in text.replace("\r", "").split("\n")]
    ok = fail = 0
    for no, raw in enumerate(lines, 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        try:
            res = op(ctx, line, dry)
            ok += 1
            if res:
                r.line("L%d: %s" % (no, res))
        except NxError as e:
            fail += 1
            r.line("L%d `%s`: %s%s" % (no, trunc(line, 80), e, (" — " + e.hint) if e.hint else ""))
            if atomic:
                raise NxError("atomic: stopped at L%d; whole edit reverted" % no)
        except Exception as e:
            fail += 1
            r.line("L%d `%s`: %s" % (no, trunc(line, 80), conn.explain_com_error(e)))
            if atomic:
                raise NxError("atomic: stopped at L%d; whole edit reverted" % no)
    if ctx.nodes is not None and ctx.nodes.created and not dry:
        n = split_existing(ctx)
        if n:
            r.line("split %d existing line(s) at new nodes (connected)" % n)
    r.ok = fail == 0 or ok > 0
    r.lines.insert(0, "%s: %d/%d lines applied" % ("ok" if fail == 0 else "partial" if ok else "FAILED", ok, ok + fail))
    if fail and ok:
        r.line("fix only the failed lines (the others are applied)")


def split_existing(ctx):
    """New nodes that lie inside an existing line: split that line there, so the structure is connected."""
    m, ni = ctx.m, ctx.nodes
    new = set(ni.created)
    count = 0
    for _ in range(50):                        # one split per line per pass; ids are re-read every pass
        snap = Snapshot(m, loads=False)
        done = 0
        for lid in range(len(snap.lines) - 1, 0, -1):
            L = snap.lines[lid]
            if L["geom"] != 0:                 # straight lines only
                continue
            inner = [n for n in ni.on_segment(L["n1"], L["n2"]) if n in new]
            if inner:
                try:
                    res = m.Lines.Item[lid].SplitByNode(inner[0])
                    if k.code(res) and k.code(res) > 0:
                        done += 1
                except Exception:
                    pass
        count += done
        if not done:
            break
    return count


def pts(ctx, toks, kv):
    out = []
    for t in toks:
        if re.fullmatch(r"n\d+", t):
            out.append(int(t[1:]))
            continue
        try:
            c = [float(x) * ctx.unit for x in t.split(",")]
        except ValueError:
            raise NxError("'%s' is not a point x,y,z or node handle nN" % t)
        if len(c) == 2:
            c.append(0.0)
        if len(c) != 3:
            raise NxError("point '%s' needs x,y,z" % t)
        out.append(tuple(c))
    return out


def repeats(kv, unit):
    """@ suffix (kv keys dx/dy/dz or x/y/z after '@'): list of offsets."""
    if "@" not in kv:
        return [(0.0, 0.0, 0.0)]
    spec = kv.pop("@")
    xs = ys = zs = [0.0]
    for part in re.findall(r"([xyz])=([^\s]+)", spec):
        vals = [v * unit for v in parse_list(part[1])]
        if part[0] == "x":
            xs = vals
        elif part[0] == "y":
            ys = vals
        else:
            zs = vals
    return [(x, y, z) for z in zs for y in ys for x in xs]


def node_of(ctx, p, off=(0, 0, 0)):
    if isinstance(p, int):
        if off != (0, 0, 0):
            raise NxError("node handles cannot be repeated with @")
        return p
    return ctx.ni.get((p[0] + off[0], p[1] + off[1], p[2] + off[2]))


def handles(toks, prefix):
    out = []
    for t in toks:
        mm = re.fullmatch(prefix + r"(\d+)(?:-%s?(\d+))?" % prefix, t)
        if not mm:
            return None
        out += list(range(int(mm.group(1)), int(mm.group(2) or mm.group(1)) + 1))
    return out


def op(ctx, line, dry):
    m = ctx.m
    # pull the repeat suffix "@ x=0:6:24 y=0,5" out before key=value parsing
    at = None
    if " @" in line or line.startswith("@"):
        line, at = line.split("@", 1)
    word, _, rest = line.strip().partition(" ")
    word = word.lower()
    toks, kv = split_kv(rest)
    if at is not None:
        kv["@"] = at
    if dry:
        return "dry-run: %s parsed (%d positional, keys %s)" % (word, len(toks), ",".join(kv) or "-")

    if word == "units":
        u = (toks or ["m"])[0].lower()
        ctx.unit = {"m": 1.0, "cm": 0.01, "mm": 0.001}.get(u)
        if ctx.unit is None:
            raise NxError("units: m | cm | mm")
        return None
    if word == "tol":
        ctx.tol = float(toks[0]) * ctx.unit
        ctx.nodes = None
        return None
    if word == "use":
        ctx.default.update(kv)
        return None
    if word in ("mat", "sec"):
        mm = re.fullmatch(r"\s*(\S+)\s*=\s*(.+)", rest)
        if not mm:
            name = rest.strip()
            i = ctx.mat(name) if word == "mat" else ctx.sec(name)
            return "%s %s = #%d" % (word, name, i)
        alias, name = mm.group(1), mm.group(2).strip()
        (ctx.alias_mat if word == "mat" else ctx.alias_sec)[alias] = name
        i = ctx.mat(alias) if word == "mat" else ctx.sec(alias)
        return None

    if word in ELEMENTS:
        kind = ELEMENTS[word]
        lids = handles(toks, "l")
        made = []
        if lids:                                        # define existing lines
            for lid in lids:
                if kind:
                    k.define_line(m, lid, kind, ctx.mat(kv.get("mat")), ctx.sec(kv.get("sec")), ctx.sec(kv["sec2"]) if kv.get("sec2") else None)
                made.append(lid)
            return "%s %s" % (word, ranges(made, "l"))
        P = pts(ctx, toks, kv)
        if len(P) < 2:
            raise NxError("%s needs two or more points (x,y,z or nN) or line handles" % word)
        mat = ctx.mat(kv.get("mat")) if kind else 0
        sec = ctx.sec(kv.get("sec")) if kind else 0
        sec2 = ctx.sec(kv["sec2"]) if kind and kv.get("sec2") else None
        reused = 0
        for off in repeats(kv, ctx.unit):
            ns = [node_of(ctx, p, off) for p in P]
            for a_, b_ in zip(ns, ns[1:]):
                if a_ == b_:
                    raise NxError("zero-length segment (same node twice)")
                for lid, new in k.chain(m, ctx.ni, a_, b_, kv.get("split", "yes") != "no"):
                    reused += 0 if new else 1
                    if kind:
                        k.define_line(m, lid, kind, mat, sec, sec2)
                    made.append(lid)
                    ctx.created["l"].append(lid)
            if kv.get("release"):
                k.releases(m, made[-1], start=kv["release"], end=kv["release"])
        _post_line_opts(ctx, made, kv)
        return "%s %s%s" % (word, ranges(made, "l"), " (%d existing line(s) reused)" % reused if reused else "")

    if word in SURFACES:
        t = kv.get("t") or ctx.default.get("t")
        if not t:
            raise NxError("%s needs t=<thickness>" % word, "t in the current units (default m): t=0.2")
        thick = float(t) * ctx.unit
        mat = ctx.mat(kv.get("mat"))
        made = []
        lids = handles(toks, "l")
        if lids:
            made.append(k.domain(m, lids, word, thick, mat))
        else:
            P = pts(ctx, toks, kv)
            if len(P) < 3:
                raise NxError("%s needs 3+ corner points (or contour line handles)" % word)
            for off in repeats(kv, ctx.unit):
                ns = [node_of(ctx, p, off) for p in P]
                edge = [lid for i in range(len(ns)) for lid, _ in k.chain(m, ctx.ni, ns[i], ns[(i + 1) % len(ns)])]
                made.append(k.domain(m, edge, word, thick, mat))
        ctx.created["d"] += made
        return "%s %s" % (word, ranges(made, "d"))

    if word == "hole":
        did = handles(toks[:1], "d")
        if not did:
            raise NxError("hole d<N> P P P …")
        P = pts(ctx, toks[1:], kv)
        ns = [node_of(ctx, p) for p in P]
        edge = [lid for i in range(len(ns)) for lid, _ in k.chain(m, ctx.ni, ns[i], ns[(i + 1) % len(ns)])]
        k.check(m.Domains.Item[did[0]].AddHole(edge), "hole in d%d" % did[0])
        return "hole in d%d" % did[0]

    if word == "support":
        for key in ("x", "y", "z"):            # 'support z=0 fixed': the plane value is one number, the rest are words
            if key in kv:
                parts = kv[key].split()
                kv[key] = parts[0]
                toks += parts[1:]
        spec = kv.get("k")
        if not spec and toks and re.fullmatch(r"[a-z][a-z\-]*", toks[-1].lower()) and not re.fullmatch(r"[nl]\d+(-[nl]?\d+)?", toks[-1]):
            spec = toks.pop()
        spec = spec or "fixed"
        targets = toks
        out = []
        nodes = _select_nodes(ctx, targets, kv)
        for n in nodes:
            out.append("ns%d" % k.nodal_support(m, n, spec))
        for lid in handles([t for t in targets if t.startswith("l")], "l") or []:
            out.append("ls%d" % k.line_support(m, lid, spec))
        if not out:
            raise NxError("support: no node/line selected", "support n1 n4 fixed · support 0,0,0 6,0,0 pinned · support z=0 fixed · support l3 pinned")
        return "%s %s ×%d" % (spec, " ".join(out[:6]) + (" …" if len(out) > 6 else ""), len(out))

    if word == "release":
        lids = handles(toks, "l")
        if not lids:
            raise NxError("release l3 l4 start=hinge end=hinge (or both=hinge)")
        b = kv.get("both")
        for lid in lids:
            k.releases(m, lid, start=kv.get("start", b), end=kv.get("end", b))
        return "released %s" % ranges(lids, "l")

    if word == "case":
        if not toks:
            raise NxError("case <name> [self]")
        cid, new = k.load_case(m, toks[0])
        extra = ""
        if len(toks) > 1 and toks[1].lower() in ("self", "selfweight", "sw"):
            extra = ", self-weight on %d element(s)" % k.self_weight(m, cid)
        return "case %s #%d%s%s" % (toks[0], cid, "" if new else " (existing)", extra)

    if word == "load":
        if len(toks) < 2:
            raise NxError("load <case> <targets> fz=… | qz=… | pz=… | self")
        cid, _ = k.load_case(m, toks[0])
        targets = toks[1:]
        if targets == ["self"]:
            return "self-weight on %d element(s)" % k.self_weight(m, cid)
        v = lambda key: float(kv.get(key, 0) or 0)
        local = "local" in targets or kv.get("sys", "").startswith("l")
        targets = [t for t in targets if t not in ("local", "global")]
        n_l = handles([t for t in targets if t.startswith("l")], "l") or []
        n_d = handles([t for t in targets if t.startswith("d")], "d") or []
        n_n = _select_nodes(ctx, [t for t in targets if not t.startswith(("l", "d"))], {})
        cnt = 0
        for n in n_n:
            k.nodal_force(m, cid, n, (v("fx"), v("fy"), v("fz"), v("mx"), v("my"), v("mz")))
            cnt += 1
        for lid in n_l:
            k.beam_load(m, cid, lid, (v("qx"), v("qy"), v("qz")), local)
            cnt += 1
        for did in n_d:
            q = (v("px") or v("qx"), v("py") or v("qy"), v("pz") or v("qz"))
            k.area_load(m, cid, did, q, local, projected="projected" in toks)
            cnt += 1
        if not cnt:
            raise NxError("load: no target", "nodes nN / x,y,z · lines lN (qz=kN/m) · domains dN (pz=kN/m2)")
        return "%d load(s) in %s" % (cnt, toks[0])

    if word == "combo":
        mm = re.fullmatch(r"\s*(\S+)(?:\s+(\w+))?\s*=\s*(.+)", rest)
        if not mm:
            raise NxError("combo <name> [uls|sls|quasi|freq|other] = 1.35 G + 1.5 Q")
        name, kind, expr = mm.group(1), mm.group(2) or ("uls" if "uls" in mm.group(1).lower() else "sls" if "sls" in mm.group(1).lower() else "other"), mm.group(3)
        f, ids = [], []
        for term in re.split(r"\s*\+\s*", expr.strip()):
            tt = term.split()
            fac, cname = (float(tt[0]), " ".join(tt[1:])) if len(tt) > 1 else (1.0, tt[0])
            cid, _ = k.load_case(m, cname, create=False)
            f.append(fac)
            ids.append(cid)
        i = k.combination(m, name, f, ids, kind)
        return "combo %s #%d (%s)" % (name, i, kind)

    if word == "delete":
        ls_ = handles([t for t in toks if t.startswith("l")], "l") or []
        ds = handles([t for t in toks if t.startswith("d")], "d") or []
        ns = handles([t for t in toks if t.startswith("n")], "n") or []
        for did in sorted(ds, reverse=True):
            k.check(m.Domains.Delete(did), "delete d%d" % did)
        for lid in sorted(ls_, reverse=True):
            k.check(m.Lines.Delete(lid), "delete l%d" % lid)
        for n in sorted(ns, reverse=True):
            k.check(m.Nodes.Delete(n), "delete n%d" % n)
        ctx.nodes = None
        return "deleted %d item(s); AxisVM renumbered the rest" % (len(ls_) + len(ds) + len(ns))

    if word == "set":
        lids = handles([t for t in toks if t.startswith("l")], "l") or []
        if not lids:
            raise NxError("set l3 l4 sec=IPE 330 [mat=…] [type=beam|rib|truss]")
        snap = Snapshot(m, loads=False)
        for lid in lids:
            L = snap.lines[lid]
            kind = kv.get("type") or (L["type"] if L["type"] in ("beam", "rib", "truss") else "beam")
            mat = ctx.mat(kv["mat"]) if kv.get("mat") else L["mat"]
            sec = ctx.sec(kv["sec"]) if kv.get("sec") else L["sec"]
            k.define_line(m, lid, kind, mat, sec)
        return "set %s" % ranges(lids, "l")

    if word == "select":
        a = conn.ax()
        m.SelectAll(a.lbFalse)
        for pre, coll in (("l", m.Lines), ("d", m.Domains), ("n", m.Nodes)):
            for i in handles([t for t in toks if t.startswith(pre)], pre) or []:
                coll.Selected[i] = a.lbTrue
        m.Refresh()
        return "selected in AxisVM"

    if word == "intersect":
        lids = handles(toks, "l") or list(range(1, m.Lines.Count + 1))
        k.check(m.Lines.CrossLines(lids), "intersect lines")
        ctx.nodes = None
        return "intersected %d line(s)" % len(lids)

    raise NxError("unknown action '%s'" % word,
                  "units tol use mat sec beam column rib truss line plate slab shell wall membrane hole support release case load combo delete set select intersect")


def _post_line_opts(ctx, lids, kv):
    if kv.get("start") or kv.get("end"):
        for lid in lids:
            k.releases(ctx.m, lid, start=kv.get("start"), end=kv.get("end"))


def _select_nodes(ctx, toks, kv):
    """Node targets: nN handles, x,y,z points (existing or new node), 'z=0' / 'x=…' plane selectors, 'all'."""
    out = []
    for t in toks:
        if re.fullmatch(r"n\d+(-n?\d+)?", t):
            out += handles([t], "n")
        elif re.fullmatch(r"[xyz]=[-\d.]+", t):
            ax_, v = t.split("=")
            v = float(v) * ctx.unit
            snap = Snapshot(ctx.m, loads=False)
            j = "xyz".index(ax_)
            out += [i for i in range(1, len(snap.nodes)) if abs(snap.nodes[i][j] - v) <= ctx.tol]
        elif "," in t:
            out.append(node_of(ctx, pts(ctx, [t], {})[0]))
    for key in ("x", "y", "z"):
        if key in kv and re.fullmatch(r"[-\d.]+", kv[key]):
            snap = Snapshot(ctx.m, loads=False)
            j = "xyz".index(key)
            out += [i for i in range(1, len(snap.nodes)) if abs(snap.nodes[i][j] - float(kv[key]) * ctx.unit) <= ctx.tol]
    return list(dict.fromkeys(out))


# ------------------------------------------------------------------ import / export / mesh / analysis
def do_import(s, path, opt, r):
    path = os.path.abspath(path)
    if not os.path.exists(path):
        raise NxError("file not found: " + path)
    m = s.model
    a = conn.ax()
    ext = os.path.splitext(path)[1].lower()
    add = a.fimAdd if opt.get("mode", "add") == "add" else a.fimOverwrite
    if ext == ".json":
        if not s.host:
            raise NxError("the Rhino import runs inside the NextraAxisVM add-on; this AxisVM has none", "run Setup.bat, restart AxisVM")
        import json
        res = s.host.call("RhinoImport", path, json.dumps(opt))
        d = json.loads(res)
        if not d.get("ok"):
            raise NxError("Rhino import failed: %s" % d.get("error"))
        c = d["created"]
        r.line("Rhino import (%s): read %s → created %s" % (d["units"], d["read"], ", ".join("%s %d" % kv for kv in c.items() if kv[1])))
        if d.get("attribute_errors"):
            r.line("attribute problems: %d" % d["attribute_errors"])
        for n in d.get("notes", [])[:25]:
            r.line("  note: " + n)
        if len(d.get("notes", [])) > 25:
            r.line("  … %d more notes" % (len(d["notes"]) - 25))
        return
    if ext == ".dxf":
        p = a.RDXFimportParameters()
        p.CoordinateUnit = getattr(a, "lu_" + opt.get("unit", "m"))
        p.MaxDeviation = float(opt.get("max_deviation", 0.01))
        p.GeometryCheckTolerance = float(opt.get("tolerance", 0.001))
        p.CoordinateScaleFactor = float(opt.get("scale", 1.0))
        p.ImportAs = a.fiaBackgroundLayer if opt.get("as") == "background" else a.fiaActualNodes
        p.ImportMode = add
        p.BasePlane = {"xy": a.fipPlaneXY, "xz": a.fipPlaneXZ, "yz": a.fipPlaneYZ}.get(opt.get("plane", "xy"), a.fipPlaneXY)
        p.VisibleLayersOnly = a.lbFalse
        p.ImportHatch = a.lbFalse
        p.ActivateDXFonAllDrawings = a.lbFalse
        rc = m.ImportDXF(path, p)
    elif ext == ".ifc":
        p = a.RIFCimportParameters()
        p.ImportMode = add
        p.ImportMethod = a.iimArchitecturalModelObjects if opt.get("method") == "architectural" else a.iimStaticModel
        p.MaxDeviation = float(opt.get("max_deviation", 0.01))
        p.ByAngle = float(opt.get("by_angle", 10))
        p.JoinIfObjectsAreCloserThan = float(opt.get("join", 0.05))
        p.ImportAs = a.fiaBackgroundLayer if opt.get("as") == "background" else a.fiaActualNodes
        rc = m.ImportIFC(path, p)
    elif ext == ".axs":
        p = a.RAXSimportParameters()
        off = opt.get("place", [0, 0, 0])
        p.Place = k.rec("RPoint3d", x=off[0], y=off[1], z=off[2])
        p.CheckTolerance = float(opt.get("tolerance", 0.001))
        p.MergeLoadCases = a.lbTrue
        p.UserInteraction = a.lbFalse
        p.IgnoreDesignCode = a.lbTrue
        p.MergeLayers = a.lbTrue
        rc = m.ImportAXS(path, p)
    elif ext == ".pdf":
        p = a.RPDFimportParameters()
        p.PageNumber = int(opt.get("page", 1))
        p.MaxDeviation = float(opt.get("max_deviation", 0.01))
        p.GeometryCheckTolerance = float(opt.get("tolerance", 0.001))
        p.Scale = float(opt.get("scale", 1.0))
        p.ImportAs = a.fiaBackgroundLayer if opt.get("as", "background") == "background" else a.fiaActualNodes
        p.ImportMode = add
        p.BasePlane = a.fipPlaneXY
        rc = m.ImportPDF(path, p, opt.get("font", "Arial"))
    else:
        raise NxError("import supports .dxf .ifc .axs .pdf and Rhino AxisBridge .json", path)
    k.check(rc, "import of " + os.path.basename(path))
    r.line("imported %s" % path)


def export(s, path, r):
    path = os.path.abspath(path)
    a = conn.ax()
    m = s.model
    ext = os.path.splitext(path)[1].lower()
    if ext == ".dxf":
        rc = m.ExportToDXF(path, a.dxfR2000, a.lu_m, 1.0)
    elif ext == ".ifc":
        rc = m.ExportToIFC(path, a.ifc2x3, a.lbFalse, a.lbFalse, a.lbFalse, a.RIFCExportReinforcementParams())
    else:
        raise NxError("export supports .dxf and .ifc (save .axs with save:'path')")
    k.check(rc, "export to " + path)
    r.line("exported %s" % path)


def mesh(s, spec, r, size=None):
    """Mesh domains: spec 'all' | 'd1 d2' | number (size for all). Returns meshed ids."""
    a = conn.ax()
    m = s.model
    if isinstance(spec, (int, float)):
        size, spec = float(spec), "all"
    spec = str(spec or "all")
    mm = re.search(r"size=([\d.]+)", spec)
    if mm:
        size = float(mm.group(1))
    ids = handles([t for t in spec.split() if t.startswith("d")], "d") or list(range(1, m.Domains.Count + 1))
    done = []
    for did in ids:
        p = a.RDomainMeshParameters()
        p.MeshSize = float(size or default_mesh_size(s, did))
        p.MeshType = a.mtAdaptive
        p.MeshGeometryType = a.mgtMixedQuadTriangle
        p.QuadMeshQuality = 5
        res = m.Domains.Item[did].GenerateMesh(p)
        if k.code(res) is not None and k.code(res) > 0:
            done.append(did)
        else:
            bad = list(res[3]) if isinstance(res, tuple) and len(res) > 3 else []
            r.line("mesh d%d failed%s" % (did, ": check lines " + " ".join("l%d" % x for x in bad) +
                                         " (overlapping or unconnected; try ops 'intersect')" if bad else " (%s)" % (res,)))
    if done:
        r.line("meshed %s (size %s m)" % (ranges(done, "d"), num(size) if size else "auto"))
    return done


def default_mesh_size(s, did):
    from .core import cfg
    if cfg("mesh_size"):
        return float(cfg("mesh_size"))
    snap = STATE.get("snap_mesh") or Snapshot(s.model, loads=False)
    STATE["snap_mesh"] = snap
    area, *_ = snap.domain_info(did) if did < len(snap.domains) else (1.0,)
    return max(0.25, min(1.0, (area ** 0.5) / 8 if area else 0.5))


def analyze(s, kind, mesh_size, r):
    a = conn.ax()
    m = s.model
    kind = (kind or "linear").lower()
    STATE.pop("snap_mesh", None)
    unmeshed = [i for i in range(1, m.Domains.Count + 1) if not m.Domains.Item[i].MeshExists]
    if unmeshed:
        with undo.step(s, "Nextra mesh", r, quiet=True, report=False):
            mesh(s, " ".join("d%d" % i for i in unmeshed) + (" size=%s" % mesh_size if mesh_size else ""), r)
    calc = m.Calculation
    ui = a.cuiNoUserInteractionWithAutoCorrectNoShow
    if kind.startswith("lin"):
        rc = calc.LinearAnalysis(ui)
    elif kind.startswith("non"):
        raise NxError("nonlinear analysis needs parameters", "use run with model.Calculation.NonLinearAnalysis(params, %d); see query {scope:'api', filter:'RNonLinearAnalysis'}" % ui)
    elif kind.startswith("vib"):
        raise NxError("vibration analysis needs parameters", "run: model.Calculation.Vibration(...) — query {scope:'api', filter:'IAxisVMCalculation.Vibration'}")
    elif kind.startswith("buck"):
        raise NxError("buckling analysis needs parameters", "run: model.Calculation.Buckling(...) — query {scope:'api', filter:'IAxisVMCalculation.Buckling'}")
    else:
        raise NxError("analyze: linear (nonlinear/vibration/buckling through run)")
    code = k.code(rc)
    if code != a.lbTrue and code != 1:
        from . import win
        dlg = win.dialogs(s.pid) if s.pid else []
        raise NxError("linear analysis failed (%s)%s" % (conn.error_name(code) if isinstance(code, int) else code,
                                                      "; AxisVM shows: " + "; ".join(t for t, _ in dlg) if dlg else ""),
                      "check supports (mechanism?), meshes, and AxisVM's messages; query {scope:'status'}")
    r.line("linear analysis done. Results: query {scope:'results', case:'…'|combo:'…'} · picture: view {target:'axisvm'}")

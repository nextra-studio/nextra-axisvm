"""One bulk read of the model geometry and attributes (a few COM calls, independent of model size), shared by query,
view and the edit/run deltas. Ids are AxisVM's own 1-based numbers; handles: n<i> node, l<i> line, d<i> domain."""
import math

from .conn import ax

LINE_TYPES = {0: "truss", 1: "beam", 2: "rib", 3: "spring", 4: "gap", 5: "edge", 6: "hole", 7: "line", 8: "nnlink", 9: "lllink"}
SURF_TYPES = {0: "hole", 1: "membrane", 2: "membrane-strain", 3: "plate", 4: "shell"}


class Snapshot:
    def __init__(self, model, loads=True):
        self.model = model
        a = ax()
        m = model
        n = m.Nodes.Count
        self.nodes = [None]
        if n:
            for p in m.Nodes.BulkGetCoord(list(range(1, n + 1)))[0]:
                self.nodes.append((p.x, p.y, p.z))
        self.lines = [None]
        nl = m.Lines.Count
        if nl:
            ids = list(range(1, nl + 1))
            data = m.Lines.BulkGetLineData(ids)[0]
            attrs = m.Lines.BulkGetAttr_V161(ids)[0]
            try:
                members = m.Lines.BulkGetMemberIds(ids)[0]
            except Exception:
                members = [0] * nl
            for i, (d, t) in enumerate(zip(data, attrs)):
                typ = LINE_TYPES.get(t.LineType, str(t.LineType))
                elem = typ in ("beam", "rib", "truss")      # gap/spring/link records carry garbage material/section ids
                self.lines.append({"n1": d.NodeId1, "n2": d.NodeId2, "geom": d.GeomType, "type": typ,
                                   "mat": t.MaterialIndex if elem else 0, "sec": t.StartCrossSectionIndex if elem else 0,
                                   "sec2": t.EndCrossSectionIndex if elem else 0,
                                   "member": members[i] if i < len(members) else 0})
        self.domains = [None]
        nd = m.Domains.Count
        if nd:
            counts, lids, sattr, _ = m.Domains.BulkGetDomains(list(range(1, nd + 1)))
            k = 0
            for i in range(nd):
                ls = list(lids[k:k + counts[i]])
                k += counts[i]
                s = sattr[i]
                self.domains.append({"lines": ls, "type": SURF_TYPES.get(s.SurfaceType, str(s.SurfaceType)),
                                     "t": s.Thickness, "mat": s.MaterialId, "poly": self._chain(ls)})
        self.mats = self._names(m.Materials)
        self.secs = self._names(m.CrossSections)
        self.nsup = {}
        for i in range(1, m.NodalSupports.Count + 1):
            try:
                self.nsup.setdefault(m.NodalSupports.Item[i].NodeId, []).append(i)
            except Exception:
                pass
        self.lsup = {}
        for i in range(1, m.LineSupports.Count + 1):
            try:
                self.lsup.setdefault(m.LineSupports.LineId[i], []).append(i)
            except Exception:
                pass
        self.cases = [None] + [m.LoadCases.Name[i] for i in range(1, m.LoadCases.Count + 1)]
        self.combos = [None] + [m.LoadCombinations.Name[i] for i in range(1, m.LoadCombinations.Count + 1)]
        self.nloads = m.Loads.Count
        self.load_rows = None
        if loads and self.nloads <= 5000:
            L = m.Loads
            self.load_rows = [(L.LoadType[i], L.ElementId[i], L.LoadCaseId[i]) for i in range(1, self.nloads + 1)]

    @staticmethod
    def _names(coll):
        out = [None]
        for i in range(1, coll.Count + 1):
            try:
                out.append(coll.Item[i].Name)
            except Exception:
                out.append("?")
        return out

    def _chain(self, lids):
        """Ordered node loop of a domain contour (best effort; straight segments)."""
        edges = [(self.lines[l]["n1"], self.lines[l]["n2"]) for l in lids if l < len(self.lines) and self.lines[l]]
        if not edges:
            return []
        loop = [edges[0][0], edges[0][1]]
        rest = edges[1:]
        while rest:
            for j, (a, b) in enumerate(rest):
                if a == loop[-1]:
                    loop.append(b)
                elif b == loop[-1]:
                    loop.append(a)
                else:
                    continue
                rest.pop(j)
                break
            else:
                break
        if len(loop) > 1 and loop[0] == loop[-1]:
            loop.pop()
        return loop

    # ---------------------------------------------------------------- geometry helpers
    def line_pts(self, i):
        L = self.lines[i]
        return self.nodes[L["n1"]], self.nodes[L["n2"]]

    def line_info(self, i):
        p, q = self.line_pts(i)
        d = [q[k] - p[k] for k in range(3)]
        length = math.sqrt(sum(c * c for c in d))
        horiz = math.hypot(d[0], d[1])
        if self.lines[i]["geom"] != 0:            # arc etc.: the chord is not the length
            try:
                length = self.model.Lines.Item[i].Length
            except Exception:
                pass
            return length, "curved (chord %s)" % num(math.sqrt(sum(c * c for c in d))), tuple((p[k] + q[k]) / 2 for k in range(3))
        if length < 1e-9:
            orient = "zero-length"
        elif horiz < 1e-3 * length:
            orient = "vertical"
        elif abs(d[2]) < 1e-3 * length:
            orient = "horizontal az%d" % round(math.degrees(math.atan2(d[1], d[0])) % 180)
        else:
            orient = "inclined %d°" % round(math.degrees(math.atan2(abs(d[2]), horiz)))
        mid = tuple((p[k] + q[k]) / 2 for k in range(3))
        return length, orient, mid

    def domain_info(self, i):
        D = self.domains[i]
        pts = [self.nodes[n] for n in D["poly"] if n < len(self.nodes)]
        if len(pts) < 3:
            return 0.0, (0, 0, 0), (0, 0, 0), pts
        c = tuple(sum(p[k] for p in pts) / len(pts) for k in range(3))
        nx = ny = nz = 0.0
        for j in range(len(pts)):          # Newell normal (area vector)
            a, b = pts[j], pts[(j + 1) % len(pts)]
            nx += (a[1] - b[1]) * (a[2] + b[2])
            ny += (a[2] - b[2]) * (a[0] + b[0])
            nz += (a[0] - b[0]) * (a[1] + b[1])
        area = 0.5 * math.sqrt(nx * nx + ny * ny + nz * nz)
        nn = (nx, ny, nz)
        return area, c, nn, pts

    def bbox(self, ids=None):
        pts = [p for p in self.nodes[1:]] if ids is None else ids
        if not pts:
            return None
        return [min(p[k] for p in pts) for k in range(3)], [max(p[k] for p in pts) for k in range(3)]

    def signature(self):
        """Cheap content fingerprint for undo safety and deltas."""
        h = hash((tuple(self.nodes[1:]), tuple((L["n1"], L["n2"], L["type"], L["mat"], L["sec"]) for L in self.lines[1:]),
                  tuple((tuple(D["lines"]), D["type"], round(D["t"], 6), D["mat"]) for D in self.domains[1:]), self.nloads,
                  tuple(self.cases[1:]), tuple(self.combos[1:]), tuple(sorted((n, len(v)) for n, v in self.nsup.items())),
                  tuple(sorted((n, len(v)) for n, v in self.lsup.items())), tuple(self.mats[1:]), tuple(self.secs[1:])))
        return "%d/%d/%d/%d:%x" % (len(self.nodes) - 1, len(self.lines) - 1, len(self.domains) - 1, self.nloads, h & 0xFFFFFFFF)

    def counts(self):
        return {"nodes": len(self.nodes) - 1, "lines": len(self.lines) - 1, "domains": len(self.domains) - 1,
                "nodal supports": sum(len(v) for v in self.nsup.values()), "line supports": sum(len(v) for v in self.lsup.values()),
                "loads": self.nloads, "load cases": len(self.cases) - 1, "combinations": len(self.combos) - 1,
                "materials": len(self.mats) - 1, "sections": len(self.secs) - 1}


# ------------------------------------------------------------------ descriptions
from .core import num, xyz, trunc, ranges   # noqa: E402


def describe_line(s, i):
    L = s.lines[i]
    length, orient, mid = s.line_info(i)
    parts = ["l%d" % i, L["type"]]
    if L["type"] in ("beam", "rib", "truss"):
        sec = s.secs[L["sec"]] if 0 < L["sec"] < len(s.secs) else "?"
        if L["sec2"] and L["sec2"] != L["sec"] and L["sec2"] < len(s.secs):
            sec += ">" + s.secs[L["sec2"]]
        parts.append('"%s"' % sec)
        parts.append(s.mats[L["mat"]] if 0 < L["mat"] < len(s.mats) else "?")
    # end nodes, not the local x direction: after a split AxisVM can store them swapped (detail shows start/end)
    parts.append("n%d-n%d L=%s %s @%s" % (L["n1"], L["n2"], num(length), orient, xyz(mid, 2)))
    if L.get("member"):
        parts.append("[m%d]" % L["member"])
    if i in s.lsup:
        parts.append("support " + " ".join("ls%d" % k for k in s.lsup[i]))
    return " ".join(parts)


def describe_domain(s, i):
    D = s.domains[i]
    area, c, nn, pts = s.domain_info(i)
    a = max(area, 1e-12)
    try:
        area = s.model.Domains.Item[i].Area          # net of openings (the contour area above is gross)
    except Exception:
        pass
    n = tuple(v / (2 * a) for v in nn)
    if abs(n[2]) > 0.99:
        orient = "horizontal n%sz" % ("+" if n[2] > 0 else "-")
    elif abs(n[2]) < 0.01:
        orient = "vertical n(%s,%s,0)" % (num(n[0], 2), num(n[1], 2))
    else:
        orient = "inclined n%s" % xyz(n, 2)
    lo, hi = s.bbox(pts) if pts else ((0, 0, 0), (0, 0, 0))
    dims = "x".join(num(hi[k] - lo[k], 2) for k in range(3) if hi[k] - lo[k] > 1e-6)
    mat = s.mats[D["mat"]] if 0 < D["mat"] < len(s.mats) else "?"
    return "d%d %s t=%smm %s %s area %s %s @%s (%d edges)" % (i, D["type"], num(D["t"] * 1000, 1), mat, dims, num(area, 2),
                                                             orient, xyz(c, 2), len(D["lines"]))


def describe_node(s, i):
    t = "n%d %s" % (i, xyz(s.nodes[i]))
    if i in s.nsup:
        t += " support " + " ".join("ns%d" % k for k in s.nsup[i])
    return t


# ------------------------------------------------------------------ delta between two snapshots
def _r(p):
    return tuple(round(c, 4) for c in p)


def _line_keys(s):
    out = {}
    for i in range(1, len(s.lines)):
        L = s.lines[i]
        k = tuple(sorted((_r(s.nodes[L["n1"]]), _r(s.nodes[L["n2"]]))))
        out[k] = (i, (L["type"], s.mats[L["mat"]] if 0 < L["mat"] < len(s.mats) else "", s.secs[L["sec"]] if 0 < L["sec"] < len(s.secs) else ""))
    return out


def _dom_keys(s):
    out = {}
    for i in range(1, len(s.domains)):
        D = s.domains[i]
        k = frozenset(_r(s.nodes[n]) for n in D["poly"])
        out[k] = (i, (D["type"], round(D["t"], 6), D["mat"]))
    return out


def delta(b, a, cap=12):
    """Model changes from snapshot b to a: '+' added, '~' modified, '-' removed (matched by geometry)."""
    out = []
    bn = {_r(p) for p in b.nodes[1:]}
    an = {_r(p) for p in a.nodes[1:]}
    new_nodes = [i for i in range(1, len(a.nodes)) if _r(a.nodes[i]) not in bn]
    gone_nodes = len(bn - an)
    bl, al = _line_keys(b), _line_keys(a)
    added = [al[k][0] for k in al if k not in bl]
    removed = [k for k in bl if k not in al]
    modified = [al[k][0] for k in al if k in bl and al[k][1] != bl[k][1]]
    bd, ad = _dom_keys(b), _dom_keys(a)
    dadd = [ad[k][0] for k in ad if k not in bd]
    drem = [k for k in bd if k not in ad]
    dmod = [ad[k][0] for k in ad if k in bd and ad[k][1] != bd[k][1]]
    added = [i for i in added if a.lines[i]["type"] != "edge"]
    modified = [i for i in modified if a.lines[i]["type"] != "edge"]
    items = [("+", "l", i) for i in sorted(added)] + [("~", "l", i) for i in sorted(modified)] + \
            [("+", "d", i) for i in sorted(dadd)] + [("~", "d", i) for i in sorted(dmod)]
    if len(items) <= cap:
        for sign, kind, i in items:
            out.append("%s %s" % (sign, describe_line(a, i) if kind == "l" else describe_domain(a, i)))
    else:
        groups = {}
        for sign, kind, i in items:
            if kind == "l":
                L = a.lines[i]
                key = (sign, "l", L["type"], (a.secs[L["sec"]] if L["sec"] < len(a.secs) else "") or "")
            else:
                D = a.domains[i]
                key = (sign, "d", D["type"], "t=%smm" % num(D["t"] * 1000, 1))
            groups.setdefault(key, []).append(i)
        for (sign, kind, t, extra), ids in groups.items():
            out.append("%s %s %s%s ×%d" % (sign, ranges(ids, kind), t, " " + extra if extra else "", len(ids)))
    if removed:
        out.append("- %d line(s) removed" % len(removed))
    if drem:
        out.append("- %d domain(s) removed" % len(drem))
    if new_nodes:
        out.append("+ nodes %s" % trunc(ranges(new_nodes, "n"), 200))
    if gone_nodes:
        out.append("- %d node(s) removed" % gone_nodes)
    for label, x, y in (("nodal supports", sum(map(len, b.nsup.values())), sum(map(len, a.nsup.values()))),
                        ("line supports", sum(map(len, b.lsup.values())), sum(map(len, a.lsup.values()))),
                        ("loads", b.nloads, a.nloads)):
        if x != y:
            out.append("%s %s: %d → %d" % ("+" if y > x else "-", label, x, y))
    nc = [c for c in a.cases[1:] if c not in b.cases[1:]]
    if nc:
        out.append("+ load cases: " + ", ".join(nc))
    ncb = [c for c in a.combos[1:] if c not in b.combos[1:]]
    if ncb:
        out.append("+ combinations: " + ", ".join(ncb))
    for label, x, y in (("materials", b.mats, a.mats), ("sections", b.secs, a.secs)):
        new = [n for n in y[1:] if n not in x[1:]]
        if new:
            out.append("+ %s: %s" % (label, trunc(", ".join(map(str, new)), 200)))
    renum = (removed or drem or gone_nodes) and (len(a.lines) > 1)
    if renum:
        out.append("note: AxisVM renumbers after deletes; re-query handles before reusing old ones")
    return out

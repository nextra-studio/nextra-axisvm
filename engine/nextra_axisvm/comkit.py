"""Verified building blocks on top of the raw AxisVM COM API (units: m, kN, kNm; ids are 1-based AxisVM numbers).

Used by the `edit` shorthand and available in `run` as `kit`. Every function raises NxError with the AxisVM error
name when AxisVM rejects something, so callers never continue with an id <= 0.
"""
import math
import re

from .conn import ax, error_name
from .core import NxError

RIGID = 1e10          # kN/m or kNm/rad: AxisVM's usual "rigid" support stiffness


def code(r):
    return r[-1] if isinstance(r, (tuple, list)) else r


def check(r, what):
    c = code(r)
    if c is None or (isinstance(c, (int, float)) and c <= 0):
        raise NxError("AxisVM rejected %s (%s)" % (what, error_name(c) if isinstance(c, int) else c))
    return c


def rec(name, **fields):
    r = getattr(ax(), name)()
    for k, v in fields.items():
        setattr(r, k, v)
    return r


# ------------------------------------------------------------------ nodes / lines
class NodeIndex:
    """Coordinate lookup so the same point always becomes the same AxisVM node (tolerance in m)."""

    def __init__(self, model, tol=1e-3):
        self.model, self.tol, self.grid, self.coord = model, tol, {}, {}
        n = model.Nodes.Count
        if n:
            coords = model.Nodes.BulkGetCoord(list(range(1, n + 1)))[0]
            for i, p in enumerate(coords, 1):
                self._put(i, (p.x, p.y, p.z))
        self.created = []

    def _key(self, p):
        return tuple(int(math.floor(c / self.tol)) for c in p)

    def _put(self, i, p):
        self.grid.setdefault(self._key(p), []).append((i, p))
        self.coord[i] = p

    def on_segment(self, a, b):
        """Existing nodes strictly between nodes a and b on the straight segment, ordered from a to b."""
        p, q = self.coord.get(a), self.coord.get(b)
        if p is None or q is None:
            return []
        d = [q[k] - p[k] for k in range(3)]
        L2 = sum(c * c for c in d)
        if L2 <= 0:
            return []
        out = []
        for i, r in self.coord.items():
            if i in (a, b):
                continue
            t = sum((r[k] - p[k]) * d[k] for k in range(3)) / L2
            if t <= 1e-9 or t >= 1 - 1e-9:
                continue
            if max(abs(p[k] + t * d[k] - r[k]) for k in range(3)) <= self.tol:
                out.append((t, i))
        return [i for _, i in sorted(out)]

    def find(self, p):
        k = self._key(p)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for i, q in self.grid.get((k[0] + dx, k[1] + dy, k[2] + dz), ()):
                        if max(abs(a - b) for a, b in zip(p, q)) <= self.tol:
                            return i
        return 0

    def get(self, p):
        p = tuple(float(c) for c in p)
        i = self.find(p)
        if i:
            return i
        i = check(self.model.Nodes.Add(*p), "node %s" % (p,))
        self._put(i, p)
        self.created.append(i)
        return i


def chain(model, ni, n1, n2, split=True):
    """Lines from n1 to n2, split at every existing node lying on the segment (so members connect and slab edges
    reuse beam lines instead of overlapping them). Returns [(line id, created?)]."""
    seq = [n1] + (ni.on_segment(n1, n2) if split else []) + [n2]
    return [line_between(model, a, b) for a, b in zip(seq, seq[1:])]


def line_between(model, n1, n2):
    """Existing straight line n1-n2 (either direction) or a new one."""
    try:
        for lid in model.Nodes.GetConnectedLines(n1)[0] or ():
            ln = model.Lines.Item[lid]
            if {ln.StartNode, ln.EndNode} == {n1, n2}:
                return lid, False
    except Exception:
        pass
    a = ax()
    lid = check(model.Lines.Add(n1, n2, a.lgtStraightLine, a.RLineGeomData()), "line n%d-n%d" % (n1, n2))
    if isinstance(lid, tuple):
        lid = lid[-1]
    return lid, True


# ------------------------------------------------------------------ materials / sections
def _names(coll):
    out = {}
    for i in range(1, coll.Count + 1):
        try:
            out[coll.Item[i].Name] = i
        except Exception:
            pass
    return out


def _compact(s):
    return re.sub(r"[\s_\-]", "", s).lower()


def material(model, name):
    """Existing material by name, else from the AxisVM catalog (model's design code first, then Eurocode)."""
    want = _compact(name)
    for n, i in _names(model.Materials).items():
        if _compact(n) == want:
            return i
    a = ax()
    codes = []
    try:
        codes.append(model.Settings.NationalDesignCode)
    except Exception:
        pass
    codes.append(a.ndcEuroCode)
    variants = [name, re.sub(r"^([A-Za-z]+)\s*(\d)", r"\1 \2", name), name.replace(" ", "")]
    for c in codes:
        for v in dict.fromkeys(variants):
            try:
                r = model.Materials.AddFromCatalog(c, v)
            except Exception:
                r = 0
            if code(r) and code(r) > 0:
                return code(r)
    raise NxError("material '%s' not in the AxisVM catalog" % name,
                  "search it: query {scope:'catalog', filter:'material %s'}" % name.split()[0])


SHAPES = ("csseI", "csseU", "csseL", "csseT", "cssePipe", "csseBox", "csseRectangleHollow", "csseCircleHollow", "csseC", "csseZ")
PARAM = re.compile(r"^(rect|rhs|shs|pipe|chs|circle|round)\s+([\d.]+)(?:\s*[x*/ ]\s*([\d.]+))?(?:\s*[x*/ ]\s*([\d.]+))?(?:\s*[x*/ ]\s*([\d.]+))?$", re.I)


def section(model, spec, unit=0.001):
    """Existing section by name; parametric 'rect 300x500' / 'rhs 200x100x8' / 'pipe 168.3x8' / 'circle 400'
    (dimensions in mm unless unit says otherwise); else a catalog profile ('IPE 300', 'HEB200', 'SHS 100x100x5')."""
    spec = spec.strip()
    existing = _names(model.CrossSections)
    want = _compact(spec)
    for n, i in existing.items():
        if _compact(n) == want:
            return i
    a = ax()
    cs = model.CrossSections
    m = PARAM.match(spec)
    if m:
        kind = m.group(1).lower()
        d = [float(x) * unit for x in m.groups()[1:] if x]
        try:
            if kind == "rect" and len(d) == 2:
                return check(cs.AddRectangular(spec, d[0], d[1], a.cspOther), "section " + spec)
            if kind in ("rhs", "shs") and len(d) >= 2:
                b, h, t = (d + [d[-1]])[:3] if kind == "rhs" else (d[0], d[0], d[1])
                return check(cs.AddRectangularHollow(spec, b, h, t, t), "section " + spec)
            if kind in ("pipe", "chs") and len(d) == 2:
                return check(cs.AddPipe(spec, d[0], d[1], a.cspOther), "section " + spec)
            if kind in ("circle", "round") and len(d) == 1:
                return check(cs.AddCircle(spec, d[0]), "section " + spec)
        except NxError:
            raise
        except Exception as e:
            raise NxError("section '%s' failed: %s" % (spec, e))
        raise NxError("parametric section '%s' not understood" % spec, "rect BxH · rhs BxHxT · shs BxT · pipe DxT · circle D (mm)")
    base = re.sub(r"\s+", " ", spec)
    variants = [base, re.sub(r"^([A-Za-z]+)\s*(\d)", r"\1 \2", base), base.replace(" ", ""), base.upper()]
    for v in dict.fromkeys(variants):
        for sh in SHAPES:
            try:
                r = cs.AddFromCatalog_V161(getattr(a, sh), v)
            except Exception:
                r = 0
            if code(r) and code(r) > 0:
                return code(r)
    raise NxError("cross-section '%s' not found in the AxisVM catalog" % spec,
                  "search: query {scope:'catalog', filter:'%s'} · or parametric 'rect 300x500'" % spec.split()[0])


# ------------------------------------------------------------------ elements
def define_line(model, lid, kind, mat, sec, sec_end=None):
    a = ax()
    ln = model.Lines.Item[lid]
    sec_end = sec_end or sec
    if kind == "truss":
        r = ln.DefineAsTruss(mat, sec, a.lnlTensionAndCompression, 0.0)
    elif kind == "rib":
        r = ln.DefineAsRib(mat, sec, sec_end, a.RPoint3d(), a.RPoint3d())
    else:
        r = ln.DefineAsBeam(mat, sec, sec_end, a.RPoint3d(), a.RPoint3d())
    return check(r, "%s on l%d" % (kind, lid))


SURF = {"plate": "stPlate", "slab": "stPlate", "shell": "stShell", "wall": "stShell",
        "membrane": "stMembraneStress", "membrane_strain": "stMembraneStrain"}


def domain(model, line_ids, kind, thickness, mat):
    a = ax()
    attr = a.RSurfaceAttr()
    attr.SurfaceType = getattr(a, SURF.get(kind, "stShell"))
    attr.Thickness = float(thickness)
    attr.MaterialId = mat
    return check(model.Domains.Add(list(line_ids), attr), "%s domain" % kind)


def stiffness(spec):
    """'fixed' | 'pinned' | 'roller' (z only) | 'x,y,z' axes subset like 'xyz' / 'z' | six numbers 'kx,ky,kz,kxx,kyy,kzz'."""
    s = spec.strip().lower()
    if s in ("fixed", "fix", "clamped", "rigid"):
        k = [RIGID] * 6
    elif s in ("pinned", "pin", "hinged"):
        k = [RIGID] * 3 + [0, 0, 0]
    elif s in ("roller", "rollerz", "roller-z"):
        k = [0, 0, RIGID, 0, 0, 0]
    elif re.fullmatch(r"[xyz]+(r[xyz]+)?", s):
        t, _, r = s.partition("r")
        k = [RIGID if c in t else 0 for c in "xyz"] + [RIGID if c in r else 0 for c in "xyz"]
    else:
        try:
            k = [float(v) for v in re.split(r"[,\s]+", s) if v]
        except ValueError:
            k = []
        if len(k) != 6:
            raise NxError("support '%s' not understood" % spec, "fixed | pinned | roller | xyz | xyzrz | k=kx,ky,kz,kxx,kyy,kzz")
    st = ax().RStiffnesses()
    for f, v in zip(("x", "y", "z", "xx", "yy", "zz"), k):
        setattr(st, f, v)
    return st


def nodal_support(model, node, spec):
    a = ax()
    return check(model.NodalSupports.AddNodalGlobal(stiffness(spec), a.RNonLinearity(), a.RResistances(), node),
                 "support at n%d" % node)


def line_support(model, lid, spec):
    a = ax()
    return check(model.LineSupports.AddEdgeGlobal(stiffness(spec), a.RNonLinearity(), a.RResistances(), lid, 0, 0, 0, 0),
                 "line support on l%d" % lid)


def releases(model, lid, start=None, end=None):
    """start/end: 'hinge' (all rotations free except torsion) | 'pin' (same) | 'free:yy,zz' | 'rigid'."""
    a = ax()
    ln = model.Lines.Item[lid]
    for which, spec in (("Start", start), ("End", end)):
        if not spec:
            continue
        cur = getattr(ln, "Get%sReleases" % which)()[0]
        s = spec.lower()
        free = {"hinge": ("yy", "zz"), "pin": ("yy", "zz"), "pinned": ("yy", "zz"), "rigid": ()}.get(s)
        if free is None:
            free = tuple(x.strip() for x in s.split(":", 1)[-1].split(",") if x.strip())
        for dof in ("x", "y", "z", "xx", "yy", "zz"):
            r = getattr(cur, dof)
            r.ReleaseType = a.rtHinged if dof in free else a.rtRigid
            setattr(cur, dof, r)
        check(getattr(ln, "Set%sReleases" % which)(cur), "%s release on l%d" % (which.lower(), lid))


# ------------------------------------------------------------------ loads
def load_case(model, name, create=True):
    lc = model.LoadCases
    for i in range(1, lc.Count + 1):
        if lc.Name[i] == name:
            return i, False
    if not create:
        raise NxError("load case '%s' does not exist" % name)
    return check(lc.Add(name, ax().lctStandard), "load case " + name), True


def nodal_force(model, case, node, F):
    r = rec("RLoadNodalForce", LoadCaseId=case, NodeId=node, Fx=F[0], Fy=F[1], Fz=F[2], Mx=F[3], My=F[4], Mz=F[5])
    return check(model.Loads.AddNodalForce(r), "nodal load on n%d" % node)


def beam_load(model, case, lid, q, local=False):
    """Uniform distributed load on a beam/rib [kN/m] over the whole length; q = (qx, qy, qz)."""
    a = ax()
    rib = model.Lines.Item[lid].LineType == a.ltRib
    vals = dict(LoadCaseId=case, LineId=lid, qx1=q[0], qy1=q[1], qz1=q[2], qx2=q[0], qy2=q[1], qz2=q[2],
                SystemGLR=a.sysLocal if local else a.sysGlobal, Position1=0.0, Position2=1.0,
                DistributionType=a.brdtLength, Trapezoid=a.lbFalse)
    r = getattr(a, "RLoadRibDistributed" if rib else "RLoadBeamDistributed")()
    names = {f[0] for f in r._fields_}
    for f, v in vals.items():
        if f in names:
            setattr(r, f, v)
    fn = model.Loads.AddRibDistributed if rib else model.Loads.AddBeamDistributed
    return check(fn(r), "line load on l%d" % lid)


def area_load(model, case, did, q, local=False, projected=False):
    a = ax()
    r = rec("RLoadDomainConstant", LoadCaseId=case, DomainId=did, qx=q[0], qy=q[1], qz=q[2],
            SystemGLR=a.sysLocal if local else a.sysGlobal,
            DistributionType=a.sddtProjected if projected else a.sddtSurface)
    return check(model.Loads.AddDomainConstant(r), "area load on d%d" % did)


def self_weight(model, case, lines=None, domains=None):
    """Self-weight of the given (default: all) beams/ribs/trusses and domains."""
    a = ax()
    n = 0
    lines = range(1, model.Lines.Count + 1) if lines is None else lines
    domains = range(1, model.Domains.Count + 1) if domains is None else domains
    for lid in lines:
        t = model.Lines.Item[lid].LineType
        fn = {a.ltBeam: model.Loads.AddBeamSelfWeight, a.ltRib: model.Loads.AddRibSelfWeight,
              a.ltTruss: model.Loads.AddTrussSelfWeight}.get(t)
        if fn and code(fn(lid, case)) > 0:
            n += 1
    for did in domains:
        if code(model.Loads.AddDomainSelfWeight(did, case)) > 0:
            n += 1
    return n


COMBO = {"uls": "ctULS1", "sls": "ctSLS1", "sls1": "ctSLS1", "char": "ctSLS1", "sls2": "ctSLS2", "freq": "ctSLS2",
         "sls3": "ctSLS3", "quasi": "ctSLS3", "seismic": "ctULS2", "acc": "ctULS3", "other": "ctOther"}


def combination(model, name, factors, case_ids, kind="other"):
    a = ax()
    t = getattr(a, COMBO.get(kind.lower(), "ctOther"))
    return check(model.LoadCombinations.Add(name, t, [float(f) for f in factors], [int(c) for c in case_ids]),
                 "combination " + name)

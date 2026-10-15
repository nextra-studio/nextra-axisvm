"""query: text answers, cheapest first.

scope model (default)  level summary → list → detail; filter 'l3 d1 n5' 'type:beam' 'section:IPE*' 'material:S*' 'vertical'
                       'horizontal' 'sel' 'bbox:x0,y0,z0,x1,y1,z1' 'nodes' 'lines' 'domains' 'supports'
scope loads            load cases (with load counts by type), combinations with factors; filter 'case:G' lists its loads
scope results          case:'G' | combo:'ULS' (name or number); kind summary|displacements|reactions|forces|surface; filter handles
scope catalog          materials / cross-sections in the AxisVM catalog: 'IPE' 'HEB 2*' 'material C30*' 'tables'
scope api | docs | library | status | instances
"""
import re

from . import conn, memory
from .core import STATE, NxError, num, xyz, like, trunc, ranges
from .modeldata import Snapshot, describe_line, describe_domain, describe_node

LOAD_TYPES = None


def run(a, r):
    scope = (a.str("scope", "model") or "model").lower()
    if scope in ("model", "axisvm", "rhino"):
        model_query(a, r)
    elif scope == "loads":
        loads_query(a, r)
    elif scope == "results":
        results_query(a, r)
    elif scope == "catalog":
        catalog_query(a, r)
    elif scope == "api":
        from . import apidocs
        f = a.str("filter") or a.str("name")
        if not f:
            raise NxError("api needs filter", "free words 'line load' · 'IAxisVMLoads.AddBeamDistributed' · 'RSurfaceAttr' · 'ELineType'")
        r.line(apidocs.search(f, a.int("limit", 25)))
    elif scope == "docs":
        memory.docs(a.str("filter") or a.str("topic"), r)
    elif scope == "library":
        name = a.str("name")
        if name:
            p = memory.lib_find(name)
            r.line(p)
            r.line(open(p, encoding="utf-8").read())
        else:
            r.line("library dirs: " + "; ".join(memory.lib_dirs()))
            r.line(memory.lib_index(a.str("filter"), a.int("limit", 60)))
            r.line("run one: run {lib:'name', args:{…}} · read: query {scope:'library', name}")
    elif scope == "status":
        from .core import status
        text, imgs = status({"answer": a.str("answer")})
        r.line(text)
        r.images += imgs
    elif scope == "instances":
        cs = conn.instances()
        r.line(conn.describe(cs) if cs else "no AxisVM with the NextraAxisVM add-on is running. " + conn.not_found_message())
        b = STATE.get("bound")
        r.line("bound: %s" % (b if b else "not yet (binds automatically when exactly one instance is open)"))
    else:
        raise NxError("scope '%s' unknown" % scope, "model | loads | results | catalog | api | docs | library | status | instances")


# ------------------------------------------------------------------ model
def model_query(a, r):
    s_ = conn.get()
    m = s_.model
    level = (a.str("level") or ("list" if a.has("filter") else "summary")).lower()
    filt = a.str("filter", "") or ""
    snap = Snapshot(m, loads=(level == "summary"))
    STATE["snap"] = snap
    if level == "summary":
        summary(s_, snap, r)
        return
    nodes, lines, doms = select(snap, filt, m)
    limit, offset = a.int("limit", 60), a.int("offset", 0)
    rows = [("n", i) for i in nodes] + [("l", i) for i in lines] + [("d", i) for i in doms]
    total = len(rows)
    if total == 0:
        r.line("nothing matches '%s'. Try query {} (summary) or filter 'type:beam' 'l3' 'section:IPE*'." % filt)
        return
    if level == "list" and total > limit and not any(t in filt for t in ("n", "l", "d")) and offset == 0 and total > 3 * limit:
        aggregate(snap, nodes, lines, doms, r)
        r.line("(%d items aggregated; narrow the filter or page with limit/offset)" % total)
        return
    for kind, i in rows[offset:offset + limit]:
        if level == "detail":
            detail(m, snap, kind, i, r)
        else:
            r.line(describe_node(snap, i) if kind == "n" else describe_line(snap, i) if kind == "l" else describe_domain(snap, i))
    if total > offset + limit:
        r.line("… %d more (offset:%d)" % (total - offset - limit, offset + limit))


def summary(s_, snap, r):
    m = s_.model
    c = snap.counts()
    try:
        modified = bool(m.Modified)
    except Exception:
        modified = False
    r.line("AxisVM pid %s · file '%s'%s · units m, kN" % (s_.pid, m.FileName or "untitled", " (unsaved changes)" if modified else ""))
    types = {}
    for L in snap.lines[1:]:
        types[L["type"]] = types.get(L["type"], 0) + 1
    dtypes = {}
    for D in snap.domains[1:]:
        dtypes[D["type"]] = dtypes.get(D["type"], 0) + 1
    if types.get("edge"):
        types["edge (mesh, hidden in lists)"] = types.pop("edge")
    r.line("nodes %d · lines %d (%s) · domains %d (%s)" % (c["nodes"], c["lines"], ", ".join("%s %d" % kv for kv in sorted(types.items())) or "-",
                                                           c["domains"], ", ".join("%s %d" % kv for kv in sorted(dtypes.items())) or "-"))
    r.line("supports: nodal %d, line %d · loads %d in %d case(s) · combinations %d" % (
        c["nodal supports"], c["line supports"], c["loads"], c["load cases"], c["combinations"]))
    if snap.mats[1:]:
        r.line("materials: " + ", ".join("%d %s" % (i, n) for i, n in enumerate(snap.mats) if n))
    if snap.secs[1:]:
        r.line("sections: " + trunc(", ".join("%d %s" % (i, n) for i, n in enumerate(snap.secs) if n), 400))
    bb = snap.bbox()
    if bb:
        r.line("extents x %s..%s y %s..%s z %s..%s m" % (num(bb[0][0]), num(bb[1][0]), num(bb[0][1]), num(bb[1][1]), num(bb[0][2]), num(bb[1][2])))
    if snap.cases[1:]:
        r.line("load cases: " + trunc(", ".join("%d %s" % (i, n) for i, n in enumerate(snap.cases) if n), 300))
    if snap.combos[1:]:
        r.line("combinations: " + trunc(", ".join("%d %s" % (i, n) for i, n in enumerate(snap.combos) if n), 300))
    state = results_state(m)
    r.line("results: " + state)
    r.line("next: query {filter:'type:beam'} (list) → level:'detail' · view {} for a picture · query {scope:'results', case:'…'}")


def results_state(m):
    a = conn.ax()
    try:
        n = m.Results.ResultCaseCount if hasattr(m.Results, "ResultCaseCount") else None
    except Exception:
        n = None
    valid = []
    try:
        for i in range(1, m.LoadCases.Count + 1):
            v = m.Results.GetResultsValid(a.atLinearStatic, i)
            if (v[0] if isinstance(v, tuple) else v) == a.lbTrue:
                valid.append(i)
    except Exception:
        pass
    if valid:
        return "linear static results valid for case(s) %s" % ranges(valid)
    return "none (run edit {analyze:'linear'})"


def select(snap, filt, model=None):
    """Filter tokens AND together. Returns (nodes, lines, domains) id lists."""
    toks = filt.split()
    ids = {"n": [], "l": [], "d": []}
    rest = []
    for t in toks:
        m = re.fullmatch(r"([nld])(\d+)(?:-[nld]?(\d+))?", t)
        if m:
            k, a, b = m.group(1), int(m.group(2)), int(m.group(3) or m.group(2))
            ids[k] += list(range(a, b + 1))
        else:
            rest.append(t.lower())
    explicit = any(ids.values())
    N = ids["n"] if explicit else list(range(1, len(snap.nodes)))
    L = ids["l"] if explicit else list(range(1, len(snap.lines)))
    D = ids["d"] if explicit else list(range(1, len(snap.domains)))
    N = [i for i in N if 0 < i < len(snap.nodes)]
    L = [i for i in L if 0 < i < len(snap.lines)]
    D = [i for i in D if 0 < i < len(snap.domains)]
    want = set()
    for t in rest:
        if t in ("nodes", "lines", "domains", "supports"):
            want.add(t)
            continue
        if t.startswith("type:"):
            v = t[5:]
            L = [i for i in L if like(snap.lines[i]["type"], v) or (v == "column" and snap.line_info(i)[1] == "vertical")]
            D = [i for i in D if like(snap.domains[i]["type"], v) or v in ("slab", "wall") and _dom_kind(snap, i) == v]
            if not want:
                want.add("lines" if L and not D else "domains" if D and not L else "both")
        elif t.startswith(("section:", "sec:")):
            v = t.split(":", 1)[1]
            L = [i for i in L if 0 < snap.lines[i]["sec"] < len(snap.secs) and like(snap.secs[snap.lines[i]["sec"]], v)]
            D, N = [], []
        elif t.startswith(("material:", "mat:")):
            v = t.split(":", 1)[1]
            L = [i for i in L if 0 < snap.lines[i]["mat"] < len(snap.mats) and like(snap.mats[snap.lines[i]["mat"]], v)]
            D = [i for i in D if 0 < snap.domains[i]["mat"] < len(snap.mats) and like(snap.mats[snap.domains[i]["mat"]], v)]
            N = []
        elif t in ("vertical", "horizontal", "inclined"):
            L = [i for i in L if snap.line_info(i)[1].startswith(t)]
            D = [i for i in D if _dom_kind(snap, i) == {"vertical": "wall", "horizontal": "slab"}.get(t, "inclined")]
            N = []
        elif t.startswith("bbox:"):
            v = [float(x) for x in t[5:].split(",")]
            lo, hi = v[:3], v[3:]
            inside = lambda p: all(lo[k] - 1e-9 <= p[k] <= hi[k] + 1e-9 for k in range(3))
            N = [i for i in N if inside(snap.nodes[i])]
            L = [i for i in L if all(inside(p) for p in snap.line_pts(i))]
            D = [i for i in D if all(inside(snap.nodes[n]) for n in snap.domains[i]["poly"])]
        elif t == "sel" and model is not None:
            N = _sel(model.Nodes, N)
            L = _sel(model.Lines, L)
            D = _sel(model.Domains, D)
        elif t.startswith("member:"):
            v = int(t.split(":")[1].lstrip("m"))
            L = [i for i in L if snap.lines[i].get("member") == v]
            N, D = [], []
        else:
            raise NxError("filter token '%s' unknown" % t,
                          "handles 'l3 d1 n5 l4-l9' · type:beam|rib|truss|plate|shell|column|slab|wall · section:IPE* · material:S* · vertical · horizontal · sel · bbox:x0,y0,z0,x1,y1,z1 · member:m5 · nodes|lines|domains|supports")
    if not explicit and not any(t.startswith("type:") for t in rest):
        L = [i for i in L if snap.lines[i]["type"] != "edge"]     # finite-element surface edges after meshing
    if "supports" in want:
        N = [i for i in N if i in snap.nsup]
        L = [i for i in L if i in snap.lsup]
        D = []
    elif want:
        if "nodes" not in want:
            N = [] if not explicit or not ids["n"] else N
        if "lines" not in want and "both" not in want:
            L = [] if not explicit or not ids["l"] else L
        if "domains" not in want and "both" not in want:
            D = [] if not explicit or not ids["d"] else D
    elif not explicit:
        N = []     # nodes only on request: lines/domains carry their node numbers
    return N, L, D


def _sel(coll, cand):
    try:
        got = coll.GetSelectedItemIds()
        got = set(got[0] if isinstance(got, tuple) else got or ())
    except Exception:
        got = set()
    return [i for i in cand if i in got]


def _dom_kind(snap, i):
    area, c, nn, pts = snap.domain_info(i)
    if area <= 0:
        return "?"
    nz = abs(nn[2]) / (2 * area)
    return "slab" if nz > 0.99 else "wall" if nz < 0.01 else "inclined"


def aggregate(snap, nodes, lines, doms, r):
    g = {}
    for i in lines:
        L = snap.lines[i]
        key = ("l", L["type"], snap.secs[L["sec"]] if 0 < L["sec"] < len(snap.secs) else "", snap.line_info(i)[1].split(" az")[0])
        g.setdefault(key, []).append(i)
    for i in doms:
        D = snap.domains[i]
        key = ("d", D["type"], "t=%smm" % num(D["t"] * 1000, 1), _dom_kind(snap, i))
        g.setdefault(key, []).append(i)
    for (k, t, extra, orient), ids in sorted(g.items(), key=lambda kv: -len(kv[1])):
        r.line("%s ×%d %s %s %s" % (trunc(ranges(ids, k), 80), len(ids), t, extra, orient))
    if nodes:
        r.line("nodes ×%d %s" % (len(nodes), trunc(ranges(nodes, "n"), 80)))


def detail(m, snap, kind, i, r):
    a = conn.ax()
    if kind == "n":
        r.line(describe_node(snap, i))
        try:
            ls = m.Nodes.GetConnectedLines(i)
            r.line("  connected lines: " + " ".join("l%d" % x for x in (ls[0] or ())))
        except Exception:
            pass
        return
    if kind == "l":
        r.line(describe_line(snap, i))
        ln = m.Lines.Item[i]
        try:
            for which in ("Start", "End"):
                rel = getattr(ln, "Get%sReleases" % which)()[0]
                free = [d for d in ("x", "y", "z", "xx", "yy", "zz") if getattr(rel, d).ReleaseType != a.rtRigid]
                r.line("  %s release: %s" % (which.lower(), ",".join(free) if free else "rigid"))
        except Exception:
            pass
        _loads_on(snap, ("beam", "rib", "truss"), i, r)
        return
    D = snap.domains[kind == "d" and i]
    r.line(describe_domain(snap, i))
    r.line("  contour lines: %s · nodes: %s" % (" ".join("l%d" % x for x in D["lines"]), " ".join("n%d" % x for x in D["poly"])))
    try:
        dm = m.Domains.Item[i]
        if dm.HoleCount:
            r.line("  holes: %d" % dm.HoleCount)
    except Exception:
        pass
    _loads_on(snap, ("domain",), i, r)


def _load_type_names():
    global LOAD_TYPES
    if LOAD_TYPES is None:
        from . import apidocs
        LOAD_TYPES = {v: n[2:] for n, v in dict(apidocs.index()["enums"]).get("ELoadType", [])}
    return LOAD_TYPES


def _loads_on(snap, prefixes, i, r):
    if snap.load_rows is None:
        snap.load_rows = [(snap.model.Loads.LoadType[k], snap.model.Loads.ElementId[k], snap.model.Loads.LoadCaseId[k])
                          for k in range(1, snap.model.Loads.Count + 1)]
    names = _load_type_names()
    hits = []
    for k, (t, el, lc) in enumerate(snap.load_rows, 1):
        nm = names.get(t, str(t))
        if el == i and any(nm.lower().startswith(p) for p in prefixes):
            hits.append("%s[%s]" % (nm, snap.cases[lc] if lc < len(snap.cases) else lc))
    if hits:
        r.line("  loads: " + ", ".join(hits))


# ------------------------------------------------------------------ loads
def loads_query(a, r):
    m = conn.get().model
    snap = Snapshot(m, loads=True)
    names = _load_type_names()
    filt = a.str("filter", "") or ""
    by = {}
    for k, (t, el, lc) in enumerate(snap.load_rows or [], 1):
        by.setdefault(lc, []).append((k, names.get(t, str(t)), el))
    want = None
    mm = re.search(r"case:(\S+)", filt)
    if mm:
        want = _case_id(snap.cases, mm.group(1))
    for i in range(1, len(snap.cases)):
        if want and i != want:
            continue
        items = by.get(i, [])
        cnt = {}
        for _, t, _ in items:
            cnt[t] = cnt.get(t, 0) + 1
        r.line("case %d '%s': %d load(s)%s" % (i, snap.cases[i], len(items), (" — " + ", ".join("%s %d" % kv for kv in cnt.items())) if cnt else ""))
        if want:
            for k, t, el in items[: a.int("limit", 80)]:
                pre = "n" if t.startswith("Nodal") else "d" if t.startswith("Domain") else "l" if t.startswith(("Beam", "Rib", "Truss")) else "#"
                r.line("  load %d %s on %s%d" % (k, t, pre, el))
    for i in range(1, len(snap.combos)):
        try:
            f, ids, _ = m.LoadCombinations.GetCombination(i)
            terms = " + ".join("%s %s" % (num(x), snap.cases[c] if c < len(snap.cases) else c) for x, c in zip(f, ids) if x)
        except Exception:
            terms = "?"
        r.line("combo %d '%s' = %s" % (i, snap.combos[i], terms))
    if snap.load_rows is None:
        r.line("(%d loads: too many to list per case)" % snap.nloads)


def _case_id(names, v):
    v = str(v)
    if v.isdigit() and int(v) < len(names):
        return int(v)
    for i, n in enumerate(names):
        if n and n.lower() == v.lower():
            return i
    return 0


# ------------------------------------------------------------------ results
def results_query(a, r):
    s_ = conn.get()
    m = s_.model
    A = conn.ax()
    snap = Snapshot(m, loads=False)
    case, combo = a.str("case"), a.str("combo")
    if not case and not combo:
        raise NxError("results need case:'<load case>' or combo:'<combination>'", "cases: %s · combos: %s" % (
            ", ".join(c for c in snap.cases if c), ", ".join(c for c in snap.combos if c) or "-"))
    if case:
        cid = _case_id(snap.cases, case)
        if not cid:
            raise NxError("no load case '%s'" % case, "cases: " + ", ".join(c for c in snap.cases if c))
        label, by = "case '%s'" % snap.cases[cid], "LoadCaseId"
    else:
        cid = _case_id(snap.combos, combo)
        if not cid:
            raise NxError("no combination '%s'" % combo, "combos: " + ", ".join(c for c in snap.combos if c))
        label, by = "combo '%s'" % snap.combos[cid], "LoadCombinationId"
    at = A.atLinearStatic if (a.str("analysis", "linear") or "linear").startswith("lin") else A.atNonLinearStatic
    kind = (a.str("kind", "summary") or "summary").lower()
    filt = a.str("filter", "") or ""
    N, L, D = select(snap, filt) if filt else (list(range(1, len(snap.nodes))), list(range(1, len(snap.lines))), list(range(1, len(snap.domains))))
    if filt and not N and not L and not D:
        raise NxError("filter '%s' selects nothing" % filt)
    if filt and N == [] and (L or D):
        N = sorted({snap.lines[i]["n1"] for i in L} | {snap.lines[i]["n2"] for i in L} | {n for i in D for n in snap.domains[i]["poly"]})
    R = m.Results
    r.line("%s results, %s (m, kN, kNm; displacements mm)" % ("linear" if at == A.atLinearStatic else "nonlinear", label))
    ok = False
    if kind in ("summary", "displacements", "disp"):
        try:
            res = getattr(R.Displacements, "GetAllNodalDisplacementsBy" + by)(cid, 0, at, A.lbFalse)
            vals = res[0]
            if _code(res) > 0 and vals:
                ok = True
                sel = [(i, vals[i - 1]) for i in N if i - 1 < len(vals)]
                for comp in ("ex", "ey", "ez", "eR"):
                    if not sel:
                        break
                    i, v = max(sel, key=lambda t: abs(getattr(t[1], comp)))
                    r.line("  max |%s| = %s mm at n%d %s" % (comp, num(getattr(v, comp) * 1000, 2), i, xyz(snap.nodes[i], 2)))
                if kind != "summary":
                    for i, v in sel[: a.int("limit", 40)]:
                        r.line("  n%d ex %s ey %s ez %s mm" % (i, num(v.ex * 1000, 2), num(v.ey * 1000, 2), num(v.ez * 1000, 2)))
        except Exception as e:
            r.line("  displacements unavailable: %s" % conn.explain_com_error(e))
    if kind in ("summary", "reactions", "supports"):
        try:
            res = getattr(R.Forces, "GetAllNodalSupportForcesBy" + by)(cid, 0, at)
            vals = res[0]
            if _code(res) > 0 and vals:
                ok = True
                sup_node = {}
                for n, sids in snap.nsup.items():
                    for sid in sids:
                        sup_node[sid] = n
                tot = [0.0] * 6
                rows = []
                for sid, v in enumerate(vals, 1):
                    f = [v.Rx, v.Ry, v.Rz, v.Rxx, v.Ryy, v.Rzz]
                    tot = [t + x for t, x in zip(tot, f)]
                    n = sup_node.get(sid, 0)
                    if not filt or n in N:
                        rows.append((sid, n, f))
                r.line("  reactions sum: Rx %s Ry %s Rz %s kN" % (num(tot[0], 2), num(tot[1], 2), num(tot[2], 2)))
                if kind != "summary" or len(rows) <= 8:
                    for sid, n, f in rows[: a.int("limit", 40)]:
                        r.line("  ns%d n%d: R %s %s %s kN · M %s %s %s kNm" % (sid, n, *[num(x, 2) for x in f]))
        except Exception as e:
            r.line("  reactions unavailable: %s" % conn.explain_com_error(e))
    if kind in ("summary", "forces", "lines", "members"):
        try:
            res = getattr(R.Forces, "GetAllLineForcesBy" + by)(cid, 0, at)
            counts, forces, pos = res[0], res[1], res[2]
            if _code(res) > 0 and counts:
                ok = True
                k = 0
                ext = {}
                for lid, c in enumerate(counts, 1):
                    seg = forces[k:k + c]
                    k += c
                    if lid in L and seg:
                        ext[lid] = {f: max((getattr(x, "lfv" + f) for x in seg), key=abs) for f in ("Nx", "Vy", "Vz", "Tx", "My", "Mz")}
                if ext:
                    for comp in ("Nx", "Vz", "My", "Mz"):
                        lid = max(ext, key=lambda i: abs(ext[i][comp]))
                        r.line("  max |%s| = %s at l%d (%s)" % (comp, num(ext[lid][comp], 2), lid, snap.lines[lid]["type"]))
                    if kind != "summary":
                        for lid in sorted(ext)[: a.int("limit", 40)]:
                            e = ext[lid]
                            r.line("  l%d extremes: N %s Vy %s Vz %s T %s My %s Mz %s" % (lid, *[num(e[f], 2) for f in ("Nx", "Vy", "Vz", "Tx", "My", "Mz")]))
        except Exception as e:
            r.line("  line forces unavailable: %s" % conn.explain_com_error(e))
    if kind in ("summary", "surface", "domains") and len(snap.domains) > 1:
        try:
            res = getattr(R.Forces, "GetAllSurfaceForcesBy" + by)(cid, 0, at)
            vals = res[0]
            if _code(res) > 0 and vals:
                ok = True
                for comp in ("Mx", "My", "Nx", "Ny", "Vxz", "Vyz"):
                    v = max((getattr(sf.sfvCenterPoint, "sfv" + comp) for sf in vals), key=abs)
                    r.line("  surface max |%s| = %s (element centres)" % (comp, num(v, 2)))
        except Exception as e:
            r.line("  surface forces unavailable: %s" % conn.explain_com_error(e))
    if not ok:
        r.line("no results for %s. Run edit {analyze:'linear'} first (results are lost after model changes)." % label)


def _code(res):
    return res[-1] if isinstance(res, tuple) else res


# ------------------------------------------------------------------ catalog
def catalog_query(a, r):
    s_ = conn.get()
    A = conn.ax()
    cat = s_.app.Catalog
    f = (a.str("filter") or "").strip()
    limit = a.int("limit", 60)
    if f.lower().startswith("material"):
        pat = f[8:].strip() or "*"
        try:
            dc = s_.model.Settings.NationalDesignCode
        except Exception:
            dc = A.ndcEuroCode
        names = list(cat.GetMaterialNames(dc)[0] or ())
        if not names:
            names = list(cat.GetMaterialNames(A.ndcEuroCode)[0] or ())
        hits = [n for n in names if like(n, pat if "*" in pat else "*%s*" % pat)]
        r.line("%d material(s): %s" % (len(hits), ", ".join(hits[:limit])))
        return
    idx = section_catalog(s_)
    if not f or f.lower() == "tables":
        tables = sorted({t for _, t in idx})
        r.line("%d section tables: %s" % (len(tables), trunc(", ".join(tables), 2500)))
        r.line("search: query {scope:'catalog', filter:'IPE 3*'} · materials: filter:'material C30*'")
        return
    pc = re.sub(r"\s", "", f if "*" in f else "*%s*" % f).lower()
    hits, seen = [], set()
    for n, t in idx:
        if n not in seen and like(re.sub(r"\s", "", n).lower(), pc):
            seen.add(n)
            hits.append("%s [%s]" % (n, t))
    r.line("%d section(s): %s" % (len(hits), ", ".join(hits[:limit])) if hits else "no catalog section matches '%s'" % f)
    if hits:
        r.line("use the exact name in edit, e.g. sec A = %s" % hits[0].split(" [")[0])


_CAT = {}


def section_catalog(s_):
    """[(section name, table)] over all catalog shapes (cssAll returns nothing, so walk the shapes)."""
    if "idx" in _CAT:
        return _CAT["idx"]
    import json, os
    from .core import LOCALDIR
    try:
        stamp = "%s" % int(os.path.getmtime(s_.app.FullExePath))
    except Exception:
        stamp = "x"
    cache = os.path.join(LOCALDIR, "catalog-%s.json" % stamp)
    if os.path.exists(cache):
        with open(cache, encoding="utf-8") as fh:
            _CAT["idx"] = [tuple(x) for x in json.load(fh)]
        return _CAT["idx"]
    A = conn.ax()
    cat = s_.app.Catalog
    out = []
    for name, val in sorted(vars(A).items()):
        if not name.startswith("csse") or name in ("csseAll", "csseCustom") or not isinstance(val, int):
            continue
        try:
            tables = cat.GetCrossSectionTableNamesEx(val)[0] or ()
        except Exception:
            continue
        for t in tables:
            try:
                for n in cat.GetCrossSectionNamesEx(val, t)[0] or ():
                    out.append((n, t))
            except Exception:
                pass
    _CAT["idx"] = out
    os.makedirs(LOCALDIR, exist_ok=True)
    with open(cache, "w", encoding="utf-8") as fh:
        json.dump(out, fh)
    return out

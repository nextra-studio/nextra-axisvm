"""API reference of the INSTALLED AxisVM, read from its COM type library (so it always matches the user's version).

query {scope:'api', filter:...}
  free words        -> ranked one-liners ('add nodal support', 'line load')
  Interface.Member  -> full signature(s) ('IAxisVMLoads.AddBeamDistributed')
  Interface         -> member list ('IAxisVMNodes')
  RRecord / EEnum   -> fields / values ('RLoadBeamDistributed', 'ELineType')
  value search      -> enum constant name ('lbTrue', 'ltBeam')
The index is cached per type-library version in %LOCALAPPDATA%/NextraAxisVM/api-<ver>.json.
Optional: config "api_text" = path to a text export of the AxisVM COM PDF; matching paragraphs are appended.
"""
import json
import os
import re

from .core import LOCALDIR, NxError, cfg, trunc

VT = {2: "short", 3: "long", 4: "float", 5: "double", 6: "currency", 7: "date", 8: "string", 9: "IDispatch",
      10: "error", 11: "bool", 12: "variant", 13: "IUnknown", 16: "int8", 17: "byte", 18: "word", 19: "dword",
      20: "int64", 21: "uint64", 22: "int", 23: "uint", 24: "void", 25: "HRESULT"}
_index = None


def _tdesc(info, td):
    import comtypes.typeinfo as ti
    vt = td.vt
    if vt == 26:   # VT_PTR
        return _tdesc(info, td._.lptdesc[0])
    if vt == 27:   # VT_SAFEARRAY
        return _tdesc(info, td._.lptdesc[0]) + "[]"
    if vt == 29:   # VT_USERDEFINED
        try:
            return info.GetRefTypeInfo(td._.hreftype).GetDocumentation(-1)[0]
        except Exception:
            return "?"
    return VT.get(vt, "vt%d" % vt)


def _build():
    import comtypes.gen.AxisVM as g
    import comtypes.typeinfo as ti
    tlib = ti.LoadTypeLibEx(g.typelib_path)
    la = tlib.GetLibAttr()
    ver = "%d.%d" % (la.wMajorVerNum, la.wMinorVerNum)
    idx = {"version": ver, "interfaces": {}, "records": {}, "enums": {}}
    for i in range(tlib.GetTypeInfoCount()):
        info = tlib.GetTypeInfo(i)
        ta = info.GetTypeAttr()
        name = info.GetDocumentation(-1)[0]
        if ta.typekind == ti.TKIND_ENUM:
            vals = []
            for j in range(ta.cVars):
                vd = info.GetVarDesc(j)
                try:
                    vals.append([info.GetNames(vd.memid)[0], vd._.lpvarValue[0].value])
                except Exception:
                    pass
            idx["enums"][name] = vals
        elif ta.typekind == ti.TKIND_RECORD:
            flds = []
            for j in range(ta.cVars):
                vd = info.GetVarDesc(j)
                flds.append([info.GetNames(vd.memid)[0], _tdesc(info, vd.elemdescVar.tdesc)])
            idx["records"][name] = flds
        elif ta.typekind in (ti.TKIND_DISPATCH, ti.TKIND_INTERFACE):
            if ta.typekind == ti.TKIND_DISPATCH and ta.wTypeFlags & 0x40:   # dual: use the vtable view
                try:
                    info = info.GetRefTypeInfo(info.GetRefTypeOfImplType(-1))
                    ta = info.GetTypeAttr()
                except Exception:
                    pass
            members = {}
            for j in range(ta.cFuncs):
                fd = info.GetFuncDesc(j)
                names = info.GetNames(fd.memid, fd.cParams + 1)
                mname = names[0]
                if mname in ("QueryInterface", "AddRef", "Release", "GetTypeInfoCount", "GetTypeInfo", "GetIDsOfNames", "Invoke"):
                    continue
                ps = []
                for k in range(fd.cParams):
                    ed = fd.lprgelemdescParam[k]
                    flags = ed._.paramdesc.wParamFlags
                    pn = names[k + 1] if k + 1 < len(names) else "p%d" % k
                    t = _tdesc(info, ed.tdesc)
                    if flags & 8:          # PARAMFLAG_FRETVAL
                        continue
                    ps.append(("out " if flags & 2 and not flags & 1 else "var " if flags & 2 else "") + "%s %s" % (t, pn))
                kind = {2: "get", 4: "set", 8: "set"}.get(fd.invkind, "")
                ret = _tdesc(info, fd.elemdescFunc.tdesc)
                # the retval parameter carries the real return type
                for k in range(fd.cParams):
                    ed = fd.lprgelemdescParam[k]
                    if ed._.paramdesc.wParamFlags & 8:
                        ret = _tdesc(info, ed.tdesc)
                sig = ("property %s%s: %s" % (mname, "[%s]" % ", ".join(ps) if ps else "", ret)) if kind == "get" else \
                      ("%s(%s) -> %s" % (mname, ", ".join(ps), ret)) if not kind else None
                if sig:
                    members.setdefault(mname, []).append(sig)
                elif mname not in members:
                    members[mname] = []
                if kind in ("set",) and members.get(mname) and not members[mname][-1].endswith("(settable)"):
                    members[mname][-1] += " (settable)"
            idx["interfaces"][name] = members
    return idx


def index():
    global _index
    if _index is not None:
        return _index
    try:
        import comtypes.gen.AxisVM as g
        stamp = "%s-%d" % (os.path.basename(g.typelib_path), int(os.path.getmtime(g.typelib_path)))
    except Exception as e:
        raise NxError("AxisVM type library not available (%s)" % e, "install AxisVM and run Setup.bat")
    cache = os.path.join(LOCALDIR, "api-%s.json" % re.sub(r"[^\w\-]", "_", stamp))
    if os.path.exists(cache):
        with open(cache, encoding="utf-8") as f:
            _index = json.load(f)
        return _index
    _index = _build()
    os.makedirs(LOCALDIR, exist_ok=True)
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(_index, f)
    return _index


def enum_constants():
    for vals in index()["enums"].values():
        for n, v in vals:
            yield n, v


def _words(s):
    return [w for w in re.split(r"[^a-z0-9]+", re.sub(r"([a-z])([A-Z])", r"\1 \2", s).lower()) if w]


def search(q, limit=25):
    idx = index()
    q = q.strip()
    out = []
    I, R, E = idx["interfaces"], idx["records"], idx["enums"]
    if "." in q and " " not in q:
        iname, m = q.split(".", 1)
        iname = _fix_iface(iname, I)
        mem = I.get(iname, {})
        hits = [k for k in mem if k.lower() == m.lower()] or [k for k in mem if m.lower() in k.lower()]
        if not hits:
            raise NxError("%s has no member like '%s'" % (iname, m), "members: query {scope:'api', filter:'%s'}" % iname)
        for k in hits[:8]:
            for sig in mem[k] or [k + " (write-only)"]:
                out.append("%s.%s" % (iname, sig))
        out += _related_types(" ".join(out), R, E)
        out += _pdf(iname, hits[0])
        return "\n".join(out)
    for table, label in ((I, "interface"), (R, "record"), (E, "enum")):
        hit = next((k for k in table if k.lower() == q.lower()), None)
        if hit:
            if table is I:
                ms = sorted(table[hit])
                return "%s (%d members, AxisVM type library %s):\n%s\nfull signature: query {scope:'api', filter:'%s.<Member>'}" % (
                    hit, len(ms), idx["version"], ", ".join(ms), hit)
            if table is R:
                return "record %s { %s }" % (hit, ", ".join("%s: %s" % (a, b) for a, b in table[hit]))
            return "enum %s: %s" % (hit, ", ".join("%s=%s" % (a, b) for a, b in table[hit]))
    for en, vals in E.items():
        for n, v in vals:
            if n.lower() == q.lower():
                return "%s = %s (enum %s: %s)" % (n, v, en, ", ".join("%s=%s" % (a, b) for a, b in vals[:30]))
    # ranked free-text search over member names, interfaces, records, enums
    qw = _words(q)
    scored = []
    for iname, mem in I.items():
        iw = set(_words(iname))
        for m, sigs in mem.items():
            mw = set(_words(m))
            s = sum(3 if w in mw else 2 if w in iw else (1 if any(w in x for x in mw) else 0) for w in qw)
            if s and any(w in mw or any(w in x for x in mw) for w in qw):
                s -= 0.5 * bool(re.search(r"_V\d+$|_vb$", m)) + 0.1 * len(mw)
                scored.append((s, "%s.%s" % (iname, (sigs or [m])[-1])))
    for rname, f in R.items():
        s = sum(2 for w in qw if w in set(_words(rname)))
        if s:
            scored.append((s - 0.5, "record %s {%s}" % (rname, trunc(", ".join(a for a, _ in f), 120))))
    for ename, vals in E.items():
        s = sum(2 for w in qw if w in set(_words(ename)))
        if s:
            scored.append((s - 0.5, "enum %s: %s" % (ename, trunc(", ".join("%s=%s" % (a, b) for a, b in vals), 140))))
    scored.sort(key=lambda t: -t[0])
    if not scored:
        return "no API match for '%s'. Try other words, an interface ('IAxisVMLoads') or a record ('RLoadBeamDistributed')." % q
    best = scored[0][0]
    lines = [trunc(x, 230) for s, x in scored[:limit] if s >= best - 2]
    return "\n".join(lines) + "\nfull: query {scope:'api', filter:'Interface.Member'} · records/enums by name"


def _fix_iface(name, I):
    for cand in (name, "IAxisVM" + name, "IAxisVM" + name.replace("IAxisVM", "")):
        hit = next((k for k in I if k.lower() == cand.lower()), None)
        if hit:
            return hit
    raise NxError("no interface '%s'" % name, "e.g. IAxisVMNodes, IAxisVMLines, IAxisVMLoads, IAxisVMDomains")


def _related_types(text, R, E):
    out = []
    for t in sorted(set(re.findall(r"\b([RE][A-Z]\w+)", text))):
        if t in R:
            out.append("  record %s { %s }" % (t, trunc(", ".join("%s: %s" % (a, b) for a, b in R[t]), 600)))
        elif t in E:
            out.append("  enum %s: %s" % (t, trunc(", ".join("%s=%s" % (a, b) for a, b in E[t]), 400)))
    return out


def _pdf(iface, member):
    p = cfg("api_text")
    if not p or not os.path.exists(p):
        return []
    try:
        with open(p, encoding="utf-8", errors="ignore") as f:
            lines = f.read().splitlines()
    except OSError:
        return []
    for i, l in enumerate(lines):
        if l.strip() == "%s.%s" % (iface, member) or l.strip().startswith(member + "(") or l.strip() == member:
            block = [x for x in lines[i:i + 30] if x.strip()]
            return ["  doc (%s):" % os.path.basename(p)] + ["    " + trunc(x, 160) for x in block[:20]]
    return []

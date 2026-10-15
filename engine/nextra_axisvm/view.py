"""view: images the model can point at.

target 'model' (default): Nextra's own drawing of the AxisVM model (exact, independent of AxisVM's window), orthographic,
  with an 8x8 grid (columns A-H, rows 1-8) and handle tags (n5 l12 d3). Crowded → no tags, per-cell counts; then
  focus:'C3:E5' re-renders that region of the last image, tagged. focus can also be handles 'l3 d1' or a filter
  'type:beam' (framed; isolate:true hides the rest). Results: case/combo + result:'deformed'|'Nx'|'Vz'|'My'|'Mz'.
target 'axisvm': screenshot of AxisVM's own window (whatever it shows: results, contours, labels); view sets its view.
"""
import math
import os
import re
import time

from . import conn
from .core import LOCALDIR, STATE, NxError, num, ranges, trunc
from .modeldata import Snapshot

COLS = "ABCDEFGH"
EYES = {"iso": (1.0, -1.3, 0.9), "persp": (1.0, -1.3, 0.9), "top": (0, 0, 1), "front": (0, -1, 0), "back": (0, 1, 0),
        "right": (1, 0, 0), "left": (-1, 0, 0), "bottom": (0, 0, -1), "iso2": (-1.0, -1.3, 0.9)}
LINE_COL = {"beam": (31, 78, 160), "rib": (18, 130, 125), "truss": (214, 110, 20), "spring": (150, 60, 160),
            "line": (120, 120, 120), "edge": (205, 205, 205)}
DOM_COL = {"plate": (170, 190, 220), "shell": (175, 215, 180), "membrane": (235, 215, 150), "membrane-strain": (235, 215, 150)}


def run(a, r):
    target = (a.str("target", "model") or "model").lower()
    if target == "axisvm":
        return axisvm_capture(a, r)
    if target != "model":
        raise NxError("target: model | axisvm")
    s = conn.get()
    snap = Snapshot(s.model, loads=False)
    if len(snap.nodes) <= 1:
        r.line("the model is empty (no nodes)")
        return
    W, H = (a.get("size") or [800, 600])[:2]
    W, H = int(W), int(H)
    focus = (a.str("focus") or "").strip()
    vname = (a.str("view") or (STATE.get("last_view") or {}).get("view") if re.fullmatch(r"[A-H][1-8](:[A-H][1-8])?", focus) else a.str("view")) or "iso"
    if vname not in EYES:
        raise NxError("view '%s' unknown" % vname, "iso | top | front | back | left | right | bottom | iso2")
    cam = Camera(EYES[vname], vname)
    lines = [i for i in range(1, len(snap.lines)) if snap.lines[i]["type"] != "edge"]
    doms = list(range(1, len(snap.domains)))
    hi_l, hi_d, hi_n = set(), set(), set()
    window = None
    if focus:
        mcell = re.fullmatch(r"([A-H])([1-8])(?::([A-H])([1-8]))?", focus)
        if mcell:
            last = STATE.get("last_view")
            if not last:
                raise NxError("no previous model image to zoom into", "view {} first")
            cam = last["cam"]
            vname = cam.name
            c0, r0 = COLS.index(mcell.group(1)), int(mcell.group(2)) - 1
            c1, r1 = (COLS.index(mcell.group(3)), int(mcell.group(4)) - 1) if mcell.group(3) else (c0, r0)
            c0, c1 = sorted((c0, c1))
            r0, r1 = sorted((r0, r1))
            lw = last["window"]
            fx = lambda c: lw[0] + (lw[2] - lw[0]) * c / 8.0
            fy = lambda rr: lw[3] - (lw[3] - lw[1]) * rr / 8.0
            window = (fx(c0), fy(r1 + 1), fx(c1 + 1), fy(r0))
        else:
            from .query import select
            N, L, D = select(snap, focus, s.model)
            if not (N or L or D):
                raise NxError("focus '%s' selects nothing" % focus)
            hi_l, hi_d, hi_n = set(L), set(D), set(N)
            if a.bool("isolate"):
                lines, doms = [i for i in lines if i in hi_l], [i for i in doms if i in hi_d]
    # optional results
    res = result_overlay(a, s, snap) if (a.has("case") or a.has("combo")) else None
    disp = res.get("disp") if res else None
    pts3 = {}

    def P(n):
        if n not in pts3:
            p = snap.nodes[n]
            if disp and n - 1 < len(disp):
                d = disp[n - 1]
                p = (p[0] + d[0] * res["dscale"], p[1] + d[1] * res["dscale"], p[2] + d[2] * res["dscale"])
            pts3[n] = p
        return pts3[n]

    # framing
    if window is None:
        if hi_l or hi_d or hi_n:
            ids = {snap.lines[i]["n1"] for i in hi_l} | {snap.lines[i]["n2"] for i in hi_l} | {n for d in hi_d for n in snap.domains[d]["poly"]} | hi_n
        else:
            ids = {snap.lines[i]["n1"] for i in lines} | {snap.lines[i]["n2"] for i in lines} | {n for d in doms for n in snap.domains[d]["poly"]}
            ids = ids or set(range(1, len(snap.nodes)))
        xy = [cam.proj(P(n)) for n in ids]
        window = fit(xy, W, H)
    img, tags, counts, shown = draw(snap, cam, window, W, H, lines, doms, hi_l, hi_d, hi_n, P, res, a)
    os.makedirs(os.path.join(LOCALDIR, "captures"), exist_ok=True)
    STATE["img_n"] = STATE.get("img_n", 0) + 1
    path = os.path.join(LOCALDIR, "captures", "view_%s_%d.png" % (time.strftime("%H%M%S"), STATE["img_n"]))
    img.save(path)
    r.images.append(path)
    STATE["last_view"] = {"cam": cam, "window": window, "view": vname}
    head = "model view '%s' %dx%d%s. Grid A-H x 1-8." % (vname, W, H, " focus " + focus if focus else "")
    r.line(head)
    if res:
        r.line(res["text"])
    r.line("%d element(s) in frame%s" % (shown, ", tagged: " + trunc(tags, 600) if tags else ""))
    if counts:
        r.line("crowded: no tags. Elements per cell: " + " ".join("%s:%d" % kv for kv in counts))
        r.line("zoom: view {focus:'C3:E5'} (cells of this image) · or focus:'type:beam' / 'l3 l4'")


class Camera:
    def __init__(self, eye, name):
        w = _norm(eye)
        up = (0, 1, 0) if abs(w[2]) > 0.99 else (0, 0, 1)
        u = _norm(_cross(up, w))
        v = _cross(w, u)
        self.w, self.u, self.v, self.name = w, u, v, name

    def proj(self, p):
        return (_dot(p, self.u), _dot(p, self.v))

    def depth(self, p):
        return _dot(p, self.w)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    l = math.sqrt(_dot(a, a)) or 1.0
    return (a[0] / l, a[1] / l, a[2] / l)


def fit(xy, W, H, margin=0.08):
    xs, ys = [p[0] for p in xy], [p[1] for p in xy]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    w, h = max(x1 - x0, 1e-6), max(y1 - y0, 1e-6)
    s = max(w / (W * (1 - 2 * margin)), h / (H * (1 - 2 * margin)))
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return (cx - s * W / 2, cy - s * H / 2, cx + s * W / 2, cy + s * H / 2)


def draw(snap, cam, window, W, H, lines, doms, hi_l, hi_d, hi_n, P, res, a):
    from PIL import Image, ImageDraw, ImageFont
    S = 2                                    # supersample for clean lines/text
    img = Image.new("RGB", (W * S, H * S), (255, 255, 255))
    dr = ImageDraw.Draw(img, "RGBA")
    x0, y0, x1, y1 = window
    sx = W * S / (x1 - x0)

    def scr(p):
        u, v = cam.proj(p)
        return ((u - x0) * sx, (y1 - v) * sx)

    try:
        font = ImageFont.truetype("arial.ttf", 11 * S)
        small = ImageFont.truetype("arial.ttf", 10 * S)
    except Exception:
        font = small = ImageFont.load_default()
    focus_mode = bool(hi_l or hi_d or hi_n)
    inside = lambda q: -5 <= q[0] <= W * S + 5 and -5 <= q[1] <= H * S + 5
    # domains, far first
    order = sorted(doms, key=lambda d: sum(cam.depth(P(n)) for n in snap.domains[d]["poly"]) / max(1, len(snap.domains[d]["poly"])))
    shown_d = []
    for d in order:
        poly = [scr(P(n)) for n in snap.domains[d]["poly"]]
        if len(poly) < 3:
            continue
        col = DOM_COL.get(snap.domains[d]["type"], (200, 200, 200))
        alpha = 150 if (not focus_mode or d in hi_d) else 45
        dr.polygon(poly, fill=col + (alpha,), outline=(110, 120, 140, 200))
        if any(inside(q) for q in poly):
            shown_d.append(d)
    # lines
    color_by = res.get("line_vals") if res else None
    vmax = max((abs(v) for v in color_by.values()), default=0) if color_by else 0
    shown_l = []
    for i in lines:
        L = snap.lines[i]
        p, q = scr(P(L["n1"])), scr(P(L["n2"]))
        if not (inside(p) or inside(q)) and not _seg_hits_box(p, q, W * S, H * S):
            continue
        col = LINE_COL.get(L["type"], (90, 90, 90))
        width = 3 if L["type"] in ("beam", "rib", "truss") else 1
        if color_by and i in color_by and vmax > 0:
            col = _heat(abs(color_by[i]) / vmax)
            width = 4
        if focus_mode and i not in hi_l:
            col, width = (200, 200, 200), 1
        dr.line([p, q], fill=col, width=width * S)
        shown_l.append(i)
    if res and res.get("disp"):        # undeformed ghost
        for i in lines:
            L = snap.lines[i]
            p0, q0 = snap.nodes[L["n1"]], snap.nodes[L["n2"]]
            u0, u1 = cam.proj(p0), cam.proj(q0)
            dr.line([((u0[0] - x0) * sx, (y1 - u0[1]) * sx), ((u1[0] - x0) * sx, (y1 - u1[1]) * sx)], fill=(150, 150, 150, 120), width=S)
    # supports
    for n in snap.nsup:
        q = scr(P(n))
        if inside(q):
            r_ = 6 * S
            dr.polygon([(q[0], q[1]), (q[0] - r_, q[1] + 1.6 * r_), (q[0] + r_, q[1] + 1.6 * r_)], fill=(200, 40, 40, 220))
    # grid
    for k in range(1, 8):
        X, Y = k * W * S / 8, k * H * S / 8
        dr.line([(X, 0), (X, H * S)], fill=(0, 0, 0, 28), width=S)
        dr.line([(0, Y), (W * S, Y)], fill=(0, 0, 0, 28), width=S)
    for k in range(8):
        dr.text((k * W * S / 8 + 4 * S, 2 * S), COLS[k], fill=(120, 120, 120), font=small)
        dr.text((2 * S, k * H * S / 8 + 14 * S), str(k + 1), fill=(120, 120, 120), font=small)
    # tags
    cands = []
    for i in shown_l:
        L = snap.lines[i]
        p, q = scr(P(L["n1"])), scr(P(L["n2"]))
        if focus_mode and i not in hi_l:
            continue
        cands.append(("l%d" % i, ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2), LINE_COL.get(L["type"], (60, 60, 60))))
    for d in shown_d:
        if focus_mode and d not in hi_d:
            continue
        pts = [scr(P(n)) for n in snap.domains[d]["poly"]]
        cands.append(("d%d" % d, (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)), (60, 70, 110)))
    want_nodes = hi_n or a.str("tags") == "nodes"
    for n in (hi_n or (range(1, len(snap.nodes)) if want_nodes else [])):
        q = scr(P(n))
        if inside(q):
            dr.ellipse([q[0] - 2 * S, q[1] - 2 * S, q[0] + 2 * S, q[1] + 2 * S], fill=(0, 0, 0))
            cands.append(("n%d" % n, q, (0, 0, 0)))
    tagmode = (a.str("tags") or "auto").lower()
    counts = []
    tagged = []
    cells = {}
    for name, q, _ in cands:
        if inside(q):
            c = "%s%d" % (COLS[min(7, max(0, int(q[0] / (W * S / 8))))], min(8, max(1, int(q[1] / (H * S / 8)) + 1)))
            cells[c] = cells.get(c, 0) + 1
    crowded = len(cands) > 70 or (cells and max(cells.values()) > 14)
    if tagmode == "off" or (tagmode == "auto" and crowded):
        if tagmode != "off":
            counts = sorted(cells.items(), key=lambda kv: (kv[0][1], kv[0][0]))
    else:
        boxes = []
        for name, q, col in cands:
            tw, th = dr.textbbox((0, 0), name, font=font)[2:]
            placed = None
            for dx, dy in ((4, -th - 4), (4, 4), (-tw - 4, -th - 4), (-tw - 4, 4), (-tw / 2, -th - 10), (-tw / 2, 8)):
                b = (q[0] + dx * 1, q[1] + dy * 1, q[0] + dx + tw, q[1] + dy + th)
                if b[0] < 0 or b[1] < 0 or b[2] > W * S or b[3] > H * S:
                    continue
                if not any(not (b[2] < o[0] or b[0] > o[2] or b[3] < o[1] or b[1] > o[3]) for o in boxes):
                    placed = b
                    break
            if not placed:
                continue
            boxes.append(placed)
            dr.rectangle([placed[0] - S, placed[1] - S, placed[2] + S, placed[3] + S], fill=(255, 255, 255, 215))
            dr.text((placed[0], placed[1]), name, fill=col, font=font)
            tagged.append(name)
    if res and res.get("legend"):
        dr.text((8 * S, H * S - 18 * S), res["legend"], fill=(40, 40, 40), font=font)
    img = img.resize((W, H), Image.LANCZOS)
    groups = {}
    for t in tagged:
        groups.setdefault(t[0], []).append(int(t[1:]))
    tags = " ".join(ranges(v, k) for k, v in groups.items())
    return img, tags, counts, len(shown_l) + len(shown_d)


def _seg_hits_box(p, q, W, H):
    return not (max(p[0], q[0]) < 0 or min(p[0], q[0]) > W or max(p[1], q[1]) < 0 or min(p[1], q[1]) > H)


def _heat(t):
    t = max(0.0, min(1.0, t))
    return (int(40 + 215 * t), int(90 + 60 * (1 - abs(t - 0.5) * 2)), int(200 * (1 - t)))


def result_overlay(a, s, snap):
    """Deformed shape or line force colouring for one case/combo."""
    from .query import _case_id
    A = conn.ax()
    m = s.model
    case, combo = a.str("case"), a.str("combo")
    if case:
        cid, by, label = _case_id(snap.cases, case), "LoadCaseId", "case " + case
    else:
        cid, by, label = _case_id(snap.combos, combo), "LoadCombinationId", "combo " + combo
    if not cid:
        raise NxError("unknown %s" % label)
    what = (a.str("result") or "deformed").lower()
    out = {}
    if what in ("deformed", "disp", "displacement"):
        res = getattr(m.Results.Displacements, "GetAllNodalDisplacementsBy" + by)(cid, 0, A.atLinearStatic, A.lbFalse)
        vals = res[0] or ()
        if not vals:
            raise NxError("no results for %s" % label, "edit {analyze:'linear'}")
        d = [(v.ex, v.ey, v.ez) for v in vals]
        dmax = max(math.sqrt(x * x + y * y + z * z) for x, y, z in d) or 1e-12
        bb = snap.bbox()
        size = max(bb[1][k] - bb[0][k] for k in range(3)) if bb else 1.0
        scale = float(a.get("scale") or (0.08 * size / dmax))
        out.update(disp=d, dscale=scale, text="deformed shape, %s: max %s mm, drawn ×%s (grey = undeformed)" % (label, num(dmax * 1000, 2), num(scale, 2)))
        return out
    comp = {"nx": "Nx", "n": "Nx", "vy": "Vy", "vz": "Vz", "v": "Vz", "t": "Tx", "tx": "Tx", "my": "My", "m": "My", "mz": "Mz"}.get(what)
    if not comp:
        raise NxError("result '%s' unknown" % what, "deformed | Nx | Vy | Vz | Tx | My | Mz")
    res = getattr(m.Results.Forces, "GetAllLineForcesBy" + by)(cid, 0, A.atLinearStatic)
    counts, forces = res[0] or (), res[1] or ()
    if not counts:
        raise NxError("no line force results for %s" % label, "edit {analyze:'linear'}")
    vals, k = {}, 0
    for lid, c in enumerate(counts, 1):
        seg = forces[k:k + c]
        k += c
        if seg:
            vals[lid] = max((getattr(x, "lfv" + comp) for x in seg), key=abs)
    vmax = max((abs(v) for v in vals.values()), default=0)
    out.update(line_vals=vals, text="lines coloured by |%s| (%s), max %s kN/kNm (blue low → red high)" % (comp, label, num(vmax, 2)),
               legend="|%s| max %s" % (comp, num(vmax, 2)))
    return out


def axisvm_capture(a, r):
    s = conn.get()
    m = s.model
    A = conn.ax()
    wins = m.Windows
    idx = a.int("window", 0) or wins.ActiveWindowIndex or 1
    v = (a.str("view") or "").lower()
    if v:
        ev = {"front": A.vFront, "top": A.vTop, "side": A.vSide, "right": A.vSide, "persp": A.vPerspective, "iso": A.vPerspective}.get(v)
        if ev is None:
            raise NxError("AxisVM window views: front | top | side | persp")
        wins.View[idx] = ev
    if a.bool("fit", True):
        try:
            m.FitInView()
        except Exception:
            pass
    os.makedirs(os.path.join(LOCALDIR, "captures"), exist_ok=True)
    bmp = os.path.join(LOCALDIR, "captures", "axisvm_%s.bmp" % time.strftime("%H%M%S"))
    rc = wins.SaveWindowToBitmap(idx, A.wcmColour, bmp)
    if not os.path.exists(bmp):
        raise NxError("AxisVM could not save its window (%s)" % (rc,))
    from PIL import Image
    im = Image.open(bmp).convert("RGB")
    W, H = (a.get("size") or [1000, 750])[:2]
    im.thumbnail((int(W), int(H)))
    png = bmp[:-4] + ".png"
    im.save(png)
    try:
        os.remove(bmp)
    except OSError:
        pass
    r.images.append(png)
    r.line("AxisVM window %d (%dx%d)%s. Shows what AxisVM displays (results/contours set in AxisVM). "
           "Element tags: view {} (target model)." % (idx, im.size[0], im.size[1], " view " + v if v else ""))

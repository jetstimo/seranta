# -*- coding: utf-8 -*-
"""Integritas jalur kabel (Python murni, bisa diuji tanpa QGIS) - Seranta 3.13.0.

Jalur di KMZ harus menjadi SATU jaringan kabel yang bisa dibangun: setiap bagian kabel ditumpu tiang, ujung kabel
berakhir di tiang, percabangan ada di tiang, dan semua bagian tersambung ke jaringan cluster. Pemeriksaan bentang lama
hanya menilai rentang yang KEDUA ujungnya tiang; bagian jalur yang berujung di titik tanpa tiang (ujung, percabangan)
atau tidak punya tiang sama sekali tidak pernah diukur sepanjang jalurnya. Modul ini menutup celah itu.

Dasar (sumber dapat diperiksa, lihat DASAR_ATURAN.md bagian 3.13.0):
* Bentang = jarak dua titik tumpu kabel berurutan (USDA RUS Bulletin 1751F-630, Definitions; Corning AEN 14). Kabel di
  antara dua titik tumpu yang bukan tiang (ujung/percabangan tanpa tiang) tetap satu bentang tanpa tumpuan -> diukur
  sepanjang jalur sampai tiang terdekat dan dinilai dengan batas bentang yang sama.
* Ujung jalur di tiang tambat akhir (RUS 1751F-650: deadend guy "at the end of a line"); sambungan/percabangan kabel di
  tiang (Fiber Optic Association, Aerial Workmanship: "Splice closures should be attached to poles"; "no loose hanging
  cables along the span").
* Jaringan distribusi satu hubungan OLT -> banyak ONT lewat ODN (ITU-T G.984.1 ps. 1 dan 3.6): bagian jalur yang tidak
  tersambung ke jaringan cluster tidak bisa dialiri serat dari FDT cluster itu.

Semua koordinat dalam meter (proyeksi lokal). Kunci simpul: ("P", indeks_tiang) atau ("X", x, y).
Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later.
"""
import heapq
import math


def _uf_find(par, a):
    while par[a] != a:
        par[a] = par[par[a]]
        a = par[a]
    return a


def _uf_union(par, a, b):
    ra, rb = _uf_find(par, a), _uf_find(par, b)
    if ra != rb:
        par[rb] = ra


def _plen(xy):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(xy, xy[1:]))


def _pt_seg(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 <= 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy), t


def _seg_seg(a, b, c, d):
    """Jarak terdekat dua ruas (0 bila berpotongan)."""
    if _intersect(a, b, c, d) is not None:
        return 0.0
    return min(_pt_seg(a, c, d)[0], _pt_seg(b, c, d)[0], _pt_seg(c, a, b)[0], _pt_seg(d, a, b)[0])


def _intersect(a, b, c, d):
    """Titik potong ruas a-b dan c-d (termasuk menyentuh), atau None. -> (x, y, ta, tc)"""
    r = (b[0] - a[0], b[1] - a[1])
    s = (d[0] - c[0], d[1] - c[1])
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < 1e-12:
        return None
    qp = (c[0] - a[0], c[1] - a[1])
    t = (qp[0] * s[1] - qp[1] * s[0]) / den
    u = (qp[0] * r[1] - qp[1] * r[0]) / den
    eps = 1e-9
    if -eps <= t <= 1 + eps and -eps <= u <= 1 + eps:
        return (a[0] + t * r[0], a[1] + t * r[1], t, u)
    return None


def _angle(a, b, c, d):
    """Sudut lancip (0-90 derajat) antara arah ruas a-b dan c-d."""
    v1 = (b[0] - a[0], b[1] - a[1])
    v2 = (d[0] - c[0], d[1] - c[1])
    n1, n2 = math.hypot(*v1), math.hypot(*v2)
    if not n1 or not n2:
        return 0.0
    cs = abs(v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)
    return math.degrees(math.acos(max(-1.0, min(1.0, cs))))


class _Grid(object):
    def __init__(self, cell):
        self.cell, self.g = float(cell), {}

    def _cells(self, a, b, pad):
        c = self.cell
        x0, x1 = int(math.floor((min(a[0], b[0]) - pad) / c)), int(math.floor((max(a[0], b[0]) + pad) / c))
        y0, y1 = int(math.floor((min(a[1], b[1]) - pad) / c)), int(math.floor((max(a[1], b[1]) + pad) / c))
        for i in range(x0, x1 + 1):
            for j in range(y0, y1 + 1):
                yield (i, j)

    def add(self, idx, a, b):
        for k in self._cells(a, b, 0.0):
            self.g.setdefault(k, []).append(idx)

    def near(self, a, b, pad):
        out = set()
        for k in self._cells(a, b, pad):
            out.update(self.g.get(k, ()))
        return out


# ---------------------------------------------------------------- bagian jalur tanpa tiang

def pieces(spans, deg):
    """Bagian jalur di antara titik tumpu (tiang). spans: [(ka, kb, L, xy)] hasil penelusuran rentang (setelah dipecah
    di tiang yang berdiri di garis); deg: derajat simpul X di graf jalur lengkap.
    -> [dict(spans=[i], poles=set(kunci P), leaves=set, junctions=set, length)] hanya untuk rentang yang punya ujung X."""
    idx = [i for i, s in enumerate(spans) if s[0][0] != "P" or s[1][0] != "P"]
    par = {}
    for i in idx:
        for k in spans[i][:2]:
            if k[0] == "X":
                par.setdefault(k, k)
    for i in idx:
        xs = [k for k in spans[i][:2] if k[0] == "X"]
        for k in xs[1:]:
            _uf_union(par, xs[0], k)
    grp = {}
    for i in idx:
        x0 = next(k for k in spans[i][:2] if k[0] == "X")
        grp.setdefault(_uf_find(par, x0), []).append(i)
    out = []
    for _r, ii in sorted(grp.items(), key=lambda t: min(t[1])):
        P, X = set(), set()
        for i in ii:
            for k in spans[i][:2]:
                (P if k[0] == "P" else X).add(k)
        out.append({"spans": ii, "poles": P,
                    "leaves": {k for k in X if deg.get(k, 0) == 1},
                    # simpul X di ujung rentang yang bukan ujung jalur = titik henti penelusuran (percabangan, garis rangkap
                    # yang berakhir di titik sudut, awal lingkar): kabel di kedua sisinya satu bentang tanpa tumpuan
                    "junctions": {k for k in X if deg.get(k, 0) != 1},
                    "length": sum(spans[i][2] for i in ii)})
    return out


def _dijkstra(spans, ii, src):
    adj = {}
    for i in ii:
        ka, kb, L = spans[i][0], spans[i][1], spans[i][2]
        adj.setdefault(ka, []).append((i, kb, L))
        adj.setdefault(kb, []).append((i, ka, L))
    dist, prev = {src: 0.0}, {}
    h = [(0.0, 0, src)]
    n = 0
    while h:
        d, _c, u = heapq.heappop(h)
        if d > dist.get(u, 1e18):
            continue
        for i, v, L in adj.get(u, ()):
            nd = d + L
            if nd < dist.get(v, 1e18) - 1e-9:
                dist[v], prev[v] = nd, (u, i)
                n += 1
                heapq.heappush(h, (nd, n, v))
    return dist, prev


def _path_xy(spans, prev, src, dst):
    """Polyline dari src ke dst menurut pohon Dijkstra (orientasi tiap rentang diperhatikan)."""
    chain, cur = [], dst
    while cur != src and cur in prev:
        u, i = prev[cur]
        chain.append((u, i, cur))
        cur = u
    chain.reverse()
    xy = []
    for u, i, v in chain:
        ka, kb, _L, pts = spans[i]
        seq = list(pts) if ka == u else list(reversed(pts))
        xy.extend(seq if not xy else seq[1:])
    return xy, [i for _u, i, _v in chain]


def evaluate_piece(piece, spans, pole_kind=None):
    """Nilai satu bagian jalur tanpa tiang. -> daftar dict(tipe, panjang, xy, ujung_a, ujung_b, span_idx)
    tipe: 'tanpa_tiang' (tidak ada tiang sama sekali), 'ujung' (ujung jalur -> tiang terdekat sepanjang jalur),
    'antartiang' (dua tiang lewat percabangan/simpul tanpa tiang)."""
    pole_kind = pole_kind or {}
    ii = piece["spans"]
    out = []
    if not piece["poles"]:
        # tidak ada tiang sama sekali: panjang = seluruh kabel bagian ini; garis = lintasan terpanjang antar ujung
        best = None
        ends = sorted(piece["leaves"]) or sorted({k for i in ii for k in spans[i][:2]})[:1]
        for a in ends:
            dist, prev = _dijkstra(spans, ii, a)
            b = max(dist, key=lambda k: (dist[k], k))
            if best is None or dist[b] > best[0]:
                best = (dist[b], a, b, prev)
        if best and best[0] > 0:
            xy, si = _path_xy(spans, best[3], best[1], best[2])
        else:
            xy, si = list(spans[ii[0]][3]), [ii[0]]
        out.append({"tipe": "tanpa_tiang", "panjang": piece["length"], "xy": xy, "ujung_a": None, "ujung_b": None,
                    "span_idx": si})
        return out
    # ujung jalur: jarak SEPANJANG JALUR ke tiang terdekat (kabel tergantung tanpa tumpuan dari tiang itu ke ujung)
    worst = None
    for lf in sorted(piece["leaves"]):
        dist, prev = _dijkstra(spans, ii, lf)
        cand = [(d, k) for k, d in dist.items() if k[0] == "P"]
        if not cand:
            continue
        d, p = min(cand)
        if worst is None or d > worst[0]:
            worst = (d, lf, p, prev)
    if worst:
        xy, si = _path_xy(spans, worst[3], worst[1], worst[2])
        out.append({"tipe": "ujung", "panjang": worst[0], "xy": list(reversed(xy)), "ujung_a": worst[2],
                    "ujung_b": worst[1], "span_idx": si})
    # dua tiang lewat simpul tanpa tiang (percabangan): kabel di antaranya satu bentang tanpa tumpuan
    if len(piece["poles"]) >= 2 and piece["junctions"]:
        worst = None
        P = sorted(piece["poles"])
        for a in P:
            dist, prev = _dijkstra(spans, ii, a)
            for b in P:
                if b <= a or b not in dist:
                    continue
                if pole_kind.get(a[1]) == "existing" and pole_kind.get(b[1]) == "existing":
                    continue        # EP-EP: tiang pihak lain, tidak dinilai (sama dengan rentang biasa)
                xy, si = _path_xy(spans, prev, a, b)
                if not any(spans[i][0] in piece["junctions"] or spans[i][1] in piece["junctions"] for i in si):
                    continue
                if worst is None or dist[b] > worst[0]:
                    worst = (dist[b], a, b, xy, si)
        if worst:
            out.append({"tipe": "antartiang", "panjang": worst[0], "xy": worst[3], "ujung_a": worst[1],
                        "ujung_b": worst[2], "span_idx": worst[4]})
    return out


# ---------------------------------------------------------------- jalur terputus

def components(spans):
    """Komponen jalur tersambung. -> [dict(spans=[i], poles=set, length, keys=set)] urut panjang menurun."""
    par = {}
    for ka, kb, _L, _xy in spans:
        par.setdefault(ka, ka)
        par.setdefault(kb, kb)
        _uf_union(par, ka, kb)
    grp = {}
    for i, s in enumerate(spans):
        grp.setdefault(_uf_find(par, s[0]), []).append(i)
    out = []
    for ii in grp.values():
        keys = {k for i in ii for k in spans[i][:2]}
        out.append({"spans": ii, "keys": keys, "poles": {k for k in keys if k[0] == "P"},
                    "length": sum(spans[i][2] for i in ii)})
    out.sort(key=lambda c: (-c["length"], min(c["spans"])))
    return out


def comp_gap(spans, ca, cb, cell=50.0, cap=1e9):
    """Jarak terdekat dua komponen jalur (m) dan titik terdekat di ca. -> (jarak, (x, y))"""
    g = _Grid(cell)
    segs_b = []
    for i in cb["spans"]:
        xy = spans[i][3]
        for a, b in zip(xy, xy[1:]):
            segs_b.append((a, b))
            g.add(len(segs_b) - 1, a, b)
    best = (cap, None)
    for i in ca["spans"]:
        xy = spans[i][3]
        for a, b in zip(xy, xy[1:]):
            pad = min(best[0], cell)
            for j in g.near(a, b, pad):
                c, d = segs_b[j]
                dd = _seg_seg(a, b, c, d)
                if dd < best[0]:
                    pa = min((a, b), key=lambda p: _pt_seg(p, c, d)[0])
                    best = (dd, pa)
    if best[1] is None:
        # tidak ada ruas dalam jangkauan sel: cari kasar dari titik ujung
        for i in ca["spans"]:
            for p in (spans[i][3][0], spans[i][3][-1]):
                for c, d in segs_b:
                    dd = _pt_seg(p, c, d)[0]
                    if dd < best[0]:
                        best = (dd, p)
    return best


# ---------------------------------------------------------------- persilangan & tumpukan

def crossings(segs, node_tol=0.5, min_angle=10.0, cell=50.0):
    """Ruas jalur yang berpotongan/bersinggungan TANPA simpul bersama. segs: [(ka, kb, a_xy, b_xy)].
    Sudut < min_angle derajat = garis bertumpuk (dinilai di overlaps), bukan persilangan.
    -> [dict(x, y, sudut, i, j)] satu per titik (titik berdekatan <= 1 m digabung)."""
    g = _Grid(cell)
    for i, (_ka, _kb, a, b) in enumerate(segs):
        g.add(i, a, b)
    found = []
    for i, (ka, kb, a, b) in enumerate(segs):
        for j in g.near(a, b, 0.0):
            if j <= i:
                continue
            kc, kd, c, d = segs[j]
            if {ka, kb} & {kc, kd}:
                continue
            x = _intersect(a, b, c, d)
            if x is None:
                continue
            ang = _angle(a, b, c, d)
            if ang < min_angle:
                continue
            px, py = x[0], x[1]
            if any(math.hypot(px - f["x"], py - f["y"]) <= 1.0 for f in found):
                continue
            # jarak titik potong ke keempat titik ujung ruas (untuk mengenali ujung garis yang menempel/melewati garis lain)
            found.append({"x": px, "y": py, "sudut": ang, "i": i, "j": j,
                          "ujung": [(math.hypot(px - p[0], py - p[1]), k) for p, k in ((a, ka), (b, kb), (c, kc), (d, kd))],
                          "singgung": min(math.hypot(px - p[0], py - p[1]) for p in (a, b, c, d)) <= node_tol})
    return found


def leaf_near_lines(segs, leaves, tol, cell=50.0):
    """Ujung jalur (simpul derajat 1) yang berjarak <= tol m dari ruas jalur lain tanpa tersambung. -> {kunci: jarak}"""
    g = _Grid(cell)
    pos, nbr = {}, {}
    for i, (ka, kb, a, b) in enumerate(segs):
        g.add(i, a, b)
        nbr.setdefault(ka, set()).add(kb)
        nbr.setdefault(kb, set()).add(ka)
        for k, p in ((ka, a), (kb, b)):
            if k in leaves:
                pos[k] = p
    out = {}
    for k, p in pos.items():
        best = None
        near_k = {k} | nbr.get(k, set())       # ruas yang menyentuh ujung ini atau tetangganya = garisnya sendiri
        for j in g.near(p, p, tol):
            ka, kb, a, b = segs[j]
            if ka in near_k or kb in near_k:
                continue
            d = _pt_seg(p, a, b)[0]
            if d <= tol and (best is None or d < best):
                best = d
        if best is not None:
            out[k] = best
    return out


def overlaps(segs, tol=1.0, max_angle=10.0, min_len=0.5, cell=50.0):
    """Ruas jalur yang digambar menumpuk (searah/berbalik di jalur yang sama, jarak <= tol m, sudut < max_angle).
    -> [dict(panjang, xy=[(x,y),(x,y)], i, j)] per pasangan ruas, panjang tumpukan > min_len."""
    g = _Grid(cell)
    for i, (_ka, _kb, a, b) in enumerate(segs):
        g.add(i, a, b)
    out = []
    for i, (ka, kb, a, b) in enumerate(segs):
        for j in g.near(a, b, tol):
            if j <= i:
                continue
            _kc, _kd, c, d = segs[j]
            if _angle(a, b, c, d) >= max_angle:
                continue
            La, Lc = math.hypot(b[0] - a[0], b[1] - a[1]), math.hypot(d[0] - c[0], d[1] - c[1])
            (p, q), (r, s), Lp = ((a, b), (c, d), La) if La >= Lc else ((c, d), (a, b), Lc)
            if Lp <= 0:
                continue
            ux, uy = (q[0] - p[0]) / Lp, (q[1] - p[1]) / Lp
            t1 = (r[0] - p[0]) * ux + (r[1] - p[1]) * uy
            t2 = (s[0] - p[0]) * ux + (s[1] - p[1]) * uy
            lo, hi = max(0.0, min(t1, t2)), min(Lp, max(t1, t2))
            if hi - lo <= min_len:
                continue
            # jarak tegak lurus di kedua ujung irisan harus <= tol
            ok = True
            for t in (lo, hi):
                pt = (p[0] + ux * t, p[1] + uy * t)
                if _pt_seg(pt, r, s)[0] > tol:
                    ok = False
                    break
            if ok:
                out.append({"panjang": hi - lo, "xy": [(p[0] + ux * lo, p[1] + uy * lo), (p[0] + ux * hi, p[1] + uy * hi)],
                            "i": i, "j": j})
    return out


def merge_overlaps(ovs, join_m=1.0):
    """Gabungkan tumpukan yang bersambung menjadi satu bentangan. -> [dict(panjang, xy, n)] urut panjang menurun."""
    par = list(range(len(ovs)))
    for i in range(len(ovs)):
        for j in range(i + 1, len(ovs)):
            if min(math.hypot(p[0] - q[0], p[1] - q[1]) for p in ovs[i]["xy"] for q in ovs[j]["xy"]) <= join_m:
                _uf_union(par, i, j)
    grp = {}
    for i in range(len(ovs)):
        grp.setdefault(_uf_find(par, i), []).append(i)
    out = []
    for ii in grp.values():
        xy = [p for i in ii for p in ovs[i]["xy"]]
        out.append({"panjang": sum(ovs[i]["panjang"] for i in ii), "xy": ovs[max(ii, key=lambda i: ovs[i]["panjang"])]["xy"],
                    "n": len(ii), "pts": xy})
    out.sort(key=lambda o: -o["panjang"])
    return out


def cut_gaps(xy, supports, tol):
    """Panjang terpanjang tanpa tumpuan pada polyline xy setelah dipotong di titik tumpu (<= tol m dari garis).
    -> (panjang terpanjang, jumlah titik potong, posisi potong)"""
    cum = [0.0]
    for a, b in zip(xy, xy[1:]):
        cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    L = cum[-1]
    cuts = []
    for p in supports:
        best = None
        for i, (a, b) in enumerate(zip(xy, xy[1:])):
            d, t = _pt_seg(p, a, b)
            if d <= tol and (best is None or d < best[0]):
                best = (d, cum[i] + t * (cum[i + 1] - cum[i]))
        if best and 1.0 < best[1] < L - 1.0:
            cuts.append(best[1])
    pos = sorted([0.0, L] + cuts)
    return (max(b - a for a, b in zip(pos, pos[1:])) if L > 0 else 0.0), len(cuts), cuts

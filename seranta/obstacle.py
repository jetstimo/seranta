# -*- coding: utf-8 -*-
"""
Seranta - FTTH Design Assistant
Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later dengan syarat tambahan pasal 7 (lihat LICENSE).

OBSTACLE TIM (3.15.8, masukan pengguna 23 Nov 2026)
--------------------------------------------------
"Bahan KMZ obstacle jadi bahan kajian Seranta: obstacle yang harus reject jika route/cable melintasinya."
Data referensi tim 'Obstacle (Rel KAI, Toll, dll).kmz' (letakkan di folder data referensi; dikenali dari nama
*OBSTACLE* / *RINTANGAN* atau dari isinya) memuat:
  * rel KA AKTIF dan NON AKTIF (Jawa, Sumatera; termasuk tambahan Wikimapia) - garis
  * jalan tol (OSM motorway, tol beroperasi) dan RENCANA tol - garis
  * isu area 'Jalan Plan Penurunan Kabel' - garis (rute kabel udara yang menyusuri/memotong jalan ini ditolak)
  * Kawasan Hutan Lindung, Kawasan Industri, Kawasan Militer - poligon
Stasiun (titik) tidak dipakai. Setiap ruas jalur kabel (antar tiang) yang memotong garis obstacle, menyusuri jalan
penurunan kabel (>= 20 m dalam 10 m), atau masuk/memotong poligon obstacle = temuan JALUR_MELINTAS_OBSTACLE (ERROR,
alasan reject). KMZ obstacle (KML +-100 MB) diurai SEKALI menjadi indeks per petak 0,25 derajat di cache; setiap cluster
hanya membaca petak di sekitarnya.
"""
import json
import math
import os
import re
import time
import zipfile
from xml.etree import ElementTree as ET  # nosec B405 - data referensi tim, dibaca sebagai data (iterparse)

try:
    from . import _log
except ImportError:          # diuji tanpa paket
    import _log

TILE = 0.25
INDEX_VER = 2
BIG_TILES = 4          # fitur yang menyentuh > 4 petak disimpan SEKALI di _besar.json (dulu disalin ke tiap petak: 418 MB)
NAME_RX = re.compile(r"OBSTACLE|RINTANGAN|HAMBATAN", re.IGNORECASE)
LABEL = {"rel_aktif": "rel KA aktif", "rel_nonaktif": "rel KA non aktif", "tol": "jalan tol",
         "tol_rencana": "rencana jalan tol", "isu_kabel": "jalan rencana penurunan kabel",
         "hutan_lindung": "kawasan hutan lindung", "kawasan_industri": "kawasan industri",
         "kawasan_militer": "kawasan militer", "obstacle_lain": "obstacle"}
ALONG_M = 10.0          # jalan penurunan kabel: rute dalam 10 m dari garis jalan ...
ALONG_MIN_M = 20.0      # ... sepanjang >= 20 m = menyusuri jalan itu
MERGE_M = 15.0
_MEMO = {}


def _kind_name(p):
    """Jenis dari SATU nama folder; None bila nama itu tidak menyebut jenis."""
    if "stasiun" in p or "station" in p:
        return "skip"
    if re.search(r"\brel\b|kereta|railway", p):
        return "rel_nonaktif" if re.search(r"non\s*aktif|nonaktif|abandon", p) else "rel_aktif"
    if re.search(r"plan\s*tol|rencana\s*tol|tol+\s*plan", p):
        return "tol_rencana"
    if re.search(r"\btol+\b|motorway", p):
        return "tol"
    if "penurunan kabel" in p or "isu area" in p:
        return "isu_kabel"
    if "hutan" in p:
        return "hutan_lindung"
    if "industri" in p:
        return "kawasan_industri"
    if "militer" in p:
        return "kawasan_militer"
    if re.search(r"non\s*aktif|nonaktif", p):
        return "rel_nonaktif?"
    return None


def kind_of(path):
    """Jenis obstacle dari jalur folder KMZ: folder TERDALAM yang menyebut jenis menentukan; folder induk bernama
    'Obstacle (Rel KAI, Toll, dll)' diabaikan (namanya memuat semua jenis)."""
    hint_nonaktif = False
    for nm in reversed(path):
        p = (nm or "").lower()
        if NAME_RX.search(p) or p.endswith((".kmz", ".kml")):
            continue
        k = _kind_name(p)
        if k == "skip":
            return None
        if k == "rel_nonaktif?":
            hint_nonaktif = True
            continue
        if k:
            return "rel_nonaktif" if (k == "rel_aktif" and hint_nonaktif) else k
    return "obstacle_lain"


def is_obstacle_kmz(path):
    """Nama berkas *OBSTACLE* atau folder di dalamnya bernama rel/tol/kawasan (dicek dari 256 kB awal KML)."""
    if NAME_RX.search(os.path.basename(path)):
        return True
    try:
        with zipfile.ZipFile(path) as z:
            n = next((x for x in z.namelist() if x.lower().endswith(".kml")), None)
            if not n:
                return False
            with z.open(n) as fh:
                head = fh.read(262144).decode("utf-8", "replace").lower()
        return "obstacle" in head or ("rel aktif" in head and ("tol" in head or "kawasan" in head))
    except (OSError, zipfile.BadZipFile):
        return False


def _st(tag):
    return tag.rsplit("}", 1)[-1]


def _coords(txt):
    out = []
    for t in (txt or "").split():
        p = t.split(",")
        if len(p) >= 2:
            try:
                out.append([round(float(p[0]), 6), round(float(p[1]), 6)])
            except ValueError:
                continue
    return out


def _tiles_of(coords):
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    for tx in range(int(math.floor(min(xs) / TILE)), int(math.floor(max(xs) / TILE)) + 1):
        for ty in range(int(math.floor(min(ys) / TILE)), int(math.floor(max(ys) / TILE)) + 1):
            yield "%d_%d" % (tx, ty)


def ensure_index(kmz, cache_dir, feedback=None):
    """Indeks petak obstacle di cache (dibuat sekali per versi berkas). -> folder indeks atau None."""
    st = os.stat(kmz)
    stem = re.sub(r"[^A-Za-z0-9]+", "_", os.path.splitext(os.path.basename(kmz))[0])[:40]
    out = os.path.join(cache_dir, "obstacle", "%s_%d_%d_v%d" % (stem, st.st_size, int(st.st_mtime), INDEX_VER))
    if os.path.exists(os.path.join(out, "indeks.json")):
        return out
    if feedback is not None:
        feedback.pushInfo("Menyiapkan indeks data obstacle %s (%.0f MB) - sekali saja, +-1-2 menit ..."
                          % (os.path.basename(kmz), st.st_size / 1e6))
    tiles, big, n_feat, counts, t0 = {}, [], 0, {}, time.time()
    stack = []
    with zipfile.ZipFile(kmz) as z:
        n = next((x for x in z.namelist() if x.lower() == "doc.kml"), None) or \
            next(x for x in z.namelist() if x.lower().endswith(".kml"))
        with z.open(n) as fh:
            for ev, el in ET.iterparse(fh, events=("start", "end")):  # nosec B314
                t = _st(el.tag)
                if ev == "start" and t in ("Folder", "Document"):
                    stack.append("")
                elif ev == "end" and t == "name" and stack and stack[-1] == "":
                    stack[-1] = (el.text or "").strip() or " "
                elif ev == "end" and t in ("Folder", "Document"):
                    stack.pop()
                    el.clear()
                elif ev == "end" and t == "Placemark":
                    k = kind_of(stack)
                    if k:
                        nm = next(((c.text or "").strip() for c in el if _st(c.tag) == "name"), "")
                        for g in el.iter():
                            gt = _st(g.tag)
                            if gt == "LineString":
                                cs = _coords(next((c.text for c in g.iter() if _st(c.tag) == "coordinates"), ""))
                                typ = "L"
                            elif gt == "Polygon":
                                ob = next((b for b in g.iter() if _st(b.tag) == "outerBoundaryIs"), g)
                                cs = _coords(next((c.text for c in ob.iter() if _st(c.tag) == "coordinates"), ""))
                                typ = "P"
                            else:
                                continue
                            if len(cs) < 2:
                                continue
                            n_feat += 1
                            counts[k] = counts.get(k, 0) + 1
                            rec = [n_feat, k, nm[:60], typ, cs]
                            keys = list(_tiles_of(cs))
                            if len(keys) > BIG_TILES:
                                xs_, ys_ = [q[0] for q in cs], [q[1] for q in cs]
                                big.append(rec + [[min(xs_), min(ys_), max(xs_), max(ys_)]])
                            else:
                                for key in keys:
                                    tiles.setdefault(key, []).append(rec)
                    el.clear()
    tmp = out + ".tmp"
    os.makedirs(tmp, exist_ok=True)
    for key, recs in tiles.items():
        with open(os.path.join(tmp, key + ".json"), "w", encoding="utf-8") as fh:
            json.dump(recs, fh, separators=(",", ":"))
    with open(os.path.join(tmp, "_besar.json"), "w", encoding="utf-8") as fh:
        json.dump(big, fh, separators=(",", ":"))
    with open(os.path.join(tmp, "indeks.json"), "w", encoding="utf-8") as fh:
        json.dump({"sumber": os.path.basename(kmz), "fitur": n_feat, "jenis": counts, "petak": len(tiles),
                   "detik": round(time.time() - t0, 1), "ver": INDEX_VER}, fh)
    if os.path.exists(out):
        import shutil
        shutil.rmtree(out, ignore_errors=True)
    os.replace(tmp, out)
    return out


def query(index_dir, bbox):
    """Fitur obstacle yang petaknya menyentuh bbox (xmin, ymin, xmax, ymax) -> [(id, jenis, nama, tipe, koordinat)]."""
    seen, out = set(), []
    pb = os.path.join(index_dir, "_besar.json")
    if pb not in _MEMO:
        try:
            with open(pb, encoding="utf-8") as fh:
                _MEMO[pb] = json.load(fh)
        except OSError:
            _MEMO[pb] = []
    for r in _MEMO[pb]:
        b = r[5]
        if not (b[2] < bbox[0] or b[0] > bbox[2] or b[3] < bbox[1] or b[1] > bbox[3]):
            seen.add(r[0])
            out.append(r[:5])
    for tx in range(int(math.floor(bbox[0] / TILE)), int(math.floor(bbox[2] / TILE)) + 1):
        for ty in range(int(math.floor(bbox[1] / TILE)), int(math.floor(bbox[3] / TILE)) + 1):
            p = os.path.join(index_dir, "%d_%d.json" % (tx, ty))
            if p not in _MEMO:
                try:
                    with open(p, encoding="utf-8") as fh:
                        _MEMO[p] = json.load(fh)
                except OSError:
                    _MEMO[p] = []
            for r in _MEMO[p]:
                if r[0] not in seen:
                    seen.add(r[0])
                    out.append(r)
    return out


def _seg_x(a, b, c, d):
    r = (b[0] - a[0], b[1] - a[1])
    s = (d[0] - c[0], d[1] - c[1])
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < 1e-12:
        return None
    t = ((c[0] - a[0]) * s[1] - (c[1] - a[1]) * s[0]) / den
    u = ((c[0] - a[0]) * r[1] - (c[1] - a[1]) * r[0]) / den
    if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
        return (a[0] + t * r[0], a[1] + t * r[1])
    return None


def _pt_seg(p, a, b):
    vx, vy = b[0] - a[0], b[1] - a[1]
    L2 = vx * vx + vy * vy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / L2))
    return math.hypot(p[0] - (a[0] + t * vx), p[1] - (a[1] + t * vy))


def _inside(p, ring):
    x, y, ins = p[0], p[1], False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
            ins = not ins
        j = i
    return ins


_GEOM = {}            # id fitur -> (geometri OGR, kotak) selama sesi QGIS


def _geom(fid, typ, cs):
    """Geometri OGR (GEOS, kode C) satu fitur, dibuat sekali per sesi. Poligon hutan lindung bisa ratusan ribu titik:
    menelusurinya dengan Python per cluster memakan menit (uji Tomohon 23 Nov 2026: 472 detik); GEOS milidetik."""
    g = _GEOM.get(fid)
    if g is None:
        from osgeo import ogr
        pts = cs + ([cs[0]] if typ == "P" and cs[0] != cs[-1] else [])
        wkt = ", ".join("%r %r" % (p[0], p[1]) for p in pts)
        geo = ogr.CreateGeometryFromWkt(("POLYGON ((%s))" if typ == "P" else "LINESTRING (%s)") % wkt)
        if geo is not None and typ == "P" and not geo.IsValid():
            fixed = geo.MakeValid() if hasattr(geo, "MakeValid") else None
            geo = fixed if fixed is not None else geo.Buffer(0)
        xs, ys = [p[0] for p in cs], [p[1] for p in cs]
        g = (geo, (min(xs), min(ys), max(xs), max(ys)))
        _GEOM[fid] = g
        if len(_GEOM) > 20000:
            _GEOM.clear()
    return g


def crossings(segs, feats, kx, ky):
    """segs: [(nama_ruas, (lon, lat), (lon, lat))]; feats: dari query(). -> [dict(kind, label, name, lon, lat, seg, mode)]
    Persilangan dihitung dengan GEOS (osgeo.ogr) pada koordinat derajat; jarak 'menyusuri' jalan penurunan kabel dalam
    meter (pendekatan datar lokal kx, ky)."""
    if not segs or not feats:
        return []
    from osgeo import ogr
    hits = []

    def add(fid, k, nm, lon, lat, seg, mode):
        x, y = lon * kx, lat * ky
        for h in hits:
            if h["_fid"] == fid and math.hypot(h["_x"] - x, h["_y"] - y) <= MERGE_M:
                return
        hits.append({"kind": k, "label": LABEL.get(k, k), "name": nm, "lon": lon, "lat": lat, "seg": seg,
                     "mode": mode, "_fid": fid, "_x": x, "_y": y})
    mg = ALONG_M / 111000.0
    for snm, a, b in segs:
        sb = (min(a[0], b[0]) - mg, min(a[1], b[1]) - mg, max(a[0], b[0]) + mg, max(a[1], b[1]) + mg)
        sl = None
        for fid, k, nm, typ, cs in feats:
            geo, fb = _geom(fid, typ, cs)
            if fb[2] < sb[0] or fb[0] > sb[2] or fb[3] < sb[1] or fb[1] > sb[3] or geo is None:
                continue
            if sl is None:
                sl = ogr.CreateGeometryFromWkt("LINESTRING (%r %r, %r %r)" % (a[0], a[1], b[0], b[1]))
            if typ == "P":
                if not geo.Intersects(sl):
                    continue
                pa = ogr.CreateGeometryFromWkt("POINT (%r %r)" % a)
                if geo.Contains(pa):
                    add(fid, k, nm, a[0], a[1], snm, "masuk/memotong kawasan")
                    continue
                cut = sl.Intersection(geo.GetBoundary())
                pts = _points(cut)
                lon, lat = pts[0] if pts else b
                add(fid, k, nm, lon, lat, snm, "masuk/memotong kawasan")
                continue
            crossed = False
            if geo.Intersects(sl):
                for lon, lat in _points(sl.Intersection(geo)):
                    add(fid, k, nm, lon, lat, snm, "memotong")
                    crossed = True
            if k == "isu_kabel" and not crossed:
                A, B = (a[0] * kx, a[1] * ky), (b[0] * kx, b[1] * ky)
                pm = [(p[0] * kx, p[1] * ky) for p in cs]
                L = math.hypot(B[0] - A[0], B[1] - A[1])
                n = max(1, int(L / 5.0))
                near = [i for i in range(n + 1)
                        if min(_pt_seg((A[0] + (B[0] - A[0]) * i / n, A[1] + (B[1] - A[1]) * i / n), c_, d_)
                               for c_, d_ in zip(pm, pm[1:])) <= ALONG_M]
                if near and len(near) * (L / n) >= ALONG_MIN_M:
                    i = near[len(near) // 2]
                    add(fid, k, nm, a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n, snm,
                        "menyusuri +-%.0f m" % (len(near) * L / n))
    return hits


def _points(g):
    """Titik-titik dari hasil Intersection OGR (titik, multititik, garis berimpit -> titik awalnya)."""
    out = []
    if g is None or g.IsEmpty():
        return out
    n = g.GetGeometryCount()
    if n:
        for i in range(n):
            out += _points(g.GetGeometryRef(i))
        return out
    if g.GetPointCount():
        out.append((g.GetX(0), g.GetY(0)))
    return out

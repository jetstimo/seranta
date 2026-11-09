# -*- coding: utf-8 -*-
"""
Seranta - FTTH Design Assistant
Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later dengan syarat tambahan pasal 7 (lihat LICENSE).

PERSILANGAN JALUR KABEL DENGAN JALAN TOL / REL / JALAN BESAR (3.14.1)
---------------------------------------------------------------------
Masukan pengguna: "kalau crossing jalan tol apakah bisa dideteksi?". Peta dasar OpenStreetMap di Seranta hanya gambar
(ubin), tidak bisa dihitung. Modul ini memakai DATA jalan OpenStreetMap (vektor):
  1. file lokal di folder data referensi: *OSM*.geojson / .gpkg / .shp (mis. hasil unduhan plugin QuickOSM, kolom
     highway, toll, railway, name, ref) - dipakai lebih dulu, bekerja tanpa internet;
  2. bila tidak ada: Overpass API (hanya jalan tol/arteri dan rel di kotak wilayah cluster +-300 m), disimpan di cache
     profil QGIS 30 hari. Offline -> cek ditandai 'tidak dicek', QC lain tetap berjalan.
Penggolongan (dokumentasi tag OpenStreetMap, Indonesian Tagging Guidelines): highway=motorway/motorway_link atau
toll=yes -> JALAN TOL; railway=rail/light_rail -> REL KERETA; highway=construction + construction=motorway dan
railway=construction -> ruas yang SEDANG DIBANGUN (akan beroperasi selama umur desain); highway=trunk/primary -> jalan
arteri (nasional/provinsi).
Kelengkapan OSM berbeda per daerah: hasil 'tidak ada persilangan' bukan jaminan; ruas tol baru (mis. JTTS
Betung-Tempino-Jambi yang dibuka bertahap 2024-2026) bisa belum tergambar atau belum bertag toll=yes.

DASAR ATURAN (hanya sumber resmi; teks temuan di buat_input_desain.py):
  * jalan tol : PP 23/2024 tentang Jalan Tol Pasal 71 dan 75 (mencabut PP 15/2005 dan perubahannya; JDIH BPK
                peraturan.bpk.go.id/Details/286315); izin pemanfaatan ruang milik jalan tol oleh Dirjen Bina Marga atas
                rekomendasi teknis BPJT/BUJT, SE Dirjen Bina Marga 11/SE/Db/2017 (sip3rumijatol.binamarga.pu.go.id).
                Permen PU 20/PRT/M/2010 Pasal 3 mengecualikan bagian-bagian jalan tol: angka 5 m TIDAK dipakai untuk tol;
                tidak ada angka ruang bebas resmi khusus tol -> metode & ruang bebas ditetapkan BUJT.
  * rel KA    : PM Perhubungan 36/2011 Pasal 7 (di atas rel: ruang tinggi >= 6,20 m dari kepala rel, ruang sisi >= 10 m
                dari as rel terluar), Pasal 8 (di bawah rel: >= 150 cm di bawah subgrade, mulai >= 10 m dari sisi terluar
                jalur), Pasal 11 (izin Dirjen Perkeretaapian; syarat di portal.djka.kemenhub.go.id/crossing termasuk izin
                prinsip penyelenggara prasarana). Salinan resmi: bphn.go.id/data/documents/11pmhub036.pdf.
  * jalan non-tol : Permen PU 20/PRT/M/2010 Pasal 12 ayat (6) (>= 5 m dari permukaan jalan tertinggi) dan Pasal 5
                (pemberi izin sesuai status jalan); tetap berlaku menurut Ketentuan Peralihan Permen PU 6/2025.
"""
import json
import math
import os
import re
import time

try:
    from . import _log
except ImportError:          # diuji tanpa paket
    import _log

OVERPASS = ("https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter")
CACHE_DAYS = 30
MARGIN_DEG = 0.003           # +-300 m di sekitar jalur
LOCAL_RX = re.compile(r"OSM", re.IGNORECASE)
LOCAL_EXT = (".geojson", ".json", ".gpkg", ".shp")
HW_TOLL = {"motorway", "motorway_link"}
HW_MAJOR = {"trunk", "trunk_link", "primary", "primary_link"}


def classify(tags):
    """'tol' / 'rel' / 'arteri' / None dari tag OSM."""
    t = {str(k).lower(): str(v or "").lower() for k, v in (tags or {}).items()}
    hw, rw, cons = t.get("highway", ""), t.get("railway", ""), t.get("construction", "")
    if hw == "construction" and cons in HW_TOLL:
        return "tol"
    if rw == "construction" and cons in ("rail", "light_rail", ""):
        return "rel"
    if hw in HW_TOLL or (t.get("toll") == "yes" and hw):
        return "tol"
    if rw in ("rail", "light_rail", "subway", "narrow_gauge") and t.get("tunnel", "no") in ("no", ""):
        return "rel"
    if hw in HW_MAJOR:
        return "arteri"
    return None


def _label(tags):
    t = tags or {}
    nm = t.get("name") or t.get("ref") or ""
    return nm if not t.get("ref") or t.get("ref") in nm else ("%s (%s)" % (nm, t.get("ref")) if nm else t.get("ref"))


def parse_overpass(js):
    """JSON Overpass ('out tags geom') -> [dict(kind, name, pts=[(lon, lat)], bridge, tunnel)]"""
    out = []
    for el in (js or {}).get("elements", []):
        if el.get("type") != "way" or not el.get("geometry"):
            continue
        tags = el.get("tags") or {}
        k = classify(tags)
        if not k:
            continue
        out.append({"kind": k, "name": _label(tags), "pts": [(g["lon"], g["lat"]) for g in el["geometry"]],
                    "bridge": tags.get("bridge", "no") not in ("no", ""), "tunnel": tags.get("tunnel", "no") not in ("no", ""),
                    "building": "construction" in (tags.get("highway", ""), tags.get("railway", ""))})
    return out


def find_local(ref_dir):
    if not ref_dir or not os.path.isdir(ref_dir):
        return []
    return sorted(os.path.join(ref_dir, f) for f in os.listdir(ref_dir)
                  if LOCAL_RX.search(f) and f.lower().endswith(LOCAL_EXT) and not f.startswith("~$"))


def load_local(paths, bbox):
    """File OSM lokal (OGR) -> daftar jalan dalam bbox (xmin, ymin, xmax, ymax)."""
    from osgeo import ogr
    out = []
    for p in paths:
        ds = ogr.Open(p)
        if ds is None:
            continue
        for li in range(ds.GetLayerCount()):
            lyr = ds.GetLayer(li)
            lyr.SetSpatialFilterRect(*bbox)
            names = [lyr.GetLayerDefn().GetFieldDefn(i).GetName() for i in range(lyr.GetLayerDefn().GetFieldCount())]
            for f in lyr:
                tags = {n.lower(): f.GetField(n) for n in names if f.GetField(n) is not None}
                if "other_tags" in tags:      # ekspor GDAL OSM: '"toll"=>"yes","ref"=>"..."'
                    tags.update({a.lower(): b for a, b in re.findall(r'"([^"]+)"=>"([^"]*)"', str(tags["other_tags"]))})
                k = classify(tags)
                g = f.GetGeometryRef()
                if not k or g is None:
                    continue
                gs = [g.GetGeometryRef(i) for i in range(g.GetGeometryCount())] if g.GetGeometryCount() and \
                    ogr.GT_Flatten(g.GetGeometryType()) != ogr.wkbLineString else [g]
                for part in gs:
                    pts = [(part.GetX(i), part.GetY(i)) for i in range(part.GetPointCount())]
                    if len(pts) >= 2:
                        out.append({"kind": k, "name": _label(tags), "pts": pts,
                                    "bridge": str(tags.get("bridge", "no")).lower() not in ("no", "", "none"),
                                    "tunnel": str(tags.get("tunnel", "no")).lower() not in ("no", "", "none"),
                                    "building": "construction" in (str(tags.get("highway", "")).lower(),
                                                                   str(tags.get("railway", "")).lower())})
        ds = None
    return out


def _cache_path(cache_dir, bbox):
    key = "_".join("%.3f" % v for v in bbox)
    return os.path.join(cache_dir, "osm_jalan_%s.json" % key.replace("-", "m"))


def fetch(bbox, cache_dir, feedback=None, timeout_s=25):
    """Jalan tol/arteri & rel dari Overpass (dengan cache). -> (daftar jalan, keterangan sumber) atau (None, alasan)."""
    b = (math.floor(bbox[0] / 0.005) * 0.005, math.floor(bbox[1] / 0.005) * 0.005,
         math.ceil(bbox[2] / 0.005) * 0.005, math.ceil(bbox[3] / 0.005) * 0.005)
    cp = _cache_path(cache_dir, b) if cache_dir else None
    if cp and os.path.exists(cp) and time.time() - os.path.getmtime(cp) < CACHE_DAYS * 86400:
        try:
            with open(cp, encoding="utf-8") as fh:
                return parse_overpass(json.load(fh)), "OpenStreetMap (cache %s)" % time.strftime(
                    "%d-%m-%Y", time.localtime(os.path.getmtime(cp)))
        except Exception as e:
            _log.note(e)
    q = ('[out:json][timeout:%d];(way["highway"~"^(motorway|motorway_link|trunk|trunk_link|primary|primary_link)$"]'
         '(%f,%f,%f,%f);way["railway"~"^(rail|light_rail|narrow_gauge)$"](%f,%f,%f,%f);'
         'way["highway"="construction"]["construction"~"^motorway"](%f,%f,%f,%f);'
         'way["railway"="construction"](%f,%f,%f,%f););out tags geom;'
         % ((timeout_s,) + (b[1], b[0], b[3], b[2]) * 4))
    try:
        from qgis.core import QgsBlockingNetworkRequest
        from qgis.PyQt.QtCore import QUrl, QByteArray
        from qgis.PyQt.QtNetwork import QNetworkRequest
    except Exception as e:
        return None, "modul jaringan QGIS tidak tersedia (%s)" % e
    last = ""
    for url in OVERPASS:
        try:
            req = QNetworkRequest(QUrl(url))
            req.setHeader(QNetworkRequest.ContentTypeHeader, "application/x-www-form-urlencoded")
            req.setRawHeader(b"User-Agent", b"Seranta-QGIS-plugin")
            br = QgsBlockingNetworkRequest()
            err = br.post(req, QByteArray(b"data=") + QUrl.toPercentEncoding(q))
            if err != QgsBlockingNetworkRequest.NoError:
                last = br.errorMessage()
                continue
            raw = bytes(br.reply().content())
            js = json.loads(raw.decode("utf-8"))
            if cp:
                try:
                    os.makedirs(cache_dir, exist_ok=True)
                    with open(cp, "w", encoding="utf-8") as fh:
                        json.dump(js, fh)
                except Exception as e:
                    _log.note(e)
            return parse_overpass(js), "OpenStreetMap (Overpass, %s)" % time.strftime("%d-%m-%Y")
        except Exception as e:
            last = str(e)
    return None, "OpenStreetMap tidak terjangkau (offline?): %s" % last[:100]


def _seg_x(a, b, c, d):
    """Titik potong ruas a-b dan c-d (koordinat meter) atau None."""
    r = (b[0] - a[0], b[1] - a[1])
    s = (d[0] - c[0], d[1] - c[1])
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < 1e-12:
        return None
    t = ((c[0] - a[0]) * s[1] - (c[1] - a[1]) * s[0]) / den
    u = ((c[0] - a[0]) * r[1] - (c[1] - a[1]) * r[0]) / den
    if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
        return (a[0] + t * r[0], a[1] + t * r[1]), t
    return None


def crossings(segs, roads, kx, ky, merge_m=15.0):
    """segs: [(nama_ruas, (lon, lat) a, (lon, lat) b)]; roads: dari fetch/load_local.
    -> [dict(kind, name, lon, lat, seg, bridge, tunnel)] satu per titik persilangan (titik berdekatan <= merge_m digabung,
    mis. jalan tol dua jalur atau ruas jalur yang dipecah di titik yang sama)."""
    def m(p):
        return (p[0] * kx, p[1] * ky)
    rs = []
    for r in roads:
        pm = [m(p) for p in r["pts"]]
        xs, ys = [p[0] for p in pm], [p[1] for p in pm]
        rs.append((r, pm, (min(xs), min(ys), max(xs), max(ys))))
    out = []
    for nm, a, b in segs:
        A, B = m(a), m(b)
        bb = (min(A[0], B[0]), min(A[1], B[1]), max(A[0], B[0]), max(A[1], B[1]))
        for r, pm, rb in rs:
            if rb[2] < bb[0] or rb[0] > bb[2] or rb[3] < bb[1] or rb[1] > bb[3]:
                continue
            for c, d in zip(pm, pm[1:]):
                hit = _seg_x(A, B, c, d)
                if hit:
                    (x, y), _t = hit
                    if any(o["kind"] == r["kind"] and math.hypot(o["_x"] - x, o["_y"] - y) <= merge_m for o in out):
                        continue
                    # jarak kedua ujung ruas (tiang) ke garis jalan/rel: PM 36/2011 Pasal 7 ruang sisi >= 10 m
                    dmin = min(_pt_line(A, pm), _pt_line(B, pm))
                    out.append({"kind": r["kind"], "name": r["name"] or "-", "lon": x / kx, "lat": y / ky, "seg": nm,
                                "bridge": r["bridge"], "tunnel": r["tunnel"], "building": r.get("building", False),
                                "d_end": dmin, "_x": x, "_y": y})
    return out


def _pt_line(p, pm):
    best = float("inf")
    for c, d in zip(pm, pm[1:]):
        vx, vy = d[0] - c[0], d[1] - c[1]
        L2 = vx * vx + vy * vy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - c[0]) * vx + (p[1] - c[1]) * vy) / L2))
        best = min(best, math.hypot(p[0] - (c[0] + t * vx), p[1] - (c[1] + t * vy)))
    return best

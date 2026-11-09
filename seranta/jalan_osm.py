# -*- coding: utf-8 -*-
"""
Seranta - FTTH Design Assistant
Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later dengan syarat tambahan pasal 7 (lihat LICENSE).

PERSILANGAN JALUR KABEL DENGAN JALAN TOL / REL / JALAN BESAR / SUNGAI (3.14.1, standar 10 sejak 3.15.0)
---------------------------------------------------------------------
Masukan pengguna: "kalau crossing jalan tol apakah bisa dideteksi?". Peta dasar OpenStreetMap di Seranta hanya gambar
(ubin), tidak bisa dihitung. Modul ini memakai DATA jalan OpenStreetMap (vektor):
  1. file lokal di folder data referensi: *OSM*.geojson / .gpkg / .shp (mis. hasil unduhan plugin QuickOSM, kolom
     highway, toll, railway, name, ref) - dipakai lebih dulu, bekerja tanpa internet;
  2. bila tidak ada: Overpass API (3 server), cadangan API utama OSM 0.6 (/map, kotak cluster +-300 m), disimpan di
     cache profil QGIS 30 hari. Offline -> standar 10 'tidak dicek', QC lain tetap berjalan.
Penggolongan (dokumentasi tag OpenStreetMap, Indonesian Tagging Guidelines): highway=motorway/motorway_link atau
toll=yes -> JALAN TOL; railway=rail/light_rail -> REL KERETA; highway=construction + construction=motorway dan
railway=construction -> ruas yang SEDANG DIBANGUN (akan beroperasi selama umur desain); highway=trunk/primary ATAU
lanes >= 4 / width >= 14 m -> JALAN BESAR; secondary/tertiary -> jalan kolektor; waterway=river/canal -> sungai.
Tingkat temuan & dasar aturan lengkap: DASAR_ATURAN.md bagian "Standar 10".
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

OVERPASS = ("https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
            "https://overpass.private.coffee/api/interpreter")
# 3.15.0: cadangan bila semua server Overpass menolak/sibuk. Uji 10 Nov 2026 dari laptop pengguna: overpass-api.de
# menjawab "406 Not Acceptable", server lain tidak menjawab dalam 40 detik, sehingga di 3.14.1 cek ini SELALU
# 'tidak dicek' (laporan Bitung: "Expecting value: line 1 column 1"). API utama OpenStreetMap (api.openstreetmap.org,
# /api/0.6/map) melayani kotak kecil (<= 0,25 derajat persegi) dan menjawab dalam beberapa detik. Satu permintaan per
# cluster, disimpan di cache 30 hari, sesuai kebijakan pemakaian API OSMF (pemakaian ringan, ada User-Agent).
OSM_API = "https://api.openstreetmap.org/api/0.6/map?bbox=%.6f,%.6f,%.6f,%.6f"
OSM_API_MAX_DEG2 = 0.25
CACHE_DAYS = 30
MARGIN_DEG = 0.003           # +-300 m di sekitar jalur
LOCAL_RX = re.compile(r"OSM", re.IGNORECASE)
LOCAL_EXT = (".geojson", ".json", ".gpkg", ".shp")
HW_TOLL = {"motorway", "motorway_link"}
HW_MAJOR = {"trunk", "trunk_link", "primary", "primary_link"}
HW_MID = {"secondary", "secondary_link", "tertiary", "tertiary_link"}
WW_RIVER = {"river", "canal"}
# Ambang "jalan besar" dari lebar/lajur (PP 34/2006 Pasal 32 ayat 3: jalan raya = minimal 2 lajur per arah @ 3,5 m
# dengan median -> 4 lajur, badan jalan >= 14 m; rumija jalan raya >= 25 m, Pasal 40 ayat 1).
BIG_LANES = 4
BIG_WIDTH_M = 14.0
# Jarak tiang dari jalan tol/rel (bukan persilangan, rute sejajar):
#   tol: setengah lebar rumija minimal jalan bebas hambatan 30 m (PP 34/2006 Pasal 40 ayat 1) = 15 m dari as;
#        OSM menggambar tiap jalur (carriageway) terpisah, maka diukur dari garis jalur terdekat.
#   rel: ruang sisi >= 10 m dari as rel terluar (PM Perhubungan 36/2011 Pasal 7 huruf b); rute sejajar hanya boleh di
#        luar ruang manfaat jalur KA dan masuk ruang milik jalur KA wajib izin (PP 56/2009 Pasal 59 ayat 1, Pasal 82).
NEAR_TOLL_M = 15.0
NEAR_RAIL_M = 10.0
KINDS = ("tol", "rel", "besar", "sedang", "sungai")


def _num(v):
    m = re.search(r"\d+(?:[.,]\d+)?", str(v or ""))
    return float(m.group(0).replace(",", ".")) if m else None


def lanes_of(t):
    n = _num(t.get("lanes"))
    f, b = _num(t.get("lanes:forward")), _num(t.get("lanes:backward"))
    if f is not None and b is not None:
        n = max(n or 0, f + b)
    return n


def classify(tags):
    """'tol' / 'rel' / 'besar' / 'sedang' / 'sungai' / None dari tag OSM.
    besar  = jalan nasional/arteri (trunk/primary) ATAU jalan yang lebarnya terbaca >= 4 lajur / >= 14 m;
    sedang = secondary/tertiary (kolektor/jalan provinsi-kabupaten utama) yang tidak memenuhi ambang besar."""
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
    if hw == "construction" and cons in HW_MAJOR:
        return "besar"
    if hw and hw not in ("footway", "path", "steps", "cycleway", "pedestrian", "track", "bridleway", "proposed"):
        ln, wd = lanes_of(t), _num(t.get("width"))
        if hw in HW_MAJOR or (ln is not None and ln >= BIG_LANES) or (wd is not None and wd >= BIG_WIDTH_M):
            return "besar"
        if hw in HW_MID:
            return "sedang"
        return None
    if t.get("waterway", "") in WW_RIVER and t.get("tunnel", "no") in ("no", ""):
        return "sungai"
    return None


def _label(tags):
    t = tags or {}
    nm = t.get("name") or t.get("ref") or ""
    return nm if not t.get("ref") or t.get("ref") in nm else ("%s (%s)" % (nm, t.get("ref")) if nm else t.get("ref"))


def _flag(tags, k):
    return str((tags or {}).get(k, "no") or "no").lower() not in ("no", "", "none", "0")


def _road(tags, pts):
    k = classify(tags)
    if not k or len(pts) < 2:
        return None
    t = tags or {}
    return {"kind": k, "name": _label(t), "pts": pts, "bridge": _flag(t, "bridge"), "tunnel": _flag(t, "tunnel"),
            "building": "construction" in (str(t.get("highway", "")).lower(), str(t.get("railway", "")).lower()),
            "hw": str(t.get("highway", "") or t.get("railway", "") or t.get("waterway", "")).lower(),
            "lanes": lanes_of({str(a).lower(): b for a, b in t.items()}), "width": _num(t.get("width"))}


def parse_overpass(js):
    """JSON Overpass ('out tags geom') -> [dict(kind, name, pts=[(lon, lat)], bridge, tunnel, building, hw, lanes, width)]"""
    out = []
    for el in (js or {}).get("elements", []):
        if el.get("type") != "way" or not el.get("geometry"):
            continue
        r = _road(el.get("tags") or {}, [(g["lon"], g["lat"]) for g in el["geometry"] if g])
        if r:
            out.append(r)
    return out


_ATTR_RX = re.compile(r'([A-Za-z_:]+)\s*=\s*("([^"]*)"|\'([^\']*)\')')
_EL_RX = re.compile(r"<(node|way)\b([^>]*?)(/>|>(.*?)</\1>)", re.S)
_ND_RX = re.compile(r"<nd\b([^>]*)/?>")
_TAG_RX = re.compile(r"<tag\b([^>]*)/?>")


def _attrs(s):
    import html
    return {m.group(1): html.unescape(m.group(3) if m.group(3) is not None else m.group(4)) for m in _ATTR_RX.finditer(s)}


def osm_xml_to_overpass(raw):
    """Jawaban XML API OSM 0.6 (/map) -> bentuk JSON Overpass {'elements': [way + geometry]} (hanya way bertag
    highway/railway/waterway) agar diproses & di-cache dengan cara yang sama. Dibaca dengan pola teks sederhana (format
    OSM 0.6 tetap: node/way/nd/tag), tanpa pengurai XML umum (tidak ada entitas eksternal yang diproses)."""
    txt = raw.decode("utf-8", "replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
    nodes, els = {}, []
    for m in _EL_RX.finditer(txt):
        at = _attrs(m.group(2))
        if m.group(1) == "node":
            try:
                nodes[at.get("id")] = (float(at["lon"]), float(at["lat"]))
            except (KeyError, ValueError):
                pass
            continue
        body = m.group(4) or ""
        tags = {}
        for t in _TAG_RX.finditer(body):
            ta = _attrs(t.group(1))
            if "k" in ta:
                tags[ta["k"]] = ta.get("v", "")
        if not any(k in tags for k in ("highway", "railway", "waterway")):
            continue
        refs = [_attrs(n.group(1)).get("ref") for n in _ND_RX.finditer(body)]
        geom = [{"lon": nodes[r][0], "lat": nodes[r][1]} for r in refs if r in nodes]
        if len(geom) >= 2:
            els.append({"type": "way", "id": int(at.get("id", "0") or 0), "tags": tags, "geometry": geom})
    return {"elements": els, "generator": "api.openstreetmap.org/0.6"}


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
                g = f.GetGeometryRef()
                if g is None or not classify(tags):
                    continue
                gs = [g.GetGeometryRef(i) for i in range(g.GetGeometryCount())] if g.GetGeometryCount() and \
                    ogr.GT_Flatten(g.GetGeometryType()) != ogr.wkbLineString else [g]
                for part in gs:
                    r = _road(tags, [(part.GetX(i), part.GetY(i)) for i in range(part.GetPointCount())])
                    if r:
                        out.append(r)
        ds = None
    return out


def _cache_path(cache_dir, bbox):
    key = "_".join("%.3f" % v for v in bbox)
    return os.path.join(cache_dir, "osm_jalan_%s.json" % key.replace("-", "m"))


def _http(url, post=None, feedback=None):
    """Permintaan HTTP lewat jaringan QGIS (ikut setelan proxy QGIS). -> (kode_status, bytes) atau (None, pesan galat)."""
    from qgis.core import QgsBlockingNetworkRequest
    from qgis.PyQt.QtCore import QUrl, QByteArray
    from qgis.PyQt.QtNetwork import QNetworkRequest
    req = QNetworkRequest(QUrl(url))
    req.setRawHeader(b"User-Agent", b"Seranta-QGIS-plugin (FTTH survey QC; github.com/jetstimo/seranta)")
    req.setRawHeader(b"Accept", b"application/json, application/xml, text/xml, */*")
    br = QgsBlockingNetworkRequest()
    if post is not None:
        req.setHeader(QNetworkRequest.ContentTypeHeader, "application/x-www-form-urlencoded")
        err = br.post(req, QByteArray(post), True, feedback)
    else:
        err = br.get(req, True, feedback)
    rep = br.reply()
    try:
        code = rep.attribute(QNetworkRequest.HttpStatusCodeAttribute)
    except Exception:
        code = None
    raw = bytes(rep.content()) if rep is not None else b""
    if err != QgsBlockingNetworkRequest.NoError and not raw:
        return None, (br.errorMessage() or "galat jaringan")[:120]
    return (int(code) if code else (200 if err == QgsBlockingNetworkRequest.NoError else 0)), raw


def overpass_query(b, timeout_s=25):
    """Kueri Overpass: jalan tol, jalan nasional/provinsi/kolektor (+ lebar/lajur), rel, sungai/kanal di kotak b."""
    box = "(%f,%f,%f,%f)" % (b[1], b[0], b[3], b[2])
    return ('[out:json][timeout:%d];('
            'way["highway"~"^(motorway|motorway_link|trunk|trunk_link|primary|primary_link|secondary|secondary_link|'
            'tertiary|tertiary_link)$"]%s;way["highway"]["lanes"]%s;way["highway"]["width"]%s;'
            'way["railway"~"^(rail|light_rail|narrow_gauge|construction)$"]%s;'
            'way["highway"="construction"]%s;way["waterway"~"^(river|canal)$"]%s;);out tags geom;'
            % ((timeout_s,) + (box,) * 6))


def fetch(bbox, cache_dir, feedback=None, timeout_s=25):
    """Jalan/rel/sungai di kotak bbox dari OpenStreetMap (Overpass, cadangan API OSM 0.6; dengan cache).
    -> (daftar jalan, keterangan sumber) atau (None, alasan)."""
    b = (math.floor(bbox[0] / 0.005) * 0.005, math.floor(bbox[1] / 0.005) * 0.005,
         math.ceil(bbox[2] / 0.005) * 0.005, math.ceil(bbox[3] / 0.005) * 0.005)
    cp = _cache_path(cache_dir, b) if cache_dir else None
    if cp and os.path.exists(cp) and time.time() - os.path.getmtime(cp) < CACHE_DAYS * 86400:
        try:
            with open(cp, encoding="utf-8") as fh:
                js = json.load(fh)
            if js.get("seranta_v", 0) >= 2:
                return parse_overpass(js), "OpenStreetMap (cache %s)" % time.strftime(
                    "%d-%m-%Y", time.localtime(os.path.getmtime(cp)))
        except Exception as e:
            _log.note(e)
    try:
        from qgis.PyQt.QtCore import QUrl
    except Exception as e:
        return None, "modul jaringan QGIS tidak tersedia (%s)" % e
    q = overpass_query(b, timeout_s)
    tried, js, src = [], None, None
    for url in OVERPASS:
        try:
            code, raw = _http(url, b"data=" + bytes(QUrl.toPercentEncoding(q)), feedback)
            if code is None or code != 200 or not raw.lstrip().startswith(b"{"):
                tried.append("%s: %s" % (url.split("/")[2], raw if code is None else "HTTP %s" % code))
                continue
            js = json.loads(raw.decode("utf-8"))
            if "remark" in js and not js.get("elements") and "error" in str(js.get("remark", "")).lower():
                tried.append("%s: %s" % (url.split("/")[2], str(js["remark"])[:60]))
                js = None
                continue
            src = "OpenStreetMap (Overpass %s, %s)" % (url.split("/")[2], time.strftime("%d-%m-%Y"))
            break
        except Exception as e:
            tried.append("%s: %s" % (url.split("/")[2], str(e)[:60]))
        if feedback is not None and feedback.isCanceled():
            return None, "dibatalkan"
    if js is None and (b[2] - b[0]) * (b[3] - b[1]) <= OSM_API_MAX_DEG2:
        try:
            code, raw = _http(OSM_API % b, None, feedback)
            if code == 200 and raw.lstrip().startswith(b"<"):
                js = osm_xml_to_overpass(raw)
                src = "OpenStreetMap (API 0.6, %s)" % time.strftime("%d-%m-%Y")
            else:
                tried.append("api.openstreetmap.org: %s" % (raw if code is None else "HTTP %s" % code))
        except Exception as e:
            tried.append("api.openstreetmap.org: %s" % str(e)[:60])
    if js is None:
        return None, "OpenStreetMap tidak terjangkau (offline/server sibuk): %s" % "; ".join(
            str(t) for t in tried)[:220]
    js["seranta_v"] = 2
    if cp:
        try:
            os.makedirs(cache_dir, exist_ok=True)
            with open(cp, "w", encoding="utf-8") as fh:
                json.dump(js, fh)
        except Exception as e:
            _log.note(e)
    return parse_overpass(js), src


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


PARALLEL_DEG = 25.0     # jalan biasa/sungai: perpotongan bersudut < 25 deg = jalur menyusuri jalan (melewati garis as
#                         jalan bolak-balik), bukan menyeberang. Jalan tol & rel tetap dihitung pada sudut berapa pun.


def _angle(a, b, c, d):
    v1 = (b[0] - a[0], b[1] - a[1])
    v2 = (d[0] - c[0], d[1] - c[1])
    n1, n2 = math.hypot(*v1), math.hypot(*v2)
    if n1 == 0 or n2 == 0:
        return 90.0
    cs = abs(v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)
    return math.degrees(math.acos(min(1.0, cs)))


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
                if hit and r["kind"] not in ("tol", "rel") and _angle(A, B, c, d) < PARALLEL_DEG:
                    continue
                if hit:
                    (x, y), _t = hit
                    if any(o["kind"] == r["kind"] and math.hypot(o["_x"] - x, o["_y"] - y) <= merge_m for o in out):
                        continue
                    # jarak kedua ujung ruas (tiang) ke garis jalan/rel: PM 36/2011 Pasal 7 ruang sisi >= 10 m
                    dmin = min(_pt_line(A, pm), _pt_line(B, pm))
                    out.append({"kind": r["kind"], "name": r["name"] or "-", "lon": x / kx, "lat": y / ky, "seg": nm,
                                "bridge": r["bridge"], "tunnel": r["tunnel"], "building": r.get("building", False),
                                "hw": r.get("hw", ""), "lanes": r.get("lanes"), "width": r.get("width"),
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


def near_poles(poles, roads, kx, ky, crossed=()):
    """Tiang yang terlalu dekat jalan tol (< NEAR_TOLL_M) atau rel (< NEAR_RAIL_M) walau rentangnya TIDAK memotong
    (rute sejajar di ruang milik jalan tol / jalur KA). poles: [(nama, (lon, lat))]; crossed: nama tiang yang sudah
    dilaporkan di temuan persilangan (tidak diulang). -> [dict(kind, name, pole, lon, lat, d)]"""
    lim = {"tol": NEAR_TOLL_M, "rel": NEAR_RAIL_M}
    rs = []
    for r in roads:
        if r["kind"] not in lim or r.get("tunnel"):
            continue
        pm = [(p[0] * kx, p[1] * ky) for p in r["pts"]]
        xs, ys = [p[0] for p in pm], [p[1] for p in pm]
        rs.append((r, pm, (min(xs), min(ys), max(xs), max(ys))))
    out = []
    for nm, p in poles:
        if nm in crossed:
            continue
        P = (p[0] * kx, p[1] * ky)
        best = None
        for r, pm, bb in rs:
            L = lim[r["kind"]]
            if P[0] < bb[0] - L or P[0] > bb[2] + L or P[1] < bb[1] - L or P[1] > bb[3] + L:
                continue
            d = _pt_line(P, pm)
            if d < L and (best is None or d < best[1]):
                best = (r, d)
        if best:
            out.append({"kind": best[0]["kind"], "name": best[0]["name"] or "-", "pole": nm, "lon": p[0], "lat": p[1],
                        "d": best[1]})
    return out

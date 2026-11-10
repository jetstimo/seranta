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
     ATAU ekstrak Geofabrik *.osm.pbf (download.geofabrik.de/asia/indonesia.html, per pulau): diubah SEKALI menjadi
     paket GeoPackage ringkas di cache (hanya jalan tol/besar/kolektor, rel, sungai), lalu dibaca seketika;
  2. bila tidak ada: server Overpass publik (berurutan, sesuai kebijakan pemakaian), disimpan di cache profil QGIS
     30 hari. Offline/server menolak -> cache lama atau standar 10 'tidak dicek', QC lain tetap berjalan.
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

# Server Overpass publik, dicoba BERURUTAN (tiga operator berbeda; daftar resmi: wiki.openstreetmap.org/wiki/Overpass_API,
# "Public Overpass API instances"). overpass.kumi.systems tidak dipakai: itu nama lama overpass.private.coffee.
# Kepatuhan kebijakan (kajian 10 Nov 2026, sumber resmi):
#   * tidak ada permintaan paralel ("No parallel running of multiple scripts"), satu kueri kecil per wilayah, hasil
#     di-cache 30 hari ("Cache and rate-limit calls, use extracts if you need a lot of data");
#   * User-Agent yang mengidentifikasi aplikasi; jawaban 429/406 -> server diistirahatkan (wiki: jeda >= 30 detik);
#   * API penyuntingan api.openstreetmap.org (/api/0.6/map) TIDAK dipakai: OSMF API Usage Policy menyatakan API itu
#     "not for read-only purposes or projects" (operations.osmfoundation.org/policies/api/);
#   * pemakaian banyak/rutin -> paket data lokal dari ekstrak Geofabrik (lihat PAKET DATA JALAN LOKAL di bawah).
OVERPASS = ("https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter",
            "https://maps.mail.ru/osm/tools/overpass/api/interpreter")
ATTRIBUTION = "(c) OpenStreetMap contributors, ODbL - openstreetmap.org/copyright"
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
    f = _num(t.get("lanes:forward") or t.get("lanes_forward"))
    b = _num(t.get("lanes:backward") or t.get("lanes_backward"))
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


HW_PBF = ("'motorway','motorway_link','trunk','trunk_link','primary','primary_link','secondary','secondary_link',"
          "'tertiary','tertiary_link','construction'")


def pbf_where(fields):
    """Saringan layer 'lines' driver OSM GDAL. Kunci yang punya kolom sendiri (bergantung osmconf.ini versi GDAL: highway,
    waterway, kadang railway) disaring lewat kolomnya; kunci lain ada di kolom other_tags ('"kunci"=>"nilai"')."""
    f = {x.lower() for x in fields}
    w = []
    if "highway" in f:
        w.append("highway IN (%s)" % HW_PBF)
    if "waterway" in f:
        w.append("waterway IN ('river','canal')")
    for k in ("railway", "toll", "lanes", "width"):
        if k in f:
            w.append("%s IS NOT NULL" % k)
        elif "other_tags" in f:
            w.append("other_tags LIKE '%%\"%s\"=>%%'" % k)
    return " OR ".join(w)


def find_pbf(ref_dir):
    if not ref_dir or not os.path.isdir(ref_dir):
        return []
    return sorted(os.path.join(ref_dir, f) for f in os.listdir(ref_dir) if f.lower().endswith(".osm.pbf"))


def pbf_package(pbf, cache_dir, feedback=None):
    """PAKET DATA JALAN LOKAL: ekstrak OSM .osm.pbf (mis. Geofabrik sulawesi-latest.osm.pbf) -> GeoPackage ringkas di
    cache (sekali; diulang hanya bila berkas .pbf berganti). Driver OSM GDAL tidak cocok dibaca langsung berulang-ulang
    untuk berkas besar (dokumentasi GDAL: impor dulu ke GeoPackage). -> path .gpkg atau None bila gagal."""
    from osgeo import gdal
    st = os.stat(pbf)
    stem = re.sub(r"[^A-Za-z0-9]+", "_", os.path.basename(pbf))[:40]
    out = os.path.join(cache_dir, "osm_paket_%s_%d_%d.gpkg" % (stem, st.st_size, int(st.st_mtime)))
    if os.path.exists(out) and os.path.getsize(out) > 0:
        return out
    os.makedirs(cache_dir, exist_ok=True)
    if feedback is not None:
        feedback.pushInfo("Menyiapkan paket data jalan lokal dari %s (%.0f MB) - sekali saja, bisa beberapa menit ..."
                          % (os.path.basename(pbf), st.st_size / 1e6))
    tmp = out + ".tmp.gpkg"
    try:
        if os.path.exists(tmp):
            os.remove(tmp)
        gdal.SetConfigOption("OSM_MAX_TMPFILE_SIZE", "1024")
        src = gdal.OpenEx(pbf, gdal.OF_VECTOR)
        lyr = src.GetLayerByName("lines") if src is not None else None
        if lyr is None:
            return None
        defn = lyr.GetLayerDefn()
        where = pbf_where([defn.GetFieldDefn(i).GetName() for i in range(defn.GetFieldCount())])
        src = None
        ds = gdal.VectorTranslate(tmp, pbf, format="GPKG", layers=["lines"], where=where, layerName="jalan_osm",
                                  layerCreationOptions=["SPATIAL_INDEX=YES"])
        if ds is None:
            return None
        ds = None
        os.replace(tmp, out)
        return out
    except Exception as e:
        _log.note(e)
        return None


# ---- 3.15.0: PAKET DATA JALAN SERANTA (sumber utama, cepat) ------------------------------------------------------
# Server Overpass publik sering sibuk/menolak (uji lapangan 10 Nov 2026: 2 dari 6 cluster 'tidak dicek'). Paket ini dibuat
# bulanan oleh alur kerja GitHub 'data-jalan' dari ekstrak Geofabrik per pulau (jalan tol, nasional/provinsi/kolektor,
# rel, sungai/kanal saja), diunduh SEKALI per pulau ke cache lalu dibaca seketika tanpa internet. Sesuai anjuran
# kebijakan Overpass ("use extracts if you need a lot of data"). Data (c) OpenStreetMap contributors, ODbL.
PKG_BASE = "https://github.com/jetstimo/seranta/releases/download/data-jalan/"
PKG_INDEX_DAYS = 7          # indeks dicek ulang paling sering seminggu sekali
PKG_REQ_TIMEOUT_MS = 20000  # tanpa byte selama 20 detik -> batal


def _pkg_dir(cache_dir):
    return os.path.join(cache_dir, "paket_jalan")


def _pkg_index(cache_dir, feedback=None):
    """indeks.json paket (dari cache; diperbarui dari GitHub bila lebih tua dari PKG_INDEX_DAYS). -> dict atau None."""
    d = _pkg_dir(cache_dir)
    p = os.path.join(d, "indeks.json")
    old = None
    try:
        with open(p, encoding="utf-8") as fh:
            old = json.load(fh)
        if time.time() - os.path.getmtime(p) < PKG_INDEX_DAYS * 86400:
            return old
    except Exception:
        old = None
    st = _state(cache_dir)
    if time.time() < st["rest"].get("paket", 0):
        return old
    try:
        code, raw = _http(PKG_BASE + "indeks.json", None, feedback, 10000)
        if code == 200 and raw.lstrip().startswith(b"{"):
            js = json.loads(raw.decode("utf-8"))
            if js.get("paket"):
                os.makedirs(d, exist_ok=True)
                with open(p, "w", encoding="utf-8") as fh:
                    json.dump(js, fh)
                return js
    except Exception as e:
        _log.note(e)
    _state(cache_dir, lambda s_: s_["rest"].__setitem__("paket", time.time() + REST_BUSY_S))
    return old


def _pkg_hit(item, bbox):
    b = item.get("bbox") or [0, 0, 0, 0]
    if b[2] < bbox[0] or b[0] > bbox[2] or b[3] < bbox[1] or b[1] > bbox[3]:
        return False
    cells = item.get("sel")
    if not cells:
        return True
    want = {"%d_%d" % (x, y) for x in range(int(math.floor(bbox[0])), int(math.floor(bbox[2])) + 1)
            for y in range(int(math.floor(bbox[1])), int(math.floor(bbox[3])) + 1)}
    return bool(want & set(cells))


def package(bbox, cache_dir, feedback=None):
    """Berkas paket data jalan (GeoPackage per pulau) yang mencakup bbox; diunduh bila belum ada / ada versi baru.
    -> ([path], keterangan) ; daftar kosong bila paket belum bisa dipakai (offline dan belum pernah diunduh)."""
    import hashlib
    if not cache_dir:
        return [], ""
    idx = _pkg_index(cache_dir, feedback)
    if not idx:
        return [], ""
    d = _pkg_dir(cache_dir)
    out = []
    for it in idx.get("paket", []):
        if not _pkg_hit(it, bbox):
            continue
        fn = os.path.basename(str(it.get("file", "")))
        if not fn.endswith(".gpkg"):
            continue
        p = os.path.join(d, fn)
        mark = p + ".sha256"
        have = None
        try:
            with open(mark, encoding="utf-8") as fh:
                have = fh.read().strip()
        except Exception:
            have = None
        if os.path.exists(p) and have == it.get("sha256"):
            out.append(p)
            continue
        if time.time() < _state(cache_dir)["rest"].get("paket", 0):
            if os.path.exists(p):
                out.append(p)       # versi lama masih dipakai
            continue
        if feedback is not None:
            feedback.pushInfo("Mengunduh paket data jalan %s (%.0f MB) - sekali saja, lalu dipakai tanpa internet ..."
                              % (fn, (it.get("bytes") or 0) / 1e6))
        ok = False
        try:
            code, raw = _http(PKG_BASE + fn, None, feedback, PKG_REQ_TIMEOUT_MS)
            if code == 200 and raw and hashlib.sha256(raw).hexdigest() == it.get("sha256"):
                os.makedirs(d, exist_ok=True)
                with open(p + ".part", "wb") as fh:
                    fh.write(raw)
                os.replace(p + ".part", p)
                with open(mark, "w", encoding="utf-8") as fh:
                    fh.write(it.get("sha256"))
                ok = True
        except Exception as e:
            _log.note(e)
        if ok or os.path.exists(p):
            out.append(p)
        if not ok:
            _state(cache_dir, lambda s_: s_["rest"].__setitem__("paket", time.time() + REST_BUSY_S))
    return out, "paket data jalan Seranta %s (data per %s; %s)" % (
        ", ".join(os.path.basename(x) for x in out), idx.get("dibuat", "?"), ATTRIBUTION)


def find_local(ref_dir, cache_dir=None, feedback=None):
    """Data jalan lokal di folder data referensi: *OSM*.geojson/.gpkg/.shp, dan paket dari ekstrak *.osm.pbf."""
    if not ref_dir or not os.path.isdir(ref_dir):
        return []
    out = sorted(os.path.join(ref_dir, f) for f in os.listdir(ref_dir)
                 if LOCAL_RX.search(f) and f.lower().endswith(LOCAL_EXT) and not f.startswith("~$"))
    if cache_dir:
        for p in find_pbf(ref_dir):
            g = pbf_package(p, cache_dir, feedback)
            if g:
                out.append(g)
    return out


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


# ---- 3.15.0: kecepatan ------------------------------------------------------------------------------------------
# Sebelumnya tiap server ditunggu sampai batas bawaan QGIS (60 detik) pada SETIAP cluster. Sekarang:
#   1. hasil diingat di memori selama sesi QGIS dan di cache disk 30 hari; cache dipakai bila kotaknya MENCAKUP wilayah
#      cluster, dan kotak unduhan dibulatkan ke petak 0,01 derajat (+-1,1 km) sehingga cluster bertetangga dalam satu
#      batch memakai unduhan yang sama;
#   2. server dicoba berurutan mulai dari yang terakhir berhasil; tiap server dibatasi SERVER_LIMIT_S (server Overpass
#      bisa mengantrekan kueri sampai 15 detik sebelum menjalankannya), seluruh percobaan TOTAL_LIMIT_S;
#   3. pemutus sirkuit: server yang menolak (406/429) diistirahatkan REST_BLOCK_S, yang sibuk/diam (504/timeout)
#      REST_BUSY_S, disimpan di cache sehingga cluster & sesi berikutnya langsung melewatinya;
#   4. semua server gagal -> cache kedaluwarsa dipakai (diberi tanggal), dan kegagalan diingat FAIL_MEMO_S (di memori
#      dan di cache, jadi berlaku juga setelah QGIS dibuka ulang) sehingga batch tidak menunggu di setiap cluster.
GRID_DEG = 0.01
REQ_TIMEOUT_MS = 15000
SERVER_LIMIT_S = 20.0      # antrean server Overpass <= 15 detik + waktu kueri kecil
TOTAL_LIMIT_S = 35.0       # batas seluruh percobaan untuk satu cluster
REST_BLOCK_S = 6 * 3600
REST_BUSY_S = 1800
FAIL_MEMO_S = 1800
_MEMO = {}            # kotak -> (waktu, js, sumber)
_FAIL = {"t": 0.0, "why": ""}
_JOBS = []
_CACHE_RX = re.compile(r"^osm_jalan_(m?[\d.]+)_(m?[\d.]+)_(m?[\d.]+)_(m?[\d.]+)\.json$")


def _cache_path(cache_dir, bbox):
    key = "_".join("%.3f" % v for v in bbox)
    return os.path.join(cache_dir, "osm_jalan_%s.json" % key.replace("-", "m"))


def _covers(big, small):
    return big[0] <= small[0] + 1e-9 and big[1] <= small[1] + 1e-9 and big[2] >= small[2] - 1e-9 and big[3] >= small[3] - 1e-9


def _cache_find(cache_dir, bbox, stale=False):
    """Berkas cache yang kotaknya mencakup bbox -> (js, waktu_berkas, kotak) atau None. stale=True: juga yang sudah
    lewat CACHE_DAYS (dipakai hanya bila semua server gagal)."""
    if not cache_dir or not os.path.isdir(cache_dir):
        return None
    now = time.time()
    for fn in os.listdir(cache_dir):
        m = _CACHE_RX.match(fn)
        if not m:
            continue
        try:
            box = tuple(float(g.replace("m", "-")) for g in m.groups())
        except ValueError:
            continue
        p = os.path.join(cache_dir, fn)
        if not _covers(box, bbox) or (not stale and now - os.path.getmtime(p) >= CACHE_DAYS * 86400):
            continue
        try:
            with open(p, encoding="utf-8") as fh:
                js = json.load(fh)
            if js.get("seranta_v", 0) >= 2:
                return js, os.path.getmtime(p), box
        except Exception as e:
            _log.note(e)
    return None


def _clip(roads, bbox):
    """Hanya jalan yang kotaknya menyentuh bbox (cache bisa lebih luas dari wilayah cluster)."""
    out = []
    for r in roads:
        xs = [p[0] for p in r["pts"]]
        ys = [p[1] for p in r["pts"]]
        if max(xs) >= bbox[0] and min(xs) <= bbox[2] and max(ys) >= bbox[1] and min(ys) <= bbox[3]:
            out.append(r)
    return out


def _state(cache_dir, update=None):
    """Keadaan server di cache: {'good': host terakhir berhasil, 'rest': {host: istirahat_sampai}}."""
    st = {"good": None, "rest": {}, "fail_t": 0.0, "fail_why": ""}
    if not cache_dir:
        return st
    p = os.path.join(cache_dir, "osm_server.json")
    try:
        with open(p, encoding="utf-8") as fh:
            got = json.load(fh)
        st["good"] = got.get("good")
        st["rest"] = {k: float(v) for k, v in (got.get("rest") or {}).items() if float(v) > time.time()}
        st["fail_t"], st["fail_why"] = float(got.get("fail_t") or 0), str(got.get("fail_why") or "")
    except Exception:
        pass
    if update:
        update(st)
        try:
            os.makedirs(cache_dir, exist_ok=True)
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(st, fh)
        except Exception as e:
            _log.note(e)
    return st


def _user_agent():
    try:
        from .buat_input_desain import __version__ as v
    except Exception:
        v = "3"
    return ("Seranta/%s (QGIS plugin, FTTH survey QC; https://github.com/jetstimo/seranta)" % v).encode("ascii", "replace")


def _http(url, post=None, feedback=None, timeout_ms=REQ_TIMEOUT_MS):
    """Permintaan HTTP lewat jaringan QGIS (ikut setelan proxy QGIS). -> (kode_status, bytes) atau (None, pesan galat)."""
    from qgis.core import QgsBlockingNetworkRequest
    from qgis.PyQt.QtCore import QUrl, QByteArray
    from qgis.PyQt.QtNetwork import QNetworkRequest
    req = QNetworkRequest(QUrl(url))
    # QGIS menimpa User-Agent dengan "Mozilla/5.0 QGIS/<versi>" (QgsNetworkAccessManager), jadi aplikasi diidentifikasi
    # juga lewat Referer - kebijakan Overpass menerima "User-Agent or Referer headers that uniquely identify your app".
    req.setRawHeader(b"User-Agent", _user_agent())
    req.setRawHeader(b"Referer", b"https://github.com/jetstimo/seranta")
    req.setRawHeader(b"Accept", b"application/json, */*")
    try:
        req.setTransferTimeout(int(timeout_ms))      # Qt >= 5.15: batalkan bila server diam
    except Exception as e:
        _log.note(e)
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


def _ask(url, body):
    """Satu server Overpass -> (js, None, None) atau (None, alasan, jenis); jenis: 'block' (406/429/403: klien ditolak)
    atau 'busy' (504/timeout/galat lain)."""
    host = url.split("/")[2]
    try:
        code, raw = _http(url, body, None)
        if code is None or not raw:
            return None, "%s: %s" % (host, raw if code is None else "tidak menjawab"), "busy"
        if code in (403, 406, 429):
            return None, "%s: HTTP %s (permintaan ditolak/terlalu sering)" % (host, code), "block"
        if code != 200 or not raw.lstrip().startswith(b"{"):
            return None, "%s: HTTP %s" % (host, code), "busy"
        js = json.loads(raw.decode("utf-8"))
        # Overpass bisa membatalkan kueri dengan HTTP 200 + 'remark: runtime error ...' (waktu/memori habis)
        if "remark" in js and "error" in str(js.get("remark", "")).lower():
            return None, "%s: %s" % (host, str(js["remark"])[:60]), "busy"
        return js, None, None
    except Exception as e:
        return None, "%s: %s" % (host, str(e)[:60]), "busy"


def _one(url, body, feedback=None, limit_s=SERVER_LIMIT_S):
    """Jalankan _ask di thread Qt dengan batas SERVER_LIMIT_S (QGIS tetap bisa dibatalkan)."""
    import queue
    from qgis.PyQt.QtCore import QThread
    q = queue.Queue()

    class _Job(QThread):          # QThread (bukan thread Python biasa): pewaktu jaringan Qt butuh thread Qt
        def run(self):
            q.put(_ask(url, body))
    j = _Job()
    _JOBS[:] = [o for o in _JOBS if o.isRunning()] + [j]     # simpan acuan sampai thread selesai
    j.start()
    t0 = time.time()
    while time.time() - t0 < limit_s:
        if feedback is not None and feedback.isCanceled():
            return None, "dibatalkan", "cancel"
        try:
            return q.get(timeout=0.2)
        except queue.Empty:
            continue
    return None, "%s: tidak menjawab dalam %.0f detik" % (url.split("/")[2], limit_s), "busy"


def overpass_query(b, timeout_s=25):
    """Kueri Overpass ringkas: [bbox] global, [timeout]/[maxsize] kecil (lebih mudah diterima server sibuk), satu regex
    ber-jangkar per kunci, 'out tags geom qt' (koordinat langsung di tiap way, tanpa rekursi node, tanpa pengurutan).
    Jalan tol, nasional/provinsi/kolektor (+ yang bertag lanes/width), rel, sungai/kanal di kotak b."""
    return ('[out:json][timeout:%d][maxsize:67108864][bbox:%f,%f,%f,%f];('
            'way[highway~"^(motorway|trunk|primary|secondary|tertiary)(_link)?$"];way[highway][lanes];way[highway][width];'
            'way[highway=construction];way[railway~"^(rail|light_rail|narrow_gauge|construction)$"];'
            'way[waterway~"^(river|canal)$"];);out tags geom qt;' % (timeout_s, b[1], b[0], b[3], b[2]))


def _src_label(js, how):
    ts = str(((js or {}).get("osm3s") or {}).get("timestamp_osm_base", ""))[:10]
    return "OpenStreetMap (%s%s; %s)" % (how, (", data per %s" % ts) if ts else "", ATTRIBUTION)


def fetch(bbox, cache_dir, feedback=None, timeout_s=25):
    """Jalan/rel/sungai di kotak bbox dari OpenStreetMap: memori -> cache disk -> server Overpass (berurutan, dengan
    pemutus sirkuit) -> cache kedaluwarsa. -> (daftar jalan, keterangan sumber) atau (None, alasan)."""
    g = GRID_DEG
    b = (math.floor(bbox[0] / g) * g, math.floor(bbox[1] / g) * g, math.ceil(bbox[2] / g) * g, math.ceil(bbox[3] / g) * g)
    b = tuple(round(v, 6) for v in b)
    now = time.time()
    for box, (t_, js_, src_) in list(_MEMO.items()):
        if _covers(box, bbox) and now - t_ < CACHE_DAYS * 86400:
            return _clip(parse_overpass(js_), bbox), src_
    hit = _cache_find(cache_dir, bbox)
    if hit:
        js, mt, box = hit
        src = _src_label(js, "cache %s" % time.strftime("%d-%m-%Y", time.localtime(mt)))
        _MEMO[box] = (mt, js, src)
        return _clip(parse_overpass(js), bbox), src

    def stale(why):
        old = _cache_find(cache_dir, bbox, stale=True)
        if old:
            js, mt, _box = old
            return _clip(parse_overpass(js), bbox), _src_label(
                js, "cache LAMA %s, server tidak terjangkau" % time.strftime("%d-%m-%Y", time.localtime(mt)))
        return None, why
    st = _state(cache_dir)
    if st["fail_t"] > _FAIL["t"]:
        _FAIL.update(t=st["fail_t"], why=st["fail_why"])
    if 0 <= now - _FAIL["t"] < FAIL_MEMO_S:
        return stale("%s (dicoba %d menit lalu; dicoba lagi otomatis setelah %d menit)" % (
            _FAIL["why"], int((now - _FAIL["t"]) / 60), FAIL_MEMO_S // 60))
    try:
        from qgis.PyQt.QtCore import QUrl
    except Exception as e:
        return None, "modul jaringan QGIS tidak tersedia (%s)" % e
    body = b"data=" + bytes(QUrl.toPercentEncoding(overpass_query(b, timeout_s)))
    hosts = sorted(OVERPASS, key=lambda u: 0 if u.split("/")[2] == st["good"] else 1)
    js, name, fails, t0 = None, None, [], time.time()
    for url in hosts:
        host = url.split("/")[2]
        if time.time() - t0 > TOTAL_LIMIT_S - 3:
            fails.append("%s: dilewati (batas waktu %d detik)" % (host, TOTAL_LIMIT_S))
            continue
        if host in st["rest"]:
            fails.append("%s: diistirahatkan %d menit lagi" % (host, max(1, int((st["rest"][host] - now) / 60))))
            continue
        js, why, kind = _one(url, body, feedback, min(SERVER_LIMIT_S, max(3.0, TOTAL_LIMIT_S - (time.time() - t0))))
        if js is not None:
            name = host
            break
        fails.append(why)
        if kind == "cancel":
            return None, "dibatalkan"
        rest = REST_BLOCK_S if kind == "block" else REST_BUSY_S
        _state(cache_dir, lambda s_, h_=host, r_=rest: s_["rest"].__setitem__(h_, time.time() + r_))
    if js is None:
        why = ("OpenStreetMap tidak terjangkau (offline / server publik sibuk atau menolak): %s. Untuk pemakaian rutin, "
               "taruh paket data jalan lokal (*OSM*.gpkg atau ekstrak Geofabrik *.osm.pbf) di folder data referensi"
               % "; ".join(str(t) for t in fails)[:200])
        _FAIL.update(t=time.time(), why=why)
        _state(cache_dir, lambda s_: s_.update(fail_t=_FAIL["t"], fail_why=why))
        return stale(why)
    _FAIL["t"] = 0.0
    js["elements"] = [e for e in js.get("elements", []) if classify(e.get("tags") or {})]
    js["seranta_v"] = 2
    src = _src_label(js, "%s, %s" % (name, time.strftime("%d-%m-%Y")))
    _MEMO[b] = (time.time(), js, src)
    _state(cache_dir, lambda s_: s_.update(good=name, fail_t=0.0, fail_why=""))
    if cache_dir:
        try:
            os.makedirs(cache_dir, exist_ok=True)
            with open(_cache_path(cache_dir, b), "w", encoding="utf-8") as fh:
                json.dump(js, fh)
        except Exception as e:
            _log.note(e)
    return _clip(parse_overpass(js), bbox), src


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

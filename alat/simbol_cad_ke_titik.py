# -*- coding: utf-8 -*-
"""
SIMBOL CAD -> TITIK  (SATU skrip Processing QGIS 3.22 - 4.x; satu berkas ATAU satu folder)
=========================================================================================
Masalah: data jaringan hasil konversi CAD (DGN/DWG -> KML/DXF -> Shapefile) menyimpan SIMBOL sebagai garis. Satu
homepass/tiang/FAT/closure bukan titik, melainkan:
  * lingkaran = polyline tertutup 16-17 verteks, sering diisi ARSIRAN (garis-garis 2 titik di dalamnya);
  * kotak label (mis. "FAT"), sering berbingkai GANDA, berisi huruf yang juga digambar sebagai garis;
  * semua bagian satu level tergabung dalam SATU fitur MultiLineString per level (kolom 'folders' = "Levels; FAT").
Skrip ini mengubah setiap simbol menjadi SATU titik di pusatnya, dengan aturan:
  1. Bagian-bagian satu simbol (bingkai, bingkai ganda, huruf, arsiran) dalam LEVEL yang sama digabung -> 1 titik.
  2. Simbol dari LEVEL BERBEDA yang saling menimpa (mis. kotak FAT ditimpa lingkaran tiang) tetap DUA titik.
  3. Titik ganda (level sama, pusat <= toleransi duplikat) dibuang, yang pertama dipertahankan.
  4. Garis panjang (kabel/strand/span) tidak diubah; ditulis ke layer garis tersendiri yang bersih dari simbol.

SATU ALAT, DUA CARA (isi salah satu):
  * "Satu layer / berkas"  : layer di peta atau berkas .shp/.gpkg/.kml/.kmz/.dxf/.geojson;
  * "Satu folder"          : semua data CAD di folder (dan subfolder) diproses sekaligus.
Hasil (keduanya sama formatnya) di folder hasil (bawaan: <folder data>/HASIL_TITIK_SIMBOL):
  <nama>_titik.shp, <nama>_garis.shp, REKAP_SIMBOL_CAD.csv (status, jumlah, titik per level & bentuk, proyeksi, waktu)
  dan SEMUA_TITIK.gpkg (gabungan berkolom 'berkas'), lalu hasilnya dimuat ke peta.

Stabil & deterministik: jarak dihitung dalam meter pada proyeksi UTM per berkas (otomatis), bagian diurutkan menurut
koordinat sebelum diproses, tanpa angka acak; input yang sama selalu menghasilkan titik yang sama. Satu berkas gagal
tidak menghentikan berkas lain (alasannya ditulis di rekap); folder hasil tidak ikut dibaca ulang.

Dasar perhitungan (sumber):
  * pusat lingkaran: kuadrat terkecil aljabar (Kasa, IEEE Trans. Instrum. Meas. IM-25, 1976; Chernov, "Circular and
    Linear Regression", CRC 2010); lingkaran dikenali bila simpangan jari-jari verteks < 5 % (poligon >= 8 sisi);
  * meter: UTM (Snyder, "Map Projections - A Working Manual", USGS Prof. Paper 1395, 1987), faktor skala 0,9996 ->
    galat jarak <= 0,04 % di dalam zona; transformasi oleh PROJ/QGIS;
  * arsiran di dalam bentuk: uji titik-dalam-poligon ray casting (Shimrat, CACM 5(8), 1962);
  * luas bentuk: rumus shoelace (Gauss); pengelompokan bagian: union-find (Tarjan, J. ACM 22(2), 1975).

Cara pakai: Processing Toolbox -> ikon Python -> "Add Script to Toolbox..." -> pilih berkas ini, lalu
Processing Toolbox -> Scripts -> Simbol CAD -> Titik -> "Simbol CAD menjadi titik". Hanya berkas ini yang diperlukan.

HAK CIPTA, LISENSI DAN KEASLIAN (bagian ini wajib dipertahankan di setiap salinan dan modifikasi)
---------------------------------------------------------------------------------------------------------------------
Copyright (C) 2026 Joseph Edward Timothy Siahaan <edwardtimoo@gmail.com>. Pencipta dan pemegang hak cipta.
Lisensi: GNU General Public License versi 3 atau lebih baru (https://www.gnu.org/licenses/gpl-3.0.html), DENGAN SYARAT
TAMBAHAN berdasarkan pasal 7 GPL v3 berikut, yang merupakan bagian dari lisensi setiap salinan:
  1. (7b) Pertahankan pemberitahuan hak cipta "Copyright (C) 2026 Joseph Edward Timothy Siahaan", blok ini, nama
     pencipta di keterangan alat, dan pemeriksaan keaslian (fungsi status_keaslian) beserta keluarannya di log dan di
     TENTANG_HASIL.txt. Pemeriksaan keaslian boleh diubah HANYA agar versi Anda melaporkan dirinya dengan jujur sebagai
     DIMODIFIKASI / TIDAK RESMI.
  2. (7c) Dilarang mengaku atau menyiratkan sebagai pencipta/pemilik skrip ini atau bagian yang ditulis Joseph Edward
     Timothy Siahaan. Versi modifikasi wajib ditandai: "Berbasis Simbol CAD -> Titik oleh Joseph Edward Timothy
     Siahaan, dimodifikasi oleh <nama>, <tanggal>", dan memakai nama alat lain.
  3. (7e) Lisensi ini tidak memberi hak atas nama alat "Simbol CAD -> Titik" untuk versi modifikasi.
  4. Rilis resmi ditandatangani digital (Ed25519) dengan kunci rilis pencipta; SIDIK KUNCI RESMI: 92C4-D078-D1FC-1C5B.
     Baris terakhir berkas ("# RILIS-RESMI: ...") memuat tanda tangannya. Salinan dengan sidik kunci lain, tanda
     tangan tidak cocok, atau isi yang diubah BUKAN rilis resmi. Pemeriksa independen: rilis_resmi.py cek <berkas>.
Melanggar syarat ini menggugurkan izin memakai, menyalin dan memodifikasi skrip ini (GPL v3 pasal 8).
"""
import csv
import hashlib
import math
import os
import re
import time

from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeature, QgsField, QgsFields,
                       QgsGeometry, QgsPointXY, QgsProcessingAlgorithm, QgsProcessingException,
                       QgsProcessingParameterBoolean, QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterField, QgsProcessingParameterFile,
                       QgsProcessingParameterFolderDestination, QgsProcessingParameterNumber, QgsProject,
                       QgsVectorFileWriter, QgsVectorLayer)
from qgis.PyQt.QtCore import QCoreApplication, QVariant

VERSI = "1.3.0"
PEMBUAT = "Joseph Edward Timothy Siahaan"
PRODUK = "Simbol CAD -> Titik"
# Kunci publik rilis pencipta (Ed25519, 8 x 32-bit) dan sidiknya; sama dengan Seranta dan Seuntai. Juga tertulis di
# blok hak cipta di atas (cek silang).
KUNCI_PUBLIK = (1549593263, 1258448507, 3948243780, 1745094294, 3588476158, 1130529245, 3255756279, 3988926214)
SIDIK_RESMI = "92C4-D078-D1FC-1C5B"
TANDA = "# RILIS-RESMI: "

# ---- Ed25519 (RFC 8032) untuk memverifikasi tanda tangan rilis; murni Python, tanpa pustaka luar
_P = 2 ** 255 - 19
_Q = 2 ** 252 + 27742317777372353535851937790883648493


def _inv(x):
    return pow(x, _P - 2, _P)


_D = -121665 * _inv(121666) % _P
_I = pow(2, (_P - 1) // 4, _P)


def _ed_add(a, b):
    A = (a[1] - a[0]) * (b[1] - b[0]) % _P
    B = (a[1] + a[0]) * (b[1] + b[0]) % _P
    C = 2 * a[3] * b[3] * _D % _P
    D = 2 * a[2] * b[2] % _P
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F % _P, G * H % _P, F * G % _P, E * H % _P)


def _ed_mul(s, pt):
    q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            q = _ed_add(q, pt)
        pt = _ed_add(pt, pt)
        s >>= 1
    return q


def _ed_x(y, sign):
    if y >= _P:
        return None
    x2 = (y * y - 1) * _inv(_D * y * y + 1) % _P
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P:
        x = x * _I % _P
    if (x * x - x2) % _P:
        return None
    if (x & 1) != sign:
        x = _P - x
    return x


_GY = 4 * _inv(5) % _P
_GX = _ed_x(_GY, 0)
_G = (_GX, _GY, 1, _GX * _GY % _P)


def _ed_dec(b):
    if len(b) != 32:
        return None
    y = int.from_bytes(b, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _ed_x(y, sign)
    return None if x is None else (x, y, 1, x * y % _P)


def _ed_verify(public, msg, sig):
    if len(public) != 32 or len(sig) != 64:
        return False
    A, R = _ed_dec(public), _ed_dec(sig[:32])
    if A is None or R is None:
        return False
    s = int.from_bytes(sig[32:], "little")
    if s >= _Q:
        return False
    h = int.from_bytes(hashlib.sha512(sig[:32] + public + msg).digest(), "little") % _Q
    lhs, rhs = _ed_mul(s, _G), _ed_add(R, _ed_mul(h, A))
    return (lhs[0] * rhs[2] - rhs[0] * lhs[2]) % _P == 0 and (lhs[1] * rhs[2] - rhs[1] * lhs[2]) % _P == 0


def _ints_bytes(v):
    return b"".join(int(x).to_bytes(4, "big") for x in v)


def sidik(public):
    h = hashlib.sha256(public).hexdigest().upper()[:16]
    return "-".join(h[i:i + 4] for i in range(0, 16, 4))


def pesan_rilis(body, versi):
    """Yang ditandatangani: produk, versi, pencipta dan SHA-256 isi berkas (tanpa baris tanda tangan; CRLF = LF)."""
    h = hashlib.sha256(body.replace("\r\n", "\n").encode("utf-8")).hexdigest()
    return ("%s|%s|%s|%s" % (PRODUK, versi, PEMBUAT, h)).encode("utf-8")


def status_keaslian(path=None):
    """(kode, teks). ASLI / DIMODIFIKASI / TIDAK_RESMI / PENGEMBANGAN, selalu menyebut sidik kunci."""
    try:
        path = path or os.path.abspath(__file__)
        with open(path, encoding="utf-8", newline="") as fh:
            text = fh.read()
    except Exception as e:
        return "GAGAL", "tidak diverifikasi (%s)" % str(e)[:60]
    sk = sidik(_ints_bytes(KUNCI_PUBLIK))
    i = text.rfind("\n" + TANDA)
    if i < 0:
        return "PENGEMBANGAN", "salinan pengembangan (belum rilis bertanda tangan)"
    body, line = text[:i + 1], text[i + 1:].strip()
    if sk != SIDIK_RESMI or ("SIDIK KUNCI RESMI: " + SIDIK_RESMI) not in body:
        return "TIDAK_RESMI", ("TIDAK RESMI - kunci rilis diganti (kunci %s, kunci resmi %s): bukan rilis resmi "
                               "Simbol CAD -> Titik" % (sk, SIDIK_RESMI))
    try:
        kv = dict(x.split("=", 1) for x in line[len(TANDA):].split(";") if "=" in x)
        versi, ttd = kv.get("v", ""), _ints_bytes(int(x) for x in kv.get("ttd", "").split(",") if x)
    except Exception:
        return "TIDAK_RESMI", "TIDAK RESMI - baris tanda tangan rusak (kunci resmi %s)" % SIDIK_RESMI
    if not _ed_verify(_ints_bytes(KUNCI_PUBLIK), pesan_rilis(body, versi), ttd):
        return "DIMODIFIKASI", ("DIMODIFIKASI - isi berkas tidak sama dengan rilis resmi %s yang ditandatangani %s "
                                "(kunci %s): bukan rilis resmi" % (versi, PEMBUAT, sk))
    if versi != VERSI:
        return "DIMODIFIKASI", "DIMODIFIKASI - versi di kode (%s) beda dengan rilis bertanda tangan %s" % (VERSI, versi)
    return "ASLI", "ASLI - rilis resmi %s ditandatangani %s (kunci %s)" % (versi, PEMBUAT, sk)


def _enum(*names):
    """Enum QGIS 3.22 (lama) s.d. QGIS 4 (Qgis.*) - ambil yang tersedia."""
    from qgis import core
    for n in names:
        obj = core
        for p in n.split("."):
            obj = getattr(obj, p, None)
            if obj is None:
                break
        if obj is not None:
            return obj
    raise AttributeError(names)


T_LINE = _enum("Qgis.ProcessingSourceType.VectorLine", "QgsProcessing.TypeVectorLine")
T_POLY = _enum("Qgis.ProcessingSourceType.VectorPolygon", "QgsProcessing.TypeVectorPolygon")
T_POINT = _enum("Qgis.ProcessingSourceType.VectorPoint", "QgsProcessing.TypeVectorPoint")
NUM_DBL = _enum("Qgis.ProcessingNumberParameterType.Double", "QgsProcessingParameterNumber.Double")
FLD_STR = _enum("Qgis.ProcessingFieldParameterDataType.String", "QgsProcessingParameterField.String")
W_POINT = _enum("Qgis.WkbType.Point", "QgsWkbTypes.Point")
W_LINE = _enum("Qgis.WkbType.LineString", "QgsWkbTypes.LineString")


def _field(name, kind, length=0, prec=0):
    """QgsField lintas versi (QVariant di QGIS 3, QMetaType di QGIS 4)."""
    try:
        from qgis.PyQt.QtCore import QMetaType
        mt = {"s": QMetaType.Type.QString, "i": QMetaType.Type.Int, "d": QMetaType.Type.Double}[kind]
        return QgsField(name, mt, len=length, prec=prec)
    except Exception:
        vt = {"s": QVariant.String, "i": QVariant.Int, "d": QVariant.Double}[kind]
        return QgsField(name, vt, len=length, prec=prec)


# ----------------------------------------------------------------------------------------------- geometri murni
def _closed(pts, eps):
    return len(pts) >= 4 and math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) <= eps


def _bbox(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def _fit_circle(pts):
    """Pusat & jari-jari lingkaran kuadrat terkecil (Kasa). Kembali (cx, cy, r, simpangan_relatif) atau None."""
    q = pts[:-1] if _closed(pts, 1e-9) else pts
    n = len(q)
    if n < 6:
        return None
    mx = sum(p[0] for p in q) / n
    my = sum(p[1] for p in q) / n
    suu = suv = svv = suuu = svvv = suvv = svuu = 0.0
    for x, y in q:
        u, v = x - mx, y - my
        suu += u * u
        svv += v * v
        suv += u * v
        suuu += u * u * u
        svvv += v * v * v
        suvv += u * v * v
        svuu += v * u * u
    det = suu * svv - suv * suv
    if abs(det) < 1e-12:
        return None
    b1 = 0.5 * (suuu + suvv)
    b2 = 0.5 * (svvv + svuu)
    uc = (b1 * svv - b2 * suv) / det
    vc = (b2 * suu - b1 * suv) / det
    cx, cy = mx + uc, my + vc
    rs = [math.hypot(x - cx, y - cy) for x, y in q]
    r = sum(rs) / n
    if r <= 0:
        return None
    sd = math.sqrt(sum((v - r) ** 2 for v in rs) / n)
    return cx, cy, r, sd / r


def _in_ring(x, y, ring):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-300) + xi:
            inside = not inside
        j = i
    return inside


def _area(ring):
    return abs(sum(ring[i][0] * ring[i - 1][1] - ring[i - 1][0] * ring[i][1] for i in range(len(ring)))) / 2.0


class _UF:
    def __init__(self, n):
        self.p = list(range(n))

    def f(self, a):
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def u(self, a, b):
        a, b = self.f(a), self.f(b)
        if a != b:
            self.p[max(a, b)] = min(a, b)


def _touch(a, b, pad):
    return not (a[2] + pad < b[0] or b[2] + pad < a[0] or a[3] + pad < b[1] or b[3] + pad < a[1])


def build_symbols(parts, sym_max=12.0, hatch_max=None, dup_tol=0.5, circ_tol=0.05, close_eps=0.05):
    """parts: [dict(level, pts=[(x,y)] dalam meter, src)] (urutan bebas). Kembali (titik, garis).
    titik: [dict(level, x, y, simbol, n_bagian, d_m, w_m, h_m, arsir, src)]; garis: [dict(level, pts, src)]."""
    hatch_max = hatch_max or sym_max
    parts = sorted(parts, key=lambda p: (p["level"], round(p["pts"][0][0], 3), round(p["pts"][0][1], 3),
                                         len(p["pts"]), round(p["pts"][-1][0], 3), round(p["pts"][-1][1], 3)))
    shapes, shorts, lines = [], [], []
    for p in parts:
        pts = p["pts"]
        if len(pts) < 2:
            continue
        bb = _bbox(pts)
        size = max(bb[2] - bb[0], bb[3] - bb[1])
        if _closed(pts, close_eps) and size <= sym_max:
            c = _fit_circle(pts)
            circ = c is not None and len(pts) >= 9 and c[3] <= circ_tol
            shapes.append({"level": p["level"], "pts": pts, "bb": bb, "size": size, "circle": c if circ else None,
                           "area": _area(pts[:-1]), "src": p["src"]})
        elif size <= hatch_max:              # bagian terbuka kecil: arsiran / goresan simbol
            shorts.append({"level": p["level"], "pts": pts, "bb": bb, "src": p["src"]})
        else:
            lines.append(p)
    # 1) arsiran: garis pendek yang titik tengahnya di dalam bentuk tertutup level sama (atau level apa pun bila tidak ada)
    owner = {}
    for si, s in enumerate(shorts):
        a, b = s["pts"][0], s["pts"][-1]
        mx, my = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
        best = None
        for ki, k in enumerate(shapes):
            bb = k["bb"]
            if not (bb[0] <= mx <= bb[2] and bb[1] <= my <= bb[3]):
                continue
            if not _in_ring(mx, my, k["pts"]):
                continue
            key = (0 if k["level"] == s["level"] else 1, k["area"], ki)
            if best is None or key < best[0]:
                best = (key, ki)
        if best is not None and (best[0][0] == 0 or shapes[best[1]]["circle"] is not None):
            owner[si] = best[1]     # arsiran level lain hanya diserap lingkaran (CAD: hatch kadang di level terpisah)
    # 2) kelompok bentuk tertutup per level: kotak batas bersinggungan (bingkai ganda, huruf di dalam bingkai)
    uf = _UF(len(shapes))
    by_level = {}
    for i, k in enumerate(shapes):
        by_level.setdefault(k["level"], []).append(i)
    for lv, ix in by_level.items():
        ix.sort(key=lambda i: shapes[i]["bb"][0])
        for a_ in range(len(ix)):
            i = ix[a_]
            for b_ in range(a_ + 1, len(ix)):
                j = ix[b_]
                if shapes[j]["bb"][0] > shapes[i]["bb"][2]:
                    break
                ci, cj = shapes[i]["circle"], shapes[j]["circle"]
                if ci and cj and math.hypot(ci[0] - cj[0], ci[1] - cj[1]) > 0.5 * min(ci[2], cj[2]):
                    continue        # dua lingkaran berdampingan di level sama = dua objek
                if _touch(shapes[i]["bb"], shapes[j]["bb"], 0.0):
                    uf.u(i, j)
    groups = {}
    for i in range(len(shapes)):
        groups.setdefault(uf.f(i), []).append(i)
    hatch_of = {}
    for si, ki in owner.items():
        hatch_of.setdefault(uf.f(ki), []).append(si)
    # 3) arsiran tanpa bingkai (garis pendek sejajar berkumpul, level sama): satu simbol per kumpulan
    free = [si for si in range(len(shorts)) if si not in owner]
    uf2 = _UF(len(free))
    for a_ in range(len(free)):
        for b_ in range(a_ + 1, len(free)):
            if shorts[free[a_]]["level"] == shorts[free[b_]]["level"] and \
                    _touch(shorts[free[a_]]["bb"], shorts[free[b_]]["bb"], 0.3):
                uf2.u(a_, b_)
    clusters = {}
    for a_, si in enumerate(free):
        clusters.setdefault(uf2.f(a_), []).append(si)
    # 4) titik per simbol
    out = []
    for root, ix in groups.items():
        frame = max(ix, key=lambda i: (shapes[i]["area"], -i))
        k = shapes[frame]
        circles = [shapes[i]["circle"] for i in ix if shapes[i]["circle"]]
        hat = hatch_of.get(root, [])
        allpts = [p for i in ix for p in shapes[i]["pts"]]
        bb = _bbox(allpts)
        if k["circle"]:
            cx, cy, r = k["circle"][0], k["circle"][1], k["circle"][2]
            kind = "LINGKARAN_ARSIR" if hat else "LINGKARAN"
        else:
            ring = k["pts"][:-1]
            cx = (k["bb"][0] + k["bb"][2]) / 2.0
            cy = (k["bb"][1] + k["bb"][3]) / 2.0
            r = None
            kind = ("BINGKAI_TEKS" if len(ix) > 2 else "BINGKAI") if len(ring) <= 6 else "BENTUK"
            if hat:
                kind += "_ARSIR"
        out.append({"level": k["level"], "x": cx, "y": cy, "simbol": kind, "n_bagian": len(ix) + len(hat),
                    "d_m": round(2 * r, 2) if r else None, "w_m": round(bb[2] - bb[0], 2),
                    "h_m": round(bb[3] - bb[1], 2), "arsir": len(hat), "n_lingkaran": len(circles),
                    "src": k["src"]})
    for root, ix in clusters.items():
        if len(ix) < 3:
            for si in ix:                      # 1-2 garis pendek lepas: bukan simbol, kembalikan sebagai garis
                lines.append({"level": shorts[si]["level"], "pts": shorts[si]["pts"], "src": shorts[si]["src"]})
            continue
        bb = _bbox([p for si in ix for p in shorts[si]["pts"]])
        if max(bb[2] - bb[0], bb[3] - bb[1]) > sym_max:
            for si in ix:
                lines.append({"level": shorts[si]["level"], "pts": shorts[si]["pts"], "src": shorts[si]["src"]})
            continue
        out.append({"level": shorts[ix[0]]["level"], "x": (bb[0] + bb[2]) / 2.0, "y": (bb[1] + bb[3]) / 2.0,
                    "simbol": "ARSIR_TANPA_BINGKAI", "n_bagian": len(ix), "d_m": None, "w_m": round(bb[2] - bb[0], 2),
                    "h_m": round(bb[3] - bb[1], 2), "arsir": len(ix), "n_lingkaran": 0, "src": shorts[ix[0]]["src"]})
    # 5) titik ganda di level yang sama
    out.sort(key=lambda t: (t["level"], round(t["x"], 3), round(t["y"], 3), t["simbol"]))
    keep = []
    cell = {}
    g = max(dup_tol, 1e-6)
    for t in out:
        cx_, cy_ = int(math.floor(t["x"] / g)), int(math.floor(t["y"] / g))
        dup = False
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for o in cell.get((t["level"], cx_ + dx, cy_ + dy), []):
                    if math.hypot(o["x"] - t["x"], o["y"] - t["y"]) <= dup_tol:
                        dup = True
                        o["ganda"] = o.get("ganda", 0) + 1
        if not dup:
            cell.setdefault((t["level"], cx_, cy_), []).append(t)
            keep.append(t)
    return keep, lines


LEVEL_KEYS = ("folders", "Layer", "layer", "Level", "level", "LEVEL", "LAYER")


def level_of(attrs, level_field):
    """Nama level: kolom pilihan, atau otomatis 'folders' KML ("Levels; FAT" -> "FAT"), 'Layer' DXF, 'Level' DGN."""
    if level_field and level_field in attrs:
        v = attrs[level_field]
    else:
        v = None
        for k in LEVEL_KEYS + ("name", "Name"):
            if k in attrs and attrs[k] not in (None, ""):
                v = attrs[k]
                break
    v = "" if v is None else str(v)
    v = v.split(";")[-1].strip()
    return re.sub(r"\s+", " ", v) or "(tanpa level)"


def utm_crs(lon, lat):
    zone = int(math.floor((lon + 180.0) / 6.0)) % 60 + 1
    return QgsCoordinateReferenceSystem("EPSG:%d" % ((32600 if lat >= 0 else 32700) + zone))


def work_crs(crs, extent):
    """Proyeksi kerja bermeter: CRS asal bila sudah meter, selain itu UTM zona pusat data (Snyder 1987, USGS PP 1395;
    faktor skala 0,9996 -> galat jarak <= 0,04 % di dalam zona). CRS kosong + koordinat derajat -> dianggap WGS 84.
    Kembali (crs_asal_efektif, crs_kerja, catatan)."""
    note = ""
    if crs is None or not crs.isValid():
        if extent is not None and -180 <= extent.xMinimum() <= extent.xMaximum() <= 180 and \
                -90 <= extent.yMinimum() <= extent.yMaximum() <= 90:
            crs = QgsCoordinateReferenceSystem("EPSG:4326")
            note = "CRS tidak ada (.prj hilang): koordinat berbentuk derajat, dianggap WGS 84 (EPSG:4326)"
        else:
            return None, None, "CRS tidak ada dan koordinat bukan derajat: tidak bisa dihitung dalam meter"
    meters = _enum("Qgis.DistanceUnit.Meters", "QgsUnitTypes.DistanceMeters")
    if not crs.isGeographic() and crs.mapUnits() == meters:
        return crs, crs, note
    to_wgs = QgsCoordinateTransform(crs, QgsCoordinateReferenceSystem("EPSG:4326"), QgsProject.instance())
    c = to_wgs.transform(extent.center())
    return crs, utm_crs(c.x(), c.y()), note


def features_to_parts(features, names, fwd, level_field="", fallback_level=""):
    """Fitur QGIS (garis/poligon, tunggal/multi) -> bagian garis dalam meter: [dict(level, pts, src)]."""
    parts = []
    poly_t = _enum("Qgis.GeometryType.Polygon", "QgsWkbTypes.PolygonGeometry")
    line_t = _enum("Qgis.GeometryType.Line", "QgsWkbTypes.LineGeometry")
    for f in features:
        g = f.geometry()
        if g is None or g.isEmpty() or g.type() not in (poly_t, line_t):
            continue
        attrs = dict(zip(names, f.attributes()))
        if fallback_level and not level_field and not any(k in names for k in LEVEL_KEYS):
            lv = fallback_level          # KML/GPKG: nama folder/layer = level (kolom 'Name' = nama placemark, bukan level)
        else:
            lv = level_of(attrs, level_field)
        g = QgsGeometry(g)
        g.transform(fwd)
        if g.type() == poly_t:
            polys = g.asMultiPolygon() if g.isMultipart() else [g.asPolygon()]
            lines_ = [ring for poly in polys for ring in poly]          # cincin poligon = garis tertutup
        else:
            lines_ = g.asMultiPolyline() if g.isMultipart() else [g.asPolyline()]
        for k, pl in enumerate(lines_):
            pts = [(p.x(), p.y()) for p in pl]
            if len(pts) >= 2:
                parts.append({"level": lv, "pts": pts, "src": "%s#%d" % (f.id(), k)})
    return parts


POINT_FIELDS = (("id", "i", 0, 0), ("level", "s", 80, 0), ("simbol", "s", 30, 0), ("n_bagian", "i", 0, 0),
                ("arsir", "i", 0, 0), ("n_lingk", "i", 0, 0), ("diam_m", "d", 10, 2), ("lebar_m", "d", 10, 2),
                ("tinggi_m", "d", 10, 2), ("ganda", "i", 0, 0), ("sumber", "s", 40, 0))


def point_attrs(i, t):
    return [i, t["level"], t["simbol"], t["n_bagian"], t["arsir"], t["n_lingkaran"], t["d_m"], t["w_m"], t["h_m"],
            t.get("ganda", 0), t["src"]]


# ----------------------------------------------------------------------------------------------- algoritma QGIS
FOLDER_B = _enum("Qgis.ProcessingFileParameterBehavior.Folder", "QgsProcessingParameterFile.Folder")
EKSTENSI = (".shp", ".gpkg", ".kml", ".kmz", ".dxf", ".geojson", ".json", ".gml", ".tab", ".mif")
HASIL_DEFAULT = "HASIL_TITIK_SIMBOL"
LINE_FIELDS = (("id", "i", 0, 0), ("level", "s", 80, 0), ("panjang_m", "d", 12, 2), ("sumber", "s", 40, 0))


def find_files(folder, recursive, skip_dirs):
    """Data CAD di folder (urut stabil, tanpa membedakan huruf besar); folder hasil dilewati."""
    out = []
    skip = {os.path.normcase(os.path.abspath(d)) for d in skip_dirs if d}
    for root, dirs, files in os.walk(folder):
        dirs[:] = sorted((d for d in dirs if os.path.normcase(os.path.abspath(os.path.join(root, d))) not in skip
                          and not d.startswith(".") and not d.upper().startswith(HASIL_DEFAULT)), key=str.lower)
        for f in sorted(files, key=str.lower):
            if f.lower().endswith(EKSTENSI):
                out.append(os.path.join(root, f))
        if not recursive:
            break
    return out


def sublayers(path):
    """[(uri, nama_layer)] semua layer vektor satu berkas (GPKG/KML/DXF bisa banyak layer)."""
    p = path
    try:
        from osgeo import ogr
        ds = ogr.Open(p)
        if ds is None and path.lower().endswith(".kmz"):       # tanpa driver LIBKML: baca KML di dalam zip
            import zipfile
            with zipfile.ZipFile(path) as z:
                inner = sorted((n for n in z.namelist() if n.lower().endswith(".kml")),
                               key=lambda n: (n.lower() != "doc.kml", n.count("/"), n))
            if inner:
                p = "/vsizip/%s/%s" % (path.replace("\\", "/"), inner[0])
                ds = ogr.Open(p)
        if ds is None:
            return [(p, os.path.splitext(os.path.basename(path))[0])]
        names = [ds.GetLayerByIndex(i).GetName() for i in range(ds.GetLayerCount())]
        ds = None
        if len(names) <= 1:
            return [(p, names[0] if names else os.path.splitext(os.path.basename(path))[0])]
        return [("%s|layername=%s" % (p, n), n) for n in names]
    except Exception:
        return [(p, os.path.splitext(os.path.basename(path))[0])]


def _writer(path, fields, wkb, crs, driver="ESRI Shapefile", layer=None):
    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = driver
    opts.fileEncoding = "UTF-8"
    if layer:
        opts.layerName = layer
    try:
        w = QgsVectorFileWriter.create(path, fields, wkb, crs, QgsProject.instance().transformContext(), opts)
    except AttributeError:      # QGIS < 3.26
        w = QgsVectorFileWriter(path, "UTF-8", fields, wkb, crs, driver)
    if w.hasError():
        raise IOError(w.errorMessage())
    return w


def _fields(spec):
    fs = QgsFields()
    for nm, kd, ln, pr in spec:
        fs.append(_field(nm, kd, ln, pr))
    return fs


def process_inputs(inputs, base, sym, dup, lines_on, wgs_points=None):
    """inputs: [(sumber_fitur, nama_kolom, crs, extent, level_kolom, level_cadangan)] dari SATU berkas/layer;
    sumber_fitur = layer atau feature source (punya getFeatures()); fitur dibaca satu layer demi satu layer.
    Menulis base_titik.shp (+ base_garis.shp). Kembali dict ringkasan (bagian, titik, garis, crs, per-level, catatan).
    wgs_points: list untuk titik gabungan (WGS 84) bila tidak None."""
    parts, crs, work, note = [], None, None, ""
    for source, names, lcrs, ext, lvf, fb in inputs:
        if crs is None:
            crs, work, note = work_crs(lcrs, ext)
            if work is None:
                raise ValueError(note)
            fwd = QgsCoordinateTransform(crs, work, QgsProject.instance())
        elif lcrs is not None and lcrs.isValid() and lcrs != crs:
            fwd = QgsCoordinateTransform(lcrs, work, QgsProject.instance())
        else:
            fwd = QgsCoordinateTransform(crs, work, QgsProject.instance())
        parts += features_to_parts(source.getFeatures(), names, fwd, lvf, fb)
    out = {"bagian": len(parts), "titik": 0, "garis": 0, "crs": work.authid() if work else "", "catatan": note,
           "per": {}}
    if not parts:
        return out
    pts, lines = build_symbols(parts, sym_max=sym, dup_tol=dup)
    back = QgsCoordinateTransform(work, crs, QgsProject.instance())
    to_wgs = QgsCoordinateTransform(work, QgsCoordinateReferenceSystem("EPSG:4326"), QgsProject.instance())
    os.makedirs(os.path.dirname(base) or ".", exist_ok=True)
    pf = _fields(POINT_FIELDS)
    w = _writer(base + "_titik.shp", pf, W_POINT, crs)
    for i, t in enumerate(pts, 1):
        ft = QgsFeature(pf)
        ft.setGeometry(QgsGeometry.fromPointXY(back.transform(QgsPointXY(t["x"], t["y"]))))
        ft.setAttributes(point_attrs(i, t))
        w.addFeature(ft)
        key = "%s | %s" % (t["level"], t["simbol"])
        out["per"][key] = out["per"].get(key, 0) + 1
        if wgs_points is not None:
            wgs_points.append((t, to_wgs.transform(QgsPointXY(t["x"], t["y"]))))
    del w
    if lines_on:
        lf = _fields(LINE_FIELDS)
        w = _writer(base + "_garis.shp", lf, W_LINE, crs)
        for i, ln in enumerate(sorted(lines, key=lambda q: (q["level"], round(q["pts"][0][0], 3),
                                                             round(q["pts"][0][1], 3))), 1):
            g = QgsGeometry.fromPolylineXY([QgsPointXY(x, y) for x, y in ln["pts"]])
            length = g.length()
            g.transform(back)
            ft = QgsFeature(lf)
            ft.setGeometry(g)
            ft.setAttributes([i, ln["level"], round(length, 2), ln["src"]])
            w.addFeature(ft)
        del w
    out.update({"titik": len(pts), "garis": len(lines)})
    return out


def file_inputs(path):
    """Semua layer garis/poligon dalam satu berkas -> argumen process_inputs. Kembali (inputs, n_layer_terbaca)."""
    subs = sublayers(path)
    multi = len(subs) > 1 or path.lower().endswith((".kml", ".kmz"))
    line_t = _enum("Qgis.GeometryType.Line", "QgsWkbTypes.LineGeometry")
    poly_t = _enum("Qgis.GeometryType.Polygon", "QgsWkbTypes.PolygonGeometry")
    inputs, n_valid = [], 0
    for uri, lname in subs:
        lyr = QgsVectorLayer(uri, lname, "ogr")
        if not lyr.isValid():
            continue
        n_valid += 1
        if lyr.featureCount() == 0 or lyr.geometryType() not in (line_t, poly_t):
            continue
        # lyr disimpan dalam tuple agar tetap hidup selama fiturnya dibaca (iterator fitur yang dibuat lebih dulu
        # membuat KML/GPKG terkunci). KML: folder = level; GPKG multi-layer: nama layer = level.
        inputs.append((lyr, lyr.fields().names(), lyr.crs(), lyr.extent(), "", lname if multi else ""))
    return inputs, n_valid


class SimbolCadKeTitik(QgsProcessingAlgorithm):
    INPUT, FOLDER, RECUR, LEVEL, SYM, DUP, LINES_ON, LOAD, OUTDIR = (
        "INPUT", "FOLDER", "RECURSIVE", "LEVEL_FIELD", "SYMBOL_MAX", "DUP_TOL", "WRITE_LINES", "LOAD", "OUTPUT_FOLDER")

    def tr(self, s):
        return QCoreApplication.translate("SimbolCadKeTitik", s)

    def createInstance(self):
        return SimbolCadKeTitik()

    def name(self):
        return "simbol_cad_ke_titik"

    def displayName(self):
        return self.tr("Simbol CAD menjadi titik")

    def group(self):
        return self.tr("Simbol CAD -> Titik")

    def groupId(self):
        return "simbol_cad"

    def shortHelpString(self):
        return self.tr(
            "Mengubah simbol hasil konversi CAD (lingkaran berarsir, lingkaran, kotak label berbingkai ganda dengan "
            "huruf, arsiran) yang tersimpan sebagai garis menjadi SATU TITIK per simbol, di pusatnya.\n\n"
            "Isi SALAH SATU: 'Satu layer / berkas' (layer di peta atau berkas data) ATAU 'Satu folder' (semua SHP, "
            "GPKG, KML/KMZ, DXF, GeoJSON, GML, TAB/MIF di folder dan subfolder diproses sekaligus).\n\n"
            "Aturan: bagian satu simbol dalam level yang sama digabung; simbol dari level berbeda yang saling menimpa "
            "(mis. kotak FAT dan lingkaran tiang) tetap dua titik; titik ganda (level sama, pusat <= toleransi) "
            "dibuang. Jarak dalam meter (UTM otomatis per berkas). Hasil di folder hasil: <nama>_titik.shp, "
            "<nama>_garis.shp, REKAP_SIMBOL_CAD.csv dan SEMUA_TITIK.gpkg. Versi " + VERSI + ".\n\n"
            "(c) 2026 " + PEMBUAT + ". GPL v3 dengan syarat tambahan pasal 7 (lihat kepala berkas). Keaslian: "
            + status_keaslian()[1] + ".")

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.INPUT, self.tr("Satu layer / berkas data CAD (garis atau poligon)"), [T_LINE, T_POLY], optional=True))
        self.addParameter(QgsProcessingParameterFile(
            self.FOLDER, self.tr("... ATAU satu folder (semua berkas di dalamnya)"), behavior=FOLDER_B, optional=True))
        self.addParameter(QgsProcessingParameterBoolean(self.RECUR, self.tr("Folder: termasuk subfolder"), True))
        self.addParameter(QgsProcessingParameterField(
            self.LEVEL, self.tr("Kolom level (kosong = otomatis: folders / Layer / Level)"),
            parentLayerParameterName=self.INPUT, type=FLD_STR, optional=True))
        self.addParameter(QgsProcessingParameterNumber(self.SYM, self.tr("Ukuran simbol maksimum (m)"), NUM_DBL, 12.0,
                                                       minValue=0.5, maxValue=200.0))
        self.addParameter(QgsProcessingParameterNumber(self.DUP, self.tr("Toleransi titik ganda, level sama (m)"),
                                                       NUM_DBL, 0.5, minValue=0.0, maxValue=50.0))
        self.addParameter(QgsProcessingParameterBoolean(self.LINES_ON, self.tr("Tulis juga garis kabel bersih "
                                                                               "(tanpa simbol)"), True))
        self.addParameter(QgsProcessingParameterBoolean(self.LOAD, self.tr("Muat hasil ke peta"), True))
        self.addParameter(QgsProcessingParameterFolderDestination(
            self.OUTDIR, self.tr("Folder hasil (kosong = <folder data>/%s)" % HASIL_DEFAULT), optional=True,
            createByDefault=False))

    def checkParameterValues(self, parameters, context):
        has_in = parameters.get(self.INPUT) not in (None, "")
        has_dir = parameters.get(self.FOLDER) not in (None, "")
        if not has_in and not has_dir:
            return False, self.tr("Isi 'Satu layer / berkas' ATAU 'Satu folder'.")
        if has_in and has_dir:
            return False, self.tr("Isi salah satu saja: 'Satu layer / berkas' ATAU 'Satu folder'.")
        return super().checkParameterValues(parameters, context)

    def processAlgorithm(self, parameters, context, feedback):
        sym = self.parameterAsDouble(parameters, self.SYM, context)
        dup = self.parameterAsDouble(parameters, self.DUP, context)
        lines_on = self.parameterAsBool(parameters, self.LINES_ON, context)
        load = self.parameterAsBool(parameters, self.LOAD, context)
        folder = self.parameterAsFile(parameters, self.FOLDER, context) if parameters.get(self.FOLDER) else ""
        outdir = self.parameterAsString(parameters, self.OUTDIR, context) if parameters.get(self.OUTDIR) else ""
        if outdir and (outdir.upper().endswith("TEMPORARY_OUTPUT") or "/processing_" in outdir.replace("\\", "/")):
            outdir = ""
        jobs = []                                       # (nama_relatif, fungsi -> (inputs, n_valid))
        if folder:
            if not os.path.isdir(folder):
                raise QgsProcessingException("Folder tidak ditemukan: %s" % folder)
            outdir = outdir or os.path.join(folder, HASIL_DEFAULT)
            files = find_files(folder, self.parameterAsBool(parameters, self.RECUR, context), [outdir])
            if not files:
                raise QgsProcessingException("Tidak ada data CAD (%s) di folder ini." % ", ".join(EKSTENSI))
            for p in files:
                jobs.append((os.path.relpath(p, folder), lambda p=p: file_inputs(p)))
        else:
            src = self.parameterAsSource(parameters, self.INPUT, context)
            if src is None:
                raise QgsProcessingException(self.invalidSourceError(parameters, self.INPUT))
            lyr = self.parameterAsVectorLayer(parameters, self.INPUT, context)
            path = lyr.source().split("|")[0] if lyr is not None else str(parameters.get(self.INPUT))
            path = path if os.path.isfile(path) else ""
            if not outdir:
                if path:
                    outdir = os.path.join(os.path.dirname(path), HASIL_DEFAULT)
                else:
                    from qgis.core import QgsProcessingUtils
                    outdir = os.path.join(QgsProcessingUtils.tempFolder(), HASIL_DEFAULT)
            nm = os.path.basename(path) if path else (lyr.name() if lyr is not None else "layer") + ".shp"
            lvf = self.parameterAsString(parameters, self.LEVEL, context)
            jobs.append((nm, lambda: ([(src, src.fields().names(), src.sourceCrs(),
                                        src.sourceExtent(), lvf, "")], 1)))
        os.makedirs(outdir, exist_ok=True)
        integ = status_keaslian()[1]
        feedback.pushInfo("%s %s (c) %s | keaslian: %s" % (PRODUK, VERSI, PEMBUAT, integ))
        feedback.pushInfo("%d berkas | hasil: %s" % (len(jobs), outdir))
        rekap, keys, merged, outs = [], set(), [], []
        for n, (rel, get_inputs) in enumerate(jobs):
            if feedback.isCanceled():
                break
            t0 = time.time()
            row = {"berkas": rel, "status": "OK", "keterangan": "", "bagian": 0, "titik": 0, "garis": 0, "crs": ""}
            try:
                inputs, n_valid = get_inputs()
                if n_valid == 0:
                    raise ValueError("berkas tidak bisa dibaca (rusak, .shx/.dbf tidak lengkap, atau format tidak "
                                     "dikenali)")
                stem, ext = os.path.splitext(rel)
                if ext.lower() != ".shp":
                    stem += "_" + ext.lower().lstrip(".")       # tes.shp dan tes.dxf di satu folder tidak bertabrakan
                base = os.path.join(outdir, stem)
                pts_wgs = []
                res = process_inputs(inputs, base, sym, dup, lines_on, pts_wgs)
                row.update({k: res[k] for k in ("bagian", "titik", "garis", "crs")})
                row["keterangan"] = res["catatan"]
                if not res["bagian"]:
                    row["status"] = "DILEWATI"
                    row["keterangan"] = "; ".join(x for x in (res["catatan"], "tidak ada garis/poligon (layer titik "
                                                              "atau kosong)") if x)
                else:
                    for k, v in res["per"].items():
                        row[k] = v
                        keys.add(k)
                    merged += [(rel, t, p) for t, p in pts_wgs]
                    outs.append((rel, base))
                    feedback.pushInfo("%-50s %5d titik  %4d garis  (%s)" % (rel[:50], res["titik"], res["garis"],
                                                                         res["crs"]))
            except Exception as e:      # satu berkas gagal tidak menghentikan berkas lain
                row["status"] = "GAGAL"
                row["keterangan"] = str(e)[:200]
                feedback.pushWarning("%s: GAGAL - %s" % (rel, e))
            row["detik"] = round(time.time() - t0, 2)
            rekap.append(row)
            feedback.setProgress(100.0 * (n + 1) / len(jobs))
        cols = ["berkas", "status", "bagian", "titik", "garis", "crs", "detik"] + sorted(keys) + ["keterangan"]
        with open(os.path.join(outdir, "TENTANG_HASIL.txt"), "w", encoding="utf-8") as fh:
            fh.write("Dibuat oleh : %s %s\nPencipta    : %s (c) 2026\nLisensi     : GNU GPL v3 atau lebih baru dengan "
                     "syarat tambahan pasal 7\nKeaslian    : %s\nSidik resmi : %s\nWaktu       : %s\n"
                     % (PRODUK, VERSI, PEMBUAT, integ, SIDIK_RESMI, time.strftime("%Y-%m-%d %H:%M:%S")))
        rp = os.path.join(outdir, "REKAP_SIMBOL_CAD.csv")
        with open(rp, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, delimiter=";", extrasaction="ignore")
            w.writeheader()
            for r in rekap:
                w.writerow({c: r.get(c, 0 if c in keys else "") for c in cols})
        result = {self.OUTDIR: outdir, "REKAP": rp, "N_BERKAS": len(jobs),
                  "N_OK": sum(1 for r in rekap if r["status"] == "OK"),
                  "N_GAGAL": sum(1 for r in rekap if r["status"] == "GAGAL"),
                  "N_TITIK": sum(int(r.get("titik") or 0) for r in rekap)}
        gp = os.path.join(outdir, "SEMUA_TITIK.gpkg")
        if merged:
            if os.path.exists(gp):
                os.remove(gp)
            mf = _fields((("berkas", "s", 254, 0),) + POINT_FIELDS)
            wr = _writer(gp, mf, W_POINT, QgsCoordinateReferenceSystem("EPSG:4326"), "GPKG", "semua_titik")
            for i, (rel, t, p) in enumerate(merged, 1):
                ft = QgsFeature(mf)
                ft.setGeometry(QgsGeometry.fromPointXY(p))
                ft.setAttributes([rel] + point_attrs(i, t))
                wr.addFeature(ft)
            del wr
            result["SEMUA_TITIK"] = gp
        if load and outs:
            try:
                prj = context.project() or QgsProject.instance()
                if len(outs) == 1:
                    rel, base = outs[0]
                    nm = os.path.splitext(os.path.basename(rel))[0]
                    if lines_on and os.path.exists(base + "_garis.shp"):
                        context.addLayerToLoadOnCompletion(base + "_garis.shp", context.LayerDetails(
                            nm + " - garis kabel", prj, "GARIS"))
                    context.addLayerToLoadOnCompletion(base + "_titik.shp", context.LayerDetails(
                        nm + " - titik simbol", prj, "TITIK"))
                else:
                    context.addLayerToLoadOnCompletion(gp, context.LayerDetails("Semua titik simbol", prj,
                                                                                "SEMUA_TITIK"))
            except Exception as e:
                feedback.pushInfo("Hasil tidak dimuat otomatis: %s" % e)
        feedback.pushInfo("Selesai: %d berkas, %d OK, %d gagal, %d titik. Rekap: %s"
                          % (result["N_BERKAS"], result["N_OK"], result["N_GAGAL"], result["N_TITIK"], rp))
        return result
# RILIS-RESMI: v=1.3.0;sidik=92C4-D078-D1FC-1C5B;ttd=4055980310,238374854,3795081485,1437782851,3905353975,1972650170,215498051,980937509,2464659766,1815876563,2604530743,3621590505,1537173151,822144031,2428186733,3002370822

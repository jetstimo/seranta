# -*- coding: utf-8 -*-
"""
Seranta - FTTH Design Assistant
Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later.

QC LINTAS CLUSTER (cluster saudara)
-----------------------------------
Satu wilayah survei (mis. satu Funnel induk "RT 023 PASIR PUTIH") sering dipecah menjadi beberapa sub-cluster yang
disurvei dan diserahkan terpisah (RT 05, RT 22, RT 23, ...). Pemeriksaan per cluster tidak bisa melihat bahwa:
  1. rumah yang sama tercatat di dua cluster (HP duplikat lintas cluster: titik HPDB/KMZ disalin ke dua cluster);
  2. HP cluster ini masuk ke BOUNDARY cluster saudara;
  3. BOUNDARY dua cluster saling tumpang tindih;
  4. ID cluster yang sama dipakai di nama file dua cluster berbeda.
Pemeriksaan Funnel tidak menolong, karena semua sub-cluster berada di dalam SATU poligon Funnel induk yang sama.

Modul ini murni Python (tanpa QGIS) agar bisa diuji otomatis. Pembaca XLSX dan pencari file HPDB/KMZ disuntikkan
dari buat_input_desain (read_xlsx, find_hpdb, find_kmz, hpdb_candidates, kode_wilayah, cluster_label).

Dasar ambang (lihat DASAR_ATURAN.md):
  * koordinat sama <= 0,5 m = satu titik yang disalin (ERROR, sama dengan aturan duplikat di dalam cluster);
  * nomor rumah/nama titik sama dalam <= 15 m = rumah yang sama (GPS ponsel 4,9 m langit terbuka, GPS.gov;
    7-13 m di permukiman, Merry & Bettinger PLOS ONE 2019) -> ERROR;
  * 0,5-5 m dengan nomor rumah kosong = kemungkinan duplikat (INFO);
  * HP > 10 m di dalam BOUNDARY cluster saudara = ERROR; <= 10 m = INFO tepi (garis BOUNDARY digambar tangan).
"""
import math
import os
import re
import zipfile

try:
    from . import geodesi as _geo
except ImportError:          # diuji tanpa paket
    import geodesi as _geo

try:
    import defusedxml.ElementTree as ET
except ImportError:  # pragma: no cover
    import xml.etree.ElementTree as ET  # nosec B405

RULE_VERSION = "2026.11-r17"

HP_RX = re.compile(r"\b(hp|homepass|home ?pass|rumah)\b", re.IGNORECASE)
# 'EVIDEN' (tanpa -CE) dipakai vendor di KMZ 1 PIC Tomohon 2026; dulu tidak dikenali sebagai folder foto
EVID_RX = re.compile(r"evid[ae]n[cs]e|evid[ae]n\b|evident|foto|photo|dokumentasi", re.IGNORECASE)
DUPF_RX = re.compile(r"duplikat|duplicate|\berror\b", re.IGNORECASE)
BND_RX = re.compile(r"boundary|boundry|boundari|bondary|batas", re.IGNORECASE)
# NP6M / EP9M / TIANG7 / T6: kata tiang boleh menempel angka (nama folder vendor)
POLE_RX = re.compile(r"(?<![a-z])(poles?|tiang|np|ep|te)(?![a-z])|\bt\d{1,2}m?\b", re.IGNORECASE)
ROUTE_RX = re.compile(r"(?<![a-z])(routes?|cables?|kabel|jalur)(?![a-z])", re.IGNORECASE)
ID_RX = re.compile(r"(?<!\d)(\d{9,12})(?!\d)")
ZW_RX = re.compile(u"[\u200b-\u200f\u2060\ufeff]")
GENERIC_NAMES = {"", "HP", "HOMEPASS", "RUMAH", "UNTITLEDPLACEMARK", "TITIK", "POINT", "NA", "NONE", "NULL"}
SKIP_DIR_RX = re.compile(r"^(INPUT|HASIL|QC_|_|~)", re.IGNORECASE)
# jenis tiang (sama dengan buat_input_desain.EXIST_RX/NEW_RX): tiang eksisting dipakai bersama bukan BOQ tiang baru ganda
EXIST_POLE_RX = re.compile(r"\b(ep|ext|exs|exist\w*|eksist\w*|existing|te|tiang ?eksisting)\b|^(ep|te|ext)[\s\-_]?\d",
                           re.IGNORECASE)
NEW_POLE_RX = re.compile(r"\b(np|new|baru)\b|^np[\s\-_]?\d", re.IGNORECASE)


POLE_ROUTE_M = 5.0     # tiang cluster saudara <= 5 m dari jalur cluster itu = bagian jalurnya (GPS.gov 4,9 m)


def pole_kind_of(name, dirs=""):
    """'existing' / 'new' / '' dari nama tiang lalu folder terdalam (sama dengan buat_input_desain.pole_kind)."""
    folders = [f for f in str(dirs or "").split(" / ") if f]
    for t in [name or ""] + list(reversed(folders)):
        if NEW_POLE_RX.search(t):
            return "new"
        if EXIST_POLE_RX.search(t):
            return "existing"
    return ""


# ----------------------------------------------------------------------------------------- geometri
def dist_m(x1, y1, x2, y2):
    return _geo.dist_m(x1, y1, x2, y2)


def _pip(x, y, ring):
    """Titik di dalam cincin, aturan bilangan lilitan tidak nol (3.15.2; sama dengan buat_input_desain._pip): area yang
    dilingkupi dua kali oleh garis batas yang menimpa dirinya sendiri dihitung di dalam, bukan di luar."""
    wn, j = 0, len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if yj <= y:
            if yi > y and (xi - xj) * (y - yj) - (x - xj) * (yi - yj) > 0:
                wn += 1
        elif yi <= y and (xi - xj) * (y - yj) - (x - xj) * (yi - yj) < 0:
            wn -= 1
        j = i
    return wn != 0


def in_poly(x, y, poly):
    outer, holes = poly
    return _pip(x, y, outer) and not any(_pip(x, y, h) for h in holes)


def edge_dist_m(x, y, poly):
    kx, ky = _geo.m_per_deg(y)
    best = 1e9
    for r in [poly[0]] + list(poly[1]):
        for i in range(len(r)):
            ax, ay = (r[i - 1][0] - x) * kx, (r[i - 1][1] - y) * ky
            bx, by = (r[i][0] - x) * kx, (r[i][1] - y) * ky
            dx, dy = bx - ax, by - ay
            t = max(0.0, min(1.0, -(ax * dx + ay * dy) / ((dx * dx + dy * dy) or 1e-12)))
            best = min(best, math.hypot(ax + t * dx, ay + t * dy))
    return best


def depth_m(x, y, polys):
    """Kedalaman bertanda terhadap gabungan poligon: + di dalam (jarak ke tepi), - di luar. None bila tanpa poligon."""
    if not polys:
        return None
    inside = [p for p in polys if in_poly(x, y, p)]
    if inside:
        return max(edge_dist_m(x, y, p) for p in inside)
    return -min(edge_dist_m(x, y, p) for p in polys)


def _bbox_pts(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def _bbox_union(*bbs):
    bbs = [b for b in bbs if b]
    if not bbs:
        return None
    return (min(b[0] for b in bbs), min(b[1] for b in bbs), max(b[2] for b in bbs), max(b[3] for b in bbs))


def _bbox_gap_m(a, b):
    """Jarak (m) antara dua bbox; 0 bila bersinggungan."""
    if not a or not b:
        return 1e12
    dx = max(0.0, max(a[0], b[0]) - min(a[2], b[2]))
    dy = max(0.0, max(a[1], b[1]) - min(a[3], b[3]))
    kx, ky = _geo.m_per_deg((a[1] + a[3]) / 2.0)
    return math.hypot(dx * kx, dy * ky)


def round_area(a):
    """Luas hasil sampel grid dibulatkan sesuai resolusinya (galat sampel ~0,5-1 %): tampilan tidak memberi
    ketelitian semu dan tidak berubah karena pergeseran sampel sub-meter (uji stabilitas antar-wilayah)."""
    a = float(a or 0.0)
    step = 1.0 if a < 100 else 5.0 if a < 1000 else 10.0 if a < 10000 else 100.0
    return int(round(a / step) * step)


def overlap_area(polys_a, polys_b, max_samples=40000):
    """Luas irisan (m2) dua himpunan poligon, dihitung dengan sampel grid (cukup teliti untuk keputusan QC).
    Kembali (luas_m2, titik_tengah (x, y) atau None, [(x, y) sampel di irisan, maks 400])."""
    if not polys_a or not polys_b:
        return 0.0, None, []
    ba = _bbox_union(*[_bbox_pts(p[0]) for p in polys_a])
    bb = _bbox_union(*[_bbox_pts(p[0]) for p in polys_b])
    x0, y0, x1, y1 = max(ba[0], bb[0]), max(ba[1], bb[1]), min(ba[2], bb[2]), min(ba[3], bb[3])
    if x0 >= x1 or y0 >= y1:
        return 0.0, None, []
    kx, ky = _geo.m_per_deg((y0 + y1) / 2.0)
    w, h = (x1 - x0) * kx, (y1 - y0) * ky
    step = max(1.0, math.sqrt(w * h / float(max_samples)))
    nx, ny = max(1, int(w / step)), max(1, int(h / step))
    sx, sy = (x1 - x0) / nx, (y1 - y0) / ny
    # 3.15.3: sampel yang sama, dihitung per baris (garis sapuan): titik potong tiap cincin dengan baris y dicari sekali,
    # lalu tiap sampel cukup pencarian biner. Aturan di-dalam sama dengan _pip (bilangan lilitan), jadi hasilnya sama,
    # tetapi tidak lagi menelusuri semua titik sudut poligon untuk setiap sampel (dulu +-1 detik per pasangan cluster).
    from bisect import bisect_right

    def ring_row(ring, y):
        ev, j = [], len(ring) - 1
        for i in range(len(ring)):
            xi, yi = ring[i]
            xj, yj = ring[j]
            if yj <= y:
                if yi > y:
                    ev.append((xj + (y - yj) * (xi - xj) / (yi - yj), 1))
            elif yi <= y:
                ev.append((xj + (y - yj) * (xi - xj) / (yi - yj), -1))
            j = i
        ev.sort()
        suf = [0] * (len(ev) + 1)
        for k in range(len(ev) - 1, -1, -1):
            suf[k] = suf[k + 1] + ev[k][1]
        return [e[0] for e in ev], suf

    def rows(polys, y):
        return [(ring_row(p[0], y), [ring_row(h, y) for h in p[1]]) for p in polys]

    def inside(rw, x):
        for (xs, suf), holes in rw:
            if xs and suf[bisect_right(xs, x)] != 0 and not any(
                    hx and hs[bisect_right(hx, x)] != 0 for hx, hs in holes):
                return True
        return False
    found = []
    for j in range(ny):
        y = y0 + (j + 0.5) * sy
        ra, rb = rows(polys_a, y), rows(polys_b, y)
        for i in range(nx):
            x = x0 + (i + 0.5) * sx
            if inside(ra, x) and inside(rb, x):
                found.append((i, j, x, y))
    found.sort()                      # urutan sama dengan versi lama (x dulu, lalu y)
    hits = [(x, y) for _i, _j, x, y in found]
    if not hits:
        return 0.0, None, []
    area = len(hits) * (sx * kx) * (sy * ky)
    cx = sum(p[0] for p in hits) / len(hits)
    cy = sum(p[1] for p in hits) / len(hits)
    # titik tengah harus di dalam irisan (irisan bisa berbentuk L): ambil sampel terdekat ke rata-rata
    c = min(hits, key=lambda p: (p[0] - cx) ** 2 + (p[1] - cy) ** 2)
    stride = max(1, len(hits) // 400)
    return area, c, hits[::stride]


# ----------------------------------------------------------------------------------------- teks
def norm_name(v):
    """Nomor rumah / nama titik dinormalkan: '​Kantin Kaka' -> 'KANTINKAKA', 11 -> '11', '-' -> ''."""
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    t = ZW_RX.sub("", str(v)).upper()
    t = re.sub(r"[^A-Z0-9?]", "", t)
    if t.endswith(".0") and t[:-2].isdigit():
        t = t[:-2]
    t = t.strip("?") if t.strip("?") == "" else t
    return "" if t in GENERIC_NAMES or t in ("0", "-") else t


GENERIC_WORDS = {"RUMAH", "TOKO", "WARUNG", "KOS", "KOST", "KONTRAKAN", "RUKO", "KANTOR", "GUDANG", "BENGKEL",
                 "MASJID", "MUSHOLA", "MUSHALLA", "SEKOLAH", "KANTIN", "KIOS", "LAUNDRY", "SALON", "CAFE", "KAFE",
                 "KOSONG", "TANAH", "LAHAN", "BANGUNAN", "GEDUNG", "HP", "HOMEPASS", "RR", "NA"}


def norm_street(v):
    """Nama jalan dinormalkan: 'Jl. RB. Siagian' = 'RB SIAGIAN'; '-' -> ''."""
    t = ZW_RX.sub("", str(v or "")).upper()
    t = re.sub(r"\b(JL|JLN|JALAN|GG|GANG|LRG|LORONG)\b\.?", " ", t)
    t = re.sub(r"[^A-Z0-9]", "", t)
    return "" if t in ("", "0", "NA") else t


def norm_block(v):
    """Blok alamat dinormalkan: 'Blok C' = 'C', '-' -> ''. Dua rumah bernomor sama di blok berbeda = dua rumah."""
    t = ZW_RX.sub("", str(v or "")).upper()
    t = re.sub(r"\b(BLOK|BLOCK|BLK)\b\.?", " ", t)
    t = re.sub(r"[^A-Z0-9]", "", t)
    return "" if t in ("", "0", "NA") else t


def blocks_differ(a, b):
    """True bila kedua titik punya blok terisi dan berbeda (nomor rumah sama di blok lain bukan duplikat)."""
    a, b = a or "", b or ""
    return bool(a) and bool(b) and a != b


def label_kind(n):
    """Jenis label titik survei (n = hasil norm_name):
    'seq'  : nomor urut aplikasi survei (?327, N087) - unik per survei -> pengenal kuat;
    'name' : nama usaha/bangunan (TOKO TAUFIK, KOPYCO) - jarang berulang di sekitar -> pengenal kuat;
    'num'  : nomor rumah biasa (3, 11, 35B) - bisa berulang di gang lain -> pengenal lemah;
    ''     : kosong/generik."""
    if not n:
        return ""
    if re.match(r"^\?+[A-Z]?\d+[A-Z]?$", n) or re.match(r"^[A-Z]\d{3,}$", n):
        return "seq"
    if re.match(r"^\d{1,4}[A-Z]{0,2}$", n):
        return "num"
    letters = re.sub(r"[^A-Z]", "", n)
    if len(letters) >= 4 and n.lstrip("?") not in GENERIC_WORDS:
        return "gen" if generic_unit(n) else "name"
    return ""


_GEN_RX = re.compile(r"^(%s)(?:NO|NOMOR|NOMER|UNIT|BLOK|BLK)?([A-Z]{0,2}\d{1,4}[A-Z]{0,2})$"
                     % "|".join(sorted(GENERIC_WORDS - {"HP", "RR", "NA"}, key=len, reverse=True)))


def generic_unit(n):
    """Label umum = kata generik + nomor unit ('RUKO-1', 'Toko 2', 'KIOS A3', 'Kos No 12' -> ternormal RUKO1, TOKO2, ...).
    Penomoran unit seperti ini diulang di setiap deret bangunan/lingkungan (review Tomohon 2026: 'RUKO-1' L3 dan
    'Ruko-1' L7 berjarak 17 m), jadi label sama BUKAN bukti rumah yang sama: pengenal lemah. Kembali (kata, nomor) atau
    None. Hanya mempersempit jenis 'name' (tidak pernah membuat label baru dianggap pengenal)."""
    m = _GEN_RX.match((n or "").lstrip("?"))
    return (m.group(1), m.group(2)) if m else None


def series_relation(pa, pb, word):
    """Hubungan deret label umum '<word>-n' di dua cluster (review Tomohon 2026: L7 'Ruko-1..4' ke selatan dan L3
    'RUKO-1..2' ke utara, celah 17 m, jarak antarunit +-5 m = satu deret bangunan yang dinomori ulang per lingkungan).
    Kembali None bila salah satu deret < 2 unit; selain itu dict(n_a, n_b, celah, jarak_unit, pisah):
      celah      = jarak terdekat antara titik deret A dan deret B (m);
      jarak_unit = median jarak tetangga terdekat di dalam deret (m), yaitu lebar unit di lapangan;
      pisah      = celah > 1,5 x jarak_unit (deret tidak saling tumpang: unit berbeda). Hanya menambah keterangan;
                   tingkat temuan tetap WARNING (cek citra)."""
    def pts(hp):
        out = []
        for p in hp:
            g = generic_unit(norm_name(p.get("hn")))
            if g and g[0] == word and "x" in p and "y" in p:
                out.append((p["x"], p["y"]))
        return out
    a, b = pts(pa), pts(pb)
    if len(a) < 2 or len(b) < 2:
        return None

    def nn(ps):
        return [min(dist_m(x, y, u, v) for j, (u, v) in enumerate(ps) if j != i) for i, (x, y) in enumerate(ps)]
    sp = sorted(nn(a) + nn(b))
    unit = sp[len(sp) // 2]
    gap = min(dist_m(x, y, u, v) for x, y in a for u, v in b)
    return {"n_a": len(a), "n_b": len(b), "celah": gap, "jarak_unit": unit, "pisah": gap > 1.5 * max(unit, 1.0)}


def similar(a, b):
    """Kemiripan dua label nama (0-1), untuk salah ketik: 'KANTIN KAKA' vs 'KANTIN KAKAK'."""
    import difflib
    a, b = a.lstrip("?"), b.lstrip("?")
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def match_rank(d, a, b, dup_exact=0.5, dup_near=5.0, name_m=15.0, label_m=25.0, fuzzy_m=30.0, fuzzy=0.85, bldg_m=2.0,
               same_street=False, street_m=30.0, label_warn_m=50.0, gen_m=5.0):
    """Peringkat kecocokan dua titik HP (jarak d meter, label ternormal a & b). Pola diambil dari temuan tim QC
    (review Jambi): rumah dianggap sama bila titiknya disalin (koordinat sama) ATAU label survei/nama usahanya sama
    walau titik bergeser. Kembali (rank, alasan) atau None:
      0 koordinat sama                      -> ERROR
      1 label kuat sama (?NNN / nama usaha) dalam label_m, atau nomor rumah sama dalam name_m -> ERROR
      3 nama mirip (salah ketik) dalam fuzzy_m                                                 -> WARNING
      4 berimpit <= bldg_m dengan label berbeda (satu bangunan, dua titik)                    -> WARNING
      5 label kuat sama tetapi label_m-label_warn_m (duplikat atau salah ketik label)        -> WARNING
      6 label umum sama ('RUKO-1') pada gen_m-label_m: bisa unit lain bernomor sama -> WARNING (cek citra)
      2 0,5-5 m dengan label kosong                                                            -> INFO
    Label umum (kata generik + nomor unit) hanya pasti sama dalam gen_m; di luar label_m tidak dilaporkan."""
    if d <= dup_exact:
        return 0, "koordinat sama (%.1f m)" % d
    ka, kb = label_kind(a), label_kind(b)
    if a and a == b and ka == "gen":
        if d <= gen_m:
            return 1, "label umum sama '%s', titik bergeser %.1f m (<= %.0f m: unit yang sama)" % (a, d, gen_m)
        if d <= label_m:
            return 6, "label umum sama '%s' berjarak %.1f m (nomor unit dipakai ulang per deret), cek citra" % (a, d)
        return None
    if a and a == b:
        lim = label_m if ka in ("seq", "name") else (street_m if same_street else name_m)
        if d <= lim:
            return 1, "label survei/nomor rumah sama '%s'%s, titik bergeser %.1f m" % (
                a, " di jalan yang sama" if ka == "num" and same_street else "", d)
        if ka in ("seq", "name") and d <= label_warn_m:
            return 5, "label survei/nama sama '%s' tetapi berjarak %.1f m: rumah yang sama, atau salah label" % (a, d)
    if ka == "name" and kb == "name" and d <= fuzzy_m:
        r = similar(a, b)
        if r >= fuzzy:
            return 3, "nama mirip '%s' ~ '%s' (%.0f%%), berjarak %.1f m" % (a, b, r * 100, d)
    if d <= bldg_m and a and b and a != b:
        return 4, "dua titik berimpit %.1f m (label berbeda '%s' / '%s'): kemungkinan satu bangunan" % (d, a, b)
    if d <= dup_near and (not a or not b):
        return 2, "berjarak %.1f m, nomor rumah kosong" % d
    return None


RANK_ORDER = {0: 0, 1: 1, 5: 2, 6: 3, 3: 4, 4: 5, 2: 6}


def same_label_pairs(pts, label_m=25.0, name_m=15.0, dup_exact=0.5, street_m=30.0, label_warn_m=50.0, gen_m=5.0):
    """Di dalam SATU cluster: pasangan HP dengan label kuat yang sama (atau nomor rumah sama berdekatan) tetapi
    koordinat berbeda (> dup_exact; yang berimpit sudah dilaporkan sebagai duplikat koordinat).
    pts: [dict(x, y, hn)]. Kembali [(i, j, d, label, pasti)]; pasti=False untuk label kuat pada label_m-label_warn_m."""
    by = {}
    for i, p in enumerate(pts):
        n = norm_name(p.get("hn"))
        if label_kind(n):
            by.setdefault(n, []).append(i)
    out = []
    for n, ix in by.items():
        if len(ix) < 2:
            continue
        for a in range(len(ix)):
            for b in range(a + 1, len(ix)):
                i, j = ix[a], ix[b]
                if blocks_differ(pts[i].get("blk"), pts[j].get("blk")):
                    continue                     # nomor rumah sama di blok berbeda: dua rumah, bukan duplikat
                sa, sb = pts[i].get("adr", ""), pts[j].get("adr", "")
                d = dist_m(pts[i]["x"], pts[i]["y"], pts[j]["x"], pts[j]["y"])
                if label_kind(n) == "gen":           # label umum 'RUKO-1': pasti hanya <= gen_m, sampai label_m cek citra
                    if dup_exact < d <= gen_m:
                        out.append((i, j, d, n, True))
                    elif gen_m < d <= label_m and dup_exact < d:
                        out.append((i, j, d, n, False))
                    continue
                strong = label_kind(n) in ("seq", "name")
                lim = label_m if strong else (street_m if sa and sa == sb else name_m)
                if dup_exact < d <= lim:
                    out.append((i, j, d, n, True))
                elif strong and lim < d <= label_warn_m:
                    out.append((i, j, d, n, False))
    return out


def ids_in(*texts):
    out = set()
    for t in texts:
        for m in ID_RX.finditer(os.path.basename(str(t or ""))):
            out.add(m.group(1))
    return out


# ----------------------------------------------------------------------------------------- pembaca
def _strip(tag):
    return tag.rsplit("}", 1)[-1]


def _kml_bytes(path):
    if path.lower().endswith(".kmz"):
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if n.lower().endswith(".kml")]
            if not names:
                return None
            return z.read("doc.kml" if "doc.kml" in names else names[0])
    with open(path, "rb") as fh:
        return fh.read()


def _ring(el):
    txt = " ".join(x.text or "" for x in el.iter() if _strip(x.tag) == "coordinates")
    out = []
    for tok in txt.split():
        v = tok.split(",")
        if len(v) >= 2:
            try:
                out.append((float(v[0]), float(v[1])))
            except ValueError:
                pass
    if len(out) >= 3 and out[0] != out[-1]:
        out.append(out[0])
    return out


def read_kmz(path):
    """HP (titik di folder HP, tanpa folder bukti foto/duplikat), BOUNDARY (poligon di folder BOUNDARY), tiang."""
    res = {"hp": [], "bnd": [], "poles": [], "doc": "", "hp_dupf": 0, "lines": [], "pole_dirs": [], "hp_dirs": [],
           "folder_ids": {}, "bnd_names": []}
    data = _kml_bytes(path)
    if not data:
        return res
    root = ET.fromstring(data)  # nosec B314 - KMZ milik pengguna sendiri

    def walk(el, folders, is_doc=False):
        for ch in el:
            tag = _strip(ch.tag)
            if tag in ("Folder", "Document"):
                nm = ""
                for c in ch:
                    if _strip(c.tag) == "name":
                        nm = (c.text or "").strip()
                        break
                if tag == "Document" and not res["doc"]:
                    res["doc"] = nm
                walk(ch, folders + [nm] if tag == "Folder" else folders)
            elif tag == "Placemark":
                pname = ""
                for c in ch:
                    if _strip(c.tag) == "name":
                        pname = (c.text or "").strip()
                for g in ch.iter():
                    gt = _strip(g.tag)
                    if gt == "Polygon" and any(BND_RX.search(f) for f in folders):
                        outer, holes = [], []
                        for b in g:
                            bt = _strip(b.tag)
                            r = _ring(b)
                            if len(r) < 4:
                                continue
                            if bt == "outerBoundaryIs" and not outer:
                                outer = r
                            elif bt == "innerBoundaryIs":
                                holes.append(r)
                        if outer:
                            res["bnd"].append((outer, holes))
                            res["bnd_names"].append(pname)
                    elif gt == "LineString" and any(ROUTE_RX.search(f) for f in folders) \
                            and not any(BND_RX.search(f) for f in folders):
                        r = _ring(g)
                        if len(r) >= 2 and r[0] == r[-1] and len(r) > 3:
                            r = r[:-1]                   # _ring menutup cincin; garis kabel tidak ditutup
                        if len(r) >= 2:
                            res["lines"].append(r)
                    elif gt == "Point":
                        r = _ring(g)
                        if not r:
                            continue
                        x, y = r[0]
                        for f in folders:              # ID cluster lain yang tersisip sebagai sub-folder KMZ
                            for m_ in ID_RX.finditer(f):
                                res["folder_ids"].setdefault(m_.group(1), {"hp": 0, "pole": 0, "folder": f})
                        fid_ = [m_.group(1) for f in folders for m_ in ID_RX.finditer(f)]
                        if any(HP_RX.search(f) for f in folders):
                            if any(EVID_RX.search(f) for f in folders):
                                continue
                            if any(DUPF_RX.search(f) for f in folders):
                                res["hp_dupf"] += 1      # sudah ditandai surveyor sebagai duplikat
                                continue
                            res["hp"].append((x, y, pname))
                            res["hp_dirs"].append(" / ".join(folders))
                            if fid_:
                                res["folder_ids"][fid_[-1]]["hp"] += 1
                        elif any(POLE_RX.search(f) for f in folders):
                            res["poles"].append((x, y, pname))
                            res["pole_dirs"].append(" / ".join(folders))
                            if fid_:
                                res["folder_ids"][fid_[-1]]["pole"] += 1
    walk(root, [])
    return res


def _norm_h(s):
    return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())


def hpdb_points(sheets):
    """Dari list (nama_sheet, baris) -> [dict(x, y, hn, pid, row)]. Sheet dengan kolom HOMEPASS_LATITUDE/LONGITUDE
    diutamakan (bukan sheet POLE)."""
    best = None
    for name, rows in sheets:
        for i, r in enumerate(rows[:20]):
            hn = [_norm_h(c) for c in r]
            if any("LATITUDE" in c for c in hn) and any("LONGITUDE" in c for c in hn):
                sc = (5 if "HOMEPASSLATITUDE" in hn else 1) + (2 if re.search(r"HP|HOMEPASS", name or "", re.I) else 0)
                if best is None or sc > best[0]:
                    best = (sc, rows, i, hn)
                break
    if best is None:
        return []
    _sc, rows, h, hn = best

    def col(exact, contains=None):
        for e in exact:
            if e in hn:
                return hn.index(e)
        if contains:
            for i, c in enumerate(hn):
                if contains in c:
                    return i
        return None
    ilat = col(["HOMEPASSLATITUDE"], "LATITUDE")
    ilon = col(["HOMEPASSLONGITUDE"], "LONGITUDE")
    ihn = col(["HOMEPASSHOUSENUMBER"], "HOUSENUMBER")
    ipid = col(["HOMEPASSIDPARTNER"], "IDPARTNER")
    iadr = col(["HOMEPASSADDRESS"])
    iblk = col(["HOMEPASSADDRESSBLOCK"], "ADDRESSBLOCK")
    out = []
    for j, r in enumerate(rows[h + 1:], start=h + 2):
        if not r or not any(str(v).strip() for v in r if v is not None):
            continue

        def g(i):
            return r[i] if i is not None and i < len(r) else ""
        try:
            lat = float(str(g(ilat)).replace(",", ".").strip())
            lon = float(str(g(ilon)).replace(",", ".").strip())
        except (TypeError, ValueError):
            continue
        if -11.5 <= lon <= 6.5 and 94 <= lat <= 141.5:
            lat, lon = lon, lat
        if not (-11.5 <= lat <= 6.5 and 94 <= lon <= 141.5):
            continue
        out.append({"x": lon, "y": lat, "hn": str(g(ihn) if g(ihn) is not None else "").strip(),
                    "pid": str(g(ipid) or "").strip(), "row": j, "adr": norm_street(g(iadr)),
                    "blk": norm_block(g(iblk))})
    return out


def _read_csv(path):
    import csv
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            with open(path, newline="", encoding=enc) as fh:
                sample = fh.read(4096)
                fh.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
                except csv.Error:
                    dialect = csv.excel
                return [("csv", [list(r) for r in csv.reader(fh, dialect)])]
        except UnicodeDecodeError:
            continue
    return []


# ----------------------------------------------------------------------------------------- cluster
def load_cluster(cdir, helpers, hpdb=None, kmz=None, near_bbox=None, near_km=2.0):
    """Baca satu folder cluster saudara. helpers: dict fungsi dari buat_input_desain
    (find_hpdb, find_kmz, read_xlsx, kode_wilayah, cluster_label). Kembali dict atau None bila tidak bisa dibaca."""
    note = []
    try:
        hpdb = hpdb or helpers["find_hpdb"](cdir)
    except Exception as e:
        hpdb, _ = None, note.append("HPDB tidak dipilih: %s" % str(e)[:120])
    try:
        kmz = kmz or helpers["find_kmz"](cdir)
    except Exception as e:
        kmz, _ = None, note.append("KMZ tidak dipilih: %s" % str(e)[:120])
    pts, k = [], {"hp": [], "bnd": [], "poles": [], "doc": "", "hp_dupf": 0, "lines": [], "folder_ids": {}}
    if kmz:
        try:
            k = read_kmz(kmz)
        except Exception as e:
            note.append("KMZ gagal dibaca: %s" % str(e)[:120])
    kbb = _bbox_union(_bbox_pts([(x, y) for x, y, _n in k["hp"]]), *[_bbox_pts(b[0]) for b in k["bnd"]])
    tsha = ""
    if helpers.get("tssr_sha"):
        try:
            tsha = helpers["tssr_sha"](cdir) or ""
        except Exception:
            tsha = ""
    if near_bbox and kbb and _bbox_gap_m(near_bbox, kbb) > near_km * 1000.0:
        # cluster jauh: HPDB tidak perlu dibaca. bbox ikut disimpan: hasil ini di-cache per folder dalam mode batch,
        # dan cluster yang jauh dari cluster A bisa bertetangga dengan cluster B (review Minahasa 2026: 2547640213 dibaca
        # 'jauh' saat memproses 2547640209 lalu ikut dianggap jauh saat memproses 2547640211 yang bersebelahan).
        return {"far": True, "dir": cdir, "bbox": kbb, "tssr_sha": tsha}
    if hpdb:
        try:
            ext = os.path.splitext(hpdb)[1].lower()
            sheets = _read_csv(hpdb) if ext == ".csv" else (helpers["read_xlsx"](hpdb) if ext in (".xlsx", ".xlsm") else [])
            pts = hpdb_points(sheets)
        except Exception as e:
            note.append("HPDB gagal dibaca: %s" % str(e)[:120])
    src = "HPDB"
    if not pts and k["hp"]:
        pts = [{"x": x, "y": y, "hn": nm, "pid": "", "row": None} for x, y, nm in k["hp"]]
        src = "KMZ"
    if not pts and not k["bnd"]:
        return None
    label = helpers["cluster_label"](cdir, hpdb or "")
    bsha = ""
    if helpers.get("bakp_sha"):
        try:
            bsha = helpers["bakp_sha"](cdir) or ""
        except Exception:
            bsha = ""
    return {"dir": cdir, "label": label, "kode": helpers["kode_wilayah"](cdir, hpdb or ""),
            "hpdb": hpdb, "kmz": kmz, "hp": pts, "hp_src": src, "bnd": k["bnd"], "poles": k["poles"],
            "bnd_name": next((n_ for n_ in k.get("bnd_names") or [] if n_), ""),
            "lines": k.get("lines", []), "folder_ids": k.get("folder_ids", {}), "bakp_sha": bsha, "tssr_sha": tsha,
            "pole_kinds": [pole_kind_of(n_, d_) for (_x, _y, n_), d_ in
                           zip(k["poles"], k.get("pole_dirs") or [""] * len(k["poles"]))],
            "doc": k["doc"], "note": note,
            "ids_hpdb": ids_in(hpdb), "ids_other": ids_in(kmz, k["doc"], cdir) - ids_in(hpdb),
            "bbox": _bbox_union(_bbox_pts([(p["x"], p["y"]) for p in pts]),
                                *[_bbox_pts(b[0]) for b in k["bnd"]])}


def sibling_dirs(outdir, has_hpdb, extra=(), max_dirs=120):
    """Folder cluster saudara: subfolder lain di folder induk yang berisi HPDB (dan satu tingkat lebih dalam untuk
    hasil ekstrak ZIP bertingkat), ditambah folder pembanding pilihan pengguna (satu folder cluster atau folder induk)."""
    own = os.path.normcase(os.path.abspath(outdir))
    seen, out = {own}, []

    def subdirs(d):
        try:
            return [os.path.join(d, x) for x in sorted(os.listdir(d))
                    if os.path.isdir(os.path.join(d, x)) and not SKIP_DIR_RX.match(x)]
        except OSError:
            return []

    def ok(d):
        try:
            return bool(has_hpdb(d))
        except Exception:
            return False

    def add(d):
        n = os.path.normcase(os.path.abspath(d))
        if n in seen or own.startswith(n + os.sep) or n.startswith(own + os.sep):
            return False
        seen.add(n)
        pb = os.path.join(d, "_PER_BERKAS")
        if os.path.isdir(pb):
            # 3.14.0: folder berisi beberapa cluster yang sudah dipecah per berkas -> saudara = tiap cluster di dalamnya
            hit = False
            for c in subdirs(pb):
                hit = add(c) or hit
            return hit
        if ok(d):
            out.append(d)
            return True
        return False

    parent = os.path.dirname(os.path.abspath(outdir))
    roots = [parent]
    for e in extra or []:
        if e and os.path.isdir(e):
            if ok(e):
                add(e)                       # folder pembanding = satu folder cluster
            else:
                roots.append(e)              # folder pembanding = folder induk

    def scan(r):
        for d in subdirs(r):
            if len(out) >= max_dirs:
                return
            if not add(d):
                for d2 in subdirs(d)[:20]:   # ZIP bertingkat: FOLDER/FOLDER/<file>
                    add(d2)
    for r in roots:
        scan(r)
    # Folder cluster bertingkat (mis. MINAHASA/<ID>_..._78HP_RPS/<ID> - ... (78HP)/HPDB.xlsx): folder induk langsung
    # hanya berisi cluster ini sendiri, jadi cluster saudara ada satu tingkat di atasnya. Naik maks 2 tingkat selama
    # belum ada saudara dan folder induk tidak berisi HPDB sendiri.
    up = parent
    for _lvl in range(2):
        if out or len(out) >= max_dirs:
            break
        gp = os.path.dirname(up)
        if not gp or gp == up or ok(up):
            break
        scan(gp)
        up = gp
    return out


# ----------------------------------------------------------------------------------------- pembanding
def _grid(pts, cell):
    """cell: (derajat bujur, derajat lintang) dari geodesi.cell_deg."""
    g = {}
    for i, p in enumerate(pts):
        g.setdefault(_geo.cell_of(p["x"], p["y"], cell), []).append(i)
    return g


def _near(g, cell, x, y):
    cx, cy = _geo.cell_of(x, y, cell)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for i in g.get((cx + dx, cy + dy), ()):
                yield i


def _nearest_pole(x, y, poles):
    if not poles:
        return None
    return min(dist_m(x, y, px, py) for px, py, _n in poles)


def _bnd_gap_m(A, B):
    """Jarak terdekat (m) antara dua himpunan poligon BOUNDARY (0 bila beririsan/bersinggungan); pendekatan titik
    sudut ke tepi, cukup untuk memutuskan 'berdampingan' (<= beberapa meter)."""
    if not A or not B:
        return None
    best = 1e12
    # 3.15.3: kotak pembatas tiap poligon dipakai sebagai batas bawah jarak (hasil sama persis): poligon yang kotaknya
    # tidak memuat titik tidak diuji 'di dalam', dan poligon yang kotaknya sudah lebih jauh dari jarak terbaik dilewati.
    for P, Q in ((A, B), (B, A)):
        qb = [(q, _bbox_pts(q[0])) for q in Q]
        for poly in P:
            for x, y in poly[0][::max(1, len(poly[0]) // 400)]:
                if any(b and b[0] <= x <= b[2] and b[1] <= y <= b[3] and in_poly(x, y, q) for q, b in qb):
                    return 0.0
                kx, ky = _geo.m_per_deg(y)
                for q, b in qb:
                    if b and math.hypot(max(0.0, b[0] - x, x - b[2]) * kx, max(0.0, b[1] - y, y - b[3]) * ky) >= best:
                        continue
                    best = min(best, edge_dist_m(x, y, q))
    return best


def _pt_seg_m(x, y, a, b):
    kx, ky = _geo.m_per_deg(y)
    ax, ay = (a[0] - x) * kx, (a[1] - y) * ky
    bx, by = (b[0] - x) * kx, (b[1] - y) * ky
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, -(ax * dx + ay * dy) / ((dx * dx + dy * dy) or 1e-12)))
    return math.hypot(ax + t * dx, ay + t * dy)


def shared_poles(own_poles, sib_poles, same_m=1.0):
    """Tiang yang tercatat di dua cluster (koordinat <= same_m).
    -> [(x, y, nama_sendiri, nama_saudara, jarak, indeks_sendiri, indeks_saudara)]"""
    out = []
    if not own_poles or not sib_poles:
        return out
    cell = _geo.cell_deg(max(same_m, 1.0), [p[1] for p in own_poles] + [p[1] for p in sib_poles])
    g = {}
    for j, (x, y, _n) in enumerate(sib_poles):
        g.setdefault(_geo.cell_of(x, y, cell), []).append(j)
    used = set()
    for i_own, (x, y, n) in enumerate(own_poles):
        cx, cy = _geo.cell_of(x, y, cell)
        best = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in g.get((cx + dx, cy + dy), ()):
                    if j in used:
                        continue
                    d = dist_m(x, y, sib_poles[j][0], sib_poles[j][1])
                    if d <= same_m and (best is None or d < best[0]):
                        best = (d, j)
        if best:
            used.add(best[1])
            out.append((x, y, n, sib_poles[best[1]][2], best[0], i_own, best[1]))
    return out


def lines_connected(own_lines, sib_lines, own_poles=(), sib_poles=(), tol_m=1.5):
    """True bila jalur kabel dua cluster tersambung: ujung/titik jalur satu cluster <= tol_m dari jalur cluster lain."""
    if not own_lines or not sib_lines:
        return False
    bb = _bbox_union(*[_bbox_pts(ln_) for ln_ in sib_lines])
    pad = tol_m / 90000.0
    for line in own_lines:
        for x, y in line:
            if bb and not (bb[0] - pad <= x <= bb[2] + pad and bb[1] - pad <= y <= bb[3] + pad):
                continue
            for sl in sib_lines:
                for i in range(1, len(sl)):
                    if _pt_seg_m(x, y, sl[i - 1], sl[i]) <= tol_m:
                        return True
    return False


def bnd_fingerprint(bnd, nd=6):
    """Sidik poligon BOUNDARY (titik dibulatkan 1e-6 derajat +-0,1 m, urutan & arah titik diabaikan): sama = poligon yang
    disalin. '' bila tidak ada BOUNDARY."""
    if not bnd:
        return ""
    rings = []
    for b in bnd:
        outer = b[0] if b and isinstance(b[0], (list, tuple)) and b[0] and isinstance(b[0][0], (list, tuple)) else b
        pts = sorted({(round(x, nd), round(y, nd)) for x, y in outer})
        rings.append(tuple(pts))
    return repr(sorted(rings))


def shared_route_m(own_lines, sib_lines, tol_m=2.0, step_m=2.0, max_angle=20.0):
    """Panjang (m) jalur kabel cluster ini yang menumpuk di atas jalur cluster lain: titik sampel tiap step_m di ruas
    sendiri yang <= tol_m dari ruas saudara yang searah (selisih arah <= max_angle derajat). Ruas yang hanya bersentuhan
    di ujung/simpang menghasilkan beberapa meter saja; jalur yang digambar dua kali (satu jaringan 1 PIC yang dimasukkan
    ke dua KMZ) menghasilkan puluhan-ratusan meter. -> (panjang_m, titik_tengah_bertumpuk atau None)."""
    if not own_lines or not sib_lines:
        return 0.0, None
    segs = []
    for sl in sib_lines:
        for i in range(1, len(sl)):
            a, b = sl[i - 1], sl[i]
            segs.append((a, b, min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])))
    if not segs:
        return 0.0, None
    pad = tol_m / 90000.0
    cos_lim = math.cos(math.radians(max_angle))
    total, hits = 0.0, []
    for line in own_lines:
        for i in range(1, len(line)):
            a, b = line[i - 1], line[i]
            kx, ky = _geo.m_per_deg((a[1] + b[1]) / 2.0)
            vx, vy = (b[0] - a[0]) * kx, (b[1] - a[1]) * ky
            L = math.hypot(vx, vy)
            if L < 0.01:
                continue
            cand = [s for s in segs if not (s[4] < min(a[0], b[0]) - pad or s[2] > max(a[0], b[0]) + pad or
                                            s[5] < min(a[1], b[1]) - pad or s[3] > max(a[1], b[1]) + pad)]
            par = []
            for s in cand:
                wx, wy = (s[1][0] - s[0][0]) * kx, (s[1][1] - s[0][1]) * ky
                W = math.hypot(wx, wy)
                if W >= 0.01 and abs(vx * wx + vy * wy) / (L * W) >= cos_lim:
                    par.append(s)
            if not par:
                continue
            n = max(1, int(math.ceil(L / step_m)))
            for k in range(n):
                t = (k + 0.5) / n
                x, y = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
                if any(_pt_seg_m(x, y, s[0], s[1]) <= tol_m for s in par):
                    total += L / n
                    hits.append((x, y))
    mid = hits[len(hits) // 2] if hits else None
    return total, mid


def seq_labels_restart(own_hp, sib_hp, min_common=5, frac=0.5, far_m=100.0):
    """True bila penomoran label survei urut (?NNN) DIULANG di cluster saudara: sebagian besar label urut cluster yang
    lebih kecil juga ada di cluster lain, tetapi pasangan berlabel sama berjauhan (median > far_m). Pola KMZ 1 PIC
    (review Tomohon 2026: tiap lingkungan mulai lagi dari '? -1'; 72-98% label sama, median 116-699 m). Pada pasangan
    seperti itu label urut bukan pengenal rumah lintas cluster; duplikat tetap dikenali dari koordinat."""
    def seqs(pts):
        out = {}
        for p in pts:
            n = norm_name(p.get("hn"))
            if label_kind(n) == "seq":
                out.setdefault(n, []).append(p)
        return out
    a, b = seqs(own_hp), seqs(sib_hp)
    if not a or not b:
        return False
    common = set(a) & set(b)
    if len(common) < min_common or len(common) < frac * min(len(a), len(b)):
        return False
    ds = sorted(min(dist_m(p["x"], p["y"], q["x"], q["y"]) for p in a[n] for q in b[n]) for n in common)
    return ds[len(ds) // 2] > far_m


def compare(own, sibs, dup_exact=0.5, dup_near=5.0, name_m=15.0, bnd_tol=10.0, near_km=2.0, same_frac=0.6,
            label_m=25.0, fuzzy_m=30.0, fuzzy=0.85, bldg_m=2.0, street_m=30.0, label_warn_m=50.0,
            pole_same_m=1.0, pic_gap_m=300.0, hp_per_spl=32, fdt_cap=384, ratio=4, induk_frac=0.5, route_dup_m=30.0,
            gen_m=5.0, tol_1pic=True):
    """own: dict(label, kode, hp=[dict(x, y, hn, hid)], bnd, poles=[(x, y, nama)], ids_hpdb, ids_other, bbox).
    sibs: hasil load_cluster. Kembali dict(findings, report, counts, used, skipped, scene)."""
    res = {"findings": [], "report": [], "used": [], "skipped": [], "counts": {}, "scene": {"bnd": [], "hp": []},
           "pic": []}
    F, R = res["findings"], res["report"]
    res["bnd_same"] = []
    own_fp = bnd_fingerprint(own.get("bnd"))
    own_bb = own.get("bbox") or _bbox_pts([(p["x"], p["y"]) for p in own["hp"]])
    reach = max(name_m, label_m, fuzzy_m, street_m, label_warn_m)
    cell = _geo.cell_deg(reach, [p["y"] for p in own["hp"]] +
                         [q["y"] for x in sibs if x and not x.get("far") for q in (x.get("hp") or [])])
    n_dup = n_maybe = n_warn = n_in = n_edge = n_ov = n_id = n_induk = n_induk_info = n_in_tol = 0
    dup_pairs = []
    # urutan saudara tetap (kode, label, folder): hasil & remarks tidak bergantung urutan folder di disk/zip
    sibs = sorted((x for x in sibs if x is not None),
                  key=lambda x: (str(x.get("kode") or ""), str(x.get("label") or ""), str(x.get("dir") or "")))
    for s in sibs:
        if s is None or s.get("far"):
            continue
        if s["kode"] == own["kode"]:
            res["skipped"].append((s["label"], "kode cluster sama (%s): versi lain cluster ini" % s["kode"]))
            continue
        gap = _bbox_gap_m(own_bb, s["bbox"])
        if gap > near_km * 1000.0:
            continue                                     # cluster jauh: bukan tetangga, tidak dilaporkan
        g = _grid(s["hp"], cell)
        # penomoran label urut diulang per cluster (KMZ 1 PIC): label urut tidak dipakai sebagai pengenal lintas cluster
        restart = seq_labels_restart(own["hp"], s["hp"], far_m=2.0 * label_warn_m)
        if restart:
            res["seq_restart"] = res.get("seq_restart", []) + [s["label"]]
        # ---- 1. HP duplikat lintas cluster ----
        matched = []
        for h in own["hp"]:
            best = None
            for j in _near(g, cell, h["x"], h["y"]):
                q = s["hp"][j]
                d = dist_m(h["x"], h["y"], q["x"], q["y"])
                if d > reach:
                    continue
                sa, sb = h.get("adr", ""), q.get("adr", "")
                na, nb = norm_name(h["hn"]), norm_name(q["hn"])
                if restart:
                    na = "" if label_kind(na) == "seq" else na
                    nb = "" if label_kind(nb) == "seq" else nb
                if na and na == nb and blocks_differ(h.get("blk"), q.get("blk")):
                    nb = nb + "#BLOK" + q.get("blk", "")   # nomor sama, blok beda -> bukan label yang sama
                m = match_rank(d, na, nb, dup_exact, dup_near, name_m, label_m,
                               fuzzy_m, fuzzy, bldg_m, bool(sa) and sa == sb, street_m, label_warn_m, gen_m)
                if m is None:
                    continue
                rank = m[0]
                if best is None or (RANK_ORDER[rank], d, j) < (RANK_ORDER[best[0]], best[1], best[2]):
                    best = (rank, d, j, m[1])
            if best is not None:
                matched.append((h, best))
        n_exact = sum(1 for _h, b in matched if b[0] == 0)
        if s["hp"] and n_exact >= same_frac * min(len(s["hp"]), len(own["hp"])) and n_exact >= 5:
            res["skipped"].append((s["label"], "%d dari %d HP berkoordinat sama dengan cluster ini: kemungkinan versi lain "
                                               "cluster yang sama (bukan cluster saudara)" % (n_exact, len(s["hp"]))))
            continue
        res["used"].append(s)
        res["scene"]["bnd"].extend((b, s["label"]) for b in s["bnd"])
        res["scene"]["hp"].extend((q["x"], q["y"], q["hn"], s["label"]) for q in s["hp"])
        dup_own = set()
        for h, (rank, d, j, why) in matched:
            q = s["hp"][j]
            dup_own.add(id(h))
            do, ds = depth_m(h["x"], h["y"], own["bnd"]), depth_m(q["x"], q["y"], s["bnd"])
            po, ps = _nearest_pole(h["x"], h["y"], own["poles"]), _nearest_pole(q["x"], q["y"], s["poles"])
            keep = _keep_advice(own["label"], s["label"], do, ds, po, ps)
            nm = h["hn"] or q["hn"] or "-"
            if rank == 6:
                gu = generic_unit(norm_name(h["hn"]) or norm_name(q["hn"]))
                rel = series_relation(own["hp"], s["hp"], gu[0]) if gu else None
                lab = norm_name(h["hn"]) or norm_name(q["hn"])
                if rel and rel["pisah"]:     # teks ringkas: kolom shapefile/kartu laporan dipotong +-250 karakter
                    why = ("label umum '%s' sama, %.1f m; deret %s-n tidak tumpang (celah %.0f m, antarunit %.0f m): "
                           "kemungkinan unit berbeda, cek citra" % (lab, d, gu[0], rel["celah"], rel["jarak_unit"]))
                elif rel:
                    why = ("label umum '%s' sama, %.1f m; deret %s-n saling tumpang (celah %.0f m, antarunit %.0f m): "
                           "kemungkinan disurvei dua kali, cek citra" % (lab, d, gu[0], rel["celah"], rel["jarak_unit"]))
                keep = "Bila dari citra memang bangunan yang sama: " + keep[0].lower() + keep[1:] + \
                       " Bila berbeda: beri label unik/catat di remarks tambahan."
            ket = ("%s (no. rumah %s) juga tercatat di cluster %s%s: %s. %s" % (
                h["hid"], nm, s["label"], (" baris %d" % q["row"]) if q.get("row") else "", why, keep))
            kind = {0: "HP_DUPLIKAT_LINTAS_CLUSTER", 1: "HP_DUPLIKAT_LINTAS_CLUSTER",
                    3: "WARN_HP_MUNGKIN_DUPLIKAT_LINTAS_CLUSTER", 4: "WARN_HP_MUNGKIN_DUPLIKAT_LINTAS_CLUSTER",
                    5: "WARN_HP_MUNGKIN_DUPLIKAT_LINTAS_CLUSTER", 6: "WARN_HP_MUNGKIN_DUPLIKAT_LINTAS_CLUSTER",
                    2: "INFO_HP_MUNGKIN_DUPLIKAT_LINTAS_CLUSTER"}[rank]
            if rank in (0, 1):
                n_dup += 1
            elif rank in (3, 4, 5, 6):
                n_warn += 1
            else:
                n_maybe += 1
            dup_pairs.append((h["hid"], nm, s["label"], d, rank))
            F.append({"x": h["x"], "y": h["y"], "kind": kind, "ket": ket, "val": round(d, 1),
                      "lim": {0: dup_exact, 1: (label_m if label_kind(norm_name(nm)) in ("seq", "name") else
                                                gen_m if label_kind(norm_name(nm)) == "gen" else
                                                (street_m if h.get("adr") and h.get("adr") == q.get("adr") else name_m)),
                              3: fuzzy_m, 4: bldg_m, 5: label_warn_m, 6: label_m, 2: dup_near}[rank],
                      "line": [(h["x"], h["y"]), (q["x"], q["y"])] if d > 0.05 else None,
                      "other": s["label"], "other_row": q.get("row"), "other_file": s.get("hpdb") or s.get("kmz")})
        # BOUNDARY identik (poligon yang sama disalin ke KMZ beberapa cluster; review Jambi Suka Karya 2026: 7 KMZ RT memuat
        # BOUNDARY 'RT 014 SUKA KARYA KOTA BARU' yang sama persis): satu akar masalah untuk seluruh paket wilayah. Dilaporkan
        # SEKALI per cluster sebagai boundary induk (lihat setelah perulangan), bukan per pasangan cluster dan bukan per HP.
        same_bnd = bool(own_fp) and own_fp == bnd_fingerprint(s.get("bnd"))
        if same_bnd:
            res["bnd_same"].append(s)
        sb_ = [] if same_bnd else s["bnd"]
        ob_ = [] if same_bnd else own["bnd"]
        ov_ = None          # 3.10.0: data irisan pasangan ini untuk rekap grup (luas, HP di irisan kedua sisi)
        # ---- 5. Satu PIC desain / jaringan bersama (temuan review Jambi & Minahasa 2026) ----
        # Beberapa cluster sering didesain satu PIC sebagai SATU jaringan: tiang dipakai bersama (tercatat di dua KMZ),
        # kabel tersambung, satu cluster tersisip sebagai sub-folder KMZ cluster lain, BAKP yang sama, BOUNDARY
        # berdampingan/tumpang tindih. Per cluster semua itu tidak terlihat; di sini dikumpulkan sebagai sinyal.
        sp = shared_poles(own.get("poles") or [], s.get("poles") or [], pole_same_m)
        conn = lines_connected(own.get("lines") or [], s.get("lines") or [])
        # 3.10.0: panjang berimpit dihitung dua arah dan diambil yang terbesar, supaya kedua cluster melaporkan angka
        # yang sama (dulu RT 08->RT 16 45 m tetapi RT 16->RT 08 48 m untuk pasangan yang sama)
        if conn:
            rt_a = shared_route_m(own.get("lines") or [], s.get("lines") or [])
            rt_b = shared_route_m(s.get("lines") or [], own.get("lines") or [])
            rt_m = max(rt_a, rt_b, key=lambda t: (round(t[0], 3), t[1] is not None))[0]
        else:
            rt_m = 0.0
        rt_dup = rt_m >= route_dup_m
        gap_b = _bnd_gap_m(own.get("bnd") or [], s.get("bnd") or [])
        same_bakp = bool(own.get("bakp_sha")) and own.get("bakp_sha") == s.get("bakp_sha")
        sib_ids = s.get("ids_hpdb") or set()
        own_ids = own.get("ids_hpdb") or set()
        emb_in_own = sorted(i_ for i_ in (own.get("folder_ids") or {}) if i_ in sib_ids)
        emb_in_sib = sorted(i_ for i_ in (s.get("folder_ids") or {}) if i_ in own_ids)
        sig = []
        if sp:
            sig.append("%d tiang sama koordinat" % len(sp))
        if conn:
            sig.append("jalur kabel tersambung")
        if rt_dup:
            sig.append("jalur berimpit +-%.0f m" % rt_m)
        if emb_in_own:
            sig.append("KMZ cluster ini memuat folder cluster %s" % ", ".join(emb_in_own))
        if emb_in_sib:
            sig.append("KMZ %s memuat folder cluster ini" % s["label"])
        if same_bakp:
            sig.append("file BAKP identik")
        if same_bnd:
            sig.append("BOUNDARY identik%s" % ((" ('%s')" % own.get("bnd_name")) if own.get("bnd_name") else ""))
        elif gap_b is not None and gap_b <= 5.0:
            sig.append("BOUNDARY %s" % ("tumpang tindih/bersinggungan" if gap_b == 0 else "berdampingan %.0f m" % gap_b))
        one_net = bool(sp or conn or emb_in_own or emb_in_sib)
        maybe = (not one_net) and bool(same_bakp or (gap_b is not None and gap_b <= 5.0)) and gap <= pic_gap_m
        # ---- 3.11.0: toleransi boundary bertumpuk dalam 1 PIC / berdampingan (revisi pembuat, 5 Nov 2026) ----
        # Boundary wilayah RT/RW/lingkungan yang didesain satu PIC atau berdampingan BOLEH bertumpuk; yang tetap salah
        # adalah boundary yang masuk ke FUNNEL lain. Pasangan ditoleransi bila (1) satu jaringan / 1 PIC / berdampingan,
        # (2) funnel kedua cluster sama, atau - bila funnel tidak bisa dicek (tanpa data referensi) - ada bukti satu
        # wilayah induk (BAKP/TSSR identik, BOUNDARY induk sama). Funnel berbeda = LINTAS FUNNEL, tetap ERROR.
        same_tssr = bool(own.get("tssr_sha")) and own.get("tssr_sha") == s.get("tssr_sha")
        of_, sf_ = own.get("funnel_key") or "", s.get("funnel_key") or ""
        beda_funnel = bool(of_ and sf_ and of_ != sf_)
        # 3.14.0 (diuji lalu DITOLAK): nama wilayah induk yang sama BUKAN bukti satu funnel. Uji di QGIS pengguna dengan
        # data funnel asli: 7 lingkungan KAKASKASEN (Tomohon) masing-masing funnel sendiri -> bila nama dipakai, tiang
        # saudara lintas funnel ikut dihitung dan LINGKUNGAN 7 lolos 'Approve dgn catatan' padahal seharusnya Reject.
        # Tanpa data funnel/dokumen, boundary bertumpuk tetap tidak ditoleransi (aman), dengan catatan funnel belum dicek.
        satu_induk = (bool(of_) and of_ == sf_) or ((not of_ or not sf_) and bool(same_bakp or same_tssr or same_bnd))
        tol = bool(tol_1pic) and bool(one_net or maybe) and satu_induk and not beda_funnel
        fun_txt = (" LINTAS FUNNEL: funnel cluster ini '%s', cluster %s di funnel '%s'." % (
            own.get("funnel") or of_, s["label"], s.get("funnel") or sf_)) if beda_funnel else ""
        why_tol = ("funnel sama '%s'" % (own.get("funnel") or of_)) if of_ and of_ == sf_ else \
            ("satu wilayah induk: %s" % ", ".join(w_ for w_, ok_w in (("BAKP identik", same_bakp), ("TSSR identik", same_tssr),
                                                                     ("BOUNDARY induk sama", same_bnd)) if ok_w))
        # ---- 2. HP cluster ini di dalam BOUNDARY cluster saudara ----
        # BOUNDARY induk/gabungan (review Jambi 2026: KMZ Bagan Pete RT 04 masih memuat BOUNDARY 390 HP sebelum dipecah,
        # sehingga 158 HP Pinang Merah dan 85 HP Simpang Rimbo 'masuk BOUNDARY cluster saudara'). Bila BOUNDARY satu
        # cluster menelan sebagian besar HP cluster lain, akar masalahnya satu: BOUNDARY itu belum dipotong. Kesalahan
        # dilaporkan sekali di cluster pemilik BOUNDARY besar (ERROR), di cluster lain cukup satu catatan.
        own_in_s = [h for h in own["hp"] if sb_ and in_poly_any(h["x"], h["y"], sb_)]
        s_in_own = [q for q in s["hp"] if ob_ and in_poly_any(q["x"], q["y"], ob_)]
        sib_induk = bool(sb_) and len(own_in_s) >= max(5, induk_frac * len(own["hp"]))
        own_induk = bool(ob_) and len(s_in_own) >= max(5, induk_frac * len(s["hp"]))
        if sib_induk:
            n_induk_info += 1
            c0 = own_in_s[len(own_in_s) // 2]
            F.append({"x": c0["x"], "y": c0["y"], "kind": "INFO_HP_DI_BOUNDARY_INDUK_CLUSTER_LAIN",
                      "ket": "%d dari %d HP cluster ini%s berada di dalam BOUNDARY cluster %s, yang ternyata memuat sebagian "
                             "besar cluster ini: BOUNDARY %s kemungkinan masih BOUNDARY induk/gabungan sebelum dipecah. "
                             "Perbaiki BOUNDARY di cluster %s; di cluster ini cukup dicatat (bukan HP salah cluster)."
                             % (len(own_in_s), len(own["hp"]), _rows_txt(own_in_s), s["label"], s["label"], s["label"]),
                      "val": len(own_in_s), "lim": None, "line": None, "other": s["label"], "unit": "HP"})
        if sb_ and not sib_induk:
            for h in own["hp"]:
                if id(h) in dup_own:
                    continue                             # satu akar masalah, satu temuan (sudah di duplikat)
                inside = [b for b in sb_ if in_poly(h["x"], h["y"], b)]
                if not inside:
                    continue
                dep = max(edge_dist_m(h["x"], h["y"], b) for b in inside)
                own_in = bool(ob_) and any(in_poly(h["x"], h["y"], b) for b in ob_)
                tail = (" BOUNDARY cluster ini dan %s tumpang tindih di titik ini." % s["label"]) if own_in else ""
                if dep > bnd_tol and tol:
                    n_in_tol += 1
                    po_ = _nearest_pole(h["x"], h["y"], own["poles"])
                    ps_ = _nearest_pole(h["x"], h["y"], s["poles"])
                    hint_ = (" Tiang terdekat ada di cluster %s (%.0f m, di cluster ini %.0f m): pertimbangkan rumah ini "
                             "masuk cluster %s." % (s["label"], ps_, po_, s["label"])) \
                        if po_ is not None and ps_ is not None and ps_ + 10.0 < po_ else ""
                    F.append({"x": h["x"], "y": h["y"], "kind": "INFO_HP_DI_BOUNDARY_SAUDARA_1PIC",
                              "ket": "%s (no. rumah %s) %.1f m di dalam BOUNDARY cluster %s - 1 PIC/berdampingan, %s: "
                                     "boundary bertumpuk diterima, bukan alasan reject. Pastikan rumah ini hanya tercatat di "
                                     "HPDB satu cluster.%s" % (h["hid"], h["hn"] or "-", dep, s["label"], why_tol, hint_),
                              "val": round(dep, 1), "lim": bnd_tol, "line": None, "other": s["label"]})
                elif dep > bnd_tol:
                    n_in += 1
                    F.append({"x": h["x"], "y": h["y"], "kind": "HP_DI_BOUNDARY_CLUSTER_LAIN",
                              "ket": "%s (no. rumah %s) berada %.1f m di dalam BOUNDARY cluster %s (> %.0f m).%s%s Tentukan "
                                     "satu cluster pemilik rumah ini; keluarkan dari cluster yang lain dan rapikan BOUNDARY."
                                     % (h["hid"], h["hn"] or "-", dep, s["label"], bnd_tol, tail, fun_txt),
                              "val": round(dep, 1), "lim": bnd_tol, "line": None, "other": s["label"]})
                else:
                    n_edge += 1
                    F.append({"x": h["x"], "y": h["y"], "kind": "INFO_HP_TEPI_BOUNDARY_CLUSTER_LAIN",
                              "ket": "%s (no. rumah %s) %.1f m di dalam tepi BOUNDARY cluster %s (dalam toleransi GPS %.0f m)"
                                     % (h["hid"], h["hn"] or "-", dep, s["label"], bnd_tol),
                              "val": round(dep, 1), "lim": bnd_tol, "line": None, "other": s["label"]})
        # ---- 3. BOUNDARY tumpang tindih ----
        if ob_ and sb_ and own_induk:
            n_ov += 1
            n_induk += 1
            c0 = s_in_own[len(s_in_own) // 2]
            F.append({"x": c0["x"], "y": c0["y"], "kind": "BOUNDARY_MEMUAT_CLUSTER_LAIN",
                      "ket": "BOUNDARY cluster ini memuat %d dari %d HP cluster %s%s: BOUNDARY masih BOUNDARY induk/gabungan "
                             "(belum dipotong sesuai HP cluster ini). Gambar ulang BOUNDARY hanya di sekitar HP cluster ini."
                             % (len(s_in_own), len(s["hp"]), s["label"], _rows_txt(s_in_own)),
                      "val": len(s_in_own), "lim": None, "line": None, "other": s["label"], "unit": "HP"})
        elif ob_ and sb_ and sib_induk:
            n_ov += 1
            c0 = own_in_s[len(own_in_s) // 2]
            F.append({"x": c0["x"], "y": c0["y"], "kind": "INFO_BOUNDARY_BERIRISAN_CLUSTER_LAIN",
                      "ket": "BOUNDARY cluster ini berada di dalam BOUNDARY induk/gabungan cluster %s (lihat catatan BOUNDARY "
                             "induk); perbaikan ada di cluster %s." % (s["label"], s["label"]),
                      "val": None, "lim": None, "line": None, "other": s["label"]})
        elif ob_ and sb_:
            area, c, samples = overlap_area(ob_, sb_)
            area = round_area(area)
            if area > 0 and c:
                deep_own = [h for h in own["hp"] if in_poly_any(h["x"], h["y"], sb_) and in_poly_any(h["x"], h["y"], ob_)]
                deep_sib = [q for q in s["hp"] if in_poly_any(q["x"], q["y"], sb_) and in_poly_any(q["x"], q["y"], ob_)]
                # lebar irisan = jarak terjauh sampel irisan dari tepi poligon terdekat (pendekatan setengah lebar)
                width = 2.0 * max((min(edge_dist_m(x, y, b) for b in ob_ + sb_) for x, y in samples), default=0)
                serious = bool(deep_own or deep_sib) and width > bnd_tol
                ov_ = {"m2": area, "width": round(width, 1), "serious": serious, "tolerated": tol, "beda_funnel": beda_funnel,
                       "own_rows": sorted(int(h["row"]) for h in deep_own if h.get("row")),
                       "sib_rows": sorted(int(q["row"]) for q in deep_sib if q.get("row")),
                       "n_own": len(deep_own), "n_sib": len(deep_sib)}
                n_ov += 1
                F.append({"x": c[0], "y": c[1],
                          "kind": ("INFO_BOUNDARY_BERIRISAN_1PIC" if serious and tol else
                                   "WARN_BOUNDARY_BERIRISAN_CLUSTER_LAIN" if serious else "INFO_BOUNDARY_BERIRISAN_CLUSTER_LAIN"),
                          "ket": "BOUNDARY cluster ini tumpang tindih dengan BOUNDARY cluster %s: luas irisan +-%.0f m2, "
                                 "lebar maks +-%.0f m; di dalam irisan ada %d HP cluster ini%s dan %d HP cluster %s%s. %s"
                                 % (s["label"], area, width, len(deep_own), _rows_txt(deep_own), len(deep_sib), s["label"],
                                    _rows_txt(deep_sib),
                                    ("Boundary bertumpuk dalam 1 PIC/berdampingan (%s): diterima, bukan alasan reject; "
                                     "pastikan setiap rumah hanya di HPDB satu cluster." % why_tol) if serious and tol else
                                    ("Rapikan garis BOUNDARY agar satu rumah hanya masuk satu cluster." + fun_txt) if serious else
                                    "Irisan tipis di garis batas bersama (wajar untuk garis yang digambar tangan)."),
                          "val": round(area, 0), "lim": None, "line": None, "other": s["label"], "unit": "m2"})
        # ---- 4. ID cluster dipakai cluster lain ----
        own_h, own_o = own.get("ids_hpdb", set()), own.get("ids_other", set())
        same_any = (own_h | own_o) & (s["ids_hpdb"] | s["ids_other"])
        if same_any:
            n_id += 1
            ids = ", ".join(sorted(same_any))
            where = []
            if s["ids_hpdb"] & same_any:
                where.append("nama file HPDB")
            if s["kmz"] and ids_in(s["kmz"]) & same_any:
                where.append("nama file KMZ")
            if ids_in(s["doc"]) & same_any:
                where.append("nama dokumen di dalam KMZ")
            if own_h & s["ids_hpdb"]:
                kind, lead = "WARN_ID_CLUSTER_GANDA", "HPDB cluster ini dan HPDB cluster %s memakai ID cluster yang sama %s." % (s["label"], ids)
            elif (own_o & s["ids_hpdb"]) and not (own_h & same_any):
                kind, lead = ("WARN_ID_CLUSTER_GANDA", "KMZ/folder cluster ini memakai ID %s, padahal ID itu tercantum di nama "
                              "HPDB cluster %s (kemungkinan salin-tempel nama file)." % (ids, s["label"]))
            else:
                kind, lead = "INFO_ID_CLUSTER_SAMA_DI_CLUSTER_LAIN", "ID cluster %s juga dipakai cluster %s (%s)." % (
                    ids, s["label"], ", ".join(where) or "nama file")
            F.append({"x": own["hp"][0]["x"], "y": own["hp"][0]["y"], "kind": kind,
                      "ket": lead + " Pastikan setiap cluster memakai ID-nya sendiri di HPDB, KMZ dan BAKP; bila ini ID "
                                    "induk Funnel yang memang dipakai bersama, cukup dicatat.",
                      "val": None, "lim": None, "line": None, "other": s["label"]})
        # ---- 5. (sinyal dihitung lebih awal, lihat sebelum langkah 2) ----
        ok_ = own.get("pole_kinds") or []
        sk_ = s.get("pole_kinds") or []
        sp_kinds = [((ok_[t[5]] if t[5] < len(ok_) else ""), (sk_[t[6]] if t[6] < len(sk_) else "")) for t in sp]
        if one_net or maybe:
            res["pic"].append({"label": s["label"], "kode": s["kode"], "n_hp": len(s["hp"]), "one_net": one_net,
                               "signals": sig, "shared": sp, "ids": sorted(sib_ids), "dir": s.get("dir"),
                               "route_m": round(rt_m) if rt_dup else 0,
                               "gap_m": None if gap_b is None else round(gap_b, 1), "overlap": ov_,
                               "pole_kinds": sp_kinds, "same_bakp": same_bakp,
                               "same_tssr": same_tssr, "tolerated": tol, "beda_funnel": beda_funnel,
                               "funnel": s.get("funnel") or "", "poles": list(s.get("poles") or []),
                               # tiang <= 5 m dari jalur cluster saudara = dilewati jalurnya (akurasi GPS ponsel 4,9 m,
                               # GPS.gov; review Suka Karya: 98% tiang KMZ <= 5 m dari jalurnya sendiri, hanya 68% <= 2 m)
                               "pole_on_route": [any(_pt_seg_m(px_, py_, ln_[i_ - 1], ln_[i_]) <= POLE_ROUTE_M
                                                     for ln_ in (s.get("lines") or []) for i_ in range(1, len(ln_)))
                                                 for px_, py_, _n in (s.get("poles") or [])] if tol else [],
                               "pole_kinds_sib": list(s.get("pole_kinds") or []),
                               # 3.13.0: garis jalur cluster saudara (untuk menilai jalur terputus yang tersambung lewat saudara)
                               "lines": [list(ln_) for ln_ in (s.get("lines") or [])] if tol else [],
                               "bnd": list(s.get("bnd") or []) if tol else []})
        # Jalur berimpit TANPA tiang ganda bukan kesalahan: dua kabel distribusi boleh lewat ruas tiang yang sama
        # (Tomohon 2026: jalur Lingk. 2 berimpit 572 m dengan Lingk. 4 di atas 14 tiang Lingk. 4, tiang hanya tercatat
        # sekali). Yang salah adalah tiang yang dicatat di dua KMZ (temuan tiang ganda di atas). Jalur berimpit hanya
        # dipakai sebagai sinyal satu jaringan / 1 PIC dan keterangan pada temuan tiang ganda.
        if sp:
            n_h = sum(1 for t in sp if t[4] > 0.05)
            # 3.10.0: bedakan tiang BARU ganda (BOQ tiang baru dihitung dua kali) dari tiang EKSISTING yang dipakai dua
            # cluster (bukan BOQ tiang baru; yang ganda adalah catatan sewa/attachment). Review Suka Karya 2026: tiang EP di
            # RT 05 = TE di RT 06 dilaporkan 'BOQ ganda'. Kode temuan & tingkat tetap sama (status cluster tidak bergeser).
            n_new = sum(1 for a_, b_ in sp_kinds if "new" in (a_, b_))
            n_ex = sum(1 for a_, b_ in sp_kinds if a_ == "existing" and b_ == "existing")
            n_unk = len(sp) - n_new - n_ex
            code_diff = [(t[2], t[3]) for t in sp if norm_name(t[2]) != norm_name(t[3])]
            jenis = []
            if n_new:
                jenis.append("%d tiang BARU (BOQ tiang baru ganda)" % n_new)
            if n_ex:
                jenis.append("%d tiang EKSISTING di kedua cluster (bukan BOQ tiang baru; catat sekali sebagai tiang "
                             "bersama agar sewa/attachment tidak dihitung dua kali)" % n_ex)
            if n_unk:
                jenis.append("%d tiang jenis tidak terbaca" % n_unk)
            F.append({"x": sp[0][0], "y": sp[0][1], "kind": "WARN_TIANG_GANDA_LINTAS_CLUSTER",
                      "ket": "%d tiang cluster ini juga tercatat di KMZ cluster %s (koordinat sama <= %.1f m): %s. Jenis: %s.%s "
                             "Satu tiang fisik hanya boleh dihitung di satu cluster; tentukan cluster pemiliknya, di cluster "
                             "lain jadikan tiang existing/bersama."
                             % (len(sp), s["label"], pole_same_m,
                                "; ".join("%.6f, %.6f" % (t[1], t[0]) for t in sp[:4]) + (" ..." if len(sp) > 4 else ""),
                                "; ".join(jenis),
                                (" Nama/kode tiang beda di kedua KMZ: %s." % ", ".join(
                                    "%s vs %s" % c_ for c_ in code_diff[:3])) if code_diff else "")
                             + (" Jalur kabel kedua cluster berimpit +-%.0f m." % rt_m if rt_dup else ""),
                      "val": len(sp), "lim": None, "line": None, "other": s["label"], "unit": "tiang",
                      "pts": [(t[0], t[1]) for t in sp], "n_shift": n_h})
    if res["bnd_same"]:
        same = res["bnd_same"]
        inside = [q for x in same for q in x["hp"] if in_poly_any(q["x"], q["y"], own["bnd"])]
        c0 = inside[len(inside) // 2] if inside else own["hp"][0]
        n_ov += 1
        n_induk += 1
        F.append({"x": c0["x"], "y": c0["y"], "kind": "BOUNDARY_MEMUAT_CLUSTER_LAIN",
                  "ket": "BOUNDARY cluster ini identik dengan BOUNDARY %d cluster lain%s (%s): boundary wilayah/funnel induk "
                         "yang disalin ke setiap KMZ, belum dipotong per cluster; memuat %d HP cluster lain. Gambar ulang "
                         "BOUNDARY tiap cluster hanya di sekitar HP-nya." % (
                             len(same), (" '%s'" % own["bnd_name"]) if own.get("bnd_name") else "",
                             ", ".join(x["label"] for x in same[:6]) + (" ..." if len(same) > 6 else ""), len(inside)),
                  "val": len(same), "lim": None, "line": None, "other": ", ".join(x["label"] for x in same),
                  "unit": "cluster"})
    if res["pic"]:
        tot = len(own["hp"]) + sum(g["n_hp"] for g in res["pic"])
        spl = int(math.ceil(tot / float(hp_per_spl or 32)))
        net = [g for g in res["pic"] if g["one_net"]]
        x0, y0 = own["hp"][0]["x"], own["hp"][0]["y"]
        F.append({"x": x0, "y": y0, "kind": "INFO_SATU_PIC_DESAIN",
                  "ket": "Cluster ini %s dengan: %s. Total %d HP (butuh %d splitter 1x%d; %s). Review sebagai satu "
                         "paket: tiang bersama dihitung sekali, BOUNDARY tidak saling masuk, HP tidak ganda, colo/FDT "
                         "direncanakan bersama." % (
                             "SATU JARINGAN (1 PIC desain)" if net else "kemungkinan satu PIC desain (jaringan terpisah)",
                             "; ".join("%s [%s]" % (g["label"], ", ".join(g["signals"])) for g in res["pic"]),
                             tot, spl, ratio,
                             "muat 1 FDT %d HP" % fdt_cap if tot <= fdt_cap else "lebih dari 1 FDT %d HP" % fdt_cap),
                  "val": tot, "lim": fdt_cap, "line": None, "other": ", ".join(g["label"] for g in res["pic"])})
    res["counts"] = {"dup": n_dup, "warn": n_warn, "maybe": n_maybe, "in_bnd": n_in, "edge": n_edge, "overlap": n_ov, "id": n_id,
                     "in_bnd_1pic": n_in_tol,
                     "pole_shared": sum(len(g["shared"]) for g in res["pic"]), "pic": len(res["pic"]),
                     "route_m": sum(g.get("route_m", 0) for g in res["pic"]),
                     "induk": n_induk, "induk_info": n_induk_info}
    # ---- laporan teks ----
    R.append("LINTAS CLUSTER (cluster saudara di folder yang sama / folder pembanding)")
    if not res["used"]:
        n_cand = sum(1 for x in sibs if x is not None)
        if not n_cand:
            # bedakan 'tidak ada folder' dari 'ada tetapi jauh': dulu keduanya tertulis 'radius 2 km' sehingga kegagalan
            # menemukan folder saudara (mode KMZ saja, review Tomohon 2026) tampak seperti hasil pemeriksaan
            R.append("  Cluster saudara dibandingkan : 0 (tidak ada folder cluster lain di folder induk / folder pembanding)")
        else:
            R.append("  Cluster saudara dibandingkan : 0 (%d folder cluster lain ditemukan, tidak ada yang dalam radius %.0f km "
                     "atau semuanya versi lain cluster ini)" % (n_cand, near_km))
    else:
        R.append("  Cluster saudara dibandingkan : %d" % len(res["used"]))
        for s in res["used"]:
            R.append("    - %-34s %4d HP (%s)%s%s" % (s["label"][:34], len(s["hp"]), s["hp_src"],
                                                    ", BOUNDARY %d" % len(s["bnd"]) if s["bnd"] else ", tanpa BOUNDARY",
                                                    ("; " + "; ".join(s["note"])) if s["note"] else ""))
    for nm, why in res["skipped"]:
        R.append("    ~ diabaikan: %s (%s)" % (nm, why))
    R.append("  HP duplikat lintas cluster    : %d (ERROR)" % n_dup)
    for hid, nm, other, d, rank in dup_pairs[:40]:
        if rank in (0, 1):
            R.append("    - %s no. rumah %-20s = cluster %s (%.1f m)" % (hid, nm[:20], other, d))
    R.append("  Mungkin duplikat (WARNING)    : %d (label sama %.0f-%.0f m, nama mirip <= %.0f m, titik berimpit <= %.0f m "
             "beda label)" % (n_warn, label_m, label_warn_m, fuzzy_m, bldg_m))
    R.append("  Kemungkinan duplikat lintas   : %d (info, 0,5-%.0f m, no. rumah kosong)" % (n_maybe, dup_near))
    R.append("  Aturan: koordinat <= %.1f m; label ?NNN/nama usaha sama <= %.0f m; nomor rumah sama <= %.0f m "
             "(<= %.0f m bila nama jalan sama)" % (dup_exact, label_m, name_m, street_m))
    R.append("  HP di dalam BOUNDARY cluster lain: %d (> %.0f m, ERROR); %d di tepi (info)" % (n_in, bnd_tol, n_edge))
    if n_in_tol:
        R.append("  HP di BOUNDARY cluster saudara 1 PIC (satu funnel/wilayah induk): %d - boundary bertumpuk diterima "
                 "(catatan, bukan alasan reject)" % n_in_tol)
    R.append("  BOUNDARY tumpang tindih       : %d cluster" % n_ov)
    if res["bnd_same"]:
        R.append("  BOUNDARY identik (induk)      : %d cluster%s -> boundary wilayah induk disalin ke setiap KMZ, belum "
                 "dipotong per cluster (ERROR, dilaporkan sekali)" % (
                     len(res["bnd_same"]), (" ('%s')" % own["bnd_name"]) if own.get("bnd_name") else ""))
    if n_induk:
        R.append("  ! BOUNDARY cluster ini memuat sebagian besar HP %d cluster lain (BOUNDARY induk/gabungan): ERROR" % n_induk)
    if n_induk_info:
        R.append("  HP di BOUNDARY induk cluster lain: %d cluster (perbaikan di cluster pemilik BOUNDARY, info)" % n_induk_info)
    if n_id:
        R.append("  ID cluster dipakai cluster lain: %d" % n_id)
    R.append("  Tiang tercatat di 2 cluster   : %d (WARNING; BOQ tiang tidak boleh ganda)" % res["counts"]["pole_shared"])
    R.append("  Jalur berimpit (info)         : %s (>= %.0f m searah <= 2 m; jalur bersama boleh, asal tiang tidak "
             "dicatat ganda)" % (", ".join("%s +-%d m" % (g["label"][:34], g["route_m"]) for g in res["pic"]
                                           if g.get("route_m")) or "0", route_dup_m))
    if res.get("seq_restart"):
        R.append("  Label urut (?NNN) diulang di  : %s -> label urut bukan pengenal lintas cluster (penomoran tiap "
                 "lingkungan mulai dari 1); duplikat dinilai dari koordinat & nama" % ", ".join(
                     x[:34] for x in res["seq_restart"]))
    if res["pic"]:
        tot = len(own["hp"]) + sum(g["n_hp"] for g in res["pic"])
        R.append("  SATU PIC DESAIN / JARINGAN BERSAMA:")
        for g in res["pic"]:
            R.append("    - %-34s %s: %s" % (g["label"][:34], "SATU JARINGAN" if g["one_net"] else "kemungkinan 1 PIC",
                                             "; ".join(g["signals"])))
        R.append("    Total HP grup %d -> %d splitter 1x%d (%d HP/splitter), %s" % (
            tot, int(math.ceil(tot / float(hp_per_spl or 32))), ratio, hp_per_spl,
            "muat 1 FDT %d HP" % fdt_cap if tot <= fdt_cap else "lebih dari kapasitas 1 FDT %d HP" % fdt_cap))
        R.append("    Saran review: periksa grup ini bersama (tiang bersama dihitung sekali, BOUNDARY tidak saling masuk, "
                 "HP tidak ganda, satu rencana FDT).")
    return res


def _rows_txt(pts, max_items=6):
    """' (baris 80, 81)' dari daftar HP ber-'row' (nomor baris HPDB asli); '' bila tidak ada nomor baris."""
    v = sorted({int(p["row"]) for p in pts if p.get("row")})
    if not v:
        return ""
    parts, a, b = [], v[0], v[0]
    for n in v[1:]:
        if n == b + 1:
            b = n
            continue
        parts.append((a, b))
        a = b = n
    parts.append((a, b))
    t = ["%d" % a if a == b else ("%d, %d" % (a, b) if b == a + 1 else "%d-%d" % (a, b)) for a, b in parts]
    return " (baris %s)" % (", ".join(t[:max_items]) + (" dst" if len(t) > max_items else ""))


def in_poly_any(x, y, polys):
    return any(in_poly(x, y, p) for p in polys)


def _keep_advice(own_lbl, sib_lbl, do, ds, po, ps):
    """Saran cluster pemilik rumah: di dalam BOUNDARY siapa, lalu tiang mana yang lebih dekat (kabel drop lebih pendek)."""
    io = do is not None and do > 0
    is_ = ds is not None and ds > 0
    if io and not is_:
        return "Saran: pertahankan di cluster ini (di dalam BOUNDARY-nya), hapus dari %s." % sib_lbl
    if is_ and not io:
        return "Saran: hapus dari cluster ini; rumah berada di dalam BOUNDARY %s." % sib_lbl
    if do is not None and ds is not None and abs(do - ds) >= 3.0:
        win = own_lbl if do > ds else sib_lbl
        return "Saran: pertahankan di %s (lebih dalam di BOUNDARY-nya: %.0f m vs %.0f m)." % (
            "cluster ini" if win == own_lbl else win, max(do, ds), min(do, ds))
    if po is not None and ps is not None and abs(po - ps) >= 3.0:
        win = "cluster ini" if po < ps else sib_lbl
        return "Saran: pertahankan di %s (tiang terdekat %.0f m vs %.0f m)." % (win, min(po, ps), max(po, ps))
    return "Tentukan satu cluster pemilik, lalu hapus dari cluster yang lain."

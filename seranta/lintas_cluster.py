# -*- coding: utf-8 -*-
"""
Seranta - FTTH Design Assistant
Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-2.0-or-later.

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
    import defusedxml.ElementTree as ET
except ImportError:  # pragma: no cover
    import xml.etree.ElementTree as ET  # nosec B405

RULE_VERSION = "2026.10-r7"

HP_RX = re.compile(r"\b(hp|homepass|home ?pass|rumah)\b", re.IGNORECASE)
EVID_RX = re.compile(r"evid[ae]n[cs]e|evident|foto|photo|dokumentasi", re.IGNORECASE)
DUPF_RX = re.compile(r"duplikat|duplicate|\berror\b", re.IGNORECASE)
BND_RX = re.compile(r"boundary|bondary|batas", re.IGNORECASE)
POLE_RX = re.compile(r"\b(poles?|tiang|np|ep|t\d{1,2}|te)\b", re.IGNORECASE)
ID_RX = re.compile(r"(?<!\d)(\d{9,12})(?!\d)")
ZW_RX = re.compile(u"[​-‏⁠﻿]")
GENERIC_NAMES = {"", "HP", "HOMEPASS", "RUMAH", "UNTITLEDPLACEMARK", "TITIK", "POINT", "NA", "NONE", "NULL"}
SKIP_DIR_RX = re.compile(r"^(INPUT|HASIL|QC_|_|~)", re.IGNORECASE)


# ----------------------------------------------------------------------------------------- geometri
def dist_m(x1, y1, x2, y2):
    kx = math.cos(math.radians((y1 + y2) / 2.0)) * 111320.0
    return math.hypot((x2 - x1) * kx, (y2 - y1) * 110574.0)


def _pip(x, y, ring):
    inside, j = False, len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-30) + xi:
            inside = not inside
        j = i
    return inside


def in_poly(x, y, poly):
    outer, holes = poly
    return _pip(x, y, outer) and not any(_pip(x, y, h) for h in holes)


def edge_dist_m(x, y, poly):
    kx, ky = math.cos(math.radians(y)) * 111320.0, 110574.0
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
    lat = (a[1] + a[3]) / 2.0
    return math.hypot(dx * math.cos(math.radians(lat)) * 111320.0, dy * 110574.0)


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
    kx = math.cos(math.radians((y0 + y1) / 2.0)) * 111320.0
    w, h = (x1 - x0) * kx, (y1 - y0) * 110574.0
    step = max(1.0, math.sqrt(w * h / float(max_samples)))
    nx, ny = max(1, int(w / step)), max(1, int(h / step))
    sx, sy = (x1 - x0) / nx, (y1 - y0) / ny
    hits = []
    for i in range(nx):
        x = x0 + (i + 0.5) * sx
        for j in range(ny):
            y = y0 + (j + 0.5) * sy
            if any(in_poly(x, y, p) for p in polys_a) and any(in_poly(x, y, p) for p in polys_b):
                hits.append((x, y))
    if not hits:
        return 0.0, None, []
    area = len(hits) * (sx * kx) * (sy * 110574.0)
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
        return "name"
    return ""


def similar(a, b):
    """Kemiripan dua label nama (0-1), untuk salah ketik: 'KANTIN KAKA' vs 'KANTIN KAKAK'."""
    import difflib
    a, b = a.lstrip("?"), b.lstrip("?")
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def match_rank(d, a, b, dup_exact=0.5, dup_near=5.0, name_m=15.0, label_m=25.0, fuzzy_m=30.0, fuzzy=0.85, bldg_m=2.0,
               same_street=False, street_m=30.0, label_warn_m=50.0):
    """Peringkat kecocokan dua titik HP (jarak d meter, label ternormal a & b). Pola diambil dari temuan tim QC
    (review Jambi): rumah dianggap sama bila titiknya disalin (koordinat sama) ATAU label survei/nama usahanya sama
    walau titik bergeser. Kembali (rank, alasan) atau None:
      0 koordinat sama                      -> ERROR
      1 label kuat sama (?NNN / nama usaha) dalam label_m, atau nomor rumah sama dalam name_m -> ERROR
      3 nama mirip (salah ketik) dalam fuzzy_m                                                 -> WARNING
      4 berimpit <= bldg_m dengan label berbeda (satu bangunan, dua titik)                    -> WARNING
      5 label kuat sama tetapi label_m-label_warn_m (duplikat atau salah ketik label)        -> WARNING
      2 0,5-5 m dengan label kosong                                                            -> INFO"""
    if d <= dup_exact:
        return 0, "koordinat sama (%.1f m)" % d
    ka, kb = label_kind(a), label_kind(b)
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


RANK_ORDER = {0: 0, 1: 1, 5: 2, 3: 3, 4: 4, 2: 5}


def same_label_pairs(pts, label_m=25.0, name_m=15.0, dup_exact=0.5, street_m=30.0, label_warn_m=50.0):
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
                sa, sb = pts[i].get("adr", ""), pts[j].get("adr", "")
                strong = label_kind(n) in ("seq", "name")
                lim = label_m if strong else (street_m if sa and sa == sb else name_m)
                d = dist_m(pts[i]["x"], pts[i]["y"], pts[j]["x"], pts[j]["y"])
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
    res = {"hp": [], "bnd": [], "poles": [], "doc": "", "hp_dupf": 0}
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
                    elif gt == "Point":
                        r = _ring(g)
                        if not r:
                            continue
                        x, y = r[0]
                        if any(HP_RX.search(f) for f in folders):
                            if any(EVID_RX.search(f) for f in folders):
                                continue
                            if any(DUPF_RX.search(f) for f in folders):
                                res["hp_dupf"] += 1      # sudah ditandai surveyor sebagai duplikat
                                continue
                            res["hp"].append((x, y, pname))
                        elif any(POLE_RX.search(f) for f in folders):
                            res["poles"].append((x, y, pname))
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
                    "pid": str(g(ipid) or "").strip(), "row": j, "adr": norm_street(g(iadr))})
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
    pts, k = [], {"hp": [], "bnd": [], "poles": [], "doc": "", "hp_dupf": 0}
    if kmz:
        try:
            k = read_kmz(kmz)
        except Exception as e:
            note.append("KMZ gagal dibaca: %s" % str(e)[:120])
    kbb = _bbox_union(_bbox_pts([(x, y) for x, y, _n in k["hp"]]), *[_bbox_pts(b[0]) for b in k["bnd"]])
    if near_bbox and kbb and _bbox_gap_m(near_bbox, kbb) > near_km * 1000.0:
        return {"far": True, "dir": cdir}          # cluster jauh: HPDB tidak perlu dibaca
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
    return {"dir": cdir, "label": label, "kode": helpers["kode_wilayah"](cdir, hpdb or ""),
            "hpdb": hpdb, "kmz": kmz, "hp": pts, "hp_src": src, "bnd": k["bnd"], "poles": k["poles"],
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
        if ok(d):
            out.append(d)
            return True
        return False

    roots = [os.path.dirname(os.path.abspath(outdir))]
    for e in extra or []:
        if e and os.path.isdir(e):
            if ok(e):
                add(e)                       # folder pembanding = satu folder cluster
            else:
                roots.append(e)              # folder pembanding = folder induk
    for r in roots:
        for d in subdirs(r):
            if len(out) >= max_dirs:
                return out
            if not add(d):
                for d2 in subdirs(d)[:20]:   # ZIP bertingkat: FOLDER/FOLDER/<file>
                    add(d2)
    return out


# ----------------------------------------------------------------------------------------- pembanding
def _grid(pts, cell_deg):
    g = {}
    for i, p in enumerate(pts):
        g.setdefault((int(math.floor(p["x"] / cell_deg)), int(math.floor(p["y"] / cell_deg))), []).append(i)
    return g


def _near(g, cell_deg, x, y):
    cx, cy = int(math.floor(x / cell_deg)), int(math.floor(y / cell_deg))
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for i in g.get((cx + dx, cy + dy), ()):
                yield i


def _nearest_pole(x, y, poles):
    if not poles:
        return None
    return min(dist_m(x, y, px, py) for px, py, _n in poles)


def compare(own, sibs, dup_exact=0.5, dup_near=5.0, name_m=15.0, bnd_tol=10.0, near_km=2.0, same_frac=0.6,
            label_m=25.0, fuzzy_m=30.0, fuzzy=0.85, bldg_m=2.0, street_m=30.0, label_warn_m=50.0):
    """own: dict(label, kode, hp=[dict(x, y, hn, hid)], bnd, poles=[(x, y, nama)], ids_hpdb, ids_other, bbox).
    sibs: hasil load_cluster. Kembali dict(findings, report, counts, used, skipped, scene)."""
    res = {"findings": [], "report": [], "used": [], "skipped": [], "counts": {}, "scene": {"bnd": [], "hp": []}}
    F, R = res["findings"], res["report"]
    own_bb = own.get("bbox") or _bbox_pts([(p["x"], p["y"]) for p in own["hp"]])
    cell = max(name_m, label_m, fuzzy_m, street_m, label_warn_m) / 111000.0
    reach = max(name_m, label_m, fuzzy_m, street_m, label_warn_m)
    n_dup = n_maybe = n_warn = n_in = n_edge = n_ov = n_id = 0
    dup_pairs = []
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
                m = match_rank(d, norm_name(h["hn"]), norm_name(q["hn"]), dup_exact, dup_near, name_m, label_m,
                               fuzzy_m, fuzzy, bldg_m, bool(sa) and sa == sb, street_m, label_warn_m)
                if m is None:
                    continue
                rank = m[0]
                if best is None or (RANK_ORDER[rank], d) < (RANK_ORDER[best[0]], best[1]):
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
            ket = ("%s (no. rumah %s) juga tercatat di cluster %s%s: %s. %s" % (
                h["hid"], nm, s["label"], (" baris %d" % q["row"]) if q.get("row") else "", why, keep))
            kind = {0: "HP_DUPLIKAT_LINTAS_CLUSTER", 1: "HP_DUPLIKAT_LINTAS_CLUSTER",
                    3: "WARN_HP_MUNGKIN_DUPLIKAT_LINTAS_CLUSTER", 4: "WARN_HP_MUNGKIN_DUPLIKAT_LINTAS_CLUSTER",
                    5: "WARN_HP_MUNGKIN_DUPLIKAT_LINTAS_CLUSTER",
                    2: "INFO_HP_MUNGKIN_DUPLIKAT_LINTAS_CLUSTER"}[rank]
            if rank in (0, 1):
                n_dup += 1
            elif rank in (3, 4, 5):
                n_warn += 1
            else:
                n_maybe += 1
            dup_pairs.append((h["hid"], nm, s["label"], d, rank))
            F.append({"x": h["x"], "y": h["y"], "kind": kind, "ket": ket, "val": round(d, 1),
                      "lim": {0: dup_exact, 1: (label_m if label_kind(norm_name(nm)) in ("seq", "name") else
                                                (street_m if h.get("adr") and h.get("adr") == q.get("adr") else name_m)),
                              3: fuzzy_m, 4: bldg_m, 5: label_warn_m, 2: dup_near}[rank],
                      "line": [(h["x"], h["y"]), (q["x"], q["y"])] if d > 0.05 else None,
                      "other": s["label"], "other_row": q.get("row"), "other_file": s.get("hpdb") or s.get("kmz")})
        # ---- 2. HP cluster ini di dalam BOUNDARY cluster saudara ----
        if s["bnd"]:
            for h in own["hp"]:
                if id(h) in dup_own:
                    continue                             # satu akar masalah, satu temuan (sudah di duplikat)
                inside = [b for b in s["bnd"] if in_poly(h["x"], h["y"], b)]
                if not inside:
                    continue
                dep = max(edge_dist_m(h["x"], h["y"], b) for b in inside)
                own_in = bool(own["bnd"]) and any(in_poly(h["x"], h["y"], b) for b in own["bnd"])
                tail = (" BOUNDARY cluster ini dan %s tumpang tindih di titik ini." % s["label"]) if own_in else ""
                if dep > bnd_tol:
                    n_in += 1
                    F.append({"x": h["x"], "y": h["y"], "kind": "HP_DI_BOUNDARY_CLUSTER_LAIN",
                              "ket": "%s (no. rumah %s) berada %.1f m di dalam BOUNDARY cluster %s (> %.0f m).%s Tentukan "
                                     "satu cluster pemilik rumah ini; keluarkan dari cluster yang lain dan rapikan BOUNDARY."
                                     % (h["hid"], h["hn"] or "-", dep, s["label"], bnd_tol, tail),
                              "val": round(dep, 1), "lim": bnd_tol, "line": None, "other": s["label"]})
                else:
                    n_edge += 1
                    F.append({"x": h["x"], "y": h["y"], "kind": "INFO_HP_TEPI_BOUNDARY_CLUSTER_LAIN",
                              "ket": "%s (no. rumah %s) %.1f m di dalam tepi BOUNDARY cluster %s (dalam toleransi GPS %.0f m)"
                                     % (h["hid"], h["hn"] or "-", dep, s["label"], bnd_tol),
                              "val": round(dep, 1), "lim": bnd_tol, "line": None, "other": s["label"]})
        # ---- 3. BOUNDARY tumpang tindih ----
        if own["bnd"] and s["bnd"]:
            area, c, samples = overlap_area(own["bnd"], s["bnd"])
            if area > 0 and c:
                deep_own = [h for h in own["hp"] if in_poly_any(h["x"], h["y"], s["bnd"]) and in_poly_any(h["x"], h["y"], own["bnd"])]
                deep_sib = [q for q in s["hp"] if in_poly_any(q["x"], q["y"], s["bnd"]) and in_poly_any(q["x"], q["y"], own["bnd"])]
                # lebar irisan = jarak terjauh sampel irisan dari tepi poligon terdekat (pendekatan setengah lebar)
                width = 2.0 * max((min(edge_dist_m(x, y, b) for b in own["bnd"] + s["bnd"]) for x, y in samples), default=0)
                serious = bool(deep_own or deep_sib) and width > bnd_tol
                n_ov += 1
                F.append({"x": c[0], "y": c[1],
                          "kind": "WARN_BOUNDARY_BERIRISAN_CLUSTER_LAIN" if serious else "INFO_BOUNDARY_BERIRISAN_CLUSTER_LAIN",
                          "ket": "BOUNDARY cluster ini tumpang tindih dengan BOUNDARY cluster %s: luas irisan +-%.0f m2, "
                                 "lebar maks +-%.0f m; di dalam irisan ada %d HP cluster ini dan %d HP cluster %s. %s"
                                 % (s["label"], area, width, len(deep_own), len(deep_sib), s["label"],
                                    "Rapikan garis BOUNDARY agar satu rumah hanya masuk satu cluster." if serious else
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
    res["counts"] = {"dup": n_dup, "warn": n_warn, "maybe": n_maybe, "in_bnd": n_in, "edge": n_edge, "overlap": n_ov, "id": n_id}
    # ---- laporan teks ----
    R.append("LINTAS CLUSTER (cluster saudara di folder yang sama / folder pembanding)")
    if not res["used"]:
        R.append("  Cluster saudara dibandingkan : 0 (tidak ada folder cluster lain dalam radius %.0f km)" % near_km)
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
    R.append("  BOUNDARY tumpang tindih       : %d cluster" % n_ov)
    if n_id:
        R.append("  ID cluster dipakai cluster lain: %d" % n_id)
    return res


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

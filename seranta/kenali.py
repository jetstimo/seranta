# -*- coding: utf-8 -*-
"""Mengenali berkas dari ISINYA, tidak hanya dari namanya (Python murni, bisa diuji tanpa QGIS) - Seranta 3.14.0.

Masalah di lapangan: nama berkas survei tidak seragam. 'HPBD', 'HDPB', 'HP DATABASE', 'homepas', berkas tanpa kata
HPDB sama sekali, banyak KMZ cluster dalam satu folder, KMZ referensi yang namanya diubah. Dulu Seranta hanya membaca
nama sehingga berhenti dengan 'lebih dari satu berkas' atau 'tidak ada HPDB'. Modul ini membuka berkas sebagai DATA
(zip + XML/teks, batas ukuran, tanpa menjalankan apa pun) dan mencari ciri yang memang dibutuhkan pembacanya:

* Daftar homepass (HPDB): baris judul berisi kolom LATITUDE dan LONGITUDE (syarat pembaca HPDB Seranta) dan ada
  baris data berkoordinat sah.
* KMZ survei: titik di folder HP/HOMEPASS, atau titik + garis jalur / folder tiang.
* KMZ referensi: Design Lite (folder FDT dengan data SPLITTERS), Funnel (poligon tanpa titik HP, folder funnel/RFS).
* TSSR: dokumen Word yang teksnya memuat TSSR / Site Survey / Site Profile.

Nama berkas tetap dipakai lebih dulu bila jelas (hasil lama tidak bergeser); isi dipakai bila nama tidak ada, salah
ketik, atau lebih dari satu kandidat.
Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later.
"""
import csv
import io
import os
import re
import zipfile
from xml.etree import ElementTree as ET  # nosec B405 - hanya membaca XML dari berkas pengguna sebagai data

MAX_XML = 64 * 1024 * 1024          # batas isi XML yang dibaca dari satu KMZ/XLSX
_CACHE = {}


def _key(path):
    try:
        st = os.stat(path)
        return (os.path.abspath(path), st.st_size, int(st.st_mtime))
    except OSError:
        return None


def _cached(kind, path, fn):
    k = _key(path)
    if k is None:
        return fn()
    kk = (kind,) + k
    if kk not in _CACHE:
        try:
            _CACHE[kk] = fn()
        except Exception:
            _CACHE[kk] = None
    return _CACHE[kk]


def _strip(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


# ------------------------------------------------------------------ nama: salah ketik & kemiripan

def lev(a, b, cap=3):
    """Jarak edit Damerau-Levenshtein terbatas (tukar dua huruf bersebelahan = 1 langkah: HPBD, HDPB)."""
    if a == b:
        return 0
    if abs(len(a) - len(b)) >= cap:
        return cap
    d = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        d[i][0] = i
    for j in range(len(b) + 1):
        d[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            c = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + c)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return min(d[-1][-1], cap)


def tokens(name):
    """Token huruf/angka dari nama berkas, huruf besar, angka tanpa nol di depan ('RT 09' -> RT, 9)."""
    base = os.path.splitext(os.path.basename(str(name or "")))[0].upper()
    out = []
    for t in re.findall(r"[A-Z]+|\d+", base):
        out.append(str(int(t)) if t.isdigit() and len(t) < 9 else t)
    return out


# kata yang menandai daftar homepass; salah ketik 1 huruf juga dikenali (HPBD, HDPB, HPDP, HOMEPAS, HOMPASS)
_HPDB_WORDS = ("HPDB", "HOMEPASS")
_HPDB_PAIRS = (("HP", "DB"), ("HP", "DATABASE"), ("HOME", "PASS"), ("DATABASE", "HP"))


def name_is_hpdb(name):
    """Nama berkas menandai daftar homepass (termasuk salah ketik satu huruf)."""
    tk = tokens(name)
    for t in tk:
        if len(t) >= 4 and any(lev(t, w, 4) <= (1 if len(w) <= 5 else 2) for w in _HPDB_WORDS):
            if not t.isdigit():
                return True
    for a, b in zip(tk, tk[1:]):
        if (a, b) in _HPDB_PAIRS or (a == "HP" and len(b) == 2 and lev(b, "DB", 3) <= 1):
            return True
    return False


_STOP = {"KMZ", "KML", "HPDB", "HP", "PT", "CV", "TBK", "REV", "REVISI", "FINAL", "UPDATE", "NEW", "BARU", "TSSR",
         "BAKP", "FILE", "DATA", "SURVEY", "SURVEI", "THE", "DAN", "AND"}


def similarity(a, b):
    """Kemiripan dua nama berkas 0..1: token bersama (tanpa kata umum) + ID cluster 9-12 digit yang sama.
    Angka kecil (RT 09, RW 5) diberi bobot penuh karena pembeda utama cluster bertetangga."""
    ida = set(re.findall(r"(?<!\d)\d{9,12}(?!\d)", os.path.basename(str(a or ""))))
    idb = set(re.findall(r"(?<!\d)\d{9,12}(?!\d)", os.path.basename(str(b or ""))))
    if ida and idb and ida & idb:
        return 1.0
    if ida and idb and not (ida & idb):
        return 0.0                      # ID cluster berbeda = pasti bukan pasangan
    # jumlah HP di nama ('53HP', '56 HP') sering berubah setelah revisi -> angka itu tidak dipakai
    hp_a = {str(int(x)) for x in re.findall(r"(\d+)\s*HP", os.path.basename(str(a or "")).upper())}
    hp_b = {str(int(x)) for x in re.findall(r"(\d+)\s*HP", os.path.basename(str(b or "")).upper())}
    sa = {t for t in tokens(a) if t not in _STOP and t not in hp_a}
    sb = {t for t in tokens(b) if t not in _STOP and t not in hp_b}
    if not sa or not sb:
        return 0.0
    # angka pembeda (RT 09 vs RT 10) harus sama
    na, nb = {t for t in sa if t.isdigit()}, {t for t in sb if t.isdigit()}
    if na and nb and not (na & nb):
        return 0.0
    inter = len(sa & sb)
    return inter / float(len(sa | sb))


def best_match(name, candidates, min_sim=0.5, margin=0.15):
    """Kandidat paling mirip dengan `name` bila jelas unggul. -> (kandidat | None, skor)"""
    sc = sorted(((similarity(name, c), c) for c in candidates), key=lambda t: (-t[0], t[1]))
    if not sc or sc[0][0] < min_sim:
        return None, (sc[0][0] if sc else 0.0)
    if len(sc) > 1 and sc[0][0] - sc[1][0] < margin:
        return None, sc[0][0]
    return sc[0][1], sc[0][0]


# ------------------------------------------------------------------ spreadsheet: baris judul

def _xlsx_head(path, nrows=25, max_sheets=8):
    """[(nama_sheet, [baris...])] - hanya `nrows` baris pertama setiap sheet (cepat untuk berkas besar)."""
    out = []
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        shared = []
        if "xl/sharedStrings.xml" in names and z.getinfo("xl/sharedStrings.xml").file_size <= MAX_XML:
            for _, el in ET.iterparse(z.open("xl/sharedStrings.xml")):  # nosec B314
                if _strip(el.tag) == "si":
                    shared.append("".join(t.text or "" for t in el.iter() if _strip(t.tag) == "t"))
                    el.clear()
        rels = {}
        if "xl/_rels/workbook.xml.rels" in names:
            for r in ET.parse(z.open("xl/_rels/workbook.xml.rels")).getroot():  # nosec B314
                tgt = r.get("Target", "")
                tgt = tgt.lstrip("/") if tgt.startswith("/") else os.path.normpath(os.path.join("xl", tgt)).replace("\\", "/")
                rels[r.get("Id")] = tgt
        wb = ET.parse(z.open("xl/workbook.xml")).getroot()  # nosec B314
        for sh in wb.iter():
            if _strip(sh.tag) != "sheet":
                continue
            rid = next((v for k, v in sh.attrib.items() if _strip(k) == "id"), None)
            tgt = rels.get(rid, "")
            if tgt not in names:
                continue
            rows = []
            for _, el in ET.iterparse(z.open(tgt)):  # nosec B314
                if _strip(el.tag) != "row":
                    continue
                row = []
                for c in el:
                    if _strip(c.tag) != "c":
                        continue
                    t = c.get("t", "n")
                    if t == "inlineStr":
                        v = "".join(x.text or "" for x in c.iter() if _strip(x.tag) == "t")
                    else:
                        v = next((x.text for x in c if _strip(x.tag) == "v"), None) or ""
                        if t == "s" and v.isdigit():
                            v = shared[int(v)] if int(v) < len(shared) else ""
                    row.append(v.strip())
                rows.append(row)
                el.clear()
                if len(rows) >= nrows:
                    break
            out.append((sh.get("name") or "", rows))
            if len(out) >= max_sheets:
                break
    return out


def _csv_head(path, nrows=25):
    with open(path, "rb") as fh:
        raw = fh.read(256 * 1024)
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            txt = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    try:
        dialect = csv.Sniffer().sniff(txt[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = []
    for r in csv.reader(io.StringIO(txt), dialect):
        rows.append([c.strip() for c in r])
        if len(rows) >= nrows:
            break
    return [("csv", rows)]


_HDR_TYPO = re.compile(r"(?i)LONG?T+ITUDE|LONGT?ITUTE|LATT+ITUDE|LATT?ITUTE")   # 3.15.7: sama dengan buat_input_desain


def _norm(s):
    s = _HDR_TYPO.sub(lambda m: "LONGITUDE" if m.group(0).upper().startswith("LON") else "LATITUDE", str(s or ""))
    return re.sub(r"[^A-Z0-9]", "", s.upper())


def _coord_ok(lat, lon):
    try:
        a, b = float(str(lat).replace(",", ".")), float(str(lon).replace(",", "."))
    except ValueError:
        return False
    return -90 <= a <= 90 and -180 <= b <= 180 and (a, b) != (0.0, 0.0)


def sheet_profile(path):
    """-> dict(kind='hpdb'|'lain', sheet, header_row, rows_with_coords, reason) dari isi spreadsheet.
    HPDB = baris judul memuat kolom LATITUDE dan LONGITUDE (syarat pembaca HPDB) + >= 1 baris berkoordinat sah."""
    def run():
        ext = os.path.splitext(path)[1].lower()
        if ext in (".xlsx", ".xlsm"):
            sheets = _xlsx_head(path)
        elif ext == ".csv":
            sheets = _csv_head(path)
        else:
            return {"kind": "tidak_diketahui", "reason": "format %s tidak dibaca isinya" % ext}
        best = None
        for name, rows in sheets:
            for i, r in enumerate(rows[:20]):
                n = [_norm(c) for c in r]
                ilat = next((j for j, c in enumerate(n) if "LATITUDE" in c or c in ("LAT", "LINTANG")), None)
                ilon = next((j for j, c in enumerate(n) if "LONGITUDE" in c or c in ("LONG", "LON", "LNG", "BUJUR")),
                            None)
                if ilat is None or ilon is None:
                    continue
                strict = any("LATITUDE" in c for c in n) and any("LONGITUDE" in c for c in n)
                ok = sum(1 for rr in rows[i + 1:] if len(rr) > max(ilat, ilon) and _coord_ok(rr[ilat], rr[ilon]))
                hp = any(("HOMEPASS" in c or c.startswith("HP") or "ALAMAT" in c or "ADDRESS" in c or "CLUSTER" in c)
                         for c in n)
                score = (strict, ok > 0, hp, ok)
                if best is None or score > best[0]:
                    best = (score, name, i, ok, strict, hp)
        if best is None:
            return {"kind": "lain", "reason": "tidak ada baris judul dengan kolom lintang & bujur"}
        _s, name, i, ok, strict, hp = best
        if strict and ok > 0:
            return {"kind": "hpdb", "sheet": name, "header_row": i, "rows_with_coords": ok,
                    "reason": "sheet '%s' baris %d: kolom LATITUDE/LONGITUDE, %d baris berkoordinat" % (name, i + 1, ok)}
        return {"kind": "lain", "sheet": name, "header_row": i, "rows_with_coords": ok,
                "reason": "kolom koordinat tanpa judul LATITUDE/LONGITUDE atau tanpa baris data"}
    return _cached("sheet", path, run) or {"kind": "tidak_diketahui", "reason": "tidak terbaca"}


# ------------------------------------------------------------------ KMZ/KML: isi folder & geometri

_HP_RX = re.compile(r"\b(hp|homepass|home ?pass|rumah)\b", re.IGNORECASE)
_POLE_RX = re.compile(r"\b(pole|poles|tiang|np\d*|ep\d*|new ?pole|existing ?pole|t\d|te)\b", re.IGNORECASE)
_ROUTE_RX = re.compile(r"\b(cable|kabel|jalur|route|rute|road)\b", re.IGNORECASE)
_FDT_RX = re.compile(r"^\s*FDT\s*$", re.IGNORECASE)
_FUNNEL_RX = re.compile(r"funnel|\bRFS\b", re.IGNORECASE)


def _kml_stream(path):
    if path.lower().endswith(".kmz"):
        z = zipfile.ZipFile(path)
        kmls = [n for n in z.namelist() if n.lower().endswith(".kml")]
        if not kmls:
            z.close()
            raise ValueError("KMZ tanpa KML")
        main = "doc.kml" if "doc.kml" in kmls else kmls[0]
        if z.getinfo(main).file_size > MAX_XML:
            z.close()
            raise ValueError("KML terlalu besar")
        data = z.read(main)
        z.close()
        return io.BytesIO(data)
    return open(path, "rb")


def kmz_profile(path):
    """-> dict(kind='survei'|'designlite'|'funnel'|'lain', titik_hp, titik, garis, poligon, folder_tiang,
    folder_jalur, reason). Dibaca sebagai data (iterparse), tidak ada yang dijalankan."""
    def run():
        stack, names = [], []
        n_pt = n_ln = n_pg = n_hp = 0
        f_pole = f_route = f_fdt = f_funnel = False
        spl = False
        src = _kml_stream(path)
        try:
            for ev, el in ET.iterparse(src, events=("start", "end")):  # nosec B314
                t = _strip(el.tag)
                if ev == "start" and t in ("Folder", "Document"):
                    stack.append(None)
                elif ev == "end" and t == "name" and stack and stack[-1] is None:
                    nm = (el.text or "").strip()
                    stack[-1] = nm
                    names.append(nm)
                    f_pole = f_pole or bool(_POLE_RX.search(nm))
                    f_route = f_route or bool(_ROUTE_RX.search(nm))
                    f_fdt = f_fdt or bool(_FDT_RX.match(nm))
                    f_funnel = f_funnel or bool(_FUNNEL_RX.search(nm))
                elif ev == "end" and t in ("Folder", "Document"):
                    if stack:
                        stack.pop()
                    el.clear()
                elif ev == "end" and t == "SimpleData" and (el.get("name") or "").upper() in ("SPLITTERS", "SPLITTER"):
                    spl = True
                elif ev == "end" and t == "Placemark":
                    geo = {_strip(g.tag) for g in el.iter()}
                    if "Point" in geo:
                        n_pt += 1
                        if any(_HP_RX.search(f or "") for f in stack):
                            n_hp += 1
                    if "LineString" in geo:
                        n_ln += 1
                    if "Polygon" in geo:
                        n_pg += 1
                    el.clear()
        finally:
            src.close()
        d = {"titik_hp": n_hp, "titik": n_pt, "garis": n_ln, "poligon": n_pg, "folder_tiang": f_pole,
             "folder_jalur": f_route}
        if f_fdt and spl:
            d.update(kind="designlite", reason="folder FDT dengan data SPLITTERS")
        elif n_hp > 0 and (n_ln > 0 or f_pole):
            d.update(kind="survei", reason="%d titik HP, %d garis jalur%s" % (n_hp, n_ln, ", folder tiang" if f_pole else ""))
        elif n_hp > 0:
            d.update(kind="survei", reason="%d titik HP (tanpa garis jalur)" % n_hp)
        elif n_pt > 0 and n_ln > 0 and f_pole and f_route:
            d.update(kind="survei", reason="titik tiang dan garis jalur (tanpa folder HP)")
        elif n_pg > 0 and n_pt == 0 and n_ln == 0 and f_funnel:
            d.update(kind="funnel", reason="poligon area layanan tanpa titik/garis, folder funnel/RFS")
        else:
            d.update(kind="lain", reason="%d titik, %d garis, %d poligon; tidak ada folder HP" % (n_pt, n_ln, n_pg))
        return d
    return _cached("kmz", path, run) or {"kind": "tidak_diketahui", "reason": "tidak terbaca"}


# ------------------------------------------------------------------ dokumen Word: TSSR

_TSSR_TXT = re.compile(r"\bTSSR\b|SITE\s*SURVEY|SITE\s*PROFILE|TECHNICAL\s+SITE", re.IGNORECASE)


def docx_is_tssr(path):
    """Teks .docx (word/document.xml, maks 8 MB) memuat TSSR / Site Survey / Site Profile."""
    def run():
        with zipfile.ZipFile(path) as z:
            info = z.getinfo("word/document.xml")
            if info.file_size > 8 * 1024 * 1024:
                return False
            xml = z.read(info).decode("utf-8", "replace")
        txt = " ".join(re.findall(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>", xml[:2000000]))
        return bool(_TSSR_TXT.search(txt[:20000]))
    return bool(_cached("docx", path, run))

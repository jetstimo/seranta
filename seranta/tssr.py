# -*- coding: utf-8 -*-
"""
Seranta - FTTH Design Assistant
Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later.

CEK SILANG TSSR (Site Profile Survey Report) - versi 3.9.5
----------------------------------------------------------
Dari review Jambi Argenta 6 dan Cianjur Nyalindung RW 05 (November 2026): TSSR di folder cluster bisa milik cluster lain
(ID di nama file 21100218859, sedangkan HPDB 21100232646) atau jumlah HP-nya beda dengan HPDB (TSSR 177 HP, HPDB 169).
Modul murni Python (tanpa QGIS) agar bisa diuji otomatis. TSSR .docx dibaca sebagai DATA: hanya word/document.xml di
dalam zip, dengan batas ukuran; tidak ada makro/kode yang dijalankan.
"""
import os
import re
import unicodedata
import zipfile

TSSR_RX = re.compile(r"TSSR|SITE[ _-]*PROFILE|SITE[ _-]*SURVEY", re.IGNORECASE)
ID_RX = re.compile(r"(?<!\d)(\d{9,12})(?!\d)")
MAX_XML = 8 * 1024 * 1024          # document.xml TSSR biasa 50-300 kB; foto ada di word/media, tidak dibaca
SKIP_DIRS = ("INPUT", "HASIL", "QC")


def find_tssr(folder):
    """File TSSR (.docx) di folder cluster dan satu tingkat subfolder (kecuali folder hasil Seranta)."""
    hits = []
    for root, dirs, files in os.walk(folder):
        rel = os.path.relpath(root, folder)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        dirs[:] = sorted(d for d in dirs if not d.upper().startswith(SKIP_DIRS)) if depth < 1 else []
        for f in sorted(files):
            if f.lower().endswith(".docx") and not f.startswith("~$") and TSSR_RX.search(f):
                hits.append(os.path.join(root, f))
    if not hits:
        # 3.14.0: nama tanpa kata TSSR (diubah/salah ketik) -> kenali dari teks dokumen
        try:
            from . import kenali as _k
        except ImportError:
            import kenali as _k
        for f in sorted(os.listdir(folder)):
            p = os.path.join(folder, f)
            if f.lower().endswith(".docx") and not f.startswith("~$") and os.path.isfile(p) \
                    and not re.search(r"BAKP|BERITA|KESEPAKATAN|PERI[JZ]INAN", f, re.IGNORECASE) and _k.docx_is_tssr(p):
                hits.append(p)
    return hits


def docx_text(path):
    """Teks paragraf .docx (satu baris per paragraf/sel). '' bila bukan docx yang sah."""
    try:
        with zipfile.ZipFile(path) as z:
            info = z.getinfo("word/document.xml")
            if info.file_size > MAX_XML:
                return ""
            xml = z.read(info).decode("utf-8", "replace")
    except (OSError, KeyError, zipfile.BadZipFile, RuntimeError):
        return ""
    # hanya isi <w:t> (teks yang terlihat); angka posisi/ukuran gambar (wp:posOffset, wp:extent) tidak ikut terbaca
    parts = []
    for m in re.finditer(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>|<w:tab/>|<w:br/>|</w:p>|</w:tc>", xml):
        tok = m.group(0)
        if m.group(1) is not None:
            parts.append(m.group(1))
        elif tok == "<w:tab/>":
            parts.append(" ")
        else:
            parts.append("\n")
    t = "".join(parts)
    t = t.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'")
    lines = [" ".join(x.split()) for x in t.split("\n")]
    return "\n".join(x for x in lines if x)


def _after(lines, label_rx, max_ahead=3):
    """Nilai sesudah label pada baris yang sama ('Label : nilai') atau 1-3 baris berikutnya (tabel docx)."""
    for i, ln in enumerate(lines):
        m = re.search(label_rx + r"\s*:?\s*(.*)$", ln, re.IGNORECASE)
        if not m:
            continue
        v = m.group(1).strip(" :")
        if v:
            return v
        for nx in lines[i + 1:i + 1 + max_ahead]:
            nx = nx.strip(" :")
            if nx:
                return nx
    return ""


def parse(path):
    """-> dict(file, ids_name, ids_text, name, address, hp) dari satu TSSR."""
    text = docx_text(path)
    lines = text.split("\n") if text else []
    flat = " ".join(lines)
    hp = None
    # '177 HP', '1,242 HP', '1.242 HP' (pemisah ribuan dari TSSR induk, review Jambi Suka Karya 2026)
    m = re.search(r"Home\s*Pass(?:es)?(?:\s+and\s+Occupation)?\s*:?\s*(\d{1,3}(?:[.,]\d{3})+|\d{1,5})\s*HP", flat,
                  re.IGNORECASE)
    if m:
        hp = int(re.sub(r"[.,]", "", m.group(1)))
    name = _after(lines, r"(?:Complex\s*/\s*Cluster\s*/\s*Building\s*Name|Site\s+Location\s+Name)")
    addr = _after(lines, r"(?:Site\s+Location\s+Address|Site\s+Address)")
    return {"file": os.path.basename(path), "ids_name": ID_RX.findall(os.path.basename(path)),
            # nomor telepon (08xx / 628xx) juga 9-12 digit: bukan ID cluster
            "ids_text": sorted({i for i in ID_RX.findall(flat) if not i.startswith(("0", "62"))}), "name": name, "address": addr, "hp": hp,
            "readable": bool(text)}


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).upper()
    return re.sub(r"[^A-Z0-9]+", " ", s).strip()


def compare(t, cluster_id, n_hpdb, kelurahan=""):
    """-> [(kode, teks, nilai, batas)] temuan TSSR vs HPDB. Kosong bila sesuai / data tidak cukup."""
    out = []
    ids = t["ids_name"] or t["ids_text"]
    if cluster_id and ids and cluster_id not in ids:
        out.append(("WARN_TSSR_ID_BEDA",
                    "TSSR %s memuat ID %s, sedangkan HPDB/KMZ %s%s: kemungkinan TSSR cluster lain - minta TSSR cluster ini"
                    % (t["file"], ", ".join(sorted(set(ids))[:3]), cluster_id,
                       (" (nama di TSSR '%s')" % t["name"][:60]) if t["name"] else ""), None, None))
    if t["hp"] is not None and n_hpdb and t["hp"] != n_hpdb:
        out.append(("WARN_TSSR_HP_BEDA",
                    "TSSR mencatat %d HP, HPDB %d HP (selisih %+d): samakan jumlah homepass TSSR dengan HPDB%s"
                    % (t["hp"], n_hpdb, t["hp"] - n_hpdb,
                       " (TSSR kemungkinan milik cluster induk / gabungan)" if t["hp"] >= 2 * n_hpdb else ""), t["hp"], n_hpdb))
    kel = _norm(kelurahan)
    if kel and t["address"] and kel not in _norm(t["address"]):
        out.append(("INFO_TSSR_WILAYAH_BEDA",
                    "alamat TSSR '%s' tidak memuat kelurahan HPDB '%s': cek wilayah di TSSR"
                    % (t["address"][:90], kelurahan), None, None))
    return out

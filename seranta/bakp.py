# -*- coding: utf-8 -*-
"""
BAKP reminder & offline check (Berita Acara Kesepakatan Perijinan / community permit form).

Part of Seranta - FTTH Design Assistant.
Copyright (C) 2026 Joseph Edward Timothy Siahaan. Licensed under GPL-2.0-or-later (see LICENSE).

No AI, no internet, no account needed. The tool:
  * reminds the designer that the BAKP must be checked and builds a visual checklist that puts each
    BAKP page next to the values it must match (cluster ID, homepass, kelurahan/kecamatan, RT/RW, vendor);
  * detects, offline, stamps or signatures that were pasted digitally (the same transparent image reused
    on several pages, or a coloured stamp on a black-and-white scan), counts pages, and checks the
    cluster ID in the file name.
Only the Python standard library, numpy and the Qt bundled with QGIS are used (Pillow as fallback).
"""
try:
    from . import _log
except ImportError:  # dijalankan sebagai modul lepas (uji unit)
    import _log
import base64
import hashlib
import os
import re
import zlib

try:
    import numpy as np
except Exception:          # pragma: no cover - numpy ships with QGIS
    np = None

MODES = ["Ingatkan + cek otomatis offline + daftar periksa (disarankan)", "Lewati (tanpa pengingat BAKP)"]
BAKP_RX = re.compile(r"BAKP|PERI[JZ]INAN|KESEPAKATAN|BA[\s_-]*KP", re.IGNORECASE)
IMG_EXT = (".pdf", ".jpg", ".jpeg", ".png")
MAX_PAGES = 6


# ---------------------------------------------------------------------------------------------
# Mencari file BAKP
# ---------------------------------------------------------------------------------------------
def find_bakp(folder):
    """Semua file BAKP di folder cluster (dan satu tingkat subfolder, kecuali folder hasil INPUT*)."""
    hits = []
    for root, dirs, files in os.walk(folder):
        rel = os.path.relpath(root, folder)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        dirs[:] = [d for d in dirs if not d.upper().startswith(("INPUT", "HASIL_PASCA"))] if depth < 1 else []
        for f in sorted(files):
            if f.startswith("~$") or not f.lower().endswith(IMG_EXT):
                continue
            if BAKP_RX.search(f):
                hits.append(os.path.join(root, f))
    return hits


OTHER_DOC_RX = re.compile(r"HPDB|KMZ|TSSR|EVID[AE]N[CS]E|FOTO|PHOTO|SURVEY|BOQ|BOM|INVOICE|QC_|RINGKASAN|LAPORAN",
                          re.IGNORECASE)
CONTENT_RX = re.compile(rb"BERITA\s*ACARA|KESEPAKATAN|PERI[JZ]INAN|PERSETUJUAN\s+WARGA", re.IGNORECASE)


def find_candidates(folder, cluster_id=""):
    """Kandidat BAKP yang namanya TIDAK memuat kata BAKP (spesifikasi X-01 / O.1 / UAT-14): dokumen PDF/gambar di
    folder cluster yang bukan HPDB/KMZ/TSSR/foto evidence. Skor: ID cluster di nama (+3), teks PDF memuat 'Berita
    Acara/Kesepakatan/Perijinan' (+3), PDF hasil scan 1-6 halaman (+1). -> [(skor, path, alasan)] urut skor."""
    out = []
    try:
        files = sorted(os.listdir(folder))
    except OSError:
        return out
    for f in files:
        p = os.path.join(folder, f)
        if f.startswith("~$") or not os.path.isfile(p) or not f.lower().endswith(IMG_EXT) or BAKP_RX.search(f):
            continue
        if OTHER_DOC_RX.search(f):
            continue
        score, why = 0, []
        if cluster_id and cluster_id in f:
            score += 3
            why.append("ID cluster %s di nama file" % cluster_id)
        if f.lower().endswith(".pdf"):
            try:
                with open(p, "rb") as fh:
                    head = fh.read(2000000)
                if CONTENT_RX.search(head):
                    score += 3
                    why.append("teks 'Berita Acara/Kesepakatan/Perijinan' di PDF")
                n = len(re.findall(rb"/Type\s*/Page[^s]", head))
                if 1 <= n <= MAX_PAGES and re.search(rb"/Subtype\s*/Image", head):
                    score += 1
                    why.append("PDF hasil scan %d halaman" % n)
                if re.search(rb"CamScanner|intsig|Scanner", head, re.IGNORECASE):
                    score += 1
                    why.append("dibuat aplikasi pemindai")
            except OSError as _e:
                _log.note(_e)
        if score >= 3:
            out.append((score, p, "; ".join(why)))
    out.sort(key=lambda t: -t[0])
    return out


def ids_in_name(name):
    return re.findall(r"(?<!\d)(\d{9,12})(?!\d)", os.path.basename(name))


# ---------------------------------------------------------------------------------------------
# Pembongkar PDF (hanya yang dibutuhkan: halaman, gambar per halaman, metadata)
# ---------------------------------------------------------------------------------------------
_OBJ = re.compile(rb"(\d+)\s+(\d+)\s+obj\b")
_REF = rb"(\d+)\s+\d+\s+R"


def _match_dict(b, i):
    """b[i:] dimulai dengan '<<'; kembalikan indeks setelah '>>' yang berpasangan."""
    depth, n = 0, len(b)
    while i < n:
        if b.startswith(b"<<", i):
            depth += 1
            i += 2
        elif b.startswith(b">>", i):
            depth -= 1
            i += 2
            if depth == 0:
                return i
        elif b[i:i + 1] == b"(":                 # string literal: lewati
            lvl = 0
            while i < n:
                c = b[i:i + 1]
                if c == b"\\":
                    i += 2
                    continue
                if c == b"(":
                    lvl += 1
                elif c == b")":
                    lvl -= 1
                    if lvl == 0:
                        i += 1
                        break
                i += 1
        else:
            i += 1
    return n


class PdfDoc:
    def __init__(self, data):
        self.data = data
        self.objs = {}      # num -> (dict_bytes, stream_bytes|None)
        self._parse()

    def _length_of(self, d):
        m = re.search(rb"/Length\s+" + _REF, d)
        if m:
            mm = re.search(rb"(?<!\d)" + m.group(1) + rb"\s+0\s+obj\s*(\d+)", self.data)
            return int(mm.group(1)) if mm else None
        m = re.search(rb"/Length\s+(\d+)", d)
        return int(m.group(1)) if m else None

    def _parse(self):
        data, pos = self.data, 0
        while True:
            m = _OBJ.search(data, pos)
            if not m:
                break
            num, i = int(m.group(1)), m.end()
            while i < len(data) and data[i:i + 1] in b" \r\n\t":
                i += 1
            dct, stream = b"", None
            if data.startswith(b"<<", i):
                j = _match_dict(data, i)
                dct = data[i:j]
                k = j
                while k < len(data) and data[k:k + 1] in b" \r\n\t":
                    k += 1
                if data.startswith(b"stream", k):
                    s = k + 6
                    if data[s:s + 2] == b"\r\n":
                        s += 2
                    elif data[s:s + 1] in (b"\n", b"\r"):
                        s += 1
                    ln = self._length_of(dct)
                    e = s + ln if ln is not None else -1
                    if ln is None or data.find(b"endstream", e, e + 64) < 0:
                        e = data.find(b"endstream", s)
                        while e > s and data[e - 1:e] in b"\r\n":
                            e -= 1
                    stream = data[s:e]
                    end = data.find(b"endobj", e)
                else:
                    end = data.find(b"endobj", j)
            else:
                end = data.find(b"endobj", i)
                dct = data[i:end] if end > 0 else b""
            self.objs[num] = (dct, stream)
            if end < 0:
                break
            pos = end + 6

    # ---- helpers
    def get(self, num):
        return self.objs.get(int(num), (b"", None))

    def _sub(self, d, key):
        """Nilai kunci: (ref_num) atau (inline_bytes)."""
        m = re.search(rb"/" + key + rb"\s*(<<|" + _REF + rb")", d)
        if not m:
            return None
        if m.group(1) == b"<<":
            j = _match_dict(d, m.start(1))
            return d[m.start(1):j]
        return self.get(int(m.group(2)))[0]

    def pages(self):
        """Daftar (dict_halaman, resources_terwaris) sesuai urutan pohon halaman."""
        root = None
        for n, (d, _) in self.objs.items():
            if re.search(rb"/Type\s*/Catalog", d):
                m = re.search(rb"/Pages\s+" + _REF, d)
                root = int(m.group(1)) if m else None
                break
        out, seen = [], set()

        def walk(num, res):
            if num in seen or len(out) > 500:
                return
            seen.add(num)
            d = self.get(num)[0]
            r = self._sub(d, b"Resources") or res
            if re.search(rb"/Type\s*/Pages", d):
                km = re.search(rb"/Kids\s*\[([^\]]*)\]", d)
                for k in re.findall(_REF, km.group(1) if km else b""):
                    walk(int(k), r)
            elif re.search(rb"/Type\s*/Page(?![s\w])", d):
                out.append((d, r))
        if root:
            walk(root, None)
        if not out:          # cadangan: urutan objek
            for n in sorted(self.objs):
                d = self.objs[n][0]
                if re.search(rb"/Type\s*/Page(?![s\w])", d):
                    out.append((d, self._sub(d, b"Resources")))
        return out

    def images_on(self, res, depth=0):
        """Gambar (num, dict, stream) yang dipakai sumber daya halaman/form."""
        if not res or depth > 3:
            return []
        xo = self._sub(res, b"XObject")
        if not xo:
            return []
        out = []
        for num in re.findall(rb"/[^\s/<>\[\]]+\s+" + _REF, xo):
            num = int(num)
            d, s = self.get(num)
            if re.search(rb"/Subtype\s*/Image", d):
                out.append((num, d, s))
            elif re.search(rb"/Subtype\s*/Form", d):
                out.extend(self.images_on(self._sub(d, b"Resources") or res, depth + 1))
        return out

    def info(self):
        meta = {}
        for n, (d, _) in self.objs.items():
            if re.search(rb"/Producer|/Creator", d) and not re.search(rb"/Type\s*/(Page|Catalog|XObject)", d):
                for k in (b"Producer", b"Creator", b"Author", b"Title"):
                    m = re.search(rb"/" + k + rb"\s*\(([^)]*)\)", d)
                    if m:
                        meta[k.decode()] = m.group(1).decode("latin-1", "replace")
        return meta


def _int(d, key, default=0):
    m = re.search(rb"/" + key + rb"\s+(\d+)", d)
    return int(m.group(1)) if m else default


def _filters(d):
    m = re.search(rb"/Filter\s*(\[[^\]]*\]|/\w+)", d)
    return [f.decode() for f in re.findall(rb"/(\w+)", m.group(1))] if m else []


def _png_unpredict(raw, cols, bpp):
    stride, out, prev, i = cols * bpp, bytearray(), bytearray(cols * bpp), 0
    while i < len(raw):
        ft, row = raw[i], bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride
        for x in range(len(row)):
            a = row[x - bpp] if x >= bpp else 0
            b = prev[x]
            c = prev[x - bpp] if x >= bpp else 0
            if ft == 1:
                row[x] = (row[x] + a) & 255
            elif ft == 2:
                row[x] = (row[x] + b) & 255
            elif ft == 3:
                row[x] = (row[x] + ((a + b) >> 1)) & 255
            elif ft == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                row[x] = (row[x] + (a if pa <= pb and pa <= pc else (b if pb <= pc else c))) & 255
        out += row
        prev = row
    return bytes(out)


def pdf_image_array(doc, d, s):
    """Gambar PDF -> numpy HxWx3 uint8 (DCT/JPEG, Flate 8-bit gray/RGB). None bila tak didukung."""
    if s is None:
        return None
    fl = _filters(d)
    w, h, bpc = _int(d, b"Width"), _int(d, b"Height"), _int(d, b"BitsPerComponent", 8)
    try:
        while fl and fl[0] in ("FlateDecode", "Fl"):
            s = zlib.decompress(s)
            fl = fl[1:]
            if not fl:
                break
        if fl and fl[0] in ("DCTDecode", "DCT"):
            return decode_image(s)
        if fl:
            return None                      # JPX/CCITT/JBIG2: tidak didukung -> cek visual
        if bpc != 8 or not w or not h:
            return None
        ncomp = 3 if re.search(rb"DeviceRGB|/N\s+3", d + _cs_bytes(doc, d)) else 1
        pm = re.search(rb"/Predictor\s+(\d+)", d)
        if pm and int(pm.group(1)) >= 10:
            s = _png_unpredict(s, w, ncomp)
        a = np.frombuffer(s[:w * h * ncomp], np.uint8)
        if a.size < w * h * ncomp:
            return None
        a = a.reshape(h, w, ncomp)
        return np.repeat(a, 3, axis=2) if ncomp == 1 else a
    except Exception:
        return None


def _cs_bytes(doc, d):
    m = re.search(rb"/ColorSpace\s+" + _REF, d)
    if not m:
        return b""
    cd = doc.get(int(m.group(1)))[0]
    m2 = re.search(rb"\[\s*/ICCBased\s+" + _REF, cd)
    return doc.get(int(m2.group(1)))[0] if m2 else cd


# ---------------------------------------------------------------------------------------------
# Gambar: decode/encode/resize (Qt bawaan QGIS; cadangan Pillow)
# ---------------------------------------------------------------------------------------------
def _qt():
    try:
        from qgis.PyQt.QtGui import QImage
        from qgis.PyQt.QtCore import QByteArray, QBuffer, QIODevice
        return QImage, QByteArray, QBuffer, QIODevice
    except Exception:
        return None


def _qfmt(QImage, name):
    return getattr(QImage, name, None) or getattr(QImage.Format, name)


def decode_image(b):
    q = _qt()
    if q:
        QImage = q[0]
        img = QImage()
        if img.loadFromData(b):
            img = img.convertToFormat(_qfmt(QImage, "Format_RGB888"))
            w, h, bpl = img.width(), img.height(), img.bytesPerLine()
            ptr = img.constBits()
            try:
                ptr.setsize(h * bpl)
                buf = bytes(ptr)
            except AttributeError:
                buf = bytes(ptr.asstring(h * bpl))
            return np.frombuffer(buf, np.uint8).reshape(h, bpl)[:, :w * 3].reshape(h, w, 3).copy()
    try:
        from PIL import Image
        import io
        return np.asarray(Image.open(io.BytesIO(b)).convert("RGB")).copy()
    except Exception:
        return None


def encode_jpeg(a, quality=85):
    a = np.ascontiguousarray(a, dtype=np.uint8)
    h, w = a.shape[:2]
    q = _qt()
    if q:
        QImage, QByteArray, QBuffer, QIODevice = q
        img = QImage(a.tobytes(), w, h, 3 * w, _qfmt(QImage, "Format_RGB888")).copy()
        ba = QByteArray()
        bf = QBuffer(ba)
        wo = getattr(QIODevice, "WriteOnly", None) or QIODevice.OpenModeFlag.WriteOnly
        bf.open(wo)
        img.save(bf, "JPEG", quality)
        bf.close()
        return bytes(ba)
    from PIL import Image
    import io
    out = io.BytesIO()
    Image.fromarray(a).save(out, "JPEG", quality=quality)
    return out.getvalue()


def shrink(a, max_side):
    """Perkecil dengan rata-rata blok (tajam untuk teks) hingga sisi terpanjang <= max_side."""
    h, w = a.shape[:2]
    f = int(np.ceil(max(h, w) / float(max_side)))
    if f <= 1:
        return a
    hh, ww = (h // f) * f, (w // f) * f
    return a[:hh, :ww].reshape(hh // f, f, ww // f, f, 3).mean(axis=(1, 3)).astype(np.uint8)


def fit(a, max_side):
    """Perkecil ke <= max_side dengan faktor pecahan (nearest pada grid rata-rata 2x)."""
    h, w = a.shape[:2]
    s = max(h, w) / float(max_side)
    if s <= 1:
        return a
    if s >= 2:
        a = shrink(a, int(max(h, w) / (s / 2.0)))     # turunkan dulu kira-kira 2x target
        h, w = a.shape[:2]
        s = max(h, w) / float(max_side)
    ys = (np.arange(int(h / s)) * s).astype(int)
    xs = (np.arange(int(w / s)) * s).astype(int)
    return a[ys][:, xs]


# ---------------------------------------------------------------------------------------------
# Muat dokumen BAKP -> halaman + tempelan
# ---------------------------------------------------------------------------------------------
def load_bakp(path):
    """Kembalikan dict: pages[{arr, w, h}], overlays[{arr, page, hash, smask, w, h}], meta, notes."""
    res = {"path": path, "pages": [], "overlays": [], "meta": {}, "notes": [], "n_pages": 0}
    data = open(path, "rb").read()
    res["sha"] = hashlib.sha256(data).hexdigest()
    if not path.lower().endswith(".pdf"):
        a = decode_image(data)
        if a is None:
            res["notes"].append("gambar tidak bisa dibaca")
        else:
            res["pages"].append({"arr": a, "w": a.shape[1], "h": a.shape[0]})
        res["n_pages"] = len(res["pages"])
        return res
    doc = PdfDoc(data)
    res["meta"] = doc.info()
    pages = doc.pages()
    res["n_pages"] = len(pages)
    for pi, (pd, rs) in enumerate(pages[:MAX_PAGES], 1):
        imgs = doc.images_on(rs)
        if not imgs:
            res["notes"].append("halaman %d tanpa gambar scan (PDF digital/teks) - cek visual" % pi)
            continue
        big = max(imgs, key=lambda t: _int(t[1], b"Width") * _int(t[1], b"Height"))
        a = pdf_image_array(doc, big[1], big[2])
        if a is None:
            res["notes"].append("halaman %d: format gambar %s belum didukung - cek visual" % (pi, "/".join(_filters(big[1])) or "?"))
        else:
            res["pages"].append({"arr": a, "w": a.shape[1], "h": a.shape[0], "no": pi})
        for num, d, s in imgs:
            if num == big[0]:
                continue
            w, h = _int(d, b"Width"), _int(d, b"Height")
            if re.search(rb"/ImageMask\s+true", d) or not s or w * h == 0:
                continue
            if re.search(rb"/Subtype\s*/Image", d) and any(num == int(x) for x in re.findall(rb"/SMask\s+" + _REF, b"".join(dd for _, dd, _ in imgs))):
                continue                     # objek ini adalah mask milik gambar lain
            aspect = w / float(h)
            if aspect > 5 or aspect < 0.2 or min(w, h) < 80:
                res["wm"] = res.get("wm", 0) + 1
                continue
            arr = pdf_image_array(doc, d, s)
            sm = re.search(rb"/SMask\s+" + _REF, d)
            if sm is not None and arr is not None:          # tempel di atas latar putih seperti tampil di PDF
                md, ms = doc.get(int(sm.group(1)))
                m = pdf_image_array(doc, md, ms)
                if m is not None and m.shape[:2] == arr.shape[:2]:
                    al = m[..., :1].astype(np.float32) / 255.0
                    arr = (arr * al + 255.0 * (1 - al)).astype(np.uint8)
            res["overlays"].append({"page": pi, "w": w, "h": h, "hash": hashlib.sha256(s).hexdigest(),
                                    "smask": sm is not None, "arr": arr})
    if res.get("wm"):
        res["notes"].append("%d watermark/label kecil (mis. 'Dipindai dengan CamScanner') diabaikan" % res["wm"])
    if res["n_pages"] > MAX_PAGES:
        res["notes"].append("hanya %d halaman pertama yang dibaca dari %d" % (MAX_PAGES, res["n_pages"]))
    return res


# ---------------------------------------------------------------------------------------------
# Analisis offline (tanpa internet)
# ---------------------------------------------------------------------------------------------
def ink_stats(a):
    s = shrink(a, 900).astype(np.int16)
    r, g, b = s[..., 0], s[..., 1], s[..., 2]
    mx, mn = s.max(axis=2), s.min(axis=2)
    sat = mx - mn
    colored = (sat > 45) & (mx < 245)
    stamp = colored & (b > r - 10) & (b > g + 20)            # biru/ungu: tinta stempel & pulpen
    red = colored & (r > g + 50) & (r > b + 30)
    hh, ww = sat.shape
    ys, xs = np.nonzero(stamp)
    box = None
    if ys.size > 50:
        y0, y1 = np.percentile(ys, [5, 95])
        x0, x1 = np.percentile(xs, [5, 95])
        box = (x0 / ww, y0 / hh, x1 / ww, y1 / hh)
    return {"gray": float((sat > 25).mean()) < 0.003, "blue_frac": float(stamp.mean()),
            "red_frac": float(red.mean()), "box": box}


def ahash(a, n=16):
    """Hash rata-rata 16x16 (256 bit) untuk mengenali gambar yang sama walau dikompres ulang."""
    g = a.astype(np.float32).mean(axis=2)
    h, w = g.shape
    ys = (np.arange(n + 1) * h / n).astype(int)
    xs = (np.arange(n + 1) * w / n).astype(int)
    m = np.array([[g[ys[i]:ys[i + 1], xs[j]:xs[j + 1]].mean() for j in range(n)] for i in range(n)])
    return m > m.mean()


def offline_check(doc):
    """Temuan dari struktur file & tinta. Hasil: dict ringkas + daftar (kode, ok, teks)."""
    items, info = [], {}
    pages = doc["pages"]
    info["n_pages"] = doc["n_pages"]
    groups = []                      # kelompok gambar tempelan yang identik secara visual
    # Lencana aplikasi pemindai (mis. 'Dipindai dengan CamScanner', 240x90 px) ikut tertanam sebagai gambar kecil di
    # SETIAP halaman. Itu bukan stempel/tanda tangan: kecil (< 2% luas halaman) dan abu-abu, atau muncul di >= 80%
    # halaman pada ukuran yang sama. Disaring dulu agar tidak dilaporkan sebagai "stempel ditempel digital".
    area = {p["no"]: float(p["w"] * p["h"]) for p in pages if p.get("w") and p.get("h")}
    n_pg = max(1, doc.get("n_pages") or len(pages))
    by_hash = {}
    for ov in doc["overlays"]:
        by_hash.setdefault(ov["hash"], set()).add(ov["page"])
    keep, badge = [], 0
    for ov in doc["overlays"]:
        pa = area.get(ov["page"]) or 0.0
        small = pa > 0 and (ov["w"] * ov["h"]) / pa < 0.02
        gray = ov.get("arr") is not None and ink_stats(ov["arr"])["gray"]
        everywhere = len(by_hash.get(ov["hash"], ())) >= max(2, int(round(0.8 * n_pg)))
        if small and (gray or everywhere):
            badge += 1
            continue
        keep.append(ov)
    if badge:
        doc.setdefault("notes", []).append("%d lencana/watermark aplikasi pemindai (gambar kecil abu-abu atau sama di "
                                           "hampir semua halaman) diabaikan - bukan stempel/tanda tangan" % badge)
    doc["overlays"] = keep
    for ov in doc["overlays"]:
        ov["ahash"] = ahash(ov["arr"]) if ov.get("arr") is not None else None
        for g in groups:
            if ov["hash"] == g[0]["hash"] or (ov["ahash"] is not None and g[0]["ahash"] is not None
                                              and int((ov["ahash"] != g[0]["ahash"]).sum()) <= 24):
                g.append(ov)
                break
        else:
            groups.append([ov])
    dup = [g for g in groups if len(g) >= 2]
    tempel = [ov for ov in doc["overlays"] if ov["smask"] or any(ov in g for g in dup)]
    info["overlay_pages"] = sorted({ov["page"] for ov in tempel})
    ov_color = ""
    for ov in tempel:
        if ov.get("arr") is not None:
            st = ink_stats(ov["arr"])
            if not st["gray"] and st["blue_frac"] > 0.01:
                ov_color = "biru/ungu"
                break
    info["overlay_color"] = ov_color
    if dup:
        n = max(len(g) for g in dup)
        hal = sorted({ov["page"] for g in dup for ov in g})
        items.append(("BAKP_STEMPEL_TTD_TEMPELAN_DIGITAL", False,
                      "gambar stempel/tanda tangan%s yang sama ditempel digital %d kali (halaman %s) - minta BAKP "
                      "dengan tanda tangan & stempel basah (hasil scan asli)" % (
                          (" " + ov_color) if ov_color else "", n, ", ".join(map(str, hal)))))
    elif tempel:
        items.append(("BAKP_ADA_GAMBAR_TEMPELAN", False,
                      "ada gambar tempelan transparan di halaman %s (kemungkinan stempel/ttd digital) - cek keaslian"
                      % ", ".join(map(str, info["overlay_pages"]))))
    stats = []
    for p in pages:
        st = ink_stats(p["arr"])
        st["no"] = p.get("no", 1)
        stats.append(st)
    info["ink"] = stats
    if stats and all(s["gray"] for s in stats) and ov_color:
        info["bw"] = True
        items.append(("INFO_BAKP_HALAMAN_HITAM_PUTIH_STEMPEL_BERWARNA", None,
                      "halaman hasil scan hitam-putih tetapi stempel berwarna %s -> stempel ditambahkan setelah scan" % ov_color))
    elif stats and all(s["gray"] for s in stats):
        info["bw"] = True
        items.append(("BAKP_SCAN_HITAM_PUTIH", None,
                      "scan hitam-putih: keaslian stempel dicek visual (lihat daftar periksa)"))
    else:
        info["bw"] = False
        stamp_pages = [s["no"] for s in stats if s["blue_frac"] > 0.0015]
        info["stamp_pages"] = stamp_pages
    meta = doc.get("meta", {})
    prod = " ".join(meta.values())
    if re.search(r"photoshop|canva|illustrator|gimp|paint", prod, re.IGNORECASE):
        items.append(("BAKP_DIEDIT_APLIKASI_GRAFIS", False, "metadata PDF menunjukkan aplikasi edit gambar: %s" % prod[:80]))
    return info, items



# ---------------------------------------------------------------------------------------------
# Checklist: what the reviewer must verify on the BAKP, with the expected values
# ---------------------------------------------------------------------------------------------
def checklist(exp):
    """Butir pemeriksaan BAKP + nilai seharusnya (dari HPDB/KMZ/FINDIM)."""
    lok = " / ".join(v for v in (exp.get("kelurahan"), exp.get("kecamatan"), exp.get("kota")) if v) or "-"
    fd = exp.get("findim")
    if fd:
        lok += "  (FINDIM: Kel. %s, Kec. %s, %s)" % fd
    hp = str(exp.get("hp_hpdb") or "-")
    if exp.get("hp_kmz") and exp.get("hp_kmz") != exp.get("hp_hpdb"):
        hp += " (KMZ %s)" % exp["hp_kmz"]
    return [
        ("Cluster ID", exp.get("cluster_id") or "-", "tabel atas dan bagian bawah halaman 1 harus sama"),
        ("Homepass", hp, "tidak boleh kurang dari HP yang didesain"),
        ("Kelurahan / Kecamatan / Kota", lok, "nama wilayah sesuai FINDIM"),
        ("RT/RW / nama cluster", exp.get("cluster_name") or "-", "nomor RT/RW sama dengan nama cluster"),
        ("Pilihan persetujuan", "menyetujui", "kata 'tidak menyetujui' harus dicoret"),
        ("Tanda tangan & stempel Ketua RT/RW", "ada, basah (bukan tempelan)", "nama & cap jelas"),
        ("Tanggal BAKP", "terisi, tidak di masa depan", "hari, tanggal, bulan, tahun"),
        ("Mitra / vendor", exp.get("vendor") or "-", "nama PT pelaksana"),
        ("Lembar verifikasi warga (bila ada)", "permit approved", "catat bila ada kompensasi"),
    ]


def evaluate(off, exp):
    """Temuan offline + cek nama file. Kembalikan items[(kode, ok, teks)]."""
    items = list(off[1])
    want_id = exp.get("cluster_id", "")
    fname = exp.get("bakp_file", "")
    fid = ids_in_name(fname)
    if want_id and not fid:
        items.append(("INFO_BAKP_NAMA_FILE_TANPA_ID", None,
                      "nama file BAKP tidak memuat Cluster ID (disarankan BAKP_<ID>_<nama>.pdf)"))
    elif want_id and want_id not in fid:
        items.append(("BAKP_NAMA_FILE_ID_BEDA", False,
                      "nama file BAKP memuat ID %s, sedangkan HPDB/KMZ %s" % (", ".join(fid), want_id)))
    n = off[0].get("n_pages", 0)
    if n and n < 2:
        items.append(("INFO_BAKP_HALAMAN_SEDIKIT", None, "BAKP hanya %d halaman; format standar 2-4 halaman" % n))
    return items


def pages_b64(doc, max_side=1300, q=78):
    return [(p.get("no", i + 1), base64.b64encode(encode_jpeg(fit(p["arr"], max_side), q)).decode("ascii"))
            for i, p in enumerate(doc["pages"])]


# ---------------------------------------------------------------------------------------------
# One entry point for the main tool
# ---------------------------------------------------------------------------------------------
def check_cluster(folder, exp, feedback=None, manual=None):
    """Kembalikan dict: ok, summary, lines[], items[], checklist[], pages[(no, b64)], file, status.
    status (spesifikasi O.1): BAKP_MAPPED (dipilih manual), BAKP_FOUND (nama memuat BAKP), BAKP_UNRECOGNIZED
    (kandidat dari isi/ID cluster - perlu konfirmasi), BAKP_NOT_SUPPLIED (tidak ada sumber -> belum bisa diputuskan)."""
    res = {"ok": None, "summary": "", "lines": ["", "BAKP (BERITA ACARA KESEPAKATAN PERIJINAN) - WAJIB DICEK MANUAL"],
           "items": [], "checklist": checklist(exp), "pages": [], "file": "", "status": ""}
    L = res["lines"]
    if manual and os.path.isfile(manual):
        files, res["status"] = [manual], "BAKP_MAPPED"
        L.append("  Sumber    : dipilih manual (BAKP_MAPPED)")
    else:
        files = find_bakp(folder)
        res["status"] = "BAKP_FOUND" if files else ""
    if not files:
        cands = find_candidates(folder, exp.get("cluster_id", ""))
        if cands:
            sc, path0, why = cands[0]
            files, res["status"] = [path0], "BAKP_UNRECOGNIZED"
            L.append("  Kandidat  : %s (nama tanpa kata BAKP; dikenali dari %s) -> BAKP_UNRECOGNIZED, konfirmasi atau "
                     "pilih manual di isian 'file BAKP'" % (os.path.basename(path0), why))
            res["items"].append(("UNV_BAKP_KANDIDAT_PERLU_KONFIRMASI", None,
                                 "BAKP dikenali dari isi/nama (%s): %s - konfirmasi, atau pilih file di isian opsional BAKP"
                                 % (why, os.path.basename(path0))))
            for _s, pth, w in cands[1:3]:
                L.append("  Kandidat lain: %s (%s)" % (os.path.basename(pth), w))
    if not files:
        res.update(ok=None, status="BAKP_NOT_SUPPLIED",
                   summary="BAKP_NOT_SUPPLIED: tidak ada file BAKP/kandidat di folder cluster - minta ke vendor; kepatuhan "
                           "belum bisa diputuskan")
        L.append("  ! Tidak ada file BAKP (nama memuat BAKP, atau dokumen ber-ID cluster) di folder cluster. Minta BAKP ke "
                 "vendor sebelum desain, atau pilih file di isian opsional BAKP.")
        res["items"].append(("UNV_BAKP_NOT_SUPPLIED", None, "BAKP_NOT_SUPPLIED: file BAKP tidak ada di folder cluster"))
        return res
    path = max(files, key=os.path.getmtime)
    res["file"] = path
    L.append("  File BAKP : %s%s" % (os.path.basename(path), " (+%d file lain)" % (len(files) - 1) if len(files) > 1 else ""))
    exp = dict(exp, bakp_file=os.path.basename(path))
    if not exp.get("vendor"):
        vm = re.search(r"PT[.\s_]+([A-Za-z]+)", os.path.basename(path))
        if vm:
            exp["vendor"] = vm.group(1)
            res["checklist"] = checklist(exp)
    try:
        doc = load_bakp(path)
        off = offline_check(doc)
    except Exception as e:
        doc, off = None, ({"n_pages": 0}, [])
        L.append("  ! BAKP tidak bisa dibuka otomatis (%s) - buka manual" % e)
    if doc:
        L.append("  Halaman   : %d%s" % (doc["n_pages"], ("; " + "; ".join(doc["notes"][:2])) if doc["notes"] else ""))
        try:
            res["pages"] = pages_b64(doc)
        except Exception:
            res["pages"] = []
    items = evaluate(off, exp)
    for k, o, t in items:
        L.append("  %s %s" % ({True: "[OK] ", False: "[CEK]", None: "[i]  "}[o], t))
    L.append("  JANGAN LUPA cocokkan isian BAKP dengan nilai berikut (centang di laporan HTML):")
    for a, b, c in res["checklist"]:
        L.append("    [ ] %-34s : %s  (%s)" % (a, b, c))
    n_cek = sum(1 for _, o, _ in items if o is False)
    res["ok"] = False if n_cek else None
    res["summary"] = ("%d temuan otomatis; " % n_cek if n_cek else "") + "WAJIB cek manual isian BAKP (daftar periksa di laporan HTML)"
    if res["status"] == "BAKP_UNRECOGNIZED":
        res["summary"] = "kandidat BAKP %s (perlu konfirmasi); " % os.path.basename(path) + res["summary"]
    res["items"] = items
    return res

# -*- coding: utf-8 -*-
"""
Gambar peta per temuan untuk laporan HTML dan Word.

Digambar langsung dari data jaringan yang sudah ada di memori (homepass, tiang, jalur/kabel, perangkat, batas wilayah)
dengan QPainter di atas QImage. Tidak butuh peta dasar, internet, atau mesin render QGIS, sehingga aman dijalankan
di thread Processing (latar belakang) dan hasilnya sama di setiap komputer.

Setiap gambar memuat: objek di sekitar temuan, geometri temuan yang disorot dengan warna tingkat, label tiang/perangkat,
skala batang, panah utara, ID temuan dan keterangan singkat.

Part of Seranta - FTTH Design Assistant.
Copyright (C) 2026 Joseph Edward Timothy Siahaan. Licensed under GPL-2.0-or-later (see LICENSE).
"""
import base64
import math
import os

try:
    from qgis.PyQt.QtCore import QPointF, QRectF, Qt, QBuffer, QByteArray, QIODevice
    from qgis.PyQt.QtGui import QImage, QPainter, QColor, QPen, QBrush, QFont, QPolygonF, QPainterPath
except ImportError:  # uji unit di luar QGIS
    from PyQt5.QtCore import QPointF, QRectF, Qt, QBuffer, QByteArray, QIODevice
    from PyQt5.QtGui import QImage, QPainter, QColor, QPen, QBrush, QFont, QPolygonF, QPainterPath


def _e(*cands):
    """Enum Qt5/Qt6: ambil nama pertama yang ada (mis. 'Format.Format_RGB32' lalu 'Format_RGB32')."""
    for owner, names in cands:
        for n in names.split("|"):
            obj = owner
            for part in n.split("."):
                obj = getattr(obj, part, None)
                if obj is None:
                    break
            if obj is not None:
                return obj
    return None


FMT = _e((QImage, "Format.Format_ARGB32_Premultiplied|Format_ARGB32_Premultiplied"))
AA = _e((QPainter, "RenderHint.Antialiasing|Antialiasing"))
TAA = _e((QPainter, "RenderHint.TextAntialiasing|TextAntialiasing"))
NOPEN = _e((Qt, "PenStyle.NoPen|NoPen"))
DASH = _e((Qt, "PenStyle.DashLine|DashLine"))
DOT = _e((Qt, "PenStyle.DotLine|DotLine"))
ROUND = _e((Qt, "PenCapStyle.RoundCap|RoundCap"))
ALIGN_L = _e((Qt, "AlignmentFlag.AlignLeft|AlignLeft"))
ALIGN_VC = _e((Qt, "AlignmentFlag.AlignVCenter|AlignVCenter"))
WRITE_ONLY = _e((QIODevice, "OpenModeFlag.WriteOnly|WriteOnly"))
BOLD = _e((QFont, "Weight.DemiBold|DemiBold"))

SEV_COLOR = dict(zip(("ERROR", "WARNING", "UNVERIFIED", "INFO", "PASS", "CEK"), ("#DA1E28", "#BA4E00", "#6F6F6F", "#0043CE", "#198038", "#DA1E28")))
SEV_WORD = dict(zip(("ERROR", "WARNING", "UNVERIFIED", "INFO", "PASS", "CEK"), ("Wajib diperbaiki", "Perlu ditinjau", "Belum bisa dicek", "Catatan", "Lolos", "Perlu dicek")))
# gaya objek latar
STYLE = {
    "route": ("#8D8D8D", 2.0), "cable": ("#3D6BB3", 2.2), "cable_new": ("#0F62FE", 2.4), "drop": ("#B8B8B8", 0.8),
    "pancingan": ("#8A3FFC", 2.0), "feeder": ("#005D5D", 2.6),
    "hp": ("#C69200", 3.0), "pole_new": ("#E8590C", 4.2), "pole_ext": ("#525252", 4.2), "pole": ("#E8590C", 4.2),
    "fat": ("#198038", 6.0), "fdt": ("#6929C4", 7.0), "closure": ("#005D5D", 5.0),
    "boundary": ("#8A3FFC", 1.4), "funnel": ("#6F6F6F", 1.2),
    "boundary_other": ("#D12771", 1.8), "hp_other": ("#D12771", 5.5),
}


class Scene(object):
    """Kumpulan objek peta (lon/lat WGS84). kind menentukan gaya (lihat STYLE)."""

    def __init__(self):
        self.lines = []      # (pts, kind)
        self.points = []     # (x, y, kind, label)
        self.polys = []      # (ring, kind)
        # atribut per objek (sejajar dengan daftar di atas) untuk peta interaktif di laporan HTML
        self.attrs_l, self.attrs_p, self.attrs_y = [], [], []

    def add_line(self, pts, kind="route", attrs=None):
        if pts and len(pts) >= 2:
            self.lines.append(([(float(x), float(y)) for x, y in pts], kind))
            self.attrs_l.append(attrs or {})

    def add_point(self, x, y, kind="pole", label="", attrs=None):
        self.points.append((float(x), float(y), kind, label or ""))
        self.attrs_p.append(attrs or {})

    def add_poly(self, ring, kind="boundary", attrs=None):
        if ring and len(ring) >= 3:
            self.polys.append(([(float(x), float(y)) for x, y in ring], kind))
            self.attrs_y.append(attrs or {})


class _Proj(object):
    """Proyeksi lokal ekuirektangular (meter) -> piksel."""

    def __init__(self, cx, cy, half_w_m, W, H):
        self.kx = 111320.0 * math.cos(math.radians(cy))
        self.ky = 110540.0
        self.cx, self.cy, self.W, self.H = cx, cy, W, H
        self.mpp = (2.0 * half_w_m) / W                     # meter per piksel

    def px(self, x, y):
        return QPointF(self.W / 2.0 + (x - self.cx) * self.kx / self.mpp, self.H / 2.0 - (y - self.cy) * self.ky / self.mpp)

    def bbox(self, pad=40):
        hw = (self.W / 2.0 + pad) * self.mpp
        hh = (self.H / 2.0 + pad) * self.mpp
        return (self.cx - hw / self.kx, self.cy - hh / self.ky, self.cx + hw / self.kx, self.cy + hh / self.ky)


def _inside(b, x, y):
    return b[0] <= x <= b[2] and b[1] <= y <= b[3]


def _nice(m):
    for v in (5, 10, 20, 25, 50, 100, 200, 250, 500, 1000):
        if v >= m:
            return v
    return 1000


def render(scene, finding, size=(960, 600), min_half_m=45.0):
    """finding: dict(fid, sev, title, lon, lat, line=[(x,y),...] atau None, value_text, label).
    Kembali: QImage."""
    W, H = size
    pts = finding.get("line") or []
    cx, cy = finding["lon"], finding["lat"]
    half = min_half_m
    if pts:
        xs = [p[0] for p in pts] + [cx]
        ys = [p[1] for p in pts] + [cy]
        cx, cy = (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0
        kx = 111320.0 * math.cos(math.radians(cy))
        span_w = (max(xs) - min(xs)) * kx
        span_h = (max(ys) - min(ys)) * 110540.0 * W / float(H)
        half = max(min_half_m, 0.5 * max(span_w, span_h) + 25.0)
    pr = _Proj(cx, cy, half, W, H)
    bb = pr.bbox()
    img = QImage(W, H, FMT)
    img.fill(QColor("#FFFFFF"))
    p = QPainter(img)
    p.setRenderHint(AA, True)
    p.setRenderHint(TAA, True)
    # grid tipis 10 m-an untuk rasa skala
    p.setPen(QPen(QColor("#F2F4F8"), 1))
    step = _nice(half / 3.0) / pr.mpp
    if step > 12:
        x0 = (W / 2.0) % step
        while x0 < W:
            p.drawLine(QPointF(x0, 0), QPointF(x0, H))
            x0 += step
        y0 = (H / 2.0) % step
        while y0 < H:
            p.drawLine(QPointF(0, y0), QPointF(W, y0))
            y0 += step
    # poligon batas
    for ring, kind in scene.polys:
        if not any(_inside(bb, x, y) for x, y in ring) and not (min(x for x, _ in ring) < cx < max(x for x, _ in ring)):
            continue
        col, w = STYLE.get(kind, STYLE["boundary"])
        pen = QPen(QColor(col), w)
        pen.setStyle(DASH)
        p.setPen(pen)
        c = QColor(col)
        c.setAlpha(14)
        p.setBrush(QBrush(c))
        p.drawPolygon(QPolygonF([pr.px(x, y) for x, y in ring]))
    p.setBrush(QBrush(QColor(0, 0, 0, 0)))
    # garis (jalur/kabel)
    for line, kind in scene.lines:
        if not any(_inside(bb, x, y) for x, y in line):
            # segmen panjang yang melintasi bingkai tanpa titik di dalamnya tetap digambar bila bbox-nya bersinggungan
            lx = [x for x, _ in line]
            ly = [y for _, y in line]
            if max(lx) < bb[0] or min(lx) > bb[2] or max(ly) < bb[1] or min(ly) > bb[3]:
                continue
        col, w = STYLE.get(kind, STYLE["route"])
        pen = QPen(QColor(col), w)
        pen.setCapStyle(ROUND)
        p.setPen(pen)
        path = QPainterPath(pr.px(*line[0]))
        for x, y in line[1:]:
            path.lineTo(pr.px(x, y))
        p.drawPath(path)
    # sorotan temuan (di bawah titik agar titik tetap terbaca)
    col = QColor(SEV_COLOR.get(finding.get("sev"), "#DA1E28"))
    if len(pts) >= 2:
        glow = QColor(col)
        glow.setAlpha(70)
        pen = QPen(glow, 12)
        pen.setCapStyle(ROUND)
        p.setPen(pen)
        path = QPainterPath(pr.px(*pts[0]))
        for x, y in pts[1:]:
            path.lineTo(pr.px(x, y))
        p.drawPath(path)
        pen = QPen(col, 3.2)
        pen.setCapStyle(ROUND)
        p.setPen(pen)
        p.drawPath(path)
    # titik
    font_s = QFont("Inter")
    font_s.setPixelSize(11)
    p.setFont(font_s)
    labels = []
    for x, y, kind, lab in scene.points:
        if not _inside(bb, x, y):
            continue
        c, r = STYLE.get(kind, STYLE["pole"])
        q = pr.px(x, y)
        p.setPen(QPen(QColor("#FFFFFF"), 1.2))
        p.setBrush(QBrush(QColor(c)))
        if kind in ("fat", "fdt", "closure"):
            p.drawRect(QRectF(q.x() - r, q.y() - r, 2 * r, 2 * r))
        else:
            p.drawEllipse(q, r, r)
        if lab and kind != "hp":
            labels.append((q, lab, kind))
    # label tiang/perangkat (maks 40, hindari tabrakan sederhana)
    used = []
    p.setPen(QPen(QColor("#393939")))
    for q, lab, kind in labels[:400]:
        rect = QRectF(q.x() + 6, q.y() - 15, 7.0 * len(lab) + 4, 14)
        if any(rect.intersects(u) for u in used) or len(used) >= 40:
            continue
        used.append(rect)
        p.fillRect(rect, QColor(255, 255, 255, 200))
        p.drawText(rect, int(ALIGN_L | ALIGN_VC), lab)
    # cincin sorotan pada titik temuan
    q = pr.px(finding["lon"], finding["lat"])
    for rad, a in ((26, 40), (17, 255)):
        cc = QColor(col)
        cc.setAlpha(a)
        p.setPen(QPen(cc, 3.0 if a == 255 else 9.0))
        p.setBrush(QBrush(QColor(0, 0, 0, 0)))
        p.drawEllipse(q, rad, rad)
    # kepala: ID, tingkat, judul
    p.setPen(NOPEN)
    p.setBrush(QBrush(QColor(22, 22, 22, 225)))
    p.drawRect(QRectF(0, 0, W, 44))
    p.setBrush(QBrush(col))
    p.drawRect(QRectF(0, 0, 8, 44))
    f1 = QFont("Inter")
    f1.setPixelSize(15)
    f1.setWeight(BOLD)
    p.setFont(f1)
    p.setPen(QPen(QColor("#FFFFFF")))
    head = "%s  ·  %s" % (finding.get("fid", ""), SEV_WORD.get(finding.get("sev"), finding.get("sev", "")))
    p.drawText(QRectF(18, 0, W - 30, 24), int(ALIGN_L | ALIGN_VC), head)
    f2 = QFont("Inter")
    f2.setPixelSize(12)
    p.setFont(f2)
    p.setPen(QPen(QColor("#E0E0E0")))
    t = finding.get("title", "")
    p.drawText(QRectF(18, 22, W - 30, 20), int(ALIGN_L | ALIGN_VC), t if len(t) <= 130 else t[:129] + "…")
    # skala batang + utara + koordinat
    sb_m = _nice(half / 2.5)
    sb_px = sb_m / pr.mpp
    y_sb = H - 22
    p.setPen(QPen(QColor("#161616"), 2))
    p.drawLine(QPointF(16, y_sb), QPointF(16 + sb_px, y_sb))
    p.drawLine(QPointF(16, y_sb - 5), QPointF(16, y_sb + 1))
    p.drawLine(QPointF(16 + sb_px, y_sb - 5), QPointF(16 + sb_px, y_sb + 1))
    p.setFont(font_s)
    p.drawText(QPointF(20 + sb_px, y_sb + 4), "%d m" % sb_m)
    p.drawText(QPointF(16, H - 6), "%.6f, %.6f" % (finding["lat"], finding["lon"]))
    nx, ny = W - 28, H - 44
    p.setBrush(QBrush(QColor("#161616")))
    p.setPen(NOPEN)
    p.drawPolygon(QPolygonF([QPointF(nx, ny - 14), QPointF(nx - 7, ny + 6), QPointF(nx, ny + 2), QPointF(nx + 7, ny + 6)]))
    p.setPen(QPen(QColor("#161616")))
    p.drawText(QPointF(nx - 4, ny + 22), "U")
    p.end()
    return img


def to_jpeg_bytes(img, quality=82):
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(WRITE_ONLY)
    img.save(buf, "JPG", quality)
    buf.close()
    return bytes(ba)


def render_many(scene, findings, out_dir=None, max_n=80, size=(960, 600)):
    """findings: daftar dict (lihat render), sudah diurutkan prioritasnya. Kembali {fid: (jpeg_bytes, path atau None)}.
    Kegagalan satu gambar tidak menghentikan yang lain."""
    out = {}
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    for f in findings[:max_n]:
        try:
            jb = to_jpeg_bytes(render(scene, f, size))
        # gambar opsional: laporan tetap dibuat tanpa gambar ini
        except Exception:  # nosec B112
            continue
        path = None
        if out_dir:
            path = os.path.join(out_dir, "%s.jpg" % f["fid"])
            with open(path, "wb") as fh:
                fh.write(jb)
        out[f["fid"]] = (jb, path)
    return out


def data_uri(jpeg_bytes):
    return "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes).decode("ascii")

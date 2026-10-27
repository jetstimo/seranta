# -*- coding: utf-8 -*-
"""
Seranta - FTTH Design Assistant - tool 3: FDT & FAT allocation estimate
=======================================================================
Copyright (C) 2026 Joseph Edward Timothy Siahaan <edwardtimoo@gmail.com>
GPL-2.0-or-later (see LICENSE).

Before designing in desain otomatis: how many FATs does this cluster need, can they be served by existing FDTs within
1 km (each FDT max 24 FAT, kebijakan internal), and how many new FDTs are needed?

  FAT needed      = ceil(HP / HP per FAT)                       (16 HP = 2 x splitter 1:8, Handbook / ODP-16)
  FAT slots left  = FAT per FDT - FAT existing - FAT reserved    (24 FAT = 384 HP per FDT, kebijakan internal)
  HP grouping     = balanced spatial bisection into groups of <= HP per FAT, FAT placed on the pole nearest
                    to the group's medoid (Handbook: FAT harus di tiang)
  Assignment      = single-source capacitated: every FAT goes to the nearest FDT within the radius that still
                    has a free FAT slot (Kim et al., EJOR 210(2) 2011: capacitated location-allocation)
  Remaining FATs  = new FDT(s), ceil(remaining / FAT per FDT), proposed on a pole near their FAT groups
  Link budget     = fibre 0.35 dB/km + splitter FDT + splitter FAT + 4 connectors x 0.5 dB + 10 splices x 0.1 dB
                    + 3 dB margin <= OLT class (B+ 28 dB / C+ 32 dB, ITU-T G.984.2)
"""
try:
    from . import _log
except ImportError:  # dijalankan sebagai modul lepas (uji unit)
    import _log
import math
import os
import re

from qgis.core import (
    QgsDistanceArea, QgsFeature, QgsGeometry, QgsPointXY, QgsProcessingAlgorithm, QgsProcessingContext,
    QgsProcessingException, QgsProcessingLayerPostProcessorInterface, QgsProcessingParameterBoolean,
    QgsProcessingParameterEnum, QgsProcessingParameterFile, QgsProcessingParameterNumber, QgsSettings,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QCoreApplication

from . import buat_input_desain as B
from . import qc_core as _qc

# Link budget WORST-CASE dari profil standar (profiles/APD_1X4.json): splitter = nilai MAKS GR-1209
# (1:4 7,7 / 1:8 11,2 / 1:16 14,2 dB); nilai tipikal industri (7,25 / 10,38 dB) hanya ditampilkan sebagai pembanding.
_PROF = _qc.get_profile("APD_1X4")[0]
SPLIT_LOSS = {4: _qc.pv(_PROF, "spl4_db", 7.7), 8: _qc.pv(_PROF, "spl8_db", 11.2), 16: _qc.pv(_PROF, "spl16_db", 14.2),
              32: 17.7}
SPLIT_TYP = {4: 7.25, 8: 10.38, 16: 14.10, 32: 17.45}     # tipikal (dikutip jurnal perguruan tinggi)
FIBER_DB_KM = _qc.pv(_PROF, "fiber_db_km", 0.35)          # G.652.D @1310 nm; config desain otomatis 0,35 dB/km
CONN_N, SPLICE_N = 4, 10
CONN_DB, SPLICE_DB, MARGIN_DB = _qc.pv(_PROF, "conn_db", 0.5), _qc.pv(_PROF, "splice_db", 0.1), _qc.pv(_PROF, "margin_db", 3.0)
REAL_HP_PER_FAT = 14.6   # rata-rata 139 FAT pada Design Lite (21-10-2026), median 16 HP; dipakai sebagai pembanding
OLT_CLASS = [("B+ (28 dB)", 28.0), ("C+ (32 dB)", 32.0)]
FDT_SPLIT = [("1:4 ", 4), ("1:8 ", 8)]


def _attr(f, names, key, default=None):
    try:
        i = names.index(key)
    except ValueError:
        return default
    v = f.attributes()[i]
    return default if v is None else v


def bisect_groups(idx, xy, cap):
    """Bagi titik menjadi grup seimbang <= cap secara rekursif sepanjang sumbu terpanjang (meter lokal)."""
    n = len(idx)
    k = int(math.ceil(n / float(cap)))
    if k <= 1:
        return [list(idx)]
    xs = [xy[i][0] for i in idx]
    ys = [xy[i][1] for i in idx]
    axis = 0 if (max(xs) - min(xs)) >= (max(ys) - min(ys)) else 1
    srt = sorted(idx, key=lambda i: xy[i][axis])
    kl = k // 2
    nl = int(round(n * kl / float(k)))
    return bisect_groups(srt[:nl], xy, cap) + bisect_groups(srt[nl:], xy, cap)


def cap_kmeans(xy, groups, cap, iters=10):
    """Perhalus grup hasil bisection dengan k-means berkapasitas: tiap titik ke pusat terdekat yang belum penuh
    (pasangan jarak terpendek lebih dulu), pusat diperbarui ke rata-rata anggota. Grup jadi lebih kompak sehingga
    jarak HP ke FAT lebih pendek. Memakai numpy (bawaan QGIS) bila ada."""
    try:
        import numpy as np
    except ImportError:
        np = None
    import heapq
    cen = [(sum(xy[i][0] for i in g) / len(g), sum(xy[i][1] for i in g) / len(g)) for g in groups]
    k, n = len(cen), len(xy)
    best = groups
    P = np.array(xy, dtype=float) if np is not None else None
    for _ in range(iters):
        kk = min(k, 12)
        if np is not None:
            C = np.array(cen, dtype=float)
            D = ((P[:, None, :] - C[None, :, :]) ** 2).sum(axis=2)
            idx = np.argpartition(D, kk - 1, axis=1)[:, :kk] if kk < k else np.tile(np.arange(k), (n, 1))
            dd = np.take_along_axis(D, idx, axis=1)
            order = np.argsort(dd, axis=None)
            pairs = [(int(o // kk), int(idx.flat[o])) for o in order]
        else:
            pp = []
            for i in range(n):
                x, y = xy[i]
                for d, c in heapq.nsmallest(kk, (((x - cx) ** 2 + (y - cy) ** 2, c) for c, (cx, cy) in enumerate(cen))):
                    pp.append((d, i, c))
            pp.sort()
            pairs = [(i, c) for d, i, c in pp]
        load, asg = [0] * k, [-1] * n
        for i, c in pairs:
            if asg[i] < 0 and load[c] < cap:
                asg[i], load[c] = c, load[c] + 1
        for i in range(n):            # sisa (semua pusat terdekat penuh): pusat mana pun yang masih ada slot
            if asg[i] < 0:
                c = min((c for c in range(k) if load[c] < cap),
                        key=lambda c: (xy[i][0] - cen[c][0]) ** 2 + (xy[i][1] - cen[c][1]) ** 2)
                asg[i], load[c] = c, load[c] + 1
        new = [[] for _ in range(k)]
        for i, c in enumerate(asg):
            new[c].append(i)
        new = [g for g in new if g]
        moved = sorted(map(sorted, best)) != sorted(map(sorted, new))
        best = new
        cen = [(sum(xy[i][0] for i in g) / len(g), sum(xy[i][1] for i in g) / len(g)) for g in best]
        k = len(cen)
        if not moved:
            break
    return best


class RoadGraph(object):
    """Graf jalur kabel dari ROADS.shp (ruas antar simpul). Jarak HP ke FAT diukur seperti desain otomatis (MAXPPDIST,
    path length): HP -> tiang terdekat (drop, garis lurus) + jarak sepanjang jalur kabel tiang -> tiang FAT."""

    def __init__(self, lines, da):
        self.adj = {}
        self.node_xy = {}
        for pts in lines:
            for a, b in zip(pts[:-1], pts[1:]):
                ka, kb = (round(a.x(), 6), round(a.y(), 6)), (round(b.x(), 6), round(b.y(), 6))
                if ka == kb:
                    continue
                L = da.measureLine(a, b)
                self.adj.setdefault(ka, []).append((kb, L))
                self.adj.setdefault(kb, []).append((ka, L))
                self.node_xy[ka], self.node_xy[kb] = a, b
        self.keys = list(self.node_xy)

    def nearest_node(self, p, max_m, da):
        best, bd = None, max_m
        for k in self.keys:
            q = self.node_xy[k]
            if abs(q.x() - p.x()) > 0.001 or abs(q.y() - p.y()) > 0.001:
                continue
            d = da.measureLine(p, q)
            if d <= bd:
                best, bd = k, d
        return best

    def dijkstra(self, src, limit=3000.0):
        import heapq
        dist = {src: 0.0}
        hq = [(0.0, src)]
        while hq:
            d, u = heapq.heappop(hq)
            if d > dist.get(u, 1e18) or d > limit:
                continue
            for v, L in self.adj.get(u, ()):
                nd = d + L
                if nd < dist.get(v, 1e18):
                    dist[v] = nd
                    heapq.heappush(hq, (nd, v))
        return dist


def _medoid(g, xy):
    return min(g, key=lambda i: sum(math.hypot(xy[i][0] - xy[j][0], xy[i][1] - xy[j][1]) for j in g))


def make_fat_groups(xy, cap, max_d, feedback=None):
    """Kelompok HP per FAT. Mulai dari jumlah minimum k0 = ceil(HP/cap) (aturan HP/16). Bila sebaran HP membuat
    sebagian HP lebih jauh dari max_d ke FAT, coba k0+1, k0+2, ... (maks +20%) dan pilih k terkecil yang
    memenuhi; hasil k0 tetap dilaporkan. -> (grup, k0, jumlah HP yang tetap melebihi max_d)."""
    n = len(xy)
    k0 = int(math.ceil(n / float(cap)))
    best = None
    for k in range(k0, k0 + max(2, int(math.ceil(k0 * 0.2))) + 1):
        per = int(math.ceil(n / float(k)))
        groups = cap_kmeans(xy, bisect_groups(list(range(n)), xy, per), cap, iters=12)
        viol = 0
        for g in groups:
            m = _medoid(g, xy)
            viol += sum(1 for i in g if math.hypot(xy[i][0] - xy[m][0], xy[i][1] - xy[m][1]) > max_d)
        if best is None or viol < best[2]:
            best = (groups, k, viol)
        if viol == 0:
            break
    return best[0], k0, best[2]


class FdtStyle(QgsProcessingLayerPostProcessorInterface):
    """Gaya layer alokasi: FAT diwarnai per FDT, FDT kotak besar, garis alokasi tipis."""
    def __init__(self, kind):
        super().__init__()
        self.kind = kind

    def postProcessLayer(self, layer, context, feedback):
        try:
            from qgis.core import (QgsCategorizedSymbolRenderer, QgsLineSymbol, QgsMarkerSymbol, QgsPalLayerSettings,
                                   QgsRendererCategory, QgsTextBufferSettings, QgsTextFormat,
                                   QgsVectorLayerSimpleLabeling)
            # tanpa merah/kuning: warna itu dipakai untuk temuan QC
            pal_cols = ["#1f78b4", "#33a02c", "#6a3d9a", "#b15928", "#17becf", "#7f7f7f", "#a6cee3", "#2ca25f",
                        "#8c6bb1", "#bc80bd", "#1b9e77", "#525252"]
            names = [f.name() for f in layer.fields()]
            key = "fdt" if "fdt" in names else "kode"
            vals = sorted({str(_attr(f, names, key, "")) for f in layer.getFeatures()})
            cats = []
            for i, v in enumerate(vals):
                col = pal_cols[i % len(pal_cols)]
                if self.kind == "line":
                    sym = QgsLineSymbol.createSimple({"color": col, "width": "0.6", "line_style": "dash"})
                elif self.kind == "fdt":
                    sym = QgsMarkerSymbol.createSimple({"name": "square", "color": col, "size": "5",
                                                        "outline_color": "#000000", "outline_width": "0.6"})
                elif self.kind == "hp":
                    sym = QgsMarkerSymbol.createSimple({"name": "circle", "color": col, "size": "1.2",
                                                        "outline_style": "no"})
                else:
                    sym = QgsMarkerSymbol.createSimple({"name": "triangle", "color": col, "size": "4",
                                                        "outline_color": "#000000"})
                cats.append(QgsRendererCategory(v, sym, v))
            layer.setRenderer(QgsCategorizedSymbolRenderer(key, cats))
            if self.kind in ("fat", "fdt"):
                pal = QgsPalLayerSettings()
                pal.isExpression = True
                pal.fieldName = ('"fat_id" || \' (\' || "hp" || \' HP)\'' if self.kind == "fat"
                                 else '"kode" || \'\\n\' || "fat_total" || \'/\' || "kapasitas" || \' FAT\'')
                fmt = QgsTextFormat()
                fmt.setSize(8)
                buf = QgsTextBufferSettings()
                buf.setEnabled(True)
                fmt.setBuffer(buf)
                pal.setFormat(fmt)
                layer.setLabeling(QgsVectorLayerSimpleLabeling(pal))
                layer.setLabelsEnabled(True)
            if self.kind in ("fat", "fdt"):
                layer.setCustomProperty("seranta_qc", "1")      # tampil di Navigator QC
            layer.triggerRepaint()
        except Exception as e:
            if feedback:
                feedback.reportError("Gaya layer alokasi tidak diterapkan: %s" % e, fatalError=False)


class AlokasiFdtFat(QgsProcessingAlgorithm):
    CLUSTER = "CLUSTER"
    REF = "REF"
    HP_PER_FAT = "HP_PER_FAT"
    FAT_PER_FDT = "FAT_PER_FDT"
    RADIUS = "RADIUS"
    FAT_DIST = "FAT_DIST"
    OLT = "OLT"
    FDT_SPL = "FDT_SPL"
    FEEDER_KM = "FEEDER_KM"
    ROUTE_FACTOR = "ROUTE_FACTOR"
    MIN_COLO = "MIN_COLO"
    OPEN_REPORT = "OPEN_REPORT"
    MODE = "MODE"
    MODE_OPTS = ["FDT terdekat diisi penuh dulu (sesedikit mungkin FDT, disarankan)",
                 "Tiap FAT ke FDT terdekatnya (kabel distribusi terpendek, bisa banyak FDT)"]

    def tr(self, s):
        return QCoreApplication.translate("Seranta", s)

    def createInstance(self):
        return AlokasiFdtFat()

    def name(self):
        return "alokasi_fdt_fat"

    def displayName(self):
        return self.tr("3. Alokasi FDT & FAT (estimasi kebutuhan)")

    def group(self):
        return "Seranta"

    def groupId(self):
        return "seranta"

    def icon(self):
        from qgis.PyQt.QtGui import QIcon
        return QIcon(os.path.join(os.path.dirname(__file__), "icon.png"))

    def shortHelpString(self):
        return self.tr(
            "<p><b>Estimasi kebutuhan FAT dan alokasi ke FDT</b> sebelum desain di desain otomatis.</p><ol>"
            "<li><b>Jumlah FAT</b> = jumlah HP / 16 (dibulatkan ke atas). 16 HP = 2 splitter 1:8 per FAT.</li>"
            "<li>HP dikelompokkan per FAT (maks 16, berdekatan); FAT ditaruh di <b>tiang</b> terdekat dari pusat "
            "kelompok.</li>"
            "<li>Setiap FDT maks <b>24 FAT</b> (= 384 HP, kebijakan internal). Sisa slot FDT existing = 24 - FAT "
            "existing di Design Lite - FAT yang sudah dipesan di COLO_RENCANA.csv.</li>"
            "<li>FAT dialokasikan ke FDT existing <b>terdekat dalam radius 1 km</b> yang masih punya slot; "
            "sisanya menjadi usulan <b>FDT baru</b>.</li>"
            "<li>Link budget tiap FAT dicek terhadap kelas optik OLT (B+ 28 dB / C+ 32 dB).</li></ol>"
            "<p>Masukan: folder cluster yang sudah diproses <b>alat 1</b> (folder INPUT berisi HP.shp dan "
            "POLE_PETA.gpkg), dan folder referensi (Design Lite). Hasil di subfolder <code>ALOKASI_FDT</code>: "
            "FAT_ESTIMASI, HP_PER_FAT, GARIS_FAT_FDT, FDT_ALOKASI (shp) dan ringkasan HTML.</p>"
            "<p>Hasil ini <b>estimasi awal</b> untuk keputusan colo/FDT baru; desain final tetap di desain otomatis.</p>")

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFile(
            self.CLUSTER, self.tr("1. Folder cluster (sudah diproses alat 1) atau folder induk untuk banyak cluster"),
            behavior=B.FOLDER_BEHAVIOR))
        try:
            st_ = QgsSettings()
            last_ref = st_.value("seranta/ref_dir", "") or ""
            last_ref = last_ref if last_ref and os.path.isdir(last_ref) else None
        except Exception:
            last_ref = None
        self.addParameter(QgsProcessingParameterFile(
            self.REF, self.tr("2. Folder data referensi tim (DESIGN LITE; diingat; kosong = cari otomatis)"),
            behavior=B.FOLDER_BEHAVIOR, optional=True, defaultValue=last_ref))
        self.addParameter(QgsProcessingParameterNumber(
            self.HP_PER_FAT, self.tr("HP per FAT (16 = 2 x splitter 1:8)"), type=B.NUM_DOUBLE, defaultValue=16, minValue=1))
        self.addParameter(QgsProcessingParameterNumber(
            self.FAT_PER_FDT, self.tr("FAT maksimum per FDT (default 24)"), type=B.NUM_DOUBLE, defaultValue=24, minValue=1))
        self.addParameter(QgsProcessingParameterNumber(
            self.RADIUS, self.tr("Radius FDT existing dari tiang cluster terdekat (meter)"), type=B.NUM_DOUBLE,
            defaultValue=1000, minValue=50))
        self.addParameter(QgsProcessingParameterEnum(
            self.MODE, self.tr("Cara alokasi"), options=self.MODE_OPTS, defaultValue=0))
        self.addParameter(QgsProcessingParameterBoolean(
            self.OPEN_REPORT, self.tr("Buka ringkasan alokasi setelah selesai"), defaultValue=True))
        adv = [
            QgsProcessingParameterNumber(self.FAT_DIST, self.tr("Jarak maks HP ke FAT (meter; umum 120-150)"), type=B.NUM_DOUBLE,
                                         defaultValue=120, minValue=10),
            QgsProcessingParameterEnum(self.OLT, self.tr("Kelas optik OLT (link budget, ITU-T G.984.2)"),
                                       options=[a for a, b in OLT_CLASS], defaultValue=0),
            QgsProcessingParameterEnum(self.FDT_SPL, self.tr("Splitter di FDT"), options=[a for a, b in FDT_SPLIT],
                                       defaultValue=0),
            QgsProcessingParameterNumber(self.FEEDER_KM, self.tr("Perkiraan panjang feeder OLT ke FDT (km)"),
                                         type=B.NUM_DOUBLE, defaultValue=5.0, minValue=0),
            QgsProcessingParameterNumber(self.MIN_COLO, self.tr("Minimum FAT yang dititipkan ke satu FDT existing (cegah cluster terpecah ke banyak FDT)"),
                                         type=B.NUM_INT, defaultValue=4, minValue=1, maxValue=24),
            QgsProcessingParameterNumber(self.ROUTE_FACTOR, self.tr("Faktor jalur kabel terhadap garis lurus FDT-FAT"),
                                         type=B.NUM_DOUBLE, defaultValue=1.3, minValue=1.0),
        ]
        for p in adv:
            try:
                p.setFlags(p.flags() | B.Qgis.ProcessingParameterFlag.Advanced)
            except Exception:
                try:
                    p.setFlags(p.flags() | B.ADVANCED_FLAG)
                except Exception as _e:
                    _log.note(_e)
            self.addParameter(p)

    # ---------- main ----------
    def prepareAlgorithm(self, parameters, context, feedback):
        """Lepas layer ALOKASI_FDT run sebelumnya dari proyek (thread utama) agar shapefile tidak terkunci Windows
        saat ditimpa - file yang setengah tertimpa membuat extent layer salah dan 'Zoom to Layer' tidak menampilkan
        apa-apa."""
        root = self.parameterAsFile(parameters, self.CLUSTER, context)
        if root and os.path.isdir(root):
            n = B.release_old_outputs(root, markers=("ALOKASI_FDT",))
            if n:
                feedback.pushInfo("%d layer alokasi run sebelumnya dilepas dari proyek agar file bisa ditimpa." % n)
        return True

    def processAlgorithm(self, parameters, context, feedback):
        root = self.parameterAsFile(parameters, self.CLUSTER, context)
        if not root or not os.path.isdir(root):
            raise QgsProcessingException("Pilih folder cluster yang sudah ada.")
        ref = self.parameterAsFile(parameters, self.REF, context)
        st = QgsSettings()
        if ref and os.path.isdir(ref):
            st.setValue("seranta/ref_dir", ref)
        else:
            ref = st.value("seranta/ref_dir", "") or ""
            if not (ref and os.path.isdir(ref)):
                ref = B.find_ref_dir(root)
        opt = {
            "hp_fat": int(self.parameterAsDouble(parameters, self.HP_PER_FAT, context)),
            "fat_fdt": int(self.parameterAsDouble(parameters, self.FAT_PER_FDT, context)),
            "radius": self.parameterAsDouble(parameters, self.RADIUS, context),
            "fat_dist": self.parameterAsDouble(parameters, self.FAT_DIST, context) if self.FAT_DIST in parameters else 120.0,
            "olt": OLT_CLASS[self.parameterAsEnum(parameters, self.OLT, context) if self.OLT in parameters else 0],
            "fdt_spl": FDT_SPLIT[self.parameterAsEnum(parameters, self.FDT_SPL, context) if self.FDT_SPL in parameters else 0][1],
            "feeder_km": self.parameterAsDouble(parameters, self.FEEDER_KM, context) if self.FEEDER_KM in parameters else 5.0,
            "route_f": self.parameterAsDouble(parameters, self.ROUTE_FACTOR, context) if self.ROUTE_FACTOR in parameters else 1.3,
            "open": self.parameterAsBool(parameters, self.OPEN_REPORT, context) if self.OPEN_REPORT in parameters else True,
            "mode": self.parameterAsEnum(parameters, self.MODE, context) if self.MODE in parameters else 0,
            "min_colo": self.parameterAsInt(parameters, self.MIN_COLO, context) if self.MIN_COLO in parameters else 4,
        }
        dl_files = [p for p, t, n in B.latest_per_kind(B.ref_files(ref, "designlite"))] if ref else []
        if not dl_files:
            feedback.reportError("Design Lite tidak ditemukan di folder referensi: semua FAT akan diusulkan ke FDT baru.",
                                 fatalError=False)
        res_rows = B.read_reservations(os.path.join(ref, "COLO_RENCANA.csv")) if ref else []
        inputs = self._find_inputs(root)
        if not inputs:
            raise QgsProcessingException(
                "Tidak ada folder INPUT hasil alat 1 (berisi HP.shp dan POLE_PETA.gpkg) di %s. "
                "Jalankan '1. Siapkan Input Desain Otomatis + QC Strand' dulu untuk cluster ini." % root)
        self._loads = []
        last = None
        for i, inp in enumerate(inputs):
            if feedback.isCanceled():
                break
            feedback.pushInfo("=== Alokasi %d/%d: %s ===" % (i + 1, len(inputs), inp))
            try:
                last = self._run_one(inp, opt, dl_files, res_rows, context, feedback)
            except QgsProcessingException as e:
                feedback.reportError("%s: %s" % (inp, e), fatalError=False)
        for k, (pth, nm, grp, kind) in enumerate(self._loads):
            try:
                det = QgsProcessingContext.LayerDetails("%s %s" % (grp, nm), context.project(), nm)
                try:
                    det.groupName = grp + " ALOKASI FDT"
                    det.layerSortKey = k
                except Exception as _e:
                    _log.note(_e)
                pp = FdtStyle(kind)
                B._KEEP_ALIVE.append(pp)
                det.setPostProcessor(pp)
                context.addLayerToLoadOnCompletion(pth, det)
            except Exception as e:
                feedback.reportError("Layer %s tidak dimuat: %s" % (nm, e), fatalError=False)
        self._open = last if (opt["open"] and last and len(inputs) == 1) else None
        return {self.CLUSTER: root}

    def postProcessAlgorithm(self, context, feedback):
        pth = getattr(self, "_open", None)
        if pth and os.path.exists(pth):
            try:
                from qgis.PyQt.QtCore import QUrl
                from qgis.PyQt.QtGui import QDesktopServices
                QDesktopServices.openUrl(QUrl.fromLocalFile(pth))
            except Exception as _e:
                _log.note(_e)
        return {}

    @staticmethod
    def _find_inputs(root):
        """Folder INPUT* (hasil alat 1) di folder ini, di dalam folder cluster, atau satu tingkat di bawah induk."""
        def ok(d):
            return any(f.upper().endswith("HP.SHP") for f in os.listdir(d)) and \
                any(f.upper().endswith("POLE_PETA.GPKG") for f in os.listdir(d))
        if os.path.basename(root.rstrip("\\/")).upper().startswith("INPUT") and ok(root):
            return [root]
        out = []
        for d in sorted(os.listdir(root)):
            p = os.path.join(root, d)
            if os.path.isdir(p) and d.upper().startswith("INPUT") and ok(p):
                out.append(p)
        if out:
            return out[-1:]          # satu cluster: pakai folder INPUT terbaru (urut nama)
        for d in sorted(os.listdir(root)):
            p = os.path.join(root, d)
            if os.path.isdir(p):
                sub = [os.path.join(p, x) for x in sorted(os.listdir(p))
                       if x.upper().startswith("INPUT") and os.path.isdir(os.path.join(p, x)) and ok(os.path.join(p, x))]
                if sub:
                    out.append(sub[-1])
        return out

    @staticmethod
    def _merge_small(placed, fat_min, cap, fd, poles, hp_pole, best_pole):
        """Gabungkan FAT yang HP-nya < fat_min ke FAT tetangga bila total <= cap dan HP terjauh tetap <= fd."""
        changed = True
        while changed:
            changed = False
            placed.sort(key=lambda t: len(t[0]))
            for a_i, (ga, pa, da_) in enumerate(placed):
                if len(ga) >= fat_min:
                    break
                best = None
                for b_i, (gb, pb, db_) in enumerate(placed):
                    if b_i == a_i or len(ga) + len(gb) > cap:
                        continue
                    if math.hypot((poles[pa][0].x() - poles[pb][0].x()) * 111320 * math.cos(math.radians(poles[pa][0].y())),
                                  (poles[pa][0].y() - poles[pb][0].y()) * 110574) > 2 * fd:
                        continue
                    u = ga + gb
                    pj_, dm_ = best_pole(u, list({hp_pole[i][0] for i in u} | {pa, pb}), allow=(pa, pb))
                    if dm_ <= fd and (best is None or dm_ < best[2]):
                        best = (b_i, pj_, dm_)
                if best:
                    b_i, pj_, dm_ = best
                    merged = (ga + placed[b_i][0], pj_, dm_)
                    used = getattr(best_pole, "used", None)
                    if used is not None:
                        used.discard(pa)
                        used.discard(placed[b_i][1])
                        used.add(pj_)
                    placed = [t for k_, t in enumerate(placed) if k_ not in (a_i, b_i)] + [merged]
                    changed = True
                    break
        return placed

    def _read_points(self, path, fields):
        lyr = QgsVectorLayer(path, "x", "ogr")
        if not lyr.isValid():
            raise QgsProcessingException("Tidak bisa membaca %s" % path)
        names = [f.name() for f in lyr.fields()]
        out = []
        for f in lyr.getFeatures():
            g = f.geometry()
            if g is None or g.isEmpty():
                continue
            p = g.asPoint()
            out.append((QgsPointXY(p.x(), p.y()), {k: _attr(f, names, k) for k in fields}))
        return out

    def _run_one(self, inp, opt, dl_files, res_rows, context, feedback):
        fs = os.listdir(inp)
        hp_path = os.path.join(inp, next(f for f in fs if f.upper().endswith("HP.SHP")))
        pole_path = os.path.join(inp, next(f for f in fs if f.upper().endswith("POLE_PETA.GPKG")))
        pre = os.path.basename(hp_path)[:-len("HP.shp")]
        kode = pre.rstrip("_") or os.path.basename(os.path.dirname(inp.rstrip("\\/")))
        da = QgsDistanceArea()
        da.setSourceCrs(B.WGS84, context.transformContext())
        da.setEllipsoid("WGS84")
        hps = self._read_points(hp_path, ["HOMEPASS_1", "HOMEPASS_I"])
        poles = self._read_points(pole_path, ["Name", "jenis"])
        if not hps or not poles:
            raise QgsProcessingException("HP atau tiang kosong di %s" % inp)
        n_hp = len(hps)
        cap, fat_fdt = opt["hp_fat"], opt["fat_fdt"]
        n_fat = int(math.ceil(n_hp / float(cap)))
        feedback.pushInfo("HP %d -> FAT dibutuhkan ceil(%d / %d) = %d; kapasitas 1 FDT = %d FAT = %d HP"
                          % (n_hp, n_hp, cap, n_fat, fat_fdt, fat_fdt * cap))
        lat0 = sum(p.y() for p, a in hps) / n_hp
        kx, ky = math.cos(math.radians(lat0)) * 111320.0, 110574.0
        xy = [(p.x() * kx, p.y() * ky) for p, a in hps]
        groups, k0, n_viol = make_fat_groups(xy, cap, opt["fat_dist"] / opt["route_f"])
        if len(groups) > k0:
            feedback.pushInfo("Sebaran HP: %d FAT minimum (HP/%d) membuat sebagian HP > %.0f m dari FAT; "
                              "usulan realistis %d FAT" % (k0, cap, opt["fat_dist"], len(groups)))
        pxy = [(p.x() * kx, p.y() * ky) for p, a in poles]

        def nearest_pole(x, y):
            return min(range(len(poles)), key=lambda j: (pxy[j][0] - x) ** 2 + (pxy[j][1] - y) ** 2)
        # graf jalur kabel (ROADS.shp hasil alat 1) untuk jarak HP -> FAT sepanjang jalur
        graph, pole_node, hp_pole = None, {}, {}
        try:
            rp = [os.path.join(inp, f) for f in fs if f.upper().endswith("ROADS.SHP")]
            if rp:
                rl = QgsVectorLayer(rp[0], "r", "ogr")
                lines = []
                for f in rl.getFeatures():
                    g = f.geometry()
                    if g is None or g.isEmpty():
                        continue
                    for part in (g.asMultiPolyline() if g.isMultipart() else [g.asPolyline()]):
                        lines.append([QgsPointXY(q.x(), q.y()) for q in part])
                graph = RoadGraph(lines, da) if lines else None
        except Exception as e:
            feedback.reportError("Jalur ROADS tidak terbaca, jarak HP-FAT memakai garis lurus x %.1f: %s"
                                 % (opt["route_f"], e), fatalError=False)
            graph = None
        for i, (p, a) in enumerate(hps):
            j = nearest_pole(p.x() * kx, p.y() * ky)
            hp_pole[i] = (j, da.measureLine(p, poles[j][0]))
        dist_cache = {}

        def path_from(pj):
            if pj not in dist_cache:
                if graph is None:
                    dist_cache[pj] = None
                else:
                    if pj not in pole_node:
                        pole_node[pj] = graph.nearest_node(poles[pj][0], 1.0, da)
                    nd = pole_node[pj]
                    dist_cache[pj] = graph.dijkstra(nd, opt["fat_dist"] * 3) if nd else None
            return dist_cache[pj]

        def hp_dist(i, pj):
            """Jarak HP i ke FAT di tiang pj: drop ke tiang terdekat + sepanjang jalur (atau garis lurus x faktor)."""
            j, drop = hp_pole[i]
            if j == pj:
                return drop
            dm = path_from(pj)
            if dm is not None:
                if j not in pole_node:
                    pole_node[j] = graph.nearest_node(poles[j][0], 1.0, da)
                nj = pole_node[j]
                if nj in dm:
                    return drop + dm[nj]
            return da.measureLine(hps[i][0], poles[pj][0]) * opt["route_f"]
        used_poles = set()               # satu FAT per tiang (Handbook kasus 30: FAT tidak bertumpuk di titik sama)

        def best_pole(g, cands, allow=()):
            free = [j for j in cands if j not in used_poles or j in allow] or list(cands)
            return min(((j, max(hp_dist(i, j) for i in g)) for j in free), key=lambda t: t[1])
        best_pole.used = used_poles
        placed = []                      # (grup HP, tiang FAT, jarak HP terjauh)
        if graph is not None:
            # Pengelompokan SEPANJANG JALUR (cara kerja desain otomatis): mulai dari tiang paling ujung jaringan, ambil HP
            # terdekat menurut jarak jalur sampai 16 HP, letakkan FAT di tiang anggota yang jarak HP terjauhnya
            # terkecil; bila masih > batas, HP terjauh dikeluarkan untuk FAT berikutnya.
            for j in range(len(poles)):
                if j not in pole_node:
                    pole_node[j] = graph.nearest_node(poles[j][0], 1.0, da)
            cx_ = sum(x for x, y in xy) / n_hp
            cy_ = sum(y for x, y in xy) / n_hp
            c_node = pole_node.get(nearest_pole(cx_, cy_))
            dc = graph.dijkstra(c_node, 1e9) if c_node else {}
            U = set(range(n_hp))
            fd = opt["fat_dist"]
            while U:
                seed = max({hp_pole[i][0] for i in U}, key=lambda j: (dc.get(pole_node.get(j), 1e9), j))
                cost = sorted((hp_dist(i, seed), i) for i in U)
                g = [i for c, i in cost if c <= 2 * fd][:cap] or [cost[0][1]]
                cands = list({hp_pole[i][0] for i in g} | {seed})
                pj, dmax = best_pole(g, cands)
                while dmax > fd and len(g) > 1:
                    far_i = max(g, key=lambda i: hp_dist(i, pj))
                    g.remove(far_i)
                    pj, dmax = best_pole(g, list({hp_pole[i][0] for i in g}))
                U -= set(g)
                used_poles.add(pj)
                placed.append((g, pj, dmax))
            # gabungkan FAT kecil (< 8 HP, Handbook FAT 8-16 HP) ke FAT tetangga bila kapasitas & jarak masih memenuhi
            # (dua putaran: FAT < 8 HP lalu FAT < 12 HP, agar jumlah FAT mendekati desain nyata ~14-15 HP/FAT)
            for fat_min in (8, 12):
                placed = self._merge_small(placed, fat_min, cap, fd, poles, hp_pole, best_pole)
            if len(placed) > k0:
                feedback.pushInfo("Sebaran HP sepanjang jalur: %d FAT minimum (HP/%d); agar setiap HP <= %.0f m "
                                  "(drop + jalur) dibutuhkan %d FAT" % (k0, cap, fd, len(placed)))
        else:
            for g in groups:
                med = _medoid(g, xy)
                mx, my = xy[med]
                cands = sorted(range(len(poles)), key=lambda j: (pxy[j][0] - mx) ** 2 + (pxy[j][1] - my) ** 2)[:6]
                pj, dmax = best_pole(g, cands)
                used_poles.add(pj)
                placed.append((g, pj, dmax))
        fats = []
        for gi, (g, pj, dmax) in enumerate(sorted(placed, key=lambda t: (-poles[t[1]][0].y(), poles[t[1]][0].x())), 1):
            pp = poles[pj][0]
            fats.append({"id": "F%02d" % gi, "hp_idx": g, "hp": len(g), "pole": poles[pj][1].get("Name") or "tiang",
                         "pt": pp, "pj": pj, "dmax": dmax, "fdt": None, "d_fdt": None})
        n_far = sum(1 for f in fats if f["dmax"] > opt["fat_dist"])

        # ----- FDT existing di sekitar (Design Lite) -----
        xs = [p.x() for p, a in poles]
        ys = [p.y() for p, a in poles]
        mdeg = opt["radius"] / B.M_PER_DEG * 1.3 + 0.002
        ext_fdt = (min(xs) - mdeg, min(ys) - mdeg, max(xs) + mdeg, max(ys) + mdeg)
        ext_fat = (min(xs) - 0.06, min(ys) - 0.06, max(xs) + 0.06, max(ys) + 0.06)   # FAT milik FDT bisa jauh
        ent = []
        fat_codes = {}
        for fp in dl_files:
            for e in B.cached_read("designlite", fp, ext_fat, B.read_design_lite, feedback):
                k = e.get("kind", "fdt")
                if k == "fdt" and ext_fdt[0] <= e["x"] <= ext_fdt[2] and ext_fdt[1] <= e["y"] <= ext_fdt[3]:
                    ent.append(e)
                elif k == "fat":
                    fat_codes.setdefault(e["fdt"], set()).add(e["code"])

        def dxy(x1, y1, x2, y2):
            return da.measureLine(QgsPointXY(x1, y1), QgsPointXY(x2, y2))
        fdts = B.group_fdt(ent, dxy) if ent else []
        cl_name = os.path.basename(os.path.dirname(inp.rstrip("\\/")))
        cl_id = (re.search(r"(?<!\d)(\d{9,12})(?!\d)", cl_name) or re.search(r"(?<!\d)(\d{9,12})(?!\d)", kode) or [None, ""])[1]
        if not cl_id:                        # ID cluster dari manifest alat 1 (folder uji sering tidak memuat ID)
            try:
                import glob as _g, json as _j
                for mp in _g.glob(os.path.join(inp, "*manifest_input.json")):
                    with open(mp, encoding="utf-8") as fh:
                        cl_id = str(_j.load(fh).get("cluster_id") or "")
                    break
            except (OSError, ValueError) as _e:
                _log.note(_e)
        reserved = {}
        for r in res_rows:
            if r[1].strip().upper() in (cl_name.upper(), kode.upper()) or (cl_id and cl_id in (r[5] or "")):
                continue                     # pesanan cluster ini sendiri (dari alat 1) tidak dihitung dua kali
            try:
                reserved[r[2]] = reserved.get(r[2], 0) + int(math.ceil(float(r[4] or 0) / cap))
            except ValueError as _e:
                _log.note(_e)
        cand = []
        for g in fdts:
            pt = QgsPointXY(g["x"], g["y"])
            d_entry = min(da.measureLine(pt, p) for p, a in poles)
            n_rec = len(fat_codes.get(g["code"], ()))
            # desain cluster ini sendiri yang sudah tercatat di Design Lite tidak dihitung dua kali
            ownd = [e for e in g.get("designs", []) if cl_id and cl_id in (e.get("design") or "")]
            own_fat = int(math.ceil(sum(e.get("prem") or 0 for e in ownd) / float(cap)))
            if ownd:
                g["used"] = max(0, (g.get("used") or 0) - sum(e.get("spl") or 0 for e in ownd))
            g["own"] = bool(ownd)
            n_est = int(math.ceil(max(0, (g.get("prem") or 0) - sum(e.get("prem") or 0 for e in ownd)) / float(cap)))
            ex = max(n_rec - own_fat, n_est)
            rs = reserved.get(g["code"], 0)
            # dua batas: slot FAT (24) dan output splitter FDT (maks splitter x rasio / 2 output per FAT 16 HP)
            ratio = opt["fdt_spl"]
            max_spl = int(math.ceil(fat_fdt * 2.0 / ratio))
            free_spl = max(0, max_spl - (g.get("used") or 0)) * ratio // 2
            free = max(0, min(fat_fdt - ex, free_spl) - rs)
            drop = any(e.get("drop") for e in g.get("designs", []))
            g.update(pt=pt, d_entry=d_entry, fat_ex=ex, fat_rec=n_rec, fat_res=rs, free=free, assigned=[])
            if d_entry > opt["radius"]:
                g["status"] = "DI LUAR %d M" % opt["radius"]
            elif drop:
                g["status"] = "DROP/REJECT"
            elif free <= 0:
                g["status"] = "PENUH (%d/%d FAT)" % (ex + rs, fat_fdt)
            else:
                g["status"] = "TERSEDIA %d FAT" % free
                cand.append(g)
            if g.get("own"):
                g["status"] += " (desain cluster ini di Design Lite tidak dihitung)"
        # ----- penugasan berkapasitas: pasangan (jarak FDT-FAT) terdekat lebih dulu -----
        def take(fi, gi, d):
            f = fats[fi]
            f["fdt"], f["d_fdt"], f["fdt_new"], f["fdt_pt"] = cand[gi]["code"], d, False, cand[gi]["pt"]
            cand[gi]["assigned"].append(f["id"])
        if opt.get("mode", 0) == 0:
            # FDT terdekat ke cluster diisi penuh lebih dulu dengan FAT yang paling dekat ke FDT itu
            # -> cluster memakai sesedikit mungkin FDT (praktik desain: 1 cluster = 1-3 FDT)
            # FDT yang hanya bisa menampung sedikit FAT dilewati (kecuali cukup untuk semua sisa FAT): satu rute
            # kabel distribusi 24D (+-12 FAT) dari FDT jauh untuk 1-3 FAT tidak efisien; Handbook: penuhi satu FDT dulu
            for gi in sorted(range(len(cand)), key=lambda i: cand[i]["d_entry"]):
                free_fats = sorted((da.measureLine(cand[gi]["pt"], f["pt"]), fi) for fi, f in enumerate(fats)
                                   if f["fdt"] is None)
                n_take = min(cand[gi]["free"], len(free_fats))
                if n_take <= 0:
                    continue
                if n_take < opt.get("min_colo", 4) and n_take < len(free_fats):
                    cand[gi]["status"] += " - dilewati: hanya %d slot (< %d FAT minimum per FDT)" % (n_take, opt.get("min_colo", 4))
                    continue
                for d, fi in free_fats[:n_take]:
                    take(fi, gi, d)
        else:
            # tiap FAT ke FDT terdekatnya yang masih punya slot (kabel distribusi terpendek)
            pairs = sorted(((da.measureLine(g["pt"], f["pt"]), fi, gi) for fi, f in enumerate(fats)
                            for gi, g in enumerate(cand)), key=lambda t: t[0])
            left = {gi: g["free"] for gi, g in enumerate(cand)}
            for d, fi, gi in pairs:
                if fats[fi]["fdt"] is None and left[gi] > 0:
                    take(fi, gi, d)
                    left[gi] -= 1
        for g in cand:
            if g["assigned"]:
                g["status"] = "DIPAKAI CLUSTER INI %d FAT, sisa %d" % (len(g["assigned"]), g["free"] - len(g["assigned"]))
        # ----- sisa -> FDT baru -----
        rest = [f for f in fats if f["fdt"] is None]
        new_fdts = []
        if rest:
            fxy = {i: (f["pt"].x() * kx, f["pt"].y() * ky) for i, f in enumerate(rest)}
            for ni, grp_ in enumerate(bisect_groups(list(fxy), fxy, fat_fdt), 1):
                cx = sum(fxy[i][0] for i in grp_) / len(grp_)
                cy = sum(fxy[i][1] for i in grp_) / len(grp_)
                pj = nearest_pole(cx, cy)
                code = "FDT-BARU-%d" % ni
                nd = {"code": code, "pt": poles[pj][0], "pole": poles[pj][1].get("Name") or "tiang",
                      "assigned": [], "fat_ex": 0, "fat_res": 0, "free": fat_fdt, "status": "USULAN FDT BARU",
                      "d_entry": 0.0}
                for i in grp_:
                    f = rest[i]
                    f["fdt"], f["fdt_new"], f["fdt_pt"] = code, True, nd["pt"]
                    f["d_fdt"] = da.measureLine(nd["pt"], f["pt"])
                    nd["assigned"].append(f["id"])
                new_fdts.append(nd)
        # ----- link budget per FAT -----
        olt_name, olt_db = opt["olt"]
        for f in fats:
            km = opt["feeder_km"] + (f["d_fdt"] or 0) * opt["route_f"] / 1000.0
            loss = (km * FIBER_DB_KM + SPLIT_LOSS[opt["fdt_spl"]] + SPLIT_LOSS[8] + CONN_N * CONN_DB
                    + SPLICE_N * SPLICE_DB + MARGIN_DB)
            f["loss"], f["sisa"] = loss, olt_db - loss
        n_bad_budget = sum(1 for f in fats if f["sisa"] < 0)
        # ----- tulis hasil -----
        out_dir = os.path.join(inp, "ALOKASI_FDT")
        os.makedirs(out_dir, exist_ok=True)
        locked = []
        for fn in os.listdir(out_dir):
            try:
                os.remove(os.path.join(out_dir, fn))
            except OSError:
                locked.append(fn)
        if locked:
            # file dikunci aplikasi lain (mis. jendela QGIS kedua): menulis di atasnya membuat layer setengah tertimpa
            # dan 'Zoom to Layer' salah -> tulis ke folder baru
            import datetime as _dt
            out_dir = out_dir + "_" + _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            os.makedirs(out_dir, exist_ok=True)
            feedback.reportError("%d file ALOKASI_FDT lama masih terkunci aplikasi lain; hasil ditulis ke %s"
                                 % (len(locked), out_dir), fatalError=False)
        grp = kode

        def write(lyr, name, kind):
            path = os.path.join(out_dir, name + ".shp")
            B.BuatInputDesain._write(lyr, path, "ESRI Shapefile", context)
            self._loads.append((path, name, grp, kind))
            return path
        L = QgsVectorLayer("Point?crs=EPSG:4326&field=fat_id:string(10)&field=hp:integer&field=fdt:string(30)"
                           "&field=fdt_jenis:string(10)&field=jarak_fdt:double(10,1)&field=hp_maks_m:double(10,1)"
                           "&field=tiang:string(40)&field=loss_db:double(6,2)&field=sisa_db:double(6,2)"
                           "&field=status:string(80)", "FAT_ESTIMASI", "memory")
        ff = []
        for f in fats:
            st_ = []
            if f["dmax"] > opt["fat_dist"]:
                st_.append("HP terjauh %.0f m > %.0f m" % (f["dmax"], opt["fat_dist"]))
            if f["sisa"] < 0:
                st_.append("link budget kurang %.1f dB" % -f["sisa"])
            if f["hp"] < 8:
                st_.append("FAT kecil %d HP (< 8, Handbook 8-16): HP terpencil, cek tambah tiang/gabung" % f["hp"])
            q = QgsFeature(L.fields())
            q.setAttributes([f["id"], f["hp"], f["fdt"], "BARU" if f["fdt_new"] else "EXISTING", round(f["d_fdt"], 1),
                             round(f["dmax"], 1), f["pole"], round(f["loss"], 2), round(f["sisa"], 2),
                             "; ".join(st_) or "OK"])
            q.setGeometry(QgsGeometry.fromPointXY(f["pt"]))
            ff.append(q)
        L.dataProvider().addFeatures(ff)
        H = QgsVectorLayer("Point?crs=EPSG:4326&field=hp_id:string(20)&field=fat_id:string(10)&field=fdt:string(30)"
                           "&field=jarak_fat:double(10,1)", "HP_PER_FAT", "memory")
        hf = []
        for f in fats:
            for i in f["hp_idx"]:
                p, a = hps[i]
                q = QgsFeature(H.fields())
                q.setAttributes([str(a.get("HOMEPASS_1") or a.get("HOMEPASS_I") or "HP%d" % (i + 1)), f["id"], f["fdt"],
                                 round(hp_dist(i, f["pj"]), 1)])
                q.setGeometry(QgsGeometry.fromPointXY(p))
                hf.append(q)
        H.dataProvider().addFeatures(hf)
        G = QgsVectorLayer("LineString?crs=EPSG:4326&field=fat_id:string(10)&field=fdt:string(30)"
                           "&field=jarak_m:double(10,1)", "GARIS_FAT_FDT", "memory")
        gf = []
        for f in fats:
            q = QgsFeature(G.fields())
            q.setAttributes([f["id"], f["fdt"], round(f["d_fdt"], 1)])
            q.setGeometry(QgsGeometry.fromPolylineXY([f["fdt_pt"], f["pt"]]))
            gf.append(q)
        G.dataProvider().addFeatures(gf)
        D = QgsVectorLayer("Point?crs=EPSG:4326&field=kode:string(30)&field=jenis:string(10)&field=fat_exist:integer"
                           "&field=fat_pesan:integer&field=fat_baru:integer&field=fat_total:integer"
                           "&field=kapasitas:integer&field=sisa:integer&field=jarak_m:double(10,1)"
                           "&field=status:string(60)", "FDT_ALOKASI", "memory")
        df = []
        all_fdt = sorted(fdts, key=lambda g: g["d_entry"]) + new_fdts
        for g in all_fdt:
            if not g["assigned"] and g["d_entry"] > opt["radius"] * 1.5:
                continue
            nb = len(g["assigned"])
            tot = g["fat_ex"] + g["fat_res"] + nb
            q = QgsFeature(D.fields())
            q.setAttributes([g["code"], "BARU" if g["code"].startswith("FDT-BARU") else "EXISTING", g["fat_ex"],
                             g["fat_res"], nb, tot, fat_fdt, fat_fdt - tot, round(g["d_entry"], 1),
                             ("DIPAKAI CLUSTER INI (%d FAT)" % nb) if nb and not g["code"].startswith("FDT-BARU")
                             else g["status"]])
            q.setGeometry(QgsGeometry.fromPointXY(g["pt"]))
            df.append(q)
        D.dataProvider().addFeatures(df)
        write(D, "FDT_ALOKASI", "fdt")
        write(G, "GARIS_FAT_FDT", "line")
        write(L, "FAT_ESTIMASI", "fat")
        write(H, "HP_PER_FAT", "hp")
        # ----- ringkasan -----
        used = [g for g in fdts if g["assigned"]]
        n_ex = sum(len(g["assigned"]) for g in used)
        lines = [
            "ALOKASI FDT & FAT (ESTIMASI) - %s" % kode,
            "Alat : %s v%s (c) %s" % (B.__product__, B.__version__, B.__author__),
            "HP %d -> FAT minimum = ceil(%d / %d) = %d FAT (HP per FAT %d = 2 x splitter 1:8); FAT estimasi sesuai "
            "sebaran HP (HP <= %.0f m dari FAT): %d" % (n_hp, n_hp, cap, n_fat, cap, opt["fat_dist"], len(fats)),
            "Pembanding desain nyata: FAT di Design Lite rata-rata %.1f HP/FAT (139 FAT, Okt 2026) -> +-%d FAT"
            % (REAL_HP_PER_FAT, int(math.ceil(n_hp / REAL_HP_PER_FAT))),
            "Kapasitas FDT: %d FAT = %d HP (kebijakan internal); radius FDT existing %.0f m dari tiang cluster terdekat"
            % (fat_fdt, fat_fdt * cap, opt["radius"]),
            "FAT ke FDT existing: %d (%s)" % (n_ex, ", ".join("%s %d FAT" % (g["code"], len(g["assigned"])) for g in used) or "-"),
            "FAT ke FDT baru    : %d -> %d FDT baru" % (len(fats) - n_ex, len(new_fdts)),
            "FAT dengan HP terjauh (drop + sepanjang jalur) > %.0f m: %d; link budget kurang (%s): %d" % (opt["fat_dist"], n_far, olt_name, n_bad_budget),
            "",
            "FDT di sekitar (urut jarak ke tiang cluster terdekat):",
        ]
        for g in sorted(fdts, key=lambda g: g["d_entry"])[:15]:
            lines.append("  %-18s %6.0f m  FAT existing %2d (%s), splitter %d, dipesan %d, cluster ini %d -> %s"
                         % (g["code"], g["d_entry"], g["fat_ex"], ("%d di Design Lite" % g["fat_rec"]) if g["fat_rec"]
                            else "premises/%d" % cap, g.get("used") or 0, g["fat_res"], len(g["assigned"]), g["status"]))
        lines += ["", "FAT estimasi:"]
        for f in fats:
            lines.append("  %s %2d HP di %-12s -> %-18s %6.0f m, HP terjauh %4.0f m, sisa budget %.1f dB"
                         % (f["id"], f["hp"], f["pole"], f["fdt"], f["d_fdt"], f["dmax"], f["sisa"]))
        lines += ["", "Dasar: FAT 16 HP = ODP-16 (2 x 1:8, praktik operator); 24 FAT/FDT dan radius 1 km = kebijakan internal;",
                  "penugasan berkapasitas (Kim dkk., EJOR 2011): FDT terdekat diisi penuh dulu; link budget: serat 0,35 dB/km, splitter "
                  "1:4 %.1f / 1:8 %.1f dB (nilai MAKS GR-1209, worst-case; tipikal industri 7,25 / 10,38 dB), 4 konektor x 0,5 dB, 10 splice x 0,1 dB, margin 3 dB <= %s (ITU-T G.984.2)."
                  % (SPLIT_LOSS[4], SPLIT_LOSS[8], olt_name),
                  "Hasil adalah ESTIMASI awal; desain dan kode FAT final tetap dari desain otomatis."]
        txt = os.path.join(out_dir, "ALOKASI_FDT.txt")
        with open(txt, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        for ln in lines:
            feedback.pushInfo(ln)
        html = os.path.join(out_dir, "ALOKASI_FDT.html")
        try:
            self._html(html, kode, n_hp, n_fat, cap, fat_fdt, opt, fats, fdts, new_fdts, n_far, n_bad_budget, olt_name)
        except Exception as e:
            feedback.reportError("Ringkasan HTML alokasi tidak dibuat: %s" % e, fatalError=False)
            html = txt
        return html

    @staticmethod
    def _html(path, kode, n_hp, n_fat, cap, fat_fdt, opt, fats, fdts, new_fdts, n_far, n_bad, olt_name):
        E = B._xe
        rows_fdt = "".join(
            "<tr><td><b>%s</b></td><td class='n'>%.0f</td><td class='n'>%d</td><td class='n'>%d</td><td class='n'>%d</td>"
            "<td class='n'>%d</td><td>%s</td></tr>" % (
                E(g["code"]), g["d_entry"], g["fat_ex"], g["fat_res"], len(g["assigned"]),
                max(0, g["free"] - len(g["assigned"])), E(g["status"]))
            for g in sorted(fdts, key=lambda g: g["d_entry"])[:15])
        rows_new = "".join("<tr><td><b>%s</b></td><td>di tiang %s</td><td class='n'>%d</td></tr>" % (
            E(g["code"]), E(g["pole"]), len(g["assigned"])) for g in new_fdts)
        rows_fat = "".join(
            "<tr><td>%s</td><td class='n'>%d</td><td>%s</td><td>%s%s</td><td class='n'>%.0f</td><td class='n' %s>%.0f</td>"
            "<td class='n' %s>%.1f</td><td>%s</td></tr>" % (
                f["id"], f["hp"], E(f["pole"]), E(f["fdt"]), " (baru)" if f["fdt_new"] else "", f["d_fdt"],
                "style='color:var(--err);font-weight:600'" if f["dmax"] > opt["fat_dist"] else "", f["dmax"],
                "style='color:var(--err);font-weight:600'" if f["sisa"] < 0 else "", f["sisa"],
                "FAT kecil: HP terpencil" if f["hp"] < 8 else "") for f in fats)
        n_ex = sum(1 for f in fats if not f["fdt_new"])
        from . import report_ui as U
        from . import penjelasan as X
        n_small = sum(1 for f in fats if f["hp"] < 8)
        counts = {"ERROR": n_bad, "WARNING": n_far, "INFO": n_small}
        if n_bad:
            verdict = "<b>%d FAT kekurangan link budget</b>; pindahkan ke FDT yang lebih dekat atau pakai splitter lebih kecil." % n_bad
        elif new_fdts and not n_ex:
            verdict = ("Tidak ada FDT existing yang bisa dipakai. Cluster ini butuh sekitar <b>%d FAT</b> dan <b>%d FDT baru</b>."
                       % (len(fats), len(new_fdts)))
        elif new_fdts:
            verdict = ("Cluster ini butuh sekitar <b>%d FAT</b>: <b>%d FAT</b> bisa memakai FDT existing (COLO) dan <b>%d FDT baru</b> "
                       "diperlukan untuk %d FAT sisanya." % (len(fats), n_ex, len(new_fdts), len(fats) - n_ex))
        else:
            verdict = ("Cluster ini butuh sekitar <b>%d FAT</b> dan semuanya bisa memakai FDT existing (COLO). "
                       "Tidak perlu FDT baru." % len(fats))
        kpi = [("Homepass", n_hp, "rumah yang akan dilayani"),
               ("FAT minimum", n_fat, "%d HP dibagi %d HP per FAT, dibulatkan ke atas" % (n_hp, cap)),
               ("FAT estimasi", len(fats), "HP dikelompokkan sepanjang jalur, jarak ke FAT maks %.0f m" % opt["fat_dist"]),
               ("Pembanding desain nyata", int(math.ceil(n_hp / REAL_HP_PER_FAT)), "rata-rata %.1f HP per FAT di jaringan existing"
                % REAL_HP_PER_FAT),
               ("FAT ke FDT existing", n_ex, "memakai FDT yang sudah ada (COLO)"),
               ("FDT baru", len(new_fdts), "melayani %d FAT" % (len(fats) - n_ex))]
        kpi_html = ("<section class='block'><h2>Angka utama</h2><div class='howto kpi'>%s</div></section>" % "".join(
            "<div class='inf'><b>%s</b><span style='font:700 26px var(--head)'>%d</span><small>%s</small></div>" % (
                E(a), b, E(c)) for a, b, c in kpi))
        fdt_card = U.rule_card(
            "fdt", "INFO" if fdts else "UNVERIFIED", "FDT existing di sekitar (radius %.0f m)" % opt["radius"],
            "%d FDT ditemukan" % len(fdts), {},
            "FDT existing dalam radius dari tiang cluster terdekat, beserta sisa slot (dalam satuan FAT).",
            "Memakai FDT existing (COLO) jauh lebih murah dan cepat daripada memasang FDT baru.",
            "Pilih FDT dengan sisa slot terbanyak dan jarak terdekat; FDT berslot sedikit dilewati agar FAT tidak tersebar.",
            "<div class='scroll'><table><tr><th>FDT</th><th class='n'>Jarak (m)</th><th class='n'>FAT existing</th>"
            "<th class='n'>Dipesan cluster lain</th><th class='n'>Cluster ini</th><th class='n'>Sisa slot</th><th>Status</th></tr>%s"
            "</table></div><p class='src'>Kapasitas %d FAT per FDT (= %d HP). FAT existing = jumlah FAT di jaringan existing atau "
            "premises/16 (yang lebih besar); sisa slot juga dibatasi output splitter FDT.</p>" % (
                rows_fdt or "<tr><td colspan='7'>Tidak ada FDT existing di sekitar.</td></tr>", fat_fdt, fat_fdt * cap), is_open=True)
        new_card = U.rule_card(
            "new", "WARNING", "Usulan FDT baru", "%d FDT baru" % len(new_fdts), {},
            "FAT yang tidak kebagian slot FDT existing dikelompokkan ke FDT baru.",
            "FDT baru menambah biaya perangkat, kabel feeder dan izin.",
            "Lokasi awal adalah tiang terdekat dari pusat FAT yang dilayani; sesuaikan dengan jalur feeder.",
            "<div class='scroll'><table><tr><th>FDT</th><th>Lokasi awal</th><th class='n'>FAT</th></tr>%s</table></div>" % rows_new,
            is_open=True) if new_fdts else ""
        fat_card = U.rule_card(
            "fat", "ERROR" if n_bad else ("WARNING" if n_far else "PASS"), "FAT estimasi", "%d FAT" % len(fats),
            {k: v for k, v in counts.items() if v},
            "Setiap kelompok HP, tiang FAT, FDT induk, jarak HP terjauh sepanjang jalur, dan sisa link budget.",
            "Jarak HP yang terlalu jauh atau link budget negatif berarti sinyal di rumah pelanggan bisa tidak stabil.",
            "Angka merah perlu ditangani: geser FAT, pecah kelompok, atau pilih FDT yang lebih dekat. FAT kecil (< 8 HP) "
            "biasanya HP terpencil: cek apakah perlu tiang atau jalur tambahan.",
            "<div class='scroll'><table><tr><th>FAT</th><th class='n'>HP</th><th>Tiang</th><th>FDT</th><th class='n'>Jarak FDT (m)</th>"
            "<th class='n'>HP terjauh (m)</th><th class='n'>Sisa budget (dB)</th><th>Catatan</th></tr>%s</table></div>" % rows_fat)
        terms = "".join("<div class='inf'><b>%s</b><small>%s</small></div>" % (E(a), E(b)) for a, b in X.TOOL3_TERMS)
        basis = ("<section class='block'><h2>Istilah</h2><div class='howto'>%s</div></section>"
                 "<section class='block'><details class='plain'><summary>Dasar perhitungan</summary><div class='stat'><ul>"
                 "<li>FAT = 16 HP: 2 splitter 1:8. HP dikelompokkan sepanjang jalur kabel; jarak HP ke FAT = drop ke tiang terdekat "
                 "+ jarak sepanjang jalur. FAT &lt; 8 HP = HP terpencil.</li>"
                 "<li>FDT maks %d FAT dan radius colo %.0f m: kebijakan internal (parameter, dapat diubah).</li>"
                 "<li>Penugasan berkapasitas: tiap FAT ke FDT terdekat yang masih punya slot (capacitated location-allocation, "
                 "Kim dkk., EJOR 210(2) 2011).</li>"
                 "<li>Link budget: serat 0,35 dB/km (G.652.D), splitter 1:4 7,7 dB / 1:8 11,2 dB (nilai maksimum GR-1209, "
                 "worst-case), 4 konektor &times; 0,5 dB, 10 splice &times; 0,1 dB, margin 3 dB, harus &le; %s (ITU-T G.984.2). "
                 "Feeder diasumsikan %.1f km, jalur FDT-FAT = %.1f &times; garis lurus.</li>"
                 "<li>Hasil adalah <b>estimasi awal</b> untuk keputusan COLO atau FDT baru; desain dan kode FAT final tetap dari "
                 "desain otomatis.</li></ul></div></details></section>" % (terms, fat_fdt, opt["radius"], E(olt_name),
                                                                           opt["feeder_km"], opt["route_f"]))
        doc = U.page("Alokasi FDT %s" % kode, "Alokasi FDT dan FAT (estimasi)", kode, verdict,
                     [("Kelas optik", olt_name), ("Batas jarak HP", "%.0f m" % opt["fat_dist"]),
                      ("Radius COLO", "%.0f m" % opt["radius"]), ("Alat", "%s v%s" % (B.__product__, B.__version__))],
                     None, [], kpi_html + fdt_card + new_card + fat_card + basis,
                     "%s v%s. Estimasi awal; keputusan desain tetap pada desainer." % (E(B.__product__), B.__version__),
                     with_tools=False)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(doc)

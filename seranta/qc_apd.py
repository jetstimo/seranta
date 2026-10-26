# -*- coding: utf-8 -*-
"""
Seranta - FTTH Design Assistant - alat 4: QC APD Pasca-Desain (Served, FAT Coverage, ujung kabel, multi-FDT,
FDT COLO/NEW Feeder-Distribusi, BOM, kode FAT, KMZ APD)
Copyright (C) 2026 Joseph Edward Timothy Siahaan <edwardtimoo@gmail.com>. GPL-2.0-or-later (see LICENSE).

Masukan (semua opsional kecuali salah satu dari 1 atau 2):
  1. folder output desain otomatis (net_nodes, net_endpoints, net_cables, net_ServiceAreasVoronoi, net_SpliceClosure .shp)
  2. KMZ APD final (aplikasi peta KMZ: Homepass, FAT Coverage, Net_Nodes, Net_Cables, Pole, Closure, Existing Cluster)
  3. paket Feeder dan Distribusi (KMZ/KML atau folder) + status FDT (AUTO/COLO/NEW/UNKNOWN)
  4. BOM / Daily FTTH (.xlsx/.csv)
  5. layer hambatan (rel/tol) untuk crossing
Keluaran di <folder>/QC_APD/: satu shp per aturan (skema temuan tunggal), QC_APD_TEMUAN.csv, QC_APD.json,
QC_APD.html. Status setiap aturan: PASS / ERROR / WARNING / INFO / UNVERIFIED (data kurang = bukan PASS).
"""
try:
    from . import _log
except ImportError:  # dijalankan sebagai modul lepas (uji unit)
    import _log
import datetime as _dt
import html as _h
import os
import re

from qgis.core import (
    QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeature, QgsGeometry, QgsPointXY, QgsProcessingAlgorithm,
    QgsProcessingContext, QgsProcessingException, QgsProcessingParameterBoolean, QgsProcessingParameterEnum,
    QgsProcessingParameterFile, QgsProcessingParameterVectorLayer, QgsProject, QgsVectorLayer, QgsWkbTypes,
)
from qgis.PyQt.QtCore import QCoreApplication

from . import buat_input_desain as B
from . import qc_core as Q
from . import qc_paket as P

_E = _h.escape
STATUS_OPTS = ["AUTO (dari nama/atribut: COLO/EXISTING atau NEW)", "COLO", "NEW", "UNKNOWN (belum diputuskan)"]
STATUS_VAL = ["AUTO", "COLO", "NEW", "UNKNOWN"]


def _gtype(layer):
    return QgsWkbTypes.geometryType(layer.wkbType())


def layer_records(path_or_layer, feedback=None):
    """Baca layer vektor (path atau QgsVectorLayer) -> [(atribut, jenis, geometri lon/lat)]; ditransformasi ke
    EPSG:4326 bila CRS lain; multi-geometri dipecah per bagian."""
    lyr = path_or_layer if isinstance(path_or_layer, QgsVectorLayer) else QgsVectorLayer(path_or_layer, "x", "ogr")
    if not lyr.isValid():
        if feedback:
            feedback.reportError("Layer tidak terbaca: %s" % path_or_layer, fatalError=False)
        return []
    wgs = QgsCoordinateReferenceSystem("EPSG:4326")
    ct = None
    if lyr.crs().isValid() and lyr.crs() != wgs:
        ct = QgsCoordinateTransform(lyr.crs(), wgs, QgsProject.instance())
    names = [f.name() for f in lyr.fields()]
    gt = _gtype(lyr)
    PT, LN, PG = (B._enum("Qgis.GeometryType.Point", "QgsWkbTypes.PointGeometry"),
                  B._enum("Qgis.GeometryType.Line", "QgsWkbTypes.LineGeometry"),
                  B._enum("Qgis.GeometryType.Polygon", "QgsWkbTypes.PolygonGeometry"))
    out = []
    for f in lyr.getFeatures():
        g = f.geometry()
        if g is None or g.isEmpty():
            continue
        if ct is not None:
            g = QgsGeometry(g)
            g.transform(ct)
        a = {n: (None if v is None or str(v) == "NULL" else v) for n, v in zip(names, f.attributes())}
        if gt == PT:
            pts = g.asMultiPoint() if g.isMultipart() else [g.asPoint()]
            for p in pts[:1]:
                out.append((a, "point", (p.x(), p.y())))
        elif gt == LN:
            parts = g.asMultiPolyline() if g.isMultipart() else [g.asPolyline()]
            for ln in parts:
                if len(ln) >= 2:
                    out.append((a, "line", [(p.x(), p.y()) for p in ln]))
        elif gt == PG:
            polys = g.asMultiPolygon() if g.isMultipart() else [g.asPolygon()]
            for pg in polys:
                if pg and len(pg[0]) >= 4:
                    out.append((a, "polygon", ([(p.x(), p.y()) for p in pg[0]], [[(p.x(), p.y()) for p in r] for r in pg[1:]])))
    return out


def read_package(path, label, feedback=None):
    """Paket Feeder/Distribusi: file KMZ/KML/SHP/GPKG atau folder berisi file tersebut -> Net (None bila tidak ada)."""
    if not path:
        return None
    net = Q.Net(label)
    files = []
    if os.path.isdir(path):
        for root, dirs, fs in os.walk(path):
            dirs[:] = [d for d in dirs if not d.upper().startswith(("QC", "HASIL", "INPUT"))]
            files += [os.path.join(root, f) for f in fs if f.lower().endswith((".kmz", ".kml", ".shp", ".gpkg"))]
    elif os.path.isfile(path):
        files = [path]
    if not files:
        return net                  # diberikan tetapi kosong -> paket ada, FDT tidak ditemukan (bukan UNVERIFIED)
    for p in files:
        try:
            if p.lower().endswith((".kmz", ".kml")):
                Q.read_kmz(p, net)
            else:
                recs = layer_records(p, feedback)
                kinds = {"point": "nodes", "line": "cables", "polygon": "polys"}
                for gt in ("point", "line", "polygon"):
                    sub = [r for r in recs if r[1] == gt]
                    if sub:
                        Q.read_layer_records(net, kinds[gt], sub, p)
        except Exception as e:
            if feedback:
                feedback.reportError("Paket %s: %s tidak terbaca (%s)" % (label, os.path.basename(p), e), fatalError=False)
    return net


def find_bom(folder):
    out = []
    if folder and os.path.isdir(folder):
        for root, dirs, fs in os.walk(folder):
            if root.count(os.sep) - folder.count(os.sep) > 1:
                dirs[:] = []
            for f in fs:
                if not f.startswith("~$") and f.lower().endswith((".xlsx", ".xlsm", ".csv")) and \
                        re.search(r"\bBOM\b|BOQ|daily ?ftth|material", f, re.I):
                    out.append(os.path.join(root, f))
    return sorted(out, key=os.path.getmtime)[-1] if out else ""


GENERIC_OUT_RX = re.compile(r"^(output|outputs|export|ekspor|hasil|result|results|data|qc_apd.*|autodesign.*|net.*)$", re.I)


def project_label(base):
    """Nama proyek untuk laporan: folder data, atau folder induknya bila folder data bernama umum (OUTPUT, EXPORT)."""
    d = base.rstrip("\\/")
    for _ in range(3):
        nm = os.path.basename(d)
        if nm and not GENERIC_OUT_RX.match(nm):
            return nm
        d = os.path.dirname(d)
    return os.path.basename(base.rstrip("\\/")) or "PROYEK"


def _search_dirs(folder):
    """Folder data + dua tingkat induknya (ekspor desain biasanya di subfolder OUTPUT proyek)."""
    out = []
    d = folder
    for _ in range(3):
        if d and os.path.isdir(d) and d not in out:
            out.append(d)
        d = os.path.dirname(d.rstrip("\\/")) if d else ""
    return out


def _find_file(folder, rx, exts, avoid=None):
    for d in _search_dirs(folder):
        c = [os.path.join(d, f) for f in os.listdir(d) if f.lower().endswith(exts) and not f.startswith("~$")
             and re.search(rx, f, re.I) and not (avoid and re.search(avoid, f, re.I))]
        if c:
            # utamakan .xlsx, lalu yang terbaru
            return sorted(c, key=lambda p: (not p.lower().endswith(".xlsx"), -os.path.getmtime(p)))[0]
    return ""


def find_apd_kmz(folder):
    return _find_file(folder, r"APD|DISTRIBUSI|FINAL", (".kmz", ".kml"), r"QC_|FEEDER|^F\d+_T\d+")


def find_code_table(folder):
    return _find_file(folder, r"(FAT|FDT)[\s_-]*(FAT|FDT)[\s_-]*CODE", (".xlsx", ".csv"))


def find_splice_plan(folder):
    return _find_file(folder, r"splice[\s_-]*plan", (".xlsx",), r"^N\d{3}_")


def read_points_any(path, feedback=None):
    """Titik dari KMZ/KML (semua Point), SHP/GPKG (layer titik) atau CSV (kolom lat/lon)."""
    pts = []
    if not path or not os.path.exists(path):
        return pts
    low = path.lower()
    try:
        if low.endswith((".kmz", ".kml")):
            data, _n = Q._kml_bytes(path)
            for m in re.finditer(rb"<Point>.*?<coordinates>\s*([-0-9.]+)\s*,\s*([-0-9.]+)", data, re.S):
                pts.append((float(m.group(1)), float(m.group(2))))
        elif low.endswith(".csv"):
            import csv as _csv
            with open(path, encoding="utf-8-sig", errors="replace") as fh:
                txt = fh.read()
            dl = ";" if txt.count(";") > txt.count(",") else ","
            rows = list(_csv.reader(txt.splitlines(), delimiter=dl))
            h = [c.strip().lower() for c in rows[0]] if rows else []
            ila = next((i for i, c in enumerate(h) if c.startswith("lat")), None)
            ilo = next((i for i, c in enumerate(h) if c.startswith(("lon", "lng", "long"))), None)
            for r in rows[1:]:
                try:
                    pts.append((float(r[ilo].replace(",", ".")), float(r[ila].replace(",", "."))))
                except (TypeError, ValueError, IndexError):
                    continue
        else:
            pts = [g for a, gt, g in layer_records(path, feedback) if gt == "point"]
    except Exception as e:
        if feedback:
            feedback.reportError("Tiang referensi tidak terbaca (%s): %s" % (os.path.basename(path), e), fatalError=False)
    return pts


class QcApdStyle(B.QgsProcessingLayerPostProcessorInterface):
    def __init__(self, name):
        super().__init__()
        self.name = name

    def postProcessLayer(self, layer, context, feedback):
        try:
            layer.setName(self.name)
            B.style_qc_layer(layer)
            layer.setCustomProperty("seranta_qc", "1")
            layer.triggerRepaint()
        except Exception as e:
            if feedback:
                feedback.reportError("Gaya QC APD tidak diterapkan: %s" % e, fatalError=False)


class QcApd(QgsProcessingAlgorithm):
    AUTODESIGN, APD, FEEDER, DIST, STATUS, BOM, OBST, PROFILE, SDPROJ, OUTDIR, OPEN = (
        "AUTODESIGN", "APD", "FEEDER", "DIST", "STATUS", "BOM", "OBST", "PROFILE", "SDPROJ", "OUTDIR", "OPEN")
    CODES, SPLICE, MASTER, POLEREF, REF = "CODES", "SPLICE", "MASTER", "POLEREF", "REF"

    def tr(self, s):
        return QCoreApplication.translate("Seranta", s)

    def createInstance(self):
        return QcApd()

    def name(self):
        return "qc_apd_pasca_desain"

    def displayName(self):
        return self.tr("4. QC APD Pasca-Desain (aturan paket APD + kualitas jaringan)")

    def group(self):
        return ""

    def groupId(self):
        return ""

    def icon(self):
        try:
            from qgis.PyQt.QtGui import QIcon
            return QIcon(os.path.join(os.path.dirname(__file__), "icon.png"))
        except Exception:
            return super().icon()

    def shortHelpString(self):
        return self.tr(
            "<p><b>QC desain APD setelah desain otomatis</b> sesuai Handbook KMZ (34 kasus QC) dan spesifikasi pembaruan 16 poin.</p>"
            "<p>Isi <b>folder output desain otomatis</b> (net_nodes, net_endpoints, net_cables, net_ServiceAreasVoronoi, "
            "net_SpliceClosure) dan/atau <b>KMZ APD final</b>. Opsional: paket Feeder & Distribusi + status FDT "
            "(COLO/NEW), BOM/Daily FTTH, layer rel/tol, profil standar (splitter 1x4 / 1x8 / regulasi ketat) atau file .sdproj.</p>"
            "<p>Setiap aturan berstatus <b>PASS</b>, <b>ERROR</b> (wajib diperbaiki), <b>WARNING</b> (perlu ditinjau), "
            "<b>INFO</b>, atau <b>UNVERIFIED</b> (data belum cukup - <u>tidak dihitung lolos</u>). Hasil: folder "
            "<code>QC_APD</code> (shp per aturan, CSV, JSON, HTML) dan panel <b>Navigator QC</b> untuk menelusuri "
            "dan memberi status review (verified / false positive / approved exception / resolved).</p>")

    def initAlgorithm(self, config=None):
        F, FO = B.FILE_BEHAVIOR, B.FOLDER_BEHAVIOR
        self.addParameter(QgsProcessingParameterFile(self.AUTODESIGN, self.tr("1. Folder output desain otomatis (net_*.shp)"),
                                                     behavior=FO, optional=True))
        self.addParameter(QgsProcessingParameterFile(self.APD, self.tr("2. KMZ APD final (opsional bila 1 diisi)"),
                                                     behavior=F, optional=True, fileFilter="KMZ/KML (*.kmz *.kml)"))
        profs = Q.load_profiles()
        self._pids = list(profs)
        self.addParameter(QgsProcessingParameterEnum(self.PROFILE, self.tr("3. Profil standar QC"),
                                                     options=["%s - %s" % (k, v.get("nama", "")) for k, v in profs.items()],
                                                     defaultValue=0))
        self.addParameter(QgsProcessingParameterEnum(self.STATUS, self.tr("4. Status FDT (COLO/NEW)"),
                                                     options=STATUS_OPTS, defaultValue=0))
        self.addParameter(QgsProcessingParameterFile(self.FEEDER, self.tr("5. Paket Feeder (KMZ atau folder; kosong = UNVERIFIED)"),
                                                     behavior=F, optional=True, fileFilter="Data (*.kmz *.kml *.shp *.gpkg)"))
        self.addParameter(QgsProcessingParameterFile(self.DIST, self.tr("6. Paket Distribusi (KMZ atau folder; kosong = pakai data 1/2)"),
                                                     behavior=F, optional=True, fileFilter="Data (*.kmz *.kml *.shp *.gpkg)"))
        self.addParameter(QgsProcessingParameterFile(self.BOM, self.tr("7. BOM / Daily FTTH (.xlsx/.csv; kosong = cari otomatis)"),
                                                     behavior=F, optional=True, fileFilter="BOM (*.xlsx *.xlsm *.csv)"))
        self.addParameter(QgsProcessingParameterFile(self.CODES, self.tr("8. Tabel kode FDT/FAT (.xlsx/.csv; kosong = cari otomatis)"),
                                                     behavior=F, optional=True, fileFilter="Tabel (*.xlsx *.csv)"))
        self.addParameter(QgsProcessingParameterFile(self.SPLICE, self.tr("9. Splice Plan (.xlsx; kosong = cari otomatis)"),
                                                     behavior=F, optional=True, fileFilter="Spreadsheet (*.xlsx)"))
        self.addParameter(QgsProcessingParameterFile(self.POLEREF, self.tr("10. Tiang existing referensi kota (KMZ/SHP/CSV; kosong = UNVERIFIED)"),
                                                     behavior=F, optional=True, fileFilter="Data (*.kmz *.kml *.shp *.gpkg *.csv)"))
        self.addParameter(QgsProcessingParameterFile(self.MASTER, self.tr("11. Rekap kode FDT / attributes (.xlsx/.csv; kosong = UNVERIFIED)"),
                                                     behavior=F, optional=True, fileFilter="Tabel (*.xlsx *.csv)"))
        self.addParameter(QgsProcessingParameterBoolean(self.OPEN, self.tr("Buka laporan HTML setelah selesai"), defaultValue=True))
        adv = [QgsProcessingParameterFile(self.REF, self.tr("Folder data referensi (jaringan existing) untuk cek kode FDT dipakai proyek lain"),
                                          behavior=FO, optional=True),QgsProcessingParameterVectorLayer(self.OBST, self.tr("Layer rel/tol/hambatan (crossing)"), optional=True),
               QgsProcessingParameterFile(self.SDPROJ, self.tr("Config desain otomatis .sdproj (menimpa angka profil)"), behavior=F,
                                          optional=True, fileFilter="desain otomatis (*.sdproj)"),
               QgsProcessingParameterFile(self.OUTDIR, self.tr("Folder hasil (kosong = di folder data)"), behavior=FO, optional=True)]
        for p in adv:
            try:
                p.setFlags(p.flags() | B.Qgis.ProcessingParameterFlag.Advanced)
            except Exception:
                try:
                    p.setFlags(p.flags() | B.ADVANCED_FLAG)
                except Exception as _e:
                    _log.note(_e)
            self.addParameter(p)

    def prepareAlgorithm(self, parameters, context, feedback):
        for k in (self.AUTODESIGN, self.APD):
            v = self.parameterAsFile(parameters, k, context)
            base = v if v and os.path.isdir(v) else (os.path.dirname(v) if v else "")
            if base:
                B.release_old_outputs(base, markers=("QC_APD",))
        return True

    # ------------------------------------------------------------------------------------------------
    def processAlgorithm(self, parameters, context, feedback):
        autodesign = self.parameterAsFile(parameters, self.AUTODESIGN, context)
        apd = self.parameterAsFile(parameters, self.APD, context)
        if not autodesign and not apd:
            raise QgsProcessingException("Isi folder output desain otomatis (1) atau KMZ APD final (2).")
        base = autodesign if autodesign and os.path.isdir(autodesign) else os.path.dirname(apd)
        if not apd and autodesign:
            apd = find_apd_kmz(autodesign)
            if apd:
                feedback.pushInfo("KMZ APD ditemukan otomatis: %s" % os.path.basename(apd))
        profs = Q.load_profiles()
        pids = list(profs)
        pid = pids[min(self.parameterAsEnum(parameters, self.PROFILE, context), len(pids) - 1)]
        prof, w = Q.get_profile(pid)
        if w:
            feedback.reportError(w, fatalError=False)
        sd = self.parameterAsFile(parameters, self.SDPROJ, context) if self.SDPROJ in parameters else ""
        if sd and os.path.isfile(sd):
            over = Q.sdproj_overrides(sd)
            prof = Q.apply_overrides(prof, over, os.path.basename(sd))
            feedback.pushInfo("Profil ditimpa dari %s: %s" % (os.path.basename(sd), over))
        status = STATUS_VAL[self.parameterAsEnum(parameters, self.STATUS, context)]

        # ---- data utama ----
        if not apd:
            apd = find_apd_kmz(base)
            if apd:
                feedback.pushInfo("KMZ APD ditemukan otomatis: %s" % os.path.basename(apd))
        main = Q.Net(project_label(base))
        kn = None
        lay = Q.find_autodesign_layers(autodesign) if autodesign else {}
        for kind, pth in lay.items():
            feedback.pushInfo("desain otomatis %-9s: %s" % (kind, os.path.basename(pth)))
            Q.read_layer_records(main, kind, layer_records(pth, feedback), pth)
        if apd:
            kn = Q.read_kmz(apd, Q.Net("APD"))
            feedback.pushInfo("KMZ APD: %d node, %d HP, %d kabel, %d coverage, %d tiang, %d closure, %d folder"
                              % (len(kn.nodes), len(kn.endpoints), len(kn.cables), len(kn.polys), len(kn.poles),
                                 len(kn.closures), len(kn.folders)))
            pr0 = kn.proj()
            merged = P.unify_nodes(kn, Q.pv(prof, "fdt_same_m", 30.0), pr0)
            if merged:
                feedback.pushInfo("Perangkat di folder Feeder & Distribution digabung sebagai satu: %s" % ", ".join(sorted(set(merged))))
            autodesign_net = None
            if "nodes" in main.has:
                autodesign_net = Q.Net("ekspor")
                autodesign_net.nodes = [dict(n) for n in main.nodes]
                n_code = P.enrich_codes(main, kn, pr0)
                if n_code:
                    feedback.pushInfo("Kode FDT/FAT dari KMZ dipasangkan ke %d node hasil ekspor (lokasi sama)" % n_code)
            for k in ("nodes", "endpoints", "cables", "polys", "poles", "closures"):
                if k not in main.has and getattr(kn, k):
                    setattr(main, k, getattr(kn, k))
                    main.has.add(k)
                    main.sources[k] = os.path.basename(apd)
            main.folders, main.icons, main.markers = kn.folders, kn.icons, main.markers + kn.markers
            main.has.add("kmz")
            main.files.append(apd)
        if not main.poles:
            pole = self._find_pole(base)
            if pole:
                feedback.pushInfo("Tiang dari hasil alat 1: %s" % os.path.basename(pole))
                Q.read_kmz(pole, main)
        obst = self.parameterAsVectorLayer(parameters, self.OBST, context) if self.OBST in parameters else None
        if obst is not None:
            for a, gt, g in layer_records(obst, feedback):
                if gt == "line":
                    main.markers.append({"kind": "obstacle", "pts": g, "name": str(a.get("name") or a.get("NAME") or obst.name())})
                elif gt == "polygon":
                    main.markers.append({"kind": "obstacle", "pts": g[0], "name": str(a.get("name") or obst.name())})
        if not any(getattr(main, k) for k in ("nodes", "endpoints", "cables")):
            raise QgsProcessingException("Tidak ada data jaringan (net_nodes/net_endpoints/net_cables atau isi KMZ APD) yang "
                                         "terbaca di %s" % (autodesign or apd))
        fp = self.parameterAsFile(parameters, self.FEEDER, context)
        dp = self.parameterAsFile(parameters, self.DIST, context)
        feeder = read_package(fp, "Feeder", feedback) if fp else None
        dist = read_package(dp, "Distribusi", feedback) if dp else main
        if not dp:
            feedback.pushInfo("Paket Distribusi = data APD/desain otomatis yang diperiksa (isian 6 kosong)")
        bom = self.parameterAsFile(parameters, self.BOM, context) or find_bom(base)
        if bom:
            feedback.pushInfo("BOM: %s" % os.path.basename(bom))

        cluster = re.sub(r"[^A-Za-z0-9]+", "_", main.label).strip("_")[:60] or "CLUSTER"
        paket = self._paket(parameters, context, feedback, base, kn, locals().get("autodesign_net"))
        results = Q.run_all(main, prof, feeder, dist, status, bom or None, cluster, paket=paket)
        out_root = self.parameterAsFile(parameters, self.OUTDIR, context) if self.OUTDIR in parameters else ""
        out_dir = os.path.join(out_root or base, "QC_APD")
        os.makedirs(out_dir, exist_ok=True)
        old = self._old_reviews(out_dir)
        n_keep = 0
        for f in Q.findings_of(results):
            rv = old.get(Q.review_key(f))
            if rv:
                f["review"], f["note"] = rv
                n_keep += 1
        locked = []
        for fn in os.listdir(out_dir):
            if re.search(r"\.(shp|shx|dbf|prj|cpg|qml|csv)$", fn, re.I) and fn != "QC_APD_TEMUAN.csv":
                try:
                    os.remove(os.path.join(out_dir, fn))
                except OSError:
                    locked.append(fn)
        if locked:
            # file masih dibuka aplikasi lain (mis. jendela QGIS kedua): jangan menulis setengah-setengah
            new_dir = out_dir + "_" + _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            feedback.reportError("%d file di %s masih terkunci aplikasi lain (mis. QGIS lain yang membuka layer QC "
                                 "ini); hasil ditulis ke %s" % (len(locked), out_dir, new_dir), fatalError=False)
            os.makedirs(new_dir, exist_ok=True)
            out_dir = new_dir
        loads = self._write_layers(results, out_dir, context, feedback)
        csvp = os.path.join(out_dir, "QC_APD_TEMUAN.csv")
        Q.write_csv(csvp, Q.findings_of(results))
        meta = {"produk": "%s v%s" % (B.__product__, B.__version__), "dibuat": _dt.datetime.now().isoformat(timespec="seconds"),
                "cluster": cluster, "autodesign": autodesign, "apd_kmz": apd, "feeder": fp, "distribusi": dp, "bom": bom,
                "status_fdt": status, "sumber_data": main.sources}
        Q.write_json(os.path.join(out_dir, "QC_APD.json"), results, prof, meta)
        html = os.path.join(out_dir, "QC_APD.html")
        self._html(html, results, prof, meta, main)
        ov = Q.overall(results)
        feedback.pushInfo("")
        feedback.pushInfo("STATUS KESELURUHAN: %s  (profil %s, versi aturan %s)" % (ov, prof["profile_id"], prof["rule_version"]))
        for r in results:
            c = r.counts()
            feedback.pushInfo("  %-11s %-14s %s%s" % (r.status, r.rule_id, ", ".join("%s %d" % kv for kv in sorted(c.items())),
                                                    (" | " + r.unverified) if r.unverified else ""))
        if n_keep:
            feedback.pushInfo("%d status review dari run sebelumnya dipertahankan" % n_keep)
        feedback.pushInfo("Hasil: %s" % out_dir)
        for k, (pth, nm) in enumerate(loads):
            try:
                det = QgsProcessingContext.LayerDetails(nm, context.project(), nm)
                try:
                    det.groupName = "%s QC APD" % cluster
                    det.layerSortKey = k
                except Exception as _e:
                    _log.note(_e)
                pp = QcApdStyle(nm)
                B._KEEP_ALIVE.append(pp)
                det.setPostProcessor(pp)
                context.addLayerToLoadOnCompletion(pth, det)
            except Exception as e:
                feedback.reportError("Layer %s tidak dimuat: %s" % (nm, e), fatalError=False)
        self._open = html if (self.parameterAsBool(parameters, self.OPEN, context) if self.OPEN in parameters else False) else None
        return {"STATUS": ov, "OUTPUT": out_dir}

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

    # ------------------------------------------------------------------------------------------------
    @staticmethod
    def _find_pole(base):
        for d in (base, os.path.dirname(base)):
            try:
                for sub in os.listdir(d):
                    full = os.path.join(d, sub)
                    if os.path.isdir(full) and sub.upper().startswith("INPUT"):
                        for f in os.listdir(full):
                            if f.upper().endswith("POLE.KMZ"):
                                return os.path.join(full, f)
            except OSError:
                continue
        return ""

    def _paket(self, parameters, context, feedback, base, kn, autodesign_net):
        """Berkas pendukung QC-01..07: tabel kode, Splice Plan, rekap kode, tiang referensi, kode FDT existing."""
        def par(k):
            return self.parameterAsFile(parameters, k, context) if k in parameters else ""
        codes_p = par(self.CODES) or find_code_table(base)
        splice_p = par(self.SPLICE) or find_splice_plan(base)
        master_p, ref_p = par(self.MASTER), par(self.POLEREF)
        pk = {"kmz": kn, "autodesign": autodesign_net}
        if codes_p:
            pk["codes"], nts = P.read_code_table(codes_p, B.read_xlsx)
            for t in nts:
                feedback.pushInfo("Tabel kode : " + t)
            if not pk["codes"]:
                pk["codes"] = None
        else:
            feedback.pushInfo("Tabel kode FDT/FAT tidak ditemukan (QC-03 UNVERIFIED)")
        if splice_p:
            pk["splice"], nts = P.read_splice_plan(splice_p, B.read_xlsx)
            for t in nts:
                feedback.pushInfo("Splice Plan: " + t)
        if master_p:
            pk["master"], pk["master_src"] = P.read_code_master(master_p, B.read_xlsx), os.path.basename(master_p)
            feedback.pushInfo("Rekap kode : %d kode FDT di %s" % (len(pk["master"]), pk["master_src"]))
        if ref_p:
            pk["ref_pts"], pk["ref_src"] = read_points_any(ref_p, feedback), os.path.basename(ref_p)
            feedback.pushInfo("Tiang referensi: %d titik dari %s" % (len(pk["ref_pts"]), pk["ref_src"]))
        ref_dir = par(self.REF)
        if not ref_dir:
            try:
                from qgis.core import QgsSettings
                ref_dir = QgsSettings().value("seranta/ref_dir", "") or ""
            except Exception:
                ref_dir = ""
        if ref_dir and os.path.isdir(ref_dir) and kn is not None and kn.nodes:
            try:
                xs = [n["x"] for n in kn.nodes]
                ys = [n["y"] for n in kn.nodes]
                ext = (min(xs) - 0.05, min(ys) - 0.05, max(xs) + 0.05, max(ys) + 0.05)
                dl = {}
                for fp in B.ref_files(ref_dir, "designlite"):
                    for e in B.cached_read("designlite", fp, ext, B.read_design_lite, feedback):
                        if e.get("kind", "fdt") == "fdt":
                            dl.setdefault(Q.norm_code(e["code"]), []).append((e["x"], e["y"]))
                pk["dl_codes"] = dl
                feedback.pushInfo("Kode FDT jaringan existing di sekitar: %d" % len(dl))
            except Exception as e:
                feedback.reportError("Data jaringan existing tidak terbaca: %s" % e, fatalError=False)
        return pk

    @staticmethod
    def _old_reviews(out_dir):
        old = {}
        p = os.path.join(out_dir, "QC_APD_TEMUAN.csv")
        if os.path.exists(p):
            import csv
            try:
                with open(p, encoding="utf-8-sig") as fh:
                    for r in csv.DictReader(fh):
                        if r.get("review") and r["review"] != "OPEN":
                            f = {"rule_id": r.get("rule_id"), "object_id": r.get("object_id"),
                                 "geom": ("point", (float(r["lon"]), float(r["lat"]))) if r.get("lon") else None}
                            old[Q.review_key(f)] = (r["review"], r.get("note", ""))
            except (OSError, ValueError, KeyError) as _e:
                _log.note(_e)
        # status yang disimpan langsung di shp oleh Navigator
        for fn in os.listdir(out_dir):
            if fn.lower().endswith(".shp"):
                lyr = QgsVectorLayer(os.path.join(out_dir, fn), "o", "ogr")
                if not lyr.isValid() or lyr.fields().indexOf("review") < 0:
                    continue
                for ft in lyr.getFeatures():
                    rv = ft["review"]
                    if rv and str(rv) not in ("OPEN", "NULL"):
                        f = {"rule_id": ft["kode"], "object_id": ft["objek_id"] if lyr.fields().indexOf("objek_id") >= 0 else "",
                             "geom": ("point", (ft["lon"], ft["lat"]))}
                        old[Q.review_key(f)] = (str(rv), str(ft["catatan"] or ""))
                del lyr
        return old

    def _write_layers(self, results, out_dir, context, feedback):
        FIELDS = ("&field=no:integer&field=status:string(10)&field=severity:string(10)&field=standar:string(12)"
                  "&field=jenis:string(80)&field=keterangan:string(254)&field=nilai:double(12,2)&field=batas:double(12,2)"
                  "&field=dasar:string(160)&field=dasar_src:string(20)&field=kode:string(40)&field=finding_id:string(24)"
                  "&field=objek:string(20)&field=objek_id:string(60)&field=saran:string(200)&field=profil:string(24)"
                  "&field=versi:string(14)&field=review:string(20)&field=catatan:string(200)"
                  "&field=lon:double(12,7)&field=lat:double(12,7)")
        loads, n = [], 0
        nogeo = [(r, f) for r in results for f in r.findings if not f.get("geom")]
        if nogeo:
            # tabel non-spasial ditulis sebagai CSV (OGR membacanya sebagai tabel atribut; shapefile tanpa geometri
            # tidak andal di semua versi GDAL)
            import csv as _csv
            cols = [c.split(":")[0] for c in FIELDS.split("&field=")[1:]]
            path = os.path.join(out_dir, "T_NONSPASIAL.csv")
            try:
                with open(path, "w", encoding="utf-8-sig", newline="") as fh:
                    wr = _csv.writer(fh)
                    wr.writerow(cols)
                    for r, f in nogeo:
                        n += 1
                        sev = f["severity"]
                        wr.writerow([n, "CEK" if sev in ("ERROR", "WARNING") else "INFO", sev,
                                     "kasus %s" % f.get("case_id") if f.get("case_id") else "", r.title[:80],
                                     B._short(f["message"], 254),
                                     f["value"] if isinstance(f.get("value"), (int, float)) else "",
                                     f["threshold"] if isinstance(f.get("threshold"), (int, float)) else "",
                                     B._short(r.sumber, 160), f.get("dasar", ""), f["rule_id"], f.get("finding_id", ""),
                                     f.get("object_type", ""), str(f.get("object_id", ""))[:60],
                                     B._short(f.get("recommendation", ""), 200), f.get("profile_id", ""),
                                     f.get("rule_version", ""), f.get("review", "OPEN"), B._short(f.get("note", ""), 200), "", ""])
                loads.append((path, "Temuan non-spasial (BOM/KMZ/data) (%d)" % len(nogeo)))
            except OSError as e:
                feedback.reportError("Tabel temuan non-spasial tidak ditulis: %s" % e, fatalError=False)
        for r in results:
            by = {}
            for f in r.findings:
                g = f.get("geom")
                if not g:
                    continue
                by.setdefault((f["rule_id"], g[0]), []).append(f)
            for (rid, gk), lst in sorted(by.items()):
                lyr = QgsVectorLayer(("LineString" if gk == "line" else "Point") + "?crs=EPSG:4326" + FIELDS, rid, "memory")
                feats = []
                for f in lst:
                    n += 1
                    g = f["geom"]
                    q = QgsFeature(lyr.fields())
                    p0 = g[1] if gk == "point" else g[1][0]
                    sev = f["severity"]
                    q.setAttributes([n, "CEK" if sev in ("ERROR", "WARNING") else "INFO", sev, "kasus %s" % f.get("case_id") if f.get("case_id") else "",
                                     r.title[:80], B._short(f["message"], 254),
                                     float(f["value"]) if isinstance(f.get("value"), (int, float)) else None,
                                     float(f["threshold"]) if isinstance(f.get("threshold"), (int, float)) else None,
                                     B._short(r.sumber, 160), f.get("dasar", ""), rid, f.get("finding_id", ""), f.get("object_type", ""),
                                     str(f.get("object_id", ""))[:60], B._short(f.get("recommendation", ""), 200),
                                     f.get("profile_id", ""), f.get("rule_version", ""), f.get("review", "OPEN"),
                                     B._short(f.get("note", ""), 200), round(p0[0], 7), round(p0[1], 7)])
                    q.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(x, y) for x, y in g[1]]) if gk == "line"
                                  else QgsGeometry.fromPointXY(QgsPointXY(*g[1])))
                    feats.append(q)
                lyr.dataProvider().addFeatures(feats)
                sev = min((f["severity"] for f in lst), key=lambda s: Q.SEV_RANK.get(s, 9))
                fn = "%s_%s%s.shp" % ({"ERROR": "E", "WARNING": "W", "UNVERIFIED": "U"}.get(sev, "I"), rid,
                                      "_GARIS" if gk == "line" else "")
                path = os.path.join(out_dir, fn)
                try:
                    B.BuatInputDesain._write(lyr, path, "ESRI Shapefile", context)
                    try:
                        sl = QgsVectorLayer(path, rid, "ogr")
                        if sl.isValid() and B.style_qc_layer(sl):
                            sl.saveNamedStyle(os.path.splitext(path)[0] + ".qml")
                        del sl
                    except Exception as _e:
                        _log.note(_e)
                    loads.append((path, "%s %s (%d)" % (sev, rid, len(lst))))
                except Exception as e:
                    feedback.reportError("%s tidak ditulis: %s" % (fn, e), fatalError=False)
        return loads

    def _html(self, path, results, prof, meta, net):
        write_html(path, results, prof, meta)


def write_html(path, results, prof, meta):
    """Laporan QC_APD.html: satu kalimat keputusan, jalur aturan, lalu kartu per aturan yang menjelaskan
    apa yang dicek, kenapa penting, hasilnya, dan apa yang harus dilakukan untuk setiap temuan."""
    from . import report_ui as U
    from . import penjelasan as X
    counts = {}
    for r in results:
        for f in r.findings:
            counts[f["severity"]] = counts.get(f["severity"], 0) + 1
        if r.status == "UNVERIFIED" and not r.findings:
            counts["UNVERIFIED"] = counts.get("UNVERIFIED", 0) + 1
    order = sorted(range(len(results)), key=lambda k: (Q.SEV_RANK.get(results[k].status, 9), k))
    cards, items = [], []
    for k in order:
        r = results[k]
        ex = X.RULES.get(r.rule_id, {})
        anchor = "r-" + re.sub(r"[^a-z0-9]+", "-", r.rule_id.lower())
        items.append((anchor, X.SHORT.get(r.rule_id, r.title.split(":")[0][:14]), r.status))
        c = r.counts()
        if r.findings:
            sub = "%d temuan" % len(r.findings)
        elif r.status == "UNVERIFIED":
            sub = U.plain(r.unverified or "data belum lengkap")
        else:
            sub = "Lolos. Tidak ada temuan."
        inner = []
        if r.unverified and r.findings:
            inner.append("<div class='unvbox'><b>Sebagian belum bisa dicek.</b> %s</div>" % _E(U.plain(r.unverified)))
        elif r.unverified:
            inner.append("<div class='unvbox'><b>Kenapa belum bisa dicek?</b> %s. Lengkapi data ini lalu jalankan ulang "
                         "QC agar aturan ini benar-benar diuji.</div>" % _E(U.plain(r.unverified).rstrip(".")))
        st = [(kk, v) for kk, v in r.stats.items() if kk not in ("per_fdt", "tabel") and not isinstance(v, (list, dict))]
        notes = [n for n in r.notes if n]
        if st or notes:
            inner.append("<div class='stat'><ul>%s%s</ul></div>" % (
                "".join("<li><b>%s</b>: %s</li>" % (_E(str(kk).replace("_", " ").capitalize()), _E(str(v))) for kk, v in st),
                "".join("<li>%s</li>" % _E(n) for n in notes)))
        if r.rule_id == "MULTI_FDT" and r.stats.get("per_fdt"):
            inner.append("<div class='scroll'><table><tr><th>FDT</th><th>Status</th><th class='n'>FAT</th><th class='n'>HP</th>"
                         "<th class='n'>Premises ikon</th><th class='n'>Kapasitas</th><th class='n'>Splitter / maks</th></tr>%s"
                         "</table></div>" % "".join(
                             "<tr><td>%s</td><td>%s</td><td class='n'>%d</td><td class='n'>%s</td><td class='n'>%s</td>"
                             "<td class='n'>%s</td><td class='n'>%s / %s</td></tr>" % (
                                 _E(t["fdt"]), _E(t["status"]), t["fat"], t["hp"],
                                 t["premises_attr"] if t["premises_attr"] is not None else "-", t["kapasitas"], t["splitter"],
                                 t["splitter_maks"]) for t in r.stats["per_fdt"]))
        if r.rule_id == "QC02_PREMISES_SPLITTER" and isinstance(r.stats.get("fdt"), list) and r.stats["fdt"]:
            inner.append("<div class='scroll'><table><tr><th>FDT</th><th class='n'>Premises FDT</th><th class='n'>Jumlah premises FAT"
                         "</th><th>Splitter FDT</th><th class='n'>Output FDT</th><th class='n'>Input FAT dibutuhkan</th></tr>%s"
                         "</table></div>" % "".join("<tr>%s</tr>" % "".join(
                             "<td%s>%s</td>" % ("" if i in (0, 3) else " class='n'", _E("%g" % x if isinstance(x, float) else str(x)))
                             for i, x in enumerate(t)) for t in r.stats["fdt"] if isinstance(t, (list, tuple))))
        if r.rule_id == "BOM" and r.stats.get("tabel"):
            inner.append("<div class='scroll'><table><tr><th>Kategori</th><th>Satuan</th><th class='n'>Desain</th>"
                         "<th class='n'>Desain + slack</th><th class='n'>BOM</th><th class='n'>Selisih</th><th class='n'>%%</th>"
                         "<th>Status</th></tr>%s</table></div>" % "".join(
                             "<tr>%s</tr>" % "".join("<td>%s</td>" % _E(str(x)) for x in t) for t in r.stats["tabel"]))
        if r.findings:
            lis = []
            fs = sorted(r.findings, key=lambda f: Q.SEV_RANK.get(f["severity"], 9))
            for f in fs[:80]:
                j, a, fx = X.finding_text(f)
                g = f.get("geom")
                ll = None
                if g:
                    ll = g[1] if g[0] == "point" else g[1][0]
                tech = "<code>%s</code> %s%s%s%s" % (
                    _E(f["rule_id"]), _E(f.get("message", "")),
                    (" | saran sistem: %s" % _E(f["recommendation"])) if f.get("recommendation") else "",
                    (" | lingkup %s" % _E(f["scope"])) if f.get("scope") else "",
                    (" | ID temuan %s" % _E(f.get("finding_id", ""))) if f.get("finding_id") else "")
                lis.append(U.finding_li(f["severity"], j, f.get("object_id") or "", a, fx, tech, ll))
            more = ("<li class='more'>+%d temuan lain. Daftar lengkap ada di QC_APD_TEMUAN.csv dan panel Navigator QC.</li>"
                    % (len(fs) - 80)) if len(fs) > 80 else ""
            inner.append("<ul class='finds'>%s%s</ul>" % ("".join(lis), more))
        dasar = Q.DASAR_LABEL.get(r.dasar, r.dasar or "")
        if dasar or r.sumber:
            inner.append("<p class='src'>Dasar aturan: %s%s</p>" % (_E(dasar), (": " + _E(r.sumber)) if r.sumber else ""))
        cards.append(U.rule_card(anchor, r.status, ex.get("judul") or r.title, sub, c, ex.get("cek", ""), ex.get("alasan", ""),
                                 ex.get("tindakan", ""), "".join(inner), is_open=r.status in ("ERROR", "WARNING")))
    prm = "".join("<tr><td><code>%s</code></td><td class='n'>%s %s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
        _E(k), _E(str(e.get("v"))), _E(e.get("unit") or ""), _E(Q.DASAR_LABEL.get(e.get("dasar"), "")), _E(e.get("sumber", "")),
        U.chip("PASS", "disahkan") if e.get("status") == "APPROVED" else U.chip("UNVERIFIED", "parameter rekayasa"))
        for k, e in prof["params"].items() if isinstance(e, dict) and k != "cable_colors")
    src = "".join("<tr><td>%s</td><td><code>%s</code></td></tr>" % (_E(k), _E(v)) for k, v in sorted(meta.get("sumber_data", {}).items()))
    body = (U.howto() + "".join(cards) +
            "<section class='block'><h2>File hasil QC</h2><p class='lead'>Lokasi setiap temuan ada di folder <code>QC_APD</code> "
            "(satu layer per aturan). Di QGIS, buka panel <b>Navigator QC</b>, klik temuan untuk langsung ke lokasinya, lalu beri "
            "status review. Tabel lengkap: <code>QC_APD_TEMUAN.csv</code> dan <code>QC_APD.json</code>.</p>"
            "<div class='scroll'><table><tr><th>Jenis data</th><th>Dibaca dari</th></tr>%s</table></div></section>"
            "<section class='block'><details class='plain'><summary>Profil standar %s: dasar setiap angka</summary>"
            "<p class='lead'>Setiap batas di laporan ini berasal dari profil di bawah. Status <i>parameter rekayasa</i> berarti "
            "angka masih perlu dikalibrasi dengan data lapangan.</p><div class='scroll'><table><tr><th>Parameter</th>"
            "<th class='n'>Nilai</th><th>Dasar</th><th>Sumber</th><th>Status</th></tr>%s</table></div></details></section>" % (
                src or "<tr><td colspan='2'>-</td></tr>", _E(prof["profile_id"]), prm))
    ov = Q.overall(results)
    html_ = U.page("QC APD %s" % meta["cluster"], "QC APD Pasca-Desain", meta["cluster"].replace("_", " "),
                   U.verdict_sentence(counts),
                   [("Status keseluruhan", U.SEV_WORD.get(ov, ov)), ("Profil", prof["profile_id"]),
                    ("Versi aturan", prof.get("rule_version", "")), ("Status FDT", meta.get("status_fdt", "")),
                    ("Dibuat", meta["dibuat"].replace("T", " ")), ("Alat", meta["produk"])],
                   counts, items, body,
                   "%s. &copy; 2026 Joseph Edward Timothy Siahaan, GPL-2.0-or-later. Hasil QC adalah alat bantu; keputusan desain "
                   "dan pengecualian tetap pada desainer dan reviewer." % _E(meta["produk"]))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html_)

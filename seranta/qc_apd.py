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



def input_manifest(main, kn, apd, autodesign, lay, feeder_path, dist_path, bom, paket, obst_name, sdproj, prof):
    """Status kelengkapan setiap masukan (audit 5.1 tahap 1): apa yang dibaca, berapa objek, dan aturan mana yang
    belum bisa diuji bila masukan itu tidak ada. Baris: (masukan, file, status, jumlah, dampak)."""
    src = (paket or {}).get("_src", {})
    pk = paket or {}
    rows = []

    def add(label, path, n, impact, used=None):
        ok = bool(path) if used is None else used
        rows.append({"masukan": label, "file": os.path.basename(str(path)) if path else "",
                     "status": "DIPAKAI" if ok else "TIDAK ADA", "jumlah": n if ok else 0,
                     "dampak": "" if ok else impact})
    for kind, lab in (("nodes", "Ekspor desain: node FDT/FAT"), ("endpoints", "Ekspor desain: homepass"),
                      ("cables", "Ekspor desain: kabel"), ("closures", "Ekspor desain: closure"),
                      ("polys", "Ekspor desain: coverage (Voronoi)")):
        f_ = lay.get(kind, "") or main.sources.get(kind, "")
        add(lab if lay.get(kind) or not f_ else lab.replace("Ekspor desain", "KMZ APD"), f_,
            len(getattr(main, kind, [])), "aturan yang membutuhkan data ini memakai data yang ada saja")
    add("KMZ APD final", apd, (len(kn.nodes) + len(kn.endpoints) + len(kn.cables) + len(kn.poles)) if kn else 0,
        "QC-01..07 dan aturan KMZ tidak bisa dijalankan")
    add("Tiang", main.sources.get("poles", ""), len(main.poles), "aturan tiang, bentang, perangkat di tiang belum bisa dicek")
    add("Paket Feeder", feeder_path or ("folder Feeder di KMZ APD" if any("FEEDER" in (n.get("packages") or ()) for n in main.nodes) else ""),
        sum(1 for o in list(main.nodes) + list(main.cables) + list(main.closures)
            if "FEEDER" in (o.get("packages") or {o.get("scope")})) if not feeder_path else "",
        "FDT di dua paket belum bisa dicek")
    add("Paket Distribution", dist_path or ("folder Distribution di KMZ APD" if kn is not None else "data utama"),
        sum(1 for o in list(main.nodes) + list(main.cables) + list(main.closures)
            if "DISTRIBUTION" in (o.get("packages") or {o.get("scope")})) if not dist_path else "", "", used=True)
    add("BOM / Daily", bom, 1, "rekonsiliasi BOM belum bisa dicek")
    add("Tabel kode FDT-FAT", src.get("codes"), len(pk.get("codes") or {}), "QC-02 (sebagian) dan QC-03 belum bisa dicek")
    add("Splice Plan", src.get("splice"), len(pk.get("splice") or {}), "cek splitter dan fiber/tube Splice Plan belum bisa dicek")
    add("Rekap kode FDT (BAKP-Attributes)", src.get("master"), len(pk.get("master") or ()),
        "QC-01: kode FDT baru terdaftar & unik lintas proyek belum bisa dicek")
    add("Tiang existing referensi kota", src.get("ref"), len(pk.get("ref_pts") or ()), "QC-04 belum bisa dicek")
    add("Jaringan existing (Design Lite)", src.get("designlite"), len(pk.get("dl_codes") or {}),
        "QC-01: bentrok kode dengan FDT existing & kandidat grouping belum bisa dicek")
    add("Layer rel/tol/hambatan", obst_name, 1, "aturan crossing belum bisa dicek")
    add("Config desain otomatis (.sdproj)", sdproj, 1, "angka dari profil %s dipakai apa adanya" % prof.get("profile_id", ""))
    return rows

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
            feedback.pushInfo("Ekspor desain %-9s: %s" % (kind, os.path.basename(pth)))
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
                "status_fdt": status, "sumber_data": main.sources,
                "kelengkapan": input_manifest(main, kn, apd, autodesign, lay, fp, dp, bom, paket,
                                              obst.name() if obst is not None else "", sd, prof),
                "kandidat_grouping": next((r.stats.get("grouping") for r in results if r.rule_id == "QC01_KODE_FDT"), []) or []}
        Q.write_json(os.path.join(out_dir, "QC_APD.json"), results, prof, meta)
        xlsx = os.path.join(out_dir, "QC_APD_TEMUAN.xlsx")
        try:
            write_xlsx(xlsx, results, prof, meta)
        except OSError as e:          # mis. masih terbuka di aplikasi spreadsheet
            alt = os.path.join(out_dir, "QC_APD_TEMUAN_%s.xlsx" % _dt.datetime.now().strftime("%H%M%S"))
            feedback.reportError("QC_APD_TEMUAN.xlsx sedang dibuka aplikasi lain (%s); daftar kerja ditulis ke %s"
                                 % (e, os.path.basename(alt)), fatalError=False)
            write_xlsx(alt, results, prof, meta)
        html = os.path.join(out_dir, "QC_APD.html")
        try:
            feedback.setProgressText("Gambar peta temuan dan laporan Word")
            meta["word"], meta["snaps"] = write_word(os.path.join(out_dir, "QC_APD_LAPORAN.docx"), results, prof, meta, main,
                                                     out_dir)
            feedback.pushInfo("Laporan Word: %s (gambar peta %d)" % (meta["word"], len(meta["snaps"])))
        except Exception as e:
            feedback.reportError("Gambar temuan / laporan Word tidak dibuat: %s" % e, fatalError=False)
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
        pk = {"kmz": kn, "autodesign": autodesign_net,
              "_src": {"codes": codes_p, "splice": splice_p, "master": master_p, "ref": ref_p}}
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
                dl_files = list(B.ref_files(ref_dir, "designlite"))
                for fp in dl_files:
                    for e in B.cached_read("designlite", fp, ext, B.read_design_lite, feedback):
                        if e.get("kind", "fdt") == "fdt":
                            dl.setdefault(str(e["code"]).strip().upper(), []).append((e["x"], e["y"]))
                pk["dl_codes"] = dl
                pk["_src"]["designlite"] = ", ".join(os.path.basename(x) for x in dl_files) or ref_dir
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
        # status review yang diisi reviewer di daftar kerja XLSX (lebih baru dari CSV)
        xp = os.path.join(out_dir, "QC_APD_TEMUAN.xlsx")
        if os.path.exists(xp):
            old.update(read_xlsx_reviews(xp))
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
                  "&field=lon:double(12,7)&field=lat:double(12,7)&field=lingkup:string(14)&field=bukti:string(254)"
                  "&field=sumber:string(80)")
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
                                     f.get("rule_version", ""), f.get("review", "OPEN"), B._short(f.get("note", ""), 200), "", "",
                                     f.get("scope", ""), B._short(f.get("evidence", ""), 254), B._short(f.get("source_file", ""), 80)])
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
                                     B._short(f.get("note", ""), 200), round(p0[0], 7), round(p0[1], 7),
                                     f.get("scope", ""), B._short(f.get("evidence", ""), 254), B._short(f.get("source_file", ""), 80)])
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


XLSX_COLS = [("No", 6), ("ID temuan", 20), ("Aturan", 22), ("Tingkat", 13), ("Judul sederhana", 30), ("Objek", 26),
             ("Jenis objek", 12), ("Lingkup", 13), ("Nilai", 10), ("Batas", 10), ("Satuan", 8), ("Arti temuan", 46),
             ("Yang perlu dilakukan", 46), ("Bukti", 40), ("File sumber", 28), ("Pesan teknis", 46), ("Lon", 12),
             ("Lat", 12), ("Peta", 14), ("Status review", 20), ("Catatan reviewer", 36), ("Versi aturan", 12), ("Profil", 16)]


def write_xlsx(path, results, prof, meta):
    """QC_APD_TEMUAN.xlsx: daftar kerja reviewer (audit 5.1 tahap 4). Sheet Ringkasan, Temuan (status review dengan
    pilihan baku, terbaca kembali saat QC diulang), Kelengkapan input, dan Grouping FDT."""
    from . import xlsx_writer as XL
    from . import penjelasan as X
    from . import report_ui as U
    sev_word = U.SEV_WORD
    ring = XL.Sheet("Ringkasan", ["Aturan", "Judul", "Status", "Wajib diperbaiki", "Perlu ditinjau", "Belum bisa dicek", "Catatan",
                                  "Yang dicek", "Alasan belum bisa dicek", "Dasar aturan"], [24, 40, 16, 10, 10, 10, 10, 50, 44, 50])
    for r in results:
        c = r.counts()
        ex = X.RULES.get(r.rule_id, {})
        ring.add([r.rule_id, r.title, sev_word.get(r.status, r.status), c.get("ERROR", 0), c.get("WARNING", 0),
                  c.get("UNVERIFIED", 0) + (1 if r.status == "UNVERIFIED" and not r.findings else 0), c.get("INFO", 0),
                  ex.get("cek", ""), r.unverified or "", (Q.DASAR_LABEL.get(r.dasar, r.dasar or "") + ": " + (r.sumber or "")).strip(": ")],
                 [2, 2, XL.SEVERITY_STYLE.get(r.status, 2), 0, 0, 0, 0, 2, 2, 2])
    tem = XL.Sheet("Temuan", [h for h, _w in XLSX_COLS], [w for _h, w in XLSX_COLS])
    n = 0
    for r in results:
        for f in sorted(r.findings, key=lambda f: Q.SEV_RANK.get(f["severity"], 9)):
            n += 1
            j, a, fx = X.finding_text(f)
            g = f.get("geom")
            lon = lat = ""
            if g:
                lon, lat = g[1] if g[0] == "point" else g[1][0]
            link = ("=", 'HYPERLINK("https://www.openstreetmap.org/?mlat=%.7f&mlon=%.7f#map=19/%.7f/%.7f","lihat peta")'
                    % (lat, lon, lat, lon), "lihat peta") if g else ""
            num = (lambda v: float(v) if isinstance(v, (int, float)) else (v if v is not None else ""))
            tem.add([n, f.get("finding_id", ""), f["rule_id"], sev_word.get(f["severity"], f["severity"]), j, f.get("object_id", ""),
                     f.get("object_type", ""), f.get("scope", ""), num(f.get("value")), num(f.get("threshold")), f.get("unit", ""),
                     a, fx, f.get("evidence", ""), f.get("source_file", ""), f.get("message", ""),
                     round(lon, 7) if lon != "" else "", round(lat, 7) if lat != "" else "", link,
                     f.get("review", "OPEN"), f.get("note", ""), f.get("rule_version", ""), f.get("profile_id", "")],
                    [0, 0, 0, XL.SEVERITY_STYLE.get(f["severity"], 0), 2, 0, 0, 0, None, None, 0, 2, 2, 2, 0, 2, 0, 0, 4, 0, 2, 0, 0])
    tem.choices(19, list(Q.REVIEW_STATES))
    kel = XL.Sheet("Kelengkapan input", ["Masukan", "Status", "File", "Jumlah objek", "Bila tidak ada"], [36, 12, 46, 12, 70])
    for k in meta.get("kelengkapan") or []:
        kel.add([k["masukan"], k["status"], k["file"], k["jumlah"] or "", k["dampak"]],
                [2, 9 if k["status"] == "DIPAKAI" else (7 if k["dampak"] else 8), 0, 0, 2])
    sheets = [ring, tem, kel]
    gr = meta.get("kandidat_grouping") or []
    if gr:
        gs = XL.Sheet("Grouping FDT", ["FDT", "Status", "Kelompok kode", "Kelompok sekitar", "FDT sekitar", "FDT existing terdekat",
                                       "Kode kandidat", "Hasil"], [22, 8, 16, 16, 10, 30, 18, 30])
        for x in gr:
            gs.add([x["fdt"], x["status_fdt"], x["kelompok_kode"], x["kelompok_sekitar"], x["jumlah_fdt_sekitar"], x["fdt_terdekat"],
                    x["kode_kandidat"], x["hasil"]], [0, 0, 0, 0, 0, 0, 0, 9 if x["hasil"].startswith("SESUAI") else (6 if x["hasil"].startswith("BEDA") else 8)])
        sheets.append(gs)
    return XL.write(path, sheets, "QC APD %s" % meta.get("cluster", ""), "Seranta")


def read_xlsx_reviews(path):
    """Status review yang diisi reviewer di QC_APD_TEMUAN.xlsx: {review_key: (status, catatan)}."""
    out = {}
    try:
        sheets = dict(B.read_xlsx(path, want=lambda n: n == "Temuan"))
    except Exception as e:
        _log.note(e)
        return out
    rows = sheets.get("Temuan") or []
    if not rows:
        return out
    h = rows[0]

    def ix(name):
        return h.index(name) if name in h else None
    i_r, i_o, i_lon, i_lat, i_rv, i_nt = ix("Aturan"), ix("Objek"), ix("Lon"), ix("Lat"), ix("Status review"), ix("Catatan reviewer")
    if None in (i_r, i_rv):
        return out
    for row in rows[1:]:
        g = (lambda k: row[k] if k is not None and k < len(row) else "")
        rv = g(i_rv).strip().upper()
        if not rv or rv == "OPEN":
            continue
        try:
            geom = ("point", (float(g(i_lon)), float(g(i_lat)))) if g(i_lon) and g(i_lat) else None
        except ValueError:
            geom = None
        f = {"rule_id": g(i_r), "object_id": g(i_o), "geom": geom}
        out[Q.review_key(f)] = (rv, g(i_nt))
    return out


def scene_of(net):
    """Objek peta dari jaringan QC (kabel, tiang, perangkat, homepass, batas) untuk gambar temuan."""
    from . import snapshot as S
    sc = S.Scene()
    for c in getattr(net, "cables", []) or []:
        k = c.get("kind") or "dist"
        kind = {"drop": "drop", "pancingan": "pancingan", "feeder": "feeder"}.get(k, "cable_new" if c.get("status") != "EXISTING"
                                                                                  else "cable")
        sc.add_line(c.get("pts") or [], kind)
    for pl in getattr(net, "polys", []) or []:
        try:
            sc.add_poly(pl["poly"][0], "funnel")
        except Exception as _e:
            _log.note(_e)
    for e in getattr(net, "endpoints", []) or []:
        sc.add_point(e["x"], e["y"], "hp", "")
    for p in getattr(net, "poles", []) or []:
        sc.add_point(p["x"], p["y"], "pole_ext" if p.get("status") == "EXISTING" else "pole_new", p.get("name") or "")
    for c in getattr(net, "closures", []) or []:
        sc.add_point(c["x"], c["y"], "closure", c.get("name") or "")
    for n in getattr(net, "nodes", []) or []:
        sc.add_point(n["x"], n["y"], "fdt" if n.get("kind") == "FDT" else "fat", n.get("name") or n.get("label") or "")
    return sc


def _midpoint(line):
    """Titik tengah polyline menurut panjang (derajat cukup untuk jarak pendek)."""
    if len(line) < 2:
        return line[0]
    seg = [((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5 for a, b in zip(line, line[1:])]
    half, acc = sum(seg) / 2.0, 0.0
    for (a, b), d in zip(zip(line, line[1:]), seg):
        if acc + d >= half and d > 0:
            t = (half - acc) / d
            return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
        acc += d
    return line[-1]


def write_word(path, results, prof, meta, net, out_dir, max_img=80):
    """Gambar peta per temuan (QC_GAMBAR) + laporan Word. Kembali (nama file Word, {finding_id: data URI})."""
    from . import snapshot as S
    from . import docx_writer as D
    from . import penjelasan as X
    sc = scene_of(net)
    fs = sorted(Q.findings_of(results), key=lambda f: Q.SEV_RANK.get(f["severity"], 9))
    recs = []
    for f in fs:
        g = f.get("geom")
        if g and g[0] == "point":
            lon, lat, line = g[1][0], g[1][1], None
        elif g and g[0] == "line" and g[1]:
            line = list(g[1])
            lon, lat = _midpoint(line)
        else:
            lon = lat = line = None
        j, a, fx = X.finding_text(f)
        recs.append({"fid": f.get("finding_id") or f["rule_id"], "sev": f["severity"], "title": j, "obj": f.get("object_id") or "",
                     "arti": a, "fix": fx, "value": f.get("value"), "limit": f.get("threshold"), "unit": f.get("unit") or "",
                     "lat": lat, "lon": lon, "line": line, "dasar": f.get("dasar") or "", "source": f.get("source_file") or "",
                     "rule": f["rule_id"]})
    shots = [dict(r, title="%s: %s" % (r["title"], r["obj"] or r["arti"])) for r in recs if r["lat"] is not None
             and r["sev"] != "PASS"][:max_img]
    imgs = S.render_many(sc, shots, out_dir=os.path.join(out_dir, "QC_GAMBAR"), max_n=max_img)
    rows = []
    for r in results:
        c = r.counts()
        rows.append(("%s" % (X.RULES.get(r.rule_id, {}).get("judul") or r.title), r.status, sum(c.values()),
                     (r.unverified or "")[:160] if r.status == "UNVERIFIED" else (", ".join("%s %d" % kv for kv in sorted(c.items())) or (
                         ("catatan: " + next(n for n in r.notes if n))[:160] if [n for n in r.notes if n] else ""))))
    rows.sort(key=lambda t: Q.SEV_RANK.get(t[1], 9))
    D.qc_report(path, "Laporan QC APD - %s" % str(meta.get("cluster", "")).replace("_", " "),
                "QC paket desain APD pasca-desain - %s" % meta.get("produk", ""),
                [("Cluster", meta.get("cluster", "")), ("Status FDT", meta.get("status_fdt", "")),
                 ("Profil standar", "%s (versi aturan %s)" % (prof.get("profile_id"), prof.get("rule_version"))),
                 ("Dibuat", str(meta.get("dibuat", "")).replace("T", " ")),
                 ("Jumlah temuan", "%d (gambar peta: %d)" % (len(recs), len(imgs))),
                 ("Berkas pendukung", "QC_APD.html, QC_APD_TEMUAN.xlsx, folder QC_GAMBAR")],
                rows, [r for r in recs if r["sev"] != "PASS"], {k: v[0] for k, v in imgs.items()},
                footer="%s - hasil QC adalah alat bantu; keputusan tetap pada desainer dan reviewer" % meta.get("produk", ""))
    return os.path.basename(path), {k: S.data_uri(v[0]) for k, v in imgs.items()}


def write_html(path, results, prof, meta):
    """Laporan QC_APD.html: satu kalimat keputusan, jalur aturan, lalu kartu per aturan yang menjelaskan
    apa yang dicek, kenapa penting, hasilnya, dan apa yang harus dilakukan untuk setiap temuan."""
    from . import report_ui as U
    from . import penjelasan as X
    U.reset_ids()
    snaps = meta.get("snaps") or {}
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
        elif [n for n in r.notes if n]:
            # lolos, tetapi ada keterbatasan cakupan yang harus diketahui pembaca (bukan lolos penuh)
            sub = "Lolos dengan catatan: " + U.plain(next(n for n in r.notes if n))[:140]
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
        if r.rule_id == "QC01_KODE_FDT" and r.stats.get("grouping"):
            inner.append("<p class='lead'><b>Kandidat grouping FDT</b>: kelompok kode area FDT existing dalam radius COLO, "
                         "FDT existing terdekat, dan kode kandidat berikutnya di kelompok itu (dicek ulang dengan rekap kode).</p>"
                         "<div class='scroll'><table><tr><th>FDT</th><th>Status</th><th>Kelompok kode</th><th>Kelompok sekitar</th>"
                         "<th class='n'>FDT sekitar</th><th>FDT existing terdekat</th><th>Kode kandidat</th><th>Hasil</th></tr>%s"
                         "</table></div>" % "".join(
                             "<tr><td><b>%s</b></td><td>%s</td><td>%s</td><td>%s</td><td class='n'>%d</td><td>%s</td><td>%s</td>"
                             "<td>%s</td></tr>" % (_E(g["fdt"]), _E(g["status_fdt"]), _E(g["kelompok_kode"] or "-"),
                                                   _E(g["kelompok_sekitar"] or "-"), g["jumlah_fdt_sekitar"], _E(g["fdt_terdekat"] or "-"),
                                                   _E(g["kode_kandidat"] or "-"),
                                                   U.chip("PASS" if g["hasil"].startswith("SESUAI") else "WARNING" if g["hasil"].startswith("BEDA")
                                                          else "UNVERIFIED", g["hasil"].capitalize()))
                             for g in r.stats["grouping"]))
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
                if f.get("evidence") or f.get("source_file"):
                    tech += "<br>%s%s" % (("Bukti: %s. " % _E(f["evidence"])) if f.get("evidence") else "",
                                          ("Sumber: <code>%s</code>" % _E(f["source_file"])) if f.get("source_file") else "")
                fid = f.get("finding_id") or None
                lis.append(U.finding_li(f["severity"], j, f.get("object_id") or "", a, fx, tech, ll, fid=fid, snap=snaps.get(fid)))
            more = ("<li class='more'>+%d temuan lain. Daftar lengkap ada di QC_APD_TEMUAN.csv dan panel Navigator QC.</li>"
                    % (len(fs) - 80)) if len(fs) > 80 else ""
            inner.append("<ul class='finds'>%s%s</ul>" % ("".join(lis), more))
        dasar = Q.DASAR_LABEL.get(r.dasar, r.dasar or "")
        if dasar or r.sumber:
            inner.append("<p class='src'>Dasar aturan: %s%s</p>" % (_E(dasar), (": " + _E(r.sumber)) if r.sumber else ""))
        cards.append(U.rule_card(anchor, r.status, ex.get("judul") or r.title, sub, c, ex.get("cek", ""), ex.get("alasan", ""),
                                 ex.get("tindakan", ""), "".join(inner),
                                 is_open=r.status in ("ERROR", "WARNING") or bool(r.stats.get("grouping"))))
    prm = "".join("<tr><td><code>%s</code></td><td class='n'>%s %s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
        _E(k), _E(str(e.get("v"))), _E(e.get("unit") or ""), _E(Q.DASAR_LABEL.get(e.get("dasar"), "")), _E(e.get("sumber", "")),
        U.chip("PASS", "disahkan") if e.get("status") == "APPROVED" else U.chip("UNVERIFIED", "parameter rekayasa"))
        for k, e in prof["params"].items() if isinstance(e, dict) and k != "cable_colors")
    src = "".join("<tr><td>%s</td><td><code>%s</code></td></tr>" % (_E(k), _E(v)) for k, v in sorted(meta.get("sumber_data", {}).items()))
    kl = meta.get("kelengkapan") or []
    n_miss = sum(1 for k in kl if k["status"] != "DIPAKAI" and k["dampak"])
    kel_html = ("<section class='block' id='kelengkapan'><h2>Kelengkapan data masukan</h2><p class='lead'>%s</p>"
                "<div class='scroll'><table><tr><th>Masukan</th><th>Status</th><th>File</th><th class='n'>Objek</th>"
                "<th>Bila tidak ada</th></tr>%s</table></div></section>" % (
                    ("Semua masukan yang dibutuhkan tersedia." if not n_miss else
                     "%d masukan belum tersedia. Aturan yang membutuhkannya berstatus <i>Belum bisa dicek</i>; lengkapi lalu "
                     "jalankan ulang QC." % n_miss),
                    "".join("<tr><td>%s</td><td>%s</td><td>%s</td><td class='n'>%s</td><td>%s</td></tr>" % (
                        _E(k["masukan"]), U.chip("PASS", "dipakai") if k["status"] == "DIPAKAI" else
                        (U.chip("UNVERIFIED", "tidak ada") if k["dampak"] else U.chip("INFO", "opsional")),
                        ("<code>%s</code>" % _E(k["file"])) if k["file"] else "-", k["jumlah"] or "-", _E(k["dampak"] or "-"))
                        for k in kl))) if kl else ""
    body = (U.howto() + kel_html + "".join(cards) +
            "<section class='block'><h2>File hasil QC</h2><p class='lead'>Lokasi setiap temuan ada di folder <code>QC_APD</code> "
            "(satu layer per aturan). Di QGIS, buka panel <b>Navigator QC</b>, klik temuan untuk langsung ke lokasinya, lalu beri "
            "status review. Tabel lengkap: <code>QC_APD_TEMUAN.xlsx</code> (daftar kerja reviewer: isi kolom <i>Status review</i> dan <i>Catatan reviewer</i>, "
            "status itu dibaca kembali saat QC diulang), <code>QC_APD_TEMUAN.csv</code> dan <code>QC_APD.json</code>.</p>"
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
                   "dan pengecualian tetap pada desainer dan reviewer." % _E(meta["produk"]),
                   run_key=str(meta.get("cluster", "")), word_href=meta.get("word"))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html_)

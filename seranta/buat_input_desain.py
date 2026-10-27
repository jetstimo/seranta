# -*- coding: utf-8 -*-
"""
Seranta - FTTH Design Assistant - tool 1: prepare desain otomatis input + Strand QC
====================================================================
Copyright (C) 2026 Joseph Edward Timothy Siahaan <edwardtimoo@gmail.com>

This program is free software; you can redistribute it and/or modify it under the terms of the GNU General
Public License as published by the Free Software Foundation; either version 2 of the License, or (at your
option) any later version. See LICENSE.

QGIS Processing algorithm (QGIS 3.22 LTR .. 4.x, Qt5/Qt6) that automates the manual SOP for building
desain otomatis input and the Strand review standard:

  HPDB (XLSX/CSV)  ->  INPUT_<CODE>/<CODE>_HP.shp     (IDs H00001.., EPSG:4326)
  cluster KMZ       ->  <CODE>_POLE.kmz                 (POLE > NP > T6/T7/T9 and POLE > EP, tidy names)
                    ->  <CODE>_ROADS.shp                (snapped to poles, exploded per segment)
  + <CODE>_RINGKASAN_QC.html (one-page summary), <CODE>_LAPORAN_INPUT.txt, <CODE>_QC_TEMUAN.shp/.kmz,
    <CODE>_FUNNEL_SEKITAR.gpkg, <CODE>_COLO.gpkg
  + checks: HP-pole distance, pole spans, RFS/Funnel boundary, HPDB vs KMZ, kelurahan/kecamatan vs
    FINDIM, design status, colocation to existing FDT, BAKP (permit) reminder
  + batch mode: choose a parent folder containing many clusters.
"""
__version__ = "3.5.6"
__author__ = "Joseph Edward Timothy Siahaan"
__product__ = "Seranta - FTTH Design Assistant"
HOMEPAGE = "https://github.com/jetstimo/seranta"

try:
    from . import _log
except ImportError:  # dijalankan sebagai modul lepas (uji unit)
    import _log
import os
import re
from collections import Counter

from osgeo import gdal, ogr
from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
    QgsCoordinateReferenceSystem, QgsDistanceArea, QgsFeature, QgsField,
    QgsFields, QgsGeometry, QgsPointXY, QgsProcessingAlgorithm,
    QgsProcessingException, QgsProcessingParameterBoolean,
    QgsProcessingParameterFile,
    QgsProcessingParameterNumber, QgsProcessingUtils, QgsProject,
    QgsProcessingParameterEnum, QgsProcessingParameterDefinition, QgsProcessingContext,
    QgsProcessingLayerPostProcessorInterface,
    QgsSettings, QgsSpatialIndex, QgsVectorFileWriter, QgsVectorLayer, QgsWkbTypes,
)
import processing
try:
    from . import bakp as _bakp
    from . import qc_core as _qc
    from . import report_html as _report_html
except ImportError:          # dijalankan sebagai skrip tunggal
    import bakp as _bakp
    import qc_core as _qc
    import report_html as _report_html

# Kompatibilitas: QGIS 3.36+ (termasuk 3.40 Bratislava) memindahkan enum ke kelas Qgis.
try:
    from qgis.core import Qgis
    FILE_BEHAVIOR = Qgis.ProcessingFileParameterBehavior.File
    FOLDER_BEHAVIOR = Qgis.ProcessingFileParameterBehavior.Folder
    NUM_DOUBLE = Qgis.ProcessingNumberParameterType.Double
    NUM_INT = Qgis.ProcessingNumberParameterType.Integer
except AttributeError:  # QGIS 3.22 - 3.34 (enum lama; dibaca lewat getattr agar kode tetap lolos cek Qt6)
    FILE_BEHAVIOR = getattr(QgsProcessingParameterFile, "File")
    FOLDER_BEHAVIOR = getattr(QgsProcessingParameterFile, "Folder")
    NUM_DOUBLE = getattr(QgsProcessingParameterNumber, "Double")
    NUM_INT = getattr(QgsProcessingParameterNumber, "Integer")
try:
    ADVANCED_FLAG = Qgis.ProcessingParameterFlag.Advanced
except AttributeError:  # QGIS < 3.36
    ADVANCED_FLAG = getattr(QgsProcessingParameterDefinition, "Flag" + "Advanced")

# Tipe kolom teks: QGIS 3.38+ dan QGIS 4 (Qt6) memakai QMetaType; versi lama memakai QVariant.
try:
    from qgis.PyQt.QtCore import QMetaType
    FIELD_STRING = QMetaType.Type.QString
    QgsField("x", FIELD_STRING)
except Exception:
    from qgis.PyQt.QtCore import QVariant
    FIELD_STRING = QVariant.String


def _enum(*cands):
    """Ambil enum pertama yang tersedia (nama enum berubah di QGIS 4)."""
    ns = globals()
    for c in cands:
        parts = c.split(".")
        obj = ns.get(parts[0])
        for p_ in parts[1:]:
            obj = getattr(obj, p_, None) if obj is not None else None
        if obj is not None:
            return obj
    return None


WRITER_OK = _enum("QgsVectorFileWriter.WriterError.NoError", "QgsVectorFileWriter.NoError")
GEOM_POLYGON = _enum("Qgis.GeometryType.Polygon", "QgsWkbTypes.PolygonGeometry")
OVERWRITE_LAYER = _enum("QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer",
                        "QgsVectorFileWriter.CreateOrOverwriteLayer")


# ---------- Identitas & integritas (jejak pencipta di setiap laporan) ----------
def integrity_status():
    """'ASLI' bila isi file sama dengan sidik jari rilis (integrity.json), 'DIMODIFIKASI' bila berbeda."""
    import hashlib
    import json
    here = os.path.dirname(os.path.abspath(__file__))
    meta = os.path.join(here, "integrity.json")
    if not os.path.exists(meta):
        return "paket rilis (keaslian dijamin repositori plugin QGIS)"
    try:
        with open(meta, encoding="utf-8") as fh:
            exp = json.load(fh)
        bad = []
        for fn, h in exp.items():
            if not fn.endswith(".py"):
                continue
            with open(os.path.join(here, fn), "rb") as fh:
                if hashlib.sha256(fh.read().replace(b"\r\n", b"\n")).hexdigest() != h:
                    bad.append(fn)
        return "ASLI" if not bad else "DIMODIFIKASI (%s)" % ", ".join(bad)
    except Exception as e:
        return "tidak diverifikasi (%s)" % e


# ---------- Pembaca KMZ/KML tanpa GDAL: membaca struktur folder lengkap ----------
import zipfile
try:  # defusedxml bila terpasang; bila tidak, ElementTree standar (expat >= 2.4.1 menolak entity expansion / billion laughs,
    # entity eksternal tidak pernah diunduh). Data yang dibaca: KMZ/XLSX/.sdproj milik pengguna sendiri.
    import defusedxml.ElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET  # nosec B405

# Nama folder dicocokkan per kata, tidak peka huruf besar/kecil:
#   tiang : POLE, pole, Poles, TIANG, NP, EP (subfolder di dalamnya ikut, mis. T6, 7M)
#   jalur : ROUTE CABLE, route cable, CABLE, Cable, ROUTE, ROADS, roads, KABEL, JALUR
POLE_RX = re.compile(r"\b(poles?|tiang|np|ep)\b", re.IGNORECASE)
SKIP_RX = re.compile(r"\b(hp|homepass|home ?pass|evid[ae]n[cs]e|boundary|bondary)\b", re.IGNORECASE)
# folder bukti foto lapangan (juga salah ketik 'EVIDANCE' yang ditemui di KMZ vendor) - bukan homepass
EVID_RX = re.compile(r"evid[ae]n[cs]e|evident|foto|photo|dokumentasi", re.IGNORECASE)
# folder titik HP yang sudah ditandai surveyor sebagai duplikat/kesalahan (mis. "DUPLIKAT HOMEPASS (ERROR)")
DUPF_RX = re.compile(r"duplikat|duplicate|\berror\b", re.IGNORECASE)
ROUTE_RX = re.compile(r"\b(routes?|cables?|kabel|roads?|jalur)\b", re.IGNORECASE)


def _strip(tag):
    return tag.rsplit("}", 1)[-1]


def kml_root(path):
    """Kembalikan elemen root KML dari file .kml atau .kmz."""
    if path.lower().endswith(".kmz"):
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if n.lower().endswith(".kml")]
            if not names:
                raise QgsProcessingException("Tidak ada file .kml di dalam %s" % path)
            name = "doc.kml" if "doc.kml" in names else names[0]
            data = z.read(name)
    else:
        with open(path, "rb") as fh:
            data = fh.read()
    return ET.fromstring(data)  # nosec B314


def _coords(text):
    out = []
    for t in (text or "").split():
        v = t.split(",")
        if len(v) >= 2:
            out.append(QgsPointXY(float(v[0]), float(v[1])))
    return out


class _kml_stream(object):
    """Buka KMZ (zip berisi .kml) ATAU file .kml biasa sebagai stream untuk iterparse."""
    def __init__(self, path):
        self.path, self._z, self._f = path, None, None

    def __enter__(self):
        if zipfile.is_zipfile(self.path):
            self._z = zipfile.ZipFile(self.path)
            names = [n for n in self._z.namelist() if n.lower().endswith(".kml")]
            if not names:
                raise ValueError("KMZ tanpa file .kml: %s" % os.path.basename(self.path))
            self._f = self._z.open("doc.kml" if "doc.kml" in names else names[0])
        else:
            self._f = open(self.path, "rb")
        return self._f

    def __exit__(self, *a):
        for h in (self._f, self._z):
            try:
                if h is not None:
                    h.close()
            except Exception as _e:
                _log.note(_e)
        return False


# Data referensi: pola nama file per jenis (dicari juga di subfolder, KMZ atau KML)
REF_KINDS = {
    "funnel": (r"FUNNEL", (".kmz", ".kml")),
    "designlite": (r"DESIGN[\s_-]*LITE", (".kmz", ".kml")),
    "attributes": (r"attribut|atribut|FINDIM", (".xlsx", ".xlsm")),
    "feeder": (r"feeder", (".kmz", ".kml")),
    "sdproj": (r".", (".sdproj",)),
}


REF_LABELS = [("funnel", "Funnel"), ("designlite", "Design Lite"), ("attributes", "FINDIM"),
              ("feeder", "Feeder"), ("sdproj", "desain otomatis .sdproj")]


def ref_summary(ref_dir):
    """Ringkasan data referensi untuk laporan: list (label, [nama file])."""
    return [(lab, [os.path.basename(x) for x in ref_files(ref_dir, k)]) for k, lab in REF_LABELS]


def ref_files(ref_dir, kind, depth=2):
    """Semua file referensi `kind` di folder referensi dan subfoldernya (maks `depth` tingkat)."""
    pat, exts = REF_KINDS[kind]
    out = []
    if not ref_dir or not os.path.isdir(ref_dir):
        return out
    for root, dirs, files in os.walk(ref_dir):
        rel = os.path.relpath(root, ref_dir)
        d = 0 if rel == "." else rel.count(os.sep) + 1
        dirs[:] = [] if d >= depth else [x for x in dirs if not x.startswith(".")
                                          and not x.upper().startswith(("INPUT", "HASIL_PASCA"))]
        for f in files:
            if not f.startswith("~$") and f.lower().endswith(exts) and re.search(pat, f, re.IGNORECASE):
                out.append(os.path.join(root, f))
    return out


def find_ref_dir(cluster_dir, max_dirs=600):
    """Cari otomatis folder data referensi di sekitar folder cluster (folder itu, induk, kakek; 2 tingkat ke bawah)
    untuk pengguna baru yang belum mengisi isian 2. Folder dengan jenis data referensi terbanyak dipilih."""
    starts, cur = [], os.path.abspath(cluster_dir)
    for _ in range(3):
        starts.append(cur)
        nxt = os.path.dirname(cur)
        if nxt == cur:
            break
        cur = nxt
    best, seen, n = None, set(), 0
    for base in starts:
        for root, dirs, files in os.walk(base):
            n += 1
            if n > max_dirs:
                break
            rel = os.path.relpath(root, base)
            d = 0 if rel == "." else rel.count(os.sep) + 1
            dirs[:] = [] if d >= 2 else [x for x in dirs if not x.startswith(".")
                                         and not x.upper().startswith(("INPUT", "HASIL_PASCA"))]
            if root in seen:
                continue
            seen.add(root)
            kinds = {k for f in files for k, (pat, exts) in REF_KINDS.items()
                     if k != "sdproj" and f.lower().endswith(exts) and re.search(pat, f, re.IGNORECASE)}
            if "funnel" in kinds or "designlite" in kinds:
                score = (len(kinds), "funnel" in kinds)
                if best is None or score > best[0]:
                    best = (score, root)
    return best[1] if best else ""


def _ring_xy(el):
    """Koordinat satu LinearRing -> [(x, y)], ditutup bila belum tertutup."""
    txt = " ".join(x.text or "" for x in el.iter() if _strip(x.tag) == "coordinates")
    ring = []
    for tok in txt.split():
        v = tok.split(",")
        if len(v) >= 2:
            try:
                ring.append((float(v[0]), float(v[1])))
            except ValueError:
                continue
    if len(ring) >= 3 and ring[0] != ring[-1]:
        ring.append(ring[0])
    return ring


def _polygon_rings(poly_el):
    """(outer, holes) dari elemen KML Polygon. SETIAP LinearRing dibaca terpisah: aplikasi peta KMZ mengizinkan
    beberapa LinearRing di dalam satu innerBoundaryIs; bila digabung, lubang menjadi garis zig-zag/paku."""
    outer, holes = [], []
    for b in poly_el:
        bt = _strip(b.tag)
        rings = [r for r in b.iter() if _strip(r.tag) == "LinearRing"] or [b]
        for r in rings:
            ring = _ring_xy(r)
            if len(ring) < 4:
                continue
            if bt == "outerBoundaryIs" and not outer:
                outer = ring
            elif bt in ("outerBoundaryIs", "innerBoundaryIs"):
                holes.append(ring) if bt == "innerBoundaryIs" else None
    return outer, holes


def kml_features(path):
    """Daftar (jalur_folder, nama, jenis, koordinat) untuk setiap Point/LineString."""
    feats = []

    def walk(el, folders):
        for ch in el:
            tag = _strip(ch.tag)
            if tag in ("Folder", "Document"):
                nm = ""
                for c in ch:
                    if _strip(c.tag) == "name":
                        nm = (c.text or "").strip()
                        break
                # nama Document (biasanya nama cluster) tidak ikut dicocokkan
                walk(ch, folders + [nm] if tag == "Folder" else folders)
            elif tag == "Placemark":
                pname = ""
                for c in ch:
                    if _strip(c.tag) == "name":
                        pname = (c.text or "").strip()
                for g in ch.iter():
                    gt = _strip(g.tag)
                    if gt == "Polygon":
                        outer, holes = _polygon_rings(g)
                        if len(outer) >= 3:
                            feats.append((folders, pname, "polygon", (outer, holes)))
                    if gt in ("Point", "LineString"):
                        for c in g:
                            if _strip(c.tag) == "coordinates":
                                pts = _coords(c.text)
                                if gt == "Point" and pts:
                                    feats.append((folders, pname, "point", pts[0]))
                                elif gt == "LineString" and len(pts) >= 2:
                                    feats.append((folders, pname, "line", pts))
    walk(kml_root(path), [])
    return feats


def classify(folders):
    """'pole' / 'route' / None berdasarkan nama folder mana pun di jalurnya."""
    for f in reversed(folders):        # folder terdalam diutamakan
        if SKIP_RX.search(f):
            return None
        if ROUTE_RX.search(f):
            return "route"
        if POLE_RX.search(f):
            return "pole"
    return None



# ---------- Mencari file HPDB dan KMZ di folder cluster ----------
_DERIVED = re.compile(r"^(poles?|tiang|cables?|routes?|route ?cable|roads?|jalur|kabel|qc_temuan)$", re.IGNORECASE)


def _choose(folder, cands, keyword, kind):
    if not cands:
        raise QgsProcessingException("Tidak ada file %s di folder cluster: %s" % (kind, folder))
    pref = [f for f in cands if keyword and keyword in f.upper()]
    pick = pref if pref else cands
    if len(pick) > 1:
        raise QgsProcessingException(
            "Ada lebih dari satu file %s di folder cluster: %s. Pilih salah satu di isian opsional %s."
            % (kind, ", ".join(sorted(pick)), kind))
    return os.path.join(folder, pick[0])


def _files(folder):
    return [f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))]


# nama file HPDB dari vendor tidak selalu tepat: HPDB, HPBD (salah ketik), HP_DB, HOMEPASS ...
HPDB_NAME_RX = re.compile(r"HP\s*[-_ ]?\s*(DB|BD)\b|HP\s*[-_ ]?\s*(DB|BD)(?=[-_ ]|$)|HOME\s*PASS", re.IGNORECASE)
NOT_HPDB_RX = re.compile(r"TSSR|\bBOM\b|BAKP|ATTRIBUT|ATRIBUT|FINDIM|DAILY|SPLICE|FDT.?FAT.?CODE|TEMPLATE|TAMPLATE",
                         re.IGNORECASE)


def _sheet_files(folder):
    return [f for f in _files(folder) if os.path.splitext(f)[1].lower() in (".xlsx", ".xls", ".csv")
            and not f.startswith("~$")]


def hpdb_candidates(folder):
    """Kandidat HPDB: nama memuat HPDB/HPBD/HOMEPASS; bila tidak ada, satu-satunya spreadsheet yang bukan
    TSSR/BOM/BAKP/attributes."""
    c = _sheet_files(folder)
    named = [f for f in c if HPDB_NAME_RX.search(os.path.splitext(f)[0]) and not NOT_HPDB_RX.search(f)]
    if named:
        return named
    other = [f for f in c if not NOT_HPDB_RX.search(f)]
    return other if len(other) == 1 else []


def find_hpdb(folder):
    """File HPDB di folder cluster: .xlsx/.xls/.csv, utamakan yang namanya mengandung HPDB (atau HPBD/HOMEPASS)."""
    c = hpdb_candidates(folder) or _sheet_files(folder)
    return _choose(folder, c, "", "HPDB")


def find_kmz(folder):
    """KMZ cluster dari vendor: .kmz/.kml selain hasil turunan (POLE, CABLE, QC_TEMUAN, ...)."""
    c = [f for f in _files(folder) if os.path.splitext(f)[1].lower() in (".kmz", ".kml")
         and not _DERIVED.match(os.path.splitext(f)[0].strip())]
    # folder proyek yang sudah sampai tahap pasca-desain juga berisi KMZ APD dan paket feeder (F5_T8_...):
    # itu hasil desain, bukan KMZ survei vendor
    survey = [f for f in c if not APD_KMZ_RX.search(f)]
    if survey:
        c = survey
    pref = [f for f in c if re.match(r"^KMZ[_\s-]", f, re.IGNORECASE)]
    return _choose(folder, pref or c, "KMZ", "KMZ cluster")


APD_KMZ_RX = re.compile(r"\bAPD\b|^F\d+_T\d+_|^QC_|FEEDER|DISTRIBUS", re.IGNORECASE)


# ---------- Pembaca .xlsx tanpa GDAL (zip + XML, hanya pustaka standar Python) ----------
import posixpath

def _local(tag):
    return tag.rsplit("}", 1)[-1]

def _col_index(ref):
    n = 0
    for ch in ref:
        if ch.isalpha():
            n = n * 26 + (ord(ch.upper()) - 64)
        else:
            break
    return n - 1

def _clean_number(v):
    try:
        f = float(v)
    except ValueError:
        return v
    if f.is_integer() and abs(f) < 1e15:
        return "%d" % f
    return "%.15g" % f

def read_xlsx(path, max_empty=200, max_scan=20000, want=None):
    """Kembalikan list (nama_sheet, baris) untuk setiap worksheet.
    Berhenti membaca sheet setelah `max_empty` baris kosong berturut-turut
    (termasuk lompatan nomor baris), sehingga sel liar di baris ke-1 juta diabaikan."""
    out = []
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        shared = []
        if "xl/sharedStrings.xml" in names:
            for _, el in ET.iterparse(z.open("xl/sharedStrings.xml")):  # nosec B314
                if _local(el.tag) == "si":
                    shared.append("".join(t.text or "" for t in el.iter() if _local(t.tag) == "t"))
                    el.clear()
        rels = {}
        if "xl/_rels/workbook.xml.rels" in names:
            for r in ET.parse(z.open("xl/_rels/workbook.xml.rels")).getroot():  # nosec B314
                tgt = r.get("Target", "")
                tgt = tgt.lstrip("/") if tgt.startswith("/") else posixpath.normpath(posixpath.join("xl", tgt))
                rels[r.get("Id")] = (tgt, r.get("Type", ""))
        wb = ET.parse(z.open("xl/workbook.xml")).getroot()  # nosec B314
        for sh in wb.iter():
            if _local(sh.tag) != "sheet":
                continue
            rid = next((v for k, v in sh.attrib.items() if _local(k) == "id"), None)
            tgt, typ = rels.get(rid, ("", ""))
            if not typ.endswith("/worksheet") or tgt not in names:
                continue                      # lewati chartsheet / sheet tanpa file
            if want is not None and not want(sh.get("name") or ""):
                continue
            rows, last, empty, seen = [], 0, 0, False
            for _, el in ET.iterparse(z.open(tgt)):  # nosec B314
                if _local(el.tag) != "row":
                    continue
                rnum = int(el.get("r") or (last + 1))
                gap = rnum - last - 1
                if seen and gap > 0:
                    empty += gap
                    if empty >= max_empty:
                        el.clear(); break
                    rows.extend([[] for _ in range(gap)])
                elif gap > 0:
                    rows.extend([[] for _ in range(gap)])
                cells = {}
                for c in el:
                    if _local(c.tag) != "c":
                        continue
                    t = c.get("t", "n")
                    ref = c.get("r")
                    idx = _col_index(ref) if ref else (max(cells) + 1 if cells else 0)
                    val = ""
                    if t == "inlineStr":
                        val = "".join(x.text or "" for x in c.iter() if _local(x.tag) == "t")
                    else:
                        v = next((x.text for x in c if _local(x.tag) == "v"), None)
                        if v is not None:
                            if t == "s":
                                val = shared[int(v)] if int(v) < len(shared) else ""
                            elif t == "b":
                                val = "TRUE" if v == "1" else "FALSE"
                            elif t in ("str", "e"):
                                val = v
                            else:
                                val = _clean_number(v)
                    cells[idx] = val.strip()
                row = [""] * (max(cells) + 1) if cells else []
                for i, v in cells.items():
                    row[i] = v
                rows.append(row)
                last = rnum
                if any(row):
                    seen, empty = True, 0
                elif seen:
                    empty += 1
                    if empty >= max_empty:
                        el.clear(); break
                el.clear()
                if len(rows) > max_scan and not seen:
                    break
            while rows and not any(rows[-1]):
                rows.pop()
            out.append((sh.get("name"), rows))
    return out


# ---------- Cek boundary terhadap Funnel ----------
BOUNDARY_RX = re.compile(r"\b(boundary|bondary|batas)\b", re.IGNORECASE)
INACTIVE_RX = re.compile(r"reject|drop|ny macro|cancel|batal", re.IGNORECASE)


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


def dist_to_poly_m(x, y, poly):
    """Jarak (meter, pendekatan lokal) dari titik ke tepi poligon (outer + holes)."""
    import math
    kx, ky = math.cos(math.radians(y)) * 111320.0, 110574.0
    best = None
    for r in [poly[0]] + list(poly[1]):
        for i in range(len(r)):
            ax, ay = r[i - 1]
            bx, by = r[i]
            ax, bx, px = ax * kx, bx * kx, x * kx
            ay, by, py = ay * ky, by * ky, y * ky
            dx, dy = bx - ax, by - ay
            t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / ((dx * dx + dy * dy) or 1e-12)))
            d = math.hypot(px - ax - t * dx, py - ay - t * dy)
            if best is None or d < best:
                best = d
    return best if best is not None else 1e9


def _bbox(ring):
    xs = [a for a, b in ring]
    ys = [b for a, b in ring]
    return min(xs), min(ys), max(xs), max(ys)


def _seg_cross(a, b, c, d):
    def o(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return o(a, b, c) * o(a, b, d) < 0 and o(c, d, a) * o(c, d, b) < 0


def polys_overlap(P, Q):
    """True bila dua poligon (outer ring) beririsan. Cepat: hanya titik & ruas di dalam bbox bersama yang diuji."""
    a, b = P[0], Q[0]
    ba, bb = _bbox(a), _bbox(b)
    x0, y0, x1, y1 = max(ba[0], bb[0]), max(ba[1], bb[1]), min(ba[2], bb[2]), min(ba[3], bb[3])
    if x0 > x1 or y0 > y1:
        return False

    def inb(pt):
        return x0 <= pt[0] <= x1 and y0 <= pt[1] <= y1
    if any(_pip(x, y, b) for x, y in a if x0 <= x <= x1 and y0 <= y <= y1) or \
            any(_pip(x, y, a) for x, y in b if x0 <= x <= x1 and y0 <= y <= y1):
        return True

    def segs(r):
        out = []
        for i in range(len(r) - 1):
            p, q = r[i], r[i + 1]
            if max(p[0], q[0]) >= x0 and min(p[0], q[0]) <= x1 and max(p[1], q[1]) >= y0 and min(p[1], q[1]) <= y1:
                out.append((p, q, min(p[0], q[0]), max(p[0], q[0]), min(p[1], q[1]), max(p[1], q[1])))
        return out
    sa, sb = segs(a), segs(b)
    sb.sort(key=lambda t: t[2])
    xs = [t[2] for t in sb]
    import bisect
    for p, q, ax0, ax1, ay0, ay1 in sa:
        for k in range(bisect.bisect_right(xs, ax1)):
            c, d, bx0, bx1, by0, by1 = sb[k]
            if bx1 < ax0 or by1 < ay0 or by0 > ay1:
                continue
            if _seg_cross(p, q, c, d):
                return True
    return False


FUNNEL_GRP_RX = re.compile(r"^\s*(RFS\s*(DONE|EXT)|BOUNDARY\s*FUNNEL)", re.IGNORECASE)


def read_funnel(paths, extent, feedback=None):
    """Baca poligon Funnel yang bbox-nya bersinggungan dengan `extent` (xmin, ymin, xmax, ymax).
    Grup diambil dari folder level-1: Boundary Funnel, RFS DONE, RFS EXTENSION."""
    out = []
    for path in paths:
        if feedback:
            feedback.pushInfo("Membaca Funnel: %s" % os.path.basename(path))
        with _kml_stream(path) as src:
            stack = []
            for ev, el in ET.iterparse(src, events=("start", "end")):  # nosec B314
                t = _strip(el.tag)
                if ev == "start" and t == "Folder":
                    stack.append(None)
                elif ev == "end" and t == "name" and stack and stack[-1] is None:
                    stack[-1] = (el.text or "").strip()
                elif ev == "end" and t == "Folder":
                    stack.pop()
                    el.clear()
                elif ev == "end" and t == "Placemark":
                    polys = []
                    for g in el.iter():
                        if _strip(g.tag) != "Polygon":
                            continue
                        outer, holes = _polygon_rings(g)
                        if len(outer) >= 3:
                            bb = _bbox(outer)
                            if bb[2] >= extent[0] and bb[0] <= extent[2] and bb[3] >= extent[1] and bb[1] <= extent[3]:
                                polys.append(((outer, holes), bb))
                    if polys:
                        d = {}
                        for x in el.iter():
                            xt = _strip(x.tag)
                            if xt == "SimpleData":
                                d[x.get("name")] = (x.text or "").strip()
                            elif xt == "Data":
                                d[x.get("name")] = "".join(v.text or "" for v in x if _strip(v.tag) == "value").strip()
                        fold = [f for f in stack if f]
                        # grup = folder bernama Boundary Funnel / RFS DONE / RFS EXTENSION di level mana pun
                        # (file yang disimpan ulang di aplikasi peta KMZ sering mendapat folder induk tambahan)
                        known = [f for f in fold if FUNNEL_GRP_RX.search(f)]
                        grp = known[0] if known else (fold[1] if len(fold) > 1 else (fold[0] if fold else ""))
                        status = d.get("StrandAPD") or (fold[-1] if fold else "")
                        nm = ""
                        for c in el:
                            if _strip(c.tag) == "name":
                                nm = (c.text or "").strip()
                        for poly, bb in polys:
                            out.append({"name": nm, "grp": grp, "status": status,
                                        "plan": d.get("HP_Plan", ""), "olt": d.get("Plan_OLT", ""),
                                        "poly": poly, "bb": bb})
                    el.clear()
    return out


def _base(name):
    return re.sub(r"[^A-Z0-9]", "", re.sub(r"-?\s*EXTENSION", "", (name or "").upper()))


def _funnel_geom(poly):
    """QgsGeometry MultiPolygon yang valid dari (outer, holes) Funnel, atau None.
    Lubang yang rusak dibuang dulu; hasil makeValid berupa GeometryCollection diambil bagian poligonnya saja."""
    def ring(r):
        r = [(float(x), float(y)) for x, y in r]
        if len(r) >= 3 and r[0] != r[-1]:
            r.append(r[0])
        return [QgsPointXY(x, y) for x, y in r] if len(set(r)) >= 3 else None
    outer = ring(poly[0])
    if outer is None:
        return None
    holes = [h for h in (ring(r) for r in poly[1]) if h]
    g = QgsGeometry.fromPolygonXY([outer] + holes)
    if g.isNull() or g.isEmpty():
        return None
    if not g.isGeosValid():
        v = g.makeValid()
        if v is None or v.isNull() or v.isEmpty():
            v = QgsGeometry.fromPolygonXY([outer]).makeValid()   # terakhir: tanpa lubang
        g = v
        if g is None or g.isNull() or g.isEmpty():
            return None
        if QgsWkbTypes.geometryType(g.wkbType()) != GEOM_POLYGON or \
                "COLLECTION" in QgsWkbTypes.displayString(g.wkbType()).upper():
            parts = []
            for part in g.asGeometryCollection():
                if QgsWkbTypes.geometryType(part.wkbType()) == GEOM_POLYGON and not part.isEmpty():
                    parts.extend(part.asMultiPolygon() if part.isMultipart() else [part.asPolygon()])
            if not parts:
                return None
            g = QgsGeometry.fromMultiPolygonXY(parts)
    g.convertToMultiType()
    return g if not g.isEmpty() else None


# ---------- Memilih file harian terbaru (nama berisi tanggal, mis. 20102026 / 20-10-2026) ----------
import datetime as _dt
_DATE_RX = re.compile(r"(?<!\d)(\d{1,2})[-_. ]?(\d{1,2})[-_. ]?(20\d{2})(?!\d)")


_MONTHS = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "MEI": 5, "JUN": 6, "JUL": 7,
           "AUG": 8, "AGU": 8, "AGS": 8, "SEP": 9, "OCT": 10, "OKT": 10, "NOV": 11, "DEC": 12, "DES": 12}
_MDATE_RX = re.compile(r"(?<!\d)(\d{1,2})[-_. ]?([A-Za-z]{3})[A-Za-z]*[-_. ]?(20\d{2})(?!\d)")


def file_date(path):
    """Tanggal dari nama file (ddmmyyyy, dd-mm-yyyy, 9_Nov_2022, 21 Okt 2026);
    jika tidak ada, tanggal ubah file."""
    base = os.path.basename(path)
    for m in _DATE_RX.finditer(base):
        try:
            return _dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            continue
    for m in _MDATE_RX.finditer(base):
        mon = _MONTHS.get(m.group(2).upper())
        if mon:
            try:
                return _dt.date(int(m.group(3)), mon, int(m.group(1)))
            except ValueError:
                continue
    return _dt.date.fromtimestamp(os.path.getmtime(path))


def latest_per_kind(paths):
    """Kelompokkan file berdasarkan nama tanpa tanggal/angka (mis. 'ALL FUNNEL (EXISTING CITY)')
    lalu ambil yang terbaru per kelompok. Mengembalikan list (path, tanggal, jumlah_versi)."""
    groups = {}
    for pth in paths:
        stem = os.path.splitext(os.path.basename(pth))[0]
        stem = re.sub(r"\s*\(\d+\)\s*$", "", stem)          # salinan unduhan: "nama (1)"
        stem = _MDATE_RX.sub(" ", _DATE_RX.sub(" ", stem))
        key = re.sub(r"\s+", " ", re.sub(r"[\d\-_.]+", " ", stem)).strip().upper()
        groups.setdefault(key, []).append(pth)
    out = []
    for key, items in sorted(groups.items()):
        items.sort(key=lambda q: (file_date(q), os.path.getmtime(q)))
        out.append((items[-1], file_date(items[-1]), len(items)))
    return out


# ---------- Analisis colo dari Design Lite (jaringan existing) ----------
DL_SKIP_RX = re.compile(r"drop|reject", re.IGNORECASE)
DESIGN_RX = re.compile(r"KMZ|APD|^\d{9,}", re.IGNORECASE)
SPL_RX = re.compile(r"^\s*(\d+)\s*x\s*1\s*x\s*(4|8)\s*$", re.IGNORECASE)
DL_HP_RX = re.compile(r"\b(hp|homepass|home ?pass)\b", re.IGNORECASE)
DL_POLE_RX = re.compile(r"\b(tiang|poles?)\b", re.IGNORECASE)


def _dl_code(d, nm):
    """Kode FDT/FAT dari atribut (nama kolom di Design Lite tidak seragam)."""
    for k, v in d.items():
        n = re.sub(r"[^A-Z]", "", (k or "").upper())
        if n.startswith("COLO") or not v or v.strip() in ("-", ""):
            continue
        if ("FDT" in n or "FAT" in n) and "CO" in n:
            return v.strip()
    return (nm or "").strip()


def _int(v):
    try:
        return int(float(str(v).replace(",", ".")))
    except (TypeError, ValueError):
        return None


def read_design_lite(paths, extent, feedback=None):
    """Titik FDT existing di Design Lite yang berada di dalam `extent`.
    Folder DROP/REJECT dilewati. Satu FDT bisa muncul di beberapa desain
    (desain induk + tiap cluster yang colo); SPLITTERS = pemakaian desain itu."""
    out = []
    for path in paths:
        if feedback:
            feedback.pushInfo("Membaca Design Lite: %s" % os.path.basename(path))
        with _kml_stream(path) as src:
            stack = []
            for ev, el in ET.iterparse(src, events=("start", "end")):  # nosec B314
                t = _strip(el.tag)
                if ev == "start" and t == "Folder":
                    stack.append(None)
                elif ev == "end" and t == "name" and stack and stack[-1] is None:
                    stack[-1] = (el.text or "").strip()
                elif ev == "end" and t == "Folder":
                    stack.pop()
                    el.clear()
                elif ev == "end" and t == "Placemark":
                    fold = [f for f in stack if f]
                    pt = None
                    if not any(DL_SKIP_RX.search(f) for f in fold):
                        for g in el.iter():
                            if _strip(g.tag) == "Point":
                                txt = " ".join(x.text or "" for x in g.iter() if _strip(x.tag) == "coordinates")
                                v = txt.split()[0].split(",") if txt.split() else []
                                if len(v) >= 2:
                                    pt = (float(v[0]), float(v[1]))
                                break
                    if pt and extent[0] <= pt[0] <= extent[2] and extent[1] <= pt[1] <= extent[3]:
                        d = {}
                        for x in el.iter():
                            xt = _strip(x.tag)
                            if xt == "SimpleData":
                                d[x.get("name")] = (x.text or "").strip()
                            elif xt == "Data":
                                d[x.get("name")] = "".join(v.text or "" for v in x if _strip(v.tag) == "value").strip()
                        nm = ""
                        for c in el:
                            if _strip(c.tag) == "name":
                                nm = (c.text or "").strip()
                        code = _dl_code(d, nm)
                        spl = SPL_RX.match(d.get("SPLITTERS", "") or "")
                        leaf = " ".join(fold[-2:]).upper()
                        is_fdt = not re.search(r"-D\d", code) and (
                            re.search(r"-H\d+$", code) or (spl and re.search(r"\bFDT\b", leaf)))
                        mfat = re.match(r"^(.+?-H\d+)-D\d+-\d+$", code) if not is_fdt else None
                        if mfat:
                            out.append({"kind": "fat", "code": code, "fdt": mfat.group(1), "x": pt[0], "y": pt[1],
                                        "prem": _int(d.get("PREMISES"))})
                        elif not is_fdt and DL_HP_RX.search(" ".join(fold[-1:])):
                            out.append({"kind": "hp", "x": pt[0], "y": pt[1], "name": nm})
                        elif not is_fdt and DL_POLE_RX.search(" ".join(fold[-1:])):
                            out.append({"kind": "pole", "x": pt[0], "y": pt[1], "name": nm, "folder": fold[-1]})
                        if is_fdt:
                            colo = ""
                            for k, v in d.items():
                                if re.sub(r"[^A-Z]", "", (k or "").upper()).startswith("COLO") and v not in ("", "-"):
                                    colo = v
                            design = next((f for f in fold if DESIGN_RX.search(f)),
                                          fold[-3] if len(fold) >= 3 else (fold[-1] if fold else ""))
                            out.append({"kind": "fdt", "code": code, "x": pt[0], "y": pt[1],
                                        "spl": int(spl.group(1)) if spl else None,
                                        "ratio": int(spl.group(2)) if spl else None,
                                        "prem": _int(d.get("PREMISES")), "colo": colo,
                                        "design": design, "city": fold[2] if len(fold) > 2 else "",
                                        "grp": fold[1] if len(fold) > 1 else ""})
                    el.clear()
    return out


# ---------- Profil proyek: angka diambil dari config desain otomatis (.sdproj) tim ----------
# splitter 1x4 (384) / 1x8 (480) / 1x4 (800): FDT maks terminasi, jarak HP->FAT maks (path length), kapasitas FAT.
PROFILES = [
    {"name": "Splitter 1x4 - FDT 384 HP, FAT 120 m", "key": "P384", "fdt_cap": 384, "fat_dist": 120, "fat_min": 8, "fat_max": 16,
     "fat_target": 15, "ratio": 4, "max_spl": 12, "hp_per_spl": 32},
    {"name": "Splitter 1x8 - FDT 480 HP, FAT 130 m", "key": "P480", "fdt_cap": 480, "fat_dist": 130, "fat_min": 8, "fat_max": 16,
     "fat_target": 15, "ratio": 8, "max_spl": 8, "hp_per_spl": 64},
    {"name": "Splitter 1x4 - FDT 800 HP, FAT 150 m", "key": "P800", "fdt_cap": 800, "fat_dist": 150, "fat_min": 8, "fat_max": 16,
     "fat_target": 15, "ratio": 4, "max_spl": 25, "hp_per_spl": 32},
]


def read_sdproj_rules(path):
    """Ambil aturan dari config desain otomatis (.sdproj = zip berisi config.xml): kapasitas FDT, FAT, jarak FAT."""
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("config.xml"))  # nosec B314
    out = {}
    for sp in root.iter("Specific"):
        sc = sp.get("scope") or ""
        cap = sp.find(".//NodeCapacityRule")
        dist = [d for d in sp.iter("NodeDistanceRule") if (d.findtext("Metric") or "") == "plength"]
        models = [m.text for m in sp.iter("ModelNumber")]
        if "FDT" in models and cap is not None and cap.findtext("Maximum"):
            out["fdt_cap"] = int(float(cap.findtext("Maximum")))
        if sc.startswith("(L:3") and cap is not None and cap.findtext("Maximum"):
            for k, t in (("fat_min", "Minimum"), ("fat_max", "Maximum"), ("fat_target", "Target")):
                if cap.findtext(t):
                    out[k] = int(float(cap.findtext(t)))
            if dist and dist[0].findtext("Maximum"):
                out["fat_dist"] = float(dist[0].findtext("Maximum"))
    return out


def resolve_profile(idx, ref_dir, feedback=None):
    """Profil bawaan, ditimpa angka dari .sdproj yang cocok di folder referensi (bila ada)."""
    prof = dict(PROFILES[max(0, min(idx, len(PROFILES) - 1))])
    prof["src"] = "bawaan plugin (dari config desain otomatis tim, Okt 2026)"
    if ref_dir and os.path.isdir(ref_dir):
        tok = {"P384": r"1\s*X\s*4(?!.*800)", "P480": r"1\s*X\s*8", "P800": r"800"}[prof["key"]]
        cands = [f for f in ref_files(ref_dir, "sdproj") if re.search(tok, os.path.basename(f), re.IGNORECASE)]
        if cands:
            pth = sorted(cands)[-1]
            try:
                prof.update(read_sdproj_rules(pth))
                prof["src"] = os.path.basename(pth)
            except Exception as e:
                if feedback:
                    feedback.reportError("Config desain otomatis %s tidak terbaca: %s" % (os.path.basename(cands[-1]), e), fatalError=False)
    prof["max_spl"] = min(prof["max_spl"], max(1, prof["fdt_cap"] // prof["hp_per_spl"])) if prof["key"] != "P480" else prof["max_spl"]
    return prof


def design_cluster_name(design):
    """'21113127175_APD Distribusi KMZ_RW 004 KALIDONI_20-07-2024' -> 'RW 004 KALIDONI'."""
    m = re.search(r"KMZ[_\s-]+(.+?)(?:[_\s-]+\d{1,2}[-_.]\d{1,2}[-_.]\d{2,4})?\s*$", design or "", re.IGNORECASE)
    return (m.group(1) if m else design or "").strip()


# ---------- Cache data referensi harian (Funnel / Design Lite / Feeder) ----------
# File harian dibaca penuh SEKALI per tanggal-versi, lalu disimpan per tile 0,2 derajat (~22 km).
# Run berikutnya (cluster lain, batch, rekan setim di laptop sama) hanya membuka tile di sekitar cluster.
_CACHE_VER = 6
_TILE = 0.2
_WORLD = (-180.0, -90.0, 180.0, 90.0)


def _cache_root():
    base = os.environ.get("SERANTA_CACHE_DIR", "") or ""
    if not base:
        try:
            from qgis.core import QgsApplication
            base = QgsApplication.qgisSettingsDirPath()
        except Exception:
            base = ""
    env = os.environ.get("SERANTA_CACHE_DIR") or None
    return base if env else os.path.join(base or os.path.expanduser("~"), "seranta_cache")


def _tile_keys(bb):
    import math
    x0, y0 = int(math.floor(bb[0] / _TILE)), int(math.floor(bb[1] / _TILE))
    x1, y1 = int(math.floor(bb[2] / _TILE)), int(math.floor(bb[3] / _TILE))
    if (x1 - x0 + 1) * (y1 - y0 + 1) > 400:          # objek raksasa (mis. batas kota): satu tile khusus
        return ["big"]
    return ["%d_%d" % (i, j) for i in range(x0, x1 + 1) for j in range(y0, y1 + 1)]


def _rec_bb(r):
    return r["bb"] if "bb" in r else (r["x"], r["y"], r["x"], r["y"])


def _jenc(o):
    """Ubah objek cache ke bentuk JSON tanpa kehilangan tipe (tuple/set) - pengganti pickle (aman untuk data cache)."""
    if isinstance(o, dict):
        return {str(k): _jenc(v) for k, v in o.items()}
    if isinstance(o, tuple):
        return {"__t__": [_jenc(v) for v in o]}
    if isinstance(o, (set, frozenset)):
        return {"__s__": [_jenc(v) for v in sorted(o, key=str)]}
    if isinstance(o, list):
        return [_jenc(v) for v in o]
    return o


def _jdec(d):
    if "__t__" in d and len(d) == 1:
        return tuple(d["__t__"])
    if "__s__" in d and len(d) == 1:
        return set(d["__s__"])
    return d


def _jdump(obj, path, gz=False):
    import gzip
    import json
    op = gzip.open if gz else open
    with op(path, "wt", encoding="utf-8") as fh:
        json.dump(_jenc(obj), fh, separators=(",", ":"))


def _jload(path, gz=False):
    import gzip
    import json
    op = gzip.open if gz else open
    with op(path, "rt", encoding="utf-8") as fh:
        return json.load(fh, object_hook=_jdec)


def cached_read(kind, path, extent, parser, feedback=None):
    """Baca `path` lewat cache tile. `parser(paths, extent, feedback)` -> list dict (punya bb atau x/y)."""
    import hashlib
    import shutil
    try:
        st = os.stat(path)
        key = hashlib.sha256(("%s|%s|%d|%d|%d" % (kind, os.path.abspath(path).lower(), st.st_size,
                                                  int(st.st_mtime), _CACHE_VER)).encode("utf-8")).hexdigest()[:16]
        root = _cache_root()
        d = os.path.join(root, "%s_%s" % (kind, key))
        idx = os.path.join(d, "index.json")
        if not os.path.exists(idx):
            if feedback:
                feedback.pushInfo("Membuat cache %s (sekali per versi file, berikutnya jauh lebih cepat): %s"
                                  % (kind, os.path.basename(path)))
            recs = parser([path], _WORLD, feedback)
            tiles = {}
            for i, r in enumerate(recs):
                r["_id"] = i
                for t in _tile_keys(_rec_bb(r)):
                    tiles.setdefault(t, []).append(r)
            tmp = d + ".tmp%d" % os.getpid()
            shutil.rmtree(tmp, ignore_errors=True)
            os.makedirs(tmp)
            for t, lst in tiles.items():
                _jdump(lst, os.path.join(tmp, t + ".json.gz"), gz=True)
            _jdump({"tiles": sorted(tiles), "n": len(recs), "src": path}, os.path.join(tmp, "index.json"))
            shutil.rmtree(d, ignore_errors=True)
            os.replace(tmp, d)
            # bersihkan cache lama untuk file sejenis (> 10 hari)
            import time
            for old in os.listdir(root):
                op = os.path.join(root, old)
                if old.startswith(kind + "_") and op != d and time.time() - os.path.getmtime(op) > 10 * 86400:
                    shutil.rmtree(op, ignore_errors=True)
        have = set(_jload(idx)["tiles"])
        out, seen = [], set()
        for t in [k for k in _tile_keys(extent) if k in have] + (["big"] if "big" in have else []):
            for r in _jload(os.path.join(d, t + ".json.gz"), gz=True):
                bb = _rec_bb(r)
                if r["_id"] in seen or bb[2] < extent[0] or bb[0] > extent[2] or bb[3] < extent[1] or bb[1] > extent[3]:
                    continue
                seen.add(r["_id"])
                out.append(r)
        return out
    except Exception as e:
        if feedback:
            feedback.reportError("Cache %s tidak dipakai (%s); membaca langsung." % (kind, e), fatalError=False)
        return parser([path], extent, feedback)


def read_feeder(paths, extent, feedback=None):
    """Semua garis (LineString) di KMZ feeder: jalur feeder/kabel existing."""
    out = []
    for path in paths:
        if feedback:
            feedback.pushInfo("Membaca Feeder: %s" % os.path.basename(path))
        with _kml_stream(path) as src:
            stack = []
            for ev, el in ET.iterparse(src, events=("start", "end")):  # nosec B314
                t = _strip(el.tag)
                if ev == "start" and t == "Folder":
                    stack.append(None)
                elif ev == "end" and t == "name" and stack and stack[-1] is None:
                    stack[-1] = (el.text or "").strip()
                elif ev == "end" and t == "Folder":
                    stack.pop()
                    el.clear()
                elif ev == "end" and t == "Placemark":
                    fold = [f for f in stack if f]
                    for g in el.iter():
                        if _strip(g.tag) == "LineString":
                            txt = " ".join(x.text or "" for x in g.iter() if _strip(x.tag) == "coordinates")
                            pts = []
                            for tok in txt.split():
                                v = tok.split(",")
                                if len(v) >= 2:
                                    pts.append((float(v[0]), float(v[1])))
                            if len(pts) >= 2:
                                bb = _bbox(pts)
                                if bb[2] >= extent[0] and bb[0] <= extent[2] and bb[3] >= extent[1] and bb[1] <= extent[3]:
                                    out.append({"coords": pts, "bb": bb, "folder": " / ".join(fold[-2:])})
                    el.clear()
    return out


def seg_dist_m(x, y, a, b):
    import math
    kx, ky = math.cos(math.radians(y)) * 111320.0, 110574.0
    ax, ay, bx, by, px, py = a[0] * kx, a[1] * ky, b[0] * kx, b[1] * ky, x * kx, y * ky
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / ((dx * dx + dy * dy) or 1e-12)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def group_fdt(entries, dist, same_m=150.0):
    """Gabungkan entri per FDT fisik (kode sama, lokasi < same_m meter; kode FDT unik per perangkat, jadi ikon yang
    bergeser puluhan meter di desain lain tetap FDT yang sama - Handbook KMZ kasus 14 'ikon FDT tidak presisi').
    Pemakaian splitter = jumlah SPLITTERS dari semua desain yang memakai FDT itu."""
    groups = []
    for e in entries:
        for g in groups:
            if g["code"] == e["code"] and dist(g["x"], g["y"], e["x"], e["y"]) < same_m:
                g["items"].append(e)
                break
        else:
            groups.append({"code": e["code"], "x": e["x"], "y": e["y"], "items": [e]})
    for g in groups:
        g["spread_m"] = max((dist(g["x"], g["y"], e["x"], e["y"]) for e in g["items"]), default=0.0)
    codes = {}
    for g in groups:
        codes.setdefault(g["code"], []).append(g)
    for g in groups:
        per = {}
        for e in g["items"]:
            k = re.sub(r"[^A-Z0-9]", "", e["design"].upper())
            if k not in per or (e["spl"] or 0) > (per[k]["spl"] or 0):
                per[k] = e
        g["designs"] = sorted(per.values(), key=lambda e: -(e["spl"] or 0))
        g["used"] = sum(e["spl"] or 0 for e in g["designs"])
        g["prem"] = sum(e["prem"] or 0 for e in g["designs"])
        g["dup_loc"] = len(codes[g["code"]]) > 1
    return groups


def read_reservations(path):
    """COLO_RENCANA.csv: tanggal;cluster;fdt;splitter;hp (rencana colo yang belum masuk Design Lite)."""
    import csv
    rows = []
    if path and os.path.exists(path):
        with open(path, newline="", encoding="utf-8-sig") as fh:
            for r in csv.reader(fh, delimiter=";"):
                if len(r) >= 4 and r[0].strip().lower() != "tanggal":
                    rows.append([c.strip() for c in r[:6]] + [""] * (6 - len(r[:6])))
    return rows


def write_reservations(path, rows):
    import csv
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["tanggal", "cluster", "fdt", "splitter", "hp", "id_cluster"])
        w.writerows(rows)


# ---------- Jenis tiang: existing (EP/EXT/TE) atau baru (NP) ----------
EXIST_RX = re.compile(r"\b(ep|ext|exs|exist\w*|eksist\w*|existing|te|tiang ?eksisting)\b|^(ep|te|ext)[\s\-_]?\d",
                      re.IGNORECASE)
NEW_RX = re.compile(r"\b(np|new|baru)\b|^np[\s\-_]?\d", re.IGNORECASE)


# ---------- Dasar teknis aturan tiang (lihat DASAR_ATURAN.md di folder plugin) ----------
# [R1] Lendutan (sag) kabel udara: 2% panjang gawang (spesifikasi teknis FTTH operator nasional PED F-002-2015); nilai dari profil
#      standar (profiles/*.json, kunci sag_pct). Nilai lama 1% (catatan aplikasi pabrikan) hanya untuk kabel tegang tinggi.
# [R2] Ruang bebas vertikal kabel komunikasi: jalan dilalui truk 4,7 m (15,5 ft); jalur pejalan 2,9 m (9,5 ft)
#      (NESC Tabel 232-1). Indonesia: Permen PU 20/PRT/M/2010 Ps.12(6) utilitas di atas jalan >= 5 m -> dipakai 5,0 m.
# [R3] Kedalaman tanam tiang ~10% panjang + 0,6 m (2 ft) (pedoman distribusi utilitas, PRE-CNS-002).
# [R4] Bentang maksimum kabel udara FTTH kecil (mini ADSS/drop): 68 m rekomendasi, 80 m kasus khusus
#      (datasheet kabel drop pabrikan; mini ADSS 80 m).
# [R5] Praktik lapangan Indonesia: jarak tiang 50-60 m, tiang 7 m umum, 9 m untuk jalan lebar/kendaraan tinggi
#      (kajian perguruan tinggi); Perwali Tangsel 47/2019: tiang FO 7-11 m, jarak maks 50 m.
SAG_RATIO = 0.02          # [R1] bawaan bila profil tidak memuat sag_pct
CLEAR_ROAD = 5.0          # Permen PU 20/PRT/M/2010 Ps.12(6): utilitas di atas jalan >= 5 m (NESC 4,7 m) [R2]
CABLE_MAX_SPAN = 80.0     # [R4] meter
POLE_TOP_MARGIN = 0.3     # jarak klem kabel dari puncak tiang (asumsi praktik)
HEIGHT_RX = re.compile(r"(?:^|[^0-9])(6|7|9|11|12|13)(?:[.,]\d)?\s*(?:m\b|meter|M\b)|\b(?:T|NP|EP|TE|EXT)\s*-?\s*(6|7|9|11|12|13)\b",
                       re.IGNORECASE)


def pole_height(folders, name):
    """Tinggi tiang (m) dari nama/folder, mis. 'NP 7M', 'T6', 'Tiang 9 Meter', folder 'NP 6'."""
    for t in [name or ""] + list(reversed(folders or [])):
        m = HEIGHT_RX.search(" " + t + " ")
        if m:
            return float(m.group(1) or m.group(2))
    return None


SPAN_REG = 50.0           # batas jarak antar tiang di regulasi daerah (Perwal Yogyakarta/Tangsel/Pekalongan, rancangan Permen Kominfo 2018)


def trace_spans(seg_list):
    """Gabungkan ruas jalur menjadi rentang tiang-ke-tiang: berjalan dari tiang melewati titik belok tanpa tiang
    (simpul 'X' berderajat 2) sampai bertemu tiang lain, percabangan, atau ujung. -> [(simpul_a, simpul_b, panjang, titik)]"""
    adj = {}
    for idx, (ka, kb, L, a, b) in enumerate(seg_list):
        adj.setdefault(ka, []).append((idx, kb))
        adj.setdefault(kb, []).append((idx, ka))
    used, out = set(), []

    def walk(start, idx0, nxt):
        ka, kb, L, a, b = seg_list[idx0]
        pts = [a, b] if ka == start else [b, a]
        total, cur, prev_idx = L, nxt, idx0
        seen = {idx0}
        while cur[0] == "X" and len(adj.get(cur, [])) == 2:
            nb = [e for e in adj[cur] if e[0] != prev_idx]
            if not nb or nb[0][0] in seen:
                break
            idx, other = nb[0]
            seen.add(idx)
            sa, sb, l2, p1, p2 = seg_list[idx]
            pts.append(p2 if sa == cur else p1)
            total += l2
            prev_idx, cur = idx, other
        return cur, total, pts, seen
    starts = [k for k in adj if k[0] == "P"] + [k for k in adj if k[0] == "X" and len(adj[k]) != 2]
    for st in starts:
        for idx, nxt in adj[st]:
            if idx in used:
                continue
            end, total, pts, seen = walk(st, idx, nxt)
            used |= seen
            out.append((st, end, total, pts))
    return out


POLE_ON_LINE_M = 3.0      # tiang <= 3 m dari garis jalur dianggap penyangga kabel (akurasi GPS ponsel 3-5 m)


def split_spans_at_poles(spans, poles, pidx, tol_m):
    """Pecah rentang tiang-ke-tiang di tiang lain yang berada <= tol_m dari garis (antara kedua ujung).
    -> (rentang baru, set indeks tiang yang ditemukan di tengah garis)."""
    import math
    out, found = [], set()
    for ka, kb, L, pts in spans:
        if len(pts) < 2:
            out.append((ka, kb, L, pts))
            continue
        lat = pts[0].y()
        kx, ky = math.cos(math.radians(lat)) * 111320.0, 110574.0
        xy = [(p.x() * kx, p.y() * ky) for p in pts]
        cum = [0.0]
        for i in range(1, len(xy)):
            cum.append(cum[-1] + math.hypot(xy[i][0] - xy[i - 1][0], xy[i][1] - xy[i - 1][1]))
        tot = cum[-1] or 1e-9
        xs = [p.x() for p in pts]
        ys = [p.y() for p in pts]
        pad = tol_m / 111320.0 * 2
        try:
            from qgis.core import QgsRectangle
            cand = pidx.intersects(QgsRectangle(min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad))
        except Exception:
            cand = range(len(poles))
        ends = {k[1] for k in (ka, kb) if k[0] == "P"}
        hits = []
        for qi in cand:
            if qi in ends:
                continue
            px, py = poles[qi].x() * kx, poles[qi].y() * ky
            best = None
            for i in range(len(xy) - 1):
                ax, ay = xy[i]
                bx, by = xy[i + 1]
                dx, dy = bx - ax, by - ay
                ll = dx * dx + dy * dy
                t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / ll)) if ll else 0.0
                d = math.hypot(px - ax - t * dx, py - ay - t * dy)
                if best is None or d < best[0]:
                    best = (d, cum[i] + t * math.sqrt(ll), i, t)
            if best and best[0] <= tol_m and 1.0 < best[1] < tot - 1.0:
                hits.append((best[1], qi, best[2], best[3]))
        if not hits:
            out.append((ka, kb, L, pts))
            continue
        hits.sort()
        prev_key, prev_ch, prev_pts = ka, 0.0, [pts[0]]
        vi = 0
        for ch, qi, seg_i, t in hits:
            found.add(qi)
            while vi < seg_i:
                vi += 1
                prev_pts.append(pts[vi])
            piece = prev_pts + [poles[qi]]
            out.append((prev_key, ("P", qi), (ch - prev_ch) * L / tot, piece))
            prev_key, prev_ch, prev_pts = ("P", qi), ch, [poles[qi]]
        prev_pts += pts[vi + 1:]
        out.append((prev_key, kb, (tot - prev_ch) * L / tot, prev_pts))
    return out, found


def line_mid(pts):
    """Titik tengah (berdasarkan panjang) dari polyline QgsPointXY."""
    import math
    if len(pts) == 1:
        return pts[0]
    ls = [math.hypot(pts[i + 1].x() - pts[i].x(), pts[i + 1].y() - pts[i].y()) for i in range(len(pts) - 1)]
    half, acc = sum(ls) / 2.0, 0.0
    for i, seg in enumerate(ls):
        if acc + seg >= half and seg > 0:
            t = (half - acc) / seg
            return QgsPointXY(pts[i].x() + t * (pts[i + 1].x() - pts[i].x()), pts[i].y() + t * (pts[i + 1].y() - pts[i].y()))
        acc += seg
    return pts[-1]


def attach_height(h, embed_frac=1.0 / 6.0):
    """Tinggi klem kabel di atas tanah: tinggi - tanam - margin puncak [R3].
    Tanam bawaan = 1/6 panjang tiang (standar konstruksi jaringan distribusi PLN, Keputusan Direksi 473.K/DIR/2010
    Buku 3); embed_frac <= 0 memakai aturan lama 10% + 0,6 m."""
    tanam = h * embed_frac if embed_frac and embed_frac > 0 else 0.1 * h + 0.6
    return h - tanam - POLE_TOP_MARGIN


def pole_kind(folders, name):
    """'existing' / 'new' / '' dari nama tiang lalu folder terdalam."""
    for t in [name or ""] + list(reversed(folders or [])):
        if NEW_RX.search(t):
            return "new"
        if EXIST_RX.search(t):
            return "existing"
    return ""


# Ikon KMZ disertakan di dalam file KMZ (folder files/) sehingga tampil tanpa internet dan tanpa layanan pihak ketiga.
KML_ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons", "kml")


def kmz_icon(name):
    return "files/%s.png" % name


def kmz_add_icons(z, kml_text):
    """Tambahkan ke arsip KMZ semua ikon files/<nama>.png yang dirujuk di kml_text."""
    for nm in sorted(set(re.findall(r"files/([A-Za-z0-9_-]+)\.png", kml_text))):
        src = os.path.join(KML_ICON_DIR, nm + ".png")
        if os.path.isfile(src):
            z.write(src, "files/%s.png" % nm)



# ---------- POLE.kmz rapi: POLE / NP / T<tinggi> / NP-01 ... dan POLE / EP / EP-01 ... ----------
_GENERIC_POLE_RX = re.compile(r"^\s*(?:untitled( placemark)?|placemark|tanpa nama|titik|point|pole|tiang|np|ep|te|ext\w*"
                              r"|exs|existing|eksisting|new|baru|t\s*\d+|(?:np|ep|t)?\s*\d+(?:[.,]\d)?\s*m(?:eter)?)"
                              r"(?:\s+(?:[a-z]{2,7}|\d+\s*m))*\s*$", re.IGNORECASE)


def _natkey(t):
    return [int(x) if x.isdigit() else x.upper() for x in re.split(r"(\d+)", t or "")]


def tidy_pole_names(names, kinds):
    """Nama tiang spesifik & unik dipertahankan; nama umum ('NP', '7M', 'EXT XYZ', 'Untitled Placemark', kosong)
    atau ganda diberi nomor lanjut: NP-01, NP-02 / EP-01 ... Mengembalikan (nama_baru, jumlah_diganti)."""
    out, used, todo = list(names), set(), []
    cnt = {}
    for nm in names:
        k = (nm or "").strip().upper()
        cnt[k] = cnt.get(k, 0) + 1
    for i, nm in enumerate(names):
        nm = (nm or "").strip()
        # nama yang dipakai berulang (mis. 'NP7' untuk semua tiang) dianggap nama kelas, bukan nama tiang
        if nm and re.search(r"\d", nm) and not _GENERIC_POLE_RX.match(nm) and cnt[nm.upper()] == 1:
            used.add(nm.upper())
            out[i] = nm
        else:
            todo.append(i)
    nxt = {}
    width = 3 if len(names) > 99 else 2
    for i in todo:
        pre = "EP" if kinds[i] == "existing" else "NP"
        n = nxt.get(pre, 0)
        while True:
            n += 1
            cand = "%s-%0*d" % (pre, width, n)
            if cand.upper() not in used:
                break
        nxt[pre] = n
        used.add(cand.upper())
        out[i] = cand
    return out, len(todo)


def _xe(t):
    return (str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def write_pole_kmz(path, doc_name, recs):
    """KMZ tiang dengan struktur folder standar Strand (seperti di aplikasi peta KMZ tim):
    POLE > NP > T6/T7/T9 > NP-01..  dan  POLE > EP > EP-01..  Ikon NP = paddle angka tinggi, EP = kotak hitam.
    recs: dict(name, kind, height, x, y, orig). desain otomatis membaca semua Placemark di dalam folder bertingkat."""
    import zipfile
    styles, np_groups, ep = [], {}, []
    for r in recs:
        if r["kind"] == "existing":
            ep.append(r)
        else:
            np_groups.setdefault(int(r["height"]) if r["height"] else 0, []).append(r)

    def style(sid, icon, lv, scale, hs="x=\"0.5\" y=\"0\""):
        for st, lab in (("n", 0), ("h", 0.9)):
            styles.append(
                '<Style id="%s_%s"><IconStyle><scale>%s</scale><Icon><href>%s</href></Icon>'
                '<hotSpot %s xunits="fraction" yunits="fraction"/></IconStyle>'
                '<LabelStyle><scale>%s</scale></LabelStyle>%s</Style>' % (
                    sid, st, scale if st == "n" else scale * 1.2, icon, hs, lab,
                    "<ListStyle><ItemIcon><href>%s</href></ItemIcon></ListStyle>" % lv if lv else ""))
        styles.append('<StyleMap id="%s"><Pair><key>normal</key><styleUrl>#%s_n</styleUrl></Pair>'
                      '<Pair><key>highlight</key><styleUrl>#%s_h</styleUrl></Pair></StyleMap>' % (sid, sid, sid))

    def pm(r, sid):
        h = ("%g" % r["height"]) if r["height"] else ""
        return ('<Placemark><name>%s</name><styleUrl>#%s</styleUrl><ExtendedData>'
                '<Data name="jenis"><value>%s</value></Data><Data name="tinggi_m"><value>%s</value></Data>'
                '<Data name="nama_asli"><value>%s</value></Data></ExtendedData>'
                '<Point><coordinates>%.8f,%.8f,0</coordinates></Point></Placemark>' % (
                    _xe(r["name"]), sid, "existing" if r["kind"] == "existing" else ("new" if r["kind"] == "new" else "-"),
                    h, _xe(r.get("orig") or ""), r["x"], r["y"]))

    def srt(lst):
        return sorted(lst, key=lambda r: _natkey(r["name"]))

    body = []
    if np_groups:
        body.append("<Folder><name>NP</name><open>1</open>")
        for h in sorted(np_groups, key=lambda v: (v == 0, v)):
            sid = "np_%d" % h
            if 1 <= h <= 10:
                style(sid, kmz_icon("pin_%d" % h), kmz_icon("pin_%d" % h), 1.0)
            else:
                style(sid, kmz_icon("pin_unknown"), kmz_icon("pin_unknown"), 1.0)
            body.append("<Folder><name>%s</name>" % ("T%d" % h if h else "TINGGI BELUM DIISI"))
            body.extend(pm(r, sid) for r in srt(np_groups[h]))
            body.append("</Folder>")
        body.append("</Folder>")
    if ep:
        style("ep", kmz_icon("square"), None, 0.6, 'x="0.5" y="0.5"')
        body.append("<Folder><name>EP</name><open>1</open>")
        body.extend(pm(r, "ep") for r in srt(ep))
        body.append("</Folder>")
    kml = ('<?xml version="1.0" encoding="UTF-8"?>\n<kml xmlns="http://www.opengis.net/kml/2.2">'
           '<Document><name>%s</name>%s<Folder><name>POLE</name><open>1</open>%s</Folder></Document></kml>'
           % (_xe(doc_name), "".join(styles), "".join(body)))
    tmp = path + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("doc.kml", kml.encode("utf-8"))
        kmz_add_icons(z, kml)
    os.replace(tmp, path)


# ---------- QC_TEMUAN.kmz ditulis sendiri (tanpa GDAL/LIBKML) ----------
QC_LABELS = [
    # (pola kode, nomor standar, label, nama file kategori, dasar aturan)
    (r"^HP_JAUH_DARI_TIANG", 1, "HP lebih dari batas jarak ke tiang", "S1_HP_JAUH_TIANG",
     "Handbook internal 50 m; bentang drop udara 15-50 m (Europacable 2023)"),
    (r"^HP_DI_RFS_DONE", 2, "HP di cluster terbangun (RFS DONE)", "S2_HP_RFS_DONE", "Standar Review Strand"),
    (r"^HP_DI_RFS_EXT", 2, "HP di RFS EXTENSION cluster lain", "S2_HP_RFS_EXT", "Standar Review Strand"),
    (r"^HP_DI_FUNNEL_LAIN", 2, "HP di funnel cluster lain", "S2_HP_FUNNEL_LAIN", "Standar Review Strand"),
    (r"^ADMIN_", 3, "Wilayah HPDB beda dengan FINDIM", "S3_WILAYAH_FINDIM", "FINDIM"),
    (r"^HP_DUPLIKAT_KOORDINAT", 4, "HP duplikat: koordinat sama", "S4_DUPLIKAT_KOORDINAT", "satu rumah satu homepass"),
    (r"^HP_DUPLIKAT_ID", 4, "HP duplikat: ID operator sama", "S4_DUPLIKAT_ID", "satu rumah satu homepass"),
    (r"^HP_HPDB_TIDAK_ADA_DI_KMZ", 4, "HP di HPDB tidak ada di KMZ", "S4_HPDB_TANPA_KMZ", "konsistensi HPDB-KMZ"),
    (r"^HP_KMZ_TIDAK_ADA_DI_HPDB", 4, "HP di KMZ tidak ada di HPDB", "S4_KMZ_TANPA_HPDB", "konsistensi HPDB-KMZ"),
    (r"^HP_BERGESER", 4, "HP sama (no. rumah) tetapi koordinat bergeser", "S4_HP_BERGESER", "konsistensi HPDB-KMZ"),
    (r"^LAT_LONG_TERTUKAR", 4, "Latitude/longitude tertukar", "S4_LATLONG_TERTUKAR", "validasi koordinat"),
    (r"^HP_LUAR_FUNNEL", 5, "HP di luar boundary Funnel", "S5_HP_LUAR_FUNNEL",
     "toleransi GPS ponsel 4,9 m terbuka / 7-13 m urban (GPS.gov; PLOS ONE 2019)"),
    (r"^HP_LUAR_BOUNDARY", 5, "HP di luar BOUNDARY KMZ", "S5_HP_LUAR_BOUNDARY",
     "Standar Review Strand; lebih dari toleransi GPS ponsel 10 m (GPS.gov 4,9 m; PLOS ONE 2019 7-13 m urban)"),
    (r"^INFO_HP_TEPI_BOUNDARY", 5, "HP di tepi BOUNDARY KMZ (dalam toleransi GPS)", "I5_HP_TEPI_BOUNDARY",
     "toleransi GPS ponsel 10 m (GPS.gov 4,9 m langit terbuka; Merry & Bettinger, PLOS ONE 2019: 7-13 m urban)"),
    (r"^FUNNEL_SENDIRI_REJECT", 6, "Funnel cluster ini berstatus reject/drop", "S6_FUNNEL_REJECT", "status Funnel"),
    (r"^HP_SUDAH_ADA_DI_DESIGN_LITE", 6, "HP sudah ada di Design Lite (double tagging)", "S6_HP_DOUBLE_TAGGING",
     "Handbook: cek Design Lite agar tidak double tagging"),
    (r"^TIANG_BARU_SUDAH_ADA", 6, "Tiang baru sudah ada di jaringan existing", "S6_NP_SUDAH_ADA",
     "Handbook: cek Design Lite agar tidak double tagging"),
    (r"^INFO_HP_MUNGKIN_DI_DESIGN_LITE", 6, "HP dekat HP Design Lite (cek double tagging)", "I6_HP_DEKAT_DESIGN_LITE",
     "GPS ponsel 4,9 m (GPS.gov): 2-5 m = mungkin rumah yang sama"),
    (r"^INFO_TIANG_BARU_DEKAT_EXISTING", 6, "Tiang baru dekat tiang Design Lite", "I6_NP_DEKAT_EXISTING",
     "buffer 10 m pencocokan tiang (Zhang dkk., Sensors 2018; OSM Conflation)"),
    (r"^COLO_", 7, "Colo FDT", "S7_COLO", "Handbook colo <= 1 km (kebijakan internal)"),
    (r"^RENTANG_NP_NP", 9, "Rentang NP-NP > batas", "S9_RENTANG_NP_NP",
     "Handbook internal 60 m; regulasi daerah 50 m (Perwal Yogyakarta/Tangsel/Pekalongan)"),
    (r"^RENTANG_NP_EP", 9, "Rentang NP-EP > batas", "S9_RENTANG_NP_EP",
     "Handbook internal 60 m; posisi NP bisa digeser desainer"),
    (r"^BAKP_", 8, "BAKP perlu dicek", "S8_BAKP", "Standar Review Strand: izin warga"),
    (r"^INFO_BAKP_", 8, "BAKP (info)", "I8_BAKP", "Standar Review Strand: izin warga"),
    (r"^TIANG_NGANGGUR", None, "Tiang tidak dilewati jalur", "T_TIANG_NGANGGUR", "Handbook: tidak ada pole nganggur"),
    (r"^UJUNG_JALUR_TANPA_TIANG", None, "Ujung jalur tanpa tiang", "T_UJUNG_JALUR_TANPA_TIANG",
     "Handbook: jalur harus ada akses pole; praktik operator: tambat akhir di tiang"),
    (r"^WARN_BELOKAN_TANPA_TIANG", None, "Belokan >= 30 derajat tanpa tiang", "W_BELOKAN_TANPA_TIANG",
     "Handbook kasus 10 pole pada belokan; Buku pedoman konstruksi jaringan distribusi TR (2010): sudut > 30 derajat wajib tiang tambat"),
    (r"^WARN_SIMPANG_TANPA_TIANG", None, "Percabangan jalur tanpa tiang", "W_SIMPANG_TANPA_TIANG",
     "Handbook: jalur harus ada akses pole"),
    (r"^INFO_BELOKAN_KECIL_TANPA_TIANG", None, "Belokan kecil 15-30 derajat tanpa tiang", "I_BELOKAN_KECIL",
     "pedoman konstruksi jaringan distribusi: 15-30 derajat tiang sudut kecil (parameter rekayasa, perlu kalibrasi)"),
    (r"^WARN_RENTANG_REGULASI", 9, "Rentang 50-60 m (di atas regulasi daerah)", "W9_RENTANG_50_60M",
     "Perwal Yogyakarta 13/2018, Tangsel 47/2019, Pekalongan 21/2024; rancangan Permenkominfo 2018; pedoman konstruksi jaringan distribusi TR: maks 50 m"),
    (r"^INFO_RENTANG_REGULASI", 9, "Rentang 50-60 m (di atas regulasi daerah)", "W9_RENTANG_50_60M",
     "Perwal daerah maks 50 m"),
    (r"^UNV_BAKP", 8, "BAKP belum dapat diverifikasi", "U8_BAKP", "Standar Review Strand: izin warga"),
    (r"^INFO_HP_TEPI_FUNNEL", 5, "HP di tepi luar Funnel", "I5_HP_TEPI_FUNNEL", "toleransi GPS ponsel (GPS.gov)"),
    (r"^INFO_HP_ALAMAT_SAMA", 4, "HP dengan alamat lengkap sama", "I4_ALAMAT_SAMA", "konsistensi alamat"),
    (r"^INFO_HP_MUNGKIN_DUPLIKAT", 4, "Kemungkinan duplikat (<= 5 m, no rumah sama/kosong)", "I4_MUNGKIN_DUPLIKAT",
     "GPS ponsel 4,9 m terbuka (GPS.gov); 7-13 m urban (PLOS ONE 2019)"),
    (r"^INFO_KABEL_RENDAH", None, "Kabel rendah di tengah bentang (< batas ruang bebas)", "I_KABEL_RENDAH",
     "Permen PU 20/PRT/M/2010 Ps.12(6): >= 5 m di atas jalan; lendutan 2% (spesifikasi teknis FTTH operator nasional)"),
    (r"^INFO_TIANG_BISA_DIHAPUS", None, "Tiang NP bisa dihapus (jalan lurus)", "I_NP_BISA_DIHAPUS",
     "Handbook: pole di jalan lurus < 60 m boleh di take out"),
    (r"^INFO_UJUNG_JALUR_TANPA_HP", None, "Ujung jalur tanpa HP", "I_UJUNG_TANPA_HP",
     "Handbook: kabel loop <= 100 m / 2 span (kebijakan internal)"),
]


def _qc_entry(kind):
    for e in QC_LABELS:
        if re.match(e[0], kind):
            return e
    return None


def qc_label(kind):
    """(nomor standar atau None, label Indonesia) untuk kode temuan."""
    e = _qc_entry(kind)
    return (e[1], e[2]) if e else (None, kind.replace("INFO_", "").replace("_", " ").capitalize())


def qc_slug(kind):
    """Nama file kategori (tanpa ekstensi), mis. S9_RENTANG_NP_NP."""
    e = _qc_entry(kind)
    if e:
        return e[3]
    return ("I_" if kind.startswith("INFO_") else "T_") + re.sub(r"[^A-Z0-9]+", "_", kind.replace("INFO_", "").upper())[:30]


def qc_source(kind):
    e = _qc_entry(kind)
    return e[4] if e else ""


QC_DASAR = [  # (pola kode, kategori dasar) untuk kolom dasar_src
    (r"^(RENTANG|WARN_RENTANG|INFO_RENTANG)", "INTERNAL+REGULASI"), (r"^INFO_KABEL_RENDAH", "REGULASI"),
    (r"^(INFO_HP_MUNGKIN|INFO_HP_TEPI|HP_LUAR_FUNNEL|INFO_TIANG_BARU_DEKAT)", "RISET"),
    (r"^HP_LUAR_BOUNDARY", "INTERNAL+RISET"), (r"BELOKAN", "STANDAR"),
    (r"^ADMIN_", "DATA RESMI"), (r".", "INTERNAL")]


# Temuan yang perlu ditinjau tetapi belum tentu salah desain (bukan "wajib diperbaiki"):
# tiang survei yang belum dilewati jalur bisa jadi cadangan rute; keputusan ada di desain.
WARNING_KINDS = {"TIANG_NGANGGUR", "HP_BERGESER"}


def qc_severity(kind):
    """Kontrak keluaran QC (spesifikasi O.2): ERROR / WARNING / INFO / UNVERIFIED."""
    if kind.startswith("INFO_"):
        return "INFO"
    if kind.startswith("UNV_"):
        return "UNVERIFIED"
    if kind.startswith(("WARN_", "COLO_")) or kind in WARNING_KINDS:
        return "WARNING"
    return "ERROR"


def qc_status(kind):
    """Status lama (kompatibel 3.2.x): CEK untuk ERROR/WARNING, INFO untuk INFO/UNVERIFIED."""
    return "CEK" if qc_severity(kind) in ("ERROR", "WARNING") else "INFO"


def qc_dasar(kind):
    return next(d for rx, d in QC_DASAR if re.search(rx, kind))


def qc_item(it):
    """Normalisasi temuan -> (titik, kode, keterangan, garis atau None, nilai, batas)."""
    p, kind, ket = it[0], it[1], it[2]
    pts = it[3] if len(it) > 3 else None
    val = it[4] if len(it) > 4 else None
    lim = it[5] if len(it) > 5 else None
    return p, kind, ket, (pts if pts and len(pts) >= 2 else None), val, lim


def _short(t, n):
    t = " ".join(str(t).split())
    return t if len(t) <= n else t[:n - 1] + "…"


def qc_by_std(qc):
    """{nomor standar: [(status, jenis, keterangan)]} untuk ditampilkan di kartu standar (CEK dulu)."""
    out = {}
    for it in qc:
        _p, kind, ket = it[:3]
        no, lab = qc_label(kind)
        no = no or 0                       # 0 = temuan jalur/tiang umum (tanpa nomor standar)
        if True:
            p = it[0]
            out.setdefault(no, []).append((qc_severity(kind), lab, _short(ket, 220),
                                           round(p.y(), 7), round(p.x(), 7), kind))

    def meters(t):
        m = re.search(r"(\d+(?:\.\d+)?) m\b", t[2])
        return -float(m.group(1)) if m else 0.0
    for no, v in out.items():
        v.sort(key=lambda t: (_qc.SEV_RANK.get(t[0], 9), meters(t) if no in (1, 9) else 0))
    return out


def read_dbf(path, encoding="utf-8"):
    """Baca tabel .dbf (dBASE III) tanpa OGR -> daftar dict. Angka dikembalikan sebagai teks/float; NULL -> None."""
    import struct
    out = []
    with open(path, "rb") as fh:
        head = fh.read(32)
        n, hlen, rlen = struct.unpack("<IHH", head[4:12])
        fields = []
        while True:
            d = fh.read(32)
            if not d or d[0] == 0x0D:
                break
            fields.append((d[:11].split(b"\0")[0].decode("ascii", "replace"), chr(d[11]), d[16]))
        fh.seek(hlen)
        for _ in range(n):
            r = fh.read(rlen)
            if not r or r[:1] == b"*":
                continue
            o, rec = 1, {}
            for name, typ, ln in fields:
                raw = r[o:o + ln].decode(encoding, "replace").strip()
                o += ln
                if typ in "NF":
                    try:
                        rec[name] = float(raw) if raw and not raw.startswith("*") else None
                    except ValueError:
                        rec[name] = None
                else:
                    rec[name] = raw or None
            out.append(rec)
    return out


def qc_order(qc):
    """(items ternormalisasi, urutan) - urutan yang sama dipakai untuk ID temuan F-0001.. di QC_TEMUAN, HTML dan Word."""
    items = [qc_item(it) for it in qc]
    order = sorted(range(len(items)), key=lambda i_: (_qc.SEV_RANK.get(qc_severity(items[i_][1]), 9),
                                                     qc_label(items[i_][1])[0] or 99, qc_slug(items[i_][1])))
    return items, order


def qc_fid_map(qc):
    """{(kode, lon7, lat7, keterangan singkat): 'F-0001'} - kunci sama dengan qc_by_std untuk laporan HTML."""
    items, order = qc_order(qc)
    out = {}
    for n_, i_ in enumerate(order, 1):
        p, kind, ket = items[i_][0], items[i_][1], items[i_][2]
        out[(kind, round(p.x(), 7), round(p.y(), 7), _short(ket, 220))] = "F-%04d" % n_
    return out


def qc_counts(qc):
    """[(status, nomor standar, label, jumlah, contoh keterangan)] urut: CEK dulu, lalu nomor standar."""
    c = {}
    for it in qc:
        _p, kind, ket = it[:3]
        no, lab = qc_label(kind)
        key = (qc_severity(kind), no, lab)
        if key not in c:
            c[key] = [0, ket]
        c[key][0] += 1
    src = {}
    for it in qc:
        no, lab = qc_label(it[1])
        src.setdefault(lab, (qc_source(it[1]), qc_slug(it[1])))
    return sorted([(k[0], k[1], k[2], v[0], _short(v[1], 140), src[k[2]][0], src[k[2]][1]) for k, v in c.items()],
                  key=lambda t: (_qc.SEV_RANK.get(t[0], 9), t[1] or 99, t[2]))


def write_qc_kmz(path, title, qc):
    """QC_TEMUAN.kmz: folder 'PERLU DICEK' dan 'INFO', subfolder per jenis temuan (nomor standar + jumlah),
    ikon merah/kuning, garis merah untuk rentang, keterangan lengkap di balon."""
    import zipfile
    groups = {}
    for it in qc:
        p, kind, ket, pts, val, lim = qc_item(it)
        groups.setdefault(kind, []).append((p, ket, pts))

    def geom(p, pts):
        if pts:
            return "<LineString><tessellate>1</tessellate><coordinates>%s</coordinates></LineString>" % " ".join(
                "%.8f,%.8f,0" % (q.x(), q.y()) for q in pts)
        return "<Point><coordinates>%.8f,%.8f,0</coordinates></Point>" % (p.x(), p.y())

    def fold(info):
        ks = [k for k in groups if (qc_status(k) == "INFO") == info]
        ks.sort(key=lambda k: ((qc_label(k)[0] or 99), qc_label(k)[1]))
        out = []
        for k in ks:
            no, lab = qc_label(k)
            out.append("<Folder><name>%s%s (%d)</name>" % ("%d. " % no if no else "", _xe(lab), len(groups[k])))
            for p, ket, pts in groups[k]:
                sid = ("linfo" if info else "lcek") if pts else ("info" if info else "cek")
                out.append(
                    "<Placemark><name>%s</name><styleUrl>#%s</styleUrl><description><![CDATA[<b>%s</b><br>%s<br>"
                    "<small>tingkat: %s<br>dasar: %s<br>kode: %s</small>]]></description><ExtendedData><Data name=\"kode\"><value>%s</value>"
                    "</Data><Data name=\"severity\"><value>%s</value></Data></ExtendedData>%s</Placemark>" % (
                        _xe(_short(ket, 60)), sid, _xe(lab), _xe(_short(ket, 3000)).replace("]]>", "]] >"),
                        qc_severity(k), _xe(qc_source(k)), k, k, qc_severity(k), geom(p, pts)))
            out.append("</Folder>")
        n = sum(len(groups[k]) for k in ks)
        return ("<Folder><name>%s (%d)</name><open>%d</open>%s</Folder>" % (
            "INFO" if info else "PERLU DICEK", n, 0 if info else 1, "".join(out))) if ks else ""

    def style(sid, ic, sc):
        return ('<Style id="%s"><IconStyle><scale>%s</scale><Icon><href>%s</href></Icon>'
                '<hotSpot x="0.5" y="0" xunits="fraction" yunits="fraction"/></IconStyle>'
                '<LabelStyle><scale>0.7</scale></LabelStyle><ListStyle><ItemIcon><href>%s</href></ItemIcon>'
                '</ListStyle></Style>' % (sid, sc, kmz_icon(ic), kmz_icon(ic)))

    def lstyle(sid, col, w):
        return '<Style id="%s"><LineStyle><color>%s</color><width>%s</width></LineStyle></Style>' % (sid, col, w)
    kml = ('<?xml version="1.0" encoding="UTF-8"?>\n<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
           '<name>%s</name><open>1</open>%s%s%s%s%s%s</Document></kml>' % (
               _xe(title), style("cek", "pin_red", 0.9), style("info", "pin_yellow", 0.7),
               lstyle("lcek", "ff1c1ae3", 5), lstyle("linfo", "ff00d4ff", 4), fold(False), fold(True)))
    tmp = path + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("doc.kml", kml.encode("utf-8"))
        kmz_add_icons(z, kml)
    os.replace(tmp, path)


# ---------- Kode wilayah untuk penamaan hasil (aman untuk batch) ----------
GENERIC_DIR_RX = re.compile(r"^\s*(tes|test|testing|uji|coba|sample|contoh|new folder|folder( baru)?|data|input|"
                            r"cluster|baru)?[\s_-]*\d*\s*$", re.IGNORECASE)


def cluster_label(cluster_dir, hpdb_path=""):
    """Nama cluster untuk tampilan: nama folder, kecuali folder umum/uji ('TES 2') -> dari nama file HPDB."""
    nm = os.path.basename(cluster_dir.rstrip("\\/"))
    hb = os.path.splitext(os.path.basename(hpdb_path or ""))[0]
    if GENERIC_DIR_RX.match(nm) and hb:
        t = re.sub(r"^HP[ _-]?(?:DB|BD)[_\s-]+", "", hb, flags=re.IGNORECASE)
        t = re.sub(r"^[A-Za-z][A-Za-z ]*?[_\s-]+(?=\d{9,12})", "", t)
        t = re.sub(r"_\d+\s*HP(?![A-Za-z]).*$|_\d+_[A-Za-z.]+$", "", t, flags=re.IGNORECASE)
        t = re.sub(r"^\s*\d{9,12}[\s_-]*", "", t).strip(" _-")
        if re.search(r"[A-Za-z]{3}", t):
            return t
    return nm


def kode_wilayah(cluster_dir, hpdb_path=""):
    """Contoh: folder 'MARTOBA RW 002' + HPDB_SIANTAR_... -> 'SIANTAR_MARTOBA_RW_002'."""
    nm = os.path.basename(cluster_dir.rstrip("\\/"))
    hb = os.path.splitext(os.path.basename(hpdb_path or ""))[0]
    if GENERIC_DIR_RX.match(nm) and hb:
        # folder uji/umum ('TES 2', 'New folder', '01') -> nama cluster dari nama file HPDB:
        # HPDB_<KOTA>_<ID> <NAMA>_<n>HP_<vendor>  atau  HPDB_<ID> <NAMA>_<n>HP_<vendor>
        t = re.sub(r"^HP[ _-]?(?:DB|BD)[_\s-]+", "", hb, flags=re.IGNORECASE)
        t = re.sub(r"^[A-Za-z][A-Za-z ]*?[_\s-]+(?=\d{9,12})", "", t)       # kota (dipasang lagi di bawah)
        t = re.sub(r"_\d+\s*HP(?![A-Za-z]).*$|_\d+_[A-Za-z.]+$", "", t, flags=re.IGNORECASE)
        if re.search(r"[A-Za-z]{3}", t):
            nm = t
    # buang ID cluster (9-12 digit), jumlah HP (101HP) dan nama vendor (PT.xxx) agar kode pendek & stabil
    nm = re.sub(r"(?<!\d)\d{9,12}(?!\d)", " ", nm)
    nm = re.sub(r"(?<![0-9])\d+\s*HP(?![A-Za-z]).*$", " ", nm, flags=re.IGNORECASE)
    nm = re.sub(r"(?<![A-Za-z])PT[.\s_]+\S+.*$", " ", nm, flags=re.IGNORECASE)
    nm = re.sub(r"[_\s-]+\d{1,5}[_\s-]+[A-Za-z.]{2,8}\s*$", " ", nm)          # ..._244_XYZ (jumlah HP + kode vendor)
    nm = re.sub(r"^\s*(KOTA|KABUPATEN|KAB\.?)\s+", "", nm, flags=re.IGNORECASE)
    nm = re.sub(r"(?<![A-Za-z])PERUMAHAN(?![A-Za-z])", "PERUM", nm, flags=re.IGNORECASE)
    code = re.sub(r"[^A-Z0-9]+", "_", nm.upper()).strip("_") or "CLUSTER"
    m = re.match(r"HP[ _-]?(?:DB|BD)[_\s-]+([A-Za-z][A-Za-z ]*?)[_\s-]+\d", os.path.basename(hpdb_path or ""))
    if m:
        city = re.sub(r"[^A-Z0-9]+", "_", m.group(1).upper()).strip("_")
        if city and city not in code:
            code = city + "_" + code
    return _short_code(code, 40)


def _short_code(code, n):
    """Pendekkan kode (maks n karakter) dengan MEMPERTAHANKAN bagian akhir (nama area/RW yang paling spesifik),
    membuang kata depan (kota/kabupaten) lebih dulu, + 4 karakter sidik agar tetap unik."""
    if len(code) <= n:
        return code
    import hashlib
    words = [w for w in code.split("_") if w]
    keep = []
    for w in reversed(words):
        if len("_".join([w] + keep)) > n - 5:
            break
        keep.insert(0, w)
    cut = "_".join(keep) or code[-(n - 5):]
    return "%s_%s" % (cut, hashlib.sha256(code.encode()).hexdigest()[:4].upper())


# ---------- HPDB attributes (FINDIM kelurahan/kecamatan + OLT cluster) ----------
_ATTR_CACHE = {}
_ADM_DROP = re.compile(r"\b(KELURAHAN|KEL|DESA|KECAMATAN|KEC|KOTA|KOTAMADYA|KABUPATEN|KAB|ADM|ADMINISTRASI)\b\.?")
_SYN = (("SUMATRA", "SUMATERA"), ("DKI ", ""), ("DAERAH ISTIMEWA ", "DI "), ("NANGGROE ACEH DARUSSALAM", "ACEH"))


_NUM_W = {"NOL": 0, "SATU": 1, "DUA": 2, "TIGA": 3, "EMPAT": 4, "LIMA": 5, "ENAM": 6, "TUJUH": 7,
          "DELAPAN": 8, "SEMBILAN": 9, "SEPULUH": 10, "SEBELAS": 11}
_ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10,
          "XI": 11, "XII": 12, "XIII": 13, "XIV": 14, "XV": 15}


def _num_tokens(toks):
    """'TIGA PULUH LIMA' -> '35', 'DELAPAN BELAS' -> '18', 'II' -> '2' (agar 3 Ilir = TIGA ILIR)."""
    out, i = [], 0
    while i < len(toks):
        t = toks[i]
        if t in _NUM_W:
            n = _NUM_W[t]
            if i + 1 < len(toks) and toks[i + 1] == "BELAS":
                n, i = n + 10, i + 1
            elif i + 1 < len(toks) and toks[i + 1] == "PULUH":
                n, i = n * 10, i + 1
                if i + 1 < len(toks) and toks[i + 1] in _NUM_W and _NUM_W[toks[i + 1]] < 10:
                    n, i = n + _NUM_W[toks[i + 1]], i + 1
            out.append(str(n))
        elif t in _ROMAN and i > 0:
            out.append(str(_ROMAN[t]))
        else:
            out.append(t)
        i += 1
    return out


# singkatan nama wilayah yang lazim di HPDB (KP MELAYU = KAMPUNG MELAYU, TJ PRIOK = TANJUNG PRIOK, ...)
_ABBR = {"KP": "KAMPUNG", "KPG": "KAMPUNG", "KAMP": "KAMPUNG", "TJ": "TANJUNG", "TJG": "TANJUNG", "SEI": "SUNGAI",
         "SG": "SUNGAI", "SGI": "SUNGAI", "PSR": "PASAR", "PD": "PONDOK", "PDK": "PONDOK", "BT": "BATU",
         "BKT": "BUKIT", "LBK": "LUBUK", "LB": "LUBUK", "TLK": "TELUK", "SP": "SIMPANG", "SMPG": "SIMPANG",
         "KRG": "KARANG", "PLG": "PALEMBANG", "JKT": "JAKARTA", "SBY": "SURABAYA", "BDG": "BANDUNG",
         "UTR": "UTARA", "SLT": "SELATAN", "SEL": "SELATAN",
         "BRT": "BARAT", "TMR": "TIMUR", "TENG": "TENGAH", "TGH": "TENGAH", "KB": "KEBUN"}
_FINDIM_VER = 2       # naik bila adm_norm berubah (cache FINDIM di disk menyimpan nama yang sudah dinormalkan)


def adm_norm(v):
    v = " " + str(v or "").upper().replace("_", " ").replace("-", " ").replace(".", " ") + " "
    for a, b in _SYN:
        v = v.replace(a, b)
    v = _ADM_DROP.sub(" ", v)
    toks = [_ABBR.get(t, t) for t in re.findall(r"[A-Z0-9]+", v)]
    return "".join(_num_tokens(toks))


def load_attributes(path, feedback=None):
    """Baca sheet FINDIM (terbaru) dan OLT CLUSTER dari file hpdb_attributes*.xlsx.
    Hasil disimpan di memori selama QGIS terbuka (mode batch tidak membaca ulang)."""
    key = (path, os.path.getmtime(path), os.path.getsize(path))
    if key in _ATTR_CACHE:
        return _ATTR_CACHE[key]
    # cache disk: file FINDIM besar (puluhan detik dibaca), dibaca ulang hanya bila file berubah
    import hashlib
    cpath = None
    try:
        cpath = os.path.join(_cache_root(), "findim_%s.json.gz" % hashlib.sha256(
            ("%s|%d|%d|%d|%d" % (os.path.abspath(path).lower(), int(key[1]), key[2], _CACHE_VER, _FINDIM_VER)
             ).encode("utf-8")).hexdigest()[:16])
        if os.path.exists(cpath):
            att = _jload(cpath, gz=True)
            _ATTR_CACHE[key] = att
            return att
    except Exception:
        cpath = cpath if cpath else None
    import zipfile as _z
    with _z.ZipFile(path) as z:
        wbx = ET.parse(z.open("xl/workbook.xml")).getroot()  # nosec B314
        names = [sh.get("name") or "" for sh in wbx.iter() if _local(sh.tag) == "sheet"]
    fnd = [n for n in names if re.search(r"findim", n, re.IGNORECASE)]

    def yr(n):
        m = re.search(r"(20\d{2})", n)
        return int(m.group(1)) if m else 0
    fnd.sort(key=lambda n: -yr(n))
    pick = set(fnd[:1]) | {n for n in names if re.search(r"olt\s*cluster", n, re.IGNORECASE)}
    if feedback:
        feedback.pushInfo("Membaca HPDB attributes (%s): %s" % (os.path.basename(path), ", ".join(sorted(pick))))
    sheets = dict(read_xlsx(path, want=lambda n: n in pick, max_empty=500))
    att = {"findim": [], "olt": {}, "sheets": sorted(pick)}
    for n in fnd[:1]:
        rows = sheets.get(n, [])
        if not rows:
            continue
        h = [str(c).strip().lower() for c in rows[0]]

        def col(*cands):
            """Nama kolom persis, atau pola '<awalan operator>_<nama>' (mis. xxx_final_kelurahan)."""
            for c in cands:
                if c.startswith("*_"):
                    rx = re.compile(r"^[a-z0-9]+_" + re.escape(c[2:]) + r"$")
                    hit = next((i for i, x in enumerate(h) if rx.match(x)), None)
                    if hit is not None:
                        return hit
                elif c in h:
                    return h.index(c)
            return None
        ix = {k: col(*v) for k, v in {
            "id": ("id", "findim id"), "kel": ("*_final_kelurahan",), "kel2": ("kelurahan",),
            "kec": ("*_final_kecamatan",), "kec2": ("district",), "city": ("*_final_city",),
            "city2": ("city", "kabupaten_kotamadya"), "prov": ("*_final_province",), "prov2": ("propinsi",),
            "pos": ("*_kode_pos", "kode_pos"), "reg": ("*_region",), "fid": ("findim_id2", "findim_id")}.items()}

        def g(r, a, b=None):
            for k in (a, b):
                i = ix.get(k) if k else None
                if i is not None and i < len(r) and str(r[i]).strip() not in ("", "-", "None"):
                    return str(r[i]).strip()
            return ""
        for r in rows[1:]:
            kel = g(r, "kel", "kel2")
            if not kel:
                continue
            kv = {adm_norm(x) for x in (g(r, "kel"), g(r, "kel2")) if x}
            cv = {adm_norm(x) for x in (g(r, "kec"), g(r, "kec2")) if x}
            tv = {adm_norm(x) for x in (g(r, "city"), g(r, "city2")) if x}
            att["findim"].append({"id": g(r, "id"), "kel": kel, "kec": g(r, "kec", "kec2"),
                                  "kv": kv, "cv": cv, "tv": tv,
                                  "city": g(r, "city", "city2"), "prov": g(r, "prov", "prov2"),
                                  "pos": _clean_number(g(r, "pos")) if g(r, "pos") else "",
                                  "reg": g(r, "reg"), "fid": g(r, "fid"),
                                  "n_kel": adm_norm(kel), "n_kec": adm_norm(g(r, "kec", "kec2")),
                                  "n_city": adm_norm(g(r, "city", "city2")), "n_prov": adm_norm(g(r, "prov", "prov2"))})
    for n, rows in sheets.items():
        if re.search(r"olt\s*cluster", n, re.IGNORECASE):
            for r in rows[1:]:
                if len(r) >= 3 and r[0]:
                    att["olt"][_clean_number(r[0])] = (r[1], r[2])
    _ATTR_CACHE.clear()
    _ATTR_CACHE[key] = att
    if cpath:
        try:
            os.makedirs(os.path.dirname(cpath), exist_ok=True)
            _jdump(att, cpath + ".tmp", gz=True)
            os.replace(cpath + ".tmp", cpath)
        except Exception as _e:
            _log.note(_e)
    return att


def _admin_diff_txt(stt, diff, best, kel, kec, city, prov):
    """Kalimat jelas: kolom mana yang beda, tertulis apa, FINDIM apa."""
    if not best:
        return "kelurahan '%s' tidak ada di FINDIM" % (kel or "-")
    col = {"kota": ("KOTA", city, best["city"]), "kecamatan": ("KECAMATAN", kec, best["kec"]),
           "provinsi": ("PROVINSI", prov, best["prov"])}
    parts = ["%s tertulis '%s', FINDIM '%s'" % (col[d][0], col[d][1] or "-", col[d][2]) for d in diff if d in col]
    return ("(" + ", ".join(parts) + "; kelurahan '%s' sudah benar)" % kel) if parts else "(%s)" % stt


def check_admin(att, kel, kec, city, prov):
    """Cocokkan satu kombinasi kelurahan/kecamatan/kota/provinsi dengan FINDIM.
    Hasil: (status, baris_findim_terbaik, daftar_beda, saran)."""
    import difflib
    nk, nc, nt, np_ = adm_norm(kel), adm_norm(kec), adm_norm(city), adm_norm(prov)
    cands = [f for f in att["findim"] if nk in f["kv"]] if nk else []
    if not cands:
        pool = [f for f in att["findim"] if nt and nt in f["tv"]] or att["findim"]
        sug = difflib.get_close_matches(nk, list({f["n_kel"]: 1 for f in pool}), n=3, cutoff=0.75)
        names = []
        for sname in sug:
            f = next(f for f in pool if f["n_kel"] == sname)
            names.append("%s (Kec. %s, %s)" % (f["kel"], f["kec"], f["city"]))
        return "KELURAHAN_TIDAK_ADA", None, ["kelurahan"], names

    def score(f):
        return (nt in f["tv"]) * 4 + (nc in f["cv"]) * 2 + (f["n_prov"] == np_)
    best = max(cands, key=score)
    sug = []
    if nt and nt not in best["tv"]:
        # nama kelurahan sama ada di kota lain; cari yang mirip di kota yang ditulis HPDB
        pool = [f for f in att["findim"] if nt in f["tv"]]
        for sname in difflib.get_close_matches(nk, list({f["n_kel"]: 1 for f in pool}), n=3, cutoff=0.75):
            f = next(f for f in pool if f["n_kel"] == sname)
            sug.append("%s (Kec. %s, %s)" % (f["kel"], f["kec"], f["city"]))
    diff = []
    if nt and nt not in best["tv"]:
        diff.append("kota")
    if nc and nc not in best["cv"]:
        diff.append("kecamatan")
    if np_ and best["n_prov"] != np_:
        diff.append("provinsi")
    return ("OK" if not diff else "BEDA_" + "_".join(d.upper() for d in diff)), best, diff, sug


WGS84 = QgsCoordinateReferenceSystem("EPSG:4326")
M_PER_DEG = 111320.0  # perkiraan 1 derajat dalam meter (cukup untuk toleransi snap)


_KEEP_ALIVE = []   # post-processor harus tetap direferensikan Python sampai QGIS selesai memakainya


def release_old_outputs(root, markers=("INPUT", "HASIL_PASCA_DESAIN")):
    """Lepas layer hasil run sebelumnya (di bawah folder root) dari proyek supaya file tidak terkunci
    Windows saat ditimpa. Wajib dipanggil di thread utama (prepareAlgorithm)."""
    try:
        root_n = os.path.normcase(os.path.abspath(root))
        prj = QgsProject.instance()
        ids = []
        for lid, lyr in prj.mapLayers().items():
            src = (lyr.source() or "").split("|")[0]
            if not src:
                continue
            s = os.path.normcase(os.path.abspath(src))
            if s.startswith(root_n) and any(m.lower() in s.lower() for m in markers):
                ids.append(lid)
        if ids:
            prj.removeMapLayers(ids)
        return len(ids)
    except Exception:
        return 0


class FunnelStyler(QgsProcessingLayerPostProcessorInterface):
    """Boundary Funnel: hanya garis tepi (tanpa isi) agar HP/tiang di bawahnya tetap terlihat; warna per grup."""

    def postProcessLayer(self, layer, context, feedback):
        try:
            from qgis.core import (QgsCategorizedSymbolRenderer, QgsFillSymbol, QgsRendererCategory,
                                   QgsPalLayerSettings, QgsVectorLayerSimpleLabeling, QgsTextFormat)
            expr = ("CASE WHEN upper(\"grup\") LIKE 'RFS DONE%' THEN 'done' "
                    "WHEN upper(\"status\") LIKE '%REJECT%' OR upper(\"status\") LIKE '%DROP%' THEN 'reject' ELSE 'funnel' END")
            cats = []
            for val, col, txt in (("funnel", "#7b3294", "Boundary Funnel"), ("done", "#d7191c", "RFS DONE (terbangun)"),
                                  ("reject", "#9e9e9e", "Funnel reject/drop (diabaikan)")):
                sym = QgsFillSymbol.createSimple({"color": "0,0,0,0", "outline_color": col, "outline_width": "0.7",
                                                  "outline_style": "dash" if val == "reject" else "solid"})
                cats.append(QgsRendererCategory(val, sym, txt))
            layer.setRenderer(QgsCategorizedSymbolRenderer(expr, cats))
            pal = QgsPalLayerSettings()
            pal.fieldName = "Name"
            fmt = QgsTextFormat()
            fmt.setSize(7)
            pal.setFormat(fmt)
            layer.setLabeling(QgsVectorLayerSimpleLabeling(pal))
            layer.setLabelsEnabled(True)
            layer.triggerRepaint()
        except Exception as e:
            if feedback:
                feedback.reportError("Gaya Funnel tidak diterapkan: %s" % e, fatalError=False)


class FdtStyler(QgsProcessingLayerPostProcessorInterface):
    """Warna FDT: hijau bisa colo, oranye kurang, merah penuh/cek data, biru dipakai cluster ini,
    abu di luar batas; label kode + sisa. Dijalankan QGIS di thread utama setelah layer dimuat."""

    def postProcessLayer(self, layer, context, feedback):
        try:
            from qgis.core import (QgsCategorizedSymbolRenderer, QgsMarkerSymbol, QgsRendererCategory,
                                   QgsPalLayerSettings, QgsVectorLayerSimpleLabeling, QgsTextFormat)
            expr = ("CASE WHEN \"status\" = 'BISA COLO' THEN 'bisa' WHEN \"status\" LIKE 'KURANG%' THEN 'kurang' "
                    "WHEN \"status\" LIKE 'DI LUAR%' THEN 'luar' WHEN \"status\" LIKE 'SUDAH%' THEN 'sendiri' "
                    "ELSE 'penuh' END")
            cats = []
            for val, col, txt in (("bisa", "#1a9641", "Bisa colo"), ("kurang", "#fdae61", "Sisa kurang"),
                                  ("penuh", "#d7191c", "Penuh / cek data"), ("sendiri", "#2b83ba", "Dipakai cluster ini"),
                                  ("luar", "#9e9e9e", "Di luar batas colo")):
                sym = QgsMarkerSymbol.createSimple({"name": "square", "color": col, "size": "4",
                                                   "outline_color": "#000000"})
                cats.append(QgsRendererCategory(val, sym, txt))
            layer.setRenderer(QgsCategorizedSymbolRenderer(expr, cats))
            pal = QgsPalLayerSettings()
            pal.isExpression = True
            # label hanya FDT yang relevan (bisa colo / sisa kurang / dipakai cluster ini) agar peta tidak penuh tulisan
            pal.fieldName = ('CASE WHEN "status" = \'BISA COLO\' OR "status" LIKE \'KURANG%\' OR "status" LIKE \'SUDAH%\' '
                             'THEN "label" ELSE NULL END')
            fmt = QgsTextFormat()
            fmt.setSize(8)
            pal.setFormat(fmt)
            layer.setLabeling(QgsVectorLayerSimpleLabeling(pal))
            layer.setLabelsEnabled(True)
            layer.triggerRepaint()
        except Exception as e:
            if feedback:
                feedback.reportError("Gaya FDT tidak diterapkan: %s" % e, fatalError=False)


def style_qc_layer(layer):
    """Gaya temuan QC: merah = perlu dicek, kuning = info; garis tebal untuk rentang; label = keterangan singkat;
    tooltip = keterangan + dasar aturan. Layer ditandai agar dikenali panel Navigator QC Seranta."""
    from qgis.core import (QgsCategorizedSymbolRenderer, QgsMarkerSymbol, QgsLineSymbol, QgsRendererCategory,
                           QgsPalLayerSettings, QgsVectorLayerSimpleLabeling, QgsTextFormat, QgsTextBufferSettings)
    is_line = QgsWkbTypes.geometryType(layer.wkbType()) == _enum("Qgis.GeometryType.Line", "QgsWkbTypes.LineGeometry")
    cats = []
    key = "severity" if layer.fields().indexOf("severity") >= 0 else "status"
    try:
        kodes = {str(v) for v in layer.uniqueValues(layer.fields().indexOf("kode"))} if layer.fields().indexOf("kode") >= 0 else set()
    except Exception:
        kodes = set()
    low_cable = bool(kodes) and all(k.startswith("INFO_KABEL") for k in kodes)
    try:
        present = {str(v) for v in layer.uniqueValues(layer.fields().indexOf(key))}
    except Exception:
        present = set()
    table = ((("ERROR", "#e31a1c", 3.6, "ERROR - wajib diperbaiki"), ("WARNING", "#ff7f00", 3.2, "WARNING - perlu ditinjau"),
              ("UNVERIFIED", "#8c8c8c", 3.0, "UNVERIFIED - data belum cukup"), ("INFO", "#ffd000", 2.6, "INFO"))
             if key == "severity" else (("CEK", "#e31a1c", 3.6, "Perlu dicek"), ("INFO", "#ffb000", 2.6, "Info")))
    for val, col, size, txt in table:
        if present and val not in present:
            continue
        if is_line:
            props = {"color": col, "width": "1.4" if val in ("CEK", "ERROR", "WARNING") else "1.0", "capstyle": "round"}
            if low_cable:
                props.update({"line_style": "dash", "width": "0.8"})     # catatan tinggi kabel: garis putus tipis
            sym = QgsLineSymbol.createSimple(props)
        else:
            sym = QgsMarkerSymbol.createSimple({"name": "circle", "color": col, "size": str(size),
                                                "outline_color": "#ffffff"})
        cats.append(QgsRendererCategory(val, sym, txt))
    layer.setRenderer(QgsCategorizedSymbolRenderer(key, cats))
    pal = QgsPalLayerSettings()
    pal.isExpression = True
    # label garis dibedakan agar tidak terbaca menyatu: tinggi kabel di BAWAH garis, panjang bentang di ATAS garis
    pal.fieldName = ('CASE WHEN "kode" LIKE \'INFO_KABEL%\' THEN \'kabel ±\' || format_number("nilai", 1) || \' m dari tanah\' '
                     'WHEN "kode" LIKE \'%RENTANG%\' THEN \'bentang \' || format_number("nilai", 1) || \' m\' '
                     'WHEN "nilai" IS NOT NULL THEN format_number("nilai", 1) || \' m\' ELSE "jenis" END') \
        if is_line else '"jenis"'
    fmt = QgsTextFormat()
    fmt.setSize(7.5)
    buf = QgsTextBufferSettings()
    buf.setEnabled(True)
    buf.setSize(0.8)
    fmt.setBuffer(buf)
    pal.setFormat(fmt)
    try:
        pal.placement = _enum("Qgis.LabelPlacement.Line", "QgsPalLayerSettings.Line") if is_line else pal.placement
    except Exception as _e:
        _log.note(_e)
    if is_line:
        try:
            side = _enum("Qgis.LabelLinePlacementFlag.BelowLine", "QgsPalLayerSettings.BelowLine") if low_cable else \
                _enum("Qgis.LabelLinePlacementFlag.AboveLine", "QgsPalLayerSettings.AboveLine")
            flags = side | _enum("Qgis.LabelLinePlacementFlag.MapOrientation", "QgsPalLayerSettings.MapOrientation")
            if hasattr(pal, "lineSettings"):
                pal.lineSettings().setPlacementFlags(flags)
            else:
                pal.placementFlags = int(flags)
            pal.dist = 1.2
            if low_cable:
                from qgis.PyQt.QtGui import QColor
                fmt.setColor(QColor("#7a5c00"))
                pal.setFormat(fmt)
        except Exception as _e:
            _log.note(_e)
    layer.setLabeling(QgsVectorLayerSimpleLabeling(pal))
    layer.setLabelsEnabled(True)
    try:
        layer.setMapTipTemplate("<b>[% \"jenis\" %]</b> ([% \"severity\" %])<br>[% \"keterangan\" %]<br>"
                                "<i>dasar: [% \"dasar\" %]</i><br>review: [% \"review\" %]")
        layer.setDisplayExpression('"keterangan"')
        layer.setCustomProperty("seranta_qc", "1")
    except Exception as _e:
        _log.note(_e)
    return True


class QcStyler(QgsProcessingLayerPostProcessorInterface):
    """Terapkan gaya temuan QC saat layer dimuat dan kumpulkan semua kategori di sub-grup 'QC TEMUAN'."""
    def __init__(self, group=None, name=None):
        super().__init__()
        self.group = group
        self.name = name

    def postProcessLayer(self, layer, context, feedback):
        try:
            if self.name:
                layer.setName(self.name)      # nama jelas, mis. "S9 Rentang NP-NP > batas (4)"
            style_qc_layer(layer)
            layer.triggerRepaint()
        except Exception as e:
            if feedback:
                feedback.reportError("Gaya QC_TEMUAN tidak diterapkan: %s" % e, fatalError=False)
        try:
            root = QgsProject.instance().layerTreeRoot()
            node = root.findLayer(layer.id())
            if node is None:
                return
            parent = node.parent()
            sub = parent.findGroup("QC TEMUAN") or parent.insertGroup(0, "QC TEMUAN")
            if parent is not sub:
                sub.addChildNode(node.clone())
                parent.removeChildNode(node)
            # urutan: standar (S1..S9) dulu, lalu temuan tiang/jalur, lalu Info
            kids = list(sub.children())

            def rank(n):
                nm = n.name()
                return (nm.startswith("Info"), not nm.startswith("S"), nm)
            if [k.name() for k in kids] != [k.name() for k in sorted(kids, key=rank)]:
                for k in sorted(kids, key=rank):
                    sub.addChildNode(k.clone())
                for k in kids:
                    sub.removeChildNode(k)
            sub.setExpanded(True)
        except Exception as _e:
            _log.note(_e)


class PoleStyler(QgsProcessingLayerPostProcessorInterface):
    """Tiang di peta QGIS: NP merah (per tinggi), EP hitam, label nama tiang."""
    def postProcessLayer(self, layer, context, feedback):
        try:
            from qgis.core import (QgsCategorizedSymbolRenderer, QgsMarkerSymbol, QgsRendererCategory,
                                   QgsPalLayerSettings, QgsVectorLayerSimpleLabeling, QgsTextFormat)
            vals = sorted({f["folder"] for f in layer.getFeatures()}, key=lambda v: (v == "EP", _natkey(v)))
            reds = ["#d7191c", "#e8590c", "#a50f15", "#f03b20", "#bd0026"]
            cats = []
            for i, v in enumerate(vals):
                if v == "EP":
                    sym = QgsMarkerSymbol.createSimple({"name": "square", "color": "#000000", "size": "2.6",
                                                       "outline_color": "#ffffff"})
                    lab = "EP (tiang existing)"
                else:
                    sym = QgsMarkerSymbol.createSimple({"name": "circle", "color": reds[i % len(reds)], "size": "2.8",
                                                       "outline_color": "#ffffff"})
                    lab = v.replace("NP/", "NP ")
                cats.append(QgsRendererCategory(v, sym, lab))
            layer.setRenderer(QgsCategorizedSymbolRenderer("folder", cats))
            pal = QgsPalLayerSettings()
            pal.fieldName = "Name"
            fmt = QgsTextFormat()
            fmt.setSize(7)
            pal.setFormat(fmt)
            layer.setLabeling(QgsVectorLayerSimpleLabeling(pal))
            layer.setLabelsEnabled(True)
            layer.triggerRepaint()
        except Exception as e:
            if feedback:
                feedback.reportError("Gaya POLE tidak diterapkan: %s" % e, fatalError=False)


class BuatInputDesain(QgsProcessingAlgorithm):
    HPDB = "HPDB"
    POLE = "POLE"
    ROADS = "ROADS"
    OUTDIR = "OUTDIR"
    SNAP = "SNAP"
    SPAN = "SPAN"
    HPPOLE = "HPPOLE"
    REFILL = "REFILL"
    WORKDIR = "WORKDIR"
    CLUSTER_KMZ = "CLUSTER_KMZ"
    FUNNEL = "FUNNEL"
    COLO_MAX = "COLO_MAX"
    PROFILE = "PROFILE"
    OPEN_REPORT = "OPEN_REPORT"
    COLO_LOG = "COLO_LOG"
    NAMING = "NAMING"
    EXIST_SPAN = "EXIST_SPAN"          # lama (<= 3.1.x), tidak dipakai lagi
    SPAN_SCOPE = "SPAN_SCOPE"
    SPAN_SCOPE_OPTS = ["NP-NP dan NP-EP (disarankan: posisi NP bisa digeser desainer)", "Hanya NP-NP"]
    HP_TOL = "HP_TOL"
    BAKP = "BAKP"
    BAKP_FILE = "BAKP_FILE"
    QC_PROF = "QC_PROF"
    QC_PROF_OPTS = ["Handbook internal: rentang > 60 m ERROR, 50-60 m WARNING regulasi daerah (disarankan)",
                    "Perwal ketat: rentang > 50 m ERROR, ruang bebas kabel 6 m (mis. Pekalongan, Yogyakarta)"]
    COLO_BASIS = "COLO_BASIS"
    COLO_BASIS_OPTS = ["Garis lurus FDT ke tiang cluster terdekat (titik masuk)",
                       "Estimasi panjang kabel FDT ke HP terjauh (titik masuk + sepanjang jalur cluster)"]
    FUN_TOL = "FUN_TOL"
    NAMING_OPTS = ["Per wilayah: INPUT_<KODE>/<KODE>_HP.shp (aman untuk batch)",
                   "Standar SOP: INPUT/HP.shp, POLE.kmz, ROADS.shp"]

    # ---------- metadata ----------
    def tr(self, s):
        return QCoreApplication.translate("BuatInputDesain", s)

    def createInstance(self):
        return BuatInputDesain()

    def name(self):
        return "buat_input_desain_apd"

    def displayName(self):
        return self.tr("1. Siapkan Input Desain Otomatis + QC Survei")

    def group(self):
        return self.tr("FTTH Design")

    def groupId(self):
        return "ftth_design"

    def shortDescription(self):
        return self.tr("HPDB + KMZ vendor -> HP.shp, POLE.kmz, ROADS.shp untuk desain otomatis, plus QC 9 standar.")

    def shortHelpString(self):
        return self.tr(
            "<p><b>%s</b> v%s &copy; %s</p>"
            "<p><b>Cara pakai (3 langkah)</b></p><ol>"
            "<li><b>Folder cluster</b>: pilih folder yang berisi file HPDB (*.xlsx) dan KMZ vendor. "
            "Untuk banyak cluster sekaligus, pilih folder induknya.</li>"
            "<li><b>Folder data referensi</b> (sekali saja, diingat): boundary/Funnel layanan (*FUNNEL*.kmz), "
            "jaringan existing (DESIGN LITE*.kmz), HPDB attributes/FINDIM (*attributes*.xlsx), dan bila ada "
            "config desain otomatis (*.sdproj); .kmz/.kml, boleh di subfolder. File terbaru dipilih otomatis. "
            "Data ini milik tim, <b>tidak ikut di dalam plugin</b>: tiap pengguna perlu salinannya. "
            "Bila kosong, Seranta mencari otomatis di sekitar folder cluster.</li>"
            "<li>Klik <b>Run</b>. Ringkasan QC (HTML) terbuka otomatis; file input desain otomatis ada di subfolder "
            "<code>INPUT_&lt;KODE&gt;</code>.</li></ol>"
            "<p><b>Yang dicek (9 standar)</b>: 1 jarak HP-tiang &le; 50 m, 2 boundary/RFS lain, 3 wilayah sheet HP vs "
            "FINDIM, 4 HPDB vs KMZ + HP duplikat (pasti &amp; kemungkinan &le; 3 m), 5 HP di luar Funnel, 6 status desain, "
            "7 colo FDT existing (jarak + sisa splitter + total HP FDT), 8 <b>pengingat BAKP</b>, 9 jarak tiang NP "
            "&le; 60 m <b>sepanjang jalur</b> (NP-NP &amp; NP-EP; EP-EP tidak dinilai; 50-60 m = info regulasi daerah).</p>"
            "<p><b>Temuan per kategori</b>: folder <code>QC</code> berisi satu shp per jenis temuan (rentang tiang berupa "
            "garis mengikuti jalur). Buka <b>Vector &rsaquo; Seranta &rsaquo; Navigator QC</b> lalu klik temuan untuk langsung "
            "menuju lokasinya. Setelah itu jalankan <b>2. Alokasi FDT &amp; FAT</b> untuk estimasi FAT (HP/16) dan FDT.</p>"
            "<p>Juga: tinggi kabel tengah bentang, tiang yang bisa dihapus, ujung jalur tanpa HP. Dasar teknis tiap "
            "aturan ada di DASAR_ATURAN.md.</p>"
            "<p>Pengaturan lain (penamaan, batas jarak, colo) ada di bagian <b>Advanced</b>; nilai bawaan sudah "
            "sesuai praktik umum. Arti setiap isian dijelaskan di <b>Vector &gt; Seranta &gt; Handbook Seranta</b>.</p>"
            % (__product__, __version__, __author__))

    def helpUrl(self):
        from qgis.PyQt.QtCore import QUrl
        return QUrl.fromLocalFile(os.path.join(os.path.dirname(__file__), "help", "handbook.html")).toString()

    # ---------- parameters ----------
    def _adv(self, prm):
        """Tandai parameter sebagai 'Advanced' supaya form utama tetap ringkas."""
        prm.setFlags(prm.flags() | ADVANCED_FLAG)
        self.addParameter(prm)

    def initAlgorithm(self, config=None):
        # Form utama hanya 5 isian; sisanya di "Advanced" dengan nilai bawaan yang aman.
        self.addParameter(QgsProcessingParameterFile(
            self.OUTDIR, self.tr("1. Folder cluster (berisi HPDB + KMZ) atau folder induk untuk banyak cluster"),
            behavior=FOLDER_BEHAVIOR))
        try:                     # isi otomatis dengan folder referensi terakhir (juga dari versi lama)
            st_ = QgsSettings()
            last_ref = (st_.value("seranta/ref_dir", "")
                        or st_.value("seranta/funnel_dir", "") or "")
            last_ref = last_ref if last_ref and os.path.isdir(last_ref) else None
        except Exception:
            last_ref = None
        self.addParameter(QgsProcessingParameterFile(
            self.FUNNEL, self.tr("2. Folder data referensi tim: *FUNNEL*, DESIGN LITE, attributes (diingat; kosong = cari otomatis)"),
            behavior=FOLDER_BEHAVIOR, optional=True, defaultValue=last_ref))
        self.addParameter(QgsProcessingParameterEnum(
            self.PROFILE, self.tr("3. Profil proyek (otomatis dari config desain otomatis .sdproj bila ada)"),
            options=[pp["name"] for pp in PROFILES], defaultValue=0))
        self.addParameter(QgsProcessingParameterEnum(
            self.QC_PROF, self.tr("4. Standar aturan tiang (regulasi daerah)"), options=self.QC_PROF_OPTS, defaultValue=0))
        self.addParameter(QgsProcessingParameterEnum(
            self.BAKP, self.tr("Pengingat BAKP (izin warga)"), options=_bakp.MODES, defaultValue=0))
        self.addParameter(QgsProcessingParameterBoolean(
            self.OPEN_REPORT, self.tr("Buka ringkasan QC setelah selesai"), defaultValue=True))
        self._adv(QgsProcessingParameterEnum(
            self.NAMING, self.tr("Penamaan hasil"), options=self.NAMING_OPTS, defaultValue=0))
        self._adv(QgsProcessingParameterFile(
            self.WORKDIR, self.tr("Salin juga ke folder kerja desain otomatis (tiap cluster punya subfolder sendiri)"),
            behavior=FOLDER_BEHAVIOR, optional=True))
        self._adv(QgsProcessingParameterFile(
            self.HPDB, self.tr("Opsional: file HPDB (kosongkan = dicari otomatis)"),
            behavior=FILE_BEHAVIOR, optional=True,
            fileFilter="HPDB (*.xlsx *.xls *.csv)"))
        self._adv(QgsProcessingParameterFile(
            self.CLUSTER_KMZ, self.tr("Opsional: KMZ cluster (kosongkan = dicari otomatis)"),
            behavior=FILE_BEHAVIOR, optional=True,
            fileFilter="KMZ/KML (*.kmz *.kml)"))
        self._adv(QgsProcessingParameterFile(
            self.POLE, self.tr("Lanjutan: KMZ tiang terpisah (menggantikan KMZ cluster)"),
            behavior=FILE_BEHAVIOR, optional=True,
            fileFilter="KMZ/KML (*.kmz *.kml)"))
        self._adv(QgsProcessingParameterFile(
            self.ROADS, self.tr("Lanjutan: KMZ jalur terpisah (menggantikan KMZ cluster)"),
            behavior=FILE_BEHAVIOR, optional=True,
            fileFilter="KMZ/KML (*.kmz *.kml)"))
        self._adv(QgsProcessingParameterNumber(
            self.SNAP, self.tr("Toleransi snap jalur ke tiang (meter)"),
            type=NUM_DOUBLE, defaultValue=10.0, minValue=0.1))
        self._adv(QgsProcessingParameterNumber(
            self.SPAN, self.tr("Batas jarak tiang ke tiang (meter)"),
            type=NUM_DOUBLE, defaultValue=60.0, minValue=1))
        self._adv(QgsProcessingParameterNumber(
            self.HPPOLE, self.tr("Batas jarak homepass ke tiang terdekat (meter)"),
            type=NUM_DOUBLE, defaultValue=50.0, minValue=1))
        self._adv(QgsProcessingParameterBoolean(
            self.REFILL, self.tr("Isi ulang kolom Homepass_ID_Partner dengan H00001, H00002, ..."),
            defaultValue=True))
        self._adv(QgsProcessingParameterEnum(
            self.SPAN_SCOPE, self.tr("Rentang yang dinilai jaraknya (EP-EP tiang pihak lain tidak dinilai)"),
            options=self.SPAN_SCOPE_OPTS, defaultValue=0))
        self._adv(QgsProcessingParameterNumber(
            self.FUN_TOL, self.tr("HP di luar Funnel tapi <= jarak ini dari tepi = info 'tepi' (meter; 0 = ketat)"),
            type=NUM_DOUBLE, defaultValue=15.0, minValue=0))
        self._adv(QgsProcessingParameterFile(
            self.BAKP_FILE, self.tr("Opsional: file BAKP bila namanya tidak memuat kata 'BAKP' (kosong = dicari otomatis)"),
            behavior=FILE_BEHAVIOR, optional=True, fileFilter="BAKP (*.pdf *.jpg *.jpeg *.png)"))
        self._adv(QgsProcessingParameterNumber(
            self.HP_TOL, self.tr("Toleransi cocok HP di HPDB vs HP di KMZ (meter)"),
            type=NUM_DOUBLE, defaultValue=5.0, minValue=0.1))
        self._adv(QgsProcessingParameterNumber(
            self.COLO_MAX, self.tr("Colo: batas jarak FDT existing ke cluster (meter)"),
            type=NUM_DOUBLE, defaultValue=1000.0, minValue=50))
        self._adv(QgsProcessingParameterEnum(
            self.COLO_BASIS, self.tr("Colo: dasar jarak yang dibandingkan dengan batas jarak"),
            options=self.COLO_BASIS_OPTS, defaultValue=0))
        self._adv(QgsProcessingParameterBoolean(
            self.COLO_LOG, self.tr("Colo: catat rencana colo cluster ini ke COLO_RENCANA.csv (cegah rebutan FDT)"),
            defaultValue=True))

    # ---------- helpers ----------
    @staticmethod
    def _norm(s):
        return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())

    def _pick_sheet(self, sheets):
        """Pilih sheet HPDB dari daftar (nama, baris)."""
        best = None
        for name, rows in sheets:
            hdr = self._find_header(rows)
            if hdr is None:
                continue
            hn = [self._norm(c) for c in rows[hdr]]
            score = 1
            if "HOMEPASSLATITUDE" in hn and "HOMEPASSLONGITUDE" in hn:
                score += 4   # sheet HPDB template operator, bukan sheet Pole
            if re.search(r"HP|HOMEPASS|ROW TO COLUMN", (name or "").upper()):
                score += 2
            score += min(len(rows), 100000) / 1e6
            if best is None or score > best[0]:
                best = (score, name, rows, hdr)
        return best

    def _read_table(self, path, feedback):
        """Baca semua baris HPDB sebagai teks, tanpa menebak header."""
        ext = os.path.splitext(path)[1].lower()
        if ext in (".xlsx", ".xlsm"):
            # Pembaca bawaan skrip: kebal terhadap sel liar di baris ke-1 juta
            # (GDAL menolak file seperti itu: "Too big gap with previous valid row").
            try:
                sheets = read_xlsx(path)
            except Exception as e:
                raise QgsProcessingException("HPDB tidak bisa dibaca (%s): %s" % (type(e).__name__, e))
        else:
            sheets = []
            saved = {}
            for k, v in (("OGR_XLS_HEADERS", "DISABLE"), ("OGR_XLS_FIELD_TYPES", "STRING")):
                saved[k] = gdal.GetConfigOption(k)
                gdal.SetConfigOption(k, v)
            try:
                if ext == ".csv":
                    ds = gdal.OpenEx(path, gdal.OF_VECTOR,
                                     open_options=["HEADERS=NO", "AUTODETECT_TYPE=NO"])
                else:
                    ds = gdal.OpenEx(path, gdal.OF_VECTOR)
                if ds is None:
                    raise QgsProcessingException("HPDB tidak bisa dibuka: %s" % path)
                for li in range(ds.GetLayerCount()):
                    lyr = ds.GetLayer(li)
                    rows, empty = [], 0
                    for f in lyr:
                        r = ["" if f.GetField(i) is None else str(f.GetField(i)).strip()
                             for i in range(f.GetFieldCount())]
                        rows.append(r)
                        empty = 0 if any(r) else empty + 1
                        if empty >= 200 or feedback.isCanceled():
                            break
                    sheets.append((lyr.GetName(), rows))
                ds = None
            finally:
                for k, v in saved.items():
                    gdal.SetConfigOption(k, v)
        self._sheets = sheets
        best = self._pick_sheet(sheets)
        if best is None:
            raise QgsProcessingException(
                "Tidak menemukan baris header berisi kolom LATITUDE dan LONGITUDE di HPDB.")
        self._hp_sheet = best[1]
        feedback.pushInfo("Sheet HPDB: %s, header di baris %d" % (best[1], best[3] + 1))
        return best[2], best[3]

    def _find_header(self, rows):
        for i, r in enumerate(rows[:20]):
            n = [self._norm(c) for c in r]
            if any("LATITUDE" in c for c in n) and any("LONGITUDE" in c for c in n):
                return i
        return None

    def _pick_rx(self, headers, rx, skip=()):
        """Indeks kolom pertama yang nama ternormalisasinya cocok regex (mis. ID homepass operator apa pun)."""
        for i, h in enumerate(headers):
            if i not in skip and re.match(rx, self._norm(h)):
                return i
        return None

    def _pick(self, headers, exact, contains):
        n = [self._norm(h) for h in headers]
        for e in exact:
            if self._norm(e) in n:
                return n.index(self._norm(e))
        for i, h in enumerate(n):
            if contains in h:
                return i
        return None

    @staticmethod
    def _num(s):
        try:
            return float(str(s).replace(",", ".").strip())
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _walk(g, pts, lines):
        t = ogr.GT_Flatten(g.GetGeometryType())
        if t == ogr.wkbPoint:
            pts.append(QgsPointXY(g.GetX(), g.GetY()))
        elif t == ogr.wkbLineString:
            line = [QgsPointXY(g.GetX(i), g.GetY(i)) for i in range(g.GetPointCount())]
            if len(line) >= 2:
                lines.append(line)
        elif t in (ogr.wkbMultiPoint, ogr.wkbMultiLineString, ogr.wkbGeometryCollection):
            for i in range(g.GetGeometryCount()):
                BuatInputDesain._walk(g.GetGeometryRef(i), pts, lines)

    def _read_kml(self, path):
        ds = ogr.Open(path)
        if ds is None:
            raise QgsProcessingException("KMZ/KML tidak bisa dibuka: %s" % path)
        pts, lines, names, nlayers = [], [], [], ds.GetLayerCount()
        for li in range(nlayers):
            lyr = ds.GetLayer(li)
            for f in lyr:
                g = f.GetGeometryRef()
                if g is None:
                    continue
                before = len(pts)
                self._walk(g, pts, lines)
                nm = f.GetField("Name") if f.GetFieldIndex("Name") >= 0 else ""
                names.extend([nm or ""] * (len(pts) - before))
        ds = None
        return pts, lines, names, nlayers

    @staticmethod
    def _write(layer, path, driver, context):
        opts = QgsVectorFileWriter.SaveVectorOptions()
        opts.driverName = driver
        opts.fileEncoding = "UTF-8"
        err = QgsVectorFileWriter.writeAsVectorFormatV3(
            layer, path, context.transformContext(), opts)
        if err[0] != WRITER_OK:
            raise QgsProcessingException("Gagal menulis %s: %s" % (path, err[1]))

    # ---------- main ----------
    def prepareAlgorithm(self, parameters, context, feedback):
        root = self.parameterAsFile(parameters, self.OUTDIR, context)
        if root and os.path.isdir(root):
            n = release_old_outputs(root)
            if n:
                feedback.pushInfo(f"{n} layer hasil run sebelumnya dilepas dari proyek agar file bisa ditimpa.")
        return True

    @staticmethod
    def _qc_word(qc, outp, inp, kode, cluster, std, judul, poles, names, kinds, hp_xy, segs, own_bnd, funnel_polys, feedback,
                 max_img=80, hp_attrs=None, heights=None):
        """Gambar peta per temuan (folder QC_GAMBAR) dan laporan Word <KODE>_LAPORAN_QC.docx.
        Kembali (nama file Word, {F-0001: data URI})."""
        import math
        from . import snapshot as _snap
        from . import docx_writer as _docx
        from . import penjelasan as X
        if not qc:
            return None, {}, None
        sc = _snap.Scene()
        for f in segs:
            try:
                g = f.geometry()
                parts = g.asMultiPolyline() if g.isMultipart() else [g.asPolyline()]
            except Exception:
                parts = []
            for part in parts:
                pts_ = [(q.x(), q.y()) for q in part]
                L_ = sum(math.hypot((b[0] - a[0]) * 111320.0 * math.cos(math.radians(a[1])), (b[1] - a[1]) * 110574.0)
                         for a, b in zip(pts_, pts_[1:]))
                sc.add_line(pts_, "route", {"Jenis": "Ruas jalur (ROADS)", "Panjang ruas (m)": "%.1f" % L_})
        for ring in own_bnd or []:
            sc.add_poly(ring[0], "boundary", {"Jenis": "BOUNDARY cluster (KMZ)"})
        for poly in funnel_polys or []:
            sc.add_poly(poly[0], "funnel", {"Jenis": "Funnel"})
        hp_attrs = hp_attrs or []
        for k_, (x, y, hid) in enumerate(hp_xy):
            sc.add_point(x, y, "hp", str(hid), hp_attrs[k_] if k_ < len(hp_attrs) else {"ID": hid})
        heights = heights or []
        for k_, (p, nm, kd) in enumerate(zip(poles, names, kinds)):
            a_ = {"Nama": nm or "", "Jenis": "Tiang existing (EP)" if kd == "existing" else "Tiang baru (NP)"}
            if k_ < len(heights) and heights[k_]:
                a_["Tinggi (m)"] = "%g" % heights[k_]
            sc.add_point(p.x(), p.y(), "pole_ext" if kd == "existing" else "pole_new", nm or "", a_)
        items, order = qc_order(qc)
        noisy = ("INFO_HP_ALAMAT_SAMA",)
        pxy = [(p.x(), p.y(), nm or "") for p, nm in zip(poles, names)]
        recs = []
        for n_, i_ in enumerate(order, 1):
            p, kind, ket, pts, val, lim = items[i_]
            if not pts and kind.startswith("HP_JAUH") and pxy:
                # tampilkan juga tiang terdekat di gambar: garis bantu HP -> tiang
                kx = math.cos(math.radians(p.y())) * 111320.0
                q = min(pxy, key=lambda t: ((t[0] - p.x()) * kx) ** 2 + ((t[1] - p.y()) * 110574.0) ** 2)
                pts = [QgsPointXY(p.x(), p.y()), QgsPointXY(q[0], q[1])]
            obj = ket.split(":")[0].split(" (")[0].strip() if ":" in ket[:60] else ""
            sev = qc_severity(kind)
            lab = qc_label(kind)[1]
            arti, aksi = X.tool1_kind_text(kind)
            recs.append({"fid": "F-%04d" % n_, "sev": sev, "kind": kind, "title": lab, "obj": obj, "arti": ket,
                         "fix": aksi, "value": val, "limit": lim, "unit": ("derajat" if "BELOKAN" in kind else "m") if val is not None else "",
                         "lat": p.y(), "lon": p.x(), "dasar": qc_source(kind), "source": "",
                         "line": [(q.x(), q.y()) for q in pts] if pts else None, "label": arti})
        pick = [r for r in recs if r["sev"] in ("ERROR", "WARNING")]
        pick += [r for r in recs if r["sev"] not in ("ERROR", "WARNING") and r["kind"] not in noisy]
        shots = []
        for r in pick[:max_img]:
            shots.append(dict(r, title="%s: %s" % (r["title"], r["arti"])))
        imgs = _snap.render_many(sc, shots, out_dir=os.path.join(inp, "QC_GAMBAR"), max_n=max_img)
        feedback.pushInfo("Gambar peta temuan: %d (folder QC_GAMBAR)" % len(imgs))
        # ringkasan per standar
        sev_rank = dict(zip(("ERROR", "WARNING", "UNVERIFIED", "INFO", "PASS"), range(5)))
        by_no = {}
        for r in recs:
            by_no.setdefault(qc_label(r["kind"])[0] or 0, []).append(r)
        rows = []
        for k in sorted(judul):
            ok = std.get(k, (None, ""))[0]
            lst = by_no.get(k, [])
            sev = "PASS" if ok is True else ("UNVERIFIED" if ok is None else
                                             (min((r["sev"] for r in lst), key=lambda v: sev_rank.get(v, 9)) if lst
                                              else ("WARNING" if k in _report_html.SOFT_STD else "ERROR")))
            rows.append(("%d. %s" % (k, judul[k]), sev, len(lst), str(std.get(k, (None, "-"))[1])[:180]))
        if by_no.get(0):
            lst = by_no[0]
            rows.append(("Jalur kabel dan tiang", min((r["sev"] for r in lst), key=lambda v: sev_rank.get(v, 9)), len(lst),
                         "pemeriksaan tambahan jalur & tiang"))
        word = [r for r in recs if r["kind"] not in noisy]
        path = outp("LAPORAN_QC.docx")
        _docx.qc_report(path, "Laporan QC Survei - %s" % cluster.replace("_", " "),
                        "QC data survei sebelum desain - %s v%s" % (__product__, __version__),
                        [("Cluster", cluster), ("Kode", kode), ("Dibuat", _dt.datetime.now().strftime("%d-%m-%Y %H:%M")),
                         ("Jumlah temuan", "%d (gambar peta: %d)" % (len(recs), len(imgs))),
                         ("Berkas pendukung", "RINGKASAN_QC.html, QC_TEMUAN.shp/.kmz, folder QC_GAMBAR")],
                        rows, word, {k: v[0] for k, v in imgs.items()},
                        footer="%s v%s - hasil QC adalah alat bantu; keputusan tetap pada desainer dan reviewer" % (
                            __product__, __version__))
        feedback.pushInfo("Laporan Word: %s" % path)
        from . import mapview as _mv
        map_data = _mv.data_from_scene(sc, recs)
        return os.path.basename(path), {k: _snap.data_uri(v[0]) for k, v in imgs.items()}, map_data

    def processAlgorithm(self, parameters, context, feedback):
        outdir = self.parameterAsFile(parameters, self.OUTDIR, context)
        if not outdir or not os.path.isdir(outdir):
            raise QgsProcessingException("Pilih folder cluster (atau folder induk) yang sudah ada.")
        o = {
            "hpdb": self.parameterAsFile(parameters, self.HPDB, context),
            "cluster_kmz": self.parameterAsFile(parameters, self.CLUSTER_KMZ, context),
            "pole_path": self.parameterAsFile(parameters, self.POLE, context),
            "road_path": self.parameterAsFile(parameters, self.ROADS, context),
            "snap_m": self.parameterAsDouble(parameters, self.SNAP, context),
            "span_max": self.parameterAsDouble(parameters, self.SPAN, context),
            "hp_max": self.parameterAsDouble(parameters, self.HPPOLE, context),
            "refill": self.parameterAsBool(parameters, self.REFILL, context),
            "workdir": self.parameterAsString(parameters, self.WORKDIR, context),
            "colo_max": self.parameterAsDouble(parameters, self.COLO_MAX, context),
            "profile": self.parameterAsEnum(parameters, self.PROFILE, context),
            "colo_log": self.parameterAsBool(parameters, self.COLO_LOG, context),
            "naming": self.parameterAsEnum(parameters, self.NAMING, context),
            "exist_span": 0.0,
            "span_scope": self.parameterAsEnum(parameters, self.SPAN_SCOPE, context) if self.SPAN_SCOPE in parameters else 0,
            "hp_tol": self.parameterAsDouble(parameters, self.HP_TOL, context),
            "fun_tol": self.parameterAsDouble(parameters, self.FUN_TOL, context),
            "bakp_file": self.parameterAsFile(parameters, self.BAKP_FILE, context) if self.BAKP_FILE in parameters else "",
            "qc_profile": _qc.get_profile("REGULASI_KETAT" if (self.parameterAsEnum(parameters, self.QC_PROF, context)
                                                            if self.QC_PROF in parameters else 0) == 1 else "APD_1X4")[0],
            "bakp": self.parameterAsEnum(parameters, self.BAKP, context) if self.BAKP in parameters else 0,
            "colo_basis": self.parameterAsEnum(parameters, self.COLO_BASIS, context) if self.COLO_BASIS in parameters else 0,
        }
        ref_dir = self.parameterAsFile(parameters, self.FUNNEL, context)
        st = QgsSettings()
        if ref_dir and os.path.isdir(ref_dir):
            st.setValue("seranta/ref_dir", ref_dir)
        else:   # diingat dari run sebelumnya (juga membaca pengaturan versi lama)
            ref_dir = (st.value("seranta/ref_dir", "")
                       or st.value("seranta/funnel_dir", "") or "")
        if ref_dir and not os.path.isdir(ref_dir):
            feedback.reportError("Folder referensi yang diingat tidak ada di komputer ini: %s" % ref_dir, fatalError=False)
            ref_dir = ""
        if not ref_dir:
            # Pengguna baru (mis. pasang dari ZIP) belum pernah mengisi isian 2: cari otomatis di sekitar folder cluster.
            auto = find_ref_dir(outdir)
            if auto:
                ref_dir = auto
                st.setValue("seranta/ref_dir", auto)
                getattr(feedback, "pushWarning", feedback.pushInfo)("Folder data referensi ditemukan otomatis: %s (isi isian 2 bila salah)" % auto)
            else:
                getattr(feedback, "pushWarning", feedback.pushInfo)(
                    "DATA REFERENSI TIDAK ADA: isian 2 (folder referensi) kosong dan tidak ditemukan otomatis. "
                    "Cek Funnel (standar 2 & 5), Design Lite/colo (6 & 7) dan FINDIM (3) DILEWATI. "
                    "Salin folder referensi tim (berisi *FUNNEL*.kmz, DESIGN LITE*.kmz, *attributes*.xlsx) "
                    "lalu pilih di isian 2.")
        o["funnel_dir"] = ref_dir if ref_dir and os.path.isdir(ref_dir) else ""
        if o["funnel_dir"]:
            feedback.pushInfo("Folder data referensi: %s" % o["funnel_dir"])
            for k, lab in REF_LABELS:
                fl = ref_files(o["funnel_dir"], k)
                feedback.pushInfo("  %s %-12s: %s" % ("OK " if fl else "-- ", lab,
                                  ", ".join(os.path.basename(x) for x in fl[:3]) + (" ..." if len(fl) > 3 else "")
                                  if fl else "tidak ada"))
        prof = resolve_profile(o["profile"], o["funnel_dir"], feedback)
        o.update(prof=prof, hp_per_spl=prof["hp_per_spl"], max_spl=prof["max_spl"])
        feedback.pushInfo("Profil: %s | FDT maks %d HP, %d splitter 1x%d | FAT %d-%d HP, jarak maks %.0f m | sumber: %s" % (
            prof["name"], prof["fdt_cap"], prof["max_spl"], prof["ratio"], prof["fat_min"], prof["fat_max"],
            prof["fat_dist"], prof["src"]))
        self._to_load = []
        self._open_path = None
        open_rep = self.parameterAsBool(parameters, self.OPEN_REPORT, context) if self.OPEN_REPORT in parameters else True

        # Batch: folder induk yang tidak berisi HPDB tetapi subfoldernya berisi HPDB
        def has_hpdb(d):
            return bool(hpdb_candidates(d))

        def subdirs(d):
            return [os.path.join(d, x) for x in sorted(os.listdir(d))
                    if os.path.isdir(os.path.join(d, x)) and not x.upper().startswith(("INPUT", "_"))]
        clusters = [outdir]
        if not o["hpdb"] and not has_hpdb(outdir):
            clusters = [d for d in subdirs(outdir) if has_hpdb(d)]
            if not clusters:
                # hasil ekstrak ZIP sering bertingkat: FOLDER/FOLDER/<file> -> cari satu tingkat lebih dalam
                clusters = [d2 for d in subdirs(outdir) for d2 in subdirs(d) if has_hpdb(d2)]
            if not clusters:
                sheets = [os.path.relpath(os.path.join(r, f), outdir) for r, _ds, fs in os.walk(outdir)
                          for f in fs if os.path.splitext(f)[1].lower() in (".xlsx", ".xls", ".csv")][:6]
                raise QgsProcessingException(
                    "Tidak ada file HPDB di folder ini maupun di subfoldernya: %s. Spreadsheet yang ada: %s. "
                    "Nama file HPDB harus memuat HPDB (atau pilih file di isian opsional HPDB)."
                    % (outdir, ", ".join(sheets) or "tidak ada"))
            feedback.pushInfo("MODE BATCH: %d folder cluster ditemukan di %s" % (len(clusters), outdir))
        if len(clusters) == 1:
            res = self._run_cluster(clusters[0], o, context, feedback)
            if open_rep:
                self._open_path = res.get("laporan")
            return {self.OUTDIR: res.get("inp", outdir)}

        # mode batch: satu cluster gagal tidak menghentikan cluster lain
        rekap, seen = [], {}
        for i, cdir in enumerate(clusters, 1):
            if feedback.isCanceled():
                break
            feedback.pushInfo("")
            feedback.pushInfo("=" * 70)
            feedback.pushInfo("[%d/%d] %s" % (i, len(clusters), cdir))
            oo = dict(o, hpdb="", cluster_kmz="", pole_path="", road_path="")
            try:
                res = self._run_cluster(cdir, oo, context, feedback)
                k = res.get("kode", "")
                if k in seen:
                    feedback.reportError("PERINGATAN: kode %s sama dengan cluster %s" % (k, seen[k]), fatalError=False)
                seen[k] = cdir
                rekap.append((os.path.basename(cdir), "OK", res))
            except Exception as e:
                feedback.reportError("GAGAL %s: %s" % (os.path.basename(cdir), e), fatalError=False)
                rekap.append((os.path.basename(cdir), "GAGAL: %s" % str(e)[:200], {}))
        lines = ["REKAP BATCH INPUT AUTODESIGN - %s" % _dt.datetime.now().strftime("%d-%m-%Y %H:%M"),
                 "Folder induk: %s" % outdir, "",
                 "Temuan = perlu dicek + info (i). Detail di <KODE>_QC_TEMUAN.shp (QGIS) / .kmz (aplikasi peta KMZ) dan <KODE>_LAPORAN_INPUT.txt", "",
                 "%-34s %-8s %5s %5s %8s %-5s %-16s  %s" % ("Cluster", "Status", "HP", "Tiang", "Temuan", "BAKP", "Colo", "Folder hasil")]
        for nm, stt, r in rekap:
            lines.append("%-34s %-8s %5s %5s %8s %-5s %-16s  %s" % (
                nm[:34], stt[:8], r.get("hp", "-"), r.get("poles", "-"), r.get("qc", "-"), r.get("bakp", "-"),
                (r.get("colo") or "-")[:16], r.get("inp", "")))
            if not stt.startswith("OK"):
                lines.append("    " + stt)
        rk = os.path.join(outdir, "REKAP_BATCH_%s.txt" % _dt.datetime.now().strftime("%Y%m%d_%H%M"))
        with open(rk, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        feedback.pushInfo("")
        for ln in lines:
            feedback.pushInfo(ln)
        feedback.pushInfo("Rekap batch: %s" % rk)
        if open_rep:
            self._open_path = rk
        return {self.OUTDIR: outdir}

    @staticmethod
    def _write_manifest(path, kode, cl_id, hpdb, headers, idx, data, hp_path, hp_csv, roads_path, pole_path, qprof, opt):
        """manifest_input.json (spesifikasi 11): file, tipe, jumlah fitur, CRS, SHA-256, pemetaan kolom, status siap impor
        dan petunjuk setelan desain otomatis. Plugin TIDAK mengendalikan GUI desain otomatis."""
        import hashlib
        import json as _json

        def sha(p):
            if not p or not os.path.exists(p):
                return None
            h_ = hashlib.sha256()
            with open(p, "rb") as fh_:
                for blk in iter(lambda: fh_.read(1 << 20), b""):
                    h_.update(blk)
            return h_.hexdigest()

        def nfeat(p):
            try:
                lyr = QgsVectorLayer(p, "m", "ogr")
                return lyr.featureCount() if lyr.isValid() else None
            except Exception:
                return None
        ilon, ilat, iid = idx
        ids = [str(r[iid]).strip() for r, _p in data] if iid is not None else []
        checks = []

        def chk(code, ok, txt):
            checks.append({"kode": code, "status": "UNVERIFIED" if ok is None else ("PASS" if ok else "ERROR"),
                           "keterangan": txt})
        n_shp = nfeat(hp_path)
        n_csv = None
        if hp_csv and os.path.exists(hp_csv):
            with open(hp_csv, encoding="utf-8-sig") as fh_:
                n_csv = sum(1 for _ in fh_) - 1
        chk("INPUT_HP_COUNT", None if n_shp is None else (n_shp == len(data) and (n_csv is None or n_csv == n_shp)),
            "HP.shp %s fitur, HP.csv %s baris, HPDB valid %d" % (n_shp, n_csv, len(data)))
        chk("INPUT_HP_ID_DUPLICATE", len(ids) == len(set(ids)) if ids else False,
            "ID unik %d dari %d" % (len(set(ids)), len(ids)) if ids else "kolom Homepass_ID_Partner tidak ada")
        badf = [i for i in ids if not re.match(r"^H\d{5,}$", i)]
        chk("INPUT_HP_ID_FORMAT", not badf, "format H00001..: %d tidak sesuai%s" % (len(badf), (" (mis. %s)" % badf[0]) if badf else ""))
        badc = [1 for _r, p in data if not (-11.5 <= p.y() <= 6.5 and 94.5 <= p.x() <= 141.5)]
        chk("INPUT_HP_COORD_INVALID", not badc, "koordinat di luar wilayah Indonesia: %d" % len(badc))
        chk("INPUT_SCHEMA_INVALID", ilon is not None and ilat is not None,
            "kolom Homepass_Longitude/Latitude %s" % ("ditemukan" if ilon is not None and ilat is not None else "TIDAK ADA"))
        n_road = nfeat(roads_path)
        chk("INPUT_ROADS_EMPTY", None if n_road is None else bool(n_road), "ROADS.shp %s ruas" % n_road)
        files = []
        for lab, p, typ in (("HP", hp_path, "ESRI Shapefile"), ("HP_CSV", hp_csv, "CSV (Comma Delimited)"),
                            ("ROADS", roads_path, "ESRI Shapefile"), ("POLE", pole_path, "KMZ (cutting points)")):
            if p and os.path.exists(p):
                files.append({"peran": lab, "file": os.path.basename(p), "tipe": typ, "crs": "EPSG:4326 (WGS 84)",
                              "fitur": nfeat(p) if typ == "ESRI Shapefile" else (n_csv if lab == "HP_CSV" else None),
                              "sha256": sha(p), "ukuran_byte": os.path.getsize(p)})
        sts = {c["status"] for c in checks}
        ready = "SIAP" if sts == {"PASS"} else ("PERLU PERBAIKAN" if "ERROR" in sts else "BELUM TERVERIFIKASI")
        out = {"produk": "%s v%s" % (__product__, __version__), "dibuat": _dt.datetime.now().isoformat(timespec="seconds"),
               "kode": kode, "cluster_id": cl_id, "hpdb": os.path.basename(hpdb or ""),
               "profil_qc": qprof.get("profile_id"), "versi_aturan": qprof.get("rule_version"),
               "pemetaan_kolom": {"Homepass_Longitude": headers[ilon] if ilon is not None else None,
                                  "Homepass_Latitude": headers[ilat] if ilat is not None else None,
                                  "Homepass_ID_Partner": headers[iid] if iid is not None else None},
               "parameter_pemrosesan": {"snap_m": opt.get("snap_m"), "snap_behavior": "prefer aligning nodes, don't insert new vertices",
                                        "explode_lines": True, "span_max_m": opt.get("span_max"), "hp_pole_max_m": opt.get("hp_max")},
               "file": files, "pemeriksaan": checks, "status_siap_impor": ready,
               "petunjuk_autodesign": ["Import Homepass dari HP.shp (atau HP.csv: X=Homepass_Longitude, Y=Homepass_Latitude, EPSG:4326)",
                                   "Import Roads dari ROADS.shp",
                                   "Split line by points memakai POLE.kmz (context layer) lalu split into equal parts maks 50 m",
                                   "Seranta tidak mengoperasikan GUI desain otomatis; langkah di atas dilakukan desainer"]}
        with open(path, "w", encoding="utf-8") as fh_:
            _json.dump(out, fh_, ensure_ascii=False, indent=1)
        return path, out["status_siap_impor"], ["%s %s: %s" % (c["status"], c["kode"], c["keterangan"]) for c in checks]

    def _write_qc(self, qc, inp, outp, kode, context, feedback):
        """Tulis temuan QC:
        - QC/<kategori>.shp  satu file per jenis temuan (titik, atau GARIS mengikuti jalur untuk rentang tiang),
          masing-masing dengan gaya .qml (merah = perlu dicek, kuning = info) -> analisa per kategori.
        - <KODE>_QC_TEMUAN.shp gabungan semua temuan (titik) dan <KODE>_QC_TEMUAN.kmz untuk aplikasi peta KMZ.
        Mengembalikan (path gabungan atau None, [(path kategori, nama tampilan, jumlah)])."""
        qdir = os.path.join(inp, "QC")
        qc_map = outp("QC_TEMUAN.shp")
        qbase = os.path.splitext(qc_map)[0]
        # status review (Navigator) dari run sebelumnya dipertahankan: kunci = kode + lokasi (~1 m)
        old_rev = {}
        if os.path.exists(qc_map):
            # dibaca langsung dari .dbf (bukan lewat layer OGR): kumpulan koneksi OGR QGIS bisa menahan file sehingga
            # QC_TEMUAN lama tidak bisa dihapus/ditulis ulang saat alat dijalankan dua kali dalam satu sesi
            try:
                for f in read_dbf(os.path.splitext(qc_map)[0] + ".dbf"):
                    rv = f.get("review")
                    if rv and str(rv) not in ("OPEN", "NULL"):
                        old_rev["%s|%.5f,%.5f" % (f.get("kode"), float(f.get("lon") or 0), float(f.get("lat") or 0))] = (
                            str(rv), str(f.get("catatan") or ""))
            except Exception:
                old_rev = {}
        for old_ in [outp("QC_TEMUAN.kmz"), outp("QC_TEMUAN_PETA.gpkg")] + [
                qbase + e for e in (".shp", ".shx", ".dbf", ".prj", ".cpg", ".qml", ".qpj")]:
            if os.path.exists(old_):
                try:
                    os.remove(old_)       # jangan tinggalkan temuan lama bila sekarang bersih
                except OSError as _e:
                    _log.note(_e)
        if os.path.isdir(qdir):
            for fn in os.listdir(qdir):
                try:
                    os.remove(os.path.join(qdir, fn))
                except OSError as _e:
                    _log.note(_e)
        if not qc:
            return None, []
        items, order = qc_order(qc)
        FIELDS = ("&field=no:integer&field=status:string(10)&field=severity:string(10)&field=standar:string(4)"
                  "&field=jenis:string(80)&field=keterangan:string(254)&field=nilai:double(12,2)&field=batas:double(12,2)"
                  "&field=dasar:string(160)&field=dasar_src:string(20)&field=kode:string(60)&field=finding_id:string(24)"
                  "&field=profil:string(20)&field=versi:string(14)&field=review:string(20)&field=catatan:string(200)"
                  "&field=lon:double(12,7)&field=lat:double(12,7)")
        pid = (getattr(self, "_qprof", None) or {}).get("profile_id", "APD_1X4")
        n_rev = [0]

        def feat(lyr, n_, it, as_line):
            p, kind, ket, pts, val, lim = it
            no, lab = qc_label(kind)
            f = QgsFeature(lyr.fields())
            rv = old_rev.get("%s|%.5f,%.5f" % (kind, round(p.x(), 7), round(p.y(), 7)))
            if rv and not as_line:
                n_rev[0] += 1
            f.setAttributes([n_, qc_status(kind), qc_severity(kind), str(no) if no else "", lab,
                             _short(ket, 254), float(val) if val is not None else None,
                             float(lim) if lim is not None else None, _short(qc_source(kind), 160), qc_dasar(kind), kind,
                             "F-%04d" % n_, pid, _qc.RULE_VERSION,
                             rv[0] if rv else "OPEN", rv[1][:200] if rv else "",
                             round(p.x(), 7), round(p.y(), 7)])
            f.setGeometry(QgsGeometry.fromPolylineXY(list(pts)) if as_line else QgsGeometry.fromPointXY(p))
            return f

        def save(lyr, path, name):
            self._write(lyr, path, "ESRI Shapefile", context)
            try:      # gaya ikut file: dibuka manual di QGIS pun langsung berwarna & berlabel
                sl = QgsVectorLayer(path, name, "ogr")
                if sl.isValid() and style_qc_layer(sl):
                    sl.saveNamedStyle(os.path.splitext(path)[0] + ".qml")
                del sl
            except Exception as _e:
                _log.note(_e)
        # gabungan (titik)
        allq = QgsVectorLayer("Point?crs=EPSG:4326" + FIELDS, "QC_TEMUAN", "memory")
        allq.dataProvider().addFeatures([feat(allq, n_, items[i_], False) for n_, i_ in enumerate(order, 1)])
        try:
            write_qc_kmz(outp("QC_TEMUAN.kmz"), "QC TEMUAN %s" % kode, qc)
        except Exception as e:
            feedback.reportError("QC_TEMUAN.kmz tidak bisa ditulis: %s" % e, fatalError=False)
        try:
            save(allq, qc_map, "QC_TEMUAN")
        except Exception as e:
            feedback.reportError("QC_TEMUAN.shp tidak ditulis: %s" % e, fatalError=False)
            qc_map = None
        # per kategori
        cats = {}
        for n_, i_ in enumerate(order, 1):
            cats.setdefault(qc_slug(items[i_][1]), []).append((n_, items[i_]))
        os.makedirs(qdir, exist_ok=True)
        out = []
        for slug, lst in cats.items():
            as_line = all(it[3] for _n, it in lst)
            lyr = QgsVectorLayer(("LineString" if as_line else "Point") + "?crs=EPSG:4326" + FIELDS, slug, "memory")
            lyr.dataProvider().addFeatures([feat(lyr, n_, it, as_line) for n_, it in lst])
            path = os.path.join(qdir, slug + ".shp")
            no, lab = qc_label(lst[0][1][1])
            sev_ = qc_severity(lst[0][1][1])
            info_ = sev_ in ("INFO", "UNVERIFIED")
            pre_ = {"WARNING": "W", "UNVERIFIED": "Unverified"}.get(sev_, "")
            name = "%s%s (%d)" % (("Info %d: " % no if info_ else "%s%d " % (pre_ or "S", no)) if no
                                  else ("Info: " if info_ else ("Warning: " if pre_ == "W" else "")), lab, len(lst))
            try:
                save(lyr, path, name)
                out.append((path, name, len(lst)))
            except Exception as e:
                feedback.reportError("QC/%s.shp tidak ditulis: %s" % (slug, e), fatalError=False)
        feedback.pushInfo("Temuan QC: %d titik/garis dalam %d kategori -> %s (satu shp per kategori), QC_TEMUAN.shp, "
                          "QC_TEMUAN.kmz%s" % (len(qc), len(out), qdir,
                                               "; %d status review dari run sebelumnya dipertahankan" % n_rev[0] if n_rev[0] else ""))
        return qc_map, out

    def _write_funnel(self, polys, fun_path, context, feedback, rep):
        """Tulis poligon Funnel di sekitar cluster sebagai layer tampilan. Tahan banting: tiap poligon diperbaiki
        sendiri (makeValid, ambil bagian poligon saja dari GeometryCollection), poligon yang tetap rusak dilewati
        satu per satu, dan bila GeoPackage gagal ditulis (versi GDAL/izin folder) dicoba Shapefile.
        Mengembalikan (daftar_poligon_tertulis, path) atau ([], path) bila gagal total."""
        fl = QgsVectorLayer("MultiPolygon?crs=EPSG:4326&field=Name:string(120)&field=grup:string(40)"
                            "&field=status:string(80)&field=hp_plan:string(20)", "FUNNEL_SEKITAR", "memory")
        ff, kept, bad = [], [], 0
        for f in polys:
            try:
                g = _funnel_geom(f["poly"])
            except Exception:
                g = None
            if g is None:
                bad += 1
                continue
            ft = QgsFeature(fl.fields())
            ft.setAttributes([str(f["name"])[:120], str(f["grp"])[:40], str(f["status"] or "")[:80],
                              str(f["plan"] or "")[:20]])
            ft.setGeometry(g)
            ff.append(ft)
            kept.append(f)
        if not ff:
            rep.append("  Layer FUNNEL_SEKITAR         : tidak dibuat (%d poligon rusak)" % bad)
            return [], fun_path
        fl.dataProvider().addFeatures(ff)
        errs = []
        for path, drv in ((fun_path, "GPKG"), (os.path.splitext(fun_path)[0] + ".shp", "ESRI Shapefile")):
            try:
                base = os.path.splitext(path)[0]
                for ext in ((".gpkg", ".gpkg-wal", ".gpkg-shm") if drv == "GPKG"
                            else (".shp", ".shx", ".dbf", ".prj", ".cpg", ".qpj")):
                    if os.path.exists(base + ext):
                        os.remove(base + ext)
                self._write(fl, path, drv, context)
                if not os.path.exists(path):
                    raise IOError("file tidak terbentuk")
                rep.append("  Layer FUNNEL_SEKITAR         : %d poligon -> %s%s" % (
                    len(ff), os.path.basename(path), ", %d poligon rusak dilewati" % bad if bad else ""))
                return kept, path
            except Exception as e:
                errs.append("%s: %s" % (drv, str(e)[:200]))
        # Layer ini hanya tampilan; kegagalannya tidak boleh menghentikan Run.
        feedback.reportError("Layer FUNNEL_SEKITAR tidak bisa ditulis (cek boundary tetap jalan): %s"
                             % " | ".join(errs), fatalError=False)
        rep.append("  ! Layer FUNNEL_SEKITAR gagal ditulis: %s" % " | ".join(errs))
        return [], fun_path

    def _run_cluster(self, outdir, opt, context, feedback):
        o = opt
        hpdb, cluster_kmz = o["hpdb"], o["cluster_kmz"]
        pole_path, road_path = o["pole_path"], o["road_path"]
        separate = bool(pole_path and road_path)
        if not hpdb:
            hpdb = find_hpdb(outdir)
        if separate:
            cluster_kmz = ""
        elif not cluster_kmz:
            cluster_kmz = find_kmz(outdir)
        feedback.pushInfo("HPDB dipakai : %s" % hpdb)
        feedback.pushInfo("KMZ dipakai  : %s" % (cluster_kmz or (pole_path + " + " + road_path)))
        snap_m, span_max, hp_max = o["snap_m"], o["span_max"], o["hp_max"]
        refill, workdir, funnel_dir = o["refill"], o["workdir"], o["funnel_dir"]
        colo_max, hp_per_spl, max_spl, colo_log = o["colo_max"], o["hp_per_spl"], o["max_spl"], o["colo_log"]
        exist_span, hp_tol, fun_tol = o["exist_span"], o["hp_tol"], o.get("fun_tol", 15.0)
        # profil standar QC (profiles/*.json): angka berbasis regulasi/standar/riset + status pengesahan
        qprof = o.get("qc_profile") or _qc.get_profile("APD_1X4")[0]

        def qcp(key, default=None):
            return _qc.pv(qprof, key, default)
        self._qprof = qprof
        if float(qcp("span_max_m", span_max)) < span_max:
            feedback.pushInfo("Profil %s: batas rentang %.0f m (lebih ketat dari isian %.0f m) dipakai"
                              % (qprof["profile_id"], qcp("span_max_m"), span_max))
            span_max = float(qcp("span_max_m"))
        sag_ratio = float(qcp("sag_pct", 2.0)) / 100.0
        clear_road = float(qcp("clear_road_m", CLEAR_ROAD))
        clear_fail = min(clear_road, float(qcp("clear_road_fail_m", 4.7)))
        embed_frac = float(qcp("pole_embed_frac", 1.0 / 6.0))
        span_reg = float(qcp("span_reg_m", SPAN_REG))

        # Penamaan: per wilayah (default) -> INPUT_<KODE>/<KODE>_HP.shp ; SOP -> INPUT/HP.shp
        kode = kode_wilayah(outdir, hpdb)
        # Windows: path penuh maksimal 260 karakter -> pendekkan kode bila folder cluster sudah panjang
        base_len = len(os.path.abspath(outdir)) + len("\\INPUT_\\_FUNNEL_SEKITAR.gpkg") + 10
        short_dir = False
        if base_len + 2 * len(kode) > 240:
            short_dir = True                     # folder cluster sudah unik -> cukup "INPUT", kode hanya di nama file
            room = max(14, 240 - base_len)
            if len(kode) > room:
                kode = _short_code(kode, room)
            feedback.pushInfo("Path folder panjang (batas 260 karakter Windows): hasil ditulis ke INPUT\\%s_*" % kode)
        if o["naming"] == 0:
            inp = os.path.join(outdir, "INPUT" if short_dir else "INPUT_" + kode)
            pre = kode + "_"
        else:
            inp = os.path.join(outdir, "INPUT")
            pre = ""

        def outp(name):
            return os.path.join(inp, pre + name)
        os.makedirs(inp, exist_ok=True)
        feedback.pushInfo("Kode wilayah : %s -> %s" % (kode, inp))
        da = QgsDistanceArea()
        da.setSourceCrs(WGS84, context.transformContext())
        da.setEllipsoid("WGS84")
        rep, qc = [], []   # laporan teks, titik temuan (point, jenis, ket)
        ignored = {}       # temuan yang sengaja diabaikan sesuai aturan (untuk laporan)

        # ===== 1. HPDB -> HP.shp =====
        feedback.setProgressText("1/3 Membaca HPDB")
        rows, h = self._read_table(hpdb, feedback)
        headers = []
        for i, c in enumerate(rows[h]):
            c = c or "KOLOM_%d" % (i + 1)
            while c in headers:
                c += "_"
            headers.append(c)
        while headers and headers[-1].startswith("KOLOM_"):
            headers.pop()
        ilat = self._pick(headers, ["Homepass_Latitude"], "LATITUDE")
        ilon = self._pick(headers, ["Homepass_Longitude"], "LONGITUDE")
        iid = self._pick(headers, ["Homepass_ID_Partner"], "IDPARTNER")

        data, skipped = [], 0
        meta = []          # per HP: (nomor baris spreadsheet, ID asli sebelum diisi ulang)
        for j, r in enumerate(rows[h + 1:], start=h + 2):
            r = (r + [""] * len(headers))[:len(headers)]
            if not any(r):
                continue
            lat, lon = self._num(r[ilat]), self._num(r[ilon])
            if lat is None or lon is None:
                skipped += 1
                continue
            if -11.5 <= lon <= 6.5 and 94 <= lat <= 141.5:   # lat/long tertukar
                lat, lon = lon, lat
                r[ilat], r[ilon] = str(lat), str(lon)
                qc.append((QgsPointXY(lon, lat), "LAT_LONG_TERTUKAR", "Kolom lat/long tertukar, sudah dibalik"))
            if not (-11.5 <= lat <= 6.5 and 94 <= lon <= 141.5):
                skipped += 1
                rep.append("  ! Koordinat di luar Indonesia dilewati: %s, %s" % (lat, lon))
                continue
            data.append((r, QgsPointXY(lon, lat)))
            meta.append((j, (r[iid] if iid is not None else "").strip()))
        if not data:
            raise QgsProcessingException("Tidak ada baris homepass dengan koordinat valid.")

        if iid is not None and refill:
            for n, (r, _) in enumerate(data, 1):
                r[iid] = "H%05d" % n
        elif iid is None:
            rep.append("  ! Kolom Homepass_ID_Partner tidak ditemukan; ID tidak diisi.")

        fields = QgsFields()
        for name in headers:
            fields.append(QgsField(name, FIELD_STRING, len=254))
        hp = QgsVectorLayer("Point?crs=EPSG:4326", "HP", "memory")
        hp.dataProvider().addAttributes(fields.toList())
        hp.updateFields()
        feats = []
        for r, p in data:
            f = QgsFeature(hp.fields())
            f.setAttributes(r)
            f.setGeometry(QgsGeometry.fromPointXY(p))
            feats.append(f)
        hp.dataProvider().addFeatures(feats)
        # ---- HP duplikat: koordinat sama (<= 0,5 m), ID operator sama, atau alamat lengkap sama ----
        def _col(*names):
            return self._pick(headers, list(names), "\x00")
        i_opid = self._pick_rx(headers, r"^HOMEPASSID(?!PARTNER)[A-Z]+$", skip=(iid,))   # ID homepass operator
        i_adr = [_col("HOMEPASS_ADDRESS"), _col("HOMEPASS_HOUSE_NUMBER"), _col("HOMEPASS_ADDRESS_BLOCK"),
                 _col("NEIGHBORHOOD_NO_RT"), _col("HAMLET_NO_RW"), _col("HOMEPASS_UNIT_NUMBER")]

        def _hpname(k):
            return "baris %d (%s)" % (meta[k][0], data[k][0][iid] if iid is not None else "HP %d" % (k + 1))

        def _addr(r):
            # hanya alamat setingkat rumah: wajib ada nomor rumah (HOMEPASS_HOUSE_NUMBER)
            hn = i_adr[1]
            if hn is None or hn >= len(r) or r[hn].strip() in ("", "-", "0"):
                return ""
            v = [r[i].strip() for i in i_adr if i is not None and i < len(r)]
            v = [x for x in v if x and x != "-"]
            return " ".join(v).upper() if len(v) >= 2 else ""
        dup_groups = []          # (jenis, [indeks HP])
        adr_generic = []         # (alamat, jumlah HP) alamat dipakai > 3 HP
        grid = {}
        for k, (r, p) in enumerate(data):
            grid.setdefault((round(p.x() / 5e-6), round(p.y() / 5e-6)), []).append(k)
        used_k = set()
        for k, (r, p) in enumerate(data):
            if k in used_k:
                continue
            gx, gy = round(p.x() / 5e-6), round(p.y() / 5e-6)
            grp = [k]
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for k2 in grid.get((gx + dx, gy + dy), []):
                        if k2 != k and k2 not in used_k and k2 not in grp and da.measureLine(p, data[k2][1]) <= 0.5:
                            grp.append(k2)
            if len(grp) > 1:
                used_k.update(grp)
                dup_groups.append(("koordinat sama", sorted(grp)))
        # kemungkinan duplikat: 0,5-3 m (akurasi GPS ponsel 3-5 m), nomor rumah sama atau tidak diisi -> info
        near_dup = []
        hn_i = i_adr[1]

        def _hn(r):
            return r[hn_i].strip().upper() if hn_i is not None and hn_i < len(r) else ""
        dup_near = float(qcp("dup_near_m", 5.0))
        cell = dup_near / 111320.0
        grid3 = {}
        for k, (r, p) in enumerate(data):
            grid3.setdefault((int(p.x() / cell), int(p.y() / cell)), []).append(k)
        for k, (r, p) in enumerate(data):
            if k in used_k:
                continue
            cx_, cy_ = int(p.x() / cell), int(p.y() / cell)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for k2 in grid3.get((cx_ + dx, cy_ + dy), []):
                        if k2 <= k or k2 in used_k:
                            continue
                        d = da.measureLine(p, data[k2][1])
                        if 0.5 < d <= dup_near:
                            h1, h2 = _hn(r), _hn(data[k2][0])
                            if not h1 or not h2 or h1 == h2:
                                near_dup.append((k, k2, d))
        for k, k2, d in near_dup[:300]:
            qc.append((data[k2][1], "INFO_HP_MUNGKIN_DUPLIKAT",
                       "%s dan %s berjarak %.1f m (nomor rumah sama/kosong): cek apakah rumah yang sama"
                       % (_hpname(k), _hpname(k2), d), None, round(d, 1), dup_near))
        for jenis, getter in (("ID operator sama", lambda r: r[i_opid].strip() if i_opid is not None else ""),
                              ("alamat sama", _addr)):
            byv = {}
            for k, (r, p) in enumerate(data):
                v = getter(r)
                if v and v not in ("-", "0"):
                    byv.setdefault(v, []).append(k)
            for v, ks in byv.items():
                if jenis == "alamat sama" and len(ks) > 3:
                    adr_generic.append((v, len(ks)))    # satu alamat untuk banyak HP: alamat tidak spesifik
                    continue
                if len(ks) > 1 and not any(set(ks) <= set(g) for _j, g in dup_groups):
                    dup_groups.append((jenis, ks))
        dup = sum(len(g) - 1 for j, g in dup_groups if j == "koordinat sama")
        dup_id = sum(len(g) - 1 for j, g in dup_groups if j == "ID operator sama")
        dup_adr = sum(len(g) - 1 for j, g in dup_groups if j == "alamat sama")
        for jenis, ks in dup_groups:
            names_ = ", ".join(_hpname(k) for k in ks[:10]) + (" dan %d lainnya" % (len(ks) - 10) if len(ks) > 10 else "")
            kind_ = {"koordinat sama": "HP_DUPLIKAT_KOORDINAT", "ID operator sama": "HP_DUPLIKAT_ID",
                     "alamat sama": "INFO_HP_ALAMAT_SAMA"}[jenis]
            qc.append((data[ks[1]][1], kind_, "HP duplikat (%s): %s" % (jenis, names_)))
        hp_path = outp("HP.shp")
        self._write(hp, hp_path, "ESRI Shapefile", context)
        # HP.csv (Comma Delimited, nama kolom utuh - Langkah Pembuatan Input Desain Otomatis APD hlm. 10-18)
        hp_csv = outp("HP.csv")
        try:
            import csv as _csv
            with open(hp_csv, "w", newline="", encoding="utf-8-sig") as fh_:
                w_ = _csv.writer(fh_)
                w_.writerow(headers)
                for r_, _p in data:
                    w_.writerow((list(r_) + [""] * len(headers))[:len(headers)])
        except Exception as e:
            hp_csv = None
            feedback.reportError("HP.csv tidak ditulis: %s" % e, fatalError=False)

        # nama kolom setelah dipotong shapefile (maks 10 karakter)
        written = QgsVectorLayer(hp_path, "HP", "ogr")
        trunc = [f.name() for f in written.fields()]
        rep.append("HOMEPASS")
        rep.append("  Baris valid        : %d" % len(data))
        rep.append("  Baris dilewati     : %d (tanpa koordinat/di luar Indonesia)" % skipped)
        rep.append("  HP duplikat        : %d koordinat sama, %d ID operator sama, %d alamat sama (info), "
                   "%d pasang kemungkinan duplikat <= %.0f m (info)" % (dup, dup_id, dup_adr, len(near_dup), dup_near))
        if adr_generic:
            rep.append("    info: %d alamat dipakai lebih dari 3 HP (mis. '%s' untuk %d HP); alamat tidak setingkat rumah, "
                       "tidak dihitung duplikat" % (len(adr_generic), max(adr_generic, key=lambda a: a[1])[0],
                                                     max(a[1] for a in adr_generic)))
        for jenis, ks in dup_groups[:30]:
            r0 = data[ks[0]][0]
            rep.append("    - %s: %s%s" % (jenis, ", ".join(_hpname(k) for k in ks[:10]) + (
                " dan %d lainnya" % (len(ks) - 10) if len(ks) > 10 else ""),
                                         ("; alamat: %s" % _addr(r0)) if _addr(r0) else ""))
        if len(dup_groups) > 30:
            rep.append("    ... %d grup lain di QC_TEMUAN.kmz" % (len(dup_groups) - 30))
        if iid is not None:
            rep.append("  ID dibuat          : %s s/d %s" % (data[0][0][iid], data[-1][0][iid]))
        rep.append("  Nama kolom di HP.shp (untuk pemetaan Name/External ID di desain otomatis):")
        for o, t in zip(headers, trunc):
            rep.append("    %-12s <- %s" % (t, o))
        feedback.setProgress(33)

        # ===== 2. Tiang -> POLE.kmz =====
        feedback.setProgressText("2/3 Menggabungkan tiang")
        if cluster_kmz:
            feats = kml_features(cluster_kmz)
            ppts, pnames, pkinds, pheights, rlines = [], [], [], [], []
            pfold, rfold, other = set(), set(), set()
            HP_RX = re.compile(r"\b(hp|homepass|home ?pass|rumah)\b", re.IGNORECASE)
            # titik di sub-folder EVIDANCE/EVIDENCE di dalam folder HP = HP bertanda foto bukti (aplikasi Map Marker
            # menamai '?-79'); dipakai untuk memasangkan baris HPDB, tetapi titik foto yang tidak berpasangan tidak dianggap HP
            kmz_hp = [(geom, nm) for folders, nm, kind, geom in feats
                      if kind == "point" and any(HP_RX.search(f) for f in folders)
                      and not any(EVID_RX.search(f) for f in folders)]
            # titik di folder 'DUPLIKAT ... (ERROR)' sudah ditandai surveyor sebagai duplikat: tetap dihitung sebagai
            # HP duplikat KMZ, tetapi tidak dilaporkan lagi sebagai 'HP KMZ tidak ada di HPDB' (hindari hitung ganda)
            kmz_dupf = {j for j, (folders, nm, kind, geom) in enumerate(
                [x for x in feats if x[2] == "point" and any(HP_RX.search(f) for f in x[0])
                 and not any(EVID_RX.search(f) for f in x[0])]) if any(DUPF_RX.search(f) for f in folders)}
            n_main = len(kmz_hp)
            kmz_hp += [(geom, nm) for folders, nm, kind, geom in feats
                       if kind == "point" and any(HP_RX.search(f) for f in folders)
                       and any(EVID_RX.search(f) for f in folders)]
            kmz_ev0 = n_main
            own_bnd = [geom for folders, nm, kind, geom in feats
                       if kind == "polygon" and any(BOUNDARY_RX.search(f) for f in folders)]
            for folders, nm, kind, geom in feats:
                cls = classify(folders)
                label = " / ".join(folders) or "(akar)"
                if cls == "pole" and kind == "point":
                    ppts.append(geom); pnames.append(nm); pfold.add(label)
                    pkinds.append(pole_kind(folders, nm))
                    pheights.append(pole_height(folders, nm))
                elif cls == "route" and kind == "line":
                    rlines.append(geom); rfold.add(label)
                else:
                    other.add(label)
            pl, rl = len(pfold), len(rfold)
            feedback.pushInfo("Folder tiang terdeteksi : %s" % (", ".join(sorted(pfold)) or "-"))
            feedback.pushInfo("Folder jalur terdeteksi : %s" % (", ".join(sorted(rfold)) or "-"))
            feedback.pushInfo("Folder lain (diabaikan) : %s" % (", ".join(sorted(other)) or "-"))
            if not ppts or not rlines:
                raise QgsProcessingException(
                    "Folder tiang atau jalur tidak ditemukan di KMZ cluster. Folder yang ada: %s. "
                    "Ganti nama foldernya (mis. POLE / ROUTE CABLE) atau pakai isian KMZ terpisah."
                    % ", ".join(sorted(pfold | rfold | other)))
            pole_path = road_path = cluster_kmz
        else:
            own_bnd, kmz_hp = [], []
            kmz_ev0 = 0
            kmz_dupf = set()
            ppts, _, pnames, pl = self._read_kml(pole_path)
            pkinds = [pole_kind([], nm) for nm in pnames]
            pheights = [pole_height([], nm) for nm in pnames]
        uniq, names, kinds, heights = {}, [], [], []
        for p, nm, kd, hh in zip(ppts, pnames, pkinds, pheights):
            k = (round(p.x(), 7), round(p.y(), 7))
            if k not in uniq:
                uniq[k] = p
                names.append(nm)
                kinds.append(kd)
                heights.append(hh)
        poles = list(uniq.values())
        if not poles:
            raise QgsProcessingException("Tidak ada titik tiang di file tiang.")
        orig_names = list(names)
        names, n_renamed = tidy_pole_names(names, kinds)
        n_unk = sum(1 for kd in kinds if kd not in ("new", "existing"))
        pole_out = outp("POLE.kmz")
        if os.path.exists(pole_out):
            os.remove(pole_out)
        write_pole_kmz(pole_out, os.path.splitext(os.path.basename(pole_out))[0],
                       [{"name": nm, "kind": kd, "height": hh, "x": p.x(), "y": p.y(), "orig": on}
                        for p, nm, kd, hh, on in zip(poles, names, kinds, heights, orig_names)])
        # salinan GeoPackage hanya untuk tampilan peta QGIS (KMZ bertingkat dibaca QGIS sebagai beberapa sublayer)
        pole = QgsVectorLayer("Point?crs=EPSG:4326&field=Name:string(80)&field=jenis:string(10)&field=tinggi_m:double"
                              "&field=folder:string(40)", "POLE", "memory")
        pf = []
        for p, nm, kd, hh in zip(poles, names, kinds, heights):
            f = QgsFeature(pole.fields())
            f.setAttributes([nm, kd or "-", float(hh) if hh else None,
                             "EP" if kd == "existing" else ("NP/T%d" % int(hh) if hh else "NP/TINGGI BELUM DIISI")])
            f.setGeometry(QgsGeometry.fromPointXY(p))
            pf.append(f)
        pole.dataProvider().addFeatures(pf)
        pole_map = outp("POLE_PETA.gpkg")
        try:
            if os.path.exists(pole_map):
                os.remove(pole_map)
            self._write(pole, pole_map, "GPKG", context)
        except Exception as e:
            feedback.reportError("Layer peta POLE tidak ditulis (POLE.kmz untuk desain otomatis tetap ada): %s" % e, fatalError=False)
            pole_map = None
        pidx = QgsSpatialIndex()
        for i, p in enumerate(poles):
            g = QgsFeature(i)
            g.setGeometry(QgsGeometry.fromPointXY(p))
            pidx.addFeature(g)
        rep.append("")
        rep.append("TIANG")
        rep.append("  Folder dibaca      : %d%s" % (pl, (" (" + ", ".join(sorted(pfold)) + ")") if cluster_kmz else ""))
        rep.append("  Tiang unik         : %d (duplikat dibuang: %d)" % (len(poles), len(ppts) - len(poles)))
        rep.append("  Jenis tiang        : existing %d, baru %d, tidak dikenali %d"
                   % (kinds.count("existing"), kinds.count("new"), kinds.count("")))
        hc = {}
        for hh in heights:
            hc[hh] = hc.get(hh, 0) + 1
        rep.append("  POLE.kmz           : POLE > NP > T<tinggi> (%d) dan POLE > EP (%d), urut nama"
                   % (len(kinds) - kinds.count("existing"), kinds.count("existing")))
        if n_renamed:
            rep.append("  Nama tiang dirapikan: %d tiang bernama umum/ganda (mis. 'NP', '7M', 'Untitled Placemark') "
                       "diberi nomor NP-xx / EP-xx; nama asli di atribut nama_asli" % n_renamed)
        if n_unk:
            rep.append("  ! %d tiang tanpa tanda NP/EP di nama/folder: dimasukkan ke folder NP. Cek dengan tim Strand." % n_unk)
        rep.append("  Tinggi tiang       : %s" % ", ".join(("%g m: %d" % (k, v)) if k else ("tak tertulis di nama: %d" % v)
                                                          for k, v in sorted(hc.items(), key=lambda kv: kv[0] or 0)))

        def nearest_pole(p):
            ids = pidx.nearestNeighbor(p, 1)
            q = poles[ids[0]]
            return q, da.measureLine(p, q)

        def nearest_idx(p):
            i = pidx.nearestNeighbor(p, 1)[0]
            return i, da.measureLine(p, poles[i])

        # ===== 3. Jalur -> ROADS.shp =====
        feedback.setProgressText("3/3 Snap dan explode jalur")
        if not cluster_kmz:
            _, rlines, _, rl = self._read_kml(road_path)
        if not rlines:
            raise QgsProcessingException("Tidak ada garis jalur di file jalur.")
        road = QgsVectorLayer("LineString?crs=EPSG:4326", "ROADS_raw", "memory")
        rf = []
        for line in rlines:
            f = QgsFeature()
            f.setGeometry(QgsGeometry.fromPolylineXY(line))
            rf.append(f)
        road.dataProvider().addFeatures(rf)
        snapped = processing.run("native:snapgeometries", {
            "INPUT": road, "REFERENCE_LAYER": pole,
            "TOLERANCE": snap_m / M_PER_DEG,
            "BEHAVIOR": 2,  # Prefer aligning nodes, don't insert new vertices (sama dengan SOP)
            "OUTPUT": "TEMPORARY_OUTPUT"}, context=context, feedback=feedback,
            is_child_algorithm=True)["OUTPUT"]
        exploded = processing.run("native:explodelines", {
            "INPUT": snapped, "OUTPUT": "TEMPORARY_OUTPUT"},
            context=context, feedback=feedback, is_child_algorithm=True)["OUTPUT"]
        ex = QgsProcessingUtils.mapLayerFromString(exploded, context)

        out = QgsVectorLayer("LineString?crs=EPSG:4326&field=Name:string(40)&field=LEN_M:double(10,2)",
                             "ROADS", "memory")
        segs, total, long_n, free_n, zero = [], 0.0, 0, 0, 0
        long_list = []    # (panjang, nama tiang, jenis) rentang tiang ke tiang yang melebihi batas
        touched = set()
        edges = []        # (simpul_a, simpul_b, panjang) untuk analisa efisiensi tiang & ujung jalur
        seg_list = []     # (simpul_a, simpul_b, panjang, titik_a, titik_b) untuk rentang tiang ke tiang
        clear_n = clear_rev = 0
        for n, f in enumerate(ex.getFeatures(), 1):
            g = f.geometry()
            if g.isEmpty():
                continue
            ln = g.constGet()
            a = QgsPointXY(ln.startPoint().x(), ln.startPoint().y())
            b = QgsPointXY(ln.endPoint().x(), ln.endPoint().y())
            L = da.measureLine(a, b)
            if L < 0.01:
                zero += 1
                continue
            total += L
            ends, keys = [], []
            for end in (a, b):
                qi, d = nearest_idx(end)
                q = poles[qi]
                keys.append(("P", qi) if d <= 0.5 else ("X", round(end.x(), 7), round(end.y(), 7)))
                if d <= 0.5:
                    touched.add((round(q.x(), 7), round(q.y(), 7)))
                    ends.append(kinds[qi])
                else:
                    ends.append(None)
            if keys[0] != keys[1]:
                edges.append((keys[0], keys[1], L))
                seg_list.append((keys[0], keys[1], L, a, b))
            nf = QgsFeature(out.fields())
            nf.setAttributes(["R%04d" % n, round(L, 2)])
            nf.setGeometry(g)
            segs.append(nf)
        out.dataProvider().addFeatures(segs)
        roads_path = outp("ROADS.shp")
        self._write(out, roads_path, "ESRI Shapefile", context)

        # ----- Titik jalur tanpa tiang (spesifikasi X-02 / UAT-04): nilai per SIMPUL, bukan per ujung ruas -----
        # derajat 1 = ujung jalur sebenarnya; derajat 2 = sambungan dua ruas (lurus -> bukan temuan; belok dinilai
        # dari sudutnya); derajat >= 3 = percabangan. Ambang sudut dari profil (pedoman konstruksi jaringan distribusi TR: 15/30 derajat).
        import math as _m
        b_info, b_warn = float(qcp("bend_info_deg", 15)), float(qcp("bend_warn_deg", 30))
        xadj = {}
        for ka, kb, _L in edges:
            xadj.setdefault(ka, []).append(kb)
            xadj.setdefault(kb, []).append(ka)

        def _kpt(k):
            return poles[k[1]] if k[0] == "P" else QgsPointXY(k[1], k[2])
        n_bend = n_end_free = n_junc = 0
        for k, nb in xadj.items():
            if k[0] != "X":
                continue
            c = _kpt(k)
            qi_, d_ = nearest_idx(c)
            if len(nb) == 1:
                n_end_free += 1
                qc.append((c, "UJUNG_JALUR_TANPA_TIANG", "Ujung jalur %.1f m dari tiang terdekat %s: kabel harus "
                           "berakhir di tiang (tambat akhir)" % (d_, names[qi_] or ""), None, round(d_, 1), 0.5))
            elif len(nb) == 2:
                p1, p2 = _kpt(nb[0]), _kpt(nb[1])
                kx = _m.cos(_m.radians(c.y()))
                v1 = ((c.x() - p1.x()) * kx, c.y() - p1.y())
                v2 = ((p2.x() - c.x()) * kx, p2.y() - c.y())
                n1, n2 = _m.hypot(*v1), _m.hypot(*v2)
                if not n1 or not n2:
                    continue
                ang = _m.degrees(_m.acos(max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))))
                if ang >= b_warn:
                    n_bend += 1
                    qc.append((c, "WARN_BELOKAN_TANPA_TIANG", "Belokan %.0f derajat tanpa tiang (tiang terdekat %s %.1f m): "
                               "pasang tiang tambat/sudut di belokan" % (ang, names[qi_] or "", d_), None, round(ang, 1), b_warn))
                elif ang >= b_info:
                    qc.append((c, "INFO_BELOKAN_KECIL_TANPA_TIANG", "Belokan kecil %.0f derajat tanpa tiang (%.1f m dari %s)"
                               % (ang, d_, names[qi_] or ""), None, round(ang, 1), b_info))
            else:
                n_junc += 1
                qc.append((c, "WARN_SIMPANG_TANPA_TIANG", "Percabangan %d arah tanpa tiang (tiang terdekat %.1f m)"
                           % (len(nb), d_), None, len(nb), 2))
        free_n = n_end_free + n_bend + n_junc

        # ----- Rentang tiang ke tiang SEPANJANG JALUR (melewati titik belok tanpa tiang) -----
        spans = trace_spans(seg_list)
        # Tiang yang berdiri TEPAT di garis jalur (<= 3 m) tetapi tidak menjadi titik sudut garis: vendor menggambar
        # kabel lurus melewati tiang. desain otomatis memotong jalur di cutting point seperti ini, jadi rentangnya dipecah di
        # tiang tersebut (dan tiangnya tidak dianggap nganggur).
        spans, on_line = split_spans_at_poles(spans, poles, pidx, POLE_ON_LINE_M)
        for qi in on_line:
            touched.add((round(poles[qi].x(), 7), round(poles[qi].y(), 7)))
        if on_line:
            rep.append("  Tiang di tengah garis jalur (<= %.0f m, tanpa titik sudut): %d -> rentang dipecah di tiang itu"
                       % (POLE_ON_LINE_M, len(on_line)))
        span_scope = opt.get("span_scope", 0)
        n_epep = n_reg = n_low6 = 0
        span_layer_rows = []      # untuk QC per kategori
        # Dua garis jalur yang saling menumpang (mis. jalur utama + garis 'Penanda' di folder yang sama) menghasilkan
        # rentang tiang yang sama dua kali (A-B dan B-A). Satu rentang fisik = satu penilaian.
        seen_span, n_dup_span = set(), 0
        for ka, kb, L, pts in spans:
            if ka[0] != "P" or kb[0] != "P":
                continue          # ujung jalur tanpa tiang: dicek di analisa ujung jalur
            key_ = (frozenset((ka, kb)), int(round(L / 2.0)))
            if key_ in seen_span:
                n_dup_span += 1
                continue
            seen_span.add(key_)
            ta, tb = kinds[ka[1]], kinds[kb[1]]
            na, nb = names[ka[1]] or "tiang", names[kb[1]] or "tiang"
            pn = "%s - %s" % (na, nb)
            mid = line_mid(pts)
            ex_a, ex_b = ta == "existing", tb == "existing"
            if ex_a and ex_b:
                n_epep += 1      # EP-EP / EXT-EXT: tiang milik pihak lain, jaraknya tidak dinilai
                continue
            jenis = "NP-NP" if not ex_a and not ex_b else "NP-EP"
            if jenis == "NP-EP" and span_scope == 1:
                continue
            if L > span_max:
                long_n += 1
                long_list.append((L, pn, jenis))
                qc.append((mid, "RENTANG_%s" % jenis.replace("-", "_"),
                           "%s: rentang %s %.1f m > %.0f m (sepanjang jalur); sisipkan tiang di tengah%s" % (
                               pn, jenis, L, span_max,
                               (" - selisih %.1f m masih di bawah akurasi GPS ponsel +-%.0f m: ukur ulang di lapangan dulu"
                                % (L - span_max, hp_tol)) if L - span_max < hp_tol else ""), pts, round(L, 1), span_max))
            elif L > span_reg:
                n_reg += 1
                qc.append((mid, "WARN_RENTANG_REGULASI",
                           "%s: rentang %s %.1f m, di atas batas regulasi daerah %.0f m (Perwal/rancangan Permen Kominfo)"
                           " tetapi <= %.0f m Handbook: perlu justifikasi/izin pemda" % (pn, jenis, L, span_reg, span_max),
                           pts, round(L, 1), span_reg))
            # tinggi kabel di tengah bentang = tinggi klem terendah - lendutan (profil: 2%) x bentang [R1][R2][R3]
            hs = [heights[ka[1]], heights[kb[1]]]
            if all(hs) and max(hs) <= 6.0:
                n_low6 += 1      # tiang 6 m memang untuk gang (kabel < 5 m): diringkas, tidak ditandai per rentang
            elif all(hs):
                # pita: >= ruang bebas jalan = lolos; antara batas gagal (NESC 232-1: 4,7 m) dan ruang bebas = tinjau
                # (hanya diringkas); < batas gagal = INFO per rentang. Data jalan tidak tersedia -> tidak diketahui
                # apakah bentang melintang jalan, sehingga tingkatnya INFO (catatan), bukan pelanggaran.
                clr = min(attach_height(h, embed_frac) for h in hs) - sag_ratio * L
                if clear_fail <= clr < clear_road:
                    clear_rev += 1
                elif clr < clear_fail:
                    clear_n += 1
                    qc.append((mid, "INFO_KABEL_RENDAH",
                               "%s: bentang %.0f m (tiang %s m, lendutan %.1f%%): kabel di tengah bentang +-%.1f m dari tanah "
                               "(< %.1f m). Aman di sepanjang tepi jalan/gang; bila melintang jalan pakai tiang 9 m "
                               "atau perpendek bentang" % (
                                   pn, L, "/".join("%g" % h for h in hs), sag_ratio * 100, clr, clear_fail),
                               pts, round(clr, 2), clear_fail))
        rep.append("")
        rep.append("RENTANG TIANG KE TIANG (sepanjang jalur, termasuk belokan tanpa tiang)")
        rep.append("  Rentang dinilai    : NP-NP%s; EP-EP tidak dinilai (%d rentang, tiang pihak lain)"
                   % (" dan NP-EP" if span_scope == 0 else " saja", n_epep))
        if n_dup_span:
            rep.append("  Rentang ganda (garis jalur bertumpuk) diabaikan: %d" % n_dup_span)
        rep.append("  > %.0f m (CEK)       : %d" % (span_max, long_n))
        rep.append("  %.0f-%.0f m (WARNING regulasi daerah %.0f m): %d" % (span_reg, span_max, span_reg, n_reg))
        if n_low6:
            rep.append("  Info: %d rentang antar tiang 6 m -> kabel tengah bentang < %.1f m (tinggi klem +-%.1f m): hanya untuk "
                       "gang/jalan kecil; crossing jalan raya pakai tiang 9 m (Permen PU 20/2010; Perwal Pekalongan 34/2025). "
                       "Tiang 6 m di luar daftar tinggi tiang 7/8/9 m pedoman infrastruktur bersama Kominfo: pastikan disetujui pemda"
                       % (n_low6, clear_road, attach_height(6.0, embed_frac)))

        idle = [(p, nm_) for p, nm_ in zip(poles, names) if (round(p.x(), 7), round(p.y(), 7)) not in touched]
        for p, nm_ in idle:
            qc.append((p, "TIANG_NGANGGUR", "%s tidak dilewati jalur (pole nganggur)" % nm_))
        far, far_list = 0, []
        serve = {}          # tiang -> daftar HP yang tiang terdekatnya tiang ini
        for k_, (r, p) in enumerate(data):
            qi, d = nearest_idx(p)
            serve.setdefault(qi, []).append(p)
            if d > hp_max:
                far += 1
                hid_ = r[iid] if iid is not None else "HP %d" % (k_ + 1)
                far_list.append((d, hid_, names[qi]))
                qc.append((p, "HP_JAUH_DARI_TIANG",
                           "%s (baris %d HPDB): %.1f m ke tiang terdekat %s (batas %.0f m)"
                           % (hid_, meta[k_][0], d, names[qi], hp_max), None, round(d, 1), hp_max))

        # ===== 3a. Efisiensi tiang & ujung jalur (Handbook QC: "minimalisir tiang", "kabel loop <= 100 m / 2 span") =====
        import math
        adj = {}
        for ka, kb, L in edges:
            adj.setdefault(ka, []).append((kb, L))
            adj.setdefault(kb, []).append((ka, L))

        def node_pt(k):
            return poles[k[1]] if k[0] == "P" else QgsPointXY(k[1], k[2])
        removable = []
        for k, nb in adj.items():
            if k[0] != "P" or len(nb) != 2 or kinds[k[1]] != "new":
                continue
            (k1, l1), (k2, l2) = nb
            if l1 + l2 > span_max:
                continue
            c, p1, p2 = node_pt(k), node_pt(k1), node_pt(k2)
            v1 = ((p1.x() - c.x()) * math.cos(math.radians(c.y())), p1.y() - c.y())
            v2 = ((p2.x() - c.x()) * math.cos(math.radians(c.y())), p2.y() - c.y())
            n1, n2 = math.hypot(*v1), math.hypot(*v2)
            if not n1 or not n2:
                continue
            ang = math.degrees(math.acos(max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))))
            if ang < 170:
                continue                      # di belokan tiang wajib ada
            ok = True
            for hp_pt in serve.get(k[1], []):
                ids = pidx.nearestNeighbor(hp_pt, 2)
                alt = [j for j in ids if j != k[1]]
                if not alt or da.measureLine(hp_pt, poles[alt[0]]) > hp_max:
                    ok = False
                    break
            if ok:
                removable.append(k[1])
                qc.append((c, "INFO_TIANG_BISA_DIHAPUS", "NP di jalan lurus, rentang gabungan %.0f m <= %.0f m" % (l1 + l2, span_max)))
        loops = 0
        for k, nb in adj.items():
            if len(nb) != 1:
                continue
            # telusuri dari ujung sampai simpang; catat ekor tanpa HP (calon kabel loop)
            prev, cur, tail_len, tail_span, seen_k = None, k, 0.0, 0, {k}
            while True:
                if cur[0] == "P" and serve.get(cur[1]):
                    break
                nxt = [(kk, L) for kk, L in adj.get(cur, []) if kk != prev and kk not in seen_k]
                if len(adj.get(cur, [])) > 2 or not nxt:
                    break
                prev, (cur, L) = cur, nxt[0]
                seen_k.add(cur)
                tail_len += L
                tail_span += 1
            if tail_len > 100 or tail_span > 2:
                loops += 1
                qc.append((node_pt(k), "INFO_UJUNG_JALUR_TANPA_HP",
                           "Ujung jalur %.0f m / %d span tanpa HP (kabel loop maks 100 m atau 2 span)" % (tail_len, tail_span)))

        rep.append("")
        rep.append("JALUR")
        rep.append("  Folder dibaca      : %d%s, garis asli: %d" % (rl, (" (" + ", ".join(sorted(rfold)) + ")") if cluster_kmz else "", len(rlines)))
        rep.append("  Ruas hasil explode : %d (ruas nol dibuang: %d)" % (len(segs), zero))
        rep.append("  Total panjang      : %.0f m" % total)
        rep.append("")
        rep.append("CEK QC OTOMATIS")
        rep.append("  Rentang tiang ke tiang > %.0f m : %d (NP-NP%s, sepanjang jalur; EP-EP tidak dinilai)" % (
            span_max, long_n, " & NP-EP" if opt.get("span_scope", 0) == 0 else ""))
        for L_, pn_, jn_ in sorted(long_list, reverse=True)[:30]:
            rep.append("    - %6.1f m  %s  [%s]" % (L_, pn_, jn_))
        rep.append("  Titik jalur tanpa tiang     : %d (ujung %d, belokan >= %.0f derajat %d, simpang %d; sambungan lurus "
                   "tidak dihitung)" % (free_n, n_end_free, b_warn, n_bend, n_junc))
        rep.append("  Tiang nganggur              : %d" % len(idle))
        rep.append("  Info: NP bisa dihapus (lurus): %d   ujung jalur tanpa HP > 100 m/2 span: %d" % (len(removable), loops))
        rep.append("  Info: kabel tengah bentang < %.1f m (tanam 1/%.0f tinggi tiang, lendutan %.1f%%): %d; %.1f-%.1f m (tinjau bila "
                   "melintang jalan): %d" % (clear_fail, 1.0 / embed_frac if embed_frac else 0, sag_ratio * 100, clear_n,
                                             clear_fail, clear_road, clear_rev))
        rep.append("  Dasar aturan: [R1]-[R5] di DASAR_ATURAN.md (folder plugin)")
        rep.append("  HP > %.0f m dari tiang      : %d" % (hp_max, far))
        rep.append("  HP duplikat (koordinat/ID)  : %d / %d" % (dup, dup_id))
        rep.append("  Detail lokasi: %sQC_TEMUAN.shp (QGIS) dan %sQC_TEMUAN.kmz (aplikasi peta KMZ)" % (pre, pre))
        far_list.sort(reverse=True)
        std = {1: (far == 0, ("%d HP lebih dari %.0f m ke tiang: %s%s" % (
            far, hp_max, "; ".join("%s %.1f m ke %s" % (h, d, t) for d, h, t in far_list[:3]),
            " ..." if far > 3 else "")) if far else "semua %d HP <= %.0f m ke tiang" % (len(data), hp_max))}
        m_id = re.search(r"(?<!\d)(\d{9,12})(?!\d)", os.path.basename(hpdb))
        cl_id = m_id.group(1) if m_id else ""

        # ===== 3b. HP di HPDB vs HP di KMZ (standar no. 4) =====
        rep.append("")
        rep.append("HPDB vs KMZ (HOMEPASS)")
        n_kmz = len(kmz_hp)
        if kmz_hp:
            kidx = QgsSpatialIndex()
            for i, (g, nm) in enumerate(kmz_hp):
                ft = QgsFeature(i)
                ft.setGeometry(QgsGeometry.fromPointXY(g))
                kidx.addFeature(ft)
            hidx = QgsSpatialIndex()
            for i, (r, p) in enumerate(data):
                ft = QgsFeature(i)
                ft.setGeometry(QgsGeometry.fromPointXY(p))
                hidx.addFeature(ft)
            # pasangan satu-satu: setiap titik KMZ hanya boleh dipakai satu baris HPDB (agar HP duplikat terhitung)
            cand = []
            for i, (r, p) in enumerate(data):
                for j in kidx.nearestNeighbor(p, 4):
                    d = da.measureLine(p, kmz_hp[j][0])
                    if d <= hp_tol:
                        cand.append((d, i, j))
            cand.sort()
            pair_h, pair_k = {}, {}
            for d, i, j in cand:
                if i not in pair_h and j not in pair_k:
                    pair_h[i], pair_k[j] = j, i
            no_kmz = no_hpdb = n_geser = 0
            dup_idx = {k for j_, ks in dup_groups if j_ == "koordinat sama" for k in ks}
            # Tahap 2 - pasangan berdasarkan identitas: nomor rumah HPDB = nama titik KMZ (aplikasi survei menamai titik
            # dengan nomor rumah) dan jarak <= hp_shift_max. Rumah yang sama dengan koordinat bergeser (galat GPS ponsel
            # 7-13 m di permukiman, Merry & Bettinger 2019) dilaporkan sekali sebagai HP_BERGESER, bukan dua temuan
            # 'tidak ada'.
            shift_max = float(opt.get("hp_shift_max", 30.0) or 30.0)
            hn_i = i_adr[1]

            def _norm_no(v):
                v = re.sub(r"\s+", "", str(v or "")).upper().lstrip("?-").lstrip("0")
                return v

            kname = {}
            for j, (g, nm) in enumerate(kmz_hp):
                if j not in pair_k and j < kmz_ev0 and j not in kmz_dupf and _norm_no(nm):
                    kname.setdefault(_norm_no(nm), []).append(j)
            for i, (r, p) in enumerate(data):
                if i in pair_h or hn_i is None or hn_i >= len(r):
                    continue
                key = _norm_no(r[hn_i])
                if not key or key in ("-", ""):
                    continue
                best = min(((da.measureLine(p, kmz_hp[j][0]), j) for j in kname.get(key, []) if j not in pair_k),
                           default=None)
                if best and best[0] <= shift_max:
                    pair_h[i], pair_k[best[1]] = best[1], i
                    n_geser += 1
                    qc.append((p, "HP_BERGESER", "%s: no. rumah %s sama dengan titik KMZ '%s' tetapi koordinat bergeser %.1f m"
                               " (> %.0f m); samakan koordinat HPDB dengan KMZ" % (
                                   _hpname(i), r[hn_i].strip(), kmz_hp[best[1]][1], best[0], hp_tol)))
            for i, (r, p) in enumerate(data):
                if i in pair_h:
                    continue
                no_kmz += 1
                j = kidx.nearestNeighbor(p, 1)[0]
                d = da.measureLine(p, kmz_hp[j][0])
                why = "duplikat koordinat; titik KMZ-nya sudah dipakai baris lain" if i in dup_idx and d <= hp_tol \
                    else "HP KMZ terdekat %.1f m, tidak ada titik KMZ dengan no. rumah sama" % d
                qc.append((p, "HP_HPDB_TIDAK_ADA_DI_KMZ", "%s: %s" % (_hpname(i), why)))
            n_ev = len(kmz_hp) - kmz_ev0
            ev_used = sum(1 for j in pair_k if j >= kmz_ev0)
            n_kmz = kmz_ev0 + ev_used          # HP KMZ efektif: folder HP + titik evidence yang berpasangan HPDB
            for j, (g, nm) in enumerate(kmz_hp):
                if j in pair_k or j >= kmz_ev0 or j in kmz_dupf:
                    continue
                no_hpdb += 1
                i = hidx.nearestNeighbor(g, 1)[0]
                d = da.measureLine(g, data[i][1])
                qc.append((g, "HP_KMZ_TIDAK_ADA_DI_HPDB", "%s: HP HPDB terdekat %.1f m" % (nm or "HP KMZ", d)))
            kmz_dup = kmz_ev0 - len({(round(g.x(), 6), round(g.y(), 6)) for g, _n in kmz_hp[:kmz_ev0]})
            rep.append("  Jumlah HP          : HPDB %d, KMZ %d (selisih %+d)%s" % (
                len(data), n_kmz, n_kmz - len(data),
                (" - termasuk %d dari %d titik sub-folder EVIDENCE (foto bukti) yang berpasangan dengan HPDB" % (ev_used, n_ev))
                if n_ev else ""))
            rep.append("  HP duplikat        : HPDB %d (koordinat) / %d (ID operator), KMZ %d (koordinat)" % (dup, dup_id, kmz_dup))
            rep.append("  HPDB tanpa pasangan di KMZ (> %.0f m atau duplikat) : %d" % (hp_tol, no_kmz))
            rep.append("  KMZ tanpa pasangan di HPDB (> %.0f m)              : %d%s" % (
                hp_tol, no_hpdb, (" (titik folder DUPLIKAT %d tidak dihitung ulang)" % len(kmz_dupf)) if kmz_dupf else ""))
            rep.append("  HP sama (no. rumah) tapi bergeser %.0f-%.0f m     : %d" % (hp_tol, shift_max, n_geser))
            # Cakupan: HPDB jauh lebih sedikit dari KMZ -> kemungkinan HPDB hanya sebagian dari survei
            if n_kmz >= 1.5 * max(1, len(data)) and no_hpdb >= 10:
                rep.append("  Info cakupan: KMZ memuat %d HP, HPDB %d baris - HPDB kemungkinan hanya sebagian wilayah survei;"
                           " pastikan cakupan pengajuan sebelum memperbaiki satu per satu" % (n_kmz, len(data)))
                parts_scope = "cakupan: KMZ %d vs HPDB %d (HPDB kemungkinan sebagian survei)" % (n_kmz, len(data))
            else:
                parts_scope = ""
            ci = _col("CLUSTER_NAME")
            if ci is not None:
                cn = Counter(r[ci].strip() for r, _p in data if ci < len(r) and r[ci].strip() not in ("", "-"))
                if len(cn) > 1:
                    rep.append("  Info: CLUSTER_NAME HPDB bercampur: %s" % ", ".join("%s %d" % kv for kv in cn.most_common()))
                    parts_scope = (parts_scope + "; " if parts_scope else "") + "CLUSTER_NAME bercampur (%s)" % ", ".join(
                        "%s %d" % kv for kv in cn.most_common())
            parts = ["HPDB %d vs KMZ %d%s" % (len(data), n_kmz, (" (%d dari folder EVIDENCE)" % ev_used) if ev_used else "")]
            if dup or dup_id or kmz_dup:
                parts.append("HP duplikat: %s" % ", ".join(x for x in (
                    ("%d koordinat sama di HPDB" % dup) if dup else "", ("%d ID operator sama" % dup_id) if dup_id else "",
                    ("%d koordinat sama di KMZ" % kmz_dup) if kmz_dup else "") if x))
                first = [g for j_, g in dup_groups if j_ in ("koordinat sama", "ID operator sama")][:2]
                if first:
                    parts.append("contoh " + "; ".join(" & ".join(_hpname(k) for k in g) for g in first))
            parts.append("tanpa pasangan: HPDB %d, KMZ %d" % (no_kmz, no_hpdb))
            if n_geser:
                parts.append("%d HP sama no. rumah tapi koordinat bergeser" % n_geser)
            if parts_scope:
                parts.append(parts_scope)
            m_nhp = re.search(r"(?<![0-9])(\d{1,5})\s*HP(?![A-Za-z])", os.path.basename(hpdb), re.IGNORECASE)
            if m_nhp and int(m_nhp.group(1)) != len(data):
                parts.append("info: nama file HPDB menyebut %s HP, isi HPDB %d baris valid" % (m_nhp.group(1), len(data)))
                rep.append("  Info: nama file HPDB menyebut %s HP, isi HPDB %d baris valid (cek versi HPDB/TSSR)"
                           % (m_nhp.group(1), len(data)))
            std[4] = (no_kmz == 0 and no_hpdb == 0 and n_geser == 0 and n_kmz == len(data) and not dup and not dup_id and not kmz_dup,
                      "; ".join(parts))
        else:
            rep.append("  Folder HP tidak ditemukan di KMZ cluster (cek dilewati)")
            std[4] = ((False, "folder HP tidak ada di KMZ; HP duplikat di HPDB: %d koordinat, %d ID operator" % (dup, dup_id))
                      if (dup or dup_id) else (None, "folder HP tidak ada di KMZ"))

        # ===== 3c. HPDB vs HPDB attributes / FINDIM (standar no. 3) =====
        rep.append("")
        rep.append("ADMINISTRASI HPDB vs FINDIM (hpdb attributes)")
        att, findim_ids, olt_reg = None, set(), None
        if funnel_dir:
            ac = ref_files(funnel_dir, "attributes")
            for pth, tgl, nver in latest_per_kind(ac)[:1]:
                umur = (_dt.date.today() - tgl).days
                rep.append("  File attributes    : %s (tanggal %s%s)" % (
                    os.path.basename(pth), tgl.strftime("%d-%m-%Y"),
                    ", %d versi lama diabaikan" % (nver - 1) if nver > 1 else ""))
                if umur > 90:
                    rep.append("  ! Nama file bertanggal %d hari lalu; pastikan ini versi FINDIM terbaru." % umur)
                try:
                    att = load_attributes(pth, feedback)
                except Exception as e:
                    feedback.reportError("HPDB attributes tidak bisa dibaca: %s" % e, fatalError=False)
        if att and att["findim"]:
            def ci(*names):
                return self._pick(headers, list(names), "\x00")

            def combos(rows_, ix):
                cnt = {}
                for r_ in rows_:
                    k = tuple((r_[i].strip() if i is not None and i < len(r_) else "") for i in ix)
                    if any(k):
                        cnt[k] = cnt.get(k, 0) + 1
                return cnt
            ixk = [ci("SUBDISTRICT", "KELURAHAN"), ci("DISTRICT", "KECAMATAN"), ci("CITY", "KOTA"),
                   ci("PROVINCE", "PROVINSI")]
            ipos, ireg = ci("POSTAL_CODE", "KODE_POS"), self._pick_rx(headers, r"^[A-Z]*BUSINESSAREA$")
            bad_admin = 0
            ok_admin = 0
            hp_diffs = []     # ringkasan isian HP yang beda: "kota (tertulis X, FINDIM Y)"
            other_bad = []    # (nama sheet, jumlah baris, beda kolom apa)
            for (kel, kec, city, prov), n in sorted(combos([r for r, _ in data], ixk).items(), key=lambda kv: -kv[1]):
                stt, best, diff, sug = check_admin(att, kel, kec, city, prov)
                rep.append("  HP  %3d baris: %s / %s / %s / %s -> %s" % (n, kel or "-", kec or "-", city or "-", prov or "-", stt))
                if best:
                    findim_ids.add(best["id"])
                    rep.append("      FINDIM: %s %s, Kec. %s, %s, %s (kode pos %s, region %s)" % (
                        best["id"], best["kel"], best["kec"], best["city"], best["prov"], best["pos"] or "-", best["reg"] or "-"))
                for sg in sug:
                    rep.append("      saran: %s" % sg)
                if stt == "OK":
                    ok_admin += n
                else:
                    bad_admin += n
                    hp_diffs.append("%d baris %s%s" % (n, _admin_diff_txt(stt, diff, best, kel, kec, city, prov),
                                                       ("; kemungkinan salah ketik, ejaan FINDIM: %s" % sug[0]) if sug else ""))
                    pts = [p for r, p in data if tuple((r[i].strip() if i is not None and i < len(r) else "") for i in ixk) == (kel, kec, city, prov)]
                    cx_ = sum(q.x() for q in pts) / len(pts)
                    cy_ = sum(q.y() for q in pts) / len(pts)
                    qc.append((QgsPointXY(cx_, cy_), "ADMIN_" + stt,
                               "%d HP: %s/%s/%s -> FINDIM %s%s" % (n, kel, kec, city,
                                                                   ("Kec. %s, %s" % (best["kec"], best["city"])) if best else "tidak ada",
                                                                   (". Mungkin maksudnya %s" % sug[0]) if sug else "")))
                if best and ipos is not None:
                    pos = {r[ipos] for r, _ in data if ipos < len(r) and r[ipos] not in ("", "-")}
                    if best["pos"] and pos and pos != {best["pos"]}:
                        rep.append("      info: kode pos HPDB %s, FINDIM %s" % (", ".join(sorted(pos)), best["pos"]))
                if best and ireg is not None:
                    reg = {r[ireg] for r, _ in data if ireg < len(r) and r[ireg] not in ("", "-")}
                    if best["reg"] and reg and reg != {best["reg"]}:
                        rep.append("      info: BUSINESS_AREA HPDB %s, region FINDIM %s" % (", ".join(sorted(reg)), best["reg"]))
            # sheet tiang di HPDB (kolom PROVINSI/KOTA/KECAMATAN/KELURAHAN)
            for sname, srows in getattr(self, "_sheets", []):
                if sname == getattr(self, "_hp_sheet", None):
                    continue          # sheet homepass sudah dicek di atas
                hi = None
                for i, r in enumerate(srows[:10]):
                    nr = [self._norm(c) for c in r]
                    if "KELURAHAN" in nr and "KECAMATAN" in nr:
                        hi = i
                        break
                if hi is None:
                    continue
                nr = [self._norm(c) for c in srows[hi]]
                ix = [nr.index(k) if k in nr else None for k in ("KELURAHAN", "KECAMATAN", "KOTA", "PROVINSI")]
                for (kel, kec, city, prov), n in combos(srows[hi + 1:], ix).items():
                    if self._norm(kel) in ("KELURAHAN", "SUBDISTRICT"):
                        continue
                    stt, best, diff, sug = check_admin(att, kel, kec, city, prov)
                    if stt != "OK":
                        other_bad.append((sname.strip(), n, _admin_diff_txt(stt, diff, best, kel, kec, city, prov)))
                        rep.append("  Sheet %s, %d baris: %s / %s / %s / %s -> %s%s" % (
                            sname.strip(), n, kel, kec, city, prov, stt,
                            (" (FINDIM: Kec. %s, %s, %s)" % (best["kec"], best["city"], best["prov"])) if best else ""))
            # cluster terdaftar di OLT CLUSTER?
            if cl_id:
                olt_reg = att["olt"].get(cl_id)
                if olt_reg:
                    rep.append("  ID cluster %s terdaftar: %s -> %s" % (cl_id, olt_reg[0], olt_reg[1]))
                else:
                    rep.append("  ! ID cluster %s TIDAK ada di sheet OLT CLUSTER" % cl_id)
                    qc.append((data[0][1], "ADMIN_ID_CLUSTER_TIDAK_TERDAFTAR", "ID %s tidak ada di OLT CLUSTER" % cl_id))
            # Status dari sheet HOMEPASS (data yang masuk sistem). Sheet lain (mis. daftar tiang) = info.
            t3 = ("sheet HP: %d baris sesuai FINDIM" % ok_admin) if not bad_admin else \
                "sheet HP: %d baris beda dengan FINDIM (%s)" % (bad_admin, "; ".join(hp_diffs[:2]))
            if other_bad:
                t3 += "; info sheet %s" % "; sheet ".join("'%s' %d baris %s" % x for x in other_bad[:2])
                rep.append("  Catatan: status standar 3 dihitung dari sheet homepass. Sheet lain hanya info, tetap rapikan.")
            std[3] = (bad_admin == 0, t3)
        else:
            rep.append("  hpdb_attributes*.xlsx tidak ada di folder referensi (cek dilewati)")
            std[3] = (None, "file hpdb attributes tidak ada")

        # ===== 4. Cek boundary: BOUNDARY cluster + Funnel =====
        hp_xy = [(p.x(), p.y(), (r[iid] if iid is not None else "HP")) for r, p in data]
        funnel_files, funnel_info = [], []
        if funnel_dir and os.path.isdir(funnel_dir):
            cands = ref_files(funnel_dir, "funnel")
            for pth, tgl, nver in latest_per_kind(cands):
                funnel_files.append(pth)
                umur = (_dt.date.today() - tgl).days
                funnel_info.append("%s (tanggal %s, %d hari lalu%s)" % (
                    os.path.basename(pth), tgl.strftime("%d-%m-%Y"), umur,
                    ", %d versi lama diabaikan" % (nver - 1) if nver > 1 else ""))
                if umur > 2:
                    qc_warn = "PERINGATAN: data Funnel %s sudah %d hari; minta versi terbaru." % (os.path.basename(pth), umur)
                    feedback.reportError(qc_warn, fatalError=False)
                    rep.append("  " + qc_warn)
        rep.append("")
        rep.append("BOUNDARY")
        cname = cluster_label(outdir, hpdb)
        # Pita ragu (pass / review / fail): titik HP berasal dari GPS ponsel (rata-rata 4,9 m langit terbuka, 7-13 m
        # urban) dan garis BOUNDARY digambar tangan -> HP yang hanya beberapa meter di luar garis = INFO "di tepi".
        bnd_tol = float(qcp("boundary_edge_tol_m", 10.0))
        edge_own = []
        if own_bnd:
            out_own = []
            for x, y, hid in hp_xy:
                if any(in_poly(x, y, g) for g in own_bnd):
                    continue
                d = min(dist_to_poly_m(x, y, g) for g in own_bnd)
                if d <= bnd_tol:
                    edge_own.append((x, y, hid))
                    qc.append((QgsPointXY(x, y), "INFO_HP_TEPI_BOUNDARY",
                               "%s %.1f m di luar garis BOUNDARY (dalam toleransi GPS %.0f m)" % (hid, d, bnd_tol),
                               None, round(d, 1), bnd_tol))
                else:
                    out_own.append((x, y, hid))
                    qc.append((QgsPointXY(x, y), "HP_LUAR_BOUNDARY",
                               "%s %.1f m di luar BOUNDARY cluster (> %.0f m)" % (hid, d, bnd_tol), None, round(d, 1), bnd_tol))
            rep.append("  BOUNDARY di KMZ cluster      : %d poligon" % len(own_bnd))
            rep.append("  HP di luar BOUNDARY sendiri  : %d (> %.0f m dari garis)" % (len(out_own), bnd_tol))
            rep.append("  HP di tepi BOUNDARY (info)   : %d (<= %.0f m dari garis; galat GPS ponsel)" % (len(edge_own), bnd_tol))
        else:
            out_own = []
            rep.append("  BOUNDARY di KMZ cluster      : tidak ditemukan (cek dilewati)")
        near, mine, out_fun, edge_fun, mine_status = [], None, [], [], ""
        std[2] = (None, "Funnel tidak diisi")
        std[5] = (len(out_own) == 0 if own_bnd else None, "%d HP di luar BOUNDARY KMZ (> %.0f m), %d di tepi"
                  % (len(out_own), bnd_tol, len(edge_own)))
        if funnel_files:
            feedback.setProgressText("4/4 Cek boundary Funnel")
            xs = [h[0] for h in hp_xy]
            ys = [h[1] for h in hp_xy]
            m = 0.01  # +- 1 km
            fext = (min(xs) - m, min(ys) - m, max(xs) + m, max(ys) + m)
            near, fun_err = [], []
            for fp in funnel_files:
                try:
                    near.extend(cached_read("funnel", fp, fext, read_funnel, feedback))
                except Exception as e:      # file rusak / unduhan terpotong: jangan hentikan Run
                    fun_err.append("%s (%s)" % (os.path.basename(fp), str(e)[:120]))
                    feedback.reportError("File Funnel tidak bisa dibaca, mungkin rusak/terpotong saat diunduh: %s"
                                         % fun_err[-1], fatalError=False)
            hits = {}
            for x, y, hid in hp_xy:
                for f in near:
                    bb = f["bb"]
                    if bb[0] <= x <= bb[2] and bb[1] <= y <= bb[3] and in_poly(x, y, f["poly"]):
                        hits.setdefault((f["grp"], f["name"], f["status"], f["plan"]), []).append((x, y, hid))
            # funnel milik cluster ini = Boundary Funnel / RFS EXTENSION yang memuat HP terbanyak
            cand = [(len(v), k) for k, v in hits.items() if not k[0].upper().startswith("RFS DONE")]
            if cand:
                mine = max(cand)[1]
            for info in funnel_info:
                rep.append("  File Funnel dipakai          : %s" % info)
            rep.append("  Poligon Funnel di sekitar    : %d (radius +- 1 km dari HP)" % len(near))
            for e in fun_err:
                rep.append("  ! File Funnel GAGAL dibaca   : %s -> unduh ulang file ini" % e)
            if not near:
                rep.append("  ! Tidak ada poligon Funnel di sekitar cluster: file Funnel yang ada tidak mencakup")
                rep.append("    kota/lokasi cluster ini, atau koordinat HP salah. Tambahkan file Funnel kota ini ke folder referensi.")
            if mine:
                n_in = len(hits[mine])
                rep.append("  Funnel cluster ini           : %s [%s, status %s]" % (mine[1], mine[0], mine[2] or "-"))
                rep.append("  HP_Plan Funnel vs HP aktual  : %s vs %d" % (mine[3] or "-", len(hp_xy)))
                rep.append("  HP di dalam funnel sendiri   : %d dari %d" % (n_in, len(hp_xy)))
                mine_status = mine[2] or ""
                # Standar no. 5: HP di luar boundary Funnel milik cluster ini.
                # Area sendiri = semua poligon (Boundary Funnel / RFS EXTENSION) dengan nama dasar yang sama.
                mb = _base(mine[1])
                own_f = [f for f in near if _base(f["name"]) == mb and not f["grp"].upper().startswith("RFS DONE")]
                for x, y, hid in hp_xy:
                    if not any(f["bb"][0] <= x <= f["bb"][2] and f["bb"][1] <= y <= f["bb"][3]
                               and in_poly(x, y, f["poly"]) for f in own_f):
                        d = min(dist_to_poly_m(x, y, f["poly"]) for f in own_f)
                        if d <= fun_tol:
                            edge_fun.append((x, y, hid))
                            qc.append((QgsPointXY(x, y), "INFO_HP_TEPI_FUNNEL",
                                       "%s %.1f m di luar tepi Funnel %s" % (hid, d, mine[1]), None, round(d, 1), fun_tol))
                        else:
                            out_fun.append((x, y, hid))
                            qc.append((QgsPointXY(x, y), "HP_LUAR_FUNNEL",
                                       "%s %.1f m di luar boundary Funnel %s" % (hid, d, mine[1]), None, round(d, 1), fun_tol))
                rep.append("  HP di luar Funnel sendiri    : %d (> %.0f m dari tepi)" % (len(out_fun), fun_tol))
                rep.append("  HP di tepi luar Funnel (info): %d (<= %.0f m dari tepi)" % (len(edge_fun), fun_tol))
                if INACTIVE_RX.search(mine_status):
                    rep.append("  ! STATUS FUNNEL CLUSTER INI: %s -> konfirmasi sebelum desain" % mine_status)
                    qc.append((QgsPointXY(hp_xy[0][0], hp_xy[0][1]), "FUNNEL_SENDIRI_REJECT",
                               "Funnel %s berstatus %s" % (mine[1], mine_status)))
            else:
                rep.append("  Funnel cluster ini           : tidak ditemukan (tidak ada HP di dalam Boundary Funnel)")
            if mine:
                std[5] = (not out_own and not out_fun,
                          "%d HP di luar Funnel, %d di tepi (<= %.0f m), %d di luar BOUNDARY KMZ (> %.0f m), %d di tepi BOUNDARY"
                          % (len(out_fun), len(edge_fun), fun_tol, len(out_own), bnd_tol, len(edge_own)))
            elif not near:
                std[5] = (False, "File Funnel tidak mencakup lokasi cluster (0 poligon dalam 1 km)%s; "
                                 "tambahkan Funnel kota ini" % ("; file rusak: " + fun_err[0] if fun_err else ""))
            else:
                std[5] = (False, "Funnel cluster ini tidak ditemukan (%d poligon di sekitar, tidak ada yang memuat HP)"
                          % len(near))
            mine_base = _base(mine[1]) if mine else _base(cname)
            n_done = n_ext = n_act = n_rej = 0
            for k, pts in sorted(hits.items(), key=lambda kv: -len(kv[1])):
                grp, nm, status, plan = k
                if k == mine:
                    continue
                g = grp.upper()
                if g.startswith("RFS DONE"):
                    kind, n_done = "HP_DI_RFS_DONE", n_done + len(pts)
                    ket = "masuk cluster TERBANGUN %s (risiko double tagging)" % nm
                elif INACTIVE_RX.search(status or ""):
                    # Funnel cluster lain berstatus reject/drop: tidak akan dibangun -> diabaikan.
                    n_rej += len(pts)
                    ignored["HP di funnel lain berstatus reject"] = ignored.get("HP di funnel lain berstatus reject", 0) + len(pts)
                    rep.append("    %-26s %3d HP : %s [%s] (diabaikan)" % ("abaikan: funnel reject", len(pts), nm, status))
                    continue
                elif g.startswith("RFS EXT"):
                    if _base(nm) == mine_base:
                        continue
                    kind, n_ext = "HP_DI_RFS_EXTENSION", n_ext + len(pts)
                    ket = "rumah sudah tercatat di %s" % nm
                else:
                    kind, n_act = "HP_DI_FUNNEL_LAIN", n_act + len(pts)
                    ket = "masuk funnel cluster lain %s (status %s)" % (nm, status)
                rep.append("    %-26s %3d HP : %s" % (kind, len(pts), ket))
                for x, y, hid in pts:
                    qc.append((QgsPointXY(x, y), kind, "%s %s" % (hid, ket)))
            rep.append("  HP di cluster terbangun (RFS DONE)      : %d" % n_done)
            rep.append("  HP di rumah RFS EXTENSION cluster lain  : %d" % n_ext)
            rep.append("  HP di funnel cluster lain yang aktif    : %d" % n_act)
            rep.append("  HP di funnel lain berstatus reject      : %d (diabaikan)" % n_rej)
            std[2] = (n_done + n_ext + n_act == 0,
                      "RFS DONE %d, RFS EXT lain %d, funnel aktif lain %d (reject diabaikan %d)" % (n_done, n_ext, n_act, n_rej))
            if not near:
                std[2] = (None, "tidak bisa dicek: file Funnel tidak mencakup lokasi cluster (0 poligon dalam 1 km)")
            if own_bnd:
                ov = set()
                for gpoly in own_bnd:
                    gb = _bbox(gpoly[0])
                    for f in near:
                        if f["grp"].upper().startswith("RFS EXT") or (mine and f["name"] == mine[1]) \
                                or (not f["grp"].upper().startswith("RFS DONE") and INACTIVE_RX.search(f["status"] or "")):
                            continue
                        bb = f["bb"]
                        if bb[2] < gb[0] or bb[0] > gb[2] or bb[3] < gb[1] or bb[1] > gb[3]:
                            continue
                        if polys_overlap(gpoly, f["poly"]):
                            ov.add((f["grp"], f["name"], f["status"]))
                for grp, nm, status in sorted(ov):
                    note = " (wajar: cluster induk dari extension)" if _base(nm) == mine_base else ""
                    rep.append("  BOUNDARY beririsan dengan    : %s %s [%s]%s" % (grp, nm, status or "-", note))
        else:
            if not funnel_dir:
                why = "folder referensi kosong (isian 2)"
            else:
                why = "tidak ada file *FUNNEL*.kmz/.kml di %s" % funnel_dir
            rep.append("  Funnel/boundary layanan      : %s -> cek Funnel DILEWATI" % why)
            std[2] = (None, "Funnel tidak dicek: " + why)
            if own_bnd:
                std[5] = (False if out_own else None,
                          "%d HP di luar BOUNDARY KMZ; Funnel tidak dicek (%s)" % (len(out_own), why))
            else:
                std[5] = (None, "Funnel tidak dicek: " + why)
            getattr(feedback, "pushWarning", feedback.pushInfo)("FUNNEL TIDAK DICEK: %s" % why)

        # poligon funnel di sekitar untuk ditampilkan di peta
        # GeoPackage: menerima poligon apa pun (KMZ/LIBKML menolak sebagian poligon Funnel yang rumit)
        fun_path = outp("FUNNEL_SEKITAR.gpkg")
        show = [f for f in near if not f["grp"].upper().startswith("RFS EXT")]
        if show:
            show, fun_path = self._write_funnel(show, fun_path, context, feedback, rep)

        # ===== 5. Analisis colo: FDT existing di Design Lite =====
        colo_path, colo_layers, colo_rows = outp("COLO.gpkg"), [], []
        rec, own_dl = None, []
        rep.append("")
        rep.append("COLO (FDT EXISTING DARI DESIGN LITE)")
        dl_files = []
        if funnel_dir and os.path.isdir(funnel_dir):
            dl_c = ref_files(funnel_dir, "designlite")
            for pth, tgl, nver in latest_per_kind(dl_c):
                dl_files.append(pth)
                umur = (_dt.date.today() - tgl).days
                rep.append("  File Design Lite dipakai     : %s (tanggal %s, %d hari lalu%s)" % (
                    os.path.basename(pth), tgl.strftime("%d-%m-%Y"), umur,
                    ", %d versi lama diabaikan" % (nver - 1) if nver > 1 else ""))
                if umur > 2:
                    w = "PERINGATAN: Design Lite %s sudah %d hari; minta versi terbaru." % (os.path.basename(pth), umur)
                    feedback.reportError(w, fatalError=False)
                    rep.append("  " + w)
        if not dl_files:
            rep.append("  Design Lite                  : tidak ada di folder Funnel (analisis colo dilewati)")
        else:
            feedback.setProgressText("5/5 Analisis colo Design Lite")
            import math
            xs = [h[0] for h in hp_xy]
            ys = [h[1] for h in hp_xy]
            mdeg = colo_max / M_PER_DEG * 1.3 + 0.002
            dext = (min(xs) - mdeg, min(ys) - mdeg, max(xs) + mdeg, max(ys) + mdeg)
            allent = []
            for fp in dl_files:
                allent.extend(cached_read("designlite", fp, dext, read_design_lite, feedback))
            ent = [e for e in allent if e.get("kind", "fdt") == "fdt"]
            dl_points = [e for e in allent if e.get("kind") in ("hp", "pole")]

            def dxy(x1, y1, x2, y2):
                return da.measureLine(QgsPointXY(x1, y1), QgsPointXY(x2, y2))
            fdts = group_fdt(ent, dxy)
            # Handbook: tidak boleh colo ke cluster berstatus DROP -> cek status Funnel tiap desain
            fstat = {}
            for fp in funnel_files:
                for f in cached_read("funnel", fp, dext, read_funnel, feedback):
                    if not f["grp"].upper().startswith("RFS"):
                        fstat.setdefault(_base(f["name"]), f["status"] or "")
            for g in fdts:
                for e in g["designs"]:
                    e["fstatus"] = fstat.get(_base(design_cluster_name(e["design"])), "")
                    e["drop"] = bool(INACTIVE_RX.search(e["fstatus"]))
                g["used"] = sum(e["spl"] or 0 for e in g["designs"] if not e["drop"])
                parent = [e for e in g["designs"] if not e["colo"]]
                g["induk_drop"] = bool(parent) and all(e["drop"] for e in parent)
            cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
            n_hp = len(hp_xy)
            need = int(math.ceil(n_hp / hp_per_spl))
            prof = opt["prof"]
            n_fdt = int(math.ceil(n_hp / float(prof["fdt_cap"])))
            m_id = re.search(r"(?<!\d)(\d{9,12})(?!\d)", os.path.basename(hpdb))
            cl_id = m_id.group(1) if m_id else ""
            induk = _base(mine[1]) if mine else ""

            res_path = os.path.join(funnel_dir, "COLO_RENCANA.csv")
            try:
                res_rows = read_reservations(res_path)
            except Exception as e:
                res_rows = []
                feedback.reportError("COLO_RENCANA.csv tidak bisa dibaca: %s" % e, fatalError=False)
            reserved = {}
            for r in res_rows:
                if r[1] not in (cname, kode):
                    reserved.setdefault(r[2], []).append((r[1], _int(r[3]) or 0, r[0], r[5], _int(r[4]) or 0))

            # jaringan jalur cluster (dari ROADS) untuk jarak sepanjang kabel
            import heapq
            adj = {}
            for ka, kb, L in edges:
                adj.setdefault(ka, []).append((kb, L))
                adj.setdefault(kb, []).append((ka, L))
            hp_pole = [nearest_idx(p) for _r, p in data]          # (indeks tiang, jarak HP->tiang)

            def net_far(start):
                dist = {start: 0.0}
                pq = [(0.0, start)]
                while pq:
                    d0, u = heapq.heappop(pq)
                    if d0 > dist.get(u, 1e18):
                        continue
                    for v, L in adj.get(u, []):
                        nd = d0 + L
                        if nd < dist.get(v, 1e18):
                            dist[v] = nd
                            heapq.heappush(pq, (nd, v))
                far, miss = 0.0, 0
                for qi, dq in hp_pole:
                    dd = dist.get(("P", qi))
                    if dd is None:
                        miss += 1
                        continue
                    far = max(far, dd + dq)
                return far, miss
            basis = opt.get("colo_basis", 0)
            fdt_cap = prof["fdt_cap"]
            rows = []
            for g in fdts:
                qi_e, d_entry = nearest_idx(QgsPointXY(g["x"], g["y"]))
                pe = poles[qi_e]
                far, miss = net_far(("P", qi_e))
                g["d_entry"], g["d_cable"], g["net_miss"] = d_entry, d_entry + far, miss
                g["d_hp"] = g["d_entry"] if basis == 0 else g["d_cable"]
                g["p_hp"] = (pe.x(), pe.y(), names[qi_e] or "tiang")
                g["d_c"] = dxy(g["x"], g["y"], cx, cy)
                g["hp_used"] = sum((e["prem"] or 0) for e in g["designs"] if not e.get("drop"))
                g["hp_unknown"] = any(e["prem"] is None for e in g["designs"] if not e.get("drop"))
                # pesanan gugur jika desain cluster pemesan sudah masuk Design Lite (sudah terhitung di "pakai")
                res = [r for r in reserved.get(g["code"], [])
                       if not (r[3] and any(r[3] in e["design"] for e in g["designs"]))]
                g["res"] = sum(r[1] for r in res)
                g["hp_res"] = sum(r[4] for r in res)
                g["hp_total"] = g["hp_used"] + g["hp_res"] + n_hp
                g["res_by"] = ", ".join("%s (%d)" % (r[0], r[1]) for r in res)
                dn = [re.sub(r"[^A-Z0-9]", "", e["design"].upper()) for e in g["designs"]]
                g["own"] = bool(cl_id) and any(cl_id in e["design"] for e in g["designs"])
                if g["own"]:
                    # desain cluster ini sendiri sudah ada di Design Lite: jangan dihitung dua kali
                    ownd = [e for e in g["designs"] if cl_id in e["design"] and not e.get("drop")]
                    g["own_spl"] = sum(e["spl"] or 0 for e in ownd)
                    g["used"] = max(0, g["used"] - g["own_spl"])
                    g["hp_used"] = max(0, g["hp_used"] - sum(e["prem"] or 0 for e in ownd))
                    g["hp_total"] = g["hp_used"] + g["hp_res"] + n_hp
                g["spare"] = max(0, max_spl - g["used"] - g["res"])
                g["induk"] = bool(induk) and len(induk) >= 6 and any(induk in k for k in dn)
                if g["d_hp"] > colo_max:
                    g["status"] = "DI LUAR %d M" % colo_max
                elif g["induk_drop"]:
                    g["status"] = "INDUK DROP/REJECT di Funnel (cek sheet Macro)"
                elif g["used"] > max_spl:
                    g["status"] = "CEK DATA (tercatat %d > %d splitter)" % (g["used"], max_spl)
                elif g["hp_total"] > fdt_cap:
                    g["status"] = "KAPASITAS HP PENUH (%d+%d+%d=%d > %d HP)" % (
                        g["hp_used"], g["hp_res"], n_hp, g["hp_total"], fdt_cap)
                elif g["spare"] >= need:
                    g["status"] = "BISA COLO"
                elif g["spare"] > 0:
                    g["status"] = "KURANG (sisa %d, butuh %d)" % (g["spare"], need)
                else:
                    g["status"] = "PENUH"
                if g["own"] and g["d_hp"] <= colo_max:
                    g["status"] = ("SUDAH DICOLO CLUSTER INI (kapasitas cukup)" if g["status"] == "BISA COLO" else
                                   "SUDAH DICOLO CLUSTER INI tetapi %s (tanpa desain ini %d splitter terpakai + %d = %d > %d)"
                                   % (g["status"], g["used"], need, g["used"] + need, max_spl)
                                   if g["used"] + g["res"] + need > max_spl else
                                   "SUDAH DICOLO CLUSTER INI tetapi " + g["status"])
                if g.get("spread_m", 0) > 30:
                    g["status"] += "; ikon FDT tercatat di %d lokasi berbeda (sebaran %.0f m, Handbook kasus 14)" % (
                        len({(round(e["x"], 5), round(e["y"], 5)) for e in g["items"]}), g["spread_m"])
                rows.append(g)

            ok = [g for g in rows if g["status"].startswith("BISA COLO") or g["status"].startswith(
                "SUDAH DICOLO CLUSTER INI (kapasitas cukup)")]
            ok.sort(key=lambda g: (not g["own"], not g["induk"], g["d_hp"]))
            rows.sort(key=lambda g: (g not in ok, g["d_hp"]))
            rec = ok[0] if ok else None
            colo_rows = sorted(rows, key=lambda g: g["d_hp"])

            rep.append("  HP cluster ini               : %d -> butuh %d splitter 1x4 (%d HP/splitter)%s"
                       % (n_hp, need, hp_per_spl, ", ID cluster %s" % cl_id if cl_id else ""))
            rep.append("  FDT existing <= %.0f m        : %d (dari %d FDT di sekitar)"
                       % (colo_max, sum(1 for g in rows if g["d_hp"] <= colo_max), len(rows)))
            basis_txt = ("garis lurus FDT ke tiang cluster terdekat" if basis == 0 else
                         "estimasi kabel FDT ke HP terjauh: garis lurus ke titik masuk + sepanjang jalur cluster")
            rep.append("  Dasar jarak colo             : %s, batas %.0f m" % (basis_txt, colo_max))
            if rec:
                rep.append("  >> REKOMENDASI COLO          : %s, %.0f m ke titik masuk (%s), estimasi kabel ke HP terjauh %.0f m"
                           % (rec["code"], rec["d_entry"], rec["p_hp"][2], rec["d_cable"]))
                rep.append("     Splitter                  : terpakai %d + dipesan %d + cluster ini %d = %d dari %d"
                           % (rec["used"], rec["res"], need, rec["used"] + rec["res"] + need, max_spl))
                rep.append("     Total homepass di FDT     : existing %d%s + dipesan %d + cluster ini %d = %d dari %d HP%s"
                           % (rec["hp_used"], "?" if rec["hp_unknown"] else "", rec["hp_res"], n_hp, rec["hp_total"],
                              fdt_cap, ", FDT INDUK cluster ini" if rec["induk"] else ""))
            else:
                rep.append("  >> TIDAK ADA FDT existing <= %.0f m dengan sisa >= %d splitter -> rencanakan FDT baru"
                           % (colo_max, need))
            own_bad = [g for g in rows if g["own"] and g not in ok]
            for o in own_bad:
                rep.append("  !! Cluster ini sudah tercatat di Design Lite memakai %s: %s" % (o["code"], o["status"]))
            if n_fdt > 1:
                rep.append("  ! HP %d > kapasitas 1 FDT (%d HP, profil %s): butuh minimal %d FDT; penuhi satu FDT dulu (Handbook)"
                           % (n_hp, prof["fdt_cap"], prof["key"], n_fdt))
            rep.append("  Catatan: titik masuk = tiang cluster terdekat dari FDT. Panjang kabel final tetap dicek di desain otomatis.")
            # jalur feeder/existing terdekat (Handbook: FDT harus menjemput feeder)
            fd_files = ref_files(funnel_dir, "feeder")
            best_f = None
            for fp, _tg, _nv in latest_per_kind(fd_files):
                fext = (cx - 0.03, cy - 0.03, cx + 0.03, cy + 0.03)
                for ln in cached_read("feeder", fp, fext, read_feeder, feedback):
                    for i in range(len(ln["coords"]) - 1):
                        d = seg_dist_m(cx, cy, ln["coords"][i], ln["coords"][i + 1])
                        if best_f is None or d < best_f[0]:
                            best_f = (d, ln["folder"], os.path.basename(fp))
            if fd_files:
                rep.append("  Feeder/jalur existing terdekat: %s" % (
                    "%.0f m dari pusat cluster (%s, %s)" % best_f if best_f else "tidak ada dalam radius 3 km"))
            # double tagging terhadap Design Lite (HP & tiang yang sudah dipakai cluster lain)
            dup_hp = dup_pole = 0
            dl_hp_rev = float(qcp("dl_dup_hp_review_m", 5.0))
            dl_pole_rev = float(qcp("dl_dup_pole_review_m", 10.0))
            for e in dl_points:
                ex_ = QgsPointXY(e["x"], e["y"])
                if e["kind"] == "hp":
                    for r_, p_ in data:
                        if abs(p_.x() - e["x"]) < 6e-5 and abs(p_.y() - e["y"]) < 6e-5:
                            dd = da.measureLine(p_, ex_)
                            if dd <= 2.0:
                                dup_hp += 1
                                qc.append((p_, "HP_SUDAH_ADA_DI_DESIGN_LITE", "%s sudah tercatat di Design Lite (double tagging, %.1f m)"
                                           % (r_[iid] if iid is not None else "HP", dd), None, round(dd, 1), 2.0))
                                break
                            if dd <= dl_hp_rev:
                                qc.append((p_, "INFO_HP_MUNGKIN_DI_DESIGN_LITE", "%s %.1f m dari HP Design Lite: cek apakah rumah yang sama"
                                           % (r_[iid] if iid is not None else "HP", dd), None, round(dd, 1), dl_hp_rev))
                                break
                elif e["kind"] == "pole":
                    for pi, pp in enumerate(poles):
                        if kinds[pi] != "new" or abs(pp.x() - e["x"]) > 1e-4 or abs(pp.y() - e["y"]) > 1e-4:
                            continue
                        dd = da.measureLine(pp, ex_)
                        if dd <= 1.5:
                            dup_pole += 1
                            qc.append((pp, "TIANG_BARU_SUDAH_ADA", "%s sudah ada di Design Lite (%s, %.1f m): jadikan existing"
                                       % (names[pi], e.get("folder", ""), dd), None, round(dd, 1), 1.5))
                            break
                        if dd <= dl_pole_rev:
                            qc.append((pp, "INFO_TIANG_BARU_DEKAT_EXISTING", "%s %.1f m dari tiang Design Lite (%s): cek apakah tiang yang sama"
                                       % (names[pi], dd, e.get("folder", "")), None, round(dd, 1), dl_pole_rev))
                            break
            if dl_points or dup_hp or dup_pole:
                rep.append("  Double tagging vs Design Lite: HP %d, tiang baru yg sudah ada %d" % (dup_hp, dup_pole))
            std_dt = (dup_hp, dup_pole)
            rep.append("")
            rep.append("  %-17s %7s %8s %6s %5s %5s %14s  %s" % (
                "FDT", "masuk", "kabel est", "pakai", "pesan", "sisa", "HP total/kap", "status"))
            for g in rows[:12]:
                rep.append("  %-17s %6.0fm %8.0fm %3d/%-2d %5d %5d %9d/%-4d  %s%s%s" % (
                    g["code"][:17], g["d_entry"], g["d_cable"], g["used"], max_spl, g["res"], g["spare"],
                    g["hp_total"], fdt_cap, g["status"],
                    " [INDUK]" if g["induk"] else "", " [KODE DOBEL DI LOKASI LAIN]" if g["dup_loc"] else ""))
                for e in g["designs"]:
                    rep.append("      - %2s splitter, %4s HP : %s%s%s" % (
                        e["spl"] if e["spl"] is not None else "?", e["prem"] if e["prem"] is not None else "?",
                        e["design"][:70], " (COLO)" if e["colo"] else "",
                        " [Funnel %s: tidak dihitung, cek sheet Macro]" % e["fstatus"] if e.get("drop") else ""))
                if g["res_by"]:
                    rep.append("      - dipesan rencana        : %s" % g["res_by"])

            # konflik: rekomendasi kita juga dipesan cluster lain
            for g in rows:
                if g["res"] and g["d_hp"] <= colo_max and g["used"] + g["res"] + need > max_spl >= g["used"] + need:
                    qc.append((QgsPointXY(g["x"], g["y"]), "COLO_KONFLIK",
                               "%s cukup untuk cluster ini, tapi sudah dipesan %s" % (g["code"], g["res_by"])))
                    rep.append("  ! KONFLIK: %s cukup jika tidak dipesan %s" % (g["code"], g["res_by"]))

            own_dl = [g for g in rows if g["own"]]
            if colo_log and (rec or any(r[1] in (cname, kode) for r in res_rows)):
                try:
                    keep = [r for r in res_rows if r[1] not in (cname, kode)]
                    if rec:
                        keep.append([_dt.date.today().strftime("%d-%m-%Y"), kode, rec["code"],
                                     str(need), str(n_hp), cl_id])
                    write_reservations(res_path, keep)
                    rep.append("  Rencana dicatat di           : %s" % res_path)
                except Exception as e:
                    feedback.reportError("COLO_RENCANA.csv tidak bisa ditulis: %s" % e, fatalError=False)

            # layer peta: FDT sekitar + garis colo
            try:
                fl = QgsVectorLayer(
                    "Point?crs=EPSG:4326&field=fdt:string(40)&field=status:string(60)&field=jarak_m:double(10,1)"
                    "&field=pakai:integer&field=pesan:integer&field=sisa:integer&field=label:string(80)"
                    "&field=desain:string(254)&field=masuk_m:double(10,1)&field=kabel_m:double(10,1)"
                    "&field=hp_total:integer&field=hp_kap:integer", "FDT_SEKITAR", "memory")
                ff = []
                for g in rows:
                    ft = QgsFeature(fl.fields())
                    ft.setAttributes([g["code"], g["status"][:60], round(g["d_hp"], 1), g["used"], g["res"], g["spare"],
                                      "%s | sisa %d/%d | HP %d/%d | %.0f m" % (g["code"], g["spare"], max_spl,
                                                                         g["hp_total"], fdt_cap, g["d_hp"]),
                                      " ; ".join(e["design"] for e in g["designs"])[:254],
                                      round(g["d_entry"], 1), round(g["d_cable"], 1), g["hp_total"], fdt_cap])
                    ft.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(g["x"], g["y"])))
                    ff.append(ft)
                fl.dataProvider().addFeatures(ff)
                gl = QgsVectorLayer("LineString?crs=EPSG:4326&field=fdt:string(40)&field=jarak_m:double(10,1)",
                                    "GARIS_COLO", "memory")
                if rec:
                    ft = QgsFeature(gl.fields())
                    ft.setAttributes([rec["code"], round(rec["d_hp"], 1)])
                    ft.setGeometry(QgsGeometry.fromPolylineXY(
                        [QgsPointXY(rec["x"], rec["y"]), QgsPointXY(rec["p_hp"][0], rec["p_hp"][1])]))
                    gl.dataProvider().addFeatures([ft])
                if os.path.exists(colo_path):
                    os.remove(colo_path)
                for i, lyr in enumerate((fl, gl)):
                    opts = QgsVectorFileWriter.SaveVectorOptions()
                    opts.driverName = "GPKG"
                    opts.layerName = lyr.name()
                    opts.fileEncoding = "UTF-8"
                    if i:
                        opts.actionOnExistingFile = OVERWRITE_LAYER
                    err = QgsVectorFileWriter.writeAsVectorFormatV3(lyr, colo_path, context.transformContext(), opts)
                    if err[0] != WRITER_OK:
                        raise QgsProcessingException(err[1])
                    colo_layers.append(("%s|layername=%s" % (colo_path, lyr.name()), lyr.name()))
            except Exception as e:
                feedback.reportError("Layer COLO tidak bisa ditulis (laporan colo tetap ada): %s" % str(e)[:300],
                                     fatalError=False)
                colo_layers = []

        # ===== Standar no. 6 (status desain) dan no. 7 (colo) =====
        sd = []
        if own_dl:
            sd.append("sudah tercatat di Design Lite (%s)" % ", ".join(g["code"] for g in own_dl))
        if mine:
            sd.append("%s '%s' status %s" % (mine[0], mine[1], mine_status or "-"))
        if olt_reg:
            sd.append("terdaftar %s" % olt_reg[1])
        std[6] = (False if own_dl else (None if not sd else True),
                  "; ".join(sd) if sd else "data Funnel/Design Lite/attributes tidak tersedia")
        if rec:
            std[7] = (True, "%s: %.0f m ke tiang cluster terdekat (kabel ke HP terjauh +-%.0f m); sisa %d splitter; "
                      "HP di FDT %d+%d+%d=%d dari %d" % (rec["code"], rec["d_entry"], rec["d_cable"], rec["spare"],
                                                       rec["hp_used"], rec["hp_res"], n_hp, rec["hp_total"], opt["prof"]["fdt_cap"]))
            if findim_ids and not any(rec["code"].startswith(fi) for fi in findim_ids):
                rep.append("  info: FDT colo %s berada di kelurahan lain (FINDIM cluster: %s)"
                           % (rec["code"], ", ".join(sorted(findim_ids))))
        elif dl_files:
            std[7] = (False, "tidak ada SATU FDT existing <= %.0f m (%s) dengan sisa splitter & kapasitas HP cukup -> FDT baru, "
                             "atau bagi ke beberapa FDT (menu 2. Alokasi FDT & FAT)%s"
                      % (colo_max, "ke tiang cluster terdekat" if opt.get("colo_basis", 0) == 0 else "estimasi kabel",
                         ("; terdekat: " + "; ".join("%s %.0f m (%s)" % (g["code"], g["d_hp"], g["status"])
                                                    for g in colo_rows[:3])) if colo_rows else
                         "; tidak ada FDT existing di sekitar"))
        else:
            std[7] = (None, "Design Lite tidak ada")
        if locals().get("own_bad"):
            std[7] = (False, "desain cluster ini sudah tercatat colo ke %s di Design Lite, tetapi %s%s" % (
                own_bad[0]["code"], own_bad[0]["status"].replace("SUDAH DICOLO CLUSTER INI tetapi ", ""),
                ("; alternatif: " + std[7][1]) if std[7][0] else ""))
        if len(data) > opt["prof"]["fdt_cap"]:
            import math as _m
            n_hp_all = len(data)
            std[7] = (False if std[7][0] is not None else None,
                      "CLUSTER %d HP > kapasitas 1 FDT (%d HP): perlu minimal %d FDT / pecah cluster. %s" % (
                          n_hp_all, opt["prof"]["fdt_cap"], _m.ceil(n_hp_all / float(opt["prof"]["fdt_cap"])), std[7][1]))
        if "std_dt" in locals() and (std_dt[0] or std_dt[1]):
            ok2, t2 = std.get(2, (None, ""))
            std[2] = (False, (t2 + "; " if t2 else "") + "double tagging Design Lite: HP %d, tiang %d" % std_dt)
        # ===== 8. BAKP (izin warga) =====
        bk_mode = opt.get("bakp", 0)
        bres = None
        if bk_mode == 0:
            try:
                def _maj(*names):
                    i_ = self._pick(headers, list(names), "\x00")
                    cnt_ = {}
                    for r_, _p in data:
                        v_ = r_[i_].strip() if i_ is not None and i_ < len(r_) else ""
                        if v_ and v_ != "-":
                            cnt_[v_] = cnt_.get(v_, 0) + 1
                    return max(cnt_, key=cnt_.get) if cnt_ else ""
                vm = re.search(r"_\d+\s*HP[_\s]+([A-Za-z][A-Za-z.\s]*)", os.path.basename(hpdb)) or \
                    re.search(r"PT[.\s_]+([A-Za-z]+)", os.path.basename(outdir.rstrip("\\/")))
                exp_bk = {"cluster_id": cl_id, "hp_hpdb": len(data), "hp_kmz": n_kmz if kmz_hp else None,
                          "cluster_name": cluster_label(outdir, hpdb),
                          "kota": _maj("CITY", "KOTA"), "kecamatan": _maj("DISTRICT", "KECAMATAN"),
                          "kelurahan": _maj("SUBDISTRICT", "KELURAHAN"),
                          "vendor": vm.group(1).strip(" ._") if vm else ""}
                if att and att.get("findim") and exp_bk["kelurahan"]:
                    _st, _best, _d, _s = check_admin(att, exp_bk["kelurahan"], exp_bk["kecamatan"], exp_bk["kota"], "")
                    if _best and _st != "OK":
                        exp_bk["findim"] = (_best["kel"], _best["kec"], _best["city"])
                bres = _bakp.check_cluster(outdir, exp_bk, feedback, manual=opt.get("bakp_file") or None)
                rep.extend(bres["lines"])
                std[8] = (bres["ok"], bres["summary"])
                warn = getattr(feedback, "pushWarning", feedback.pushInfo)
                warn("PENGINGAT: jangan lupa cek BAKP (%s) - daftar periksa ada di laporan HTML."
                     % (os.path.basename(bres["file"]) if bres["file"] else "file BAKP belum ada!"))
                anchor = data[0][1] if data else None
                if anchor is not None:
                    for k_, o_, t_ in bres["items"]:
                        if o_ is False:
                            qc.append((anchor, k_, t_))
                        elif o_ is None:
                            qc.append((anchor, k_ if k_.startswith(("INFO_", "UNV_")) else "INFO_" + k_, t_))
            except Exception as e:
                feedback.reportError("Cek BAKP dilewati: %s" % e, fatalError=False)
                rep.append("")
                rep.append("BAKP: cek otomatis dilewati (%s) - tetap cek BAKP secara manual!" % e)
                std[8] = (None, "cek manual BAKP (otomatis gagal: %s)" % str(e)[:60])
        else:
            std[8] = (None, "dilewati (pilihan pengguna) - tetap pastikan BAKP sudah dicek")
        lmax = max([x[0] for x in long_list] or [0])
        n_np_spans = len({(frozenset((ka, kb)), int(round(L / 2.0))) for ka, kb, L, pts in spans
                          if ka[0] == "P" and kb[0] == "P"
                          and not (kinds[ka[1]] == "existing" and kinds[kb[1]] == "existing")})   # tanpa rentang ganda
        std[9] = (long_n == 0, ("semua %d rentang dengan NP <= %.0f m sepanjang jalur (%d rentang %.0f-%.0f m: WARNING regulasi "
                                "daerah 50 m; EP-EP tidak dinilai)" % (n_np_spans, span_max, n_reg, SPAN_REG, span_max))
                  if not long_n else
                  "%d rentang > %.0f m (terpanjang %.1f m: %s [%s]); sisipkan tiang di tengah%s. EP-EP tidak dinilai" % (
                      long_n, span_max, lmax, max(long_list)[1], max(long_list)[2],
                      (" (kelebihan %.1f m < akurasi GPS +-%.0f m: verifikasi ukur lapangan)" % (lmax - span_max, hp_tol))
                      if lmax - span_max < hp_tol else ""))
        judul = {1: "Jarak HP ke tiang (<= %.0f m)" % hp_max, 2: "Boundary RFS / funnel lain",
                 3: "Wilayah HPDB vs FINDIM", 4: "HPDB vs KMZ + HP duplikat",
                 5: "HP di luar boundary Funnel", 6: "Status desain cluster", 7: "Bisa colo FDT",
                 8: "BAKP (izin warga)", 9: "Jarak tiang ke tiang NP (<= %.0f m)" % span_max}
        summ = ["RINGKASAN STANDAR REVIEW STRAND"]
        for k in range(1, 10):
            ok, txt = std.get(k, (None, "-"))
            summ.append("  %d. %-30s [%s] %s" % (k, judul[k], {True: "OK", False: "CEK", None: "--"}[ok], txt))
        summ.append("  Kabel rendah tengah bentang (info): %d < %.1f m; %d antara %.1f-%.1f m (tinjau bila melintang jalan)"
                    % (clear_n, clear_fail, clear_rev, clear_fail, clear_road))
        summ.append("  Efisiensi (info): NP bisa dihapus %d, ujung jalur tanpa HP %d | Profil %s (%s)" % (
            len(removable), loops, opt["prof"]["key"], opt["prof"]["src"]))
        if ignored:
            summ.append("  Diabaikan sesuai aturan: " + "; ".join("%s: %d" % kv for kv in sorted(ignored.items())))
        summ.append("")

        head = ["LAPORAN INPUT DESAIN OTOMATIS APD",
                "Alat    : %s v%s (c) %s, integritas %s" % (__product__, __version__, __author__, integrity_status()),
                "Cluster : %s  (kode %s%s)" % (
                    cluster_label(outdir, hpdb), kode, ", ID %s" % cl_id if cl_id else ""),
                "Dibuat  : %s" % _dt.datetime.now().strftime("%d-%m-%Y %H:%M"),
                "HPDB    : %s" % hpdb, "Tiang   : %s" % pole_path, "Jalur   : %s" % road_path,
                "Snap    : %.1f m, perilaku: prefer aligning nodes, don't insert new vertices" % snap_m,
                "Input   : Roads=%s, cutting points=%s, Homepass=%s" % (
                    os.path.basename(roads_path), os.path.basename(pole_out), os.path.basename(hp_path)), ""]
        # ===== Temuan QC: satu Shapefile per kategori (folder QC) + gabungan + KMZ =====
        qc_map, qc_cats = self._write_qc(qc, inp, outp, kode, context, feedback)
        try:
            man = self._write_manifest(outp("manifest_input.json"), kode, cl_id, hpdb, headers, (ilon, ilat, iid), data,
                                       hp_path, hp_csv, roads_path, pole_out, qprof, opt)
            feedback.pushInfo("Manifest input: %s (%s)" % (os.path.basename(man[0]), man[1]))
            rep.append("")
            rep.append("MANIFEST INPUT DESAIN OTOMATIS: %s -> %s" % (os.path.basename(man[0]), man[1]))
            for line_ in man[2]:
                rep.append("  " + line_)
        except Exception as e:
            feedback.reportError("manifest_input.json tidak ditulis: %s" % e, fatalError=False)
        qc_path = outp("QC_TEMUAN.kmz")
        refs = ref_summary(funnel_dir) if funnel_dir else []
        head.append("DATA REFERENSI : %s" % (funnel_dir or "TIDAK ADA (isian 2 kosong, tidak ditemukan otomatis)"))
        for lab, fl in refs:
            head.append("  [%s] %-14s %s" % ("v" if fl else "x", lab, ", ".join(fl) if fl else "tidak ada"))
        if not funnel_dir or not refs or not refs[0][1]:
            head.append("  -> Tanpa file *FUNNEL* standar 2 & 5 tidak dicek. Salin folder referensi tim dan pilih di isian 2.")
        head.append("")
        lap = outp("LAPORAN_INPUT.txt")
        with open(lap, "w", encoding="utf-8") as fh:
            fh.write("\n".join(head + summ + rep) + "\n")
        for line in head + summ + rep:
            feedback.pushInfo(line)
        feedback.pushInfo("")
        feedback.pushInfo("Laporan disimpan di: %s" % lap)
        lap_html = outp("RINGKASAN_QC.html")
        fid_map, snaps_uri, word_name, map_html = {}, {}, None, ""
        try:
            fid_map = qc_fid_map(qc)
            feedback.setProgressText("Gambar peta temuan dan laporan Word")
            # atribut HP dari HPDB (kolom terisi saja) untuk panel detail peta interaktif
            hp_attrs = []
            pri_ = ("ID", "HOMEPASS_ID", "HOMEPASS_ADDRESS_PREFIX", "HOMEPASS_ADDRESS", "HOMEPASS_HOUSE_NUMBER", "HOMEPASS_ADDRESS_BLOCK",
                    "NEIGHBORHOOD_NO_RT", "HAMLET_NO_RW", "CLUSTER_NAME", "SUBDISTRICT", "DISTRICT", "CITY", "BUILDING_TYPE",
                    "HOMEPASS_STATUS", "HOMEPASS_RFSDATE", "HOMEPASS_LATITUDE", "HOMEPASS_LONGITUDE")
            ordr_ = sorted(range(len(headers)), key=lambda k_: (pri_.index(str(headers[k_]).upper())
                                                                 if str(headers[k_]).upper() in pri_ else 99, k_))
            for r_, _p in data:
                a_ = {}
                for k_ in ordr_:
                    v_ = r_[k_] if k_ < len(r_) else ""
                    if str(v_).strip() in ("", "-", "None"):
                        continue
                    if "DATE" in str(headers[k_]).upper() and re.match(r"^\d{5}(\.0+)?$", str(v_).strip()):
                        try:      # tanggal serial Excel -> dd-mm-yyyy
                            v_ = (_dt.date(1899, 12, 30) + _dt.timedelta(days=int(float(v_)))).strftime("%d-%m-%Y")
                        except (ValueError, OverflowError):
                            pass
                    a_[headers[k_]] = v_
                hp_attrs.append(a_)
            word_name, snaps_uri, map_data = self._qc_word(
                qc, outp, inp, kode, cluster_label(outdir, hpdb), std, judul, poles, names, kinds,
                locals().get("hp_xy") or [], segs, own_bnd, [f["poly"] for f in (locals().get("own_f") or [])], feedback,
                hp_attrs=hp_attrs, heights=heights)
            from . import mapview as _mv
            map_html = _mv.block(map_data, "Peta temuan QC survei")
        except Exception as e:
            feedback.reportError("Gambar temuan / laporan Word / peta tidak dibuat: %s" % e, fatalError=False)
        try:
            _report_html.build(
                lap_html,
                {"product": __product__, "version": __version__, "author": __author__,
                 "cluster": cluster_label(outdir, hpdb), "kode": kode, "cl_id": cl_id,
                 "date": _dt.datetime.now().strftime("%d-%m-%Y %H:%M"),
                 "profile": "%s (%s)" % (opt["prof"]["name"], opt["prof"]["src"]),
                 "ref_dir": funnel_dir, "refs": refs, "qc_counts": qc_counts(qc), "qc_by_std": qc_by_std(qc),
                 "qc_profile_id": qprof.get("profile_id"), "rule_version": qprof.get("rule_version"),
                 "fid_map": fid_map, "snaps": snaps_uri, "word": word_name, "map_html": map_html,
                 "qc_params": [(k, e.get("v"), e.get("unit"), _qc.DASAR_LABEL.get(e.get("dasar"), e.get("dasar")),
                                e.get("sumber"), e.get("status")) for k, e in qprof["params"].items()
                               if k in ("span_max_m", "span_reg_m", "hp_pole_max_m", "clear_road_m", "sag_pct", "dup_near_m",
                                        "edge_tol_m", "bend_info_deg", "bend_warn_deg", "pole_on_line_m", "colo_radius_m",
                                        "fat_max_hp", "fdt_max_premises", "fdt_max_spl")]},
                std, judul, summ[1 + len(judul):], bres,
                [("Roads", os.path.basename(roads_path)), ("Cutting points (tiang)", os.path.basename(pole_out)),
                 ("Homepass", os.path.basename(hp_path)), ("Homepass CSV (Comma Delimited)", os.path.basename(outp("HP.csv"))),
                 ("Manifest impor (cek siap impor + SHA-256)", os.path.basename(outp("manifest_input.json"))),
                 ("Laporan teks", os.path.basename(lap))]
                + ([("Temuan QC (QGIS)", os.path.basename(qc_map))] if qc_map else []),
                "\n".join(head + summ + rep))
            feedback.pushInfo("Ringkasan HTML: %s" % lap_html)
        except Exception as e:
            feedback.reportError("Ringkasan HTML tidak dibuat: %s" % e, fatalError=False)
            lap_html = lap

        if workdir:
            import shutil
            dst = os.path.join(workdir, os.path.basename(inp))   # tiap cluster subfolder sendiri
            os.makedirs(dst, exist_ok=True)
            for fn in os.listdir(inp):
                if os.path.isfile(os.path.join(inp, fn)):
                    shutil.copy2(os.path.join(inp, fn), os.path.join(dst, fn))
            feedback.pushInfo("Disalin juga ke: %s" % dst)

        grp = kode if opt["naming"] == 0 else os.path.basename(outdir.rstrip("\\/"))
        loads = [(hp_path, "HP"), (roads_path, "ROADS"), (pole_map or pole_out, "POLE")]
        if show:
            loads.insert(0, (fun_path, "FUNNEL_SEKITAR"))
        for cpath_, cname_, cn_ in qc_cats:          # satu layer per kategori temuan (sub-grup "QC TEMUAN")
            loads.append((cpath_, "QC " + cname_))
        if not qc_cats and qc_map:
            loads.append((qc_map, "QC_TEMUAN"))
        loads.extend(colo_layers)
        # Muat layer lewat mekanisme resmi Processing (aman, dijalankan QGIS di thread utama).
        for k, (pth, nm) in enumerate(loads):
            try:
                det = QgsProcessingContext.LayerDetails("%s %s" % (grp, nm), context.project(), nm)
                try:
                    det.groupName = grp            # QGIS 3.32+: satu grup per cluster
                    det.layerSortKey = k
                except Exception as _e:
                    _log.note(_e)
                if nm.startswith("QC") and pth.endswith(".shp"):
                    pp = QcStyler(grp, nm[3:] if nm.startswith("QC ") else nm)
                    _KEEP_ALIVE.append(pp)
                    det.setPostProcessor(pp)
                if nm == "POLE" and pth.endswith(".gpkg"):
                    pp = PoleStyler()
                    _KEEP_ALIVE.append(pp)
                    det.setPostProcessor(pp)
                if nm == "FUNNEL_SEKITAR":
                    pp = FunnelStyler()
                    _KEEP_ALIVE.append(pp)
                    det.setPostProcessor(pp)
                if nm == "FDT_SEKITAR":
                    pp = FdtStyler()
                    _KEEP_ALIVE.append(pp)
                    det.setPostProcessor(pp)
                context.addLayerToLoadOnCompletion(pth, det)
            except Exception as e:
                feedback.reportError("Layer %s tidak dimuat otomatis (file tetap ada): %s" % (nm, e), fatalError=False)
            self._to_load.append((pth, nm, grp))
        feedback.setProgress(100)
        n_cek = sum(1 for it in qc if not it[1].startswith("INFO"))
        b8 = std.get(8, (None, ""))
        return {"inp": inp, "kode": kode, "hp": len(data), "poles": len(poles), "laporan": lap_html,
                "bakp": {True: "OK", False: "CEK", None: "--"}[b8[0]],
                "qc": "%d+%di" % (n_cek, len(qc) - n_cek),
                "colo": rec["code"] if rec else ("FDT baru" if std.get(7, (None,))[0] is False else "-")}

    def postProcessAlgorithm(self, context, feedback):
        # Layer dimuat oleh QGIS dari daftar addLayerToLoadOnCompletion (lihat _run_cluster).
        pth = getattr(self, "_open_path", None)
        if pth and os.path.exists(pth):
            try:
                from qgis.PyQt.QtCore import QUrl
                from qgis.PyQt.QtGui import QDesktopServices
                QDesktopServices.openUrl(QUrl.fromLocalFile(pth))
            except Exception as _e:
                _log.note(_e)
        return {}

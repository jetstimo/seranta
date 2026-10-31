# -*- coding: utf-8 -*-
"""
Seranta - FTTH Design Assistant - tool 3: post-design FDT FAT CODE + closure table + APD QC
=================================================================
Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-2.0-or-later (see LICENSE).

Menggantikan langkah manual setelah desain desain otomatis selesai (Handbook KMZ):
  * FDT FAT CODE  : dulu net_nodes -> QGIS "Add geometry" -> VLOOKUP spreadsheet ke spliceplan (Route optique)
  * Closure Table : dulu tiap sheet closure disalin ke tablesgenerator.com lalu ditempel ke KMZ
  * QC APD        : jumlah HP per FAT, jarak FAT->HP (MAXPPDIST), format & urutan kode, premises FDT,
                    jumlah FAT APD = spliceplan, kapasitas splitter FDT, tube harus penuh dulu, FAT di tiang.
Masukan: folder output desain otomatis (net_nodes.shp, net_SpliceClosure.shp, file splice plan .xlsx).
"""
try:
    from . import _log
except ImportError:  # dijalankan sebagai modul lepas (uji unit)
    import _log
import math
import os
import re
import zipfile

from qgis.core import (QgsProcessingAlgorithm, QgsProcessingException, QgsProcessingParameterBoolean,
                       QgsProcessingParameterEnum, QgsProcessingParameterFile, QgsProcessingParameterString,
                       QgsVectorLayer, QgsSettings)

from .buat_input_desain import (kmz_add_icons, ADVANCED_FLAG, FOLDER_BEHAVIOR, FILE_BEHAVIOR, PROFILES, __author__, __product__, __version__,
                                integrity_status, kml_features, release_old_outputs, read_xlsx, resolve_profile, classify, _int)

# Warna serat TIA-598 (1 biru ... 12 aqua) seperti di spliceplan desain otomatis
FIBER_COLORS = {1: ("#1f4fff", "#fff"), 2: ("#ff9900", "#000"), 3: ("#1aa31a", "#fff"), 4: ("#8b4513", "#fff"),
                5: ("#8c8c8c", "#fff"), 6: ("#ffffff", "#000"), 7: ("#e00000", "#fff"), 8: ("#000000", "#fff"),
                9: ("#ffff00", "#000"), 10: ("#8a2be2", "#fff"), 11: ("#ff2fb4", "#000"), 12: ("#00e5ff", "#000")}
FDT_RX = re.compile(r"^[A-Z]{3}\d-[A-Z0-9]{3}\d{2}-H\d{2}$")
FAT_RX = re.compile(r"^([A-Z]{3}\d-[A-Z0-9]{3}\d{2}-H\d{2})-D(\d{2})-(\d{2})$")


def _n(s):
    return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())


def _num(s):
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(s or ""))
    return float(m.group(0).replace(",", ".")) if m else None


def find_autodesign_files(folder):
    """Cari net_nodes.shp, net_SpliceClosure*.shp dan file splice plan (.xlsx) di folder output desain otomatis."""
    nodes = clos = None
    plans = []
    for root, dirs, files in os.walk(folder):
        for f in files:
            lf = f.lower()
            if lf.endswith(".shp") and re.search(r"net_?nodes", lf):
                nodes = nodes or os.path.join(root, f)
            elif lf.endswith(".shp") and re.search(r"splice_?closure", lf):
                clos = clos or os.path.join(root, f)
            elif lf.endswith((".xlsx", ".xlsm")) and re.search(r"splice", lf) and not f.startswith("~$"):
                plans.append(os.path.join(root, f))
    plans.sort(key=lambda p: -os.path.getmtime(p))
    return nodes, clos, (plans[0] if plans else None)


def parse_route_sheet(sheets):
    """Sheet 'Route optique': baris per serat ke terminal (FAT).
    Hasil: dict terminal -> {length, fibers:[(fiber, tube)], cable, fatcode, budget}, urutan terminal, fdt_id."""
    for name, rows in sheets:
        for hi, r in enumerate(rows[:8]):
            nr = [_n(c) for c in r]
            if "TERMINAL" in nr and any(c.startswith("PATCHPANEL") for c in nr):
                it = nr.index("TERMINAL")
                ipp = next(i for i, c in enumerate(nr) if c.startswith("PATCHPANEL"))
                il = next((i for i, c in enumerate(nr) if c.startswith("LENGTH") and i > it), None)
                ib = next((i for i, c in enumerate(nr) if "OPTICALBUD" in c or c.startswith("OPTICAL")), None)
                icab = next((i for i, c in enumerate(nr) if c.startswith("CABLESECTION")), None)
                ifat = next((i for i, c in enumerate(nr) if "FAT" in c and i != it), None)
                fdt_id = (rows[0][0] if rows and rows[0] else "").strip()
                terms, order = {}, []
                for r2 in rows[hi + 1:]:
                    r2 = list(r2) + [""] * 20
                    t = (r2[it] or "").strip()
                    if not t:
                        continue
                    if t not in terms:
                        terms[t] = {"length": _num(r2[il]) if il is not None else None, "fibers": [],
                                    "cable": re.sub(r"_\d+$", "", (r2[icab] or "").strip()) if icab is not None else "",
                                    "fatcode": (r2[ifat] or "").strip() if ifat is not None else "",
                                    "budget": (r2[ib] or "").strip() if ib is not None else ""}
                        order.append(t)
                    fib, tub = _int(r2[ipp + 1]), _int(r2[ipp + 2])
                    if fib:
                        terms[t]["fibers"].append((fib, tub))
                return name, terms, order, fdt_id
    return None, {}, [], ""


def parse_closure_sheets(sheets):
    """Sheet per closure (A1 = B000123): tabel Section In | tube | fiber | Usage | fiber | tube | Section Out."""
    out = {}
    for name, rows in sheets:
        if not rows or not rows[0] or not re.match(r"^B\d{4,}", (rows[0][0] or "").strip()):
            continue
        cid = rows[0][0].strip()
        hi = next((i for i, r in enumerate(rows[:15]) if r and _n(r[0]).startswith("SECTIONIN")), None)
        if hi is None:
            continue
        kind = (rows[3][0] if len(rows) > 3 and rows[3] else "").strip()
        body = []
        for r in rows[hi + 1:]:
            r = list(r) + [""] * 8
            if not any(r[:7]):
                continue
            body.append([str(x or "").strip() for x in r[:7]])
        cables = []
        for r in rows[1:6]:
            r = list(r) + [""] * 20
            if r[8] and _n(r[8]).startswith("C"):
                cables.append(" ".join(str(x).strip() for x in (r[8], r[9], r[10], r[11]) if x))
        out[cid] = {"sheet": name, "kind": kind, "rows": body, "cables": cables}
    return out


def _cell(v):
    n = _int(v)
    if n in FIBER_COLORS:
        bg, fg = FIBER_COLORS[n]
        return '<td style="background:%s;color:%s;text-align:center;border:1px solid #999">%s</td>' % (bg, fg, n)
    return '<td style="border:1px solid #999;padding:0 4px">%s</td>' % (v or "")


def closure_html(cid, c):
    h = ['<b>%s</b> %s<br/>' % (cid, c.get("kind", ""))]
    for cb in c.get("cables", []):
        h.append('<small>%s</small><br/>' % cb)
    h.append('<table style="border-collapse:collapse;font-family:Arial;font-size:10px">')
    h.append('<tr style="background:#ddd"><th>Section In</th><th>T</th><th>F</th><th>Usage</th>'
             '<th>F</th><th>T</th><th>Section Out</th></tr>')
    for r in c["rows"]:
        h.append("<tr>" + "".join(_cell(v) if i in (1, 2, 4, 5) else
                                  '<td style="border:1px solid #999;padding:0 4px">%s</td>' % v
                                  for i, v in enumerate(r)) + "</tr>")
    h.append("</table>")
    return "".join(h)


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def write_kmz(path, folders):
    """folders: list (nama_folder, warna_ikon_aabbggrr, [ (nama, lon, lat, html) ])."""
    k = ['<?xml version="1.0" encoding="UTF-8"?>', '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
         '<name>%s</name>' % _esc(os.path.splitext(os.path.basename(path))[0])]
    for i, (fname, color, items) in enumerate(folders):
        k.append('<Style id="s%d"><IconStyle><color>%s</color><scale>0.8</scale><Icon><href>'
                 'files/circle.png</href></Icon></IconStyle>'
                 '<LabelStyle><scale>0.8</scale></LabelStyle></Style>' % (i, color))
    for i, (fname, color, items) in enumerate(folders):
        k.append("<Folder><name>%s</name>" % _esc(fname))
        for nm, lon, lat, html in items:
            k.append('<Placemark><name>%s</name><styleUrl>#s%d</styleUrl><description><![CDATA[%s]]></description>'
                     '<Point><coordinates>%.8f,%.8f,0</coordinates></Point></Placemark>' % (_esc(nm), i, html, lon, lat))
        k.append("</Folder>")
    k.append("</Document></kml>")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("doc.kml", "\n".join(k))
        kmz_add_icons(z, "\n".join(k))


def read_points(path, want=("ELEMENTID", "SUPPORT", "NAME", "PREMISES", "MAXPPDIST", "MODELNUM")):
    lyr = QgsVectorLayer(path, "n", "ogr")
    if not lyr.isValid():
        raise QgsProcessingException("Cannot open %s" % path)
    names = [f.name() for f in lyr.fields()]
    idx = {w: next((i for i, n in enumerate(names) if _n(n) == _n(w)), None) for w in want}
    out = []
    for f in lyr.getFeatures():
        a = f.attributes()
        g = f.geometry()
        if g is None or g.isEmpty():
            continue
        try:
            p = g.asPoint() if not g.isMultipart() else g.centroid().asPoint()
        except Exception:
            p = g.centroid().asPoint()
        rec = {w: (a[i] if i is not None and i < len(a) else None) for w, i in idx.items()}
        rec["x"], rec["y"] = p.x(), p.y()
        out.append(rec)
    return out


def build_codes(fdt_code, fats, terms, order, ratio):
    """Kode FAT: pakai kolom FAT di spliceplan bila ada; bila kosong -> usulan
    <FDT>-Dxx-yy, D = kabel distribusi keluar FDT (urut keluaran pertama), yy = urut jarak dari FDT."""
    have = {t: terms[t]["fatcode"] for t in order if terms[t].get("fatcode")}
    proposed = {}
    if len(have) < len(fats):
        cab_order = []
        for t in order:
            c = terms[t]["cable"] or "?"
            if c not in cab_order:
                cab_order.append(c)
        seq = {}
        for t in sorted([t for t in order if t in fats], key=lambda t: (cab_order.index(terms[t]["cable"] or "?"),
                                                                       terms[t]["length"] or 0, order.index(t))):
            d = cab_order.index(terms[t]["cable"] or "?") + 1
            seq[d] = seq.get(d, 0) + 1
            proposed[t] = "%s-D%02d-%02d" % (fdt_code, d, seq[d])
    return {t: have.get(t) or proposed.get(t, "") for t in fats}, bool(proposed) and len(have) < len(fats)


class PascaDesain(QgsProcessingAlgorithm):
    OUTDIR = "OUTDIR"
    FDT_CODE = "FDT_CODE"
    PROFILE = "PROFILE"
    POLES = "POLES"
    COLO = "COLO"
    OPEN_REPORT = "OPEN_REPORT"

    def createInstance(self):
        return PascaDesain()

    def name(self):
        return "pasca_desain_fdt_fat_code"

    def displayName(self):
        return "3. Post-Design Tables"

    def group(self):
        return "FTTH Design"

    def groupId(self):
        return "ftth_design"

    def shortDescription(self):
        return "Auto-design output folder -> FDT-FAT code table, colour-coded closure tables and post-design checks."

    def shortHelpString(self):
        return ("<p><b>%s</b> v%s &copy; %s</p>" % (__product__, __version__, __author__) +
                "<p><b>How to use</b>: export the finished design from the auto-design software (net_nodes.shp, "
                "net_SpliceClosure.shp, splice plan .xlsx), pick that <b>output folder</b> and click <b>Run</b>.</p>"
                "<p><b>Output</b> (subfolder <code>HASIL_PASCA_DESAIN</code>): FDT-FAT code table (CSV), closure tables "
                "with TIA-598 fibre/tube colours (KMZ, HTML) and a post-design check (homepasses per FAT, FAT-homepass "
                "distance, code format and order, FDT premises, splitter capacity, tube fill, FAT on a pole).</p>"
                "<p><b>Advanced</b>: FDT code (when the splice plan has none), design profile, pole KMZ, colocation note. "
                "Reports are written in Indonesian.</p>")

    def initAlgorithm(self, config=None):
        # Form utama hanya 1 isian (folder); sisanya di "Advanced".
        self.addParameter(QgsProcessingParameterFile(self.OUTDIR, "Auto-design output folder (net_nodes.shp + splice plan .xlsx)",
                                                     behavior=FOLDER_BEHAVIOR))
        for prm in (
                QgsProcessingParameterString(self.FDT_CODE, "FDT code, e.g. ABC1-DEF01-H01 (empty = taken from the splice plan)",
                                             optional=True),
                QgsProcessingParameterEnum(self.PROFILE, "Design profile", options=[p["name"] for p in PROFILES],
                                           defaultValue=0),
                QgsProcessingParameterFile(self.POLES, "Pole or cluster KMZ (checks that every FAT sits on a pole)",
                                           behavior=FILE_BEHAVIOR, optional=True,
                                           fileFilter="KMZ/KML (*.kmz *.kml)"),
                QgsProcessingParameterString(self.COLO, "Colocation note written in the code table (e.g. COLO FDT <cluster ID>)",
                                             optional=True),
                QgsProcessingParameterBoolean(self.OPEN_REPORT, "Open the report when finished", defaultValue=True)):
            prm.setFlags(prm.flags() | ADVANCED_FLAG)
            self.addParameter(prm)

    def prepareAlgorithm(self, parameters, context, feedback):
        root = self.parameterAsFile(parameters, self.OUTDIR, context)
        if root and os.path.isdir(root):
            n = release_old_outputs(root, ("HASIL_PASCA_DESAIN",))
            if n:
                feedback.pushInfo(f"{n} layers from the previous run were removed from the project so the files can be overwritten.")
        return True

    def processAlgorithm(self, parameters, context, feedback):
        folder = self.parameterAsFile(parameters, self.OUTDIR, context)
        if not folder or not os.path.isdir(folder):
            raise QgsProcessingException("Pick the auto-design output folder.")
        fdt_code_in = (self.parameterAsString(parameters, self.FDT_CODE, context) or "").strip().upper()
        ref_dir = QgsSettings().value("seranta/funnel_dir", "") or ""
        prof = resolve_profile(self.parameterAsEnum(parameters, self.PROFILE, context), ref_dir, feedback)
        pole_kmz = self.parameterAsFile(parameters, self.POLES, context)
        colo = (self.parameterAsString(parameters, self.COLO, context) or "").strip() or "-"
        nodes_p, clos_p, plan_p = find_autodesign_files(folder)
        feedback.pushInfo("net_nodes   : %s" % nodes_p)
        feedback.pushInfo("closure     : %s" % clos_p)
        feedback.pushInfo("splice plan : %s" % plan_p)
        if not nodes_p:
            raise QgsProcessingException("net_nodes.shp not found in %s (export shapefiles from the auto-design software first)." % folder)
        if not plan_p:
            raise QgsProcessingException("Splice plan (.xlsx) not found in %s." % folder)

        nodes = read_points(nodes_p)
        sheets = read_xlsx(plan_p, max_empty=50)
        rname, terms, order, fdt_eid = parse_route_sheet(sheets)
        if not terms:
            raise QgsProcessingException("Route sheet (Terminal and Patch panel columns) not found in the splice plan.")
        closures = parse_closure_sheets(sheets)
        fdt_nodes = [n for n in nodes if _n(n["SUPPORT"]) == "FDT"]
        fat_nodes = [n for n in nodes if "FAT" in _n(n["SUPPORT"])]
        fats = {n["ELEMENTID"]: n for n in fat_nodes}
        fdt = fdt_nodes[0] if fdt_nodes else None

        rep, qc = [], []
        # kode FDT: masukan pengguna > awalan kode FAT di spliceplan
        fdt_code = fdt_code_in
        if not fdt_code:
            for t in order:
                m = FAT_RX.match(terms[t].get("fatcode", "").upper())
                if m:
                    fdt_code = m.group(1)
                    break
        if not fdt_code:
            fdt_code = "XXXX-XXXXX-H01"
            qc.append(("KODE_FDT_KOSONG", "Isi parameter Kode FDT (kode FINDIM + -Hxx); dipakai placeholder %s" % fdt_code))
        codes, proposed = build_codes(fdt_code, list(fats), terms, order, prof["ratio"])

        # ===== tabel FDT FAT CODE =====
        rows, fat_spl_sum, prem_sum = [], 0, 0
        for t in sorted(fats, key=lambda e: codes.get(e) or e):
            n = fats[t]
            prem = _int(n["PREMISES"]) or 0
            spl = "1x1x8" if prem < 9 else "2x1x8"          # aturan template FAT FDT CODE
            fat_spl_sum += int(spl[0])
            prem_sum += prem
            fib = terms.get(t, {}).get("fibers", [])
            f1 = fib[0] if len(fib) > 0 else ("-", "-")
            f2 = fib[1] if len(fib) > 1 else ("-", "-")
            rows.append([t, codes.get(t, ""), prem, spl, "%.8f" % n["x"], "%.8f" % n["y"],
                         f1[0], f1[1], f2[0], f2[1], colo])
        fdt_spl = int(math.ceil(fat_spl_sum / float(prof["ratio"])))
        if fdt:
            rows.insert(0, [fdt["ELEMENTID"], fdt_code, _int(fdt["PREMISES"]) or prem_sum,
                            "%dx1x%d" % (fdt_spl, prof["ratio"]), "%.8f" % fdt["x"], "%.8f" % fdt["y"],
                            "-", "-", "-", "-", colo])
        base = re.sub(r"[^A-Z0-9_-]", "_", fdt_code)
        out_dir = os.path.join(folder, "HASIL_PASCA_DESAIN")
        os.makedirs(out_dir, exist_ok=True)
        csv_p = os.path.join(out_dir, "%s_FDT_FAT_CODE.csv" % base)
        import csv
        with open(csv_p, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(["ELEMENTID", "FAT FDT CODE", "PREMISES", "SPLITTERS", "LONG", "LAT", "F", "T", "F", "T", "COLO"])
            w.writerows(rows)

        # ===== QC APD (Handbook KMZ) =====
        fd = prof["fat_dist"]
        for t, n in fats.items():
            prem = _int(n["PREMISES"]) or 0
            code = codes.get(t, "")
            if prem > prof["fat_max"]:
                qc.append(("FAT_LEBIH_%d_HP" % prof["fat_max"], "%s (%s) melayani %d HP" % (code, t, prem)))
            elif prem < prof["fat_min"]:
                qc.append(("INFO_FAT_KURANG_%d_HP" % prof["fat_min"], "%s (%s) hanya %d HP (maksimalkan 8/16)" % (code, t, prem)))
            dmax = _num(n["MAXPPDIST"])
            if dmax is not None and dmax > fd:
                kind = "FAT_HP_LEBIH_%dM" % fd
                qc.append((kind, "%s: HP terjauh %.0f m (batas %.0f m%s)" % (code, dmax, fd,
                                                                              "; 150 m hanya special case" if fd < 150 else "")))
            if code and not FAT_RX.match(code):
                qc.append(("KODE_FAT_SALAH", "%s: harus 21 karakter pola AAA9-AAA99-H99-D99-99" % code))
            elif code and not code.startswith(fdt_code):
                qc.append(("KODE_FAT_BEDA_FDT", "%s tidak berawalan kode FDT %s" % (code, fdt_code)))
        if fdt_code and not FDT_RX.match(fdt_code):
            qc.append(("KODE_FDT_SALAH", "%s: harus 14 karakter pola AAA9-AAA99-H99" % fdt_code))
        # urutan FAT per kabel D: berurutan 1..n dan makin jauh dari FDT
        byd = {}
        for t, c in codes.items():
            m = FAT_RX.match(c or "")
            if m:
                byd.setdefault(m.group(2), []).append((int(m.group(3)), terms.get(t, {}).get("length") or 0, c))
        for d, lst in sorted(byd.items()):
            nums = sorted(x[0] for x in lst)
            if nums != list(range(1, len(nums) + 1)):
                qc.append(("URUTAN_FAT_LONCAT", "D%s: nomor %s (harus 1..%d tanpa loncat/dobel)" % (d, nums, len(nums))))
            srt = sorted(lst)
            for a, b in zip(srt, srt[1:]):
                if b[1] and a[1] and b[1] + 1 < a[1]:
                    qc.append(("URUTAN_FAT_TIDAK_DARI_FDT", "%s (%.0f m) lebih dekat ke FDT daripada %s (%.0f m)" % (b[2], b[1], a[2], a[1])))
        # jumlah FAT APD vs spliceplan, premises FDT, splitter FDT
        sp_fats = [t for t in order if t in fats or re.match(r"^N\d+\.\d+\.\d+$", t)]
        if len(set(sp_fats)) != len(fats):
            qc.append(("JUMLAH_FAT_BEDA", "net_nodes %d FAT, spliceplan %d terminal" % (len(fats), len(set(sp_fats)))))
        if fdt:
            fprem = _int(fdt["PREMISES"])
            if fprem is not None and fprem != prem_sum:
                qc.append(("PREMISES_FDT_BEDA", "FDT %d HP, jumlah HP di FAT %d (samakan dengan BOM)" % (fprem, prem_sum)))
            if (fprem or prem_sum) > prof["fdt_cap"]:
                qc.append(("FDT_LEBIH_KAPASITAS", "%d HP > %d (profil %s)" % (fprem or prem_sum, prof["fdt_cap"], prof["key"])))
        if fdt_spl > prof["max_spl"]:
            qc.append(("SPLITTER_FDT_LEBIH", "%dx1x%d > maks %d splitter" % (fdt_spl, prof["ratio"], prof["max_spl"])))
        # tube harus penuh dulu sebelum pindah tube (alokasi core) - per kabel distribusi
        bycab = {}
        for t in order:
            for fib, tub in terms[t]["fibers"]:
                bycab.setdefault(terms[t]["cable"] or "?", []).append((tub or 0, fib))
        for cab, lst in bycab.items():
            tubes = sorted({t for t, f in lst})
            for tb in tubes[:-1]:
                used = len({f for t, f in lst if t == tb})
                if used < 12:
                    qc.append(("TUBE_BELUM_PENUH", "%s: tube %d baru terpakai %d/12 core tapi tube berikutnya sudah dipakai" % (cab, tb, used)))
        # FAT harus di titik tiang
        if pole_kmz:
            from . import qc_core as _qc
            # sama dengan alat 4 (profil fat_pole_tol_m, Handbook kasus 3 "FAT melayang")
            fat_pole_tol = float(_qc.pv(_qc.get_profile("APD_1X4")[0], "fat_pole_tol_m", 2.0))
            poles = [g for folders, nm, kind, g in kml_features(pole_kmz) if kind == "point" and classify(folders) == "pole"]
            for t, n in fats.items():
                dmin = min((math.hypot((p.x() - n["x"]) * 111320 * math.cos(math.radians(n["y"])), (p.y() - n["y"]) * 110574)
                            for p in poles), default=None)
                if dmin is not None and dmin > fat_pole_tol:
                    qc.append(("FAT_MELAYANG", "%s %.1f m dari tiang terdekat (batas %.1f m)" % (codes.get(t, t), dmin, fat_pole_tol)))

        # ===== KMZ closure table + info FAT/FDT =====
        kmz_p = os.path.join(out_dir, "%s_CLOSURE_TABLE.kmz" % base)
        folders = []
        if fdt:
            folders.append(("FDT", "ff000000", [(fdt_code, fdt["x"], fdt["y"],
                                                 "<b>%s</b><br/>Premises: %s<br/>Splitter: %s<br/>%s" % (
                                                     fdt_code, rows[0][2], rows[0][3], "" if colo == "-" else colo))]))
        fat_items = []
        for r in rows[1 if fdt else 0:]:
            fat_items.append((r[1] or r[0], float(r[4]), float(r[5]),
                              '<b>%s</b><br/>ElementID: %s<br/>Premises: %s<br/>Splitter: %s<br/>'
                              '<table style="border-collapse:collapse;font-size:11px"><tr><th>F</th><th>T</th></tr>'
                              '<tr>%s%s</tr><tr>%s%s</tr></table>' % (r[1], r[0], r[2], r[3], _cell(r[6]), _cell(r[7]),
                                                                       _cell(r[8]), _cell(r[9]))))
        folders.append(("FAT", "ff00ffff", fat_items))
        clos_items, miss = [], 0
        if clos_p:
            cpts = {c["ELEMENTID"]: c for c in read_points(clos_p)}
            for cid, c in sorted(closures.items()):
                if cid in cpts:
                    clos_items.append((cid, cpts[cid]["x"], cpts[cid]["y"], closure_html(cid, c)))
                else:
                    miss += 1
        folders.append(("Closure (tabel core)", "ff0000ff", clos_items))
        write_kmz(kmz_p, folders)
        html_p = os.path.join(out_dir, "%s_CLOSURE_TABLE.html" % base)
        from . import report_ui as U
        body = ("<section class='block'><h2>Cara membaca</h2><p class='lead'>Satu tabel per closure. Setiap baris adalah satu core: "
                "warna sel mengikuti kode warna serat TIA-598 (1 biru sampai 12 aqua), sehingga teknisi bisa langsung mencocokkan "
                "dengan kabel di lapangan. Kolom kiri adalah kabel masuk, kolom kanan kabel keluar.</p></section>" +
                "".join("<section class='block' style='overflow-x:auto'>%s</section>" % closure_html(cid, c)
                        for cid, c in sorted(closures.items())))
        with open(html_p, "w", encoding="utf-8") as fh:
            fh.write(U.page("Tabel closure %s" % base, "Tabel core per closure", fdt_code or base,
                            "%d closure dengan tabel core dari Splice Plan." % len(closures),
                            [("FDT", fdt_code), ("Alat", "%s v%s" % (__product__, __version__))], None, [], body,
                            "%s v%s" % (U.E(__product__), __version__), with_tools=False))

        # ===== laporan =====
        cek = [q for q in qc if not q[0].startswith("INFO")]
        head = ["LAPORAN PASCA-DESAIN (FDT FAT CODE + CLOSURE TABLE + QC APD)",
                "Alat    : %s v%s (c) %s, integritas %s" % (__product__, __version__, __author__, integrity_status()),
                "Folder  : %s" % folder, "Profil  : %s (%s)" % (prof["name"], prof["src"]),
                "FDT     : %s  (%s)" % (fdt_code, fdt["ELEMENTID"] if fdt else "tidak ada node FDT"),
                "FAT     : %d node, %d terminal di sheet '%s', %d closure ber-tabel" % (len(fats), len(order), rname, len(closures)),
                "Hasil   : %s" % out_dir, ""]
        if proposed:
            head.append("PERHATIAN: spliceplan belum punya kolom kode FAT -> kode di CSV adalah USULAN "
                        "(D = kabel keluar FDT, nomor urut dari FDT). Periksa lalu isi kolom FAT di spliceplan.")
            head.append("")
        rep.append("RINGKASAN: %d perlu dicek, %d info" % (len(cek), len(qc) - len(cek)))
        kinds = {}
        for k, t in qc:
            kinds.setdefault(k, []).append(t)
        for k, lst in sorted(kinds.items(), key=lambda kv: kv[0].startswith("INFO")):
            rep.append("  %-28s %3d" % (k, len(lst)))
            for t in lst[:30]:
                rep.append("      - %s" % t)
        if miss:
            rep.append("  (%d closure di spliceplan tidak ada di net_SpliceClosure.shp)" % miss)
        lap = os.path.join(out_dir, "%s_QC_APD.txt" % base)
        with open(lap, "w", encoding="utf-8") as fh:
            fh.write("\n".join(head + rep) + "\n")
        for ln in head + rep:
            feedback.pushInfo(ln)
        self._open = lap if self.parameterAsBool(parameters, self.OPEN_REPORT, context) else None
        return {self.OUTDIR: out_dir}

    def postProcessAlgorithm(self, context, feedback):
        if getattr(self, "_open", None) and os.path.exists(self._open):
            try:
                from qgis.PyQt.QtCore import QUrl
                from qgis.PyQt.QtGui import QDesktopServices
                QDesktopServices.openUrl(QUrl.fromLocalFile(self._open))
            except Exception as _e:
                _log.note(_e)
        return {}

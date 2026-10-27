# -*- coding: utf-8 -*-
# Seranta - FTTH Design Assistant - QC paket tiga berkas (KMZ APD + Splice Plan + tabel kode FDT/FAT)
# Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-2.0-or-later (see LICENSE).
"""Tujuh kelompok QC operasional untuk desain APD (tanpa QGIS; dapat diuji dengan Python biasa):

QC-01 kode & grouping FDT   QC-02 premises, splitter, fiber/tube   QC-03 properties FDT/FAT (COLO/NEW)
QC-04 tiang existing vs referensi   QC-05 rasio pancingan & closure   QC-06 tiang pada perangkat
QC-07 pancingan & tiang nganggur

Prinsip: lingkup Feeder dan Distribution dipisah (closure/kabel Feeder tidak ikut penyebut Distribution);
satu kode FDT = satu perangkat walau digambar di dua paket; data acuan tidak ada -> UNVERIFIED (bukan PASS).
"""
import csv
import os
import re

try:
    from . import qc_core as Q
except ImportError:          # diuji tanpa paket (python tests/...)
    import qc_core as Q

finding, RuleResult, pv, norm_code = Q.finding, Q.RuleResult, Q.pv, Q.norm_code
Grid, line_len, point_line = Q.Grid, Q.line_len, Q.point_line

FAT_RX = re.compile(r"^(?P<fdt>[A-Z0-9]+(?:-[A-Z0-9]+)*?-H\d{1,3})-D(?P<d>\d{1,3})-(?P<n>\d{1,3})$", re.I)
FDT_RX = re.compile(r"^[A-Z0-9]{2,6}-[A-Z0-9]{2,8}-H\d{1,3}$", re.I)
SPL_RX = re.compile(r"^\s*(\d+)\s*x\s*1\s*x\s*(\d+)\s*$", re.I)


def _pt(o):
    return ("point", (o["x"], o["y"]))


def _path(o):
    return " / ".join(o.get("folders") or []).lower()


def _f(v):
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _i(v):
    x = _f(v)
    return int(x) if x is not None else None


# =============================================================================================
# Pembaca berkas pendukung
# =============================================================================================
def _rows_of(path, read_xlsx=None):
    """[(nama_sheet, rows)] dari .xlsx (lewat read_xlsx yang diberikan) atau .csv (pemisah ; atau ,)."""
    if path.lower().endswith(".csv"):
        with open(path, encoding="utf-8-sig", errors="replace") as fh:
            txt = fh.read()
        dl = ";" if txt.count(";") > txt.count(",") else ","
        return [("csv", [r for r in csv.reader(txt.splitlines(), delimiter=dl)])]
    if read_xlsx is None:
        return []
    return read_xlsx(path)


def read_code_table(path, read_xlsx=None):
    """Tabel kode FDT/FAT (kolom: kode, PREMISES, SPLITTERS, LAT, LONG, F/T SP1, F/T SP2, COLO opsional).
    Hasil: ({kode_norm: baris}, catatan)."""
    out, notes = {}, []
    for sh, rows in _rows_of(path, read_xlsx):
        hi = None
        for i, r in enumerate(rows[:15]):
            h = [str(c or "").strip().upper() for c in r]
            if any(re.search(r"(FDT|FAT).*(FDT|FAT).*CODE|^CODE$|^KODE", c) for c in h) and any("PREMIS" in c for c in h):
                hi = i
                break
        if hi is None:
            continue
        h = [str(c or "").strip().upper() for c in rows[hi]]

        def col(rx):
            return next((j for j, c in enumerate(h) if re.search(rx, c)), None)
        ic, ip, isp = col(r"CODE|KODE"), col(r"PREMIS"), col(r"^SPLITTERS?$")
        ila, ilo = col(r"^LAT"), col(r"^LON")
        f1, t1, f2, t2 = col(r"^F\s*\(\s*SP\s*1"), col(r"^T\s*\(\s*SP\s*1"), col(r"^F\s*\(\s*SP\s*2"), col(r"^T\s*\(\s*SP\s*2")
        icolo = col(r"COLO|KETERANGAN|CLUSTER")
        for r in rows[hi + 1:]:
            def g(j):
                return str(r[j]).strip() if j is not None and j < len(r) and r[j] is not None else ""
            code = g(ic)
            if not code or not re.search(r"[A-Z]", code, re.I):
                continue
            m = SPL_RX.match(g(isp))
            out[norm_code(code)] = {
                "code": code, "premises": _f(g(ip)), "spl_n": int(m.group(1)) if m else None,
                "spl_r": int(m.group(2)) if m else None, "lat": _f(g(ila)), "lon": _f(g(ilo)),
                "ft": [(_i(g(f1)), _i(g(t1))), (_i(g(f2)), _i(g(t2)))], "colo": g(icolo),
                "sheet": sh, "kind": "FAT" if FAT_RX.match(code) else "FDT"}
        notes.append("%s: %d kode dari sheet '%s'" % (os.path.basename(path), len(out), sh))
        break
    if not out:
        notes.append("%s: kolom kode/PREMISES tidak dikenali" % os.path.basename(path))
    return out, notes


def read_splice_plan(path, read_xlsx=None):
    """Splice Plan: satu sheet per FAT (nama sheet = kode FAT). Ambil masukan splitter dari baris 'Section In | T |
    F | Usage | ...' yang Usage-nya 'Kxx SPnnnnnn'. Hasil: ({kode_norm: [(sp_id, tube, fiber)]}, catatan)."""
    out, notes = {}, []
    if not path:
        return out, notes
    route = {}
    for sh, rows in _rows_of(path, read_xlsx):
        if re.match(r"route\s*optique", sh.strip(), re.I):
            # serat di sisi FDT (patch panel): Terminal | Length | Patch panel | F | T
            for i, r in enumerate(rows[:10]):
                h = [str(x or "").strip().lower() for x in r]
                if "terminal" in h and "f" in h and "t" in h:
                    it, i_f, i_t = h.index("terminal"), h.index("f"), h.index("t")
                    for rr in rows[i + 1:]:
                        if len(rr) > max(it, i_f, i_t) and FAT_RX.match(str(rr[it] or "").strip()):
                            route[norm_code(rr[it])] = (_i(rr[i_t]), _i(rr[i_f]))
                    break
            continue
        if not FAT_RX.match(sh.strip()):
            continue
        hdr = None
        for i, r in enumerate(rows):
            c = [str(x or "").strip().lower() for x in r[:7]]
            if len(c) >= 4 and c[0] == "section in" and c[3] == "usage":
                hdr = i
                break
        if hdr is None:
            continue
        sps = {}
        for r in rows[hdr + 1:]:
            if len(r) < 4:
                continue
            m = re.search(r"\bSP\s*0*(\d+)", str(r[3] or ""), re.I)
            if not m:
                continue
            t, f = _i(r[1]), _i(r[2])
            sps.setdefault(int(m.group(1)), (t, f))
        out[norm_code(sh)] = [(k, v[0], v[1]) for k, v in sorted(sps.items())]
    # nomor serat di sheet FAT bisa nomor lokal kabel cabang (setelah closure); acuan tabel kode = serat di FDT.
    # Bila Route optique ada: SP1 = serat di FDT, SPn = SP1 + selisih lokal (urutan serat dipertahankan di closure)
    for k, (t0, f0) in route.items():
        sp = out.get(k)
        if not sp or t0 is None or f0 is None:
            continue
        lt, lf = sp[0][1], sp[0][2]
        out[k] = [(s_id, t0 + ((t or lt) - (lt or 0)), f0 + ((f or lf) - (lf or 0))) for s_id, t, f in sp]
    notes.append("%s: %d sheet FAT dengan data splitter%s" % (os.path.basename(path), len(out),
                 ", serat di FDT dari sheet Route optique (%d FAT)" % len(route) if route else ""))
    return out, notes


def read_code_master(path, read_xlsx=None):
    """Daftar kode FDT acuan (rekap kode / attributes): semua sel berbentuk kode FDT."""
    codes = set()
    for _sh, rows in _rows_of(path, read_xlsx):
        for r in rows:
            for c in r:
                s = str(c or "").strip()
                if FDT_RX.match(s):
                    codes.add(norm_code(s))
    return codes


# =============================================================================================
# Normalisasi
# =============================================================================================
def unify_nodes(net, same_m, pr):
    """Satu kode perangkat = satu objek logis. FDT yang digambar di folder Feeder dan Distribution (kode sama,
    lokasi <= same_m) digabung; keanggotaan paket disimpan di 'packages'. Kode sama di lokasi berjauhan TIDAK
    digabung (itu kandidat duplikat). Hasil: daftar (kode, jumlah digabung)."""
    keep, merged = [], []
    for n in net.nodes:
        k = norm_code(n.get("name"))
        twin = None
        if k:
            for o in keep:
                if norm_code(o.get("name")) == k and o["kind"] == n["kind"] and pr.d((o["x"], o["y"]), (n["x"], n["y"])) <= same_m:
                    twin = o
                    break
        if twin is None:
            n.setdefault("packages", set())
            if n.get("scope"):
                n["packages"].add(n["scope"])
            keep.append(n)
        else:
            twin.setdefault("packages", set())
            if n.get("scope"):
                twin["packages"].add(n["scope"])
            for a, v in (n.get("attrs") or {}).items():
                twin.setdefault("attrs", {}).setdefault(a, v)
            twin.setdefault("twins", []).append(n)
            merged.append(twin.get("name"))
    net.nodes[:] = keep
    return merged


def enrich_codes(main, kmz, pr, tol_m=3.0):
    """Node hasil ekspor (ELEMENTID N001.01.xx, tanpa kode) diberi kode FDT/FAT dari KMZ APD pada lokasi yang sama."""
    if not kmz or not kmz.nodes or main is kmz:
        return 0
    g = Grid([((n["x"], n["y"]), n) for n in kmz.nodes], pr, 20.0)
    n_set = 0
    for n in main.nodes:
        if n["kind"] not in ("FAT", "FDT") or FAT_RX.match(n.get("name") or "") or FDT_RX.match(n.get("name") or ""):
            continue
        hits = [h for h in g.near((n["x"], n["y"]), tol_m) if h[2]["kind"] == n["kind"]]
        hit = hits[0] if hits else None
        if hit:
            n["autodesign_name"] = n.get("name")
            n["name"] = hit[2]["name"]
            n["folders"], n["scope"] = hit[2].get("folders", []), hit[2].get("scope", "")
            n["packages"] = set(hit[2].get("packages") or ({hit[2]["scope"]} if hit[2].get("scope") else set()))
            if hit[2].get("status") and not n.get("status"):
                n["status"] = hit[2]["status"]
            for k, v in (hit[2].get("attrs") or {}).items():
                n.setdefault("attrs", {}).setdefault(k, v)
            n_set += 1
    return n_set


# =============================================================================================
# Kelas objek dari folder KMZ APD
# =============================================================================================
def devices(kmz):
    """Perangkat menurut folder: FDT baru, FDT existing, FAT AE, FAT UG, closure 96 baru (per lingkup)."""
    out = {"fdt_new": [], "fdt_exist": [], "fat_ae": [], "fat_ug": [], "fat_exist": [], "clos96_new": [], "clos_other": []}
    for n in kmz.nodes:
        p = _path(n)
        if n["kind"] == "FDT":
            (out["fdt_exist"] if re.search(r"eksist|exist", p) else out["fdt_new"]).append(n)
        elif n["kind"] == "FAT":
            if re.search(r"eksist|exist", p):
                out["fat_exist"].append(n)
            elif re.search(r"\bug\b|pedestal", p):
                out["fat_ug"].append(n)
            else:
                out["fat_ae"].append(n)
    for c in kmz.closures:
        p = _path(c)
        if re.search(r"new\s*closure\s*96", p):
            out["clos96_new"].append(c)
        else:
            out["clos_other"].append(c)
    return out


# =============================================================================================
# QC-01 kode & grouping FDT
# =============================================================================================
def rule_fdt_code(net, kmz, prof, pr, master=None, master_src="", dl_codes=None):
    r = RuleResult("QC01_KODE_FDT", "Kode FDT: format, tidak duplikat, kode baru tercatat di rekap", "-", "QC-01",
                   "INTERNAL", "Aturan QC operasional slide 2 (kode sesuai attributes, tidak duplikat, masuk rekap)")
    src = kmz if kmz is not None and kmz.nodes else net
    fdts = [n for n in src.nodes if n["kind"] == "FDT"]
    if not fdts:
        return r.unverify("tidak ada FDT di data")
    same = pv(prof, "fdt_same_m", 30.0)
    by = {}
    for n in src.nodes:
        k = norm_code(n.get("name"))
        if k:
            by.setdefault(k, []).append(n)
    for k, lst in by.items():
        if len(lst) < 2:
            continue
        far = max(pr.d((a["x"], a["y"]), (b["x"], b["y"])) for a in lst for b in lst)
        kinds = {a["kind"] for a in lst}
        if far > same or len(kinds) > 1:
            r.add(finding("FDT_CODE_DUPLICATE", "ERROR", "Kode %s dipakai %d objek berbeda (terpisah %.0f m) - satu kode harus satu "
                          "perangkat" % (lst[0]["name"], len(lst), far), _pt(lst[0]), lst[0]["kind"], lst[0]["name"],
                          round(far, 1), same, "beri kode unik atau hapus objek ganda", scope=lst[0].get("scope", ""), unit="m"))
    for d in fdts:
        nm = d.get("name") or ""
        if not FDT_RX.match(nm):
            r.add(finding("FDT_CODE_FORMAT", "WARNING", "Kode FDT '%s' tidak berpola <KOTA>-<AREA>-Hnn" % nm, _pt(d), "FDT", nm,
                          recommendation="samakan dengan kode di attributes/rekap", scope=d.get("scope", "")))
    for f in [n for n in src.nodes if n["kind"] == "FAT"]:
        m = FAT_RX.match(f.get("name") or "")
        if m and not any(norm_code(m.group("fdt")) == norm_code(d.get("name")) for d in fdts):
            r.add(finding("FAT_CODE_PARENT_UNKNOWN", "ERROR", "Awalan kode FAT %s (%s) tidak sama dengan kode FDT mana pun di desain"
                          % (f["name"], m.group("fdt")), _pt(f), "FAT", f["name"], recommendation="perbaiki awalan kode FAT",
                          scope=f.get("scope", "")))
    new_fdts = [d for d in fdts if not re.search(r"eksist|exist", _path(d)) and d.get("status") != "EXISTING"]
    dln = {}
    for k_, v_ in (dl_codes or {}).items():
        dln.setdefault(norm_code(k_), []).extend(v_)
    if dl_codes:
        for d in new_fdts:
            hits = [x for x in dln.get(norm_code(d.get("name")), []) if pr.d((x[0], x[1]), (d["x"], d["y"])) > pv(prof, "fdt_same_m", 30.0) * 5]
            if hits:
                r.add(finding("FDT_CODE_EXISTS_ELSEWHERE", "ERROR", "Kode FDT baru %s sudah dipakai FDT lain di data jaringan existing "
                              "(%.0f m dari sini)" % (d["name"], min(pr.d((x[0], x[1]), (d["x"], d["y"])) for x in hits)),
                              _pt(d), "FDT", d["name"], recommendation="ambil kode baru yang belum terpakai",
                              scope=d.get("scope", "")))
    if master is None:
        r.notes.append("Rekap kode / attributes tidak diberikan: keterdaftaran kode FDT baru UNVERIFIED.")
        r.unverify("UNVERIFIED: rekap kode FDT / attributes tidak diberikan - keunikan lintas proyek belum dapat dipastikan")
    else:
        for d in new_fdts:
            if norm_code(d.get("name")) not in master:
                r.add(finding("FDT_NEW_NOT_IN_REKAP", "ERROR", "Kode FDT baru %s belum ada di rekap kode (%s)" % (d["name"], master_src),
                              _pt(d), "FDT", d["name"], recommendation="daftarkan kode di rekap atau pakai kode yang terdaftar",
                              scope=d.get("scope", "")))
        r.stats["rekap"] = "%d kode di %s" % (len(master), master_src)
    if dl_codes is None:
        r.notes.append("Data jaringan existing tidak dibaca: duplikasi kode dengan proyek lain tidak dicek.")
    else:
        r.stats["grouping"] = fdt_grouping(fdts, dl_codes, master, prof, pr, r)
    return r


def _code_parts(code):
    """'BNA1-LEP01-H05' -> ('BNA1-LEP01', 5); None bila bukan pola kode FDT."""
    c = str(code or "").strip().upper()
    m = re.match(r"^(?P<area>[A-Z0-9]{2,6}-[A-Z0-9]{2,8})-H(?P<n>\d{1,3})$", c) or \
        re.match(r"^(?P<area>[A-Z0-9]{4,14}?)H(?P<n>\d{1,3})$", re.sub(r"[^A-Z0-9]", "", c))
    if not m:
        return None
    return (re.sub(r"[^A-Z0-9]", "", m.group("area")), int(m.group("n")), m.group("area"))


def fdt_grouping(fdts, dl_codes, master, prof, pr, r=None):
    """Kandidat grouping FDT (aturan PPT 1: grouping dari jaringan existing): untuk setiap FDT di desain, kelompok area
    (awalan kode) FDT existing di sekitarnya, FDT existing terdekat, dan kode kandidat berikutnya di area itu.
    Menambah temuan FDT_GROUP_MISMATCH bila awalan kode FDT baru berbeda dari kelompok mayoritas di sekitarnya."""
    radius = pv(prof, "colo_radius_m", 1000.0)
    same_m = pv(prof, "fdt_same_m", 30.0) * 5
    # FDT desain ini yang sudah tercatat di jaringan existing pada lokasi yang sama (mis. Design Lite terbaru sudah memuat
    # proyek ini) bukan "pemakaian di tempat lain": keluarkan dari daftar kode terpakai.
    selves = {norm_code(d.get("name")): (d["x"], d["y"]) for d in fdts if d.get("name")}

    def _is_self(code, pts):
        xy = selves.get(norm_code(code))
        return bool(xy and pts and min(pr.d(xy, (x, y)) for x, y in pts) <= same_m)
    used, disp = {}, {}
    # rekap kode yang sudah memuat kode FDT desain ini juga bukan pemakaian di tempat lain (memang wajib tercatat)
    for code in [c for c in dl_codes if not _is_self(c, dl_codes[c])] + [c for c in (master or ()) if norm_code(c) not in selves]:
        cp = _code_parts(code)
        if cp:
            used.setdefault(cp[0], set()).add(cp[1])
            if "-" in cp[2] or cp[0] not in disp:
                disp[cp[0]] = cp[2]
    out = []
    for d in fdts:
        near = []
        for code, pts in dl_codes.items():
            if not pts:
                continue
            dist = min(pr.d((x, y), (d["x"], d["y"])) for x, y in pts)
            if dist <= radius and norm_code(code) != norm_code(d.get("name")):
                near.append((dist, code))
        near.sort()
        areas = {}
        for dist, code in near:
            cp = _code_parts(code)
            if cp:
                areas[cp[0]] = areas.get(cp[0], 0) + 1
        mine = _code_parts(d.get("name"))
        best = max(areas, key=lambda a: (areas[a], -min(dd for dd, c in near if (_code_parts(c) or ("",))[0] == a))) if areas else ""
        nums = used.get(best, set())
        label = disp.get(best, best)
        nxt = "%s-H%02d" % (label, max(nums) + 1) if best and nums else ""
        if not mine:
            status = "KODE TIDAK BERPOLA"
        elif not best:
            status = "TIDAK ADA FDT EXISTING DI RADIUS"
        elif mine[0] == best:
            status = "SESUAI KELOMPOK SEKITAR"
        elif mine[0] in used:
            status = "BEDA KELOMPOK (kelompok %s sudah dipakai di tempat lain)" % mine[2]
        else:
            status = "KELOMPOK BARU"
        own = used.get(mine[0], set()) if mine else set()
        exist = bool(re.search(r"eksist|exist", _path(d))) or d.get("status") == "EXISTING"
        cand = ""
        if mine and not exist:
            cand = "%s-H%02d" % (mine[2], (max(own) + 1) if own else 1) if mine[1] in own else ""
        row = {"fdt": d.get("name") or "", "status_fdt": "COLO" if exist else "NEW", "kelompok_kode": mine[2] if mine else "",
               "kelompok_sekitar": label, "jumlah_fdt_sekitar": len(near),
               "fdt_terdekat": ("%s (%.0f m)" % (near[0][1], near[0][0])) if near else "",
               "kode_kandidat": cand or (nxt if status.startswith("BEDA") else ""), "hasil": status}
        out.append(row)
        if r is None or exist:
            continue
        ev = "FDT terdekat: " + ", ".join("%s %.0f m" % (c, dd) for dd, c in near[:3])
        if status.startswith("BEDA"):
            r.add(finding("FDT_GROUP_MISMATCH", "WARNING", "Kode FDT %s berkelompok %s, padahal %d FDT existing dalam %.0f m berkelompok "
                          "%s dan kelompok %s sudah dipakai di lokasi lain" % (d.get("name"), mine[2], len(near), radius, label, mine[2]),
                          _pt(d), "FDT", d.get("name"), areas.get(best), None,
                          "periksa kelompok kode; kandidat di kelompok sekitar: %s" % (nxt or label), scope=d.get("scope", ""),
                          evidence=ev))
        elif status == "KELOMPOK BARU":
            r.add(finding("FDT_GROUP_NEW", "INFO", "Kode FDT %s membuka kelompok area baru %s (FDT existing sekitar berkelompok %s)"
                          % (d.get("name"), mine[2], label), _pt(d), "FDT", d.get("name"), None, None,
                          "pastikan kelompok area baru ini sudah didaftarkan di rekap kode", scope=d.get("scope", ""), evidence=ev))
    return out


# =============================================================================================
# QC-02 premises, splitter, fiber/tube
# =============================================================================================
def fat_tier(premises):
    if premises is None:
        return None
    return (1, 8) if premises <= 8 else ((2, 8) if premises <= 16 else None)


def rule_premises_splitter(net, kmz, prof, pr, codes=None, splice=None):
    r = RuleResult("QC02_PREMISES_SPLITTER", "Premises & splitter FDT/FAT, alokasi fiber/tube", "22", "QC-02",
                   "INTERNAL", "Aturan QC operasional slide 2; Handbook kasus 22 (premises ikon FDT); kapasitas splitter")
    src = kmz if kmz is not None and kmz.nodes else net
    fdts = [n for n in src.nodes if n["kind"] == "FDT"]
    fats = [n for n in src.nodes if n["kind"] == "FAT"]
    if not fdts or not fats:
        return r.unverify("butuh FDT dan FAT")
    max_spl, ratio = pv(prof, "fdt_max_spl", 12), pv(prof, "fdt_spl_ratio", 4)
    for d in fdts:
        mine = [f for f in fats if (FAT_RX.match(f.get("name") or "") and
                                    norm_code(FAT_RX.match(f["name"]).group("fdt")) == norm_code(d.get("name")))] or \
            (fats if len(fdts) == 1 else [])
        tot = sum(f["premises"] or 0 for f in mine)
        if d["premises"] is not None and mine and abs(d["premises"] - tot) > 0.5:
            r.add(finding("FDT_PREMISES_NE_SUM_FAT", "ERROR", "Premises FDT %s = %g, jumlah premises %d FAT = %g (selisih %+g)"
                          % (d["name"], d["premises"], len(mine), tot, d["premises"] - tot), _pt(d), "FDT", d["name"],
                          d["premises"], tot, "samakan premises ikon FDT dengan jumlah premises FAT", scope=d.get("scope", ""), unit="HP"))
        n, rr = d.get("spl_n"), d.get("spl_r")
        if n is None:
            r.add(finding("FDT_SPLITTER_MISSING", "WARNING", "Properti SPLITTERS FDT %s kosong" % d["name"], _pt(d), "FDT", d["name"],
                          scope=d.get("scope", "")))
            continue
        if rr == ratio and n > max_spl:
            r.add(finding("FDT_SPLITTER_OVER_MAX", "ERROR", "FDT %s memakai %dx1x%d > maksimum %dx1x%d" % (d["name"], n, rr, max_spl, ratio),
                          _pt(d), "FDT", d["name"], n, max_spl, "pecah ke FDT lain / kurangi FAT", scope=d.get("scope", ""), unit="splitter"))
        need = sum(f.get("spl_n") or 0 for f in mine)
        if rr and need > n * rr:
            r.add(finding("FDT_OUTPUT_SHORT", "ERROR", "Output splitter FDT %s = %d (%dx1x%d) < kebutuhan %d input splitter FAT"
                          % (d["name"], n * rr, n, rr, need), _pt(d), "FDT", d["name"], n * rr, need,
                          "tambah splitter FDT (maks %d) atau pindahkan FAT" % max_spl, scope=d.get("scope", ""), unit="port"))
        r.stats.setdefault("fdt", []).append((d["name"], d["premises"], tot, "%sx1x%s" % (n, rr), n * rr if rr else None, need))
    for f in fats:
        t = fat_tier(f["premises"])
        if t is None and f["premises"] is not None:
            r.add(finding("FAT_PREMISES_OVER_16", "ERROR", "FAT %s %g premises > 16" % (f["name"], f["premises"]), _pt(f), "FAT", f["name"],
                          f["premises"], 16, scope=f.get("scope", ""), unit="HP"))
            continue
        if t is None or f.get("spl_n") is None:
            continue
        if (f["spl_n"], f.get("spl_r")) != t:
            under = f["spl_n"] * (f.get("spl_r") or 8) < (f["premises"] or 0)
            r.add(finding("FAT_SPLITTER_TIER", "ERROR" if under else "WARNING",
                          "FAT %s: %g premises memakai %dx1x%s; aturan: 1-8 premises = 1x1x8, 9-16 = 2x1x8%s"
                          % (f["name"], f["premises"], f["spl_n"], f.get("spl_r"),
                             " (kapasitas kurang)" if under else " (splitter berlebih)"),
                          _pt(f), "FAT", f["name"], f["spl_n"], t[0], "ubah splitter menjadi %dx1x8" % t[0], scope=f.get("scope", ""),
                          unit="splitter"))
    if splice is None or codes is None:
        r.notes.append("Splice Plan atau tabel kode tidak lengkap: kecocokan fiber/tube UNVERIFIED.")
    else:
        bad = 0
        for k, row in codes.items():
            if row["kind"] != "FAT":
                continue
            sp = splice.get(k)
            if sp is None:
                r.add(finding("SPLICE_SHEET_MISSING", "WARNING", "Sheet Splice Plan untuk FAT %s tidak ada" % row["code"], None, "FAT",
                              row["code"], recommendation="lengkapi Splice Plan"))
                continue
            if row.get("spl_n") is not None and len(sp) != row["spl_n"]:
                tier = fat_tier(row["premises"])
                ok_tab = tier is not None and tier[0] == row["spl_n"]
                r.add(finding("SPLICE_SPLITTER_COUNT", "ERROR", "FAT %s (%g premises): tabel kode %dx1x8, Splice Plan memuat %d splitter (%s)"
                              % (row["code"], row["premises"] or 0, row["spl_n"], len(sp), ", ".join("SP%06d" % s[0] for s in sp)),
                              None, "FAT", row["code"], len(sp), row["spl_n"],
                              ("aturan %g premises = %dx1x8 sesuai tabel kode: perbarui desain/Splice Plan" % (row["premises"], tier[0]))
                              if ok_tab else "samakan jumlah splitter di desain, Splice Plan dan tabel kode", unit="splitter"))
            for i, (s_id, tube, fib) in enumerate(sp[:2]):
                f0, t0 = row["ft"][i]
                if f0 is None and t0 is None:
                    continue
                if (f0, t0) != (fib, tube):
                    bad += 1
                    r.add(finding("FIBER_TUBE_MISMATCH", "ERROR", "FAT %s SP%d: tabel kode F%s/T%s, Splice Plan F%s/T%s"
                                  % (row["code"], i + 1, f0, t0, fib, tube), None, "FAT", row["code"],
                                  recommendation="samakan F/T tabel kode dengan Splice Plan (sumber kebenaran: Splice Plan)"))
        r.stats["fiber_ok"] = "%d FAT dicocokkan, %d beda F/T" % (sum(1 for row in codes.values() if row["kind"] == "FAT"), bad)
    return r


# =============================================================================================
# QC-03 properties FDT/FAT vs tabel kode (COLO/NEW)
# =============================================================================================
def rule_properties(net, kmz, prof, pr, codes=None, autodesign=None):
    r = RuleResult("QC03_PROPERTIES", "Properties FDT/FAT di KMZ = tabel kode FDT/FAT; keterangan COLO", "14,22", "QC-03",
                   "INTERNAL", "Aturan QC operasional slide 3 (properties sama dengan tabel kode; FDT COLO wajib keterangan cluster)")
    src = kmz if kmz is not None and kmz.nodes else net
    nodes = [n for n in src.nodes if n["kind"] in ("FDT", "FAT")]
    if not nodes:
        return r.unverify("tidak ada FDT/FAT")
    tol = pv(prof, "coord_tol_m", 1.0)
    for d in [n for n in nodes if n["kind"] == "FDT"]:
        exist = bool(re.search(r"eksist|exist", _path(d))) or d.get("status") == "EXISTING"
        colo_v = next((str(v) for k, v in (d.get("attrs") or {}).items() if re.search(r"colo", k or "", re.I) and str(v).strip(" -")), "")
        if exist and not colo_v:
            r.add(finding("FDT_COLO_INFO_MISSING", "ERROR", "FDT COLO %s tidak memuat keterangan cluster yang di-colo di Properties"
                          % d["name"], _pt(d), "FDT", d["name"], recommendation="isi kolom COLO dengan cluster induk", scope=d.get("scope", "")))
        if not exist and colo_v:
            r.add(finding("FDT_NEW_HAS_COLO", "WARNING", "FDT NEW %s memuat kolom COLO ('%s') - untuk FDT baru kolom ini tidak ada"
                          % (d["name"], colo_v[:60]), _pt(d), "FDT", d["name"], scope=d.get("scope", "")))
    if codes is None:
        return r.unverify("UNVERIFIED: tabel kode FDT/FAT (FAT FDT CODE .xlsx/.csv) tidak diberikan") if not r.findings else r
    seen = set()
    for n in nodes:
        k = norm_code(n.get("name"))
        row = codes.get(k)
        seen.add(k)
        if row is None:
            r.add(finding("PROP_CODE_NOT_IN_TABLE", "ERROR", "%s %s ada di KMZ tetapi tidak ada di tabel kode" % (n["kind"], n["name"]),
                          _pt(n), n["kind"], n["name"], scope=n.get("scope", "")))
            continue
        diffs = []
        if row["premises"] is not None and n["premises"] is not None and abs(row["premises"] - n["premises"]) > 0.5:
            diffs.append("premises %g vs %g" % (n["premises"], row["premises"]))
        if row["spl_n"] is not None and n.get("spl_n") is not None and (row["spl_n"], row["spl_r"]) != (n["spl_n"], n.get("spl_r")):
            diffs.append("splitter %sx1x%s vs %sx1x%s" % (n["spl_n"], n.get("spl_r"), row["spl_n"], row["spl_r"]))
        if row["lat"] is not None and row["lon"] is not None:
            dd = pr.d((n["x"], n["y"]), (row["lon"], row["lat"]))
            if dd > tol:
                diffs.append("koordinat bergeser %.1f m" % dd)
        a = n.get("attrs") or {}
        for i, (fk, tk) in enumerate((("F (SP1)", "T (SP1)"), ("F (SP2)", "T (SP2)"))):
            fa, ta = _i(a.get(fk)), _i(a.get(tk))
            if (fa, ta) != (None, None) and (fa, ta) != row["ft"][i]:
                diffs.append("F/T SP%d %s/%s vs %s/%s" % (i + 1, fa, ta, row["ft"][i][0], row["ft"][i][1]))
        if diffs:
            r.add(finding("PROP_MISMATCH", "ERROR", "%s %s: KMZ vs tabel kode berbeda - %s" % (n["kind"], n["name"], "; ".join(diffs)),
                          _pt(n), n["kind"], n["name"], recommendation="samakan Properties KMZ dengan tabel kode", scope=n.get("scope", "")))
    for k, row in codes.items():
        if k not in seen:
            r.add(finding("PROP_CODE_NOT_IN_KMZ", "ERROR", "%s %s ada di tabel kode tetapi tidak ada di KMZ" % (row["kind"], row["code"]),
                          ("point", (row["lon"], row["lat"])) if row["lon"] and row["lat"] else None, row["kind"], row["code"]))
    if autodesign:
        g = Grid([((n["x"], n["y"]), n) for n in autodesign.nodes if n["kind"] in ("FAT", "FDT")], pr, 20.0) if autodesign.nodes else None
        for k, row in codes.items():
            if g is None or row["lon"] is None:
                continue
            hits = g.near((row["lon"], row["lat"]), 3.0)
            hit = next((h for h in hits if h[2]["kind"] == row["kind"]), None)
            if not hit:
                continue
            s = hit[2]
            diffs = []
            if s["premises"] is not None and row["premises"] is not None and abs(s["premises"] - row["premises"]) > 0.5:
                diffs.append("premises %g vs %g" % (s["premises"], row["premises"]))
            if s.get("spl_n") is not None and row["spl_n"] is not None and s["spl_n"] != row["spl_n"]:
                diffs.append("splitter %sx1x%s vs %sx1x%s" % (s["spl_n"], s.get("spl_r"), row["spl_n"], row["spl_r"]))
            if diffs:
                r.add(finding("AUTODESIGN_VS_TABLE", "WARNING", "%s: hasil ekspor desain (%s) vs tabel kode berbeda - %s"
                              % (row["code"], s.get("autodesign_name") or s["id"], "; ".join(diffs)), ("point", (row["lon"], row["lat"])),
                              row["kind"], row["code"], recommendation="jalankan ulang ekspor atau perbarui tabel kode"))
    return r


# =============================================================================================
# QC-04 tiang existing vs referensi tiang existing
# =============================================================================================
def rule_pole_reference(kmz, prof, pr, ref_pts=None, ref_src=""):
    r = RuleResult("QC04_TIANG_REFERENSI", "Tiang existing di desain <= 10 m dari tiang existing referensi", "24", "QC-04",
                   "INTERNAL", "Aturan QC operasional slide 3 (pole > 10 m dari pole existing referensi = salah); Handbook kasus 24")
    if kmz is None or not kmz.poles:
        return r.unverify("layer tiang tidak ada")
    ex = [p for p in kmz.poles if p["status"] == "EXISTING"]
    if not ex:
        r.notes.append("Tidak ada tiang existing di desain.")
        return r
    if not ref_pts:
        return r.unverify("UNVERIFIED: data tiang existing referensi (per kota) tidak diberikan - %d tiang existing belum dapat "
                          "dicek" % len(ex))
    lim = pv(prof, "ext_pole_ref_m", 10.0)
    g = Grid([(p, None) for p in ref_pts], pr, 25.0)
    for p in ex:
        hit = g.nearest((p["x"], p["y"]), 2000)
        d = hit[0] if hit else float("inf")
        if d > lim:
            r.add(finding("EXT_POLE_FAR_FROM_REF", "ERROR", "Tiang existing %s berjarak %.1f m dari tiang referensi terdekat (> %.0f m)"
                          % (p["name"], d, lim), _pt(p), "POLE", p["name"], round(d, 1) if d != float("inf") else None, lim,
                          "geser ke tiang existing sebenarnya atau ubah menjadi tiang baru", scope=p.get("scope", ""), unit="m",
                          source=ref_src))
    r.stats["dicek"] = "%d tiang existing vs %d tiang referensi (%s)" % (len(ex), len(ref_pts), ref_src)
    return r


# =============================================================================================
# QC-05 rasio pancingan & closure (per lingkup)
# =============================================================================================
def rule_ratio(kmz, prof, pr):
    r = RuleResult("QC05_RASIO", "Pancingan <= 15% panjang kabel 24C/48C; closure 96 <= 10% jumlah FAT AE (Distribution)", "-",
                   "QC-05", "INTERNAL", "Aturan QC operasional slide 4")
    if kmz is None or "kmz" not in kmz.has:
        return r.unverify("butuh KMZ APD (klasifikasi menurut folder)")
    scopes = {c.get("scope") for c in kmz.cables} | {c.get("scope") for c in kmz.closures}
    sc = "DISTRIBUTION" if "DISTRIBUTION" in scopes else ""

    def in_sc(o):
        return (o.get("scope") or "") == sc or (sc and not o.get("scope"))
    lim_p, lim_c = pv(prof, "pancingan_max_pct", 15.0), pv(prof, "closure96_max_pct", 10.0)
    panc = [c for c in kmz.cables if c["kind"] == "pancingan" and in_sc(c)]
    base = [c for c in kmz.cables if in_sc(c) and c["kind"] not in ("pancingan", "annot") and c.get("nominal_core") in (24, 48)
            and c.get("status") != "EXISTING" and re.search(r"new\s*cable\s*(24|48)\s*c", _path(c))]
    Lp = sum(line_len(c["pts"], pr) for c in panc)
    Lb = sum(line_len(c["pts"], pr) for c in base)
    if Lb <= 0:
        r.notes.append("Tidak ada kabel di folder New Cable 24C/48C lingkup %s: rasio pancingan tidak dapat dihitung." % (sc or "-"))
    else:
        pct = 100.0 * Lp / Lb
        r.stats["pancingan"] = "%.1f m / %.1f m = %.2f%% (batas %.0f%%)" % (Lp, Lb, pct, lim_p)
        if pct > lim_p:
            r.add(finding("PANCINGAN_RATIO_OVER", "ERROR", "Pancingan %.1f m = %.2f%% dari kabel 24C/48C %.1f m (> %.0f%%)"
                          % (Lp, pct, Lb, lim_p), ("line", panc[0]["pts"]) if panc else None, "KABEL", "pancingan", round(pct, 2),
                          lim_p, "kurangi pancingan dengan memilih jalur/tiang lain", scope=sc, unit="%"))
    dv = devices(kmz)
    fat_ae = [n for n in dv["fat_ae"] if in_sc(n)]
    clo = [c for c in dv["clos96_new"] if in_sc(c)]
    other = [c for c in dv["clos96_new"] if not in_sc(c)]
    if not fat_ae:
        r.notes.append("Tidak ada FAT AE di lingkup %s: rasio closure tidak dapat dihitung." % (sc or "-"))
    else:
        pct = 100.0 * len(clo) / len(fat_ae)
        r.stats["closure"] = "%d closure 96 / %d FAT AE = %.2f%% (batas %.0f%%)%s" % (
            len(clo), len(fat_ae), pct, lim_c, ("; %d closure lingkup lain tidak dihitung" % len(other)) if other else "")
        if pct > lim_c:
            r.add(finding("CLOSURE_RATIO_OVER", "ERROR", "Closure 96 baru %d = %.2f%% dari %d FAT AE (> %.0f%%)" % (len(clo), pct, len(fat_ae), lim_c),
                          _pt(clo[0]) if clo else None, "CLOSURE", "closure 96", round(pct, 2), lim_c,
                          "kurangi closure dengan memilih rute/percabangan lain", scope=sc, unit="%"))
    if not r.stats and not r.findings:
        r.unverify("UNVERIFIED: penyebut rasio nol (tidak ada kabel 24C/48C atau FAT AE)")
    return r


# =============================================================================================
# QC-06 tiang pada perangkat
# =============================================================================================
def rule_device_pole(kmz, prof, pr, extra_poles=()):
    r = RuleResult("QC06_TIANG_PERANGKAT", "FDT baru, FAT AE, closure 96 baru berdiri di tiang", "3", "QC-06", "INTERNAL",
                   "Aturan QC operasional slide 4; Handbook kasus 3 (FAT melayang)")
    if kmz is None:
        return r.unverify("butuh KMZ APD")
    poles = list(kmz.poles) + list(extra_poles)
    tol = pv(prof, "device_pole_m", 2.0)
    dv = devices(kmz)
    items = [("FDT", n) for n in dv["fdt_new"]] + [("FAT", n) for n in dv["fat_ae"]] + [("CLOSURE", c) for c in dv["clos96_new"]]
    if not items:
        return r.unverify("tidak ada perangkat di folder New FDT / New FAT AE / New Closure 96")
    if not poles:
        return r.unverify("UNVERIFIED: data tiang tidak ada di KMZ")
    g = Grid([((p["x"], p["y"]), p) for p in poles], pr, 25.0)
    pole_scopes = {p.get("scope") for p in poles}
    unv = []
    for kind, o in items:
        sc = o.get("scope", "")
        pk = (o.get("packages") or {sc}) - {""}
        if pk and not (pk & pole_scopes) and "" not in pole_scopes:
            unv.append("%s %s (lingkup %s tanpa data tiang)" % (kind, o.get("name"), sc))
            continue
        hit = g.nearest((o["x"], o["y"]), 500)
        d = hit[0] if hit else float("inf")
        if d > tol:
            r.add(finding("DEVICE_WITHOUT_POLE", "ERROR", "%s %s tidak berdiri di tiang: tiang terdekat %.1f m (> %.1f m)"
                          % (kind, o.get("name"), d, tol), _pt(o), kind, o.get("name"), round(d, 1) if d != float("inf") else None,
                          tol, "letakkan perangkat di titik tiang atau tambah tiang", scope=sc, unit="m"))
    if unv:
        r.notes.append("Belum dapat dicek (data tiang lingkup tersebut belum ada): " + "; ".join(unv))
        if not r.findings:
            # sebagian perangkat belum dapat dicek -> jangan tampil PASS (pengguna mengira semua aman)
            r.unverify("UNVERIFIED: %d dari %d perangkat OK di tiang; belum dapat dicek: %s"
                       % (len(items) - len(unv), len(items), "; ".join(unv)))
    r.stats["dicek"] = "%d perangkat, %d belum dapat dicek" % (len(items) - len(unv), len(unv))
    return r


# =============================================================================================
# QC-07 pancingan harus bertumpu pada tiang
# =============================================================================================
def rule_pancingan(kmz, prof, pr):
    r = RuleResult("QC07_PANCINGAN", "Ujung pancingan bertumpu pada tiang", "25", "QC-07", "INTERNAL",
                   "Aturan QC operasional slide 5 (pancingan ada pole; pole tidak nganggur)")
    if kmz is None:
        return r.unverify("butuh KMZ APD")
    panc = [c for c in kmz.cables if c["kind"] == "pancingan"]
    if not panc:
        r.notes.append("Tidak ada pancingan di desain.")
        return r
    if not kmz.poles:
        return r.unverify("UNVERIFIED: data tiang tidak ada")
    tol = pv(prof, "pancingan_pole_m", 3.0)
    g = Grid([((p["x"], p["y"]), p) for p in kmz.poles], pr, 25.0)
    for c in panc:
        for end, p in (("awal", c["pts"][0]), ("akhir", c["pts"][-1])):
            hit = g.nearest(p, 500)
            d = hit[0] if hit else float("inf")
            if d > tol:
                r.add(finding("PANCINGAN_END_NO_POLE", "ERROR", "Ujung %s pancingan '%s' (%.1f m) tidak di tiang: tiang terdekat %.1f m"
                              % (end, c.get("name") or "-", line_len(c["pts"], pr), d), ("point", p), "KABEL", c.get("name"),
                              round(d, 1) if d != float("inf") else None, tol, "tambahkan tiang penyangga pancingan",
                              scope=c.get("scope", ""), unit="m"))
    return r


def run_paket(main, kmz, prof, codes=None, splice=None, master=None, master_src="", ref_pts=None, ref_src="", dl_codes=None,
              autodesign=None):
    """Jalankan QC-01..QC-07. main = data gabungan (ekspor + KMZ), kmz = data KMZ APD (semantik folder)."""
    pr = main.proj()
    out = []
    for fn, args in ((rule_fdt_code, (main, kmz, prof, pr, master, master_src, dl_codes)),
                     (rule_premises_splitter, (main, kmz, prof, pr, codes, splice)),
                     (rule_properties, (main, kmz, prof, pr, codes, autodesign)),
                     (rule_pole_reference, (kmz, prof, pr, ref_pts, ref_src)),
                     (rule_ratio, (kmz, prof, pr)),
                     (rule_device_pole, (kmz, prof, pr)),
                     (rule_pancingan, (kmz, prof, pr))):
        try:
            out.append(fn(*args))
        except Exception as e:  # satu aturan gagal tidak menggagalkan yang lain
            rr = RuleResult(fn.__name__.replace("rule_", "QC_").upper(), fn.__name__)
            rr.unverify("aturan gagal dijalankan: %s" % e)
            out.append(rr)
    return out

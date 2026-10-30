# -*- coding: utf-8 -*-
"""
Seranta - FTTH Design Assistant
Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-2.0-or-later.

CEK TAMBAHAN ALAT 1 (versi 3.6.0) - dari review lapangan Jambi, Tegal dan Minahasa (Oktober 2026)
---------------------------------------------------------------------------------------------------
Modul murni Python (tanpa QGIS) agar bisa diuji otomatis:
  * foto evidence per HP (file *Evidence*.xlsx aplikasi survei dan/atau sub-folder EVIDENCE di KMZ);
  * sheet daftar tiang di HPDB ('Pole') dibandingkan dengan tiang di KMZ (jumlah, posisi, tinggi, baris ganda);
  * penulisan nomor baris ringkas (6-8, 10-16, 60).
Remarks otomatis ada di remarks.py.
"""
import math
import re

try:
    from . import geodesi as _geo
except ImportError:          # diuji tanpa paket
    import geodesi as _geo

ID_RX = re.compile(r"(?<!\d)(\d{9,12})(?!\d)")


def dist_m(x1, y1, x2, y2):
    return _geo.dist_m(x1, y1, x2, y2)


def rows_compact(nums, max_items=8):
    """[6, 7, 8, 10, 11, 12, 60] -> '6-8, 10-12, 60' (maks max_items potongan, sisanya '+N')."""
    v = sorted({int(n) for n in nums if n is not None})
    if not v:
        return ""
    parts, a, b = [], v[0], v[0]
    for n in v[1:]:
        if n == b + 1:
            b = n
            continue
        parts.append((a, b))
        a = b = n
    parts.append((a, b))
    txt = ["%d" % a if a == b else ("%d, %d" % (a, b) if b == a + 1 else "%d-%d" % (a, b)) for a, b in parts]
    if len(txt) > max_items:
        rest = sum((b - a + 1) for a, b in parts[max_items:])
        return ", ".join(txt[:max_items]) + " +%d" % rest
    return ", ".join(txt)


def _norm_h(s):
    return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())


def _num(v):
    try:
        return float(str(v).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------------------------------- evidence
def evidence_from_sheets(sheets):
    """Laporan evidence aplikasi survei (kolom 'Identitas (ID/No)' dan 'Koordinat' berisi 'lat,\\nlon', atau kolom
    LATITUDE/LONGITUDE terpisah). -> [(x, y, label)]"""
    out = []
    for _name, rows in sheets or []:
        hi = None
        for i, r in enumerate(rows[:30]):
            hn = [_norm_h(c) for c in r]
            if any(c.startswith("KOORDINAT") or c == "COORDINATE" or c == "COORDINATES" for c in hn) or (
                    any("LATITUDE" in c for c in hn) and any("LONGITUDE" in c for c in hn)):
                hi = i
                break
        if hi is None:
            continue
        hn = [_norm_h(c) for c in rows[hi]]
        ik = next((i for i, c in enumerate(hn) if c.startswith("KOORDINAT") or c.startswith("COORDINATE")), None)
        ilat = next((i for i, c in enumerate(hn) if "LATITUDE" in c), None)
        ilon = next((i for i, c in enumerate(hn) if "LONGITUDE" in c), None)
        iid = next((i for i, c in enumerate(hn) if c.startswith("IDENTITAS") or c in ("ID", "NAMA", "NAME", "LABEL")
                    or "HOUSENUMBER" in c), None)
        for r in rows[hi + 1:]:
            if not r:
                continue

            def g(i):
                return r[i] if i is not None and i < len(r) else ""
            lat = lon = None
            if ik is not None:
                v = [t for t in re.split(r"[,;\s]+", str(g(ik)).strip()) if t]
                if len(v) >= 2:
                    lat, lon = _num(v[0]), _num(v[1])
            if (lat is None or lon is None) and ilat is not None and ilon is not None:
                lat, lon = _num(g(ilat)), _num(g(ilon))
            if lat is None or lon is None:
                continue
            if -11.5 <= lon <= 6.5 and 94 <= lat <= 141.5:
                lat, lon = lon, lat
            if not (-11.5 <= lat <= 6.5 and 94 <= lon <= 141.5):
                continue
            out.append((lon, lat, str(g(iid) or "").strip()))
    return out


def evidence_missing(hps, evs, near_m=5.0, label_m=30.0, norm=None):
    """hps: [dict(x, y, hn, row)], evs: [(x, y, label)]. Satu foto evidence dipakai satu HP saja.
    HP punya evidence bila ada titik foto <= near_m, atau label sama (ternormal) <= label_m. -> [hp tanpa evidence]"""
    norm = norm or (lambda v: re.sub(r"[^A-Z0-9]", "", str(v or "").upper()).lstrip("0"))
    if not evs:
        return []
    cell = _geo.cell_deg(max(near_m, label_m), [e[1] for e in evs] + [h["y"] for h in hps])
    g = {}
    for j, (x, y, _l) in enumerate(evs):
        g.setdefault(_geo.cell_of(x, y, cell), []).append(j)
    used, miss = set(), []
    cand = []
    for i, h in enumerate(hps):
        cx, cy = _geo.cell_of(h["x"], h["y"], cell)
        hl = norm(h.get("hn"))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in g.get((cx + dx, cy + dy), ()):
                    x, y, lab = evs[j]
                    d = dist_m(h["x"], h["y"], x, y)
                    same = bool(hl) and hl == norm(lab)
                    if d <= near_m or (same and d <= label_m):
                        cand.append((0 if same else 1, d, i, j))
    cand.sort()
    got = set()
    for _r, _d, i, j in cand:
        if i in got or j in used:
            continue
        got.add(i)
        used.add(j)
    for i, h in enumerate(hps):
        if i not in got:
            miss.append(h)
    return miss


# ------------------------------------------------------------------------------------------- sheet tiang
POLE_SHEET_RX = re.compile(r"pole|tiang", re.IGNORECASE)


def pole_sheet(sheets, skip_name=None):
    """Sheet daftar tiang di HPDB (nama sheet memuat POLE/TIANG, atau kolom 'ID Tiang'), dengan kolom LATITUDE dan
    LONGITUDE. -> (nama_sheet, [dict(no, id, x, y, row)]) atau (None, [])"""
    for name, rows in sheets or []:
        if skip_name is not None and name == skip_name:
            continue
        for i, r in enumerate(rows[:15]):
            hn = [_norm_h(c) for c in r]
            if not (any("LATITUDE" in c for c in hn) and any("LONGITUDE" in c for c in hn)):
                continue
            if not (POLE_SHEET_RX.search(name or "") or any(c in ("IDTIANG", "IDPOLE", "POLEID", "TIANG", "NAMATIANG")
                                                            for c in hn)):
                break
            ilat = next(k for k, c in enumerate(hn) if "LATITUDE" in c)
            ilon = next(k for k, c in enumerate(hn) if "LONGITUDE" in c)
            ino = next((k for k, c in enumerate(hn) if c in ("NO", "NOMOR", "NUMBER")), None)
            iid = next((k for k, c in enumerate(hn) if c in ("IDTIANG", "IDPOLE", "POLEID", "TIANG", "NAMATIANG", "NAME",
                                                             "NAMA")), None)
            out = []
            for j, rr in enumerate(rows[i + 1:], start=i + 2):
                if not rr or not any(str(v).strip() for v in rr):
                    continue
                lat = _num(rr[ilat]) if ilat < len(rr) else None
                lon = _num(rr[ilon]) if ilon < len(rr) else None
                if lat is None or lon is None:
                    continue
                if -11.5 <= lon <= 6.5 and 94 <= lat <= 141.5:
                    lat, lon = lon, lat
                no = str(rr[ino]).strip() if ino is not None and ino < len(rr) else ""
                no = no[:-2] if no.endswith(".0") else no
                out.append({"no": no or str(j), "id": str(rr[iid]).strip() if iid is not None and iid < len(rr) else "",
                            "x": lon, "y": lat, "row": j})
            if out:
                return name, out
            break
    return None, []


def pole_sheet_compare(sheet_poles, kmz_poles, height_fn, move_m=5.0, dup_m=0.5):
    """sheet_poles: hasil pole_sheet; kmz_poles: [(x, y, tinggi_m atau None)].
    -> dict(n_sheet, n_kmz, moved=[(no, d)], hdiff=[(no, tinggi_sheet, tinggi_kmz)], dup=[(no_a, no_b)])"""
    res = {"n_sheet": len(sheet_poles), "n_kmz": len(kmz_poles), "moved": [], "hdiff": [], "dup": []}
    for a in range(len(sheet_poles)):
        for b in range(a + 1, len(sheet_poles)):
            pa, pb = sheet_poles[a], sheet_poles[b]
            if dist_m(pa["x"], pa["y"], pb["x"], pb["y"]) <= dup_m:
                res["dup"].append((pa["no"], pb["no"]))
    if not kmz_poles:
        return res
    for sp in sheet_poles:
        best = min(kmz_poles, key=lambda k: dist_m(sp["x"], sp["y"], k[0], k[1]))
        d = dist_m(sp["x"], sp["y"], best[0], best[1])
        if d > move_m:
            res["moved"].append((sp["no"], d))
            continue
        hs = height_fn(sp["id"])
        # tiang berimpit di KMZ (dua catatan satu lokasi): cocok bila salah satunya sama tinggi
        hk = {k[2] for k in kmz_poles if dist_m(sp["x"], sp["y"], k[0], k[1]) <= max(dup_m, d + 0.05) and k[2]}
        if hs and hk and hs not in hk:
            res["hdiff"].append((sp["no"], hs, sorted(hk)[0]))
    return res

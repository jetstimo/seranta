# -*- coding: utf-8 -*-
"""
Seranta - FTTH Design Assistant
Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later.

KONSISTENSI DATA SURVEI (3.10.0)
--------------------------------
Pemeriksaan kecil yang dulu lolos karena setiap berkas dinilai sendiri-sendiri (review strand Jambi Suka Karya,
5 Nov 2026, 13 cluster RT):
  * poligon BOUNDARY yang memotong dirinya sendiri (KOTA RT 04): luas irisan dan uji 'HP di dalam BOUNDARY' memakai
    aturan genap-ganjil sehingga bagian yang terlipat bisa terbaca 'di luar';
  * CLUSTER_NAME / RT yang tidak seragam di satu HPDB (RT 04 memuat 15 HP 'SUKA KARYA RT 12'; RT 08 memuat 6 HP
    'SUKA KARYA RT16' pindahan dari RT 16 tanpa label diperbarui);
  * jumlah HP di nama berkas (BAKP/TSSR/KMZ/HPDB) yang tidak diperbarui setelah revisi;
  * kolom wilayah sheet tiang yang tertukar (KECAMATAN berisi nama kelurahan), yang dulu dicocokkan ke FINDIM dan
    menghasilkan wilayah jauh ('Kabupaten Kerinci').
Modul ini murni Python (tanpa QGIS) agar bisa diuji otomatis; semua fungsi deterministik (urutan hasil tetap).
"""
import os
import re

# ----------------------------------------------------------------------------------------- BOUNDARY
def _outer(poly):
    """Cincin luar dari poligon format lintas_cluster ([cincin_luar, lubang...]) atau cincin langsung."""
    if poly and isinstance(poly[0], (list, tuple)) and poly[0] and isinstance(poly[0][0], (list, tuple)):
        return poly[0]
    return poly


def _clean_ring(ring):
    pts = []
    for p in ring or []:
        q = (float(p[0]), float(p[1]))
        if not pts or abs(q[0] - pts[-1][0]) > 1e-12 or abs(q[1] - pts[-1][1]) > 1e-12:
            pts.append(q)
    if len(pts) > 1 and abs(pts[0][0] - pts[-1][0]) <= 1e-12 and abs(pts[0][1] - pts[-1][1]) <= 1e-12:
        pts.pop()
    return pts


def _seg_cross(a, b, c, d):
    """Titik potong ruas ab dan cd yang benar-benar saling silang (bukan hanya bersentuhan di ujung); None bila tidak."""
    r = (b[0] - a[0], b[1] - a[1])
    s = (d[0] - c[0], d[1] - c[1])
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < 1e-18:
        return None                                   # sejajar/berimpit: bukan silang (ditangani sebagai titik ganda)
    t = ((c[0] - a[0]) * s[1] - (c[1] - a[1]) * s[0]) / den
    u = ((c[0] - a[0]) * r[1] - (c[1] - a[1]) * r[0]) / den
    eps = 1e-9
    if eps < t < 1 - eps and eps < u < 1 - eps:
        return (a[0] + t * r[0], a[1] + t * r[1])
    return None


def ring_self_intersections(ring, max_report=20):
    """Titik tempat cincin poligon memotong dirinya sendiri -> [(x, y)] urut (x, y). Ruas bersebelahan diabaikan."""
    pts = _clean_ring(ring)
    n = len(pts)
    if n < 4:
        return []
    segs = [(pts[i], pts[(i + 1) % n]) for i in range(n)]
    # grid sederhana (sel ~ panjang ruas median) agar tetap cepat untuk poligon ribuan titik
    lens = sorted(abs(b[0] - a[0]) + abs(b[1] - a[1]) for a, b in segs)
    cell = max(lens[len(lens) // 2], 1e-7) * 2.0
    grid = {}
    for i, (a, b) in enumerate(segs):
        for gx in range(int(min(a[0], b[0]) // cell), int(max(a[0], b[0]) // cell) + 1):
            for gy in range(int(min(a[1], b[1]) // cell), int(max(a[1], b[1]) // cell) + 1):
                grid.setdefault((gx, gy), []).append(i)
    found = set()
    for idx in grid.values():
        for ii in range(len(idx)):
            for jj in range(ii + 1, len(idx)):
                i, j = idx[ii], idx[jj]
                if abs(i - j) <= 1 or abs(i - j) == n - 1:
                    continue                          # ruas bersebelahan berbagi satu titik
                p = _seg_cross(segs[i][0], segs[i][1], segs[j][0], segs[j][1])
                if p:
                    found.add((round(p[0], 7), round(p[1], 7)))
    return sorted(found)[:max_report]


def boundary_problems(bnd):
    """-> [(x, y, keterangan)] untuk setiap poligon BOUNDARY yang memotong dirinya sendiri."""
    out = []
    for k, poly in enumerate(bnd or []):
        xs = ring_self_intersections(_outer(poly))
        if xs:
            out.append((xs[0][0], xs[0][1], k, xs))
    return out


# ----------------------------------------------------------------------------------------- NAMA CLUSTER
def norm_cluster_name(v):
    """'SUKA KARYA RT16' / 'Suka Karya  RT 016' -> 'SUKA KARYA RT 16' (format diabaikan, isi dibandingkan)."""
    s = re.sub(r"[^A-Z0-9]+", " ", str(v or "").upper())
    s = re.sub(r"(?<=[A-Z])(?=\d)|(?<=\d)(?=[A-Z])", " ", s)
    s = re.sub(r"\b0+(\d)", r"\1", s)
    return " ".join(s.split())


def _rt_of(name):
    m = re.search(r"\b(RT|RW|LK|LINGKUNGAN|DUSUN|BLOK)\s+(\d+)\b", norm_cluster_name(name))
    return ("%s %s" % (m.group(1), m.group(2))) if m else ""


def rows_txt(rows, max_items=6):
    v = sorted({int(r) for r in rows if r})
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
    t = ["%d" % a if a == b else ("%d, %d" % (a, b) if b == a + 1 else "%d-%d" % (a, b)) for a, b in parts]
    return ", ".join(t[:max_items]) + (" dst" if len(t) > max_items else "")


def label_mix(names, rows, rt_values=None, own_label="", sib_labels=()):
    """Keseragaman CLUSTER_NAME satu HPDB.
    names: nilai CLUSTER_NAME per baris HP; rows: nomor baris HPDB asli; rt_values: kolom RT per baris (boleh None);
    own_label: nama folder/cluster ini; sib_labels: nama cluster saudara (untuk mengenali HP pindahan).
    -> dict(major=(nama, n), minor=[dict(name, norm, n, rows, rt, sibling)], format_only=[variasi penulisan], n=total)
       minor kosong bila seragam (variasi penulisan saja masuk format_only)."""
    groups, raw = {}, {}
    for i, v in enumerate(names):
        v = str(v or "").strip()
        if not v or v == "-":
            continue
        k = norm_cluster_name(v)
        groups.setdefault(k, []).append(i)
        raw.setdefault(k, {}).setdefault(v, 0)
        raw[k][v] += 1
    res = {"major": None, "minor": [], "format_only": [], "n": sum(len(v) for v in groups.values())}
    if not groups:
        return res
    own_n = norm_cluster_name(own_label)
    own_rt = _rt_of(own_label)

    def own_score(k):
        # cluster pemilik: nama yang RT-nya sama dengan nama folder cluster, lalu yang terbanyak
        return (bool(own_rt) and _rt_of(k) == own_rt, bool(own_n) and (k in own_n or own_n in k), len(groups[k]), k)
    major = max(groups, key=own_score)
    res["major"] = (max(raw[major], key=lambda s: (raw[major][s], s)), len(groups[major]))
    for k, v in raw.items():
        if len(v) > 1:
            res["format_only"].append(sorted(v))
    sib_map = {}
    for s in sib_labels or ():
        rt = _rt_of(s)
        if rt:
            sib_map.setdefault(rt, s)
    for k in sorted(groups, key=lambda k: (-len(groups[k]), k)):
        if k == major:
            continue
        idx = groups[k]
        rts = sorted({str(rt_values[i]).strip() for i in idx if rt_values and str(rt_values[i]).strip() not in ("", "-")})
        rt_k = _rt_of(k)
        res["minor"].append({"name": max(raw[k], key=lambda s: (raw[k][s], s)), "norm": k, "n": len(idx),
                             "rows": [rows[i] for i in idx], "rt": rts,
                             "sibling": sib_map.get(rt_k, "") if rt_k and rt_k != own_rt else ""})
    return res


def label_mix_text(mix):
    """Kalimat temuan dari label_mix (satu kalimat per label minoritas) -> [(teks, n, rows)]."""
    out = []
    if not mix or not mix["minor"]:
        return out
    maj, n_maj = mix["major"]
    for m in mix["minor"]:
        rt_txt = ""
        if m["rt"]:
            rt_txt = "; kolom RT baris itu = %s" % ", ".join(m["rt"][:3])
        rt_k = _rt_of(m["norm"])
        if m["sibling"]:
            why = (" Label ini nama cluster saudara %s: kemungkinan HP pindahan dari %s yang labelnya belum diperbarui."
                   % (m["sibling"], m["sibling"]))
        elif rt_k and rt_k != _rt_of(maj):
            why = (" %s tidak ada di cluster saudara yang dibandingkan: pastikan HP ini tidak juga diajukan di cluster %s."
                   % (rt_k, rt_k))
        else:
            why = ""
        out.append(("%d HP CLUSTER_NAME '%s' (baris %s), mayoritas %d HP '%s'%s.%s Samakan CLUSTER_NAME sesuai cluster "
                    "pemilik; bila HP memang milik cluster lain, keluarkan dari HPDB ini." % (
                        m["n"], m["name"], rows_txt(m["rows"]), n_maj, maj, rt_txt, why), m["n"], m["rows"]))
    return out


# ----------------------------------------------------------------------------------------- NAMA BERKAS
HP_IN_NAME_RX = re.compile(r"(?<![A-Za-z0-9])(\d{1,4})\s*_?\s*HP(?![A-Za-z])", re.IGNORECASE)


def hp_in_name(path):
    """Jumlah HP di nama berkas/folder ('..._62HP_..', '(38HP)', '56 HP') -> int atau None (diambil yang terakhir)."""
    nm = os.path.splitext(os.path.basename(str(path or "")))[0]
    m = HP_IN_NAME_RX.findall(nm)
    return int(m[-1]) if m else None


def filename_hp_mismatch(files, n_hp):
    """files: [(peran, path)]. -> [(peran, nama_berkas, hp_di_nama)] yang beda dengan n_hp (urut peran)."""
    out = []
    for role, p in files or []:
        if not p:
            continue
        v = hp_in_name(p)
        if v is not None and n_hp and v != n_hp:
            out.append((role, os.path.basename(p), v))
    return sorted(out)


# ----------------------------------------------------------------------------------------- WILAYAH SHEET LAIN
def _n(s):
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", str(s or "").upper()).split())


def admin_vs_hp_sheet(other, hp):
    """Bandingkan wilayah sheet lain (kel, kec, kota) dengan wilayah sheet homepass (yang sudah dicek ke FINDIM).
    -> (status, teks): 'SAMA' / 'TERTUKAR' (isi kolom kelurahan/kecamatan/kota tertukar) / 'BEDA' / '' (tak bisa dinilai)."""
    o = [_n(x) for x in other[:3]]
    h = [_n(x) for x in hp[:3]]
    if not any(h) or not any(o):
        return "", ""
    if o == h:
        return "SAMA", ""
    cols = ("KELURAHAN", "KECAMATAN", "KOTA")
    moved = []
    for i, v in enumerate(o):
        if v and v != h[i] and v in h:
            j = h.index(v)
            moved.append("%s berisi '%s' (= %s di sheet homepass)" % (cols[i], other[i], cols[j]))
    if moved:
        return "TERTUKAR", "kolom wilayah tertukar: " + "; ".join(moved) + \
            " - sheet homepass: kelurahan '%s', kecamatan '%s'" % (hp[0], hp[1])
    diff = ["%s '%s' (sheet homepass '%s')" % (cols[i], other[i], hp[i]) for i in range(3) if o[i] and h[i] and o[i] != h[i]]
    return ("BEDA", "beda dengan sheet homepass: " + ", ".join(diff)) if diff else ("SAMA", "")


# ----------------------------------------------------------------------------------------- RT / RW HPDB vs WILAYAH
# 3.14.1 (masukan pengguna: "di HPDB nama RT-nya berbeda dengan wilayahnya, mis. seharusnya RT 17 tetapi tertulis RT 24").
# Dua pembanding, keduanya tanpa data luar:
#   1. nama wilayah resmi cluster (nama Funnel cluster ini, atau nama folder cluster): 'LINGKUNGAN 5 GESEL', 'RW 05',
#      'RT 17', 'LINGKUNGAN 1&2', 'LINGKUNGAN 1-7', 'LINGKUNGAN I-IV' -> kolom RT / RW-Lingkungan dan CLUSTER_NAME tiap
#      baris HPDB harus berada di dalam nomor itu;
#   2. tetangga terdekat: rumah ber-RT 24 yang dikelilingi rumah RT 17 (radius 60 m) hampir pasti salah ketik / salah
#      salin. Rumah di satu RT berdekatan; batas RT jarang memotong deret rumah yang rapat.
# Kolom kosong, '-', '0' atau '00' = tidak diisi (wajar di daerah tanpa RT, mis. kelurahan ber-lingkungan di Sulawesi Utara).
_ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10, "XI": 11,
          "XII": 12, "XIII": 13, "XIV": 14, "XV": 15, "XVI": 16, "XVII": 17, "XVIII": 18, "XIX": 19, "XX": 20}
_NUM = r"(?:\d{1,3}|[IVX]{1,5})"
_AREA_RX = re.compile(r"\b(RT|RW|LINGKUNGAN|LINGK|LK|DUSUN|DSN)\s*\.?\s*(%s(?:\s*(?:&|,|-|DAN|S/D|SD)\s*%s)*)(?![A-Z0-9])"
                      % (_NUM, _NUM))
RW_KEYS = ("RW", "LINGKUNGAN", "LINGK", "LK", "DUSUN", "DSN")


def _num(tok):
    tok = tok.strip()
    if tok.isdigit():
        return int(tok)
    return _ROMAN.get(tok)


def parse_numbers(v):
    """'01&2' -> {1, 2}; '3-4' / 'I-IV' -> rentang; '-', '0', '00', '' -> set() (tidak diisi)."""
    s = str(v or "").upper().replace("S/D", "-").replace(" SD ", "-").replace(" DAN ", "&")
    out = set()
    for part in re.split(r"[&,/]", s):
        rng = [x for x in re.split(r"\s*-\s*", part.strip()) if x]
        nums = [n for n in (_num(x) for x in rng) if n is not None]
        if len(nums) == 2 and len(rng) == 2 and 0 < nums[1] - nums[0] <= 30:
            out.update(range(nums[0], nums[1] + 1))
        else:
            out.update(nums)
    out.discard(0)
    return out


def area_ref(label):
    """Nomor wilayah di nama cluster/Funnel -> {'RT': set, 'RW': set} (RW mencakup RW/Lingkungan/Dusun)."""
    s = re.sub(r"[_]+", " ", str(label or "").upper())
    res = {"RT": set(), "RW": set()}
    for key, nums in _AREA_RX.findall(s):
        res["RT" if key == "RT" else "RW"] |= parse_numbers(nums)
    return res


def _fmt(nums):
    v = sorted(nums)
    if len(v) > 2 and v == list(range(v[0], v[-1] + 1)):
        return "%d-%d" % (v[0], v[-1])
    return "&".join(str(n) for n in v)


def area_mismatch(ref_label, ref_src, rows, rt_vals, rw_vals, cn_vals):
    """Baris HPDB yang RT / RW-Lingkungan / CLUSTER_NAME-nya di luar nomor wilayah nama cluster.
    -> [dict(col, value, n, rows, idx, expect, text)] (satu per kolom & nilai)."""
    ref = area_ref(ref_label)
    out = []

    def scan(col, vals, want, what):
        if not want or not vals:
            return
        grp = {}
        for i, v in enumerate(vals):
            got = parse_numbers(v)
            if got and not got <= want:
                grp.setdefault(str(v).strip(), []).append(i)
        for v, idx in sorted(grp.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            out.append({"col": col, "value": v, "n": len(idx), "rows": [rows[i] for i in idx], "idx": idx,
                        "expect": "%s %s" % (what, _fmt(want)),
                        "text": "%d HP kolom %s = '%s' (baris %s), seharusnya %s %s sesuai %s '%s'" % (
                            len(idx), col, v, rows_txt([rows[i] for i in idx]), what, _fmt(want), ref_src, ref_label)})
    scan("RT", rt_vals, ref["RT"], "RT")
    scan("RW/lingkungan", rw_vals, ref["RW"], "RW/lingkungan")
    if cn_vals:
        grp = {}
        for i, v in enumerate(cn_vals):
            a = area_ref(v)
            bad = (a["RT"] and ref["RT"] and not a["RT"] <= ref["RT"]) or (a["RW"] and ref["RW"] and not a["RW"] <= ref["RW"])
            if bad:
                grp.setdefault(str(v).strip(), []).append(i)
        for v, idx in sorted(grp.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            want = " ".join(x for x in (("RT " + _fmt(ref["RT"])) if ref["RT"] else "",
                                        ("RW/lingkungan " + _fmt(ref["RW"])) if ref["RW"] else "") if x)
            out.append({"col": "CLUSTER_NAME", "value": v, "n": len(idx), "rows": [rows[i] for i in idx], "idx": idx,
                        "expect": want, "text": "%d HP kolom CLUSTER_NAME = '%s' (baris %s), seharusnya %s sesuai %s '%s'" % (
                            len(idx), v, rows_txt([rows[i] for i in idx]), want, ref_src, ref_label)})
    return out


def neighbour_odd(xy_m, vals, radius_m=60.0, k=6, min_nb=4, share=0.8):
    """Rumah yang nomor RT/RW-nya berbeda dengan hampir semua tetangga terdekatnya.
    xy_m: [(x, y)] dalam meter; vals: nilai kolom per HP. Hanya nilai satu nomor yang dinilai.
    -> [(i, nilai_sendiri, nilai_mayoritas, n_mayoritas, n_tetangga)]"""
    nums = []
    for v in vals:
        p = parse_numbers(v)
        nums.append(next(iter(p)) if len(p) == 1 else None)
    if len({n for n in nums if n is not None}) < 2:
        return []
    cell = {}
    for i, (x, y) in enumerate(xy_m):
        cell.setdefault((int(x // radius_m), int(y // radius_m)), []).append(i)
    out = []
    for i, (x, y) in enumerate(xy_m):
        if nums[i] is None:
            continue
        cx, cy = int(x // radius_m), int(y // radius_m)
        nb = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in cell.get((cx + dx, cy + dy), []):
                    if j != i and nums[j] is not None:
                        d = ((xy_m[j][0] - x) ** 2 + (xy_m[j][1] - y) ** 2) ** 0.5
                        if d <= radius_m:
                            nb.append((d, j))
        nb = [j for _d, j in sorted(nb)[:k]]
        if len(nb) < min_nb:
            continue
        cnt = {}
        for j in nb:
            cnt[nums[j]] = cnt.get(nums[j], 0) + 1
        maj, n_maj = max(cnt.items(), key=lambda kv: (kv[1], -kv[0]))
        if maj != nums[i] and n_maj >= share * len(nb) and nums[i] not in cnt:
            out.append((i, nums[i], maj, n_maj, len(nb)))
    return out


def filename_area_mismatch(ref_label, files):
    """3.15.0: nomor RT/RW di NAMA BERKAS cluster (HPDB, KMZ, BAKP, TSSR, evidence) yang berbeda dari nama wilayah cluster.
    Kasus Pasir Putih RT 17 (Nov 2026): folder & HPDB 'RT 17', tetapi BAKP bernama '..._RT_023_...' -> BAKP/berkas milik
    wilayah lain ikut tersalin. files = [(jenis, nama_berkas)]. -> [(jenis, nama_berkas, 'RT 23', 'RT 17')]"""
    ref = area_ref(ref_label)
    out = []
    for kind, fn in files:
        got = area_ref(os.path.splitext(os.path.basename(str(fn)))[0])
        for key in ("RT", "RW"):
            if ref[key] and got[key] and not got[key] <= ref[key]:
                out.append((kind, os.path.basename(str(fn)), "%s %s" % (key, _fmt(got[key])), "%s %s" % (key, _fmt(ref[key]))))
    return out

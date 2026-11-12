# -*- coding: utf-8 -*-
"""
Seranta - FTTH Design Assistant
Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later.

REMARKS REVIEW OTOMATIS (maks. 255 karakter)
--------------------------------------------
Kolom remarks sistem review hanya menampung 255 karakter. Pola yang dipakai tim QC (review Jambi, Tegal, Minahasa
Oktober 2026):
  * status di depan: 'Reject:' / 'Approve dgn catatan:' / 'Approve';
  * temuan paling berat dulu, ditulis singkat dan bisa dicek ulang: NOMOR BARIS HPDB ASLI (bukan ID H00001 buatan
    Seranta), nama tiang di POLE.kmz, ID cluster lain;
  * temuan yang selisihnya di bawah galat ukur (rentang/ jarak HP lebih <= 1 m dari batas) TIDAK dijadikan alasan reject,
    cukup dicatat 'ukur ulang';
  * temuan yang sumbernya usang (FINDIM lama) tidak dijadikan alasan reject.
Modul murni Python agar bisa diuji otomatis. Masukan: daftar temuan (kode, keterangan, nilai, batas) dari alat 1.
"""
import re

MAX_LEN = 255
MARGIN_M = 1.0          # selisih <= 1 m dari batas: di bawah galat GPS ponsel (4,9 m) -> catatan, bukan alasan reject

# Peringatan yang dianggap menghalangi persetujuan (satu rumah/tiang di dua cluster)
BLOCKING_WARN = {"WARN_BOUNDARY_BERIRISAN_CLUSTER_LAIN", "WARN_TIANG_GANDA_LINTAS_CLUSTER", "WARN_ID_CLUSTER_GANDA",
                 # 3.13.0: percabangan kabel di antara tiang = sambungan tergantung di bentang; sambungan (splice closure)
                 # dipasang di tiang (Fiber Optic Association, Aerial Workmanship)
                 "WARN_SIMPANG_TANPA_TIANG"}

# 3.13.0: kode integritas jalur. Sebelum 3.13.0 ujung jalur & percabangan tanpa tiang tidak masuk remarks (hanya di
# QC_TEMUAN), sehingga jalur yang ujungnya tanpa tiang bisa lolos 'Approve'. Saklar profil route_integrity=false -> remarks
# identik 3.12.0.
ROUTE_KEYS = {"JALUR_TANPA_TIANG", "JALUR_TERPUTUS", "UJUNG_JALUR_TANPA_TIANG", "WARN_SIMPANG_TANPA_TIANG",
              "WARN_JALUR_TERPUTUS", "WARN_JALUR_BERSILANG_TANPA_TIANG", "WARN_JALUR_BERTUMPUK",
              "INFO_JALUR_TERSAMBUNG_LEWAT_SAUDARA", "COLO_TITIK_MASUK_TIDAK_DI_JALUR", "COLO_HP_TIDAK_TERJANGKAU_JALUR",
              "WARN_TIANG_LUAR_BOUNDARY", "WARN_JALUR_LUAR_BOUNDARY", "INFO_TIANG_JALUR_DI_BOUNDARY_SAUDARA"}

# Urutan prioritas (paling berat dulu). Kode yang tidak ada di sini tidak masuk remarks.
PRIORITY = [
    "CLUSTER_LAIN_DIGABUNG", "BOUNDARY_MEMUAT_CLUSTER_LAIN", "HP_DUPLIKAT_LINTAS_CLUSTER", "HP_DI_RFS_DONE", "HP_DI_RFS_EXTENSION", "HP_DI_FUNNEL_LAIN",
    "HP_DI_BOUNDARY_CLUSTER_LAIN", "WARN_BOUNDARY_BERIRISAN_CLUSTER_LAIN", "BAKP_HP_KURANG", "BAKP_STEMPEL_TTD_TEMPELAN_DIGITAL",
    "BAKP_ADA_GAMBAR_TEMPELAN", "BAKP_NAMA_FILE_ID_BEDA", "WARN_BAKP_ID_METADATA_BEDA", "BAKP_DIEDIT_APLIKASI_GRAFIS", "FUNNEL_SENDIRI_REJECT",
    "HP_LUAR_FUNNEL", "HP_LUAR_BOUNDARY", "HP_DI_AREA_TANPA_IZIN", "TIANG_DI_AREA_TANPA_IZIN", "HP_JAUH_DARI_TIANG", "RENTANG_NP_NP", "RENTANG_NP_EP",
    "JALUR_TANPA_TIANG", "JALUR_TERPUTUS", "UJUNG_JALUR_TANPA_TIANG", "WARN_SIMPANG_TANPA_TIANG",      # 3.13.0 integritas jalur
    "JALUR_MELINTAS_TOL", "JALUR_MELINTAS_REL",                                                          # 3.15.0 standar 10
    "HP_DUPLIKAT_KOORDINAT", "HP_DUPLIKAT_ID", "HP_DUPLIKAT_LABEL", "HP_HPDB_TIDAK_ADA_DI_KMZ", "HP_KMZ_TIDAK_ADA_DI_HPDB",
    "HP_SUDAH_ADA_DI_DESIGN_LITE", "TIANG_BARU_SUDAH_ADA", "WARN_TIANG_GANDA_LINTAS_CLUSTER", "WARN_ID_CLUSTER_GANDA",
    "ADMIN_", "WARN_TIANG_DUPLIKAT_KMZ", "WARN_BELOKAN_TANPA_TIANG", "WARN_JALUR_TERPUTUS", "WARN_JALUR_BERSILANG_TANPA_TIANG",
    "WARN_POLE_SHEET_BEDA_KMZ", "WARN_CLUSTER_NAME_KOSONG",
    "WARN_HPDB_CLUSTER_NAME_CAMPUR", "WARN_HPDB_RT_RW_TIDAK_SESUAI", "WARN_NAMA_BERKAS_WILAYAH_BEDA", "WARN_BOUNDARY_TIDAK_VALID",
    "WARN_JALUR_MELINTAS_JALAN_BESAR", "WARN_TIANG_DEKAT_JALAN_TOL", "WARN_TIANG_DEKAT_REL",
    "WARN_HP_KOORDINAT_BEDA_FOTO", "WARN_JALUR_LEWAT_AREA_TANPA_IZIN",
    "WARN_HP_TANPA_EVIDENCE", "TIANG_NGANGGUR", "WARN_HP_LABEL_SAMA", "WARN_HP_JAUH_LEWAT_JALUR", "WARN_HP_AKSES_DALAM", "HP_BERGESER", "WARN_ADMIN_ID_CLUSTER_TIDAK_TERDAFTAR",
    "WARN_ADMIN_KELURAHAN_BELUM_DI_FINDIM",
    "COLO_TITIK_MASUK_TIDAK_DI_JALUR", "COLO_HP_TIDAK_TERJANGKAU_JALUR", "WARN_TIANG_LUAR_BOUNDARY", "WARN_JALUR_LUAR_BOUNDARY",
    "WARN_JALUR_BERTUMPUK",
    "WARN_TSSR_ID_BEDA", "WARN_TSSR_HP_BEDA", "WARN_TSSR_DIPAKAI_BERSAMA", "INFO_HP_TERCOVER_TIANG_SAUDARA", "INFO_HP_DI_BOUNDARY_SAUDARA_1PIC", "INFO_RENTANG_DITUMPU_TIANG_SAUDARA",
    "INFO_TITIK_JALUR_DI_TIANG_SAUDARA", "INFO_JALUR_TERSAMBUNG_LEWAT_SAUDARA", "INFO_TIANG_JALUR_DI_BOUNDARY_SAUDARA",
    "INFO_BOUNDARY_BERIRISAN_1PIC", "WARN_HPDB_KARAKTER_TERSEMBUNYI", "INFO_BAKP_HASIL_SCAN",      # hanya catatan (bukan alasan reject, tidak mengubah status)
]


def num(v, nd=1):
    """63.7 -> '63,7'; 1911 -> '1.911' (penulisan angka Indonesia)."""
    if v is None:
        return "-"
    v = float(v)
    if nd == 0 or abs(v) >= 100:
        return "{:,.0f}".format(round(v)).replace(",", ".")
    return ("%.*f" % (nd, v)).replace(".", ",")


def _excess(v):
    """Kelebihan dari batas untuk catatan 'ukur ulang': nilai yang dibulatkan ke 0,1 m bisa tampak 0,0 m padahal di atas
    batas (review Tomohon 2026: 'span 60,0 m hanya 0,0 m di atas 60 m') -> tulis '< 0,1'."""
    return num(v) if v >= 0.05 else "< 0,1"


def rows_compact(nums, max_items=6):
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
        return ", ".join(txt[:max_items]) + " dst"
    return ", ".join(txt)


def short_label(label, max_len=26):
    """Nama pendek cluster untuk remarks/grup: ID cluster (9-12 digit) bila ada; bila tidak, nama folder tanpa awalan kota
    ('JAMBI_') dan akhiran jumlah HP/vendor ('_60HP_PT.EKSPANINDO'), dipotong dari DEPAN agar bagian pembeda (RT/RW/
    lingkungan) tetap terbaca. Dulu dipotong 24 karakter pertama sehingga 'JAMBI_SUKA KARYA KOTA BARU RT 10/16/18' semua
    tertulis 'JAMBI_SUKA KARYA KOTA BA' (review Jambi 2026)."""
    m = re.search(r"(?<!\d)(\d{9,12})(?!\d)", label or "")
    if m:
        return m.group(1)
    t = (label or "").strip()
    if not t:
        return "cluster lain"
    t = re.sub(r"[_\s-]+\d+\s*HP(?![A-Za-z]).*$", "", t, flags=re.IGNORECASE)
    if "_" in t:
        head, rest = t.split("_", 1)
        if re.match(r"^[A-Za-z .]+$", head) and re.search(r"[A-Za-z]{3}", rest):
            t = rest
    t = re.sub(r"\s+", " ", t.replace("_", " ")).strip()
    if len(t) <= max_len:
        return t
    words, out = t.split(" "), ""
    for w in reversed(words):
        cand = (w + " " + out).strip()
        if len(cand) > max_len:
            break
        out = cand
    return out or t[-max_len:]


def short_cluster(label):
    return short_label(label)


def compress_names(names):
    """['SUKA KARYA RT 07', 'SUKA KARYA RT 06', 'SUKA KARYA KOTA RT 04'] -> ['SUKA KARYA RT 07', 'RT 06', 'KOTA RT 04']:
    kata depan yang sama dengan nama pertama dibuang (label RT/RW/LK tetap), untuk daftar ringkas di remarks."""
    if not names:
        return []
    first = names[0].split()
    out = [names[0]]
    for nm in names[1:]:
        w = nm.split()
        k = 0
        while k < min(len(w), len(first)) - 1 and w[k] == first[k]:
            k += 1
        while k > 0 and k < len(w) and re.match(r"^\d", w[k]):
            k -= 1                                  # jangan sisakan angka saja: 'RT 06', bukan '06'
        out.append(" ".join(w[k:]) or nm)
    return out


def _rows_of(ket, rowmap):
    """Nomor baris HPDB dari keterangan: 'baris 26' langsung, atau ID H00021 lewat rowmap."""
    rs = [int(x) for x in re.findall(r"baris (\d+)", ket or "")]
    if not rs and rowmap:
        rs = [rowmap[h] for h in re.findall(r"\bH\d{5,}\b", ket or "") if h in rowmap]
    return rs


def parse_rows(txt):
    """'2, 10, 11, 48-52 dst' -> {2, 10, 11, 48, 49, 50, 51, 52} (tanpa bagian setelah 'dst')."""
    out = set()
    for a_, b_ in re.findall(r"(\d+)(?:\s*-\s*(\d+))?", (txt or "").split("dst")[0]):
        a_, b_ = int(a_), int(b_ or a_)
        if b_ - a_ <= 5000:
            out.update(range(a_, b_ + 1))
    return out


def _group_key(kind, route=True):
    for k in PRIORITY:
        if not route and k in ROUTE_KEYS:
            continue
        if kind == k or (k.endswith("_") and kind.startswith(k)):
            return k
    return None


def phrases(findings, rowmap=None, findim_stale=False, route=True):
    """findings: [dict(kind, sev, ket, val, lim, hint)]. -> (frasa [(prioritas, blocking, panjang, pendek)], catatan [teks])
    Tiap frasa punya versi panjang (dengan nomor baris) dan pendek (jumlah saja) untuk dipadatkan ke 255 karakter."""
    by = {}
    for f in findings:
        k = _group_key(f["kind"], route)
        if k:
            by.setdefault(k, []).append(f)
    out, notes = [], []
    # HP yang sudah disebut sebagai 'HP >50 m ke tiang' tidak disebut lagi sebagai 'jauh dari jalur, akses ...' (satu
    # titik, satu akar masalah; review Tomohon 2026: titik 1-6 dan 41-43 Lingk. 5 tertulis dua kali, memakan 255 karakter)
    jauh_rows = {r for f in by.get("HP_JAUH_DARI_TIANG", [])
                 if f.get("val") is None or f.get("lim") is None or f["val"] - f["lim"] > MARGIN_M
                 for r in _rows_of(f["ket"], rowmap)}

    def add(key, long_, short_=None, blocking=None, prio_key=None, tiny=None):
        sev = by[key][0]["sev"]
        blk = blocking if blocking is not None else (sev == "ERROR" or key in BLOCKING_WARN and
                                                     (route or key not in ROUTE_KEYS))
        out.append(_Ph((PRIORITY.index(prio_key or key), blk, long_, short_ or long_) + ((tiny,) if tiny else ()),
                       key, [f for f in by.get(key, []) if f.get("ket")]))

    # 3.10.0: irisan BOUNDARY per cluster tetangga (nama pendek -> baris HP cluster ini di irisan). 'n HP masuk boundary X'
    # untuk HP yang SEMUANYA ada di irisan dengan X digabung ke frasa tumpang tindih X, supaya kedua cluster menyebut
    # angka yang sama (review Suka Karya 2026: RT 03 '4 HP masuk boundary RT 11' sedangkan RT 11 menyebut 8 HP RT 03)
    ov_rows = {}
    for f in by.get("WARN_BOUNDARY_BERIRISAN_CLUSTER_LAIN", []):
        m = re.search(r"(?:dengan )?BOUNDARY cluster (?!ini )(.+?): luas irisan \+-(\d+) m2.*?ada (\d+) HP cluster ini"
                      r"(?: \(baris ([^)]+)\))? dan (\d+) HP cluster .+?(?: \(baris ([^)]+)\))?\. ", f["ket"])
        if m:
            ov_rows[short_cluster(m.group(1))] = (parse_rows(m.group(4)) if m.group(4) and "dst" not in m.group(4)
                                                  else None)
    merged = {}

    for key in PRIORITY:
        L = by.get(key)
        if not L:
            continue
        hints = [f["hint"] for f in L if f.get("hint")]
        if hints:
            add(key, "; ".join(dict.fromkeys(h[0] for h in hints)), "; ".join(dict.fromkeys(h[1] for h in hints)))
            continue
        n = len(L)
        rows = [r for f in L for r in _rows_of(f["ket"], rowmap)]
        if key in ("RENTANG_NP_NP", "RENTANG_NP_EP"):
            real = [f for f in L if f.get("val") is not None and f.get("lim") is not None and f["val"] - f["lim"] > MARGIN_M]
            for f in L:
                if f not in real:
                    m = re.match(r"^(.+?):", f["ket"])
                    notes.append("span %s %s m hanya %s m di atas %s m (di bawah galat GPS): ukur ulang, bukan alasan reject"
                                 % (m.group(1) if m else "", num(f["val"]), _excess(f["val"] - f["lim"]), num(f["lim"], 0)))
            if not real:
                continue
            real.sort(key=lambda f: -f["val"])
            parts = []
            for f in real[:2]:
                m = re.match(r"^(.+?) - (.+?):", f["ket"])
                parts.append("span %s ke %s %s m" % (m.group(1), m.group(2), num(f["val"])) if m else "span %s m" % num(f["val"]))
            lim = num(real[0]["lim"], 0)
            long_ = ", ".join(parts) + " >%s m" % lim + (" (+%d span lain)" % (len(real) - 2) if len(real) > 2 else "")
            add(key, long_, "%d span >%s m (maks %s m)" % (len(real), lim, num(real[0]["val"])))
        elif key == "HP_JAUH_DARI_TIANG":
            real = [f for f in L if f.get("val") is None or f.get("lim") is None or f["val"] - f["lim"] > MARGIN_M]
            for f in L:
                if f not in real:
                    notes.append("HP baris %s %s m ke tiang, hanya %s m di atas batas: ukur ulang" % (
                        rows_compact(_rows_of(f["ket"], rowmap)), num(f["val"]), _excess(f["val"] - f["lim"])))
            if not real:
                continue
            rr = [r for f in real for r in _rows_of(f["ket"], rowmap)]
            lim = num(real[0].get("lim") or 50, 0)
            if len(real) == 1:
                lab = re.search(r"\((?:baris \d+ HPDB)\)", real[0]["ket"])
                add(key, "HPDB baris %s %s m ke tiang terdekat (>%s m)" % (rows_compact(rr), num(real[0]["val"]), lim))
            else:
                mx = max(f["val"] or 0 for f in real)
                add(key, "%d HP >%s m ke tiang (baris %s; maks %s m)" % (len(real), lim, rows_compact(rr), num(mx)),
                    "%d HP >%s m ke tiang" % (len(real), lim))
        elif key in ("HP_DUPLIKAT_LABEL", "HP_DUPLIKAT_KOORDINAT", "HP_DUPLIKAT_ID"):
            parts = []
            for f in L[:2]:
                r = _rows_of(f["ket"], rowmap)
                lab = re.search(r"'([^']+)'", f["ket"])
                parts.append("HPDB baris %s%s double" % (" & ".join(str(x) for x in r[:3]),
                                                          (" label %s" % lab.group(1)) if lab and key == "HP_DUPLIKAT_LABEL" else ""))
            add(key, "; ".join(parts) + (" (+%d lain)" % (n - 2) if n > 2 else ""), "%d HP double di HPDB" % n)
        elif key == "HP_LUAR_FUNNEL":
            mx = max((f.get("val") or 0) for f in L)
            add(key, "%d HP di luar funnel (baris %s; s/d %s m)" % (n, rows_compact(rows, 4), num(mx, 0)),
                "%d HP di luar funnel (s/d %s m)" % (n, num(mx, 0)))
        elif key == "HP_LUAR_BOUNDARY":
            mx = max((f.get("val") or 0) for f in L)
            add(key, "%d HP di luar boundary KMZ (baris %s; s/d %s m)" % (n, rows_compact(rows, 4), num(mx, 0)),
                "%d HP di luar boundary KMZ" % n)
        elif key in ("HP_DI_FUNNEL_LAIN", "HP_DI_RFS_DONE", "HP_DI_RFS_EXTENSION"):
            grp = {}
            for f in L:
                m = re.search(r"(?:funnel cluster lain|cluster TERBANGUN|tercatat di) (.+?)(?: \(status| \(risiko|$)", f["ket"])
                grp.setdefault(m.group(1).strip() if m else "?", []).append(f)
            word = {"HP_DI_FUNNEL_LAIN": "masuk funnel", "HP_DI_RFS_DONE": "masuk RFS DONE",
                    "HP_DI_RFS_EXTENSION": "masuk RFS EXT"}[key]
            parts = ["%d HP %s %s (baris %s)" % (len(v), word, nm, rows_compact([r for f in v for r in _rows_of(f["ket"], rowmap)], 3))
                     for nm, v in grp.items()]
            add(key, "; ".join(parts), "; ".join("%d HP %s %s" % (len(v), word, nm) for nm, v in grp.items()))
        elif key == "HP_DI_BOUNDARY_CLUSTER_LAIN":
            grp = {}
            for f in L:
                m = re.search(r"BOUNDARY cluster (.+?) \(>", f["ket"])
                grp.setdefault(short_cluster(m.group(1)) if m else "?", []).append(f)
            for nm in list(grp):
                rr = {r for f in grp[nm] for r in _rows_of(f["ket"], None)}
                if ov_rows.get(nm) and rr and rr <= ov_rows[nm]:
                    merged[nm] = len(grp.pop(nm))        # disebut di frasa tumpang tindih nm (prioritas frasa ini)
            if grp:
                add(key, "; ".join("%d HP masuk boundary %s (baris %s)" % (
                    len(v), nm, rows_compact([r for f in v for r in _rows_of(f["ket"], rowmap)], 3)) for nm, v in grp.items()),
                    "; ".join("%d HP masuk boundary %s" % (len(v), nm) for nm, v in grp.items()))
        elif key == "HP_DUPLIKAT_LINTAS_CLUSTER":
            grp = {}
            for f in L:
                m = re.search(r"tercatat di cluster (.+?)(?: baris \d+)?:", f["ket"])
                grp.setdefault(short_cluster(m.group(1)) if m else "?", []).append(f)
            add(key, "; ".join("%d HP double dgn %s (baris %s)" % (
                len(v), nm, rows_compact([r for f in v for r in _rows_of(f["ket"].split(" juga ")[0], rowmap)], 3))
                for nm, v in grp.items()), "; ".join("%d HP double dgn %s" % (len(v), nm) for nm, v in grp.items()))
        elif key == "WARN_BOUNDARY_BERIRISAN_CLUSTER_LAIN":
            # 3.10.0: satu frasa untuk semua irisan, urut luas terbesar; tiga tingkat (rinci / ringkas / sangat ringkas)
            # agar alasan lain (BAKP, span) tetap muat 255 karakter. Bila ada HP 'masuk boundary X' yang digabung ke sini,
            # frasa ini memakai prioritas HP di boundary.
            items = []
            for f in L:
                m = re.search(r"(?:dengan )?BOUNDARY cluster (?!ini )(.+?): luas irisan \+-(\d+) m2.*?ada (\d+) HP cluster ini"
                              r"(?: \(baris ([^)]+)\))? dan (\d+) HP cluster .+?(?: \(baris ([^)]+)\))?\. ", f["ket"])
                if m:
                    items.append((-int(m.group(2)), short_cluster(m.group(1)), int(m.group(3)), int(m.group(5)),
                                  m.group(4), m.group(6)))
            if items:
                items.sort()
                longs, meds = [], []
                for (neg, nm, n_o, n_s, r_o, r_s), cn in zip(items, compress_names([t[1] for t in items])):
                    det = []
                    if r_s:
                        det.append("HP %s baris %s masuk boundary ini" % (nm, r_s))
                    if r_o:
                        det.append("HP baris %s masuk boundary %s" % (r_o, nm))
                    longs.append("boundary tumpang tindih dgn %s (+-%s m2%s)" % (
                        nm, num(-neg, 0), (", " + ", ".join(det)) if det else ", HP di irisan %d/%d" % (n_o, n_s)))
                    meds.append("%s (+-%s m2%s)" % (cn, num(-neg, 0), (", %d HP di irisan" % (n_o + n_s)) if n_o + n_s
                                                    else ""))
                med = "boundary tumpang tindih dgn " + ", ".join(meds)
                tot_a, tot_h = -sum(t[0] for t in items), sum(t[2] + t[3] for t in items)
                tiny = ("boundary tumpang tindih dgn %d cluster (+-%s m2, %d HP di irisan)" % (len(items), num(tot_a, 0), tot_h)
                        if len(items) > 1 else med)
                if any(t[1] in merged for t in items):
                    add(key, "; ".join(longs), med, blocking=True, prio_key="HP_DI_BOUNDARY_CLUSTER_LAIN", tiny=tiny)
                else:
                    add(key, "; ".join(longs), med, tiny=tiny)
        elif key == "BOUNDARY_MEMUAT_CLUSTER_LAIN":
            same = [f for f in L if "identik dengan BOUNDARY" in (f["ket"] or "")]
            if same:
                m = re.search(r"identik dengan BOUNDARY (\d+) cluster lain(?: '([^']+)')?", same[0]["ket"])
                n_, nm_ = (m.group(1), m.group(2)) if m else ("?", None)
                add(key, "boundary KMZ = boundary induk%s (sama di %s cluster lain)" % ((" '%s'" % nm_) if nm_ else "", n_),
                    "boundary KMZ = boundary induk (sama di %s cluster lain)" % n_)
                L = [f for f in L if f not in same]
                if not L:
                    continue
            parts, sh = [], []
            for f in L:
                m = re.search(r"memuat (\d+) dari (\d+) HP cluster (.+?)(?: \(baris [^)]+\))?:", f["ket"])
                if m:
                    parts.append("%s/%s HP %s" % (m.group(1), m.group(2), short_cluster(m.group(3))))
            add(key, "boundary KMZ masih boundary induk, memuat %s" % ", ".join(parts) if parts else
                "boundary KMZ masih boundary induk", "boundary KMZ masih boundary induk")
        elif key == "WARN_TIANG_GANDA_LINTAS_CLUSTER":
            parts, tot = [], 0
            for f in L:
                m = re.search(r"^(\d+) tiang .*?KMZ cluster (.+?) \(", f["ket"])
                if m:
                    tot += int(m.group(1))
                    # 3.10.0: tiang eksisting di kedua cluster bukan BOQ tiang baru ganda (catatan sewa/attachment ganda)
                    ex_only = "tiang EKSISTING di kedua cluster" in f["ket"] and "tiang BARU" not in f["ket"]
                    parts.append("%s tiang sama koordinat dgn %s (%s)" % (
                        m.group(1), short_cluster(m.group(2)), "tiang eksisting dicatat 2x" if ex_only else "BOQ ganda"))
            # versi pendek agar tetap masuk 255 karakter bila banyak temuan lain (review Jambi 2026: 17 tiang ganda RT 10
            # tidak tercantum karena frasa panjangnya tidak muat)
            ex_all = bool(parts) and all("tiang eksisting dicatat 2x" in x for x in parts)
            add(key, "; ".join(parts) or "tiang dipakai cluster lain",
                ("%d tiang ganda dgn %d cluster lain (%s)" % (tot, len(parts), "eksisting" if ex_all else "BOQ"))
                if parts else None)
        elif key.startswith("BAKP_"):
            for f in L:
                t = f["ket"]
                if key == "BAKP_STEMPEL_TTD_TEMPELAN_DIGITAL":
                    hal = re.search(r"halaman ([\d, ]+)", t)
                    st = re.search(r"\(set (\d+) dari (\d+)", t)
                    if st:
                        # BAKP gabungan: tempelan hanya di sebagian set; set mana milik cluster ini belum bisa dipastikan
                        # otomatis -> dicantumkan sebagai hal yang wajib dicek, bukan otomatis alasan reject
                        add(key, "cek stempel/ttd tempelan digital di BAKP set %s/%s (hal %s)" % (
                            st.group(1), st.group(2), hal.group(1).strip() if hal else "?"),
                            "cek stempel/ttd digital BAKP set %s/%s" % (st.group(1), st.group(2)), blocking=False)
                        notes.append("BAKP gabungan: stempel/ttd tempelan digital hanya di set %s dari %s; bila set itu milik "
                                     "cluster ini -> Reject" % (st.group(1), st.group(2)))
                    else:
                        add(key, "stempel/ttd BAKP tempelan digital (hal %s)" % (hal.group(1).strip() if hal else "?"),
                            "stempel/ttd BAKP tempelan digital")
                elif key == "BAKP_NAMA_FILE_ID_BEDA":
                    m = re.search(r"memuat ID ([\d, ]+), sedangkan HPDB/KMZ (\d+)", t)
                    add(key, "ID di file BAKP %s, bukan %s" % (m.group(1).strip(), m.group(2)) if m else "ID BAKP beda",
                        "ID BAKP beda")
                elif key == "BAKP_ADA_GAMBAR_TEMPELAN":
                    add(key, "ada gambar tempelan di BAKP (cek keaslian)")
                elif key == "BAKP_DIEDIT_APLIKASI_GRAFIS":
                    add(key, "BAKP diedit aplikasi grafis")
                elif key == "BAKP_HP_KURANG":
                    add(key, t)
                break
        elif key == "ADMIN_":
            stale = [f for f in L if f["kind"] == "ADMIN_ID_CLUSTER_TIDAK_TERDAFTAR"]
            other = [f for f in L if f not in stale]
            if stale:
                if findim_stale:
                    notes.append("ID cluster belum ada di FINDIM (OLT CLUSTER); file FINDIM lama - cek versi terbaru dulu")
                else:
                    other.append(stale[0])
            if other:
                nn = sum(int(re.match(r"^(\d+) HP", f["ket"]).group(1)) if re.match(r"^(\d+) HP", f["ket"]) else 0 for f in other)
                txt = []
                if any(f["kind"] != "ADMIN_ID_CLUSTER_TIDAK_TERDAFTAR" for f in other):
                    txt.append("wilayah HPDB beda FINDIM (%d baris)" % nn if nn else "wilayah HPDB beda FINDIM")
                if any(f["kind"] == "ADMIN_ID_CLUSTER_TIDAK_TERDAFTAR" for f in other):
                    txt.append("ID cluster tidak ada di FINDIM OLT CLUSTER")
                add(key, "; ".join(txt))
        elif key == "WARN_BAKP_ID_METADATA_BEDA":
            m = re.search(r"memuat ID ([\d, ]+), sedangkan HPDB/KMZ (\d+)", L[0]["ket"])
            add(key, "cek BAKP: judul PDF memuat ID %s, bukan %s" % (m.group(1).strip(), m.group(2)) if m else
                "cek BAKP: judul PDF memuat ID cluster lain", "cek ID di BAKP")
        elif key == "FUNNEL_SENDIRI_REJECT":
            m = re.search(r"berstatus (.+)$", L[0]["ket"])
            add(key, "funnel cluster ini berstatus %s" % (m.group(1) if m else "reject/drop"))
        elif key in ("HP_HPDB_TIDAK_ADA_DI_KMZ", "HP_KMZ_TIDAK_ADA_DI_HPDB"):
            word = "HP HPDB tidak ada di KMZ" if key == "HP_HPDB_TIDAK_ADA_DI_KMZ" else "HP KMZ tidak ada di HPDB"
            add(key, "%d %s%s" % (n, word, (" (baris %s)" % rows_compact(rows, 3)) if rows else ""), "%d %s" % (n, word))
        elif key == "HP_SUDAH_ADA_DI_DESIGN_LITE":
            add(key, "%d HP sudah ada di Design Lite (double tagging)" % n)
        elif key == "TIANG_BARU_SUDAH_ADA":
            add(key, "%d tiang baru sudah ada di Design Lite" % n)
        elif key == "WARN_ID_CLUSTER_GANDA":
            m = re.search(r"cluster (.+?) memakai|HPDB cluster (.+?) \(", L[0]["ket"])
            add(key, "ID cluster dipakai juga cluster lain")
        elif key == "WARN_TIANG_DUPLIKAT_KMZ":
            m = re.match(r"^(\d+) titik tiang", L[0]["ket"])
            hd = re.search(r"(\d+) di antaranya beda tinggi", L[0]["ket"])
            add(key, "%s tiang double di KMZ%s" % (m.group(1) if m else "", " (%s beda tinggi)" % hd.group(1) if hd else ""))
        elif key == "WARN_BELOKAN_TANPA_TIANG":
            # sudut tepat di batas (<= batas + 1 derajat) dengan tiang dekat = di bawah ketelitian gambar jalur -> catatan
            real = []
            for f in L:
                v_, l_ = f.get("val"), f.get("lim")
                dp = re.search(r"tiang terdekat \S+ (\d+(?:\.\d+)?) m", f["ket"] or "")
                if v_ is not None and l_ is not None and v_ - l_ <= 1.0 and dp and float(dp.group(1)) <= 25.0:
                    notes.append("belokan %s derajat tepat di batas %s derajat, tiang %s m dari belokan: tinjau, bukan "
                                 "alasan reject" % (num(v_, 0), num(l_, 0), num(float(dp.group(1)))))
                else:
                    real.append(f)
            if real:
                mx = max((f.get("val") or 0) for f in real)
                add(key, "%d belokan >30 derajat tanpa tiang (maks %s derajat)" % (len(real), num(mx, 0)),
                    "%d belokan >30 derajat tanpa tiang" % len(real))
        elif key == "WARN_CLUSTER_NAME_KOSONG":
            m = re.search(r"(\d+) baris", L[0]["ket"])
            add(key, "CLUSTER_NAME kosong di %s baris" % (m.group(1) if m else "semua"))
        elif key == "WARN_HP_TANPA_EVIDENCE":
            m = re.match(r"^(\d+) HP", L[0]["ket"])
            rr = re.search(r"baris ([\d, \-+dst]+)", L[0]["ket"])
            add(key, "%s HP tanpa foto evidence%s" % (m.group(1) if m else n, " (baris %s)" % rr.group(1).strip() if rr else ""),
                "%s HP tanpa foto evidence" % (m.group(1) if m else n))
        elif key == "TIANG_NGANGGUR":
            nm = [re.match(r"^(\S+)", f["ket"]).group(1) for f in L if re.match(r"^(\S+)", f["ket"])]
            tk = [re.search(r"tikor ([-\d.]+, [-\d.]+)", f["ket"]) for f in L]
            tk = [m.group(1) for m in tk if m]
            if n <= 2 and tk:
                add(key, "; ".join("%s nganggur (tikor %s)" % (a, b) for a, b in zip(nm, tk)), "%d tiang NP nganggur" % n)
            else:
                add(key, "%s tidak dilewati jalur" % (", ".join(nm[:3]) if n <= 3 else "%d tiang NP" % n), "%d tiang NP nganggur" % n)
        elif key == "WARN_HP_JAUH_LEWAT_JALUR":
            add(key, "%d HP >%s m ke tiang lewat jalur/akses (baris %s): cek akses" % (
                n, num(L[0].get("lim") or 50, 0), rows_compact(rows, 4)), "%d HP jauh lewat jalur" % n)
        elif key == "WARN_HP_AKSES_DALAM":
            if jauh_rows:
                L = [f for f in L if not (set(_rows_of(f["ket"], rowmap)) and set(_rows_of(f["ket"], rowmap)) <= jauh_rows)]
                if not L:
                    continue
                n = len(L)
                rows = [r for f in L for r in _rows_of(f["ket"], rowmap)]
            add(key, "%d HP jauh dari jalur, akses masuk dari mana? (baris %s)" % (n, rows_compact(rows, 4)),
                "%d HP akses perlu dicek" % n)
        elif key == "WARN_HP_LABEL_SAMA":
            parts = []
            for f in L[:2]:
                r = _rows_of(f["ket"], rowmap)
                lab = re.search(r"'([^']+)'", f["ket"])
                dd = re.search(r"berjarak (\d+(?:\.\d+)?) m", f["ket"])
                parts.append("HPDB baris %s label %s sama (%s m)" % (" & ".join(str(x) for x in r[:2]),
                                                                    lab.group(1) if lab else "?",
                                                                    num(float(dd.group(1))) if dd else "?"))
            add(key, "; ".join(parts) + (" (+%d lain)" % (n - 2) if n > 2 else ""),
                "%d pasang label survei sama berjauhan" % n)
        elif key == "HP_BERGESER":
            add(key, "%d HP koordinat HPDB beda KMZ (baris %s)" % (n, rows_compact(rows, 3)), "%d HP bergeser dari KMZ" % n)
        elif key == "WARN_POLE_SHEET_BEDA_KMZ":
            t = re.sub(r"^sheet '[^']*' HPDB beda dengan tiang KMZ:\s*", "", L[0]["ket"] or "")
            t = re.sub(r"\.\s*Samakan sheet.*$", "", t).strip()
            parts = [x.strip() for x in t.split(";") if x.strip()]
            long_ = "sheet Pole beda dgn KMZ: " + "; ".join(parts)
            add(key, long_ if len(long_) <= 140 else "sheet Pole beda dgn KMZ: " + parts[0][:110],
                "sheet Pole beda dgn KMZ")
        elif key == "WARN_ADMIN_ID_CLUSTER_TIDAK_TERDAFTAR":
            notes.append("ID cluster belum terdaftar di FINDIM OLT CLUSTER (cek FINDIM terbaru)")
        elif key == "WARN_ADMIN_KELURAHAN_BELUM_DI_FINDIM":
            notes.append("kelurahan di HPDB belum ada di FINDIM; file FINDIM lama - cek versi terbaru dulu, bukan alasan reject")
        # ---- 3.9.5 (review Jambi Argenta, Tegal, Minahasa, Cianjur November 2026) ----
        elif key == "HP_DI_AREA_TANPA_IZIN":
            m = re.search(r"di dalam area '([^']*)'", L[0]["ket"] or "")
            add(key, "%d HP di area %s (baris %s)" % (n, ("'%s'" % m.group(1)) if m else "tanpa izin", rows_compact(rows, 4)),
                "%d HP di area tanpa izin" % n)
        elif key == "TIANG_DI_AREA_TANPA_IZIN":
            nm = [re.match(r"^(.+?) di dalam area", f["ket"]).group(1) for f in L if re.match(r"^(.+?) di dalam area", f["ket"] or "")]
            add(key, "%s di area tanpa izin" % (", ".join(nm[:3]) if n <= 3 else "%d tiang" % n), "%d tiang di area tanpa izin" % n)
        elif key == "WARN_JALUR_LEWAT_AREA_TANPA_IZIN":
            m = re.search(r"\+-(\d+) m", L[0]["ket"] or "")
            add(key, "jalur %s m lewat area tanpa izin" % (m.group(1) if m else "?"))
        elif key == "WARN_TSSR_ID_BEDA":
            m = re.search(r"memuat ID ([\d, ]+), sedangkan HPDB/KMZ (\d+)", L[0]["ket"] or "")
            add(key, "TSSR ID %s, bukan %s" % (m.group(1).strip(), m.group(2)) if m else "TSSR milik cluster lain",
                "TSSR ID beda")
        elif key == "WARN_TSSR_HP_BEDA":
            m = re.search(r"TSSR mencatat (\d+) HP, HPDB (\d+) HP", L[0]["ket"] or "")
            add(key, "TSSR %s HP vs HPDB %s HP" % (m.group(1), m.group(2)) if m else "HP TSSR beda HPDB")
        elif key == "WARN_TSSR_DIPAKAI_BERSAMA":
            m = re.search(r"identik dengan TSSR (\d+) cluster lain.*?TSSR mencatat (\S+) HP", L[0]["ket"] or "")
            add(key, "TSSR sama dgn %s cluster lain (%s HP strand), perlu TSSR per cluster" % (m.group(1), m.group(2))
                if m else "TSSR strand, perlu TSSR per cluster", "TSSR strand, perlu TSSR per cluster")
        elif key == "WARN_HPDB_CLUSTER_NAME_CAMPUR":
            parts, sh = [], []
            for f in L:
                m = re.match(r"^(\d+) HP CLUSTER_NAME '([^']+)' \(baris ([^)]+)\)", f["ket"] or "")
                if m:
                    parts.append("%s HP CLUSTER_NAME '%s' (baris %s)" % (m.group(1), short_label(m.group(2)), m.group(3)))
                    sh.append("%s HP CLUSTER_NAME '%s'" % (m.group(1), short_label(m.group(2))))
            add(key, "; ".join(parts) or "CLUSTER_NAME HPDB campur", "; ".join(sh) or "CLUSTER_NAME HPDB campur")
        elif key == "WARN_HPDB_RT_RW_TIDAK_SESUAI":
            parts, sh = [], []
            for f in L:
                m = re.match(r"^(\d+) HP kolom (\S+) = '([^']+)' \(baris ([^)]+)\), (seharusnya|tetangga) ([^:]+?)(?: sesuai |:)",
                             f["ket"] or "")
                if m:
                    col = {"RW/lingkungan": "RW/lingk."}.get(m.group(2), m.group(2))
                    parts.append("%s HP %s %s (baris %s) %s %s" % (m.group(1), col, short_label(m.group(3)), m.group(4),
                                                                 "seharusnya" if m.group(5) == "seharusnya" else "di tengah",
                                                                 m.group(6).strip()))
                    sh.append("%s HP %s %s" % (m.group(1), col, short_label(m.group(3))))
            add(key, "RT/RW HPDB beda wilayah: " + ("; ".join(parts) or "cek kolom RT/RW"),
                "RT/RW HPDB beda wilayah: " + ("; ".join(sh) or "cek kolom RT/RW"))
        elif key == "WARN_NAMA_BERKAS_WILAYAH_BEDA":
            ms = re.findall(r"(\w+) '[^']*' = (R[TW] [\d&-]+) \(seharusnya (R[TW] [\d&-]+)\)", L[0]["ket"] or "")
            add(key, "nama berkas beda wilayah: " + ("; ".join("%s %s (cluster %s)" % m for m in ms[:2]) or "cek nama berkas"),
                "nama berkas beda RT/RW" + ((": " + ms[0][0] + " " + ms[0][1]) if ms else ""))
        elif key == "WARN_BOUNDARY_TIDAK_VALID":
            add(key, "boundary KMZ memotong diri sendiri (perbaiki poligon)", "boundary KMZ tidak valid")
        elif key == "WARN_HP_KOORDINAT_BEDA_FOTO":
            dd = sorted(f.get("val") or 0 for f in L)
            jar = num(dd[0], 0) if num(dd[0], 0) == num(dd[-1], 0) else "%s-%s" % (num(dd[0], 0), num(dd[-1], 0))
            add(key, "HP baris %s %s m dari foto evidence label sama (cek koordinat)" % (rows_compact(rows, 3), jar),
                "%d HP jauh dari fotonya" % n)
        elif key == "WARN_HPDB_KARAKTER_TERSEMBUNYI":
            m = re.match(r"^(\d+) baris", L[0]["ket"] or "")
            rr = re.search(r"\(baris ([^)]+)\)", L[0]["ket"] or "")
            add(key, "karakter tersembunyi di %s baris HPDB%s" % (m.group(1) if m else n,
                                                                (" (baris %s)" % rr.group(1)) if rr else ""),
                "karakter tersembunyi di HPDB")
        # ---- 3.13.0: integritas jalur ----
        elif key == "JALUR_TANPA_TIANG":
            # selisih <= 1 m dari batas bentang: di bawah galat GPS -> catatan ukur ulang (aturan sama dengan span)
            real = [f for f in L if f.get("val") is None or f.get("lim") is None or f["val"] - f["lim"] > MARGIN_M
                    or (f["ket"] or "").startswith("Jalur tanpa tiang")]
            for f in L:
                if f not in real:
                    notes.append("bagian jalur tanpa tiang %s m hanya %s m di atas %s m (di bawah galat GPS): ukur ulang, "
                                 "bukan alasan reject" % (num(f["val"]), _excess(f["val"] - f["lim"]), num(f["lim"], 0)))
            if not real:
                continue
            L, n = real, len(real)
            L.sort(key=lambda f: -(f.get("val") or 0))
            parts = []
            for f in L[:2]:
                t, v = f["ket"] or "", num(f.get("val"))
                m = re.match(r"^(.+?) - (ujung jalur|percabangan|.+?): (?:rentang )?[\d.]+ m", t)
                if t.startswith("Jalur tanpa tiang"):
                    parts.append("jalur %s m tanpa tiang sama sekali" % v)
                elif m and m.group(2) == "ujung jalur" and "= ujung di tiang saudara" in t:
                    ms = re.search(r"dari tiang (\S+) cluster (.+?) \(<= snap", t)
                    parts.append("span %s ke tiang %s%s %s m >60 m" % (m.group(1), ms.group(1) if ms else "saudara",
                                                                 (" " + short_cluster(ms.group(2))) if ms else "", v))
                elif m and m.group(2) == "ujung jalur":
                    parts.append("kabel %s m tanpa tiang dari %s ke ujung jalur" % (v, m.group(1)))
                elif m:
                    parts.append("rentang %s ke %s %s m lewat percabangan tanpa tiang" % (m.group(1), m.group(2), v))
                else:
                    parts.append("jalur %s m tanpa tiang" % v)
            mx = num(max(f.get("val") or 0 for f in L))
            add(key, "; ".join(parts) + (" (+%d lain)" % (n - 2) if n > 2 else ""),
                "%d bagian jalur tanpa tiang (maks %s m sepanjang jalur)" % (n, mx), tiny="%d jalur tanpa tiang" % n)
        elif key in ("JALUR_TERPUTUS", "WARN_JALUR_TERPUTUS"):
            ls = [re.search(r": ([\d.]+) m jalur \((\d+) tiang\).*?celah terdekat ([\d.]+) m", f["ket"] or "") for f in L]
            det = ["%s m, %s tiang, celah %s m" % (num(float(m.group(1))), m.group(2), num(float(m.group(3))))
                   for m in ls if m][:2]
            add(key, "%d bagian jalur terputus dari jaringan cluster%s%s" % (
                n, (" (%s)" % "; ".join(det)) if det else "", ", cek FDT tiap bagian" if key.startswith("WARN") else ""),
                "%d jalur terputus" % n)
        elif key == "UJUNG_JALUR_TANPA_TIANG":
            mx = max((f.get("val") or 0) for f in L)
            alg = [float(m.group(1)) for m in (re.search(r"; ([\d.]+) m sepanjang jalur", f["ket"] or "") for f in L) if m]
            add(key, "%d ujung jalur tanpa tiang tambat (s/d %s m dari tiang%s)" % (
                n, num(mx), (", %s m sepanjang jalur" % num(max(alg))) if alg else ""),
                "%d ujung jalur tanpa tiang" % n)
        elif key == "WARN_SIMPANG_TANPA_TIANG":
            add(key, "%d percabangan jalur tanpa tiang (sambungan wajib di tiang)" % n, "%d percabangan tanpa tiang" % n)
        elif key == "WARN_JALUR_BERSILANG_TANPA_TIANG":
            add(key, "%d titik garis jalur bersilang/menempel tanpa simpul/tiang (cek sambungan)" % n,
                "%d persilangan jalur tanpa tiang" % n)
        elif key == "WARN_JALUR_BERTUMPUK":
            tot = sum(f.get("val") or 0 for f in L)
            add(key, "garis jalur bertumpuk %s m di %d tempat (panjang kabel BOQ ganda)" % (num(tot, 0), n),
                "jalur bertumpuk %s m" % num(tot, 0))
        elif key == "COLO_TITIK_MASUK_TIDAK_DI_JALUR":
            m = re.search(r"titik masuk colo (\S+) \(terdekat ke FDT (\S+)\)", L[0]["ket"] or "")
            add(key, "tiang titik masuk colo %s (FDT %s) tidak dilewati jalur" % (m.group(1), m.group(2)) if m else
                "titik masuk colo tidak dilewati jalur", "titik masuk colo tdk di jalur")
        elif key == "COLO_HP_TIDAK_TERJANGKAU_JALUR":
            tot = sum(int(f.get("val") or 0) for f in L)
            add(key, "%d HP di bagian jalur yg tidak tersambung ke titik masuk colo (serat FDT tidak sampai)" % tot,
                "%d HP tidak terjangkau dari colo" % tot)
        elif key == "WARN_TIANG_LUAR_BOUNDARY":
            nm = [re.match(r"^(\S+)", f["ket"]).group(1) for f in L if re.match(r"^(\S+)", f["ket"] or "")]
            mx = max(f.get("val") or 0 for f in L)
            add(key, "%s di luar boundary (s/d %s m): cek izin lokasi tiang" % (
                ", ".join(nm[:3]) if n <= 3 else "%d tiang NP" % n, num(mx, 0)), "%d tiang NP di luar boundary" % n)
        elif key in ("JALUR_MELINTAS_TOL", "JALUR_MELINTAS_REL", "WARN_JALUR_MELINTAS_JALAN_BESAR"):
            jenis = {"JALUR_MELINTAS_TOL": "jalan tol", "JALUR_MELINTAS_REL": "rel kereta"}.get(key, "jalan besar")
            nms = sorted({(re.search(r"memotong (?:JALAN TOL|REL KERETA API|JALAN BESAR) (.+?) \((?:rentang|[a-z_]+)",
                                     f["ket"] or "") or re.search(r"(.*)", "")).group(1) or "" for f in L} - {"", "-"})
            add(key, "jalur memotong %s%s di %d titik: %s" % (
                jenis, (" " + ", ".join(nms[:2])) if nms else "", len(L),
                "perlu izin penyelenggara jalan" if jenis == "jalan besar" else "pindah rute atau lampirkan izin"),
                "jalur memotong %s (%d titik)" % (jenis, len(L)))
        elif key in ("WARN_TIANG_DEKAT_JALAN_TOL", "WARN_TIANG_DEKAT_REL"):
            jenis = "jalan tol" if key.endswith("TOL") else "rel"
            nm = [re.match(r"^Tiang baru (\S+)", f["ket"] or "") for f in L]
            nm = [m.group(1) for m in nm if m]
            add(key, "%s terlalu dekat %s (< %s m)" % (", ".join(nm[:3]) if n <= 3 else "%d tiang" % n, jenis,
                                                    "15" if jenis == "jalan tol" else "10"),
                "%d tiang dekat %s" % (n, jenis))
        elif key == "WARN_JALUR_LUAR_BOUNDARY":
            tot = sum(f.get("val") or 0 for f in L)
            add(key, "jalur %s m di luar boundary (feeder? sebutkan)" % num(tot, 0), "jalur %s m di luar boundary" % num(tot, 0))
        elif key == "INFO_TIANG_JALUR_DI_BOUNDARY_SAUDARA":
            notes.append("%d tiang/bentangan jalur di boundary cluster saudara 1 PIC: bukan alasan reject, catat sebagai "
                         "tiang/jalur bersama" % n)
        elif key == "INFO_JALUR_TERSAMBUNG_LEWAT_SAUDARA":
            notes.append("%d bagian jalur tersambung lewat jalur cluster saudara 1 PIC: bukan alasan reject, pastikan "
                         "sambungan kabel di tiang" % n)
        elif key in ("INFO_RENTANG_DITUMPU_TIANG_SAUDARA", "INFO_TITIK_JALUR_DI_TIANG_SAUDARA"):
            if key == "INFO_RENTANG_DITUMPU_TIANG_SAUDARA":
                notes.append("%d rentang ditumpu tiang cluster saudara (terpanjang %s m): bukan alasan reject, catat tiang bersama"
                             % (n, num(max(f.get("val") or 0 for f in L))))
            else:
                notes.append("%d belokan/ujung jalur di tiang cluster saudara: pastikan treklam/tambat di tiang itu" % n)
        elif key == "INFO_HP_TERCOVER_TIANG_SAUDARA":
            # 3.11.0: catatan saja (bukan alasan reject): drop ditarik dari tiang cluster saudara 1 PIC/berdampingan
            grp = {}
            for f in L:
                m = re.search(r"cluster (.+?) (\d+(?:\.\d+)?) m \(<=", f["ket"] or "")
                grp.setdefault(short_cluster(m.group(1)) if m else "?", []).append(f)
            for nm, v in grp.items():
                notes.append("%d HP >%s m ke tiang sendiri tercover tiang %s (baris %s): desain drop dari tiang itu / tiang "
                             "bersama, atau pindahkan HP" % (len(v), num(v[0]["lim"], 0) if v[0].get("lim") else "50", nm,
                                                             rows_compact([r for f in v for r in _rows_of(f["ket"], rowmap)], 6)))
        elif key in ("INFO_HP_DI_BOUNDARY_SAUDARA_1PIC", "INFO_BOUNDARY_BERIRISAN_1PIC"):
            if key == "INFO_BOUNDARY_BERIRISAN_1PIC":
                nms = []
                for f in L:
                    m = re.search(r"(?:dengan )?BOUNDARY cluster (?!ini )(.+?): luas irisan \+-(\d+) m2", f["ket"] or "")
                    if m:
                        nms.append("%s (+-%s m2)" % (short_cluster(m.group(1)), num(int(m.group(2)), 0)))
                if nms:
                    notes.append("boundary bertumpuk dgn %s - 1 PIC/berdampingan satu funnel: diterima, bukan alasan reject"
                                 % ", ".join(nms))
            else:
                grp = {}
                for f in L:
                    m = re.search(r"di dalam BOUNDARY cluster (.+?) - 1 PIC", f["ket"] or "")
                    grp.setdefault(short_cluster(m.group(1)) if m else "?", []).append(f)
                for nm, v in grp.items():
                    notes.append("%d HP di boundary %s (baris %s) - 1 PIC: diterima; pastikan rumah hanya di satu HPDB" % (
                        len(v), nm, rows_compact([r for f in v for r in _rows_of(f["ket"], rowmap)], 6)))
        elif key == "INFO_BAKP_HASIL_SCAN":
            notes.append("BAKP hasil scan: baca manual Cluster ID/HP, RT/RW, kompensasi, centang verifikasi & ttd")
    out.sort(key=lambda t: t[0])
    return out, notes


class _Ph(tuple):
    """Frasa remarks (tuple lama: prioritas, penghalang, panjang, pendek, [mini]) + kode temuan & temuannya."""
    def __new__(cls, items, key="", fl=()):
        o = tuple.__new__(cls, items)
        o.key, o.fl = key, list(fl)
        return o


# ---- 3.14.0: remarks SEDERHANA (masukan pengguna: "lebih simple aja kata-katanya, kayak 'ada Homepass duplicate dengan
# cluster blabla, ada homepass dari pole lebih 50 meter, ada pole duplicate dengan cluster blabla, mohon di check kembali
# keseluruhannya'"). Satu kalimat pendek per jenis masalah, tanpa nomor baris/angka rinci; rincian tetap di REMARKS.txt,
# laporan dan QC_TEMUAN. {c} = nama cluster lain, {lim} = batas yang dilanggar.
SIMPLE = {
    "CLUSTER_LAIN_DIGABUNG": "ada data cluster lain yang ikut tergabung di cluster ini",
    "BOUNDARY_MEMUAT_CLUSTER_LAIN": "boundary masih boundary induk (memuat cluster lain)",
    "HP_DUPLIKAT_LINTAS_CLUSTER": "ada homepass duplikat dengan cluster {c}",
    "HP_DI_RFS_DONE": "ada homepass yang sudah masuk area RFS DONE",
    "HP_DI_RFS_EXTENSION": "ada homepass di area RFS EXTENSION",
    "HP_DI_FUNNEL_LAIN": "ada homepass yang masuk funnel lain",
    "HP_DI_BOUNDARY_CLUSTER_LAIN": "ada homepass yang masuk boundary cluster {c}",
    "WARN_BOUNDARY_BERIRISAN_CLUSTER_LAIN": "boundary tumpang tindih dengan cluster {c}",
    "BAKP_HP_KURANG": "jumlah homepass di BAKP kurang",
    "BAKP_STEMPEL_TTD_TEMPELAN_DIGITAL": "stempel/tanda tangan BAKP berupa tempelan digital",
    "BAKP_ADA_GAMBAR_TEMPELAN": "ada gambar tempelan di BAKP",
    "BAKP_NAMA_FILE_ID_BEDA": "ID cluster di nama file BAKP berbeda",
    "WARN_BAKP_ID_METADATA_BEDA": "ID cluster di BAKP berbeda",
    "BAKP_DIEDIT_APLIKASI_GRAFIS": "BAKP terdeteksi diedit dengan aplikasi grafis",
    "FUNNEL_SENDIRI_REJECT": "funnel cluster ini berstatus reject/batal",
    "HP_LUAR_FUNNEL": "ada homepass di luar funnel",
    "HP_LUAR_BOUNDARY": "ada homepass di luar boundary",
    "HP_DI_AREA_TANPA_IZIN": "ada homepass di area tanpa izin",
    "TIANG_DI_AREA_TANPA_IZIN": "ada tiang di area tanpa izin",
    "HP_JAUH_DARI_TIANG": "ada homepass yang jaraknya dari tiang lebih dari {lim} m",
    "RENTANG_NP_NP": "ada jarak antar tiang lebih dari {lim} m",
    "RENTANG_NP_EP": "ada jarak antar tiang lebih dari {lim} m",
    "JALUR_TANPA_TIANG": "ada jalur kabel tanpa tiang",
    "JALUR_TERPUTUS": "ada jalur kabel yang terputus",
    "UJUNG_JALUR_TANPA_TIANG": "ada ujung jalur kabel tanpa tiang",
    "WARN_SIMPANG_TANPA_TIANG": "ada percabangan jalur tanpa tiang",
    "HP_DUPLIKAT_KOORDINAT": "ada homepass duplikat (koordinat sama)",
    "HP_DUPLIKAT_ID": "ada ID homepass ganda",
    "HP_DUPLIKAT_LABEL": "ada homepass duplikat (label sama)",
    "HP_HPDB_TIDAK_ADA_DI_KMZ": "ada homepass di HPDB yang tidak ada di KMZ",
    "HP_KMZ_TIDAK_ADA_DI_HPDB": "ada homepass di KMZ yang tidak ada di HPDB",
    "HP_SUDAH_ADA_DI_DESIGN_LITE": "ada homepass yang sudah ada di jaringan eksisting",
    "TIANG_BARU_SUDAH_ADA": "ada tiang baru yang sudah ada di jaringan eksisting",
    "WARN_TIANG_GANDA_LINTAS_CLUSTER": "ada tiang duplikat dengan cluster {c}",
    "WARN_ID_CLUSTER_GANDA": "ID cluster juga dipakai cluster lain",
    "ADMIN_": "data wilayah administrasi tidak sesuai",
    "WARN_TIANG_DUPLIKAT_KMZ": "ada tiang dobel di KMZ",
    "WARN_BELOKAN_TANPA_TIANG": "ada belokan jalur tanpa tiang",
    "WARN_JALUR_TERPUTUS": "ada jalur kabel yang terputus",
    "WARN_JALUR_BERSILANG_TANPA_TIANG": "ada jalur kabel bersilang tanpa tiang",
    "WARN_POLE_SHEET_BEDA_KMZ": "data sheet Pole berbeda dengan KMZ",
    "WARN_CLUSTER_NAME_KOSONG": "ada nama cluster yang kosong di HPDB",
    "WARN_HPDB_CLUSTER_NAME_CAMPUR": "nama cluster di HPDB tidak seragam",
    "WARN_HPDB_RT_RW_TIDAK_SESUAI": "ada RT/RW di HPDB yang tidak sesuai wilayahnya",
    "WARN_BOUNDARY_TIDAK_VALID": "bentuk boundary tidak valid",
    "WARN_NAMA_BERKAS_WILAYAH_BEDA": "ada berkas (mis. BAKP) yang namanya memuat RT/RW lain",
    "WARN_HP_KOORDINAT_BEDA_FOTO": "ada koordinat homepass yang berbeda dengan foto",
    "WARN_JALUR_LEWAT_AREA_TANPA_IZIN": "ada jalur kabel lewat area tanpa izin",
    "WARN_HP_TANPA_EVIDENCE": "ada homepass tanpa foto",
    "TIANG_NGANGGUR": "ada tiang yang tidak dilewati jalur",
    "WARN_HP_LABEL_SAMA": "ada homepass dengan label sama",
    "WARN_HP_JAUH_LEWAT_JALUR": "ada homepass yang lebih dari {lim} m dari tiang bila diukur lewat jalan",
    "WARN_HP_AKSES_DALAM": "ada homepass yang jauh dari jalur kabel",
    "HP_BERGESER": "ada homepass yang posisinya bergeser",
    "WARN_ADMIN_ID_CLUSTER_TIDAK_TERDAFTAR": "ID cluster belum terdaftar",
    "COLO_TITIK_MASUK_TIDAK_DI_JALUR": "titik masuk kabel dari FDT tidak dilewati jalur",
    "COLO_HP_TIDAK_TERJANGKAU_JALUR": "ada homepass yang tidak terjangkau dari FDT",
    "WARN_TIANG_LUAR_BOUNDARY": "ada tiang di luar boundary",
    "WARN_JALUR_LUAR_BOUNDARY": "ada jalur kabel di luar boundary",
    "JALUR_MELINTAS_TOL": "ada jalur kabel yang memotong jalan tol (wajib izin BPJT/BUJT atau pindah rute)",
    "JALUR_MELINTAS_REL": "ada jalur kabel yang memotong rel kereta (wajib izin DJKA/KAI atau pindah rute)",
    "WARN_JALUR_MELINTAS_JALAN_BESAR": "ada jalur kabel yang memotong jalan besar (perlu izin penyelenggara jalan)",
    "WARN_TIANG_DEKAT_JALAN_TOL": "ada tiang yang terlalu dekat jalan tol",
    "WARN_TIANG_DEKAT_REL": "ada tiang yang terlalu dekat rel kereta",
    "WARN_JALUR_BERTUMPUK": "ada garis jalur yang digambar dobel",
    "WARN_TSSR_ID_BEDA": "ID cluster di TSSR berbeda",
    "WARN_TSSR_HP_BEDA": "jumlah homepass di TSSR berbeda",
    "WARN_TSSR_DIPAKAI_BERSAMA": "TSSR dipakai bersama cluster lain",
    "WARN_HPDB_KARAKTER_TERSEMBUNYI": "ada karakter tersembunyi di HPDB",
}
SIMPLE_TAIL = "Mohon dicek kembali keseluruhannya."


def _names_in(long_):
    """Nama cluster lain dari frasa rinci ('... dgn SUKA KARYA RT 10 (+-2.910 m2 ...), RT 06 (...)')."""
    m = re.search(r"\b(?:dgn|dengan)\s+(?:cluster\s+)?(.+)$", long_ or "")
    if not m:
        return []
    t = m.group(1)
    while re.search(r"\([^()]*\)", t):
        t = re.sub(r"\([^()]*\)", "", t)
    t = re.split(r";|:|\bmasuk\b|\bdi irisan\b", t)[0]
    out = []
    for x in t.split(","):
        x = " ".join(x.split()).strip(" .")
        x = re.sub(r"\s+(dan|&)\s+\d+\s+lain$", "", x)
        if x and x not in out and len(x) <= 60:
            out.append(x)
    return out


def _simple_of(p):
    key = getattr(p, "key", "")
    tpl = SIMPLE.get(key)
    if tpl is None and key.startswith("ADMIN_"):
        tpl = SIMPLE["ADMIN_"]
    if tpl is None:
        return p[3]                 # kode baru tanpa kalimat sederhana: pakai versi pendek
    lim = None
    for f in getattr(p, "fl", []):
        if f.get("lim") not in (None, ""):
            try:
                lim = float(f["lim"])
            except (TypeError, ValueError):
                pass
    if "{lim}" in tpl:
        tpl = tpl.replace("{lim}", num(lim, 0) if lim else "batas")
    if "{c}" in tpl:
        nm = _names_in(p[2])
        tpl = tpl.replace(" {c}", (" " + ", ".join(nm)) if nm else " lain")
    return tpl


def build_simple(findings, rowmap=None, findim_stale=False, max_len=MAX_LEN, route=True):
    """Remarks sederhana: 'Reject: ada A, ada B, dan C. Mohon dicek kembali keseluruhannya.' (<= 255 karakter).
    Urutan dan status SAMA dengan remarks rinci (alasan penghalang dulu)."""
    ph, notes = phrases(findings, rowmap, findim_stale, route)
    if not ph:
        return {"status": "APPROVE", "text": "Approve", "length": 7, "used": [], "dropped": [], "notes": notes}
    blocking = any(p[1] for p in ph)
    status, head = ("REJECT", "Reject: ") if blocking else ("APPROVE DENGAN CATATAN", "Approve dengan catatan: ")
    ph.sort(key=lambda t: (not t[1], t[0]))
    # 3.15.4: remarks lebih mudah dibaca. REJECT hanya menyebut ALASAN REJECT (paling banyak tiga, yang terberat dulu);
    # hal lain yang bukan alasan reject tidak dicampur ke kalimat reject, tetapi tetap tercatat di REMARKS.txt (daftar
    # 'temuan lain') dan di laporan. Approve dengan catatan menyebut paling banyak tiga catatan.
    items, lain = [], []
    for p in ph:
        t = _simple_of(p)
        if not t or t in items or t in lain:
            continue
        (items if (p[1] or not blocking) else lain).append(t)
    semua = list(items)
    items = items[:3]

    def compose(it, more):
        if not it:
            return head.rstrip()
        body = it[0] if len(it) == 1 else ", ".join(it[:-1]) + (", " if more else ", dan ") + it[-1]
        body = body[0].upper() + body[1:]
        return head + body + (", dan masalah lain" if more else "") + ". " + SIMPLE_TAIL
    used = list(items)
    text = compose(used, len(semua) > len(used))
    while len(text) > max_len and len(used) > 1:
        used.pop()
        text = compose(used, True)
    if len(text) > max_len:
        text = text[:max_len - 1].rstrip() + "."
    dropped = [t for t in semua if t not in used] + lain
    # 3.15.3: kode temuan yang menjadi alasan reject, agar HTML dan Word menandai temuan yang sama
    return {"status": status, "text": text, "length": len(text), "used": used, "dropped": dropped, "notes": notes,
            "blocking": sorted({getattr(p, "key", "") for p in ph if p[1]} - {""})}


def build(findings, rowmap=None, findim_stale=False, max_len=MAX_LEN, route=True, style="rinci"):
    """-> dict(status, text, length, used=[frasa], dropped=[frasa], notes=[...])
    route=False: tanpa kode integritas jalur 3.13.0 (hasil identik 3.12.0).
    style='sederhana': kalimat pendek tanpa angka rinci (3.14.0); 'rinci' = gaya lama."""
    if style == "sederhana":
        return build_simple(findings, rowmap, findim_stale, max_len, route)
    ph, notes = phrases(findings, rowmap, findim_stale, route)
    blocking = any(p[1] for p in ph)
    if blocking:
        status, head = "REJECT", "Reject: "
    elif ph:
        status, head = "APPROVE DENGAN CATATAN", "Approve dgn catatan: "
    else:
        return {"status": "APPROVE", "text": "Approve", "length": 7, "used": [], "dropped": [], "notes": notes}
    # alasan penghalang dulu, lalu catatan lain
    ph.sort(key=lambda t: (not t[1], t[0]))
    used, dropped = [], []
    text = head.rstrip()
    for i, (_pr, _blk, long_, short_, *rest) in enumerate(ph):
        cands = (long_, short_) + tuple(rest)
        # 3.10.0: versi rinci tidak boleh menutup alasan reject berikutnya - sisakan ruang untuk versi terpendek alasan
        # penghalang berikutnya bila versi lebih pendek frasa ini membuatnya muat (review Suka Karya 2026: rincian baris
        # irisan menggeser 'gambar tempelan di BAKP' keluar dari 255 karakter)
        nxt = next((min(len(c) for c in q[2:]) for q in ph[i + 1:] if q[1]), None) if _blk else None
        sep = " " if text.endswith(":") else "; "
        fit = [c for c in cands if len(text) + len(sep) + len(c) <= max_len]
        if fit and nxt is not None:
            room = [c for c in fit if len(text) + len(sep) + len(c) + 2 + nxt <= max_len]
            fit = room or fit
        if fit:
            cand = fit[0]
            text += sep + cand
            used.append(cand)
        else:
            dropped.append(long_)
    if dropped:
        tail = "; +%d temuan lain" % len(dropped)
        if len(text) + len(tail) <= max_len:
            text += tail          # isi temuan diutamakan; penanda sisa hanya bila masih muat
    return {"status": status, "text": text, "length": len(text), "used": used, "dropped": dropped, "notes": notes}

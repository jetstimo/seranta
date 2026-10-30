# -*- coding: utf-8 -*-
"""
Seranta - FTTH Design Assistant
Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-2.0-or-later.

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
BLOCKING_WARN = {"WARN_BOUNDARY_BERIRISAN_CLUSTER_LAIN", "WARN_TIANG_GANDA_LINTAS_CLUSTER", "WARN_ID_CLUSTER_GANDA"}

# Urutan prioritas (paling berat dulu). Kode yang tidak ada di sini tidak masuk remarks.
PRIORITY = [
    "CLUSTER_LAIN_DIGABUNG", "BOUNDARY_MEMUAT_CLUSTER_LAIN", "HP_DUPLIKAT_LINTAS_CLUSTER", "HP_DI_RFS_DONE", "HP_DI_RFS_EXTENSION", "HP_DI_FUNNEL_LAIN",
    "HP_DI_BOUNDARY_CLUSTER_LAIN", "WARN_BOUNDARY_BERIRISAN_CLUSTER_LAIN", "BAKP_HP_KURANG", "BAKP_STEMPEL_TTD_TEMPELAN_DIGITAL",
    "BAKP_ADA_GAMBAR_TEMPELAN", "BAKP_NAMA_FILE_ID_BEDA", "BAKP_DIEDIT_APLIKASI_GRAFIS", "FUNNEL_SENDIRI_REJECT",
    "HP_LUAR_FUNNEL", "HP_LUAR_BOUNDARY", "HP_JAUH_DARI_TIANG", "RENTANG_NP_NP", "RENTANG_NP_EP",
    "HP_DUPLIKAT_KOORDINAT", "HP_DUPLIKAT_ID", "HP_DUPLIKAT_LABEL", "HP_HPDB_TIDAK_ADA_DI_KMZ", "HP_KMZ_TIDAK_ADA_DI_HPDB",
    "HP_SUDAH_ADA_DI_DESIGN_LITE", "TIANG_BARU_SUDAH_ADA", "WARN_TIANG_GANDA_LINTAS_CLUSTER", "WARN_ID_CLUSTER_GANDA",
    "ADMIN_", "WARN_TIANG_DUPLIKAT_KMZ", "WARN_BELOKAN_TANPA_TIANG", "WARN_POLE_SHEET_BEDA_KMZ", "WARN_CLUSTER_NAME_KOSONG",
    "WARN_HP_TANPA_EVIDENCE", "TIANG_NGANGGUR", "WARN_HP_LABEL_SAMA", "HP_BERGESER", "WARN_ADMIN_ID_CLUSTER_TIDAK_TERDAFTAR",
]


def num(v, nd=1):
    """63.7 -> '63,7'; 1911 -> '1.911' (penulisan angka Indonesia)."""
    if v is None:
        return "-"
    v = float(v)
    if nd == 0 or abs(v) >= 100:
        return "{:,.0f}".format(round(v)).replace(",", ".")
    return ("%.*f" % (nd, v)).replace(".", ",")


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


def short_cluster(label):
    m = re.search(r"(?<!\d)(\d{9,12})(?!\d)", label or "")
    if m:
        return m.group(1)
    return (label or "cluster lain")[:24]


def _rows_of(ket, rowmap):
    """Nomor baris HPDB dari keterangan: 'baris 26' langsung, atau ID H00021 lewat rowmap."""
    rs = [int(x) for x in re.findall(r"baris (\d+)", ket or "")]
    if not rs and rowmap:
        rs = [rowmap[h] for h in re.findall(r"\bH\d{5,}\b", ket or "") if h in rowmap]
    return rs


def _group_key(kind):
    for k in PRIORITY:
        if kind == k or (k.endswith("_") and kind.startswith(k)):
            return k
    return None


def phrases(findings, rowmap=None, findim_stale=False):
    """findings: [dict(kind, sev, ket, val, lim, hint)]. -> (frasa [(prioritas, blocking, panjang, pendek)], catatan [teks])
    Tiap frasa punya versi panjang (dengan nomor baris) dan pendek (jumlah saja) untuk dipadatkan ke 255 karakter."""
    by = {}
    for f in findings:
        k = _group_key(f["kind"])
        if k:
            by.setdefault(k, []).append(f)
    out, notes = [], []

    def add(key, long_, short_=None, blocking=None):
        sev = by[key][0]["sev"]
        blk = blocking if blocking is not None else (sev == "ERROR" or key in BLOCKING_WARN)
        out.append((PRIORITY.index(key), blk, long_, short_ or long_))

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
                                 % (m.group(1) if m else "", num(f["val"]), num(f["val"] - f["lim"]), num(f["lim"], 0)))
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
                        rows_compact(_rows_of(f["ket"], rowmap)), num(f["val"]), num(f["val"] - f["lim"])))
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
            parts, sh = [], []
            for f in L:
                m = re.search(r"BOUNDARY cluster (.+?): luas irisan \+-(\d+) m2.*?ada (\d+) HP cluster ini"
                              r"(?: \(baris ([^)]+)\))? dan (\d+) HP cluster .+?(?: \(baris ([^)]+)\))?\. ", f["ket"])
                if m:
                    nm = short_cluster(m.group(1))
                    det = []
                    if m.group(6):
                        det.append("HP %s baris %s masuk boundary ini" % (nm, m.group(6)))
                    if m.group(4):
                        det.append("HP baris %s masuk boundary %s" % (m.group(4), nm))
                    parts.append("boundary tumpang tindih dgn %s (+-%s m2%s)" % (
                        nm, num(int(m.group(2)), 0), (", " + ", ".join(det)) if det else
                        ", HP di irisan %s/%s" % (m.group(3), m.group(5))))
                    sh.append("boundary tumpang tindih dgn %s (+-%s m2)" % (nm, num(int(m.group(2)), 0)))
            if parts:
                add(key, "; ".join(parts), "; ".join(sh))
        elif key == "BOUNDARY_MEMUAT_CLUSTER_LAIN":
            parts, sh = [], []
            for f in L:
                m = re.search(r"memuat (\d+) dari (\d+) HP cluster (.+?)(?: \(baris [^)]+\))?:", f["ket"])
                if m:
                    parts.append("%s/%s HP %s" % (m.group(1), m.group(2), short_cluster(m.group(3))))
            add(key, "boundary KMZ masih boundary induk, memuat %s" % ", ".join(parts) if parts else
                "boundary KMZ masih boundary induk", "boundary KMZ masih boundary induk")
        elif key == "WARN_TIANG_GANDA_LINTAS_CLUSTER":
            parts = []
            for f in L:
                m = re.search(r"^(\d+) tiang .*?KMZ cluster (.+?) \(", f["ket"])
                if m:
                    parts.append("%s tiang sama koordinat dgn %s (BOQ ganda)" % (m.group(1), short_cluster(m.group(2))))
            add(key, "; ".join(parts) or "tiang dipakai cluster lain")
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
            add(key, "%s tidak dilewati jalur" % (", ".join(nm[:3]) if n <= 3 else "%d tiang" % n), "%d tiang nganggur" % n)
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
    out.sort(key=lambda t: t[0])
    return out, notes


def build(findings, rowmap=None, findim_stale=False, max_len=MAX_LEN):
    """-> dict(status, text, length, used=[frasa], dropped=[frasa], notes=[...])"""
    ph, notes = phrases(findings, rowmap, findim_stale)
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
    for _pr, _blk, long_, short_ in ph:
        for cand in (long_, short_):
            sep = " " if text.endswith(":") else "; "
            if len(text) + len(sep) + len(cand) <= max_len:
                text += sep + cand
                used.append(cand)
                break
        else:
            dropped.append(long_)
    if dropped:
        tail = "; +%d temuan lain" % len(dropped)
        if len(text) + len(tail) <= max_len:
            text += tail          # isi temuan diutamakan; penanda sisa hanya bila masih muat
    return {"status": status, "text": text, "length": len(text), "used": used, "dropped": dropped, "notes": notes}

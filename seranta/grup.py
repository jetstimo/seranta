# -*- coding: utf-8 -*-
"""
Seranta - FTTH Design Assistant
Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later.

CEK GRUP 1 PIC DESAIN / JARINGAN BERSAMA
----------------------------------------
Beberapa cluster sering didesain satu PIC sebagai satu jaringan (review Minahasa & Jambi, Oktober 2026): tiang dipakai
bersama, kabel tersambung, satu BAKP untuk beberapa cluster, BOUNDARY berdampingan. Bila tiap cluster diperiksa sendiri,
masalah grup (tiang dihitung dua kali, rumah di dua cluster, FDT direncanakan sendiri-sendiri) tidak terlihat dan
reviewer harus menjalankan cluster satu per satu.

Modul ini (murni Python, bisa diuji tanpa QGIS) menyatukan hasil per cluster dari alat 1 menjadi grup:
  * anggota grup = cluster yang saling terhubung lewat sinyal 1 PIC (union-find, transitif: A-B dan B-C = satu grup);
  * ringkasan grup: total HP dan splitter (satu rencana FDT), tiang yang tercatat di dua cluster (dihitung sekali),
    BAKP yang dipakai bersama, status dan remarks setiap anggota, status grup (grup baru siap didesain bila semua
    anggota Approve);
  * laporan REKAP_GRUP_1PIC_<ID>.txt dan .csv.
"""
import math
import os
import re

ID_RX = re.compile(r"(?<!\d)(\d{9,12})(?!\d)")


def norm_dir(d):
    return os.path.normcase(os.path.abspath(d or ""))


def short_id(label, cl_id=""):
    if cl_id:
        return cl_id
    m = ID_RX.search(label or "")
    if m:
        return m.group(1)
    try:
        from .remarks import short_label
    except ImportError:
        from remarks import short_label
    return short_label(label) if label else "?"


def groups(results):
    """results: [dict(dir, label, cl_id, hp, remarks, pic_info=[dict(dir, label, one_net, signals, shared, n_hp)])].
    -> [[result, ...], ...] grup ber-anggota >= 2 (urut ID), memakai union-find atas tautan pic_info.
    Anggota yang hanya muncul sebagai tautan (belum dijalankan) ikut dicatat dengan field 'missing'=True."""
    by = {}
    for r in results:
        if r and r.get("dir"):
            by[norm_dir(r["dir"])] = r
    parent = {}

    def find(a):
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    links = {}
    for k, r in list(by.items()):
        find(k)
        for p in r.get("pic_info") or []:
            pk = norm_dir(p.get("dir"))
            if not pk:
                continue
            if pk not in by:
                by[pk] = {"dir": p.get("dir"), "label": p.get("label"), "cl_id": short_id(p.get("label")),
                          "hp": p.get("n_hp"), "missing": True, "pic_info": []}
            union(k, pk)
            key = tuple(sorted((k, pk)))
            old = links.get(key)
            if old is None or (p.get("one_net") and not old.get("one_net")):
                p = dict(p)
                p["_from"] = k                  # 3.10.0: sudut pandang tautan (HP 'own' = cluster k)
                links[key] = p
    comp = {}
    for k in by:
        comp.setdefault(find(k), []).append(k)
    out = []
    for members in comp.values():
        if len(members) < 2:
            continue
        mem = sorted((by[m] for m in members), key=lambda r: short_id(r.get("label"), r.get("cl_id")))
        ks = {norm_dir(r["dir"]) for r in mem}
        lk = [(a, b, p) for (a, b), p in links.items() if a in ks and b in ks]
        out.append({"members": mem, "links": lk, "by": by})
    out.sort(key=lambda g: short_id(g["members"][0].get("label"), g["members"][0].get("cl_id")))
    return out


GENERIC_AREA = {"RT", "RW", "LK", "LINGKUNGAN", "LINGK", "DUSUN", "BLOK", "NO", "TAHAP", "PERUM", "PERUMAHAN", "KEL",
                "KELURAHAN", "DESA", "JL", "JALAN", "GG", "GANG"}


def wilayah_name(labels):
    """Nama wilayah induk dari nama cluster anggota: kata depan atau kata belakang yang sama di semua anggota
    ('SUKA KARYA KOTA BARU RT 06/02/03...' -> 'SUKA KARYA KOTA BARU'; 'LINGKUNGAN 1..7-KAKASKASEN' -> 'KAKASKASEN')."""
    try:
        from .remarks import short_label
    except ImportError:
        from remarks import short_label
    toks = []
    for lb in labels:
        t = short_label(ID_RX.sub("", lb or "").strip(" _-"), max_len=200)
        toks.append([w for w in re.split(r"[\s_-]+", t.upper()) if w])
    toks = [t for t in toks if t]
    if len(toks) < 2:
        return ""

    def common(seqs):
        out = []
        for ws in zip(*seqs):
            if len(set(ws)) != 1:
                break
            out.append(ws[0])
        return out
    pre = common(toks)
    suf = list(reversed(common([list(reversed(t)) for t in toks])))
    best = max((pre, suf), key=lambda ws: sum(len(w) for w in ws if w not in GENERIC_AREA and not w.isdigit()))
    while best and (best[-1] in GENERIC_AREA or best[-1].isdigit()):
        best = best[:-1]
    while best and (best[0] in GENERIC_AREA or best[0].isdigit()):
        best = best[1:]
    name = " ".join(best)
    return name if re.search(r"[A-Z]{4}", name) else ""


def group_kind(links):
    """Jenis grup:
      'jaringan'   : SATU JARINGAN / 1 PIC desain - bukti fisik (tiang sama koordinat, jalur tersambung, folder cluster lain
                     di KMZ);
      'paket'      : PAKET SURVEI 1 PIC - jaringan terpisah, tetapi dokumen/batas disalin dari satu paket (BOUNDARY identik
                     atau file BAKP identik);
      'berdampingan': cluster bertetangga - hanya BOUNDARY bersinggungan/berdampingan."""
    sig = " | ".join("; ".join(p.get("signals") or []) for _a, _b, p in links)
    if any(p.get("one_net") for _a, _b, p in links):
        return "jaringan"
    if "BOUNDARY identik" in sig or "BAKP identik" in sig:
        return "paket"
    return "berdampingan"


KIND_TITLE = {"jaringan": "SATU JARINGAN (1 PIC desain)",
              "paket": "PAKET SURVEI 1 PIC (dokumen/boundary sama, jaringan terpisah)",
              "berdampingan": "BERDAMPINGAN (cluster bertetangga, jaringan & dokumen terpisah)"}


TOUCH_M2 = 100.0     # irisan < 100 m2 tanpa HP (+-2 m x 50 m garis batas yang digambar tangan) = bersinggungan


def _sid(r):
    return short_id(r.get("label"), r.get("cl_id"))


def _sname(r):
    """Nama pendek anggota untuk kalimat ringkas (tanpa ID panjang bila ada nama RT/RW)."""
    try:
        from .remarks import short_label
    except ImportError:
        from remarks import short_label
    return short_label(r.get("label") or "")


def _rows(v, n=6):
    try:
        from .konsistensi import rows_txt
    except ImportError:
        from konsistensi import rows_txt
    return rows_txt(v, n)


def _num(v):
    return ("{:,.0f}".format(v)).replace(",", ".")


def fdt_plan(mem, one_net, n_hp, fdt_cap=384):
    """Rencana FDT/colo grup dari hasil colo tiap anggota (3.10.0). Dulu colo dinilai per cluster sehingga anggota satu
    jaringan bisa dicolo ke FDT berbeda-beda tanpa terlihat (review Suka Karya 2026: 3 FDT existing + FDT baru di satu
    jaringan 752 HP). -> dict(lines, terpadu (True/False/None), n_target, targets, over)"""
    tgt, baru, blm = {}, [], []
    for r in mem:
        c = (r.get("colo") or "-").strip()
        if c == "FDT baru":
            baru.append(r)
        elif c in ("", "-") or r.get("missing"):
            blm.append(r)
        else:
            tgt.setdefault(c, []).append(r)
    L = []
    for c in sorted(tgt):
        rs = tgt[c]
        info = [r.get("colo_info") or {} for r in rs]
        dist = ", ".join("%s %s m" % (_sname(r), i_.get("d_entry", "?")) for r, i_ in zip(rs, info))
        L.append("colo %s: %s" % (c, dist))
    if baru:
        L.append("FDT baru: %s" % ", ".join(_sname(r) for r in baru))
    if blm:
        L.append("colo belum dinilai (tanpa Design Lite / belum dijalankan): %s" % ", ".join(_sname(r) for r in blm))
    over = []
    for c, rs in sorted(tgt.items()):
        if len(rs) > 1:
            # hp_total tiap anggota = HP terpakai FDT + HP cluster itu; dua anggota ke FDT yang sama: tambah HP anggota lain
            base = max(int((r.get("colo_info") or {}).get("hp_total") or 0) for r in rs)
            tot = base + sum(int(r.get("hp") or 0) for r in rs[1:])
            if tot > fdt_cap:
                over.append("FDT %s dipilih %d anggota (%s): total %d HP > %d HP" % (
                    c, len(rs), ", ".join(_sname(r) for r in rs), tot, fdt_cap))
    n_target = len(tgt) + (1 if baru else 0)
    terpadu = None
    if one_net and (tgt or baru):
        terpadu = n_target <= 1 and not over
    return {"lines": L, "terpadu": terpadu, "n_target": n_target, "targets": sorted(tgt), "baru": len(baru),
            "over": over}


def _group_remarks(kind, status, wil, mem, n_hp, ov_pairs, ov_hp, pole_new, pole_ex, plan, n_mix, docs_short,
                   max_len=255, cross_fun=0, n_cov=0, tol_pairs=0):
    """Remarks kesimpulan grup <= 255 karakter: alasan grup paling berat dulu (versi panjang lalu pendek)."""
    st = "REJECT" if status.startswith("REJECT") else ("BELUM LENGKAP" if status.startswith("BELUM") else
                                                     ("APPROVE DGN CATATAN" if "CATATAN" in status else "APPROVE"))
    title = {"jaringan": "grup 1 PIC", "paket": "paket 1 PIC", "berdampingan": "grup berdampingan"}[kind]
    head = "%s %s %s(%d cluster, %s HP): " % (st, title, (wil + " ") if wil else "", len(mem), _num(n_hp))
    cand = []
    if ov_pairs:
        cand.append(("%d pasang boundary tumpang tindih%s (%d HP di irisan)" % (
            ov_pairs, (" (%d lintas funnel)" % cross_fun) if cross_fun else "", ov_hp),
            "%d boundary tumpang tindih" % ov_pairs))
    if pole_new:
        cand.append(("%d tiang baru tercatat di 2 cluster (BOQ ganda)" % pole_new, "%d tiang BOQ ganda" % pole_new))
    if plan and plan.get("over"):
        cand.append(("kapasitas FDT colo terlampaui (%s)" % "; ".join(x.split(":")[0] for x in plan["over"][:2]),
                     "kapasitas FDT colo terlampaui"))
    if plan and plan.get("terpadu") is False:
        nx = len(plan["targets"])
        cand.append(("FDT tdk terpadu (%s%s)" % ("%d FDT existing" % nx if nx else "",
                                                ("%s+ FDT baru" % (" " if nx else "")) if plan["baru"] else ""),
                     "FDT tdk terpadu"))
    if n_mix:
        cand.append(("%d HP berlabel cluster lain di HPDB" % n_mix, "label HPDB campur"))
    if pole_ex:
        cand.append(("%d tiang eksisting dicatat 2 cluster" % pole_ex, "tiang eksisting ganda"))
    if docs_short:
        cand.append((docs_short, docs_short))
    n_rej = sum(1 for r in mem if ((r.get("remarks") or {}).get("status") == "REJECT"))
    if n_rej:
        cand.append(("%d/%d anggota reject" % (n_rej, len(mem)), "%d anggota reject" % n_rej))
    if tol_pairs:
        cand.append(("%d boundary bertumpuk diterima (1 PIC)" % tol_pairs, "bertumpuk 1 PIC diterima"))
    if n_cov:
        cand.append(("%d HP tercover tiang saudara" % n_cov, "%d HP via tiang saudara" % n_cov))
    text = head.rstrip()
    for long_, short_ in cand:
        for c in (long_, short_):
            sep = " " if text.endswith(":") else "; "
            if len(text) + len(sep) + len(c) <= max_len:
                text += sep + c
                break
    if text.endswith(":"):
        text += " tidak ada temuan grup"
    return text


def summarize(g, hp_per_spl=32, fdt_cap=384, ratio=4):
    """Ringkasan satu grup -> dict(ids, n_hp, spl, fdt, shared, one_net, status, lines[], remarks, ...)."""
    mem = g["members"]
    ids = [short_id(r.get("label"), r.get("cl_id")) for r in mem]
    by = g["by"]
    n_hp = sum(int(r.get("hp") or 0) for r in mem)
    spl = int(math.ceil(n_hp / float(hp_per_spl or 32))) if n_hp else 0
    n_fdt = int(math.ceil(n_hp / float(fdt_cap or 384))) if n_hp else 0
    shared = sum(len(p.get("shared") or []) for _a, _b, p in g["links"])
    one_net = any(p.get("one_net") for _a, _b, p in g["links"])
    st = [((r.get("remarks") or {}).get("status") or ("BELUM DIJALANKAN" if r.get("missing") else "-")) for r in mem]
    if any(s == "REJECT" for s in st):
        status = "REJECT (minimal satu anggota reject)"
    elif any(s in ("BELUM DIJALANKAN", "-") for s in st):
        status = "BELUM LENGKAP (ada anggota yang belum dicek)"
    elif any(s.startswith("APPROVE DENGAN") for s in st):
        status = "APPROVE DENGAN CATATAN"
    else:
        status = "APPROVE"
    kind = group_kind(g["links"])
    wil = wilayah_name([r.get("label") for r in mem])
    # dokumen/batas yang sama di beberapa anggota (union pasangan bertanda 'BOUNDARY identik' / 'BAKP identik')
    def members_with(word):
        ks = set()
        for a, b, p in g["links"]:
            if any(word in x for x in p.get("signals") or []):
                ks.update((a, b))
        return ks
    bnd_k, bakp_k = members_with("BOUNDARY identik"), members_with("BAKP identik")
    # 3.10.0: TSSR identik (sidik berkas yang sama di anggota grup)
    tsha = {}
    for r in mem:
        if r.get("tssr_sha"):
            tsha.setdefault(r["tssr_sha"], []).append(r)
    tssr_same = max(tsha.values(), key=len) if tsha else []
    tssr_same = tssr_same if len(tssr_same) >= 2 else []
    bnd_nm = ""
    for _a, _b, p in g["links"]:
        for x in p.get("signals") or []:
            m = re.search(r"BOUNDARY identik \('(.+)'\)", x)
            if m:
                bnd_nm = m.group(1)
    # 3.10.0: irisan BOUNDARY, tiang bersama per jenis, label HPDB campur
    ov_pairs, ov_m2, ov_hp, ov_lines = 0, 0.0, 0, {}
    tol_pairs, tol_m2, tol_hp, cross_fun = 0, 0.0, 0, 0
    pole_new = pole_ex = pole_unk = 0
    for a, b, p in g["links"]:
        o = p.get("overlap")
        n_o_ = int((o or {}).get("n_own") or 0) + int((o or {}).get("n_sib") or 0)
        if o and o.get("m2") and not (o.get("serious") or n_o_ or float(o["m2"]) >= TOUCH_M2):
            # irisan sangat kecil tanpa HP = garis batas bersinggungan (RT 01 x RT 02: +-2 m2), bukan tumpang tindih
            ov_lines[(a, b)] = "bersinggungan (irisan +-%s m2, tanpa HP)" % _num(o["m2"])
            o = None
        if o and o.get("m2") and o.get("tolerated"):
            # 3.11.0: bertumpuk dalam 1 PIC / satu funnel = diterima (dicatat, tidak dihitung sebagai masalah)
            tol_pairs += 1
            tol_m2 += float(o["m2"])
            tol_hp += n_o_
        elif o and o.get("m2"):
            ov_pairs += 1
            ov_m2 += float(o["m2"])
            ov_hp += n_o_
            if o.get("beda_funnel"):
                cross_fun += 1
        if o and o.get("m2"):
            own_k = p.get("_from") or a
            oth_k = b if own_k == a else a
            parts = []
            if o.get("n_own"):
                parts.append("%d HP %s%s" % (o["n_own"], _sname(by[own_k]),
                                             (" baris %s" % _rows(o.get("own_rows"))) if o.get("own_rows") else ""))
            if o.get("n_sib"):
                parts.append("%d HP %s%s" % (o["n_sib"], _sname(by[oth_k]),
                                             (" baris %s" % _rows(o.get("sib_rows"))) if o.get("sib_rows") else ""))
            ov_lines[(a, b)] = "irisan +-%s m2%s%s" % (
                _num(o["m2"]), (": " + "; ".join(parts)) if parts else ", tanpa HP",
                " - DITERIMA (1 PIC, satu funnel/wilayah induk)" if o.get("tolerated") else
                " - LINTAS FUNNEL (perlu diperbaiki)" if o.get("beda_funnel") else " - perlu diperbaiki")
        for ka, kb in p.get("pole_kinds") or []:
            if "new" in (ka, kb):
                pole_new += 1
            elif ka == "existing" and kb == "existing":
                pole_ex += 1
            else:
                pole_unk += 1
    n_mix = sum(int(r.get("label_mix") or 0) for r in mem)
    plan = fdt_plan(mem, one_net, n_hp, fdt_cap)
    L = []
    L.append("GRUP %s: %s" % (KIND_TITLE[kind], " + ".join(ids)))
    L.append("  Status grup      : %s" % status)
    if wil:
        L.append("  Wilayah induk    : %s (%d cluster)" % (wil, len(mem)))
    docs = []
    if bnd_k:
        docs.append("BOUNDARY identik%s di %d cluster (boundary induk belum dipotong per cluster)" % (
            (" '%s'" % bnd_nm) if bnd_nm else "", len(bnd_k)))
    if bakp_k:
        docs.append("file BAKP identik di %d cluster (BAKP harus mencantumkan ID & HP setiap cluster)" % len(bakp_k))
    if tssr_same:
        hp_t = sorted({r.get("tssr_hp") for r in tssr_same if r.get("tssr_hp")})
        docs.append("file TSSR identik di %d cluster (%sperlu TSSR/lampiran per cluster)" % (
            len(tssr_same), ("%s HP; " % "/".join(_num(x) for x in hp_t)) if hp_t else ""))
    if docs:
        L.append("  Dokumen bersama  : %s" % "; ".join(docs))
    cap = n_fdt * (fdt_cap or 384)
    L.append("  Total HP grup    : %d -> %d splitter 1x%d (%d HP/splitter), %s%s" % (
        n_hp, spl, ratio, hp_per_spl, "muat 1 FDT %d HP" % fdt_cap if n_fdt <= 1 else "butuh %d FDT %d HP" % (n_fdt, fdt_cap),
        (" (kapasitas %d HP, sisa %d HP = %.0f%%%s)" % (cap, cap - n_hp, 100.0 * (cap - n_hp) / cap,
                                                       "; cadangan tipis, rencanakan pertumbuhan" if cap and
                                                       (cap - n_hp) < 0.05 * cap else "")) if cap else ""))
    if plan["lines"]:
        verdict = {True: "TERPADU", False: "TIDAK TERPADU - anggota satu jaringan memakai %d rencana FDT berbeda; "
                                           "tentukan satu rencana FDT/feeder grup" % plan["n_target"],
                   None: "-"}[plan["terpadu"]]
        L.append("  Rencana FDT grup : %s" % verdict)
        for x in plan["lines"] + plan["over"]:
            L.append("    - %s" % x)
    if shared:
        jn = []
        if pole_new:
            jn.append("%d tiang BARU (BOQ ganda)" % pole_new)
        if pole_ex:
            jn.append("%d tiang eksisting di kedua cluster (catat sekali, sewa/attachment)" % pole_ex)
        if pole_unk:
            jn.append("%d jenis tidak terbaca" % pole_unk)
        L.append("  Tiang dua cluster: %d tiang tercatat di dua KMZ%s -> tiang grup harus dihitung sekali" % (
            shared, (": " + "; ".join(jn)) if jn else ""))
    if ov_pairs:
        L.append("  BOUNDARY irisan  : %d pasang tumpang tindih PERLU DIPERBAIKI%s, total +-%s m2, %d HP berada di irisan "
                 "(rincian di hubungan antar anggota)" % (ov_pairs, (" (%d lintas funnel)" % cross_fun) if cross_fun else "",
                                                          _num(ov_m2), ov_hp))
    if tol_pairs:
        L.append("  BOUNDARY bertumpuk diterima: %d pasang (1 PIC/berdampingan, satu funnel/wilayah induk), +-%s m2, %d HP "
                 "di irisan - bukan alasan reject; pastikan setiap rumah hanya di HPDB satu cluster" % (
                     tol_pairs, _num(tol_m2), tol_hp))
    n_cov = sum(int(r.get("hp_cover_sib") or 0) for r in mem)
    if n_cov:
        L.append("  HP tercover tiang saudara: %d HP > 50 m ke tiang sendiri dilayani tiang cluster saudara (%s) - desain drop "
                 "dari tiang bersama, bukan alasan reject" % (n_cov, "; ".join(
                     "%s %d HP" % (_sname(r), r["hp_cover_sib"]) for r in mem if r.get("hp_cover_sib"))))
    if n_mix:
        L.append("  Label HPDB       : %s" % "; ".join("%s %d HP berlabel cluster lain" % (_sname(r), r["label_mix"])
                                                     for r in mem if r.get("label_mix")))
    L.append("  Hubungan antar anggota:")
    all_bakp = len(bakp_k) == len(mem)
    only_doc = 0
    for a, b, p in sorted(g["links"], key=lambda t: (t[0], t[1])):
        ra, rb = by[a], by[b]
        sg = [x for x in (p.get("signals") or []) if not (all_bakp and x == "file BAKP identik")]
        if (a, b) in ov_lines:
            if ov_lines[(a, b)].startswith("bersinggungan"):
                sg = [x for x in sg if x != "BOUNDARY tumpang tindih/bersinggungan"]
            sg.append(ov_lines[(a, b)])
        if not sg:
            only_doc += 1          # pasangan yang hanya terkait dokumen bersama: sudah disebut sekali di 'Dokumen bersama'
            continue
        L.append("    - %s <-> %s: %s" % (_sid(ra), _sid(rb), "; ".join(sg)))
    if only_doc:
        L.append("    (+%d pasangan lain hanya terkait file BAKP identik, lihat 'Dokumen bersama')" % only_doc)
    L.append("  Anggota:")
    for r, s in zip(mem, st):
        rm = r.get("remarks") or {}
        L.append("    - %-12s %4s HP  %-22s %s" % (short_id(r.get("label"), r.get("cl_id")), r.get("hp") or "?", s,
                                                  rm.get("text") or ("(belum dijalankan: %s)" % r.get("dir") if r.get("missing") else "")))
    dshort = "/".join(x for x, ok in (("BAKP", bool(bakp_k)), ("TSSR", bool(tssr_same))) if ok)
    rmk = _group_remarks(kind, status, wil, mem, n_hp, ov_pairs, ov_hp, pole_new, pole_ex, plan, n_mix,
                         ("%s blm per cluster" % dshort) if dshort else "", cross_fun=cross_fun, n_cov=n_cov,
                         tol_pairs=tol_pairs)
    L.append("  Remarks grup (%d kar.): %s" % (len(rmk), rmk))
    L.append("  Saran review grup: tiang bersama dihitung sekali di satu cluster (di cluster lain jadi existing/bersama); "
             "satu rumah satu cluster; BOUNDARY tidak saling masuk; satu rencana FDT untuk %d HP; BAKP mencantumkan "
             "semua ID cluster grup." % n_hp)
    return {"ids": ids, "n_hp": n_hp, "spl": spl, "fdt": n_fdt, "shared": shared, "one_net": one_net,
            "status": status, "lines": L, "kind": kind, "wilayah": wil, "bnd_same": len(bnd_k), "bnd_name": bnd_nm,
            "bakp_same": len(bakp_k), "tssr_same": len(tssr_same), "remarks": rmk, "overlap_pairs": ov_pairs,
            "overlap_hp": ov_hp, "plan": plan, "pole_new": pole_new, "pole_existing": pole_ex,
            "tol_pairs": tol_pairs, "tol_hp": tol_hp, "cross_funnel": cross_fun, "hp_cover_sib": n_cov}


# ----------------------------------------------------------------------------------------- STRAND (wilayah induk)
def strands(results, grps=None):
    """Strand = cluster yang berasal dari satu wilayah induk (3.10.0): funnel cluster sama, file BAKP identik, file TSSR
    identik, atau satu grup 1 PIC. Satu strand bisa berisi beberapa sub-jaringan yang terpisah jauh (review Suka Karya
    2026: 13 cluster RT, satu funnel 'RT 014', satu BAKP & satu TSSR, dua sub-jaringan +-300 m terpisah).
    -> [dict(members, groups=[ringkasan grup...], basis={jenis: n}, name)] hanya strand >= 2 cluster, urut nama."""
    rs = [r for r in results if r and r.get("dir")]
    parent = list(range(len(rs)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        a, b = find(i), find(j)
        if a != b:
            parent[max(a, b)] = min(a, b)
    keys = {}
    for i, r in enumerate(rs):
        for kind, v in (("funnel", (r.get("funnel") or "").strip().upper()), ("bakp", r.get("bakp_sha") or ""),
                        ("tssr", r.get("tssr_sha") or "")):
            if v:
                keys.setdefault((kind, v), []).append(i)
    for idx in keys.values():
        for j in idx[1:]:
            union(idx[0], j)
    pos = {norm_dir(r["dir"]): i for i, r in enumerate(rs)}
    for g in grps or groups(rs):
        ii = [pos[norm_dir(m["dir"])] for m in g["members"] if norm_dir(m.get("dir")) in pos]
        for j in ii[1:]:
            union(ii[0], j)
    comp = {}
    for i in range(len(rs)):
        comp.setdefault(find(i), []).append(i)
    out = []
    for ii in comp.values():
        if len(ii) < 2:
            continue
        mem = sorted((rs[i] for i in ii), key=_sid)
        basis = {}
        for (kind, v), idx in keys.items():
            n = len([i for i in idx if i in ii])
            if n >= 2:
                basis[kind] = max(basis.get(kind, (0, ""))[0], n), (v if kind == "funnel" else "")
        out.append({"members": mem, "basis": basis})
    out.sort(key=lambda s_: _sid(s_["members"][0]))
    return out


def summarize_strand(st, grp_sums, hp_per_spl=32, fdt_cap=384):
    """Ringkasan strand -> dict(name, lines, remarks, n_hp, groups). grp_sums: [(grup, ringkasan)] semua grup batch."""
    mem = st["members"]
    keys = {norm_dir(r["dir"]) for r in mem}
    subs = [(g, s_) for g, s_ in grp_sums if {norm_dir(m["dir"]) for m in g["members"]} & keys]
    in_grp = {norm_dir(m["dir"]) for g, _s in subs for m in g["members"]}
    alone = [r for r in mem if norm_dir(r["dir"]) not in in_grp]
    n_hp = sum(int(r.get("hp") or 0) for r in mem)
    fun = (st["basis"].get("funnel") or (0, ""))[1]
    com = {}
    for r in mem:
        if r.get("commercial"):
            com[r["commercial"]] = com.get(r["commercial"], 0) + 1
    com_nm = max(com, key=lambda k: (com[k], k)) if com else ""
    name = fun or (com_nm if com.get(com_nm, 0) >= 2 else "") or wilayah_name([r.get("label") for r in mem]) or \
        " + ".join(_sid(r) for r in mem[:3])
    base_ = {os.path.basename(str(r.get("dir") or "").rstrip("\\/")) for r in mem}
    outside = sorted({x for r in mem for x in (r.get("tssr_shared") or [])} - base_)
    n_all = len(mem) + len(outside)
    L = ["STRAND / WILAYAH INDUK: %s (%d cluster%s, %s HP)" % (
        name, len(mem), (" diperiksa dari %d" % n_all) if outside else "", _num(n_hp))]
    bs = []
    for kind, word in (("funnel", "funnel cluster sama"), ("bakp", "file BAKP identik"), ("tssr", "file TSSR identik")):
        if kind in st["basis"]:
            bs.append("%s (%d cluster)" % (word, st["basis"][kind][0]))
    if com_nm and com[com_nm] >= 2:
        bs.append("CLUSTER_COMMERCIAL_NAME '%s' (%d cluster)" % (com_nm, com[com_nm]))
    L.append("  Dasar            : %s" % ("; ".join(bs) or "grup 1 PIC"))
    if outside:
        L.append("  Di luar run ini  : TSSR yang sama juga ada di %d cluster lain (%s%s) -> jalankan folder induk (mode batch) "
                 "untuk rekap strand lengkap" % (len(outside), ", ".join(outside[:6]), " ..." if len(outside) > 6 else ""))
    L.append("  Sub-jaringan     : %d grup%s" % (len(subs), (" + %d cluster berdiri sendiri" % len(alone)) if alone else ""))
    for k, (g, s_) in enumerate(subs, 1):
        L.append("    %d. %s, %d cluster, %s HP, %s: %s" % (
            k, {"jaringan": "satu jaringan", "paket": "paket 1 PIC", "berdampingan": "berdampingan"}[s_["kind"]],
            len(g["members"]), _num(s_["n_hp"]), s_["status"].split(" (")[0], ", ".join(_sname(m) for m in g["members"])))
    for r in alone:
        L.append("    - %s, %s HP, %s (tidak bertetangga dengan anggota lain)" % (
            _sname(r), r.get("hp") or "?", (r.get("remarks") or {}).get("status") or "-"))
    # HP dokumen vs HPDB
    t_hp = sorted({int(r["tssr_hp"]) for r in mem if r.get("tssr_hp") and r.get("tssr_shared")})
    hp_line = []
    if t_hp:
        for v in t_hp:
            hp_line.append("TSSR strand %s HP vs total HPDB %s HP (selisih %+d): TSSR/lampiran rincian HP per cluster "
                           "wajib%s" % (_num(v), _num(n_hp), v - n_hp,
                                        "; ada HP TSSR yang belum diajukan di cluster mana pun" if v > n_hp else ""))
    if "bakp" in st["basis"]:
        hp_line.append("BAKP bersama %d cluster: baca manual Homepass BAKP, harus >= %s HP (total HPDB strand) dan "
                       "mencantumkan ID & HP setiap cluster" % (st["basis"]["bakp"][0], _num(n_hp)))
    for x in hp_line:
        L.append("  Dokumen          : %s" % x)
    mix = [r for r in mem if r.get("label_mix")]
    if mix:
        L.append("  Label HPDB campur: %s" % "; ".join("%s %d HP" % (_sname(r), r["label_mix"]) for r in mix))
    n_rej = sum(1 for r in mem if (r.get("remarks") or {}).get("status") == "REJECT")
    st_txt = "REJECT" if n_rej else ("APPROVE" if all((r.get("remarks") or {}).get("status") == "APPROVE" for r in mem)
                                     else "APPROVE DGN CATATAN")
    cand = []
    docs = [w for k_, w in (("bakp", "BAKP"), ("tssr", "TSSR")) if k_ in st["basis"]]
    if docs:
        cand.append(("%s 1 dokumen utk %d cluster%s, wajib rincian ID & HP per cluster" % (
            " & ".join(docs), len(mem), (" (TSSR %s HP vs HPDB %s HP)" % (_num(t_hp[0]), _num(n_hp))) if t_hp else ""),
            "%s strand wajib rincian per cluster" % "/".join(docs)))
    ovs = sum(s_["overlap_pairs"] for _g, s_ in subs)
    if ovs:
        cand.append(("%d pasang boundary tumpang tindih (%d HP di irisan)" % (ovs, sum(s_["overlap_hp"] for _g, s_ in subs)),
                     "%d boundary tumpang tindih" % ovs))
    if any(s_["plan"]["terpadu"] is False for _g, s_ in subs):
        cand.append(("rencana FDT sub-jaringan tdk terpadu", "FDT tdk terpadu"))
    if mix:
        cand.append(("%d HP berlabel cluster lain di HPDB" % sum(r["label_mix"] for r in mix), "label HPDB campur"))
    if n_rej:
        cand.append(("%d/%d cluster reject" % (n_rej, len(mem)), "%d reject" % n_rej))
    ncl = ("%d dari %d cluster" % (len(mem), n_all)) if outside else ("%d cluster" % len(mem))
    text = ("%s strand %s (%s, %s HP, %d sub-jaringan):" % (st_txt, name, ncl, _num(n_hp), len(subs) + len(alone)))
    if len(text) > 120:
        text = "%s strand (%s, %s HP, %d sub-jaringan):" % (st_txt, ncl, _num(n_hp), len(subs) + len(alone))
    for long_, short_ in cand:
        for c in (long_, short_):
            sep = " " if text.endswith(":") else "; "
            if len(text) + len(sep) + len(c) <= 255:
                text += sep + c
                break
    L.append("  Remarks strand (%d kar.): %s" % (len(text), text))
    L.append("  Saran review strand: nilai dokumen (BAKP/TSSR) di level strand dan desain (boundary, tiang, FDT) per "
             "sub-jaringan; rekonsiliasi HP BAKP/TSSR/HPDB per cluster; satu label CLUSTER_NAME per HPDB.")
    return {"name": name, "lines": L, "remarks": text, "n_hp": n_hp, "groups": len(subs), "alone": len(alone),
            "members": mem}


def write_report(path_txt, g, s, product="Seranta", when=""):
    """REKAP_GRUP_1PIC_<ID>.txt + .csv (pemisah ';', UTF-8 BOM untuk Excel)."""
    import csv
    head = ["REKAP GRUP 1 PIC DESAIN / JARINGAN BERSAMA", "Dibuat  : %s (%s)" % (when, product), ""]
    with open(path_txt, "w", encoding="utf-8") as fh:
        fh.write("\n".join(head + s["lines"]) + "\n")
    path_csv = os.path.splitext(path_txt)[0] + ".csv"
    with open(path_csv, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["grup", "status_grup", "total_hp_grup", "splitter_grup", "tiang_dua_cluster", "cluster_id", "cluster",
                    "hp", "status", "remarks", "folder", "remarks_grup"])
        for r in g["members"]:
            rm = r.get("remarks") or {}
            w.writerow([" + ".join(s["ids"]), s["status"], s["n_hp"], s["spl"], s["shared"],
                        short_id(r.get("label"), r.get("cl_id")), r.get("label") or "", r.get("hp") or "",
                        rm.get("status") or ("BELUM DIJALANKAN" if r.get("missing") else ""), rm.get("text") or "",
                        r.get("dir") or "", s.get("remarks") or ""])
    return path_txt, path_csv


def write_strand(path_txt, ss, product="Seranta", when=""):
    """REKAP_STRAND_<nama>.txt + .csv (3.10.0)."""
    import csv
    head = ["REKAP STRAND / WILAYAH INDUK", "Dibuat  : %s (%s)" % (when, product), ""]
    with open(path_txt, "w", encoding="utf-8") as fh:
        fh.write("\n".join(head + ss["lines"]) + "\n")
    path_csv = os.path.splitext(path_txt)[0] + ".csv"
    with open(path_csv, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["strand", "total_hp_strand", "sub_jaringan", "cluster_id", "cluster", "hp", "status", "remarks",
                    "remarks_strand"])
        for r in ss["members"]:
            rm = r.get("remarks") or {}
            w.writerow([ss["name"], ss["n_hp"], ss["groups"] + ss["alone"], _sid(r), r.get("label") or "",
                        r.get("hp") or "", rm.get("status") or "", rm.get("text") or "", ss["remarks"]])
    return path_txt, path_csv

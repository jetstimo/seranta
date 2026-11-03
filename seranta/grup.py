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


def summarize(g, hp_per_spl=32, fdt_cap=384, ratio=4):
    """Ringkasan satu grup -> dict(ids, n_hp, spl, fdt, shared, one_net, status, lines[])."""
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
    bnd_nm = ""
    for _a, _b, p in g["links"]:
        for x in p.get("signals") or []:
            m = re.search(r"BOUNDARY identik \('(.+)'\)", x)
            if m:
                bnd_nm = m.group(1)
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
    if docs:
        L.append("  Dokumen bersama  : %s" % "; ".join(docs))
    L.append("  Total HP grup    : %d -> %d splitter 1x%d (%d HP/splitter), %s" % (
        n_hp, spl, ratio, hp_per_spl, "muat 1 FDT %d HP" % fdt_cap if n_fdt <= 1 else "butuh %d FDT %d HP" % (n_fdt, fdt_cap)))
    if shared:
        L.append("  Tiang dua cluster: %d tiang tercatat di dua KMZ -> BOQ tiang grup harus dihitung sekali" % shared)
    L.append("  Hubungan antar anggota:")
    for a, b, p in sorted(g["links"], key=lambda t: (t[0], t[1])):
        ra, rb = by[a], by[b]
        L.append("    - %s <-> %s: %s" % (short_id(ra.get("label"), ra.get("cl_id")), short_id(rb.get("label"), rb.get("cl_id")),
                                          "; ".join(p.get("signals") or []) or "-"))
    L.append("  Anggota:")
    for r, s in zip(mem, st):
        rm = r.get("remarks") or {}
        L.append("    - %-12s %4s HP  %-22s %s" % (short_id(r.get("label"), r.get("cl_id")), r.get("hp") or "?", s,
                                                  rm.get("text") or ("(belum dijalankan: %s)" % r.get("dir") if r.get("missing") else "")))
    L.append("  Saran review grup: tiang bersama dihitung sekali di satu cluster (di cluster lain jadi existing/bersama); "
             "satu rumah satu cluster; BOUNDARY tidak saling masuk; satu rencana FDT untuk %d HP; BAKP mencantumkan "
             "semua ID cluster grup." % n_hp)
    return {"ids": ids, "n_hp": n_hp, "spl": spl, "fdt": n_fdt, "shared": shared, "one_net": one_net,
            "status": status, "lines": L, "kind": kind, "wilayah": wil, "bnd_same": len(bnd_k), "bnd_name": bnd_nm,
            "bakp_same": len(bakp_k)}


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
                    "hp", "status", "remarks", "folder"])
        for r in g["members"]:
            rm = r.get("remarks") or {}
            w.writerow([" + ".join(s["ids"]), s["status"], s["n_hp"], s["spl"], s["shared"],
                        short_id(r.get("label"), r.get("cl_id")), r.get("label") or "", r.get("hp") or "",
                        rm.get("status") or ("BELUM DIJALANKAN" if r.get("missing") else ""), rm.get("text") or "",
                        r.get("dir") or ""])
    return path_txt, path_csv

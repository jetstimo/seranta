# -*- coding: utf-8 -*-
"""
Seranta - FTTH Design Assistant
Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-2.0-or-later.

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
    return m.group(1) if m else (label or "?")[:30]


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
    L = []
    L.append("GRUP %s: %s" % ("SATU JARINGAN (1 PIC desain)" if one_net else "KEMUNGKINAN 1 PIC desain (jaringan terpisah)",
                              " + ".join(ids)))
    L.append("  Status grup      : %s" % status)
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
            "status": status, "lines": L}


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

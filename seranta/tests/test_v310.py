# -*- coding: utf-8 -*-
"""Uji unit Seranta 3.10.0 (tanpa QGIS): python3 test_seranta_3_10.py <folder_plugin_seranta>"""
import sys, os
sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "seranta"))
import konsistensi as K, remarks as R, grup as G, lintas_cluster as LC

ok = 0
def check(cond, msg):
    global ok
    assert cond, msg
    ok += 1

# --- konsistensi ---
check(K.ring_self_intersections([(0, 0), (2, 2), (2, 0), (0, 2), (0, 0)]) == [(1.0, 1.0)], "kupu-kupu = 1 titik potong")
check(K.ring_self_intersections([(0, 0), (1, 0), (1, 1), (0, 1)]) == [], "persegi sah")
check(K.ring_self_intersections([(0, 0), (1, 0), (1, 0), (1, 1), (0, 1), (0, 0)]) == [], "titik ganda bukan potong")
check(K.norm_cluster_name("SUKA KARYA RT16") == K.norm_cluster_name("Suka  Karya RT 016"), "format nama diabaikan")
m = K.label_mix(["SUKA KARYA RT 08"] * 110 + ["SUKA KARYA RT16"] * 6, list(range(2, 118)), ["8"] * 116,
                "SUKA KARYA RT 08_116HP_REV", ["SUKA KARYA RT 16"])
check(m["minor"] and m["minor"][0]["n"] == 6 and m["minor"][0]["rows"] == list(range(112, 118)), "6 HP RT16 di RT 08")
check(m["minor"][0]["sibling"] == "SUKA KARYA RT 16", "dikenali sebagai label cluster saudara")
m = K.label_mix(["A RT 1"] * 3 + ["A RT1"], [2, 3, 4, 5])
check(not m["minor"] and m["format_only"], "beda penulisan saja = info")
m = K.label_mix(["X RT 12"] * 15 + ["X RT 04"] * 118, list(range(2, 135)), None, "X KOTA RT 04_133HP")
check(m["major"][0] == "X RT 04", "mayoritas mengikuti RT nama folder")
check(K.hp_in_name("TSSR_X RT 16_62HP_PT.EKSPANINDO.docx") == 62 and K.hp_in_name("A - (38HP) RPS") == 38, "HP di nama")
check(K.hp_in_name("SUKA KARYA RT 16_56 HP_REV") == 56 and K.hp_in_name("RT 16 BAKP.pdf") is None, "HP di nama (2)")
check(K.filename_hp_mismatch([("KMZ", "a_62HP.kmz"), ("TSSR", "b_56HP.docx")], 56) == [("KMZ", "a_62HP.kmz", 62)], "mismatch")
st, tx = K.admin_vs_hp_sheet(("KOTA BARU", "SUKA KARYA", "KOTA JAMBI"), ("SUKA KARYA", "KOTA BARU", "KOTA JAMBI"))
check(st == "TERTUKAR", "kolom kelurahan/kecamatan tertukar")
check(K.admin_vs_hp_sheet(("SUKA KARYA", "KOTA BARU", "KOTA JAMBI"), ("Suka Karya", "Kota Baru", "Kota Jambi"))[0] == "SAMA", "sama")
check(K.admin_vs_hp_sheet(("PAAL MERAH", "JAMBI SELATAN", "KOTA JAMBI"), ("SUKA KARYA", "KOTA BARU", "KOTA JAMBI"))[0] == "BEDA",
      "beda = lanjut cek FINDIM")

# --- lintas_cluster ---
check(LC.pole_kind_of("EP", "POLE / EP") == "existing" and LC.pole_kind_of("NP6-01", "POLE / T6") == "new", "jenis tiang")
check(LC.pole_kind_of("", "POLE / TE") == "existing", "TE = eksisting")
a = [[(103.6, -1.6), (103.601, -1.6)]]
b = [[(103.6002, -1.6), (103.6012, -1.6)]]
check(round(LC.shared_route_m(a, b)[0]) == round(LC.shared_route_m(b, a)[0]), "contoh simetris")
sp = LC.shared_poles([(1.0, 1.0, "EP")], [(1.0000001, 1.0, "EP")])
check(len(sp[0]) == 7 and sp[0][5] == 0 and sp[0][6] == 0, "indeks tiang bersama")

# --- remarks ---
HP = lambda r, nm: {"kind": "HP_DI_BOUNDARY_CLUSTER_LAIN", "sev": "ERROR", "val": 12, "lim": 10,
                    "ket": "baris %d (H%05d) (no. rumah -) berada 12.0 m di dalam BOUNDARY cluster %s (> 10 m)." % (r, r - 1, nm)}
OV = lambda nm, a, n_o, ro, n_s, rs: {"kind": "WARN_BOUNDARY_BERIRISAN_CLUSTER_LAIN", "sev": "WARNING", "val": a, "lim": None,
                                      "ket": "BOUNDARY cluster ini tumpang tindih dengan BOUNDARY cluster %s: luas irisan +-%d m2, "
                                             "lebar maks +-40 m; di dalam irisan ada %d HP cluster ini%s dan %d HP cluster %s%s. "
                                             "Rapikan garis BOUNDARY." % (nm, a, n_o, (" (baris %s)" % ro) if ro else "", n_s, nm,
                                                                          (" (baris %s)" % rs) if rs else "")}
r = R.build([HP(48, "RT 11_61HP"), HP(49, "RT 11_61HP"), OV("RT 11_61HP", 6350, 8, "2, 10, 11, 48-52", 0, "")])
check(r["status"] == "REJECT" and "masuk boundary RT 11 (baris 48" not in r["text"] and "48-52" in r["text"],
      "HP di irisan digabung ke frasa tumpang tindih: " + r["text"])
r = R.build([HP(90, "RT 18_53HP"), OV("RT 18_53HP", 2060, 2, "90, 91", 0, "")] +
            [OV("RT 10_60HP", 7790, 8, "78, 79, 82-87", 8, "3-10"), OV("RT 05_108HP", 615, 1, "2", 1, "38"),
             {"kind": "BAKP_ADA_GAMBAR_TEMPELAN", "sev": "ERROR", "ket": "halaman 3: gambar tempelan", "val": None, "lim": None}])
check(r["text"].index("RT 10") < r["text"].index("RT 18") and "tempelan" in r["text"], "urut luas & BAKP tetap muat: " + r["text"])
check(r["length"] <= 255, "<= 255")
r = R.build([{"kind": "WARN_TIANG_GANDA_LINTAS_CLUSTER", "sev": "WARNING", "val": 1, "lim": None,
              "ket": "1 tiang cluster ini juga tercatat di KMZ cluster RT 06_90HP (koordinat sama <= 1.0 m): -1.6, 103.5. Jenis: "
                     "1 tiang EKSISTING di kedua cluster (bukan BOQ tiang baru; ...). Satu tiang fisik ..."}])
check("tiang eksisting dicatat 2x" in r["text"] and r["status"] == "REJECT", "tiang eksisting bukan BOQ: " + r["text"])
r = R.build([{"kind": "WARN_TSSR_DIPAKAI_BERSAMA", "sev": "WARNING", "val": 1242, "lim": 65,
              "ket": "TSSR x.docx identik dengan TSSR 12 cluster lain (a, b): TSSR mencatat 1242 HP untuk wilayah induk/strand"}])
check(r["status"] == "APPROVE DENGAN CATATAN" and "12 cluster lain" in r["text"], "TSSR strand = catatan")
check(R.compress_names(["SUKA KARYA RT 07", "SUKA KARYA RT 06", "SUKA KARYA KOTA RT 04"]) == ["SUKA KARYA RT 07", "RT 06", "KOTA RT 04"],
      "nama ringkas")

# --- grup: rencana FDT grup & strand ---
def res(d, hp, colo, info=None, **kw):
    r = {"dir": "/x/" + d, "label": d, "hp": hp, "colo": colo, "colo_info": info, "remarks": {"status": "REJECT", "text": "-"}}
    r.update(kw)
    return r
mem = [res("RT 02", 71, "FDT-A", {"d_entry": 983, "hp_total": 292}), res("RT 05", 108, "FDT-B", {"d_entry": 950, "hp_total": 280}),
       res("RT 01", 65, "FDT baru")]
p = G.fdt_plan(mem, True, 244)
check(p["terpadu"] is False and p["n_target"] == 3, "3 rencana FDT dalam satu jaringan = tidak terpadu")
mem2 = [res("RT 02", 71, "FDT-A", {"d_entry": 900, "hp_total": 300}), res("RT 03", 100, "FDT-A", {"d_entry": 800, "hp_total": 329})]
p = G.fdt_plan(mem2, True, 171)
check(p["over"] and p["terpadu"] is False, "dua anggota ke FDT sama melebihi 384 HP")
check(G.fdt_plan([res("RT 01", 65, "-")], True, 65)["terpadu"] is None, "tanpa Design Lite = belum dinilai")
rs = [res("A RT 01", 10, "-", tssr_sha="t1", bakp_sha="b1"), res("A RT 02", 10, "-", tssr_sha="t1"),
      res("A RT 09", 10, "-", bakp_sha="b1"), res("B RT 01", 10, "-", tssr_sha="t9")]
st = G.strands(rs)
check(len(st) == 1 and len(st[0]["members"]) == 3, "strand dari TSSR/BAKP identik (transitif)")
ss = G.summarize_strand(st[0], [])
check(ss["alone"] == 3 and len(ss["remarks"]) <= 255, "strand tanpa grup")
print("OK: %d pemeriksaan lulus" % ok)

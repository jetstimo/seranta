# -*- coding: utf-8 -*-
"""Uji unit Seranta 3.11.0: toleransi boundary 1 PIC / lintas funnel. python3 test_v311.py <folder plugin seranta>"""
import sys, os
sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), ".."))
import lintas_cluster as LC, remarks as R, grup as G

# dua kotak 200 x 200 m bertumpuk 60 m; HP cluster A di dalam irisan (20 m dari tepi B)
k = 1.0 / 111320.0
def sq(x0, y0, w):
    return ([(x0, y0), (x0 + w * k, y0), (x0 + w * k, y0 + w * k), (x0, y0 + w * k), (x0, y0)], [])
X0, Y0 = 103.6, -1.62
def own(**kw):
    o = {"label": "WIL RT 01_10HP", "kode": "A", "hp": [{"x": X0 + 160 * k, "y": Y0 + 100 * k, "hn": "", "hid": "baris 2 (H00001)",
                                                           "row": 2}],
         "bnd": [sq(X0, Y0, 200)], "poles": [(X0 + 10 * k, Y0 + 10 * k, "NP-1")], "lines": [[(X0, Y0), (X0 + 100 * k, Y0)]],
         "ids_hpdb": set(), "ids_other": set(), "bbox": (X0, Y0, X0 + 200 * k, Y0 + 200 * k), "bakp_sha": "b1"}
    o.update(kw)
    return o
def sib(**kw):
    s = {"dir": "/x/B", "label": "WIL RT 02_10HP", "kode": "B", "hp": [{"x": X0 + 300 * k, "y": Y0 + 100 * k, "hn": "", "row": 2}],
         "bnd": [sq(X0 + 140 * k, Y0, 200)], "poles": [(X0 + 300 * k, Y0 + 10 * k, "NP-9")], "lines": [], "ids_hpdb": set(),
         "ids_other": set(), "kmz": "", "doc": "", "bbox": (X0 + 140 * k, Y0, X0 + 340 * k, Y0 + 200 * k), "hp_src": "HPDB",
         "note": [], "folder_ids": {}, "bakp_sha": "b1", "pole_kinds": ["new"]}
    s.update(kw)
    return s
kinds = lambda r: sorted({f["kind"] for f in r["findings"]})
r = LC.compare(own(funnel_key="RT014", funnel="RT 014"), [sib(funnel_key="RT014", funnel="RT 014")])
assert "INFO_HP_DI_BOUNDARY_SAUDARA_1PIC" in kinds(r) and "INFO_BOUNDARY_BERIRISAN_1PIC" in kinds(r), kinds(r)
assert "HP_DI_BOUNDARY_CLUSTER_LAIN" not in kinds(r) and r["pic"][0]["tolerated"]
r = LC.compare(own(funnel_key="RT014", funnel="RT 014"), [sib(funnel_key="RT022", funnel="RT 022")])
assert "HP_DI_BOUNDARY_CLUSTER_LAIN" in kinds(r) and "WARN_BOUNDARY_BERIRISAN_CLUSTER_LAIN" in kinds(r), kinds(r)
assert any("LINTAS FUNNEL" in f["ket"] for f in r["findings"]) and r["pic"][0]["beda_funnel"]
r = LC.compare(own(bakp_sha="b1"), [sib(bakp_sha="b2")])            # funnel tak diketahui, tanpa bukti satu induk
assert "HP_DI_BOUNDARY_CLUSTER_LAIN" in kinds(r), kinds(r)
r = LC.compare(own(), [sib()])                                          # funnel tak diketahui, BAKP identik = satu induk
assert "INFO_HP_DI_BOUNDARY_SAUDARA_1PIC" in kinds(r), kinds(r)
r = LC.compare(own(), [sib()], tol_1pic=False)                          # saklar profil mati = perilaku lama
assert "HP_DI_BOUNDARY_CLUSTER_LAIN" in kinds(r), kinds(r)
# remarks: temuan diterima jadi catatan, status tidak REJECT karena itu saja
r = LC.compare(own(funnel_key="RT014"), [sib(funnel_key="RT014")])
F = [{"kind": f["kind"], "sev": "INFO", "ket": f["ket"], "val": f["val"], "lim": f["lim"]} for f in r["findings"]]
b = R.build(F)
assert b["status"] == "APPROVE" and any("bertumpuk" in n for n in b["notes"]), b
b = R.build([{"kind": "INFO_HP_TERCOVER_TIANG_SAUDARA", "sev": "INFO", "val": 12.0, "lim": 50.0,
              "ket": "H00017 (baris 18 HPDB): 54.2 m ke tiang terdekat NP-08 (batas 50 m); tikor x -> TERCOVER tiang eksisting "
                     "EP cluster WIL RT 05_108HP 12.0 m (<= 50 m; 1 PIC/berdampingan ...): bukan alasan reject."}])
assert b["status"] == "APPROVE" and "tercover tiang WIL RT 05" in b["notes"][0], b
# rekap grup: pasangan diterima tidak dihitung sebagai masalah
res = [{"dir": "/x/A", "label": "WIL RT 01", "hp": 10, "remarks": {"status": "APPROVE"}, "hp_cover_sib": 2,
        "pic_info": [{"dir": "/x/B", "label": "WIL RT 02", "one_net": False, "signals": ["BOUNDARY tumpang tindih/bersinggungan"],
                      "n_hp": 10, "overlap": {"m2": 5000, "n_own": 1, "n_sib": 0, "own_rows": [2], "sib_rows": [],
                                              "serious": True, "tolerated": True}}]},
       {"dir": "/x/B", "label": "WIL RT 02", "hp": 10, "remarks": {"status": "APPROVE"}, "pic_info": []}]
g = G.groups(res)[0]
sm = G.summarize(g)
assert sm["overlap_pairs"] == 0 and sm["tol_pairs"] == 1 and sm["hp_cover_sib"] == 2, sm
assert any("irisan +-5.000 m2: 1 HP WIL RT 01 baris 2 - DITERIMA" in x for x in sm["lines"]), sm["lines"]
assert sm["remarks"].startswith("APPROVE") and "bertumpuk diterima" in sm["remarks"], sm["remarks"]
print("OK: uji 3.11.0 lulus")

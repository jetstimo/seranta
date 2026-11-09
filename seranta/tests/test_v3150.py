# -*- coding: utf-8 -*-
"""Uji 3.15.0 tanpa QGIS: standar 10 persilangan (jalan_osm.py) - penggolongan lebar/lajur, sungai, XML API OSM,
tiang dekat tol/rel; dan persilangan nyata Bitung (tol Manado-Bitung) & Tegal (rel Tegal-Prupuk) dari data OSM."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import jalan_osm as J  # noqa: E402
import konsistensi as K  # noqa: E402


def ok(cond, msg):
    if not cond:
        print("GAGAL:", msg)
        sys.exit(1)


C = J.classify
ok(C({"highway": "motorway"}) == "tol" and C({"highway": "trunk", "toll": "yes"}) == "tol", "tol")
ok(C({"highway": "primary"}) == "besar" and C({"highway": "trunk_link"}) == "besar", "nasional/arteri")
ok(C({"highway": "residential", "lanes": "4"}) == "besar", ">= 4 lajur = jalan raya (PP 34/2006 Ps 32)")
ok(C({"highway": "secondary", "width": "14 m"}) == "besar" and C({"highway": "tertiary", "width": "7,5"}) == "sedang",
   "lebar >= 14 m")
ok(C({"highway": "unclassified", "lanes:forward": "2", "lanes:backward": "2"}) == "besar", "lajur per arah")
ok(C({"highway": "secondary"}) == "sedang" and C({"highway": "tertiary_link"}) == "sedang", "kolektor")
ok(C({"highway": "residential", "lanes": "2"}) is None and C({"highway": "footway", "width": "20"}) is None, "gang")
ok(C({"waterway": "river"}) == "sungai" and C({"waterway": "drain"}) is None and C({"waterway": "canal", "tunnel": "culvert"})
   is None, "sungai")
ok(C({"railway": "abandoned"}) is None and C({"railway": "rail", "usage": "branch"}) == "rel", "rel nonaktif")

xml = b"""<?xml version='1.0'?><osm version='0.6'>
<node id='1' lat='0.0' lon='0.0'/><node id='2' lat='0.0' lon='0.001'/><node id='3' lat='-0.001' lon='0.0005'/>
<node id='4' lat='0.001' lon='0.0005'/>
<way id='10'><nd ref='1'/><nd ref='2'/><tag k='highway' v='residential'/></way>
<way id='11'><nd ref='3'/><nd ref='4'/><tag k='railway' v='rail'/><tag k='name' v='Rel X'/></way>
<way id='12'><nd ref='3'/><nd ref='1'/><tag k='building' v='yes'/></way></osm>"""
js = J.osm_xml_to_overpass(xml)
ok(len(js["elements"]) == 2, "XML API OSM -> elemen jalan/rel saja")
roads = J.parse_overpass(js)
ok([r["kind"] for r in roads] == ["rel"] and roads[0]["name"] == "Rel X", "parse XML")

# tiang sejajar rel 5 m (tidak memotong) -> dekat rel; 20 m -> aman; tiang yang sudah di temuan persilangan tidak diulang
kx, ky = 111320.0, 110574.0
rail = [{"kind": "rel", "name": "R", "pts": [(0.0, -0.01), (0.0, 0.01)], "tunnel": False}]
np_ = J.near_poles([("NP-1", (5 / kx, 0.0)), ("NP-2", (20 / kx, 0.0)), ("NP-3", (3 / kx, 0.001))], rail, kx, ky, {"NP-3"})
ok([(n["pole"], round(n["d"])) for n in np_] == [("NP-1", 5)], "tiang < 10 m dari rel")
tol = [{"kind": "tol", "name": "T", "pts": [(0.0, -0.01), (0.0, 0.01)], "tunnel": False}]
ok([n["pole"] for n in J.near_poles([("A", (12 / kx, 0)), ("B", (16 / kx, 0))], tol, kx, ky)] == ["A"], "tiang < 15 m tol")

# data OSM nyata (10 Nov 2026, api.openstreetmap.org) di sekitar cluster uji
import json  # noqa: E402
D = os.path.join(HERE, "data_osm")
if os.path.isdir(D):
    def load(fn, key):
        el = [{"type": "way", "id": i, "tags": t, "geometry": [{"lon": p[0], "lat": p[1]} for p in g]}
              for i, t, g in json.load(open(os.path.join(D, fn), encoding="utf-8"))[key]]
        return J.parse_overpass({"elements": el})
    b2 = load("osm_b.json", "b2")
    ok(sum(1 for r in b2 if r["kind"] == "tol") >= 4, "tol Manado-Bitung terbaca")
    # rentang memotong tol di Kakenturan (garis barat-timur melewati tol)
    seg = [("NP-A - NP-B", (125.1945, 1.4500), (125.1965, 1.4504))]
    xr = J.crossings(seg, b2, kx, ky)
    ok([x["kind"] for x in xr] == ["tol"], "persilangan tol Manado-Bitung (dua jalur = satu titik)")
    tg = load("osm_tg.json", "tg")
    seg = [("NP-C - NP-D", (109.1300, -6.9960), (109.1320, -6.9958))]
    xr = J.crossings(seg, tg, kx, ky)
    ok([x["kind"] for x in xr] == ["rel"] and "Tegal" in xr[0]["name"], "persilangan rel Tegal-Prupuk")
# kecepatan: cache dipakai bila kotaknya mencakup wilayah cluster; hasil dipotong ke wilayah cluster
import json as _json  # noqa: E402
import tempfile  # noqa: E402
ok(J._covers((1.0, 1.0, 1.02, 1.02), (1.005, 1.005, 1.015, 1.015)) and not J._covers((1.0, 1.0, 1.02, 1.02),
                                                                                 (1.005, 1.005, 1.03, 1.015)), "cakupan")
with tempfile.TemporaryDirectory() as td:
    box = (125.19, 1.45, 125.2, 1.46)
    with open(J._cache_path(td, box), "w", encoding="utf-8") as fh:
        _json.dump({"seranta_v": 2, "elements": [
            {"type": "way", "tags": {"highway": "motorway"}, "geometry": [{"lon": 125.191, "lat": 1.451},
                                                                         {"lon": 125.192, "lat": 1.452}]},
            {"type": "way", "tags": {"railway": "rail"}, "geometry": [{"lon": 125.198, "lat": 1.458},
                                                                      {"lon": 125.199, "lat": 1.459}]}]}, fh)
    J._MEMO.clear()
    roads, src = J.fetch((125.1905, 1.4505, 125.1935, 1.4535), td)       # tanpa jaringan: dari cache yang mencakup
    ok([r["kind"] for r in roads] == ["tol"] and "cache" in src, "cache mencakup + potong ke wilayah")
    roads, src = J.fetch((125.1975, 1.4575, 125.1995, 1.4595), td)       # kedua kali: dari memori
    ok([r["kind"] for r in roads] == ["rel"], "memori sesi")
    ok(J._cache_find(td, (125.19, 1.45, 125.21, 1.46)) is None, "kotak lebih luas tidak tercakup")
J._MEMO.clear()

# nama berkas memuat RT lain (Pasir Putih RT 17: BAKP bernama RT_023)
fm = K.filename_area_mismatch("PASIR PUTIH RT 17_91HP_REV_up", [
    ("BAKP", "BAKP_JAMBI_21100232552_RT_023_Pasir_Putih_1150HP_AIA.pdf"),
    ("KMZ", "KMZ_JAMBI_IFTJBI0519_PASIR PUTIH RT 17_177HP_AIA.kmz"), ("HPDB", "HPDB_x.xlsx")])
ok(fm == [("BAKP", "BAKP_JAMBI_21100232552_RT_023_Pasir_Putih_1150HP_AIA.pdf", "RT 23", "RT 17")], "BAKP RT 23 vs RT 17")
ok(K.filename_area_mismatch("DUKUHWRINGIN RW 03", [("BAKP", "BAKP RW 003 DUKUHRINGIN.pdf")]) == [], "RW 003 = RW 03")
print("OK")

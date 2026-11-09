# -*- coding: utf-8 -*-
"""Uji 3.14.1 tanpa QGIS: RT/RW HPDB vs wilayah (konsistensi.py) dan persilangan jalan tol/rel (jalan_osm.py)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import konsistensi as K  # noqa: E402
import jalan_osm as J  # noqa: E402


def ok(cond, msg):
    if not cond:
        print("GAGAL:", msg)
        sys.exit(1)


# --- nomor wilayah di nama cluster/Funnel ---
ok(K.area_ref("KAB. MINAHASA-2547640186_LINGKUNGAN 5 GESEL-RINEGETAN_39HP-RPS") == {"RT": set(), "RW": {5}}, "lingkungan 5")
ok(K.area_ref("LINGKUNGAN 1&2-RINEGETAN")["RW"] == {1, 2}, "lingkungan 1&2")
ok(K.area_ref("LINGKUNGAN 1-7-KAKASKASEN")["RW"] == set(range(1, 8)), "rentang 1-7")
ok(K.area_ref("LINGKUNGAN I-IV-SUMALANGKA")["RW"] == {1, 2, 3, 4}, "romawi I-IV")
ok(K.area_ref("SUKA KARYA RT16")["RT"] == {16}, "RT tanpa spasi")
ok(K.area_ref("PASIR PUTIH RT 17_91HP_REV_up") == {"RT": {17}, "RW": set()}, "91HP bukan nomor wilayah")
ok(K.area_ref("SEMEN RW 01 RT -") == {"RT": set(), "RW": {1}}, "RT kosong")
ok(K.parse_numbers("00") == set() and K.parse_numbers("-") == set() and K.parse_numbers("04&5") == {4, 5}, "nilai kolom")

# --- kolom HPDB di luar wilayah ---
mm = K.area_mismatch("LINGKUNGAN 5 GESEL-RINEGETAN", "Funnel cluster ini", list(range(2, 41)), ["00"] * 39,
                     ["03"] * 38 + ["05"], ["RINEGETAN LINGKUNGAN 03"] * 39)
ok([(m["col"], m["n"]) for m in mm] == [("RW/lingkungan", 38), ("CLUSTER_NAME", 39)], "mismatch lingkungan 03 vs 5")
ok(K.area_mismatch("LINGKUNGAN 1&2", "x", [2, 3], ["0", "0"], ["01&2", "01"], ["L 01", "L 02"]) == [], "1&2 sesuai")
mm = K.area_mismatch("PASIR PUTIH RT 17", "nama folder cluster", [2, 3, 4], ["17"] * 3, ["-"] * 3, ["RT 23 PASIR PUTIH"] * 3)
ok(len(mm) == 1 and mm[0]["col"] == "CLUSTER_NAME" and "seharusnya RT 17" in mm[0]["text"], "CLUSTER_NAME RT 23 vs RT 17")

# --- tetangga: RT 24 di tengah RT 17; batas RT alami tidak ditandai ---
xy = [(i * 15.0, j * 15.0) for i in range(5) for j in range(4)]
v = ["17"] * 20
v[6] = "24"
ok(K.neighbour_odd(xy, v) == [(6, 24, 17, 6, 6)], "RT 24 di tengah RT 17")
ok(K.neighbour_odd(xy, ["17"] * 10 + ["18"] * 10) == [], "batas RT alami")
ok(K.neighbour_odd(xy, ["17"] * 20) == [], "seragam")

# --- jalan OSM ---
ok(J.classify({"highway": "motorway"}) == "tol" and J.classify({"highway": "primary", "toll": "yes"}) == "tol", "tol")
ok(J.classify({"highway": "construction", "construction": "motorway"}) == "tol", "tol dibangun")
ok(J.classify({"railway": "rail"}) == "rel" and J.classify({"railway": "rail", "tunnel": "yes"}) is None, "rel")
ok(J.classify({"highway": "trunk"}) == "besar" and J.classify({"highway": "residential"}) is None, "besar/gang")
roads = J.parse_overpass({"elements": [
    {"type": "way", "tags": {"highway": "motorway", "name": "Tol A"}, "geometry": [{"lon": 0.0005, "lat": -0.001},
                                                                                {"lon": 0.0005, "lat": 0.001}]},
    {"type": "way", "tags": {"highway": "motorway", "name": "Tol A"}, "geometry": [{"lon": 0.00052, "lat": -0.001},
                                                                                {"lon": 0.00052, "lat": 0.001}]},
    {"type": "way", "tags": {"railway": "rail"}, "geometry": [{"lon": 0.0, "lat": 0.00003}, {"lon": 0.002, "lat": 0.00003}]},
    {"type": "way", "tags": {"highway": "service"}, "geometry": [{"lon": 0.0, "lat": 0.0}, {"lon": 0.001, "lat": 0.0}]}]})
ok(len(roads) == 3, "parse overpass (service bukan jalan besar/kolektor)")
segs = [("NP-01 - NP-02", (0.0, 0.0), (0.001, 0.0))]
xr = J.crossings(segs, roads, 111320.0, 110574.0)
ok(sorted(x["kind"] for x in xr) == ["tol"], "tol dua lajur = satu persilangan; rel sejajar tidak memotong")
segs = [("NP-03 - NP-04", (0.0003, -0.00003), (0.0003, 0.0002))]
xr = J.crossings(segs, roads, 111320.0, 110574.0)
ok(len(xr) == 1 and xr[0]["kind"] == "rel" and xr[0]["d_end"] < 10.0, "rel + tiang < 10 m")
print("OK")

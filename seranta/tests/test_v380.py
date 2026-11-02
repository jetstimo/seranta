# -*- coding: utf-8 -*-
"""Uji 3.8.0: anggota FAT dari FAT Coverage + jarak sepanjang jalur, bentang dengan tiang seberang jalan (7 m),
tiang nganggur NP/EP/feeder + tikor, kecepatan. Data SINTETIS. Jalankan: python tests/test_v380.py"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import qc_core as Q            # noqa: E402
from test_qc_core import base_net, m, run, ids, PROF, PR   # noqa: E402


def test_far_hp_with_wrong_supid_is_not_counted_for_fat():
    """Kasus dokumen: 'Rumah terlalu jauh dari FAT' karena HP jauh ber-SUPID FAT lain. Anggota FAT diambil dari
    FAT Coverage: HP itu berada di coverage FAT lain sehingga tidak membuat FAT-1 'terlalu jauh'."""
    n = base_net()
    for f in n.nodes:
        f["maxpp"] = None                       # paksa hitung sendiri (tanpa MAXPPDIST desain)
    far = n.endpoints[-1]                       # HP di FAT-4 (x ~ 400 m)
    far["sup"] = n.nodes[1]["id"]               # salah SUPID -> FAT-1 (x = 100 m)
    r = run(n)["FAT_HP_DISTANCE"]
    assert "FAT_HP_OVER_150" not in ids(r), [f["message"] for f in r.findings]
    assert r.stats["anggota_fat"] == "HP di dalam FAT Coverage"
    assert "HP_WRONG_FAT_AREA" in ids(run(n)["FAT_COVERAGE"])      # SUPID salah tetap dilaporkan di aturan coverage


def test_distance_follows_cable_not_straight_line():
    """HP 80 m garis lurus dari FAT, tetapi kabel memutar 3 sisi blok: jarak jalur > 150 m -> ERROR, geometri = jalur."""
    n = Q.Net("JALUR")
    f = m(0, 0)
    n.nodes.append(Q.make_node({"ELEMENTID": "F1", "SUPPORT": "FAT", "LEVEL": 3, "SUPID": "D", "PREMISES": 1}, "X-D01-01", *f))
    route = [m(0, 0), m(0, 70), m(80, 70), m(80, 0)]
    n.cables.append(Q.make_cable({"MODELNUM": "24D"}, "D01 24D", route))
    for k, (x, y) in enumerate([(0, 0), (0, 35), (0, 70), (40, 70), (80, 70), (80, 35), (80, 0)]):
        p = m(x, y)
        n.poles.append({"id": "NP%d" % k, "name": "NP%d" % k, "x": p[0], "y": p[1], "status": "NEW", "height": 7.0})
    hp = m(80, -10)
    n.endpoints.append(Q.make_endpoint({"ELEMENTID": "H1", "SUPID": "F1"}, "", *hp))
    ring = [m(-20, -40), m(100, -40), m(100, 90), m(-20, 90), m(-20, -40)]
    n.polys.append({"id": "F1", "owner": "F1", "poly": (ring, []), "attrs": {}, "src": ""})
    n.has.update({"nodes", "endpoints", "cables", "poles", "polys"})
    r = run(n)["FAT_HP_DISTANCE"]
    f = [x for x in r.findings if x["rule_id"] == "FAT_HP_OVER_150"]
    assert f, [x["message"] for x in r.findings]
    assert 225 <= f[0]["value"] <= 232, f[0]["value"]          # 70 + 80 + 70 + 10 = 230 m
    assert f[0]["geom"][0] == "line" and len(f[0]["geom"][1]) >= 5
    assert "jalur kabel" in f[0]["message"]


def test_span_counts_pole_across_road():
    """Kabel lurus 90 m, tiang tengah 5 m di seberang jalan: rentang 45 + 45 m (bukan 90 m)."""
    n = Q.Net("SEBERANG")
    n.cables.append(Q.make_cable({"MODELNUM": "24D"}, "D01 24D", [m(0, 0), m(90, 0)]))
    for nm, (x, y) in (("NP-A", (0, 0)), ("NP-B", (45, 5.0)), ("NP-C", (90, 0))):
        p = m(x, y)
        n.poles.append({"id": nm, "name": nm, "x": p[0], "y": p[1], "status": "NEW", "height": 7.0})
    n.has.update({"cables", "poles"})
    R = run(n)
    assert "SPAN_OVER_MAX" not in ids(R["SPAN_APD"]) and "SPAN_OVER_REGULATION" not in ids(R["SPAN_APD"])
    assert "POLE_IDLE" not in ids(R["POLE_IDLE"])
    n.poles[1]["y"] = m(45, 12.0)[1]                            # 12 m: bukan tiang penopang lagi
    R = run(n)
    assert "SPAN_OVER_MAX" in ids(R["SPAN_APD"])


def test_idle_pole_rules_np_ep_feeder_with_tikor():
    n = Q.Net("NGANGGUR")
    n.cables.append(Q.make_cable({"MODELNUM": "24D"}, "D01 24D", [m(0, 0), m(100, 0)]))
    n.cables.append(Q.make_cable({"MODELNUM": "96C FEEDER"}, "FEEDER 96C", [m(0, 100), m(100, 100)]))
    spec = (("NP-OK", (50, 0), "NEW"), ("NP-NGANGGUR", (50, 50), "NEW"), ("EP-NGANGGUR", (20, 50), "EXISTING"),
            ("NP-FEEDER", (50, 100), "NEW"))
    for nm, (x, y), st in spec:
        p = m(x, y)
        n.poles.append({"id": nm, "name": nm, "x": p[0], "y": p[1], "status": st, "height": 7.0})
    n.has.update({"cables", "poles"})
    r = run(n)["POLE_IDLE"]
    assert [f["object_id"] for f in r.findings] == ["NP-NGANGGUR"], [f["message"] for f in r.findings]
    f = r.findings[0]
    assert f["severity"] == "ERROR" and "tikor" in f["message"]
    lat, lon = n.poles[1]["y"], n.poles[1]["x"]
    assert ("%.6f, %.6f" % (lat, lon)) in f["message"]
    assert r.stats["ep_nganggur_boleh"] == 1


def test_speed_large_network():
    """3.000 tiang, 6.000 HP, 300 FAT: semua aturan inti < 30 s (Python murni)."""
    n = base_net(n_fat=300, hp_per=20)
    for f in n.nodes:
        f["maxpp"] = None
    t = time.time()
    R = run(n)
    dt = time.time() - t
    assert dt < 30, dt
    assert R["FAT_HP_DISTANCE"].stats["fat_diukur"] == 300
    print("   %d tiang, %d HP, %d FAT: %.1f s" % (len(n.poles), len(n.endpoints), 300, dt))


def test_access_deep_house_and_route_distance():
    """Kasus grup WA: rumah di belakang rumah lain (jauh dari jalur) dan rumah yang dekat garis lurus tetapi jauh lewat
    akses."""
    import akses
    # jalan L: (0,0)-(100,0)-(100,100); tiang di (0,0) dan (100,100)
    segs = [(("P", 0), ("X", 1), (0.0, 0.0), (100.0, 0.0)), (("X", 1), ("P", 1), (100.0, 0.0), (100.0, 100.0))]
    A = akses.Akses(segs, [("P", 0), ("P", 1)])
    h, via, pole = A.access((50.0, 45.0))           # rumah dalam blok, 45 m dari jalan
    assert abs(h - 45.0) < 1e-6 and abs(via - 95.0) < 1e-6 and pole == ("P", 0), (h, via, pole)
    h, via, pole = A.access((90.0, 10.0))           # 10 m dari jalan vertikal
    assert abs(h - 10.0) < 1e-6 and pole in (("P", 0), ("P", 1))
    assert abs(via - 100.0) < 1e-6, via             # min(0->90 + 10 +... ) lewat jalan: 100 (dari P0: 100+10, dari P1: 90+10)


def test_remarks_new_keys():
    import remarks
    fs = [dict(kind="WARN_HP_AKSES_DALAM", sev="WARNING", ket="HP 7 (baris 12 HPDB): 45 m dari jalur", val=45, lim=30),
          dict(kind="TIANG_NGANGGUR", sev="WARNING", ket="NP-07 tidak dilewati jalur (pole nganggur); tikor 1.234567, 124.765432")]
    out = remarks.build(fs)
    assert "akses masuk" in out["text"] and "tikor 1.234567, 124.765432" in out["text"], out


if __name__ == "__main__":
    bad = 0
    for k, fn in sorted(globals().items()):
        if k.startswith("test_"):
            try:
                fn()
                print("PASS ", k)
            except Exception as e:
                import traceback
                traceback.print_exc()
                print("GAGAL", k, e)
                bad += 1
    n = sum(1 for k in globals() if k.startswith("test_"))
    print("\n%d uji, %d gagal" % (n, bad))
    sys.exit(1 if bad else 0)

# -*- coding: utf-8 -*-
"""Uji penerimaan (UAT) S01-S10 untuk QC paket APD (tool 4, aturan QC-01..07).

Setiap skenario membangun KMZ sintetis kecil (folder Feeder / Distribution seperti KMZ APD sebenarnya), lalu
memeriksa hasil aturan. Jalankan: python tests/test_uat_paket.py
"""
import math
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import qc_core as Q  # noqa: E402
import qc_paket as P  # noqa: E402

PROF, _ = Q.get_profile("APD_1X4")
LON0, LAT0 = 95.33, 5.58
KX = 1.0 / (111320.0 * math.cos(math.radians(LAT0)))
KY = 1.0 / 110540.0
FDT = "BNA1-UAT01-H01"


def xy(mx, my=0.0):
    return (LON0 + mx * KX, LAT0 + my * KY)


def pt(name, mx, my=0.0, data=None):
    x, y = xy(mx, my)
    ed = "".join('<Data name="%s"><value>%s</value></Data>' % kv for kv in (data or {}).items())
    return ("<Placemark><name>%s</name>%s<Point><coordinates>%.9f,%.9f,0</coordinates></Point></Placemark>"
            % (name, ("<ExtendedData>%s</ExtendedData>" % ed) if ed else "", x, y))


def ln(name, pts_m, data=None):
    ed = "".join('<Data name="%s"><value>%s</value></Data>' % kv for kv in (data or {}).items())
    return ("<Placemark><name>%s</name>%s<LineString><coordinates>%s</coordinates></LineString></Placemark>"
            % (name, ("<ExtendedData>%s</ExtendedData>" % ed) if ed else "",
               " ".join("%.9f,%.9f,0" % xy(*p) for p in pts_m)))


def folder(name, *content):
    return "<Folder><name>%s</name>%s</Folder>" % (name, "".join(content))


def design(pancingan_m=40.0, feeder_fdt=True, dist_fdt=True, feeder_closure=True, ext_poles=(), fdt_folder="New FDT",
           fdt_data=None):
    """16 FAT AE tiap 40 m, 1 closure 96 di Distribution, kabel 24C 640 m, pancingan di tiang."""
    n_fat = 16
    fats = [pt("%s-D01-%02d" % (FDT, i + 1), 40.0 * (i + 1)) for i in range(n_fat)]
    poles = [pt("NP-%02d" % i, 40.0 * i) for i in range(n_fat + 1)]
    poles.append(pt("NP-P", 40.0 * 3, pancingan_m))          # tiang di ujung pancingan
    dist = folder("Distribution",
                  folder(fdt_folder, pt(FDT, 0, 0, fdt_data)) if dist_fdt else "",
                  folder("New FAT AE", *fats),
                  folder("New Tiang 7 Meter", *poles),
                  folder("Eksisting Tiang 7 Meter", *[pt(n, mx, my) for n, mx, my in ext_poles]),
                  folder("New Closure 96", pt("CL-1", 40.0 * 3)),
                  folder("New Cable 24C", ln("24C", [(0, 0), (40.0 * n_fat, 0)])),
                  folder("Pancingan", ln("P1", [(40.0 * 3, 0), (40.0 * 3, pancingan_m)])))
    feed = folder("Feeder",
                  folder(fdt_folder, pt(FDT, 0, 0, fdt_data)) if feeder_fdt else "",
                  folder("New Closure 96", pt("CL-F", -300)) if feeder_closure else "",
                  folder("New Cable 48C", ln("48C", [(-900, 0), (0, 0)])))
    kml = ('<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>UAT</name>'
           '%s%s</Document></kml>' % (feed, dist))
    d = tempfile.mkdtemp()
    p = os.path.join(d, "APD_UAT.kml")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(kml)
    net = Q.read_kmz(p, Q.Net("APD"))
    pr = net.proj()
    P.unify_nodes(net, Q.pv(PROF, "fdt_same_m", 30.0), pr)
    return net, pr


def by_id(results):
    return {r.rule_id: r for r in results}


def fids(r):
    return {f["rule_id"] for f in r.findings}


# ------------------------------------------------------------------------------------------------
def test_S01_consistent_design_passes():
    net, pr = design()
    res = by_id(P.run_paket(net, net, PROF))
    # QC-06: closure lingkup FEEDER tanpa data tiang -> sebagian belum dapat dicek = UNVERIFIED (3.5.3), bukan PASS
    assert res["QC06_TIANG_PERANGKAT"].status == "UNVERIFIED" and not res["QC06_TIANG_PERANGKAT"].findings
    assert "18 dari 19" in res["QC06_TIANG_PERANGKAT"].unverified
    for rid in ("QC05_RASIO", "QC07_PANCINGAN"):
        assert res[rid].status == "PASS", (rid, res[rid].status, [f["message"] for f in res[rid].findings], res[rid].unverified)


def test_S02_no_master_is_unverified():
    net, pr = design()
    r = by_id(P.run_paket(net, net, PROF))["QC01_KODE_FDT"]
    assert r.status == "UNVERIFIED", r.status
    assert "FDT_CODE_DUPLICATE" not in fids(r)


def test_S03_same_fdt_in_two_packages_not_duplicate():
    net, pr = design()
    fdts = [n for n in net.nodes if n["kind"] == "FDT"]
    assert len(fdts) == 1, [n["name"] for n in fdts]
    assert {"FEEDER", "DISTRIBUTION"} <= set(fdts[0].get("packages") or ()), fdts[0].get("packages")
    r = by_id(P.run_paket(net, net, PROF))["QC01_KODE_FDT"]
    assert "FDT_CODE_DUPLICATE" not in fids(r)


def test_S04_new_fdt_missing_in_distribution():
    net, pr = design(dist_fdt=False)
    res = Q.run_all(net, PROF, fdt_status="NEW", cluster="UAT", paket={"kmz": net})
    r = by_id(res)["FDT_COLO_NEW"]
    f = [x for x in r.findings if x["rule_id"] == "FDT_MISSING_IN_DISTRIBUTION"]
    assert f and f[0]["severity"] in ("ERROR", "WARNING") and f[0].get("geom"), [x["rule_id"] for x in r.findings]


def test_S05_colo_fdt_without_cluster_info():
    net, pr = design(fdt_folder="FDT Eksisting")
    r = by_id(P.run_paket(net, net, PROF))["QC03_PROPERTIES"]
    assert "FDT_COLO_INFO_MISSING" in fids(r), fids(r)
    assert any(n["kind"] == "FDT" for n in net.nodes)            # titik FDT tidak dihapus
    net2, _ = design(fdt_folder="FDT Eksisting", fdt_data={"COLO": "CLUSTER INDUK X"})
    r2 = by_id(P.run_paket(net2, net2, PROF))["QC03_PROPERTIES"]
    assert "FDT_COLO_INFO_MISSING" not in fids(r2)


def test_S06_existing_pole_11m_flagged_9m_not():
    net, pr = design(ext_poles=[("EP-11", 100.0, 30.0), ("EP-9", 300.0, 30.0)])
    ref = [xy(100.0, 30.0 + 11.0), xy(300.0, 30.0 + 9.0)]
    r = P.rule_pole_reference(net, PROF, pr, ref, "uji")
    flagged = {f["object_id"] for f in r.findings}
    assert flagged == {"EP-11"}, flagged


def test_S07_pancingan_16pct_feeder_not_in_denominator():
    net, pr = design(pancingan_m=0.16 * 640.0)
    r = P.rule_ratio(net, PROF, pr)
    assert "PANCINGAN_RATIO_OVER" in fids(r), r.stats
    assert "640.0 m" in r.stats["pancingan"], r.stats         # kabel 48C Feeder (900 m) tidak ikut penyebut
    net2, pr2 = design(pancingan_m=0.15 * 640.0 - 1)
    assert "PANCINGAN_RATIO_OVER" not in fids(P.rule_ratio(net2, PROF, pr2))


def test_S08_closure_ratio_distribution_only():
    net, pr = design(feeder_closure=True)
    r = P.rule_ratio(net, PROF, pr)
    assert "6.25%" in r.stats["closure"] and "CLOSURE_RATIO_OVER" not in fids(r), r.stats
    assert "12.50%" not in r.stats["closure"]


def test_S09_pole_reference_missing_is_unverified():
    net, pr = design(ext_poles=[("EP-1", 100.0, 30.0)])
    r = P.rule_pole_reference(net, PROF, pr, None, "")
    assert r.status == "UNVERIFIED" and not r.findings


def test_S10_nominal_core_vs_fibers_separate():
    c = Q.make_cable({"FIBERS": "20"}, "kabel", [xy(0), xy(10)], folders=["Distribution", "New Cable 24C"])
    assert c["nominal_core"] == 24 and c["fibers"] == 20 and c["core"] == 24, c


def test_explanations_cover_all_rules_and_findings():
    """Setiap aturan dan jenis temuan punya penjelasan bahasa sederhana untuk laporan HTML."""
    import re
    import penjelasan as X
    src = open(os.path.join(os.path.dirname(HERE), "qc_core.py"), encoding="utf-8").read() + \
        open(os.path.join(os.path.dirname(HERE), "qc_paket.py"), encoding="utf-8").read()
    rules = set(re.findall(r'RuleResult\("([A-Z0-9_]+)"', src))
    finds = set(re.findall(r'finding\("([A-Z0-9_]+)"', src)) | set(re.findall(r'"(BOM_[A-Z]+_MISMATCH)"', src)) | \
        set(re.findall(r'"([A-Z_]+)" if [^"]+ else "([A-Z_]+)"', src) and sum(re.findall(r'finding\("([A-Z0-9_]+)" if [^"]+else "([A-Z0-9_]+)"', src), ()))
    miss_r = sorted(rules - set(X.RULES))
    miss_f = sorted(f for f in finds if f not in X.FINDINGS)
    assert not miss_r, miss_r
    assert not miss_f, miss_f


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for k, fn in tests:
        try:
            fn()
            print("PASS ", k)
        except Exception as e:
            fails += 1
            import traceback
            print("FAIL ", k, "->", repr(e))
            traceback.print_exc()
    print("\n%d uji, %d gagal" % (len(tests), fails))
    sys.exit(1 if fails else 0)

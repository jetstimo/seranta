# -*- coding: utf-8 -*-
"""Uji regresi inti QC Seranta (tanpa QGIS). Jalankan:  python tests/test_qc_core.py   (atau pytest)

Data uji SINTETIS (koordinat dummy di sekitar Palembang, tidak ada data pelanggan). Setiap uji memetakan skenario
UAT/F/T/H/M/S/C dari dokumen 'Seranta Spesifikasi Pembaruan FINAL 16 Poin 34 QC'."""
import copy
import os
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import qc_core as Q  # noqa: E402

LAT0, LON0 = -2.98, 104.75
PR = Q.Proj(LAT0)


def m(dx, dy):
    """Offset meter -> (lon, lat)."""
    return (LON0 + dx / PR.kx, LAT0 + dy / PR.ky)


PROF, _ = Q.get_profile("APD_1X4")


def base_net(n_fat=4, hp_per=8, fdt_code="PLG1-TES01-H01", fdt_id="N001.01", x0=0.0, y0=0.0, cable=True, label="BASE"):
    """FDT di (x0,y0); jalan lurus ke timur; tiang tiap 40 m; FAT tiap 100 m di tiang; HP di kiri-kanan FAT."""
    n = Q.Net(label)
    fx, fy = m(x0, y0)
    n.nodes.append(Q.make_node({"ELEMENTID": fdt_id, "SUPPORT": "FDT", "LEVEL": 2, "PREMISES": n_fat * hp_per,
                                "SPLITTERS": "%dx1x4" % max(1, (n_fat + 1) // 2)}, fdt_code, fx, fy))
    L = n_fat * 100.0
    for k in range(0, int(L // 40) + 2):
        x = min(k * 40.0, L)
        p = m(x0 + x, y0)
        n.poles.append({"id": "NP-%02d" % k, "name": "NP-%02d" % k, "x": p[0], "y": p[1], "status": "NEW", "height": 7.0})
    for j in range(1, n_fat + 1):
        fx_, fy_ = m(x0 + j * 100.0, y0)
        n.poles.append({"id": "NPF-%02d" % j, "name": "NPF-%02d" % j, "x": fx_, "y": fy_, "status": "NEW", "height": 7.0})
        fid = "%s.%02d" % (fdt_id, j)
        n.nodes.append(Q.make_node({"ELEMENTID": fid, "SUPPORT": "FAT", "LEVEL": 3, "SUPID": fdt_id, "PREMISES": hp_per,
                                    "MAXPPDIST": 60.0, "SUPDIST": j * 100.0}, "%s-D01-%02d" % (fdt_code, j), fx_, fy_))
        for h in range(hp_per):
            hx = x0 + j * 100.0 - 35 + h * 10
            hy = y0 + (20 if h % 2 else -20)
            p = m(hx, hy)
            n.endpoints.append(Q.make_endpoint({"ELEMENTID": "E%s%02d%02d" % (fdt_id[-2:], j, h), "SUPID": fid, "CONNSTATUS": 9},
                                               "", p[0], p[1]))
        ring = [m(x0 + j * 100 - 50, y0 - 60), m(x0 + j * 100 + 50, y0 - 60), m(x0 + j * 100 + 50, y0 + 60),
                m(x0 + j * 100 - 50, y0 + 60), m(x0 + j * 100 - 50, y0 - 60)]
        n.polys.append({"id": fid, "owner": fid, "poly": (ring, []), "attrs": {}, "src": ""})
    if cable:
        n.cables.append(Q.make_cable({"MODELNUM": "24D Plan"}, "D01 24D NEW INFRA", [m(x0, y0), m(x0 + L, y0)]))
    n.has.update({"nodes", "endpoints", "polys", "poles", "cables"})
    return n


def run(n, **kw):
    return {r.rule_id: r for r in Q.run_all(n, PROF, **kw)}


def ids(r):
    return [f["rule_id"] for f in r.findings]


# ------------------------------------------------------------------------------------------------
def test_base_clean():
    R = run(base_net())
    for k in ("SERVED", "FAT_COVERAGE", "CABLE_END", "MULTI_FDT", "FAT_HP_DISTANCE", "FAT_CODE", "FAT_ON_POLE",
              "POLE_IDLE", "SPAN_APD"):
        assert R[k].status in ("PASS", "INFO"), (k, R[k].status, [f["message"] for f in R[k].findings][:3])
    assert R["BOM"].status == "UNVERIFIED"                       # BOM tidak diberikan -> bukan PASS
    assert Q.overall(list(R.values())) != "PASS"


def test_uat01_hp_not_served():
    n = base_net()
    n.endpoints[5]["sup"] = ""
    r = run(n)["SERVED"]
    hits = [f for f in r.findings if f["rule_id"] == "SERVED_HP_NOT_SERVED"]
    assert len(hits) == 1 and hits[0]["object_id"] == n.endpoints[5]["id"]
    assert r.stats["not_served"] == 1


def test_s02_served_unverified():
    n = base_net()
    for e in n.endpoints:
        e["sup"], e["conn"], e["served"] = "", None, None
    assert run(n)["SERVED"].status == "UNVERIFIED"


def test_duplicate_hp_id():
    n = base_net()
    n.endpoints[1]["id"] = n.endpoints[0]["id"]
    assert "HP_ID_DUPLICATE" in ids(run(n)["SERVED"])


def test_uat02_hp_outside_voronoi():
    n = base_net()
    e = n.endpoints[0]
    e["x"], e["y"] = m(100, 200)
    r = run(n)["FAT_COVERAGE"]
    assert ids(r).count("HP_OUTSIDE_FAT_COVERAGE") == 1 and r.status == "ERROR"


def test_coverage_no_polygon_unverified():
    n = base_net()
    n.polys = []
    n.has.discard("polys")
    assert run(n)["FAT_COVERAGE"].status == "UNVERIFIED"


def test_hp_wrong_fat_area():
    n = base_net()
    n.endpoints[0]["sup"] = "N001.01.03"          # HP di coverage FAT 1 tetapi di-assign ke FAT 3
    assert "HP_WRONG_FAT_AREA" in ids(run(n)["FAT_COVERAGE"])


def test_uat04_two_straight_segments_no_false_end():
    n = base_net()
    c = n.cables[0]
    mid = m(150, 0)
    n.cables = [dict(c, pts=[c["pts"][0], mid]), dict(c, pts=[mid, c["pts"][1]])]
    r = run(n)["CABLE_END"]
    assert "CABLE_END_WITHOUT_FAT" not in ids(r), [f["message"] for f in r.findings]
    assert r.stats["ujung_jaringan"] == 2


def test_uat03_cable_end_without_fat_and_loop():
    n = base_net()
    c = n.cables[0]
    c["pts"] = c["pts"] + [m(520, 0)]                 # ekor 120 m setelah FAT terakhir tanpa FAT
    r = run(n)["CABLE_END"]
    assert "CABLE_END_WITHOUT_FAT" in ids(r)
    assert "LOOP_LENGTH_OVER_100M" in ids(r)


def test_closure_end_is_info():
    n = base_net()
    c = n.cables[0]
    c["pts"] = c["pts"] + [m(450, 0)]
    p = m(450, 0)
    n.closures.append({"id": "C1", "name": "CLOSURE 96", "x": p[0], "y": p[1], "attrs": {}})
    r = run(n)["CABLE_END"]
    assert "CABLE_END_WITHOUT_FAT" not in ids(r) and "LOOP_TERMINATION_CHECK" in ids(r)


def test_uat05_two_fdt():
    a = base_net(3, 8, "PLG1-TES01-H01", "N001.01")
    b = base_net(2, 8, "PLG1-TES01-H02", "N001.02", y0=300.0)
    for k in ("nodes", "endpoints", "polys", "poles", "cables"):
        getattr(a, k).extend(getattr(b, k))
    r = run(a)["MULTI_FDT"]
    t = r.stats["per_fdt"]
    assert len(t) == 2 and sum(x["fat"] for x in t) == 5, t
    assert r.status in ("PASS", "INFO"), [f["message"] for f in r.findings]


def test_fat_multi_parent():
    a = base_net(2, 8, "PLG1-TES01-H01", "N001.01")
    b = base_net(1, 8, "PLG1-TES01-H02", "N001.02", y0=300.0)
    a.nodes.extend(b.nodes)
    f = [x for x in a.nodes if x["kind"] == "FAT"][0]
    f["name"] = "PLG1-TES01-H02-D01-09"                # kode menunjuk FDT H02, SUPID & ID ke H01
    assert "FAT_MULTI_PARENT" in ids(run(a)["MULTI_FDT"])


def test_fdt_capacity_and_premises():
    n = base_net(4, 8)
    n.nodes[0]["premises"] = 40                       # ikon FDT 40, HP sebenarnya 32 -> kasus 22
    for f in n.nodes[1:]:
        if f["kind"] == "FAT":
            f["premises"] = 17 if f is n.nodes[1] else f["premises"]
    r = run(n)["MULTI_FDT"]
    assert "FDT_PREMISES_MISMATCH" in ids(r) and "FAT_OVER_CAPACITY" in ids(r)


def test_fat_hp_distance():
    n = base_net()
    fats = [x for x in n.nodes if x["kind"] == "FAT"]
    fats[0]["maxpp"], fats[1]["maxpp"] = 140.0, 160.0
    r = run(n)["FAT_HP_DISTANCE"]
    assert ids(r).count("FAT_HP_120_150") == 1 and ids(r).count("FAT_HP_OVER_150") == 1


def test_fat_order_gap():
    n = base_net()
    [x for x in n.nodes if x["kind"] == "FAT"][2]["name"] = "PLG1-TES01-H01-D01-07"
    assert "FAT_LABEL_ORDER_INVALID" in ids(run(n)["FAT_CODE"])


def test_fat_floating():
    n = base_net()
    f = [x for x in n.nodes if x["kind"] == "FAT"][0]
    f["x"], f["y"] = m(100, 6)
    assert "FAT_NOT_ON_POLE" in ids(run(n)["FAT_ON_POLE"])


def test_pole_idle_and_span():
    n = base_net()
    p = m(200, 80)
    n.poles.append({"id": "NP-X", "name": "NP-X", "x": p[0], "y": p[1], "status": "NEW", "height": 7.0})
    n.poles = [q for q in n.poles if q["name"] not in ("NP-06", "NP-07", "NPF-03")]   # celah 240->320 = 80 m
    R = run(n)
    assert "POLE_IDLE" in ids(R["POLE_IDLE"])
    assert "SPAN_OVER_MAX" in ids(R["SPAN_APD"])


def _pkg(n, fdt_name, dx=0.0, with_cable=True):
    """Paket Feeder/Distribusi berisi titik FDT (dan kabel distribusi)."""
    pk = Q.Net("pkg")
    f = [x for x in n.nodes if x["kind"] == "FDT"][0]
    p = m(dx, 0)
    pk.nodes.append(Q.make_node({"SUPPORT": "FDT"}, fdt_name, p[0], p[1]))
    if with_cable:
        pk.cables = copy.deepcopy(n.cables)
    pk.has.update({"nodes", "cables"})
    return pk


def test_colo_matrix():
    n = base_net()
    code = "PLG1-TES01-H01"
    ok = Q.rule_fdt_colo_new("COLO", _pkg(n, code), _pkg(n, code), n, PROF, PR)
    assert ok.status == "PASS", [f["message"] for f in ok.findings]                   # UAT-08 / F-02
    empty = Q.Net("e")
    r = Q.rule_fdt_colo_new("COLO", _pkg(n, code), empty, n, PROF, PR)
    assert "FDT_MISSING_IN_DISTRIBUTION" in ids(r)                                       # UAT-07 / F-01
    r = Q.rule_fdt_colo_new("COLO", empty, _pkg(n, code), n, PROF, PR)
    assert "FDT_MISSING_IN_FEEDER" in ids(r)                                             # UAT-06
    r = Q.rule_fdt_colo_new("COLO", _pkg(n, code, dx=30), _pkg(n, code), n, PROF, PR)
    assert "FDT_LOCATION_MISMATCH" in ids(r)


def test_uat10_feeder_not_supplied():
    n = base_net()
    r = Q.rule_fdt_colo_new("COLO", None, _pkg(n, "PLG1-TES01-H01"), n, PROF, PR)
    assert "FDT_DATA_UNVERIFIED" in ids(r) and "FDT_MISSING_IN_FEEDER" not in ids(r)


def test_unknown_status():
    n = base_net()
    r = Q.rule_fdt_colo_new("UNKNOWN", _pkg(n, "PLG1-TES01-H01"), _pkg(n, "PLG1-TES01-H01"), n, PROF, PR)
    assert "FDT_STATUS_UNKNOWN" in ids(r) and r.status == "UNVERIFIED"


def test_uat09_new_route_disconnected():
    n = base_net()
    code = "PLG1-TES01-H01"
    ok = Q.rule_fdt_colo_new("NEW", _pkg(n, code), _pkg(n, code), n, PROF, PR)
    assert "FDT_NEW_ROUTE_DISCONNECTED" not in ids(ok), [f["message"] for f in ok.findings]
    d = _pkg(n, code)
    d.cables[0]["pts"] = [m(0, 0), m(250, 0)]          # FAT 3 & 4 putus
    r = Q.rule_fdt_colo_new("NEW", _pkg(n, code), d, n, PROF, PR)
    assert ids(r).count("FDT_NEW_ROUTE_DISCONNECTED") == 2


def _csv(text):
    fd, p = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    return p


def test_uat11_bom_poles_and_units():
    n = base_net()
    newp = sum(1 for p in n.poles if p["status"] == "NEW")
    L = 0.4                                           # kabel 24 core 400 m = 0,4 km
    p = _csv("No,Item,Satuan,Qty\n1,Homepass,HP,32\n2,FAT 16 port,unit,4\n3,Tiang 7 m,btg,%d\n4,Kabel 24 core,km,%.3f\n"
             "5,Tiang existing,btg,3\n" % (newp + 3, L + 0.07))
    r = Q.rule_bom(n, p, PROF, PR)
    os.remove(p)
    assert "BOM_POLE_MISMATCH" in ids(r)
    pole = [f for f in r.findings if f["rule_id"] == "BOM_POLE_MISMATCH"][0]
    assert pole["value"] - pole["threshold"] == 3
    assert "BOM_HP_MISMATCH" not in ids(r) and "BOM_FAT_MISMATCH" not in ids(r)
    cab = [t for t in r.stats["tabel"] if t[0] == "CABLE_24"][0]
    assert abs(cab[4] - 470.0) < 1e-6                  # km -> m dinormalkan
    assert any("EXISTING" in x for x in r.notes)


def test_bom_missing_unverified():
    r = Q.rule_bom(base_net(), None, PROF, PR)
    assert r.status == "UNVERIFIED"


def _kmz(kml, files=()):
    fd, p = tempfile.mkstemp(suffix=".kmz")
    os.close(fd)
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("doc.kml", kml)
        for f in files:
            z.writestr(f, b"x")
    return p


def test_kmz_reader_and_rules():
    a, b, c = m(0, 0), m(100, 0), m(100, 20)
    kml = ('<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
           '<Style id="c24"><LineStyle><color>ff0000ff</color><width>3</width></LineStyle></Style>'
           '<Style id="fat"><IconStyle><Icon><href>files/FAT.png</href></Icon></IconStyle></Style>'
           '<Folder><name>net_endpoints</name><Placemark><name>H1</name><Point><coordinates>%f,%f</coordinates></Point></Placemark></Folder>'
           '<Folder><name>Net_Nodes</name><Placemark><name>PLG1-TES01-H01-D01-01</name><styleUrl>#fat</styleUrl>'
           '<ExtendedData><Data name="SUPPORT"><value>FAT</value></Data></ExtendedData><Point><coordinates>%f,%f</coordinates></Point></Placemark></Folder>'
           '<Folder><name>Net_Cables</name><Folder><name>24D</name><Placemark><name></name><styleUrl>#c24</styleUrl>'
           '<LineString><coordinates>%f,%f %f,%f</coordinates></LineString></Placemark></Folder></Folder>'
           '</Document></kml>') % (c[0], c[1], b[0], b[1], a[0], a[1], b[0], b[1])
    p = _kmz(kml)
    n = Q.read_kmz(p)
    os.remove(p)
    assert len(n.endpoints) == 1 and len(n.nodes) == 1 and len(n.cables) == 1
    assert n.cables[0]["core"] == 24 and n.cables[0]["color"] == "#ff0000"
    r = Q.rule_kmz(n, False, PROF, n.proj())
    got = ids(r)
    for k in ("KMZ_FOLDER_INVALID", "KMZ_ICON_INVALID", "CABLE_COLOR_MISMATCH", "CABLE_LABEL_MISSING"):
        assert k in got, (k, got)


def test_sdproj_overrides():
    import glob
    root = os.environ.get("SERANTA_SDPROJ_DIR", "/mnt/user-data/uploads/Downloads/TUTORIAL/CONFIG")
    c14 = [f for f in glob.glob(os.path.join(root, "*.sdproj")) if "1X4" in f.upper()]
    c18 = [f for f in glob.glob(os.path.join(root, "*.sdproj")) if "1X8" in f.upper()]
    if not c14 or not c18:
        return
    o = Q.sdproj_overrides(c14[0])
    assert o["fdt_max_premises"] == 384 and o["fat_max_hp"] == 16 and o["fat_hp_warn_m"] == 120 and o["fdt_spl_ratio"] == 4
    o = Q.sdproj_overrides(c18[0])
    assert o["fdt_max_premises"] == 480 and o["fat_hp_warn_m"] == 130


def test_profiles():
    profs = Q.load_profiles()
    assert {"APD_1X4", "APD_1X8", "REGULASI_KETAT"} <= set(profs)
    p, w = Q.get_profile("TIDAK_ADA")
    assert w and p["profile_id"] == "APD_1X4"
    for pid, pf in profs.items():
        for k, e in pf["params"].items():
            assert e.get("dasar") in Q.DASAR_LABEL and e.get("sumber"), (pid, k)
    assert Q.pv(profs["REGULASI_KETAT"], "span_max_m") == 50 and Q.pv(profs["APD_1X8"], "fdt_max_premises") == 480
    for k in ("fdt_same_m", "coord_tol_m", "ext_pole_ref_m", "pancingan_max_pct", "closure96_max_pct", "device_pole_m",
              "pancingan_pole_m"):
        assert k in profs["APD_1X4"]["params"], k


def test_user_profile_dir_overrides(tmp_path=None):
    import json
    import tempfile
    d = tempfile.mkdtemp()
    json.dump({"profile_id": "ORG_X", "default": True, "rule_version": "x", "nama": "org", "keterangan": "",
               "params": {"span_max_m": {"v": 55, "dasar": "INTERNAL", "sumber": "uji"}}}, open(os.path.join(d, "o.json"), "w"))
    os.environ["SERANTA_PROFILE_DIR"] = d
    try:
        profs = Q.load_profiles()
        assert next(iter(profs)) == "ORG_X" and profs["ORG_X"]["_asal"] == "pengguna" and "APD_1X4" in profs
    finally:
        del os.environ["SERANTA_PROFILE_DIR"]


def test_overall_contract():
    a = Q.RuleResult("A", "a")
    b = Q.RuleResult("B", "b").unverify("data kurang")
    assert a.status == "PASS" and b.status == "UNVERIFIED" and Q.overall([a, b]) == "UNVERIFIED"


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

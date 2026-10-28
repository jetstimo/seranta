# -*- coding: utf-8 -*-
"""Uji regresi 3.5.3 (tanpa QGIS): garis 'Keterangan Infra' bukan kabel, pancingan tanpa label status,
versi aturan dari kode. Data sintetis."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import qc_core as Q  # noqa: E402
from test_qc_core import base_net, m, PROF, PR  # noqa: E402


def _ids(res, rule):
    return [f for r in res for f in r.findings if r.rule_id == rule]


def test_annotation_line_not_a_cable():
    c = Q.make_cable({}, "New Infra", [m(0, 0), m(900, 0)], ("Feeder", "Keterangan Infra", "New Infra"))
    assert c["kind"] == "annot"
    c2 = Q.make_cable({}, "Colo Pole iforte", [m(0, 0), m(900, 0)], ("Feeder", "Keterangan Infra", "Collo Tiang", "Colo Pole 48C"))
    assert c2["kind"] == "annot"
    real = Q.make_cable({}, "48C", [m(0, 0), m(900, 0)], ("Feeder", "Cable", "New Cable Aerial/Udara", "New Cable 48C"))
    assert real["kind"] != "annot"


def test_slack_and_label_ignore_annotation_and_pancingan():
    n = base_net()
    n.has.add("kmz")
    n.markers.append({"kind": "slack", "x": m(10, 0)[0], "y": m(10, 0)[1], "name": "Slack"})
    n.cables.append(Q.make_cable({}, "New Infra", [m(0, 5), m(0, 900)], ("Distribution", "Keterangan Infra", "New Infra")))
    n.cables.append(Q.make_cable({}, "Untitled Path", [m(100, 0), m(100, 30)], ("Distribution", "Aerial Utilities", "Pancingan")))
    s = Q.rule_slack(n, PROF, PR)
    assert not any("New Infra" in f["message"] for f in s.findings), [f["message"] for f in s.findings]
    k = Q.rule_kmz(n, False, PROF, PR)
    assert k.status != "UNVERIFIED"
    msgs = [f["message"] for f in k.findings]
    assert not any("Untitled Path" in x or "New Infra" in x for x in msgs), msgs


def test_label_status_from_template_folder():
    n = base_net(cable=False)
    n.has.add("kmz")
    n.cables.append(Q.make_cable({}, "24D Plan", [m(0, 0), m(400, 0)],
                                 ("Distribution", "Cable", "New Infra Aerial/Udara", "New Cable 24C")))
    n.cables.append(Q.make_cable({}, "24D Plan", [m(0, 10), m(400, 10)], ("Distribution", "Cable")))
    k = Q.rule_kmz(n, False, PROF, PR)
    hits = [f for f in k.findings if f["rule_id"] == "CABLE_LABEL_NO_STATUS"]
    assert len(hits) == 1, [f["message"] for f in hits]
    s = Q.rule_slack(n, PROF, PR)
    assert s.status == "UNVERIFIED" or all("slack" in f["message"] for f in s.findings)


def test_bakp_scanner_badge_not_a_stamp():
    try:
        import numpy as np
        import bakp as K
    except Exception:  # noqa: BLE001 - lingkungan tanpa numpy: lewati
        return
    badge = np.full((90, 240, 3), 235, np.uint8)
    badge[30:60, 20:220] = 60                                  # teks abu-abu
    stamp = np.full((300, 300, 3), 255, np.uint8)
    stamp[50:250, 50:250] = (60, 60, 200)                      # tinta biru
    pages = [{"arr": np.full((10, 10, 3), 255, np.uint8), "w": 2000, "h": 2800, "no": i} for i in range(1, 6)]
    doc = {"pages": pages, "n_pages": 5, "notes": [],
           "overlays": [{"page": i, "w": 240, "h": 90, "hash": "b", "smask": False, "arr": badge} for i in range(1, 6)]}
    items = K.offline_check(doc)[1]
    assert not any(k == "BAKP_STEMPEL_TTD_TEMPELAN_DIGITAL" for k, _ok, _t in items), items
    doc2 = {"pages": pages, "n_pages": 5, "notes": [],
            "overlays": [{"page": i, "w": 300, "h": 300, "hash": "s", "smask": False, "arr": stamp} for i in (2, 3)]}
    items2 = K.offline_check(doc2)[1]
    assert any(k == "BAKP_STEMPEL_TTD_TEMPELAN_DIGITAL" for k, _ok, _t in items2), items2


def test_mapview_data_and_block():
    import json
    import mapview as MV

    class Sc(object):
        lines = [([(104.75, -2.98), (104.751, -2.98)], "cable_new")]
        points = [(104.75, -2.98, "pole_new", "NP-1"), (104.7505, -2.9801, "hp", "H00001")]
        polys = []
        attrs_l = [{"Nama": "24D", "Core (nominal)": 24}]
        attrs_p = [{"Tinggi (m)": 7}, {"Alamat": "Jl. A 1", "kosong": "-"}]
        attrs_y = []
    d = MV.data_from_scene(Sc(), [{"fid": "F-0001", "sev": "ERROR", "lon": 104.7501, "lat": -2.98, "value": 76.0, "limit": 60,
                                   "unit": "m", "line": [(104.75, -2.98), (104.751, -2.98)]},
                                  {"fid": "F-0002", "sev": "INFO", "lon": None, "lat": None}])
    assert len(d["L"]) == 3 and d["F"][0]["v"] == 76.0 and d["F"][0]["ln"]
    assert len(d["F"]) == 1                                       # temuan tanpa lokasi tidak digambar
    assert "kosong" not in d["L"][2]["a"]                         # nilai '-' dibuang
    h = MV.block(d)
    assert "window.SERANTA_MAP=" in h and "L.map(" in h and "id='smap'" in h
    js = h.split("window.SERANTA_MAP=", 1)[1].split(";</script>", 1)[0]
    assert json.loads(js)["F"][0]["id"] == "F-0001"
    assert MV.block({"L": [], "F": []}) == ""


def test_evidence_panel():
    import report_ui as U
    h = U.evidence_html("F-0009", {"rule": [("Bentang", 60, 76, "m")], "rows": [{"t": "HPDB baris 51", "src": "HPDB.xlsx",
                                    "d": {"LAT": "1.2", "ALAMAT": "Jl. A"}, "hi": ["LAT"]}], "audit": [("ID temuan", "F-0009"), ("x", "")]},
                        "data:image/jpeg;base64,AA==", "Judul")
    for k in ("data-pt='img'", "data-pt='rule'", "data-pt='data'", "data-pt='audit'", "+16 m", "(+27%)", "class='hit'",
              "HPDB.xlsx", "data-img='copy'", "data-img='png'"):
        assert k in h, k
    assert U.evidence_html("F-1", {}) == ""
    li = U.finding_li("ERROR", "t", "", "a", "f", fid="F-0009", ev={"rule": [("p", 1, 2, "")]})
    assert "class='proof'" in li


def test_rule_version_from_code():
    p, _ = Q.get_profile("APD_1X4")
    assert p["rule_version"] == Q.RULE_VERSION


if __name__ == "__main__":
    bad = 0
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        try:
            fn()
            print("PASS ", fn.__name__)
        except Exception as e:  # noqa: BLE001
            bad += 1
            print("FAIL ", fn.__name__, "->", repr(e))
    print("\n%d uji, %d gagal" % (len(fns), bad))
    sys.exit(1 if bad else 0)

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

# -*- coding: utf-8 -*-
"""Uji 3.5.1: toleransi berbasis acuan (pita pass / review / fail).

- slack hanya menilai kabel BARU (kabel colo/existing tidak dinilai)
- ujung kabel tanpa FAT yang masih dalam batas loop = WARNING, di luar batas = ERROR
- profil memuat parameter baru lengkap dengan sumber
- alat 1: kode temuan baru (tepi BOUNDARY, double tagging review) punya label, tingkat dan penjelasan
Jalankan: python tests/test_v351.py   (alat 1 butuh PYTHONPATH ke stub qgis, mis. fakeqgis; dilewati bila tidak ada)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import qc_core as Q  # noqa: E402
from test_qc_core import base_net, m, PROF  # noqa: E402


def _ids(r, sev=None):
    return [f["rule_id"] for f in r.findings if sev is None or f["severity"] == sev]


def test_slack_ignores_colo_cable():
    n = base_net()
    n.cables.append(Q.make_cable({}, "Colo Cable", [m(0, 30), m(3000, 30)], folders=["Feeder", "Collo Cable"]))
    n.cables.append(Q.make_cable({}, "24C baru", [m(0, -30), m(900, -30)], folders=["Distribution", "New Cable 24C"]))
    n.markers.append({"kind": "slack", "x": m(0, -30)[0], "y": m(0, -30)[1], "name": "slack"})
    r = Q.rule_slack(n, PROF, n.proj())
    names = [f["object_id"] for f in r.findings]
    assert "Colo Cable" not in names, names
    assert "24C baru" in names, names


def test_cable_tail_within_loop_is_warning():
    n = base_net(n_fat=2)
    n.cables = [Q.make_cable({"MODELNUM": "24D Plan"}, "D01", [m(x, 0) for x in range(0, 241, 40)])]    # 40 m setelah FAT terakhir (200 m)
    r = Q.rule_cable_end(n, PROF, n.proj())
    sev = [f["severity"] for f in r.findings if f["rule_id"] == "CABLE_END_WITHOUT_FAT"]
    assert sev == ["WARNING"], [(f["rule_id"], f["severity"], f["message"]) for f in r.findings]


def test_cable_tail_beyond_loop_is_error():
    n = base_net(n_fat=2)
    n.cables = [Q.make_cable({"MODELNUM": "24D Plan"}, "D01", [m(x, 0) for x in range(0, 361, 40)])]    # 160 m > 100 m
    r = Q.rule_cable_end(n, PROF, n.proj())
    sev = [f["severity"] for f in r.findings if f["rule_id"] == "CABLE_END_WITHOUT_FAT"]
    assert sev == ["ERROR"], [(f["rule_id"], f["severity"], f["message"]) for f in r.findings]
    assert "LOOP_LENGTH_OVER_100M" in _ids(r)


def test_profiles_have_new_params_with_sources():
    for pid in ("APD_1X4", "APD_1X8", "REGULASI_KETAT"):
        prof, _ = Q.get_profile(pid)
        for k in ("boundary_edge_tol_m", "dl_dup_hp_review_m", "dl_dup_pole_review_m", "spl4_typ_db", "spl8_typ_db",
                  "conn_typ_db"):
            p = prof["params"][k]
            assert p.get("sumber") and p.get("dasar"), (pid, k)
    assert Q.pv(Q.get_profile("APD_1X4")[0], "boundary_edge_tol_m") == 10.0
    assert Q.pv(Q.get_profile("REGULASI_KETAT")[0], "boundary_edge_tol_m") == 5.0


def test_link_budget_design_vs_worst_case():
    """1:4 + 1:8, 4 konektor, 10 splice, margin 3 dB, B+ 28 dB: nilai desain lolos s.d. ~15 km, worst-case ~8,9 km."""
    prof, _ = Q.get_profile("APD_1X4")

    def loss(km, typ):
        spl = (Q.pv(prof, "spl4_typ_db"), Q.pv(prof, "spl8_typ_db")) if typ else (Q.pv(prof, "spl4_db"), Q.pv(prof, "spl8_db"))
        conn = Q.pv(prof, "conn_typ_db") if typ else Q.pv(prof, "conn_db")
        return km * Q.pv(prof, "fiber_db_km") + sum(spl) + 4 * conn + 10 * Q.pv(prof, "splice_db") + Q.pv(prof, "margin_db")
    assert loss(12, True) <= 28.0 < loss(12, False)          # 12 km: lolos desain, tipis worst-case
    assert loss(16, True) > 28.0                             # 16 km: kurang


def test_grouping_ignores_own_fdt_already_in_design_lite():
    """Design Lite terbaru sudah memuat FDT proyek ini di lokasi yang sama -> bukan 'kelompok dipakai di tempat lain'."""
    import qc_paket as P
    import test_uat_paket as U
    net, pr = U.design()
    dl = {U.FDT: [U.xy(0, 0)], "BNA1-JKE01-H02": [U.xy(300, 200)], "BNA1-JKE01-H04": [U.xy(-300, 100)]}
    r = P.rule_fdt_code(net, net, PROF, pr, None, "", dl)
    g = r.stats["grouping"][0]
    assert g["hasil"] == "KELOMPOK BARU", g
    assert "FDT_GROUP_MISMATCH" not in _ids(r)
    r2 = P.rule_fdt_code(net, net, PROF, pr, {P.norm_code(U.FDT)}, "rekap.xlsx", dl)     # rekap memuat kode sendiri
    assert r2.stats["grouping"][0]["hasil"] == "KELOMPOK BARU" and "FDT_NEW_NOT_IN_REKAP" not in _ids(r2)


def test_read_dbf_without_ogr():
    """Status review lama dibaca dari .dbf tanpa OGR (agar QC_TEMUAN tidak terkunci saat alat dijalankan ulang)."""
    try:
        import buat_input_desain as B
    except Exception:  # nosec B110
        return
    import struct
    import tempfile
    flds = [("kode", "C", 20), ("review", "C", 20), ("lon", "N", 13), ("lat", "N", 13)]
    rows = [("HP_LUAR_BOUNDARY", "VERIFIED", "123.0368000", "0.5600000"), ("X", "", "", "")]
    rlen = 1 + sum(f[2] for f in flds)
    hlen = 32 + 32 * len(flds) + 1
    head = struct.pack("<BBBBIHH20x", 3, 126, 10, 27, len(rows), hlen, rlen)
    desc = b"".join(struct.pack("<11sc4xB15x", n.encode(), t.encode(), ln) for n, t, ln in flds) + b"\x0d"
    body = b"".join(b" " + b"".join(v.encode().ljust(f[2])[:f[2]] for v, f in zip(r, flds)) for r in rows)
    p_ = os.path.join(tempfile.mkdtemp(), "t.dbf")
    with open(p_, "wb") as fh:
        fh.write(head + desc + body + b"\x1a")
    recs = B.read_dbf(p_)
    assert recs[0]["kode"] == "HP_LUAR_BOUNDARY" and recs[0]["review"] == "VERIFIED" and abs(recs[0]["lon"] - 123.0368) < 1e-9
    assert recs[1]["review"] is None and recs[1]["lon"] is None


def test_tool1_new_kinds():
    try:
        import buat_input_desain as B
        import penjelasan as X
    except Exception:  # nosec B110 - stub qgis tidak tersedia: lewati
        return
    assert B.qc_severity("INFO_HP_TEPI_BOUNDARY") == "INFO"
    assert B.qc_severity("HP_LUAR_BOUNDARY") == "ERROR"
    assert B.qc_severity("TIANG_NGANGGUR") == "WARNING"
    assert B.qc_label("INFO_HP_TEPI_BOUNDARY")[0] == 5
    assert B.qc_label("INFO_HP_MUNGKIN_DI_DESIGN_LITE")[0] == 6
    for k in ("INFO_HP_TEPI_BOUNDARY", "INFO_HP_MUNGKIN_DI_DESIGN_LITE", "INFO_TIANG_BARU_DEKAT_EXISTING"):
        assert all(X.tool1_kind_text(k)), k
    ring = [(0.0, 0.0), (0.001, 0.0), (0.001, 0.001), (0.0, 0.001), (0.0, 0.0)]
    d = B.dist_to_poly_m(0.0011, 0.0005, (ring, []))
    assert 10.0 < d < 12.5, d                                # ~11 m di luar sisi timur


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

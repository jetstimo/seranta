# -*- coding: utf-8 -*-
"""Uji fitur 3.5.0: bukti & sumber setiap temuan, kandidat grouping FDT, daftar kerja XLSX.
Jalankan: python tests/test_v35.py"""
import os
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET  # nosec B405 - membaca XLSX buatan sendiri di uji

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import qc_core as Q  # noqa: E402
import qc_paket as P  # noqa: E402
import xlsx_writer as XL  # noqa: E402
import test_uat_paket as U  # noqa: E402

PROF = U.PROF


def test_evidence_and_source_on_every_located_finding():
    net, pr = U.design(pancingan_m=0.2 * 640.0, ext_poles=[("EP-11", 100.0, 30.0)])
    res = Q.run_all(net, PROF, cluster="UAT", paket={"kmz": net, "ref_pts": [U.xy(100.0, 45.0)], "ref_src": "ref.csv"})
    fs = Q.findings_of(res)
    assert fs
    for f in fs:
        if f.get("object_id") and f["rule_id"] not in ("FDT_DATA_UNVERIFIED",):
            assert f.get("source_file"), (f["rule_id"], f["object_id"])
    ext = [f for f in fs if f["rule_id"] == "EXT_POLE_FAR_FROM_REF"]
    assert ext and ext[0]["source_file"] == "ref.csv" and ext[0]["scope"] == "DISTRIBUTION" and "folder" in ext[0]["evidence"]
    for c in ("evidence", "source_file", "scope", "unit"):
        assert c in Q.FINDING_COLS


def test_grouping_new_area_is_info_not_warning():
    net, pr = U.design()
    dl = {"BNA1-JKE01-H02": [U.xy(300, 200)], "BNA1-JKE01-H04": [U.xy(-300, 100)], "BNA1-TNG01-H05": [U.xy(500, -100)]}
    r = P.rule_fdt_code(net, net, PROF, pr, None, "", dl)
    g = r.stats["grouping"][0]
    assert g["kelompok_kode"] == "BNA1-UAT01" and g["kelompok_sekitar"] == "BNA1-JKE01" and g["hasil"] == "KELOMPOK BARU", g
    assert {f["rule_id"]: f["severity"] for f in r.findings}.get("FDT_GROUP_NEW") == "INFO"


def test_grouping_wrong_existing_group_warns_with_candidate():
    net, pr = U.design()
    dl = {"BNA1-JKE01-H02": [U.xy(300, 200)], "BNA1-JKE01-H07": [U.xy(-300, 100)],
          "BNA1-UAT01-H03": [U.xy(20000, 0)]}                    # kelompok UAT01 dipakai 20 km jauhnya
    r = P.rule_fdt_code(net, net, PROF, pr, None, "", dl)
    g = r.stats["grouping"][0]
    assert g["hasil"].startswith("BEDA") and g["kode_kandidat"] == "BNA1-JKE01-H08", g
    assert any(f["rule_id"] == "FDT_GROUP_MISMATCH" and f["severity"] == "WARNING" for f in r.findings)


def test_grouping_same_group_passes_and_codes_normalised():
    net, pr = U.design()
    dl = {"BNA1UAT01H02": [U.xy(300, 200)], "BNA1-UAT01-H05": [U.xy(-300, 100)]}
    g = P.rule_fdt_code(net, net, PROF, pr, None, "", dl).stats["grouping"][0]
    assert g["hasil"].startswith("SESUAI"), g


def _read(path, sheet):
    z = zipfile.ZipFile(path)
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    wb = ET.fromstring(z.read("xl/workbook.xml"))  # nosec B314
    names = [s.get("name") for s in wb.iter(ns + "sheet")]
    x = ET.fromstring(z.read("xl/worksheets/sheet%d.xml" % (names.index(sheet) + 1)))  # nosec B314
    rows = []
    for r in x.iter(ns + "row"):
        rows.append(["".join(t.text or "" for t in c.iter(ns + "t")) or "".join(v.text or "" for v in c.iter(ns + "v"))
                     for c in r.iter(ns + "c")])
    dv = [d.get("sqref") for d in x.iter(ns + "dataValidation")]
    return rows, dv


def test_xlsx_writer_roundtrip():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "t.xlsx")
    sh = XL.Sheet("Temuan", ["A", "B & C", "Status review"])
    sh.add([1, "teks <khusus> & 'kutip'", "OPEN"])
    sh.add([2.5, ("=", 'HYPERLINK("https://x.org/?a=1&b=2","peta")', "peta"), "VERIFIED"])
    sh.choices(2, list(Q.REVIEW_STATES))
    XL.write(p, [XL.Sheet("Ringkasan", ["x"]), sh], "uji", "Seranta")
    rows, dv = _read(p, "Temuan")
    assert rows[0] == ["A", "B & C", "Status review"] and rows[1][1] == "teks <khusus> & 'kutip'" and rows[2][2] == "VERIFIED"
    assert dv == ["C2:C3"]
    assert zipfile.ZipFile(p).testzip() is None


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

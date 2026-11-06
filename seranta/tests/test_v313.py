# -*- coding: utf-8 -*-
"""Uji 3.13.0 integritas jalur (Python murni, tanpa QGIS). Jalankan: python3 tests/test_v313.py"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import integritas_jalur as IJ  # noqa: E402
import remarks as R  # noqa: E402


def span(ka, kb, xy):
    return (ka, kb, IJ._plen(xy), xy)


def X(x, y):
    return ("X", x, y)


class TestPieces(unittest.TestCase):
    def test_route_without_any_pole(self):
        # kasus gambar revisi: garis jalur di KMZ tanpa satu pun tiang
        sp = [span(X(0, 0), X(100, 0), [(0, 0), (50, 0), (100, 0)])]
        deg = {X(0, 0): 1, X(100, 0): 1}
        pcs = IJ.pieces(sp, deg)
        self.assertEqual(len(pcs), 1)
        ev = IJ.evaluate_piece(pcs[0], sp)
        self.assertEqual(ev[0]["tipe"], "tanpa_tiang")
        self.assertAlmostEqual(ev[0]["panjang"], 100.0)

    def test_leaf_measured_along_route_not_straight(self):
        # tiang di (0,0); jalur ke timur 60 m lalu kembali ke utara-barat: ujung 20 m garis lurus, 140 m sepanjang jalur
        xy = [(0, 0), (60, 0), (60, 40), (20, 40), (20, 20)]
        sp = [span(("P", 0), X(20, 20), xy)]
        pcs = IJ.pieces(sp, {X(20, 20): 1})
        ev = IJ.evaluate_piece(pcs[0], sp)
        self.assertEqual(ev[0]["tipe"], "ujung")
        self.assertAlmostEqual(ev[0]["panjang"], 160.0)
        self.assertEqual(ev[0]["ujung_a"], ("P", 0))

    def test_junction_between_poles(self):
        J = X(40, 0)
        sp = [span(("P", 0), J, [(0, 0), (40, 0)]), span(J, ("P", 1), [(40, 0), (80, 0)]),
              span(J, X(40, 5), [(40, 0), (40, 5)])]
        deg = {J: 3, X(40, 5): 1}
        pcs = IJ.pieces(sp, deg)
        self.assertEqual(len(pcs), 1)
        ev = {e["tipe"]: e for e in IJ.evaluate_piece(pcs[0], sp)}
        self.assertAlmostEqual(ev["antartiang"]["panjang"], 80.0)
        self.assertAlmostEqual(ev["ujung"]["panjang"], 45.0)   # ujung -> tiang terdekat lewat percabangan
        # EP-EP tidak dinilai (sama dengan rentang biasa)
        ev2 = IJ.evaluate_piece(pcs[0], sp, {0: "existing", 1: "existing"})
        self.assertNotIn("antartiang", [e["tipe"] for e in ev2])

    def test_pole_pole_spans_ignored(self):
        sp = [span(("P", 0), ("P", 1), [(0, 0), (40, 0)])]
        self.assertEqual(IJ.pieces(sp, {}), [])


class TestNetwork(unittest.TestCase):
    def test_components_gap(self):
        sp = [span(("P", 0), ("P", 1), [(0, 0), (40, 0)]), span(("P", 2), ("P", 3), [(70, 0), (110, 0)])]
        cs = IJ.components(sp)
        self.assertEqual(len(cs), 2)
        g, _at = IJ.comp_gap(sp, cs[1], cs[0])
        self.assertAlmostEqual(g, 30.0)

    def test_crossing(self):
        segs = [(X(0, 0), X(10, 0), (0, 0), (10, 0)), (X(5, -5), X(5, 5), (5, -5), (5, 5))]
        cr = IJ.crossings(segs)
        self.assertEqual(len(cr), 1)
        self.assertAlmostEqual(cr[0]["x"], 5.0)
        self.assertFalse(cr[0]["singgung"])
        # ruas yang berbagi simpul bukan persilangan
        segs2 = [(X(0, 0), X(10, 0), (0, 0), (10, 0)), (X(10, 0), X(10, 10), (10, 0), (10, 10))]
        self.assertEqual(IJ.crossings(segs2), [])

    def test_overlap_back_and_forth(self):
        # bolak-balik: keluar 50 m lalu kembali 50 m di jalur yang sama (geser 0,3 m)
        segs = [(X(0, 0), X(50, 0), (0, 0), (50, 0)), (X(50, 0), X(0, 0.3), (50, 0), (0, 0.3))]
        ov = IJ.merge_overlaps(IJ.overlaps(segs))
        self.assertEqual(len(ov), 1)
        self.assertAlmostEqual(ov[0]["panjang"], 50.0, places=0)
        # garis lurus bersambung (searah) bukan tumpukan
        segs2 = [(X(0, 0), X(50, 0), (0, 0), (50, 0)), (X(50, 0), X(90, 0), (50, 0), (90, 0))]
        self.assertEqual(IJ.overlaps(segs2), [])

    def test_cut_gaps(self):
        L, n, _c = IJ.cut_gaps([(0, 0), (100, 0)], [(30, 1), (60, 2.5), (80, 5)], 3.0)
        self.assertEqual(n, 2)
        self.assertAlmostEqual(L, 40.0)


class TestRemarks(unittest.TestCase):
    def f(self, kind, sev, ket, val=None, lim=None):
        return {"kind": kind, "sev": sev, "ket": ket, "val": val, "lim": lim}

    def test_route_kinds_reject(self):
        fl = [self.f("JALUR_TANPA_TIANG", "ERROR", "Jalur tanpa tiang: 237.0 m kabel tanpa satu pun tiang", 237.0, 60.0)]
        r = R.build(fl)
        self.assertEqual(r["status"], "REJECT")
        self.assertIn("237 m tanpa tiang", r["text"])
        fl = [self.f("UJUNG_JALUR_TANPA_TIANG", "ERROR", "Ujung jalur 72.0 m dari tiang terdekat NP-1: kabel harus berakhir "
                     "di tiang (tambat akhir); 280.5 m sepanjang jalur dari tiang NP-1", 72.0, 0.5)]
        r = R.build(fl)
        self.assertEqual(r["status"], "REJECT")
        self.assertIn("ujung jalur tanpa tiang", r["text"])
        fl = [self.f("WARN_SIMPANG_TANPA_TIANG", "WARNING", "Percabangan 3 arah tanpa tiang (tiang terdekat 20.0 m)", 3, 2)]
        self.assertEqual(R.build(fl)["status"], "REJECT")
        fl = [self.f("WARN_JALUR_BERTUMPUK", "WARNING", "Garis jalur bertumpuk 71.3 m", 71.3, 5.0)]
        r = R.build(fl)
        self.assertEqual(r["status"], "APPROVE DENGAN CATATAN")
        self.assertIn("71 m", r["text"])

    def test_switch_off_identical_to_312(self):
        fl = [self.f("UJUNG_JALUR_TANPA_TIANG", "ERROR", "Ujung jalur 72.0 m dari tiang terdekat NP-1", 72.0, 0.5),
              self.f("WARN_SIMPANG_TANPA_TIANG", "WARNING", "Percabangan 3 arah tanpa tiang", 3, 2)]
        self.assertEqual(R.build(fl, route=False)["status"], "APPROVE")


if __name__ == "__main__":
    unittest.main()

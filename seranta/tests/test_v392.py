"""Uji unit Seranta 3.9.2 (murni Python, tanpa QGIS): label umum 'RUKO-1' sebagai pengenal lemah.
Jalankan: python tests/test_v392.py"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import lintas_cluster as L   # noqa: E402


def kind(s):
    return L.label_kind(L.norm_name(s))


class LabelUmum(unittest.TestCase):
    def test_jenis_label(self):
        for s in ("RUKO-1", "Ruko-1", "Toko 2", "KIOS A3", "Kos No 12", "KOST 2B", "? RUKO-3", "Warung 7"):
            self.assertEqual(kind(s), "gen", s)
        # tidak berubah dari 3.9.1
        for s, k in (("TOKO TAUFIK", "name"), ("KANTIN KAKA", "name"), ("RUKOSARI", "name"), ("KOPYCO", "name"),
                     ("?327", "seq"), ("N087", "seq"), ("? -37", "seq"), ("35B", "num"), ("11", "num"),
                     ("HP12", ""), ("RUMAH", ""), ("GUDANG", ""), ("-", "")):
            self.assertEqual(kind(s), k, s)

    def test_lintas_cluster_tomohon_ruko(self):
        # review Tomohon: 'RUKO-1' L3 vs 'Ruko-1' L7 berjarak 17 m -> WARNING cek citra, bukan ERROR
        r = L.match_rank(17.0, L.norm_name("RUKO-1"), L.norm_name("Ruko-1"))
        self.assertEqual(r[0], 6)
        self.assertIn("cek citra", r[1])
        self.assertEqual(L.match_rank(3.0, "RUKO1", "RUKO1")[0], 1)     # <= 5 m: unit yang sama
        self.assertEqual(L.match_rank(0.3, "RUKO1", "RUKO1")[0], 0)     # koordinat sama tetap ERROR
        self.assertIsNone(L.match_rank(30.0, "RUKO1", "RUKO1"))         # di luar 25 m: deret lain
        self.assertIsNone(L.match_rank(10.0, "RUKO1", "RUKO2"))         # nomor unit beda: bukan duplikat
        self.assertEqual(L.match_rank(1.5, "RUKO1", "RUKO2")[0], 4)     # berimpit satu bangunan: tetap WARNING

    def test_label_kuat_tidak_berubah(self):
        self.assertEqual(L.match_rank(17.0, "TOKOTAUFIK", "TOKOTAUFIK")[0], 1)
        self.assertEqual(L.match_rank(40.0, "TOKOTAUFIK", "TOKOTAUFIK")[0], 5)
        self.assertEqual(L.match_rank(20.0, "?327", "?327")[0], 1)
        self.assertEqual(L.match_rank(10.0, "11", "11")[0], 1)
        self.assertIsNone(L.match_rank(20.0, "11", "11"))
        self.assertEqual(L.match_rank(25.0, "KANTINKAKA", "KANTINKAKAK")[0], 3)

    def test_dalam_cluster(self):
        dlat = 1.0 / 111320.0
        pts = [{"x": 124.8, "y": 1.3, "hn": "RUKO-1"}, {"x": 124.8, "y": 1.3 + 17 * dlat, "hn": "Ruko-1"},
               {"x": 124.8, "y": 1.3 + 100 * dlat, "hn": "RUKO-2"}, {"x": 124.8, "y": 1.3 + 102 * dlat, "hn": "RUKO 2"},
               {"x": 124.8, "y": 1.3 + 300 * dlat, "hn": "TOKO TAUFIK"},
               {"x": 124.8, "y": 1.3 + 318 * dlat, "hn": "Toko Taufik"}]
        got = {(i, j): sure for i, j, d, n, sure in L.same_label_pairs(pts)}
        self.assertEqual(got.get((0, 1)), False)     # 17 m label umum: WARNING
        self.assertEqual(got.get((2, 3)), True)      # 2 m label umum: ERROR
        self.assertEqual(got.get((4, 5)), True)      # nama khas 18 m: ERROR (tidak berubah)

    def test_deret(self):
        dl = 1 / 110540.0       # koordinat nyata Tomohon: L7 Ruko-1..4 ke selatan, L3 RUKO-1..2 ke utara (celah 17 m)
        l7 = [{"hn": "Ruko-%d" % i, "x": 124.8355, "y": 1.33953 - (i - 1) * 4.4 * dl} for i in range(1, 5)]
        l3 = [{"hn": "RUKO-%d" % i, "x": 124.8355, "y": 1.339682 + (i - 1) * 4.9 * dl} for i in range(1, 3)]
        r = L.series_relation(l3, l7, "RUKO")
        self.assertTrue(r["pisah"])
        self.assertEqual((r["n_a"], r["n_b"]), (2, 4))
        dua_kali = [{"hn": "RUKO-%d" % i, "x": 124.83552, "y": p["y"] + dl} for i, p in enumerate(l7, 1)]
        self.assertFalse(L.series_relation(dua_kali, l7, "RUKO")["pisah"])
        self.assertIsNone(L.series_relation(l3[:1], l7, "RUKO"))


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""Uji unit Seranta 3.8.2-3.9.0 (murni Python, tanpa QGIS): perbaikan lintas cluster mode KMZ saja / KMZ 1 PIC.
Jalankan:  python seranta/tests/test_v39.py
"""
import os
import sys
import unittest

PLUG = sys.argv.pop(1) if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PLUG)
import lintas_cluster as L   # noqa: E402
import remarks as RM         # noqa: E402

M = 1.0 / 111320.0           # +-1 m dalam derajat (dekat ekuator)


def hp(x, y, n):
    return {"x": 124.8 + x * M, "y": 1.34 + y * M, "hn": n}


class SeqRestart(unittest.TestCase):
    def test_restart_detected(self):
        # dua lingkungan, masing-masing mulai dari '? -1', titik berjauhan 300 m
        a = [hp(i * 10, 0, "? -%d" % i) for i in range(1, 21)]
        b = [hp(i * 10, 300, "? -%d" % i) for i in range(1, 21)]
        self.assertTrue(L.seq_labels_restart(a, b, far_m=100.0))

    def test_copy_not_restart(self):
        # label sama dan titik berdekatan (salinan) -> bukan penomoran ulang; tetap dinilai duplikat
        a = [hp(i * 10, 0, "? -%d" % i) for i in range(1, 21)]
        b = [hp(i * 10, 3, "? -%d" % i) for i in range(1, 21)]
        self.assertFalse(L.seq_labels_restart(a, b, far_m=100.0))

    def test_few_common_not_restart(self):
        a = [hp(i * 10, 0, "? -%d" % i) for i in range(1, 21)]
        b = [hp(i * 10, 300, "? -%d" % (i + 100)) for i in range(1, 21)] + [hp(0, 300, "? -1")]
        self.assertFalse(L.seq_labels_restart(a, b, far_m=100.0))


class SharedRoute(unittest.TestCase):
    def line(self, pts):
        return [(124.8 + x * M, 1.34 + y * M) for x, y in pts]

    def test_overlap_length(self):
        own = [self.line([(0, 0), (200, 0)])]
        sib = [self.line([(50, 0.5), (300, 0.5)])]
        m, mid = L.shared_route_m(own, sib)
        self.assertAlmostEqual(m, 150.0, delta=5.0)
        self.assertIsNotNone(mid)

    def test_crossing_is_not_overlap(self):
        own = [self.line([(0, 0), (200, 0)])]
        sib = [self.line([(100, -100), (100, 100)])]
        self.assertLess(L.shared_route_m(own, sib)[0], 5.0)

    def test_touching_end_is_small(self):
        own = [self.line([(0, 0), (200, 0)])]
        sib = [self.line([(200, 0), (400, 0)])]
        self.assertLess(L.shared_route_m(own, sib)[0], 5.0)


def cluster(label, hps, poles=(), lines=(), bnd=()):
    return {"label": label, "kode": label, "hp": hps, "hp_src": "KMZ", "bnd": list(bnd), "poles": list(poles),
            "lines": list(lines), "folder_ids": {}, "bakp_sha": "", "doc": "", "note": [], "ids_hpdb": set(),
            "ids_other": set(), "kmz": "", "hpdb": "", "dir": label,
            "bbox": L._bbox_pts([(p["x"], p["y"]) for p in hps])}


class CompareKmzOnly(unittest.TestCase):
    def setUp(self):
        self.a_hp = [dict(hp(i * 10, 0, "? -%d" % i), hid="baris %d (H)" % i, row=i) for i in range(1, 21)]
        self.b_hp = [dict(hp(i * 10, 30, "? -%d" % i), hid="baris %d (H)" % i, row=i) for i in range(1, 21)]
        pa = [(124.8 + i * 40 * M, 1.34 + 10 * M, "NP") for i in range(6)]

        self.own = cluster("LINGKUNGAN A", self.a_hp, poles=pa,
                           lines=[[(124.8, 1.34 + 10 * M), (124.8 + 200 * M, 1.34 + 10 * M)]])
        # saudara: 4 tiang sama koordinat, jalur sama
        self.sib = cluster("LINGKUNGAN B", self.b_hp, poles=pa[:4],
                           lines=[[(124.8, 1.34 + 10 * M), (124.8 + 200 * M, 1.34 + 10 * M)]])

    def test_shared_poles_and_no_false_label_dup(self):
        # label urut sama berjarak 30 m: dulu 'label sama 25-50 m' (WARNING) untuk 20 HP; kini penomoran diulang? tidak:
        # median 30 m < 100 m -> bukan penomoran ulang, tetap dinilai (aturan lama tidak berubah)
        res = L.compare(self.own, [self.sib])
        kinds = [f["kind"] for f in res["findings"]]
        self.assertIn("WARN_TIANG_GANDA_LINTAS_CLUSTER", kinds)
        self.assertEqual(res["counts"]["pole_shared"], 4)
        self.assertIn("WARN_HP_MUNGKIN_DUPLIKAT_LINTAS_CLUSTER", kinds)

    def test_restart_suppresses_label_match(self):
        far = [dict(hp(i * 10, 400, "? -%d" % i), hid="x", row=i) for i in range(1, 21)]
        near_one = dict(hp(10, 20, "? -1"), hid="y", row=99)          # label '? -1' 20 m dari '? -1' cluster ini
        sib = cluster("LINGKUNGAN C", far + [near_one])
        res = L.compare(self.own, [sib])
        kinds = [f["kind"] for f in res["findings"]]
        self.assertNotIn("HP_DUPLIKAT_LINTAS_CLUSTER", kinds)
        self.assertEqual(res.get("seq_restart"), ["LINGKUNGAN C"])

    def test_copied_point_still_error(self):
        far = [dict(hp(i * 10, 400, "? -%d" % i), hid="x", row=i) for i in range(1, 21)]
        copy = dict(hp(10, 0.2, "? -77"), hid="y", row=99)             # koordinat sama (<= 0,5 m)
        sib = cluster("LINGKUNGAN C", far + [copy])
        res = L.compare(self.own, [sib])
        self.assertEqual(res["counts"]["dup"], 1)

    def test_no_sibling_message(self):
        res = L.compare(self.own, [])
        self.assertTrue(any("tidak ada folder cluster lain di folder induk" in r for r in res["report"]))


class Remarks(unittest.TestCase):
    def test_access_not_repeated(self):
        f = [{"kind": "HP_JAUH_DARI_TIANG", "sev": "ERROR", "ket": "x (baris %d HPDB): 70 m" % r, "val": 70.0, "lim": 50.0}
             for r in (2, 3)]
        f += [{"kind": "WARN_HP_AKSES_DALAM", "sev": "WARNING", "ket": "baris %d jauh" % r, "val": None, "lim": None}
              for r in (2, 3, 9)]
        t = RM.build(f)["text"]
        self.assertIn("1 HP jauh dari jalur", t)
        self.assertIn("(baris 9)", t)

    def test_excess_text(self):
        f = [{"kind": "RENTANG_NP_NP", "sev": "ERROR", "ket": "NP-03 - NP-01: rentang", "val": 60.0, "lim": 60.0}]
        n = RM.build(f)["notes"]
        self.assertTrue(any("< 0,1 m di atas" in x for x in n), n)


class FindimStale(unittest.TestCase):
    def test_stale_findim_is_note(self):
        f = [{"kind": "ADMIN_ID_CLUSTER_TIDAK_TERDAFTAR", "sev": "ERROR", "ket": "ID 2184641132 tidak ada di OLT CLUSTER",
              "val": None, "lim": None}]
        self.assertEqual(RM.build(f)["status"], "REJECT")
        r = RM.build(f, findim_stale=True)
        self.assertNotEqual(r["status"], "REJECT")
        self.assertTrue(any("FINDIM lama" in n for n in r["notes"]))


class BakpMetadata(unittest.TestCase):
    def test_metadata_id(self):
        import bakp
        off = ({"n_pages": 4, "title_subject": ["Cls 2184634529 Cls Name Lingkungan3"]}, [])
        it = bakp.evaluate(off, {"cluster_id": "2184641132", "bakp_file": "BAKP_x.pdf"})
        self.assertIn("WARN_BAKP_ID_METADATA_BEDA", [i[0] for i in it])
        off = ({"n_pages": 4, "title_subject": ["Cls 2184641132"]}, [])
        it = bakp.evaluate(off, {"cluster_id": "2184641132", "bakp_file": "BAKP_x.pdf"})
        self.assertNotIn("WARN_BAKP_ID_METADATA_BEDA", [i[0] for i in it])


class WilayahInduk(unittest.TestCase):
    def test_identical_boundary(self):
        ring = [(124.8, 1.34), (124.801, 1.34), (124.801, 1.341), (124.8, 1.34)]
        self.assertEqual(L.bnd_fingerprint([(ring, [])]), L.bnd_fingerprint([(list(reversed(ring)), [])]))
        self.assertNotEqual(L.bnd_fingerprint([(ring, [])]), L.bnd_fingerprint([([(x + 1e-4, y) for x, y in ring], [])]))
        self.assertEqual(L.bnd_fingerprint([]), "")

    def test_short_label(self):
        self.assertEqual(RM.short_label("JAMBI_SUKA KARYA KOTA BARU RT 10_60HP_PT.EKSPANINDO"), "SUKA KARYA KOTA BARU RT 10")
        self.assertEqual(RM.short_label("JAMBI_21100241138_SUKA KARYA KOTA BARU RT 06_90HP_PT.EKSPANINDO"), "21100241138")
        self.assertEqual(RM.short_label("LINGKUNGAN 6-KAKASKASEN"), "LINGKUNGAN 6-KAKASKASEN")

    def test_wilayah_and_kind(self):
        import grup as G
        self.assertEqual(G.wilayah_name(["JAMBI_SUKA KARYA KOTA BARU RT 10_60HP_X", "JAMBI_21100241139_SUKA KARYA KOTA BARU RT 02_74HP_X"]),
                         "SUKA KARYA KOTA BARU")
        self.assertEqual(G.wilayah_name(["LINGKUNGAN 1-KAKASKASEN", "LINGKUNGAN 2-KAKASKASEN"]), "KAKASKASEN")
        lk = lambda sig, net=False: [("a", "b", {"signals": sig, "one_net": net})]
        self.assertEqual(G.group_kind(lk(["3 tiang sama koordinat"], True)), "jaringan")
        self.assertEqual(G.group_kind(lk(["file BAKP identik"])), "paket")
        self.assertEqual(G.group_kind(lk(["BOUNDARY identik ('RT 014')"])), "paket")
        self.assertEqual(G.group_kind(lk(["BOUNDARY berdampingan 3 m"])), "berdampingan")

    def test_remarks_boundary_identik(self):
        f = [{"kind": "BOUNDARY_MEMUAT_CLUSTER_LAIN", "sev": "ERROR", "val": 6, "lim": None,
              "ket": "BOUNDARY cluster ini identik dengan BOUNDARY 6 cluster lain 'RT 014 SUKA KARYA' (a, b): boundary ..."}]
        self.assertIn("boundary induk 'RT 014 SUKA KARYA' (sama di 6 cluster lain)", RM.build(f)["text"])


class Keaslian(unittest.TestCase):
    def test_rfc8032_vector1(self):
        import keaslian as K
        sk = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
        self.assertEqual(K.public_key(sk).hex(), "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
        sig = K.sign(sk, b"")
        self.assertTrue(K.verify(K.public_key(sk), b"", sig))
        self.assertFalse(K.verify(K.public_key(sk), b"x", sig))

    def test_status_cycle(self):
        import keaslian as K, tempfile, shutil
        d = tempfile.mkdtemp()
        try:
            open(os.path.join(d, "a.py"), "w").write("x = 1\n")
            sk = os.urandom(32)
            old = K.KUNCI_PUBLIK
            K.KUNCI_PUBLIK = tuple(K.to_ints(K.public_key(sk)))
            K.write_signed(d, "9.9.9", sk)
            K._CACHE.clear(); self.assertEqual(K.check(d)[0], "ASLI")
            open(os.path.join(d, "a.py"), "w").write("x = 2\n")
            K._CACHE.clear(); self.assertEqual(K.check(d)[0], "DIMODIFIKASI")
            K.KUNCI_PUBLIK = tuple(K.to_ints(K.public_key(os.urandom(32))))
            K._CACHE.clear(); self.assertEqual(K.check(d)[0], "TIDAK_RESMI")
            K.KUNCI_PUBLIK = old
        finally:
            shutil.rmtree(d)


class Evid(unittest.TestCase):
    def test_eviden(self):
        self.assertTrue(L.EVID_RX.search("EVIDEN"))
        self.assertTrue(L.EVID_RX.search("Evidence"))
        self.assertTrue(L.EVID_RX.search("Dokumentasi"))


if __name__ == "__main__":
    unittest.main(verbosity=2)

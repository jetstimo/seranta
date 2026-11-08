# -*- coding: utf-8 -*-
"""Uji 3.14.0: pengenalan berkas dari isi/nama salah ketik, kemiripan nama, remarks sederhana (Python murni)."""
import os
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kenali as K  # noqa: E402
import remarks as R  # noqa: E402


def kmz(path, body):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("doc.kml", "<?xml version='1.0'?><kml xmlns='http://www.opengis.net/kml/2.2'><Document>%s</Document></kml>"
                   % body)


PT = "<Placemark><name>%s</name><Point><coordinates>106.8,-6.2,0</coordinates></Point></Placemark>"
LN = "<Placemark><LineString><coordinates>106.8,-6.2,0 106.81,-6.2,0</coordinates></LineString></Placemark>"


class TName(unittest.TestCase):
    def test_hpdb_typos(self):
        for n in ("HPDB_A.xlsx", "HPBD A.xlsx", "hdpb.xlsx", "HP DB RT 5.csv", "Homepas.xlsx", "HP_DATABASE.xlsx"):
            self.assertTrue(K.name_is_hpdb(n), n)
        for n in ("TSSR_x.docx", "BOQ.xlsx", "ROW TO COLUMN.xlsx", "HPID.xlsx", "DAILY REPORT.xlsx"):
            self.assertFalse(K.name_is_hpdb(n), n)

    def test_similarity(self):
        a = "HPDB_JAMBI_SUKA KARYA KOTA BARU RT 07_53HP_PT.X.xlsx"
        self.assertEqual(K.similarity(a, "JAMBI_SUKA KARYA KOTA BARU RT 07_54HP_PT.X.kmz"), 1.0)   # jumlah HP diabaikan
        self.assertEqual(K.similarity(a, "KMZ_JAMBI_SUKA KARYA KOTA BARU RT 10_60HP_PT.X.kmz"), 0.0)  # RT beda
        self.assertEqual(K.similarity("A 2170538616.xlsx", "B 2170538616.kmz"), 1.0)                 # ID sama
        bm, _s = K.best_match(a, ["KMZ_JAMBI_SUKA KARYA KOTA BARU RT 10_60HP.kmz", "JAMBI_SUKA KARYA KOTA BARU RT 07.kmz"])
        self.assertEqual(bm, "JAMBI_SUKA KARYA KOTA BARU RT 07.kmz")


class TContent(unittest.TestCase):
    def test_kmz_kinds(self):
        d = tempfile.mkdtemp()
        p1 = os.path.join(d, "a.kmz")
        kmz(p1, "<Folder><name>HP</name>%s</Folder><Folder><name>CABLE</name>%s</Folder>" % (PT % "1", LN))
        self.assertEqual(K.kmz_profile(p1)["kind"], "survei")
        p2 = os.path.join(d, "b.kmz")
        kmz(p2, "<Folder><name>FDT</name><Placemark><name>X</name><ExtendedData><SchemaData><SimpleData name='SPLITTERS'>"
                "4</SimpleData></SchemaData></ExtendedData><Point><coordinates>1,1,0</coordinates></Point></Placemark></Folder>")
        self.assertEqual(K.kmz_profile(p2)["kind"], "designlite")
        p3 = os.path.join(d, "c.kmz")
        kmz(p3, "<Folder><name>Boundary Funnel</name><Placemark><Polygon><outerBoundaryIs><LinearRing><coordinates>"
                "1,1,0 1,2,0 2,2,0 1,1,0</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark></Folder>")
        self.assertEqual(K.kmz_profile(p3)["kind"], "funnel")

    def test_csv_hpdb(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "data rumah.csv")
        with open(p, "w") as fh:
            fh.write("Homepass_ID;Homepass_Latitude;Homepass_Longitude\nH1;-6.2;106.8\nH2;-6.21;106.81\n")
        self.assertEqual(K.sheet_profile(p)["kind"], "hpdb")
        q = os.path.join(d, "boq.csv")
        with open(q, "w") as fh:
            fh.write("Material;Qty\nTiang;3\n")
        self.assertEqual(K.sheet_profile(q)["kind"], "lain")


class TSimple(unittest.TestCase):
    def f(self, kind, sev, ket, val=None, lim=None):
        return {"kind": kind, "sev": sev, "ket": ket, "val": val, "lim": lim}

    def test_simple_remarks(self):
        fl = [self.f("HP_JAUH_DARI_TIANG", "ERROR", "HP baris 5 61 m ke tiang terdekat", 61, 50),
              self.f("WARN_TIANG_GANDA_LINTAS_CLUSTER", "WARNING", "Tiang NP-01 sama koordinat dengan tiang cluster RT 06",
                     0.1, 0.5)]
        r = R.build(fl, style="sederhana")
        self.assertEqual(r["status"], "REJECT")
        self.assertTrue(r["text"].startswith("Reject: "))
        self.assertIn("lebih dari 50 m", r["text"])
        self.assertTrue(r["text"].endswith(R.SIMPLE_TAIL))
        self.assertLessEqual(r["length"], 255)
        # status sama dengan remarks rinci
        self.assertEqual(R.build(fl)["status"], r["status"])
        self.assertEqual(R.build([], style="sederhana")["text"], "Approve")

    def test_names(self):
        self.assertEqual(R._names_in("boundary tumpang tindih dgn SUKA RT 03 (+-6.350 m2, 8 HP di irisan), RT 04 (+-1 m2)"),
                         ["SUKA RT 03", "RT 04"])

    def test_length_cap(self):
        fl = [self.f(k, "ERROR", "x", 90.0, 60.0) for k in ("HP_JAUH_DARI_TIANG", "RENTANG_NP_NP", "JALUR_TANPA_TIANG",
                                                  "UJUNG_JALUR_TANPA_TIANG", "HP_LUAR_BOUNDARY", "HP_DUPLIKAT_KOORDINAT",
                                                  "HP_DUPLIKAT_ID", "TIANG_DI_AREA_TANPA_IZIN", "HP_LUAR_FUNNEL")]
        r = R.build(fl, style="sederhana")
        self.assertLessEqual(r["length"], 255)
        self.assertIn("masalah lain", r["text"])


if __name__ == "__main__":
    unittest.main()

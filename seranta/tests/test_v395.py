"""Uji unit Seranta 3.9.5 (murni Python): cek tambahan dari review Jambi Argenta 6, Tegal Karangmangu, Minahasa Tataaran
Satu dan Cianjur Nyalindung (November 2026).
Jalankan: python tests/test_v395.py"""
import os
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import qc_tambahan as T   # noqa: E402
import remarks as R       # noqa: E402
import tssr as S          # noqa: E402


def _docx(path, paras):
    body = "".join("<w:p><w:r><w:t>%s</w:t></w:r></w:p>" % p for p in paras)
    xml = ('<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/'
           'wordprocessingml/2006/main" xmlns:wp="x"><w:body><wp:posOffset>4038598609</wp:posOffset>%s</w:body>'
           '</w:document>' % body)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", xml)


class Tssr(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def _mk(self, name, paras):
        p = os.path.join(self.d, name)
        _docx(p, paras)
        return p

    def test_id_beda(self):
        p = self._mk("TSSR_JAMBI_21100218859_Perumahan_Argenta_6_50HP.docx",
                     ["Complex/Cluster/Building Name", "PERUMAHAN ARGENTA 6", "Site Address",
                      "Jl. Sersan Anwar Bay, Bagan Pete, Kec. Kota Baru", "Home Pass and Occupation", ":", "50 HP",
                      "Contact Phone Number", ": 081373321123"])
        t = S.parse(p)
        self.assertEqual(t["ids_name"], ["21100218859"])
        self.assertEqual(t["ids_text"], [])                 # nomor telepon & angka posisi gambar bukan ID
        self.assertEqual(t["hp"], 50)
        self.assertEqual(t["name"], "PERUMAHAN ARGENTA 6")
        kinds = [k for k, *_ in S.compare(t, "21100232646", 50, "SIMPANG RIMBO")]
        self.assertEqual(kinds, ["WARN_TSSR_ID_BEDA", "INFO_TSSR_WILAYAH_BEDA"])

    def test_hp_beda_dan_ribuan(self):
        p = self._mk("TSSR_2292736040_RW 005 NYALINDUNG_169HP.docx",
                     ["Site Address", "Jl. Simpang Galudra Nyalindung, Kec. Cugenang", "Home Pass and Occupation",
                      ":", "177 HP"])
        res = S.compare(S.parse(p), "2292736040", 169, "NYALINDUNG")
        self.assertEqual([r[0] for r in res], ["WARN_TSSR_HP_BEDA"])
        self.assertEqual((res[0][2], res[0][3]), (177, 169))
        p2 = self._mk("TSSR_SUKA KARYA RT 06.docx", ["Home Pass and Occupation", ":", "1,242 HP"])
        self.assertEqual(S.parse(p2)["hp"], 1242)
        self.assertIn("induk", S.compare(S.parse(p2), "", 90)[0][1])

    def test_sesuai_tanpa_temuan(self):
        p = self._mk("TSSR_2292736040_X.docx", ["Site Address", "Kel. Nyalindung", "Home Pass and Occupation", "169 HP"])
        self.assertEqual(S.compare(S.parse(p), "2292736040", 169, "NYALINDUNG"), [])

    def test_bukan_docx(self):
        p = os.path.join(self.d, "TSSR_rusak.docx")
        with open(p, "wb") as fh:
            fh.write(b"bukan zip")
        self.assertFalse(S.parse(p)["readable"])
        self.assertEqual(S.find_tssr(self.d), [p])


class Evidence(unittest.TestCase):
    # titik dalam derajat di sekitar Tondano (1 derajat ~ 111 km)
    def test_label_sama_jauh_dan_foto_tanpa_hp(self):
        hps = [{"x": 124.8724, "y": 1.26929, "hn": "?-28", "row": 42},          # foto '?-28' 150 m di barat
               {"x": 124.8746, "y": 1.26960, "hn": 1, "row": 26},               # HP blok A no. 1 (bukan '?-1')
               {"x": 124.8730, "y": 1.26940, "hn": "?-5", "row": 7}]            # foto berimpit
        evs = [(124.871044, 1.269414, "?-28"), (124.87465, 1.26990, "?-1"), (124.8730, 1.26940, "?-5"),
               (124.8730, 1.26940, "?-5")]                                      # salinan KMZ EVIDENCE
        norm = lambda v: str(v).replace("?", "").replace("-", "")          # noqa: E731 (meniru norm_name.lstrip)
        far, orphan = T.evidence_extra(hps, evs, norm=norm)
        self.assertEqual([(h["row"], e[2]) for h, e, d in far], [(42, "?-28")])
        self.assertTrue(140 < far[0][2] < 160)
        self.assertEqual([o[2] for o in orphan], ["?-1"])              # '?-1' bukan rumah HP '1'
        # evidence_missing tetap seperti 3.9.4
        self.assertEqual([h["row"] for h in T.evidence_missing(hps, evs, norm=norm)], [42, 26])

    def test_label_ganda_tidak_dinilai(self):
        hps = [{"x": 124.8724, "y": 1.26929, "hn": "12", "row": 2}, {"x": 124.8800, "y": 1.2700, "hn": "12", "row": 3}]
        evs = [(124.8710, 1.2694, "12")]
        far, _o = T.evidence_extra(hps, evs)
        self.assertEqual(far, [])


class Pola(unittest.TestCase):
    def test_area_tanpa_izin(self):
        for s in ("TIDAK DAPAT IZIN", "NO SPACE", "no_permit", "Tanpa Ijin", "WARGA MENOLAK", "Area dilarang"):
            self.assertTrue(T.EXCL_AREA_RX.search(s), s)
        for s in ("POL01 — BATAS ASLI RW 005 NYALINDUNG", "BOUNDARY", "RW 004 KARANGMANGU", "Perumahan argenta 6",
                  "RT 02 IZIN OK", "SPACE GREY", "NOSPACEX"):
            self.assertFalse(T.EXCL_AREA_RX.search(s), s)

    def test_karakter_tersembunyi(self):
        self.assertTrue(T.HIDDEN_CHAR_RX.search("​TOKO KERAMIK"))
        self.assertTrue(T.HIDDEN_CHAR_RX.search("A�B"))
        for s in ("?-1", "? -4", "Jl. Raya\nNo 5", "RUKO-1\t2", "Café"):
            self.assertFalse(T.HIDDEN_CHAR_RX.search(s), repr(s))


class Remarks(unittest.TestCase):
    def test_frasa_baru(self):
        f = [{"kind": "HP_DI_AREA_TANPA_IZIN", "sev": "ERROR", "ket": "H00005 (baris 6) di dalam area 'TIDAK DAPAT IZIN' (x)",
              "val": None, "lim": None},
             {"kind": "TIANG_DI_AREA_TANPA_IZIN", "sev": "ERROR", "ket": "NP7 [4:Point] di dalam area 'TIDAK DAPAT IZIN' (x)",
              "val": None, "lim": None},
             {"kind": "WARN_TSSR_HP_BEDA", "sev": "WARNING", "ket": "TSSR mencatat 177 HP, HPDB 169 HP (selisih +8)",
              "val": 177, "lim": 169}]
        r = R.build(f)
        self.assertEqual(r["status"], "REJECT")
        self.assertIn("1 HP di area 'TIDAK DAPAT IZIN' (baris 6)", r["text"])
        self.assertIn("NP7 [4:Point] di area tanpa izin", r["text"])
        self.assertIn("TSSR 177 HP vs HPDB 169 HP", r["text"])

    def test_bakp_scan_hanya_catatan(self):
        r = R.build([{"kind": "INFO_BAKP_HASIL_SCAN", "sev": "INFO", "ket": "x", "val": None, "lim": None}])
        self.assertEqual(r["status"], "APPROVE")                       # status tidak berubah
        self.assertTrue(any("BAKP hasil scan" in n for n in r["notes"]))

    def test_tssr_tidak_menggeser_temuan_desain(self):
        f = [{"kind": "WARN_TSSR_HP_BEDA", "sev": "WARNING", "ket": "TSSR mencatat 1242 HP, HPDB 90 HP", "val": 1242, "lim": 90},
             {"kind": "WARN_HP_JAUH_LEWAT_JALUR", "sev": "WARNING", "ket": "H00001 (baris 5 HPDB): x", "val": 57, "lim": 50}]
        r = R.build(f)
        self.assertLess(r["text"].index("lewat jalur"), r["text"].index("TSSR"))


if __name__ == "__main__":
    unittest.main()

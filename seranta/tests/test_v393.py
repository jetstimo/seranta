"""Uji unit Seranta 3.9.3: pengamanan rilis berlapis (sidik kunci, cek silang, verifikasi online).
Jalankan: python tests/test_v393.py"""
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import keaslian as K   # noqa: E402


class Pengaman(unittest.TestCase):
    def test_sidik_resmi_konsisten(self):
        self.assertEqual(K.sidik(K.from_ints(K.KUNCI_PUBLIK)), K.SIDIK_RESMI)
        self.assertEqual(K.cermin_beda(ROOT), [])            # metadata.txt, NOTICE.md, README.md memuat sidik resmi

    def test_ganti_kunci_terdeteksi(self):
        d = tempfile.mkdtemp()
        old, old_fp = K.KUNCI_PUBLIK, K.SIDIK_RESMI
        try:
            for f in K.CERMIN:
                shutil.copy(os.path.join(ROOT, f), d)
            open(os.path.join(d, "a.py"), "w").write("x = 1\n")
            sk = os.urandom(32)
            K.KUNCI_PUBLIK, K.SIDIK_RESMI = tuple(K.to_ints(K.public_key(sk))), old_fp
            K.write_signed(d, "9.9.9", sk)
            K._CACHE.clear()
            code, _v, det = K.check(d)
            self.assertEqual(code, "TIDAK_RESMI")             # kunci penyerang, SIDIK_RESMI tetap
            self.assertIn("kunci diganti", det)
            self.assertIn(old_fp, K.status(root=d))
        finally:
            K.KUNCI_PUBLIK, K.SIDIK_RESMI = old, old_fp
            K._CACHE.clear()
            shutil.rmtree(d)

    def test_cermin_diubah(self):
        d = tempfile.mkdtemp()
        try:
            for f in K.CERMIN:
                shutil.copy(os.path.join(ROOT, f), d)
            p = os.path.join(d, "NOTICE.md")
            with open(p, encoding="utf-8") as fh:
                t = fh.read()
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(t.replace(K.SIDIK_RESMI, "0000-0000-0000-0000"))
            self.assertEqual(K.cermin_beda(d), ["NOTICE.md"])
        finally:
            shutil.rmtree(d)

    def test_verifikasi_online(self):
        d = tempfile.mkdtemp()
        old, old_fp = K.KUNCI_PUBLIK, K.SIDIK_RESMI
        try:
            for f in K.CERMIN:
                shutil.copy(os.path.join(ROOT, f), d)
            sk = os.urandom(32)
            fp = K.sidik(K.public_key(sk))
            for f in K.CERMIN:
                p = os.path.join(d, f)
                with open(p, encoding="utf-8") as fh:
                    t = fh.read()
                with open(p, "w", encoding="utf-8") as fh:
                    fh.write(t.replace(old_fp, fp))
            K.KUNCI_PUBLIK, K.SIDIK_RESMI = tuple(K.to_ints(K.public_key(sk))), fp
            man = K.write_signed(d, "9.9.9", sk)
            K._CACHE.clear()
            reg = {"kunci_sidik": fp, "rilis": {"9.9.9": {"manifest": K.sidik_manifest(man)}}}
            self.assertEqual(K.verify_online(lambda u: json.dumps(reg).encode(), root=d)[0], "TERVERIFIKASI")
            reg["rilis"]["9.9.9"]["manifest"] = [0] * 8
            self.assertEqual(K.verify_online(lambda u: json.dumps(reg).encode(), root=d)[0], "TIDAK_TERDAFTAR")
            reg["kunci_sidik"] = "1111-1111-1111-1111"
            self.assertEqual(K.verify_online(lambda u: json.dumps(reg).encode(), root=d)[0], "BEDA_KUNCI")

            def offline(u):
                raise IOError("offline")
            self.assertEqual(K.verify_online(offline, root=d)[0], "GAGAL")
        finally:
            K.KUNCI_PUBLIK, K.SIDIK_RESMI = old, old_fp
            K._CACHE.clear()
            shutil.rmtree(d)


if __name__ == "__main__":
    unittest.main()

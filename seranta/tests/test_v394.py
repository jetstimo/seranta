"""Uji unit Seranta 3.9.4 (murni Python): zoom asli citra Esri untuk peta dasar.
Jalankan: python tests/test_v394.py"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import basemap as B   # noqa: E402


class ZoomAsli(unittest.TestCase):
    def test_tile_xy_tomohon(self):
        # diperiksa langsung ke server Esri (Nov 2026): Tomohon punya citra di zoom 18, tidak di zoom 19
        self.assertEqual(B.tile_xy(124.8355, 1.3395, 19), (443948, 260193))
        self.assertEqual(B.tile_xy(124.8355, 1.3395, 18), (221974, 130096))

    def test_tilemap_url(self):
        self.assertTrue(B.tilemap_url(124.8355, 1.3395, 19).endswith("/tilemap/19/260192/443947/3/3"))

    def test_parse(self):
        self.assertFalse(B.parse_tilemap('{"data":[0,0,0,0,0,0,0,0,0],"valid":true}'))
        self.assertTrue(B.parse_tilemap('{"data":[1,1,1,1,1,1,1,1,1],"valid":true}'))
        self.assertFalse(B.parse_tilemap('{"data":[1,1,1,1,0,0,0,0,0],"valid":true}'))
        self.assertFalse(B.parse_tilemap("bukan json"))

    def test_zmax_aman(self):
        self.assertEqual(B.ZMAX_DEFAULT["sat"], 17)
        self.assertIn("zmax=%d", B.SOURCES["sat"][1])


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""Tulis out/indeks.json: daftar paket data jalan per pulau (nama berkas, kotak wilayah, ukuran, SHA-256, tanggal)."""
import hashlib
import json
import os
import sys
import time

from osgeo import ogr

out = sys.argv[1]
items = []
for fn in sorted(os.listdir(out)):
    if not fn.endswith(".gpkg"):
        continue
    p = os.path.join(out, fn)
    ds = ogr.Open(p)
    lyr = ds.GetLayerByName("jalan_osm")
    x0, x1, y0, y1 = lyr.GetExtent()
    n = lyr.GetFeatureCount()
    ds = None
    with open(p, "rb") as fh:
        sha = hashlib.sha256(fh.read()).hexdigest()
    items.append({"file": fn, "bbox": [round(x0, 4), round(y0, 4), round(x1, 4), round(y1, 4)], "features": n,
                  "bytes": os.path.getsize(p), "sha256": sha})
    print(fn, n, os.path.getsize(p))
if not items or any(i["features"] < 100 for i in items):
    sys.exit("paket kosong/terlalu kecil - rilis dibatalkan")
with open(os.path.join(out, "indeks.json"), "w", encoding="utf-8") as fh:
    json.dump({"versi": 1, "dibuat": time.strftime("%Y-%m-%d"), "sumber": "Geofabrik (OpenStreetMap), ODbL",
               "atribusi": "(c) OpenStreetMap contributors, ODbL - openstreetmap.org/copyright", "paket": items}, fh, indent=1)

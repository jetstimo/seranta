# -*- coding: utf-8 -*-
"""Kompres tiap paket (.gpkg -> .gpkg.zip) dan tulis out/indeks.json: nama berkas, kotak wilayah, petak 1 derajat
yang berisi data, ukuran, SHA-256 berkas zip, tanggal."""
import hashlib
import json
import os
import sys
import time
import zipfile

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
    cells = set()          # petak 1 derajat yang berisi data: Seranta hanya mengunduh pulau yang benar-benar mencakup cluster
    for f in lyr:
        g = f.GetGeometryRef()
        if g is not None:
            e = g.GetEnvelope()
            for x in range(int(e[0] // 1), int(e[1] // 1) + 1):
                for y in range(int(e[2] // 1), int(e[3] // 1) + 1):
                    cells.add("%d_%d" % (x, y))
    ds = None
    z = p + ".zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.write(p, fn)
    os.remove(p)
    with open(z, "rb") as fh:
        sha = hashlib.sha256(fh.read()).hexdigest()
    items.append({"file": fn + ".zip", "bbox": [round(x0, 4), round(y0, 4), round(x1, 4), round(y1, 4)], "features": n,
                  "bytes": os.path.getsize(z), "sha256": sha, "sel": sorted(cells)})
    print(fn, n, os.path.getsize(z))
if not items or any(i["features"] < 100 for i in items):
    sys.exit("paket kosong/terlalu kecil - rilis dibatalkan")
with open(os.path.join(out, "indeks.json"), "w", encoding="utf-8") as fh:
    json.dump({"versi": 1, "dibuat": time.strftime("%Y-%m-%d"), "sumber": "Geofabrik (OpenStreetMap), ODbL",
               "atribusi": "(c) OpenStreetMap contributors, ODbL - openstreetmap.org/copyright", "paket": items}, fh, indent=1)

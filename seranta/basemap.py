# -*- coding: utf-8 -*-
# Seranta - FTTH Design Assistant - peta dasar pembuktian QC (citra satelit / peta jalan) di kanvas QGIS
# Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later (see LICENSE).
"""Satu layer XYZ di dasar daftar layer, dipakai ulang untuk semua cluster/wilayah:

  * ringan: hanya ubin yang terlihat di layar yang diunduh, disimpan di cache jaringan QGIS; pindah wilayah tidak
    menambah layer, tidak ada data yang ditulis ke folder cluster, tidak ada pustaka tambahan;
  * tidak mengubah hasil QC: peta dasar hanya latar untuk membuktikan temuan (HP ganda, akses, jalur) di layar,
    di gambar 'Copy picture' dan di laporan Word Navigator;
  * offline: layer tetap ada tetapi kosong; data jaringan dan temuan tetap tampil normal;
  * pilihan pengguna (Satelit / Peta jalan / Tanpa) disimpan di QgsSettings 'seranta/basemap'.

Sumber: Esri World Imagery (citra satelit, atribusi Esri, Maxar, Earthstar Geographics) dan OpenStreetMap (peta jalan,
atribusi kontributor OpenStreetMap). Sama dengan pilihan peta dasar di laporan HTML Seranta."""
try:
    from . import _log
except ImportError:  # modul lepas (uji unit)
    import _log

KEY = "seranta/basemap"
PROP = "seranta_basemap"
CHOICES = ("sat", "osm", "none")
LABELS = {"sat": "Satellite imagery", "osm": "Street map (OSM)", "none": "No base map"}
SOURCES = {
    "sat": ("Seranta base map - satellite (Esri World Imagery)",
            "type=xyz&url=https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
            "&zmax=19&zmin=0",
            "Imagery (c) Esri, Maxar, Earthstar Geographics, and the GIS User Community"),
    "osm": ("Seranta base map - streets (OpenStreetMap)",
            "type=xyz&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png&zmax=19&zmin=0",
            "(c) OpenStreetMap contributors"),
}


def choice():
    """Pilihan tersimpan; bawaan 'sat' (citra satelit) karena paling berguna untuk membuktikan temuan survei."""
    try:
        from qgis.core import QgsSettings
        v = str(QgsSettings().value(KEY, "sat") or "sat")
    except Exception as _e:
        _log.note(_e)
        v = "sat"
    return v if v in CHOICES else "sat"


def set_choice(kind):
    try:
        from qgis.core import QgsSettings
        QgsSettings().setValue(KEY, kind if kind in CHOICES else "sat")
    except Exception as _e:
        _log.note(_e)


def layers():
    """Layer peta dasar Seranta yang ada di proyek (biasanya 0 atau 1)."""
    from qgis.core import QgsProject
    out = []
    for lyr in QgsProject.instance().mapLayers().values():
        try:
            if lyr.customProperty(PROP):
                out.append(lyr)
        except Exception as _e:
            _log.note(_e)
    return out


def ensure(kind=None):
    """Pastikan tepat satu peta dasar jenis `kind` (bawaan: pilihan tersimpan) ada di dasar daftar layer.
    Tidak menambah apa pun bila sudah ada; 'none' melepas peta dasar Seranta. Kembali layer atau None. Tidak pernah
    melempar galat (QC tidak boleh gagal karena peta dasar)."""
    try:
        from qgis.core import QgsProject, QgsRasterLayer
        kind = kind or choice()
        have = layers()
        keep = [lyr for lyr in have if lyr.customProperty(PROP) == kind]
        drop = [lyr.id() for lyr in have if lyr not in keep[:1]]
        if drop:
            QgsProject.instance().removeMapLayers(drop)
        if kind == "none" or kind not in SOURCES:
            return None
        if keep:
            return keep[0]
        name, src, attr = SOURCES[kind]
        lyr = QgsRasterLayer(src, name, "wms")
        if not lyr.isValid():
            _log.note("peta dasar tidak valid: %s" % name)
            return None
        lyr.setCustomProperty(PROP, kind)
        try:
            md = lyr.metadata()
            md.setRights([attr])
            lyr.setMetadata(md)
        except Exception as _e:
            _log.note(_e)
        prj = QgsProject.instance()
        prj.addMapLayer(lyr, False)
        root = prj.layerTreeRoot()
        root.insertLayer(len(root.children()), lyr)      # paling bawah: latar, tidak menutupi data
        return lyr
    except Exception as _e:
        _log.note(_e)
        return None

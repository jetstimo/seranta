# -*- coding: utf-8 -*-
# Seranta - FTTH Design Assistant - peta dasar pembuktian QC (citra satelit / peta jalan) di kanvas QGIS
# Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later with section 7 terms (see LICENSE).
"""Satu layer XYZ di dasar daftar layer, dipakai ulang untuk semua cluster/wilayah:

  * ringan: hanya ubin yang terlihat di layar yang diunduh, disimpan di cache jaringan QGIS; pindah wilayah tidak
    menambah layer, tidak ada data yang ditulis ke folder cluster, tidak ada pustaka tambahan;
  * tidak mengubah hasil QC: peta dasar hanya latar untuk membuktikan temuan (HP ganda, akses, jalur) di layar,
    di gambar 'Copy picture' dan di laporan Word Navigator;
  * offline: layer tetap ada tetapi kosong; data jaringan dan temuan tetap tampil normal;
  * pilihan pengguna (Satelit / Peta jalan / Tanpa) disimpan di QgsSettings 'seranta/basemap'.

ZOOM ASLI CITRA (3.9.4). Esri World Imagery tidak punya citra setajam yang sama di semua tempat (Tomohon: ada sampai
zoom 18, tidak ada di zoom 19). Untuk ubin yang tidak ada, server mengirim GAMBAR PENGGANTI bertulisan "Map data not yet
available" (HTTP 200), sehingga layer dengan zmax=19 menampilkan tulisan itu berulang saat diperbesar. Seranta kini:
  1. memasang layer dengan zmax aman (17) lebih dulu, tanpa menunggu jaringan;
  2. menanyakan ketersediaan zoom 19 dan 18 di pusat wilayah QC ke layanan 'tilemap' Esri (balasan JSON kecil, tidak
     memblokir QGIS) lalu menaikkan zmax ke zoom tertinggi yang benar-benar ada; hasil disimpan per wilayah (~40 km);
  3. di atas zmax, QGIS memperbesar ubin terakhir dengan interpolasi bilinear: tetap tajam-halus, tanpa tulisan
     pengganti dan tanpa unduhan tambahan;
  4. memastikan cache jaringan QGIS minimal 1 GB agar ubin yang pernah dilihat tampil seketika saat kembali.

Sumber: Esri World Imagery (atribusi Esri, Maxar, Earthstar Geographics) dan OpenStreetMap (atribusi kontributor
OpenStreetMap). Sama dengan pilihan peta dasar di laporan HTML Seranta."""
import json
import math

try:
    from . import _log
except ImportError:  # modul lepas (uji unit)
    import _log

KEY = "seranta/basemap"
PROP = "seranta_basemap"
CHOICES = ("sat", "osm", "none")
LABELS = {"sat": "Satellite imagery", "osm": "Street map (OSM)", "none": "No base map"}
ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer"
ZSAFE = 17                       # zoom yang tersedia hampir di seluruh daratan (Esri World Imagery ~1,2 m/piksel)
SOURCES = {
    "sat": ("Seranta base map - satellite (Esri World Imagery)",
            "type=xyz&url=" + ESRI + "/tile/{z}/{y}/{x}&zmax=%d&zmin=0",
            "Imagery (c) Esri, Maxar, Earthstar Geographics, and the GIS User Community"),
    "osm": ("Seranta base map - streets (OpenStreetMap)",
            "type=xyz&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png&zmax=%d&zmin=0",
            "(c) OpenStreetMap contributors"),
}
ZMAX_DEFAULT = {"sat": ZSAFE, "osm": 19}
CACHE_MIN = 1024 * 1024 * 1024   # 1 GB cache jaringan QGIS
_ZOOM_CACHE = {}                 # (z8_x, z8_y) -> zoom asli tertinggi
_PENDING = []                    # balasan jaringan yang sedang berjalan (agar tidak dibuang garbage collector)


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


# ----------------------------------------------------------------------------------------------- zoom asli
def tile_xy(lon, lat, z):
    """Nomor ubin XYZ (Web Mercator) untuk lon/lat pada zoom z."""
    lat = max(-85.0511, min(85.0511, lat))
    n = 2 ** z
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.log(math.tan(math.radians(lat)) + 1.0 / math.cos(math.radians(lat))) / math.pi) / 2.0 * n)
    return min(max(x, 0), n - 1), min(max(y, 0), n - 1)


def tilemap_url(lon, lat, z):
    """Layanan 'tilemap' Esri: blok 3x3 ubin di sekitar titik; data[i] = 1 bila citra asli ada."""
    x, y = tile_xy(lon, lat, z)
    return "%s/tilemap/%d/%d/%d/3/3" % (ESRI, z, max(y - 1, 0), max(x - 1, 0))


def parse_tilemap(text):
    """True bila sebagian besar (>= 5 dari 9) ubin di sekitar pusat punya citra asli."""
    try:
        d = json.loads(text)
        data = d.get("data") or []
        return bool(d.get("valid", True)) and sum(1 for v in data if v) >= 5
    except Exception:
        return False


def _area_key(lon, lat):
    return tile_xy(lon, lat, 8)


def _set_zmax(lyr, zmax):
    """Ganti zmax layer XYZ tanpa membuat layer baru (posisi & gaya tetap)."""
    try:
        kind = lyr.customProperty(PROP)
        if kind not in SOURCES or int(lyr.customProperty("seranta_zmax") or 0) == zmax:
            return
        name, src, _attr = SOURCES[kind]
        opts = None
        try:
            from qgis.core import QgsDataProvider
            opts = QgsDataProvider.ProviderOptions()
        except Exception as _e:        # QGIS lama tanpa ProviderOptions: setDataSource 3 argumen
            _log.note(_e)
        if opts is not None:
            lyr.setDataSource(src % zmax, lyr.name(), "wms", opts)
        else:
            lyr.setDataSource(src % zmax, lyr.name(), "wms")
        lyr.setCustomProperty("seranta_zmax", zmax)
        _smooth(lyr)
        lyr.triggerRepaint()
    except Exception as _e:
        _log.note(_e)


def probe_native_zoom(lyr, lon, lat):
    """Tanyakan (tanpa memblokir) zoom asli tertinggi Esri di sekitar lon/lat; naikkan zmax layer bila ada."""
    key = _area_key(lon, lat)
    if key in _ZOOM_CACHE:
        _set_zmax(lyr, _ZOOM_CACHE[key])
        return
    try:
        from qgis.core import QgsNetworkAccessManager
        from qgis.PyQt.QtCore import QUrl
        from qgis.PyQt.QtNetwork import QNetworkRequest
    except Exception as _e:
        _log.note(_e)
        return
    lid = lyr.id()

    def ask(z):
        rep = QgsNetworkAccessManager.instance().get(QNetworkRequest(QUrl(tilemap_url(lon, lat, z))))
        _PENDING.append(rep)

        def done():
            try:
                ok = rep.error() == 0 and parse_tilemap(bytes(rep.readAll()).decode("utf-8", "replace"))
            except Exception as _e:
                _log.note(_e)
                ok = False
            finally:
                if rep in _PENDING:
                    _PENDING.remove(rep)
                rep.deleteLater()
            if ok or z <= ZSAFE + 1:
                zz = z if ok else ZSAFE
                _ZOOM_CACHE[key] = zz
                from qgis.core import QgsProject
                target = QgsProject.instance().mapLayer(lid)
                if target is not None:
                    _set_zmax(target, zz)
            else:
                ask(z - 1)
        rep.finished.connect(done)
    ask(19)


def _smooth(lyr):
    """Perbesaran di atas zoom asli dengan interpolasi bilinear (halus, bukan kotak-kotak)."""
    try:
        from qgis.core import QgsBilinearRasterResampler
        rf = lyr.resampleFilter()
        if rf is not None:
            rf.setZoomedInResampler(QgsBilinearRasterResampler())
            rf.setMaxOversampling(2.0)
    except Exception as _e:
        _log.note(_e)


def ensure_cache():
    """Cache jaringan QGIS minimal 1 GB (bawaan QGIS 256 MB): ubin yang sudah pernah dilihat tampil seketika."""
    try:
        from qgis.core import QgsSettings
        st = QgsSettings()
        for key in ("cache/size-bytes", "cache/size"):
            v = st.value(key, None)
            if v not in (None, ""):
                try:
                    if int(float(v)) < CACHE_MIN:
                        st.setValue(key, CACHE_MIN)
                except (TypeError, ValueError):
                    pass
                return
        st.setValue("cache/size-bytes", CACHE_MIN)
    except Exception as _e:
        _log.note(_e)


def _center_wgs84(extent, crs):
    try:
        from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject
        c = extent.center()
        if crs is not None and crs.isValid() and crs.authid() != "EPSG:4326":
            ct = QgsCoordinateTransform(crs, QgsCoordinateReferenceSystem("EPSG:4326"), QgsProject.instance())
            c = ct.transform(c)
        if -180 <= c.x() <= 180 and -86 <= c.y() <= 86:
            return c.x(), c.y()
    except Exception as _e:
        _log.note(_e)
    return None


def ensure(kind=None, extent=None, crs=None):
    """Pastikan tepat satu peta dasar jenis `kind` (bawaan: pilihan tersimpan) ada di dasar daftar layer.
    extent/crs: wilayah QC yang baru dimuat; dipakai untuk menyesuaikan zoom asli citra. Tidak menambah apa pun bila
    layer sudah ada; 'none' melepas peta dasar Seranta. Kembali layer atau None. Tidak pernah melempar galat."""
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
            lyr = keep[0]
            if lyr.customProperty("seranta_zmax") in (None, ""):
                _set_zmax(lyr, ZMAX_DEFAULT[kind])        # layer dari versi lama (zmax 19 -> tulisan pengganti)
        else:
            ensure_cache()
            name, src, attr = SOURCES[kind]
            lyr = QgsRasterLayer(src % ZMAX_DEFAULT[kind], name, "wms")
            if not lyr.isValid():
                _log.note("peta dasar tidak valid: %s" % name)
                return None
            lyr.setCustomProperty(PROP, kind)
            lyr.setCustomProperty("seranta_zmax", ZMAX_DEFAULT[kind])
            _smooth(lyr)
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
        if kind == "sat" and extent is not None:
            c = _center_wgs84(extent, crs)
            if c:
                probe_native_zoom(lyr, c[0], c[1])
        return lyr
    except Exception as _e:
        _log.note(_e)
        return None

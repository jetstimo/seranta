# -*- coding: utf-8 -*-
"""3.15.10: AKSES DROP LEWAT JALAN DEPAN (masukan reviewer 25 Nov 2026, Procot RW 02).

Kasus: rumah menghadap jalan yang TIDAK punya jalur kabel/tiang. Tiang terdekat berada di jalan lain; garis lurusnya
< 50 m, tetapi garis itu melintas di atas rumah/pekarangan orang lain. Drop yang sah harus keluar lewat jalan depan rumah
lalu menyusuri ruang jalan sampai tiang - panjang sebenarnya bisa jauh > 50 m ("homepass ini ngegrab dari mana? tidak ada
pole karena dia hadap depan").

Model (berlaku sama di semua wilayah; data jalan OpenStreetMap semua kelas, termasuk gang/jalan permukiman):
  1. jalan depan = ruas jalan OSM terdekat dari titik rumah (F = proyeksi rumah ke garis tengah jalan; s = jarak rumah-F);
  2. drop LANGSUNG sah bila bagian garis lurus rumah->tiang yang berada di luar koridor jalan (+-9 m dari garis tengah)
     tidak lebih panjang dari halaman rumah itu sendiri (s + 3 m) -> panjang = garis lurus;
  3. selain itu drop lewat jalan: s + lurus di atas koridor jalan F->proyeksi tiang (bila seluruhnya di ruang jalan) atau
     menyusuri jaringan jalan (Dijkstra) + jarak tiang ke garis tengah jalan;
  4. dinilai hanya bila jalan depan rumah TIDAK dilewati jalur kabel (pola kasus reviewer) dan garis lurus <= batas
     (garis lurus > batas sudah HP_JAUH_DARI_TIANG).
Koridor 9 m = badan jalan permukiman 2 x 3,5 m + bahu + galat garis tengah OSM. Hasil > batas + 5 m (galat GPS ponsel
4,9 m, GPS.gov) = ERROR; batas..batas + 5 m = WARNING (ukur ulang / cek lapangan).
Data OSM tidak tersedia -> pemeriksaan dicatat 'tidak dicek', tidak pernah lolos diam-diam.
"""
import heapq
import math
import os
import re

CORR_M = 9.0
SNAP_POLE_M = 20.0
FRONT_MAX_M = 40.0      # rumah > 40 m dari jalan OSM mana pun: jalan depan tidak dikenal (gang belum dipetakan) -> lewati
OWN_YARD_EXTRA_M = 3.0
GPS_MARGIN_M = 5.0
GRID_M = 50.0

HW_LOCAL = ("motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street",
            "service", "track", "road", "pedestrian", "footway", "path", "steps")


def local_query(b, timeout_s=25):
    """Kueri Overpass: SEMUA jalan (termasuk gang/jalan permukiman) di kotak b (lon_min, lat_min, lon_max, lat_max)."""
    return ('[out:json][timeout:%d][maxsize:33554432][bbox:%f,%f,%f,%f];way[highway~"^(%s)(_link)?$"];out tags geom qt;'
            % (timeout_s, b[1], b[0], b[3], b[2], "|".join(HW_LOCAL)))


def keep_local(tags):
    hw = str((tags or {}).get("highway", "")).lower()
    return hw.replace("_link", "") in HW_LOCAL


def parse_local(js):
    out = []
    for el in (js or {}).get("elements", []):
        if el.get("type") != "way" or not el.get("geometry") or not keep_local(el.get("tags")):
            continue
        pts = [(g["lon"], g["lat"]) for g in el["geometry"] if g]
        if len(pts) >= 2:
            out.append({"kind": "lokal", "hw": str((el.get("tags") or {}).get("highway", "")), "pts": pts,
                        "name": (el.get("tags") or {}).get("name", "")})
    return out


# ---- PAKET JALAN LOKAL OFFLINE (Geofabrik .osm.pbf, mis. indonesia-latest.osm.pbf) -----------------------------------
# Server Overpass publik sering sibuk -> wilayah yang belum pernah diperiksa bisa 'TIDAK DICEK'. Jalan keluar: ekstrak OSM
# satu negara/pulau dari download.geofabrik.de (server unduhan biasa, stabil, diperbarui harian) ditaruh di folder data
# referensi; Seranta mengubahnya SEKALI menjadi GeoPackage ringkas (hanya garis jalan + kolom highway, indeks spasial) di
# cache, lalu setiap pemeriksaan membacanya tanpa internet. Ganti .pbf dengan yang lebih baru = paket dibuat ulang otomatis.
PAKET_PREFIX = "osm_lokal_paket_"


def _pbf_files(ref_dir):
    if not ref_dir or not os.path.isdir(ref_dir):
        return []
    return sorted(os.path.join(ref_dir, f) for f in os.listdir(ref_dir) if f.lower().endswith(".osm.pbf"))


def paket_path(pbf, cache_dir):
    st = os.stat(pbf)
    stem = re.sub(r"[^A-Za-z0-9]+", "_", os.path.basename(pbf))[:40]
    return os.path.join(cache_dir, "%s%s_%d_%d.gpkg" % (PAKET_PREFIX, stem, st.st_size, int(st.st_mtime)))


def build_paket(pbf, cache_dir, feedback=None):
    """.osm.pbf -> GeoPackage jalan lokal (semua kelas HW_LOCAL). Sekali per berkas .pbf. -> path atau None."""
    from osgeo import gdal
    out = paket_path(pbf, cache_dir)
    if os.path.exists(out) and os.path.getsize(out) > 0:
        return out
    os.makedirs(cache_dir, exist_ok=True)
    if feedback is not None:
        feedback.pushInfo("Preparing the offline local-road package from %s (%.0f MB) - once only (whole Indonesia: about "
                          "2-10 minutes) ..." % (os.path.basename(pbf), os.path.getsize(pbf) / 1e6))
    tmp = out + ".tmp.gpkg"
    try:
        if os.path.exists(tmp):
            os.remove(tmp)
        gdal.SetConfigOption("OSM_MAX_TMPFILE_SIZE", "1024")
        hw = ",".join("'%s'" % h for h in HW_LOCAL) + "," + ",".join("'%s_link'" % h for h in HW_LOCAL)
        ds = gdal.VectorTranslate(tmp, pbf, format="GPKG", layers=["lines"], where="highway IN (%s)" % hw,
                                  selectFields=["highway"], layerName="jalan_lokal",
                                  layerCreationOptions=["SPATIAL_INDEX=YES"])
        if ds is None:
            return None
        ds = None
        os.replace(tmp, out)
        # paket lama dari .pbf yang sudah diganti dibuang (hemat disk)
        for f in os.listdir(cache_dir):
            p = os.path.join(cache_dir, f)
            if f.startswith(PAKET_PREFIX) and f.endswith(".gpkg") and p != out and \
                    f.split("_")[3:4] == os.path.basename(out).split("_")[3:4]:
                try:
                    os.remove(p)
                except OSError:
                    pass
        return out
    except Exception:      # noqa: BLE001 - gagal = kembali ke server/cache, dicatat oleh pemanggil
        return None


def find_paket(ref_dir, cache_dir, feedback=None):
    """Paket jalan lokal yang tersedia: dari .osm.pbf di folder referensi (dibuat bila belum ada) + paket di cache."""
    out = []
    if cache_dir:
        # .pbf di folder referensi tim, atau di <cache>\pbf (lokal, tidak ikut sinkron OneDrive/Google Drive)
        for pbf in _pbf_files(ref_dir) + _pbf_files(os.path.join(cache_dir, "pbf")):
            p = build_paket(pbf, cache_dir, feedback)
            if p and p not in out:
                out.append(p)
        if os.path.isdir(cache_dir):
            out += [os.path.join(cache_dir, f) for f in sorted(os.listdir(cache_dir))
                    if f.startswith(PAKET_PREFIX) and f.endswith(".gpkg") and os.path.join(cache_dir, f) not in out]
    return out


def load_paket(paths, bbox):
    """Jalan lokal dari paket yang wilayahnya MENCAKUP bbox -> (daftar jalan, nama paket) atau (None, '')."""
    from osgeo import ogr
    for p in paths:
        ds = ogr.Open(p)
        if ds is None:
            continue
        lyr = ds.GetLayer(0)
        x0, x1, y0, y1 = lyr.GetExtent()
        if not (x0 <= bbox[0] and y0 <= bbox[1] and x1 >= bbox[2] and y1 >= bbox[3]):
            ds = None
            continue
        lyr.SetSpatialFilterRect(*bbox)
        out = []
        for f in lyr:
            g = f.GetGeometryRef()
            if g is None:
                continue
            parts = [g.GetGeometryRef(i) for i in range(g.GetGeometryCount())] if g.GetGeometryCount() else [g]
            for part in parts:
                pts = [(part.GetX(i), part.GetY(i)) for i in range(part.GetPointCount())]
                if len(pts) >= 2:
                    out.append({"kind": "lokal", "hw": f.GetField("highway") or "", "pts": pts, "name": ""})
        ds = None
        return out, os.path.basename(p)
    return None, ""


def _proj(p, a, b):
    vx, vy = b[0] - a[0], b[1] - a[1]
    L = vx * vx + vy * vy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / L))
    q = (a[0] + t * vx, a[1] + t * vy)
    return math.hypot(p[0] - q[0], p[1] - q[1]), q


class Akses:
    def __init__(self, roads_lonlat, routes_lonlat, poles_lonlat, lat0, lon0):
        self.kx = 111320.0 * math.cos(math.radians(lat0))
        self.ky = 110574.0
        self.o = (lon0, lat0)
        X = self.m
        # jalur kabel survei digambar mengikuti jalan/gang -> ikut dihitung sebagai jalan: gang yang belum ada di OSM
        # tetap dikenal (uji Panancangan: jalur di gang tanpa data OSM -> rumah di gang itu dulu salah dianggap menghadap
        # jalan OSM di belakangnya)
        self.segs = [(X(a), X(b)) for pts in list(roads_lonlat) + list(routes_lonlat) for a, b in zip(pts, pts[1:])]
        self.idx = {}
        for i, (a, b) in enumerate(self.segs):
            for gx in range(int(min(a[0], b[0]) // GRID_M) - 1, int(max(a[0], b[0]) // GRID_M) + 2):
                for gy in range(int(min(a[1], b[1]) // GRID_M) - 1, int(max(a[1], b[1]) // GRID_M) + 2):
                    self.idx.setdefault((gx, gy), []).append(i)
        self.route = [(X(a), X(b)) for pts in routes_lonlat for a, b in zip(pts, pts[1:])]
        self.ridx = {}
        for i, (a, b) in enumerate(self.route):
            for gx in range(int(min(a[0], b[0]) // GRID_M) - 1, int(max(a[0], b[0]) // GRID_M) + 2):
                for gy in range(int(min(a[1], b[1]) // GRID_M) - 1, int(max(a[1], b[1]) // GRID_M) + 2):
                    self.ridx.setdefault((gx, gy), []).append(i)
        self.n_osm = sum(max(0, len(pts) - 1) for pts in roads_lonlat)
        self.G = {}
        for a, b in self.segs:
            self._add(self._r(a), self._r(b))
        # jaringan jalur survei disambung ke jaringan jalan OSM: tiap titik jalur ke ruas OSM terdekat (<= koridor)
        for i in range(self.n_osm, len(self.segs)):
            for v in self.segs[i]:
                d, q, j = self.near_road(v, osm_only=True)
                if q is not None and d <= CORR_M:
                    self._link(q, j)
                    self._add(self._r(v), self._r(q))
        self.poles = [(n, X(p)) for n, p in poles_lonlat]
        self.pnode = {}
        self.pproj = []
        for k, (n, q) in enumerate(self.poles):
            d, qq, i = self.near_road(q)
            self.pproj.append((d, qq))
            if qq is not None and d <= SNAP_POLE_M:
                self._link(qq, i)
                self.pnode.setdefault(self._r(qq), []).append((k, d))
                # juga ke jalan OSM terdekat (tiang di jalur yang tidak berimpit titik dengan jalan OSM)
                d2, q2, i2 = self.near_road(q, osm_only=True)
                if q2 is not None and d2 <= SNAP_POLE_M and i2 != i:
                    self._link(q2, i2)
                    self.pnode.setdefault(self._r(q2), []).append((k, d2))

    def _link(self, q, i):
        qn = self._r(q)
        self._add(qn, self._r(self.segs[i][0]))
        self._add(qn, self._r(self.segs[i][1]))
        return qn

    def m(self, p):
        return ((p[0] - self.o[0]) * self.kx, (p[1] - self.o[1]) * self.ky)

    @staticmethod
    def _r(p):
        return (round(p[0], 1), round(p[1], 1))

    def _add(self, a, b):
        w = math.hypot(a[0] - b[0], a[1] - b[1])
        self.G.setdefault(a, []).append((b, w))
        self.G.setdefault(b, []).append((a, w))

    def near_road(self, p, osm_only=False):
        best = (1e9, None, None)
        for i in self.idx.get((int(p[0] // GRID_M), int(p[1] // GRID_M)), ()):
            if osm_only and i >= self.n_osm:
                continue
            d, q = _proj(p, *self.segs[i])
            if d < best[0]:
                best = (d, q, i)
        return best

    def route_near(self, p, r=CORR_M):
        return any(_proj(p, *self.route[i])[0] <= r
                   for i in self.ridx.get((int(p[0] // GRID_M), int(p[1] // GRID_M)), ()))

    def _outside(self, a, b):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(1, int(L))
        k = sum(1 for j in range(n) if self.near_road(
            (a[0] + (b[0] - a[0]) * (j + .5) / n, a[1] + (b[1] - a[1]) * (j + .5) / n))[0] > CORR_M)
        return L * k / n

    def _in_corr(self, a, b):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(1, int(L / 2))
        return all(self.near_road((a[0] + (b[0] - a[0]) * j / n, a[1] + (b[1] - a[1]) * j / n))[0] <= CORR_M
                   for j in range(n + 1))

    def drop(self, lonlat, limit=200.0):
        """-> dict(s, front_route, L, pole, how) atau None bila jalan depan tidak dikenal."""
        p = self.m(lonlat)
        s, f, i = self.near_road(p)
        if f is None or s > FRONT_MAX_M:
            return None
        res = {"s": s, "front_route": self.route_near(f), "L": None, "pole": None, "how": ""}
        best = [1e9, None, ""]
        for k, (_n, q) in enumerate(self.poles):
            dq = math.hypot(p[0] - q[0], p[1] - q[1])
            if dq < best[0] and dq <= 60 and self._outside(p, q) <= s + OWN_YARD_EXTRA_M:
                best = [dq, k, "langsung"]
        for k, (_n, q) in enumerate(self.poles):
            dpq, qq = self.pproj[k]
            if qq is None or dpq > SNAP_POLE_M:
                continue
            dq = math.hypot(f[0] - qq[0], f[1] - qq[1])
            if s + dq + dpq < best[0] and dq <= 80 and self._in_corr(f, qq):
                best = [s + dq + dpq, k, "lurus di atas ruang jalan"]
        fn = self._r(f)
        self._add(fn, self._r(self.segs[i][0]))
        self._add(fn, self._r(self.segs[i][1]))
        dist = {fn: 0.0}
        pq = [(0.0, fn)]
        while pq:
            dc, u = heapq.heappop(pq)
            if s + dc >= best[0] or dc > limit:
                break
            for k, dd in self.pnode.get(u, ()):
                if s + dc + dd < best[0]:
                    best = [s + dc + dd, k, "menyusuri jalan"]
            for v, w in self.G.get(u, ()):
                if dc + w < dist.get(v, 1e9):
                    dist[v] = dc + w
                    heapq.heappush(pq, (dc + w, v))
        if best[1] is not None:
            res.update(L=best[0], pole=self.poles[best[1]][0], how=best[2])
        return res

# -*- coding: utf-8 -*-
"""Akses rumah dari jalur survei (Python murni, bisa diuji tanpa QGIS).

Garis jalur survei (ROUTE CABLE) digambar di sepanjang jalan dan gang yang bisa dilalui kabel. Kabel drop dari tiang
ke rumah praktis mengikuti akses itu: dari tiang menyusuri jalur sampai titik terdekat ke rumah, lalu masuk ke rumah.
Dua hal yang tidak terlihat dari jarak garis lurus:

* rumah DALAM (jauh dari jalur mana pun, mis. di belakang rumah lain): akses masuknya perlu dicek di lapangan /
  street view (izin melintas pekarangan, gang yang belum digambar);
* jarak tiang ke rumah LEWAT AKSES lebih panjang dari batas walaupun garis lurusnya masih di bawah batas.

Semua koordinat dalam meter (proyeksi lokal). Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-2.0-or-later.
"""
import heapq
import math


def _proj(p, a, b):
    ax, ay = a
    dx, dy = b[0] - ax, b[1] - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 <= 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L2))
    q = (ax + t * dx, ay + t * dy)
    return math.hypot(p[0] - q[0], p[1] - q[1]), t, q


class Akses(object):
    """segs: [(kunci_a, kunci_b, titik_a, titik_b)] ruas jalur; pole_keys: kunci simpul yang berupa tiang."""

    def __init__(self, segs, pole_keys, cell=50.0):
        self.segs = [(a, b, pa, pb, math.hypot(pb[0] - pa[0], pb[1] - pa[1])) for a, b, pa, pb in segs]
        self.cell = cell
        self.grid = {}
        adj = {}
        for i, (a, b, pa, pb, L) in enumerate(self.segs):
            adj.setdefault(a, []).append((b, L))
            adj.setdefault(b, []).append((a, L))
            for cx in range(int(min(pa[0], pb[0]) // cell), int(max(pa[0], pb[0]) // cell) + 1):
                for cy in range(int(min(pa[1], pb[1]) // cell), int(max(pa[1], pb[1]) // cell) + 1):
                    self.grid.setdefault((cx, cy), []).append(i)
        # jarak setiap simpul ke tiang terdekat SEPANJANG jalur (Dijkstra banyak sumber, sekali saja)
        self.to_pole = {}
        heap = []
        for k in pole_keys:
            if k in adj:
                self.to_pole[k] = (0.0, k)
                heap.append((0.0, k))
        heapq.heapify(heap)
        while heap:
            d, k = heapq.heappop(heap)
            if d > self.to_pole[k][0]:
                continue
            for j, w in adj.get(k, ()):
                nd = d + w
                if j not in self.to_pole or nd < self.to_pole[j][0]:
                    self.to_pole[j] = (nd, self.to_pole[k][1])
                    heapq.heappush(heap, (nd, j))

    def foot(self, p, rmax=500.0):
        """(jarak tegak lurus ke jalur, indeks ruas, t) terdekat, mencari bertahap sampai rmax."""
        r = self.cell
        while r <= rmax * 2:
            k = int(r // self.cell)
            cx, cy = int(p[0] // self.cell), int(p[1] // self.cell)
            best = None
            for i in range(cx - k, cx + k + 1):
                for j in range(cy - k, cy + k + 1):
                    for s in self.grid.get((i, j), ()):
                        a, b, pa, pb, L = self.segs[s]
                        d, t, _q = _proj(p, pa, pb)
                        if best is None or d < best[0] or (d == best[0] and s < best[1]):
                            best = (d, s, t)
            if best is not None and best[0] <= r:
                return best
            r *= 2
        return best if best and best[0] <= rmax else None

    def access(self, p):
        """(jarak masuk dari jalur, jarak tiang->rumah lewat jalur, kunci tiang) atau None bila tidak terhubung."""
        ft = self.foot(p)
        if ft is None:
            return None
        h, s, t = ft
        a, b, pa, pb, L = self.segs[s]
        opts = []
        if a in self.to_pole:
            opts.append((self.to_pole[a][0] + t * L, self.to_pole[a][1]))
        if b in self.to_pole:
            opts.append((self.to_pole[b][0] + (1 - t) * L, self.to_pole[b][1]))
        if not opts:
            return h, None, None
        along, pole = min(opts, key=lambda o: (o[0], str(o[1])))
        return h, along + h, pole

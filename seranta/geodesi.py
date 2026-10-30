# -*- coding: utf-8 -*-
"""
Seranta - FTTH Design Assistant
Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-2.0-or-later.

GEODESI LOKAL WGS84 (versi 3.6.0, uji stabilitas antar-wilayah)
----------------------------------------------------------------
Semua jarak pendek (<= beberapa km) di modul murni Python memakai skala meter-per-derajat dari jari-jari
kelengkungan ellipsoid WGS84 pada lintang setempat (M = meridian, N = vertikal utama), bukan konstanta ekuator.
Hasilnya selisih < 0,01 % terhadap QgsDistanceArea (ellipsoid WGS84) di seluruh Indonesia (6 LU - 11 LS) dan
tetap benar di lintang lain, sehingga batas toleransi (0,5 m, 1 m, 5 m, 25 m, ...) bermakna sama di setiap wilayah.

Grid pencarian tetangga juga dihitung dalam meter: ukuran sel bujur diperlebar 1/cos(lintang terjauh) supaya
pencarian sel +-1 selalu mencakup radius yang diminta (sebelumnya sel bujur dalam derajat menyusut di lintang tinggi
sehingga pasangan di tepi radius bisa terlewat), dan indeks sel memakai floor (bukan int) agar sel di sekitar ekuator
dan meridian 0 tidak berukuran ganda.
"""
import math

WGS84_A = 6378137.0
WGS84_E2 = 0.00669437999014
_D2R = math.pi / 180.0


def m_per_deg(lat):
    """(meter per derajat bujur, meter per derajat lintang) pada lintang lat (derajat), ellipsoid WGS84."""
    s = math.sin(lat * _D2R)
    w = 1.0 - WGS84_E2 * s * s
    n = WGS84_A / math.sqrt(w)
    m = WGS84_A * (1.0 - WGS84_E2) / (w * math.sqrt(w))
    return n * math.cos(lat * _D2R) * _D2R, m * _D2R


def dist_m(x1, y1, x2, y2):
    """Jarak (m) dua titik lon/lat berdekatan (proyeksi lokal di lintang tengah)."""
    kx, ky = m_per_deg((y1 + y2) / 2.0)
    return math.hypot((x2 - x1) * kx, (y2 - y1) * ky)


def cell_deg(cell_m, lats=()):
    """Ukuran sel grid (derajat bujur, derajat lintang) yang menjamin sel >= cell_m meter di semua titik.
    lats: lintang titik-titik yang akan dimasukkan grid (dipakai lintang terjauh dari ekuator)."""
    lat_max = 0.0
    for v in lats:
        a = abs(v)
        if a > lat_max:
            lat_max = a
    lat_max = min(lat_max + 0.5, 89.0)
    kx, _ = m_per_deg(lat_max)
    _, ky = m_per_deg(0.0)        # meter per derajat lintang terkecil di ekuator
    return cell_m * 1.001 / kx, cell_m * 1.001 / ky


def cell_of(x, y, cell):
    """Indeks sel (floor) untuk ukuran sel (cx, cy) derajat."""
    return int(math.floor(x / cell[0])), int(math.floor(y / cell[1]))

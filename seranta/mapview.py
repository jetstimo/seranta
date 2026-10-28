# -*- coding: utf-8 -*-
"""Seranta - peta temuan interaktif di laporan HTML (Leaflet 1.9.4, BSD-2, disematkan; tanpa internet tetap jalan).

Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-2.0-or-later.

Objek jaringan (homepass, tiang, perangkat, kabel, batas) beserta atributnya dan setiap temuan QC digambar di satu peta.
Klik temuan -> isi temuan, nilai vs batas, gambar, objek & temuan di sekitar, tautan Google Earth/Maps/Street View.
Klik objek -> atribut lengkap + temuan yang melekat padanya. Peta dasar citra satelit/jalan hanya dimuat bila dipilih
dan ada internet (atribusi penyedia ditampilkan)."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ASSET = os.path.join(HERE, "assets", "map")
MAX_ATTR = 24


def _r(v, n=7):
    return round(float(v), n)


def _clean(attrs):
    out = {}
    for k, v in (attrs or {}).items():
        if v is None or isinstance(v, (list, dict, tuple, set, bytes)):
            continue
        s = str(v).strip()
        if s in ("", "-", "None", "NULL", "nan"):
            continue
        out[str(k)] = s[:160]
        if len(out) >= MAX_ATTR:
            break
    return out


def data_from_scene(scene, finds):
    """scene: snapshot.Scene (opsional atribut di scene.attrs_*); finds: [{fid, sev, lon, lat, line?, value?, limit?, unit?}]."""
    objs = []
    pa = getattr(scene, "attrs_p", None) or []
    la = getattr(scene, "attrs_l", None) or []
    ya = getattr(scene, "attrs_y", None) or []
    for i, (ring, kind) in enumerate(scene.polys):
        objs.append({"k": kind, "t": "pg", "c": [[_r(x), _r(y)] for x, y in ring], "n": "", "a": _clean(ya[i] if i < len(ya) else {})})
    for i, (pts, kind) in enumerate(scene.lines):
        a = la[i] if i < len(la) else {}
        objs.append({"k": kind, "t": "ln", "c": [[_r(x), _r(y)] for x, y in pts], "n": str(a.get("Nama", "") if a else ""),
                     "a": _clean(a)})
    for i, (x, y, kind, label) in enumerate(scene.points):
        objs.append({"k": kind, "t": "pt", "c": [_r(x), _r(y)], "n": label or "", "a": _clean(pa[i] if i < len(pa) else {})})
    fs = []
    for f in finds:
        try:
            item = {"id": f["fid"], "s": f.get("sev") or "INFO", "c": [_r(f["lon"]), _r(f["lat"])]}
        except (KeyError, TypeError, ValueError):
            continue
        ln = f.get("line")
        if ln and len(ln) > 1:
            item["ln"] = [[_r(x), _r(y)] for x, y in ln]
        for k_src, k in (("value", "v"), ("limit", "lim")):
            v = f.get(k_src)
            if isinstance(v, (int, float)):
                item[k] = v
        if f.get("unit"):
            item["u"] = f["unit"]
        # teks cadangan bila temuan tidak tampil di daftar halaman (daftar dibatasi per aturan)
        for k_src, k in (("title", "ti"), ("arti", "ms"), ("fix", "fx"), ("obj", "ob")):
            if f.get(k_src):
                item[k] = str(f[k_src])[:300]
        fs.append(item)
    return {"L": objs, "F": fs}


def _read(name):
    with open(os.path.join(ASSET, name), encoding="utf-8") as fh:
        return fh.read()


def block(data, title="Peta temuan QC"):
    """Potongan HTML siap sisip (gaya + skrip disematkan). Kosong bila tidak ada data atau aset tidak ada."""
    if not data or not (data.get("F") or data.get("L")):
        return ""
    try:
        lcss, ljs, mcss, mjs = _read("leaflet.css"), _read("leaflet.js"), _read("seranta_map.css"), _read("seranta_map.js")
    except OSError:
        return ""
    js_data = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    rows = (("l", "#5CF2E8", "Kabel / jalur baru"), ("l", "#F7D774", "Kabel existing / colo"), ("l", "#FB5607", "Kabel feeder"),
            ("p", "#FF9F1C", "Tiang baru"), ("p", "#B8C2CC", "Tiang existing"), ("p", "#2EC4B6", "Homepass"),
            ("p", "#3A86FF", "FAT"), ("p", "#8338EC", "FDT"), ("p", "#FF006E", "Closure"))
    legend = "".join("<div><i class='%s' style='background:%s'></i>%s</div>" % (k, c, t) for k, c, t in rows) + \
        "<div><i class='p' style='background:#fff;box-shadow:0 0 0 2px #DA1E28'></i>Titik temuan (warna = tingkat)</div>"
    return ("<style>%s\n%s</style>"
            "<section class='smap' id='smap' aria-label='%s'>"
            "<div class='smap-head'><h2>%s</h2><span class='sevs' role='group' aria-label='Saring temuan'></span>"
            "<span class='lys' role='group' aria-label='Lapisan'></span><span class='sp'></span>"
            "<input type='search' data-q placeholder='Cari ID temuan / nama tiang / HP' aria-label='Cari di peta'>"
            "<select data-base aria-label='Peta dasar'><option value='none'>Tanpa peta dasar (offline)</option>"
            "<option value='sat'>Citra satelit (online)</option><option value='osm'>Peta jalan (online)</option></select>"
            "<button type='button' class='sbtn' data-meas title='Ukur jarak (M)'>Ukur</button>"
            "<button type='button' class='sbtn' data-snap title='Salin gambar tampilan peta sekarang (tempel di Word)'>Salin gambar</button>"
            "<button type='button' class='sbtn' data-snapd title='Unduh gambar tampilan peta sekarang (PNG)'>Unduh gambar</button>"
            "<button type='button' class='sbtn' data-fit title='Tampilkan semua'>Semua</button>"
            "<button type='button' class='sbtn' data-full title='Layar penuh (F)'>Layar penuh</button></div>"
            "<div class='smap-body'><div class='smap-map'><div class='smap-legend'>%s</div><div class='smap-meas'></div>"
            "<div class='smap-coord'>-</div><div class='smap-off'>Peta dasar tidak termuat (tidak ada internet). Data jaringan dan temuan "
            "tetap tampil.</div></div>"
            "<aside class='smap-panel'><div class='smap-pt'></div><div class='smap-pb' aria-live='polite'></div>"
            "<div class='smap-nav'><button type='button' class='sbtn' data-prev>&larr; Sebelumnya</button><span class='c'></span>"
            "<button type='button' class='sbtn' data-next>Berikutnya &rarr;</button></div></aside></div></section>"
            "<script>%s</script><script>window.SERANTA_MAP=%s;</script><script>%s</script>"
            % (lcss, mcss, title, title, legend, ljs, js_data, mjs))

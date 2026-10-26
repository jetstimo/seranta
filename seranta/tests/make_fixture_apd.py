# -*- coding: utf-8 -*-
"""Buat dataset uji APD 'golden' dari KMZ strand nyata (tiang, jalur, HP) - untuk uji regresi alat 4.

    python tests/make_fixture_apd.py <KMZ_STRAND.kmz> <folder_keluaran>

Hasil: APD_FIXTURE.kmz (Homepass/FAT Coverage/Net_Nodes/Net_Cables/Pole, dengan ExtendedData seperti export desain otomatis),
FEEDER_FIXTURE.kmz, BOM_FIXTURE.csv dan expected.json (daftar cacat yang SENGAJA disisipkan + aturan yang wajib
menemukannya). Desain ini sintetis (bukan desain desain otomatis nyata); hanya geometri lapangannya yang nyata.
"""
import json
import math
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import qc_core as Q  # noqa: E402


def clip(poly, a, b, c):
    """Potong poligon dengan setengah bidang a*x + b*y <= c (Sutherland-Hodgman)."""
    out = []
    for i in range(len(poly)):
        p, q = poly[i], poly[(i + 1) % len(poly)]
        fp, fq = a * p[0] + b * p[1] - c, a * q[0] + b * q[1] - c
        if fp <= 0:
            out.append(p)
        if fp * fq < 0:
            t = fp / (fp - fq)
            out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    return out


def voronoi(sites, box):
    cells = []
    for i, s in enumerate(sites):
        poly = list(box)
        for j, t in enumerate(sites):
            if i == j:
                continue
            a, b = t[0] - s[0], t[1] - s[1]
            c = (t[0] ** 2 + t[1] ** 2 - s[0] ** 2 - s[1] ** 2) / 2.0
            poly = clip(poly, a, b, c)
            if not poly:
                break
        cells.append(poly)
    return cells


def kml_pt(name, x, y, style="", data=None):
    ed = "".join('<Data name="%s"><value>%s</value></Data>' % (k, v) for k, v in (data or {}).items())
    return ("<Placemark><name>%s</name>%s%s<Point><coordinates>%.8f,%.8f,0</coordinates></Point></Placemark>"
            % (name, ("<styleUrl>#%s</styleUrl>" % style) if style else "", ("<ExtendedData>%s</ExtendedData>" % ed) if ed else "", x, y))


def kml_ln(name, pts, style=""):
    return ("<Placemark><name>%s</name>%s<LineString><coordinates>%s</coordinates></LineString></Placemark>"
            % (name, ("<styleUrl>#%s</styleUrl>" % style) if style else "", " ".join("%.8f,%.8f,0" % p for p in pts)))


def main(strand, out):
    os.makedirs(out, exist_ok=True)
    src = Q.read_kmz(strand)
    hps = [(e["x"], e["y"]) for e in src.endpoints]
    poles = [(p["x"], p["y"], p["name"]) for p in src.poles]
    routes = [c["pts"] for c in src.cables]
    pr = src.proj()
    # FDT di tiang paling ujung barat laut jalur (sintetis)
    allpts = [p for r in routes for p in r]
    fdt_p = min(poles, key=lambda p: (p[0] - min(q[0] for q in allpts)) ** 2 + (p[1] - max(q[1] for q in allpts)) ** 2)
    # FAT: pilih tiang secara rakus (cakupan HP terbanyak <= 100 m), kapasitas 16
    left = set(range(len(hps)))
    fats = []
    while left and len(fats) < 40:
        best = None
        for (x, y, nm) in poles:
            if any(abs(x - f[0]) < 1e-9 and abs(y - f[1]) < 1e-9 for f in fats):
                continue
            near = sorted((pr.d((x, y), hps[i]), i) for i in left)
            near = [i for d, i in near if d <= 100][:16]
            if best is None or len(near) > len(best[3]):
                best = (x, y, nm, near)
        if not best or not best[3]:
            break
        fats.append(best)
        left -= set(best[3])
    for i in sorted(left):            # sisa -> FAT terdekat yang masih ada slot
        f = min((f for f in fats if len(f[3]) < 16), key=lambda f: pr.d((f[0], f[1]), hps[i]))
        f[3].append(i)
    fats.sort(key=lambda f: pr.d((fdt_p[0], fdt_p[1]), (f[0], f[1])))
    code = "PLG1-FIX01-H01"
    nodes, sup = [], {}
    for k, (x, y, nm, g) in enumerate(fats, 1):
        fid = "N001.01.%02d" % k
        maxpp = max(pr.d((x, y), hps[i]) for i in g) * 1.25          # jalur ~1,25 x garis lurus
        nodes.append({"id": fid, "name": "%s-D01-%02d" % (code, k), "x": x, "y": y, "prem": len(g), "maxpp": round(maxpp, 1),
                      "supdist": round(pr.d((fdt_p[0], fdt_p[1]), (x, y)) * 1.3, 1)})
        for i in g:
            sup[i] = fid
    defects = []
    # --- cacat yang disisipkan ---
    e_ns = sorted(sup)[4]
    sup[e_ns] = ""
    defects.append(("SERVED_HP_NOT_SERVED", "HP E%06d tanpa SUPID" % (e_ns + 1)))
    lon_min = min(p[0] for p in hps) - 300 / pr.kx
    hps.append((lon_min, hps[0][1]))
    sup[len(hps) - 1] = nodes[0]["id"]
    defects.append(("HP_OUTSIDE_FAT_COVERAGE", "HP tambahan 300 m di barat batas coverage"))
    nodes[1]["x"] += 6.0 / pr.kx
    defects.append(("FAT_NOT_ON_POLE", "%s digeser 6 m dari tiang" % nodes[1]["name"]))
    if len(nodes) >= 4:
        nodes[3]["name"] = "%s-D01-%02d" % (code, len(nodes) + 2)
        defects.append(("FAT_LABEL_ORDER_INVALID", "nomor FAT melompat"))
    nodes[2]["maxpp"] = 165.0
    defects.append(("FAT_HP_OVER_150", "%s MAXPPDIST 165 m" % nodes[2]["name"]))
    fdt_prem = sum(n["prem"] for n in nodes) + 5
    defects.append(("FDT_PREMISES_MISMATCH", "premises ikon FDT +5"))
    # Voronoi coverage (kotak HP + 40 m)
    xs, ys = [p[0] for p in hps[:-1]], [p[1] for p in hps[:-1]]
    pad_x, pad_y = 40 / pr.kx, 40 / pr.ky
    box = [(min(xs) - pad_x, min(ys) - pad_y), (max(xs) + pad_x, min(ys) - pad_y), (max(xs) + pad_x, max(ys) + pad_y),
           (min(xs) - pad_x, max(ys) + pad_y)]
    # FAT Coverage seperti desain otomatis: dibentuk dari HP yang dilayani FAT -> sel Voronoi per HP, pemilik = FAT induknya
    cells = voronoi(hps[:-1], box)
    own = [sup.get(i) or None for i in range(len(hps) - 1)]
    # kabel: jalur strand sebagai kabel distribusi 24D; satu kabel warna salah; satu ekor 130 m tanpa FAT
    ext = routes[0]
    end = ext[-1]
    prev = next(p for p in reversed(ext[:-1]) if pr.d(p, end) > 1.0)      # data strand bisa punya titik ganda
    dx, dy = (end[0] - prev[0]) * pr.kx, (end[1] - prev[1]) * pr.ky
    L = math.hypot(dx, dy) or 1.0
    tail = [end, (end[0] + dx / L * 130 / pr.kx, end[1] + dy / L * 130 / pr.ky)]
    defects.append(("CABLE_END_WITHOUT_FAT", "ekor kabel 130 m tanpa FAT"))
    defects.append(("LOOP_LENGTH_OVER_100M", "ekor kabel 130 m (> 100 m)"))
    defects.append(("CABLE_COLOR_MISMATCH", "kabel D01 #1 merah, seharusnya oranye 24 core"))
    defects.append(("KMZ_FOLDER_INVALID", "folder net_endpoints belum di-rename Homepass"))
    defects.append(("KMZ_ICON_INVALID", "ikon files/FAT.png tidak disertakan di KMZ"))
    idle = (max(p[0] for p in poles) + 80 / pr.kx, max(p[1] for p in poles))
    defects.append(("POLE_IDLE", "tiang NP-IDLE 80 m dari jalur"))
    styles = ('<Style id="c24"><LineStyle><color>ff00aaff</color><width>3</width></LineStyle></Style>'
              '<Style id="cbad"><LineStyle><color>ff0000ff</color><width>3</width></LineStyle></Style>'
              '<Style id="fat"><IconStyle><Icon><href>files/FAT.png</href></Icon></IconStyle></Style>'
              '<Style id="fdt"><IconStyle><Icon><href>files/FDT.png</href></Icon></IconStyle></Style>'
              '<Style id="cov"><LineStyle><color>ff0000ff</color><width>3</width></LineStyle><PolyStyle><color>4d00ffff</color></PolyStyle></Style>')
    hp_k = "".join(kml_pt("H%05d" % (i + 1), x, y, data={"ELEMENTID": "E%06d" % (i + 1), "SUPID": sup.get(i, ""), "CONNSTATUS": 9})
                   for i, (x, y) in enumerate(hps))
    byid = {n["id"]: n for n in nodes}
    cov_k = "".join("<Placemark><name>%s</name><styleUrl>#cov</styleUrl><ExtendedData><Data name=\"NODEID\"><value>%s</value></Data>"
                    "</ExtendedData><Polygon><outerBoundaryIs><LinearRing><coordinates>%s</coordinates></LinearRing>"
                    "</outerBoundaryIs></Polygon></Placemark>" % (byid[o]["name"], o, " ".join("%.8f,%.8f,0" % p for p in c + [c[0]]))
                    for o, c in zip(own, cells) if o and len(c) >= 3)
    node_k = kml_pt(code, fdt_p[0], fdt_p[1], "fdt", {"ELEMENTID": "N001.01", "SUPPORT": "FDT", "LEVEL": 2, "PREMISES": fdt_prem,
                                                       "SPLITTERS": "%dx1x4" % math.ceil(len(nodes) * 2 / 4.0)})
    node_k += "".join(kml_pt(n["name"], n["x"], n["y"], "fat", {"ELEMENTID": n["id"], "SUPPORT": "FAT", "LEVEL": 3, "SUPID": "N001.01",
                                                                "PREMISES": n["prem"], "MAXPPDIST": n["maxpp"], "SUPDIST": n["supdist"]})
                      for n in nodes)
    cab_k = "".join(kml_ln("D01 24D NEW INFRA", r, "cbad" if i == 0 else "c24") for i, r in enumerate(routes))
    cab_k += kml_ln("D01 24D NEW INFRA (loop)", tail, "c24")
    pole_k = "".join(kml_pt(nm, x, y) for x, y, nm in poles) + kml_pt("NP-IDLE", idle[0], idle[1])
    kml = ('<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>APD FIXTURE</name>%s'
           '<Folder><name>net_endpoints</name><visibility>0</visibility>%s</Folder>'
           '<Folder><name>FAT Coverage</name><visibility>0</visibility>%s</Folder>'
           '<Folder><name>Net_Nodes</name>%s</Folder><Folder><name>Net_Cables</name><Folder><name>24D</name>%s</Folder></Folder>'
           '<Folder><name>Pole</name>%s</Folder></Document></kml>') % (styles, hp_k, cov_k, node_k, cab_k, pole_k)
    apd = os.path.join(out, "APD_FIXTURE.kmz")
    with zipfile.ZipFile(apd, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("doc.kml", kml)
        z.writestr("files/FDT.png", b"\x89PNG\r\n\x1a\n")
    fx, fy = fdt_p[0] + 12 / pr.kx, fdt_p[1]
    fk = ('<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><Folder><name>FDT</name>%s</Folder>'
          '</Document></kml>') % kml_pt(code, fx, fy, data={"SUPPORT": "FDT"})
    with zipfile.ZipFile(os.path.join(out, "FEEDER_FIXTURE.kmz"), "w") as z:
        z.writestr("doc.kml", fk)
    defects.append(("FDT_LOCATION_MISMATCH", "FDT di paket Feeder bergeser 12 m"))
    newp = len(poles) + 1
    with open(os.path.join(out, "BOM_FIXTURE.csv"), "w", encoding="utf-8") as fh:
        fh.write("No,Item,Satuan,Qty\n1,Homepass,HP,%d\n2,FAT (ODP 16),unit,%d\n3,Tiang besi 7 m,btg,%d\n4,FDT 48 core,unit,1\n"
                 % (len(hps), len(nodes) - 1, newp + 3))
    defects.append(("BOM_FAT_MISMATCH", "BOM FAT kurang 1"))
    defects.append(("BOM_POLE_MISMATCH", "BOM tiang lebih 3"))
    exp = {"sumber_geometri": os.path.basename(strand), "hp": len(hps), "fat": len(nodes), "tiang": len(poles) + 1,
           "cacat_disisipkan": [{"rule_id": r, "keterangan": t} for r, t in defects]}
    with open(os.path.join(out, "expected.json"), "w", encoding="utf-8") as fh:
        json.dump(exp, fh, indent=1, ensure_ascii=False)
    return exp


def check(out):
    """Jalankan inti QC pada fixture dan bandingkan dengan expected.json -> (lolos, laporan)."""
    exp = json.load(open(os.path.join(out, "expected.json"), encoding="utf-8"))
    net = Q.read_kmz(os.path.join(out, "APD_FIXTURE.kmz"))
    feeder = Q.read_kmz(os.path.join(out, "FEEDER_FIXTURE.kmz"))
    prof = Q.get_profile("APD_1X4")[0]
    res = Q.run_all(net, prof, feeder=feeder, dist=net, fdt_status="NEW", bom_path=os.path.join(out, "BOM_FIXTURE.csv"),
                    cluster="FIXTURE")
    got = {}
    for f in Q.findings_of(res):
        got[f["rule_id"]] = got.get(f["rule_id"], 0) + 1
    rep, ok = [], True
    for d in exp["cacat_disisipkan"]:
        hit = got.get(d["rule_id"], 0)
        ok &= hit > 0
        rep.append("%s %-26s %-3d %s" % ("OK  " if hit else "MISS", d["rule_id"], hit, d["keterangan"]))
    extra = {k: v for k, v in got.items() if k not in {d["rule_id"] for d in exp["cacat_disisipkan"]}}
    rep.append("temuan lain (bukan cacat sisipan): %s" % (", ".join("%s %d" % kv for kv in sorted(extra.items())) or "-"))
    rep.append("status keseluruhan: %s" % Q.overall(res))
    return ok, rep, res


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    e = main(sys.argv[1], sys.argv[2])
    print("fixture: %d HP, %d FAT, %d cacat disisipkan -> %s" % (e["hp"], e["fat"], len(e["cacat_disisipkan"]), sys.argv[2]))
    ok, rep, _ = check(sys.argv[2])
    print("\n".join(rep))
    sys.exit(0 if ok else 1)

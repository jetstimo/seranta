# -*- coding: utf-8 -*-
# Seranta - FTTH Design Assistant - inti QC terpadu (tanpa QGIS; dapat diuji dengan Python biasa)
# Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-2.0-or-later (see LICENSE).
"""Inti QC Seranta yang dipakai alat 1 dan alat 4:

* Profil standar (profiles/*.json): setiap angka punya nilai, dasar (REGULASI/STANDAR/PRAKTIK/RISET/INTERNAL),
  sumber, dan status pengesahan; setiap temuan mencatat profile_id dan rule_version.
* Kontrak keluaran QC (spesifikasi O.2, selaras ISO 19157 "hasil kesesuaian hanya dari evaluasi nyata"):
  ERROR, WARNING, INFO, UNVERIFIED (data/aturan belum cukup -> TIDAK dihitung PASS), PASS.
* Pembaca KMZ APD (folder, atribut ExtendedData, gaya warna/ikon) dan model data jaringan pasca-desain
  (net_nodes, net_endpoints, net_cables, net_ServiceAreasVoronoi, pole, closure).
* Aturan QC APD: Served, FAT Coverage/Voronoi, ujung kabel & loop, multi-FDT, FDT COLO/NEW Feeder-Distribusi,
  rekonsiliasi BOM, jarak FAT-HP, urutan & kode FAT, FAT melayang, tiang nganggur, rentang tiang, FAT center,
  slack, crossing, KMZ (folder, ikon X, warna kabel, Existing Cluster).
"""
try:
    from . import _log
except ImportError:  # dijalankan sebagai modul lepas (uji unit)
    import _log
import csv
import json
import math
import os
import re
import zipfile
try:  # defusedxml bila terpasang; bila tidak, ElementTree standar (expat >= 2.4.1 menolak entity expansion / billion laughs,
    # entity eksternal tidak pernah diunduh). Data yang dibaca: KMZ/XLSX/.sdproj milik pengguna sendiri.
    import defusedxml.ElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET  # nosec B405

RULE_VERSION = "2026.10-r9"
SEVERITIES = ("ERROR", "WARNING", "UNVERIFIED", "INFO", "PASS")
SEV_RANK = {s: i for i, s in enumerate(SEVERITIES)}
DASAR_LABEL = {"INTERNAL+RISET": "kebijakan internal dengan dukungan riset", "REGULASI": "Regulasi Indonesia", "STANDAR": "Standar (ITU-T/GR/konstruksi distribusi)",
               "PRAKTIK": "Praktik industri (operator/vendor)", "RISET": "Riset peer-review",
               "INTERNAL": "kebijakan internal (Handbook/config desain otomatis)"}
REVIEW_STATES = ("OPEN", "VERIFIED", "FALSE_POSITIVE", "APPROVED_EXCEPTION", "RESOLVED")
HERE = os.path.dirname(os.path.abspath(__file__))


# =============================================================================================
# Profil standar
# =============================================================================================
def profile_dir():
    return os.path.join(HERE, "profiles")


def user_profile_dirs():
    """Folder profil milik pengguna/organisasi (di luar paket plugin, tidak ikut terhapus saat update):
    1) variabel lingkungan SERANTA_PROFILE_DIR, 2) pengaturan QGIS seranta/profile_dir,
    3) <folder profil QGIS>/seranta/profiles, 4) Documents/Seranta/profiles atau ~/Seranta/profiles."""
    out = []
    env = os.environ.get("SERANTA_PROFILE_DIR", "")
    if env:
        out.append(env)
    try:
        from qgis.core import QgsApplication, QgsSettings
        v = QgsSettings().value("seranta/profile_dir", "") or ""
        if v:
            out.append(str(v))
        base = QgsApplication.qualifiedSettingsDirPath() if hasattr(QgsApplication, "qualifiedSettingsDirPath") else ""
        if base:
            out.append(os.path.join(str(base), "seranta", "profiles"))
    # di luar QGIS (uji unit) cukup folder bawaan
    except Exception:  # nosec B110
        pass
    home = os.path.expanduser("~")
    out += [os.path.join(home, "Documents", "Seranta", "profiles"), os.path.join(home, "Seranta", "profiles")]
    return [d for d in dict.fromkeys(out) if d and os.path.isdir(d)]


def _read_profiles(folder, origin):
    out = {}
    for fn in sorted(os.listdir(folder)):
        if fn.lower().endswith(".json"):
            try:
                with open(os.path.join(folder, fn), encoding="utf-8") as fh:
                    d = json.load(fh)
                if d.get("profile_id") and isinstance(d.get("params"), dict):
                    d["_asal"] = origin
                    # versi aturan = versi logika kode yang menilai (bukan angka lama tertulis di file profil organisasi)
                    d["profile_rule_version"] = d.get("rule_version", "")
                    d["rule_version"] = RULE_VERSION
                    d["_file"] = os.path.join(folder, fn)
                    out[d["profile_id"]] = d
            except (OSError, ValueError):
                continue
    return out


def load_profiles(folder=None):
    """{profile_id: profil}: profil bawaan paket + profil pengguna (folder luar, dapat menimpa id yang sama).
    Urutan: profil pengguna bertanda "default": true, lalu APD_1X4, lalu sisanya menurut id."""
    if folder:
        out = _read_profiles(folder, "folder") if os.path.isdir(folder) else {}
    else:
        out = _read_profiles(profile_dir(), "bawaan") if os.path.isdir(profile_dir()) else {}
        for d in user_profile_dirs():
            out.update(_read_profiles(d, "pengguna"))
    return dict(sorted(out.items(), key=lambda kv: (not kv[1].get("default"), kv[0] != "APD_1X4", kv[0])))


def get_profile(pid=None, folder=None):
    """Profil menurut id. Id tak dikenal -> profil APD_1X4 + peringatan eksplisit (spesifikasi 14)."""
    profs = load_profiles(folder)
    if not profs:
        raise ValueError("Folder profil standar kosong/rusak: %s" % (folder or profile_dir()))
    if pid and pid in profs:
        return profs[pid], None
    first = next(iter(profs.values()))
    warn = None if not pid else ("Profil '%s' tidak dikenal - memakai %s (periksa pilihan profil)" % (pid, first["profile_id"]))
    return first, warn


def pv(prof, key, default=None):
    """Nilai parameter profil."""
    e = prof.get("params", {}).get(key)
    if e is None:
        return default
    return e.get("v", default) if isinstance(e, dict) else e


def pmeta(prof, key):
    e = prof.get("params", {}).get(key) or {}
    return e if isinstance(e, dict) else {"v": e}


def apply_overrides(prof, over, source):
    """Salin profil lalu timpa beberapa nilai (mis. dari .sdproj). Mengembalikan profil baru."""
    p = json.loads(json.dumps(prof))
    for k, v in (over or {}).items():
        meta = dict(pmeta(p, k))
        meta.update({"v": v, "sumber": "%s (dibaca dari %s)" % (meta.get("sumber", ""), source), "status": "APPROVED"})
        p["params"][k] = meta
    if over:
        p["profile_id"] = p["profile_id"] + "+SDPROJ"
    return p


def sdproj_overrides(path):
    """Baca config desain otomatis (.sdproj = zip berisi config.xml) -> nilai profil yang dapat ditimpa:
    FAT min/maks/target (NodeCapacityRule level 3), MAXPPDIST FAT, kapasitas FDT (premises),
    rasio splitter FDT, redaman kabel rata-rata."""
    try:
        with zipfile.ZipFile(path) as z:
            name = next((n for n in z.namelist() if n.lower().endswith("config.xml")), None)
            if not name:
                return {}
            s = z.read(name).decode("utf-8-sig", "ignore")
    except (OSError, zipfile.BadZipFile):
        return {}
    out = {}
    m = re.search(r'scope="\(L:3,[^"]*\)">\s*<Rules>\s*<NodeCapacityRule[^>]*>.*?<Minimum>(\d+)</Minimum>\s*'
                  r'<Maximum>(\d+)</Maximum>\s*<Target>(\d+)</Target>.*?<NodeDistanceRule[^>]*>.*?<Maximum>([\d.]+)</Maximum>',
                  s, re.S)
    if m:
        out.update(fat_min_hp=int(m.group(1)), fat_max_hp=int(m.group(2)), fat_target_hp=int(m.group(3)),
                   fat_hp_warn_m=float(m.group(4)))
    m = re.search(r'scope="\(L:2,[^"]*\)">\s*<Rules>\s*<NodeCapacityRule[^>]*>.*?<Maximum>(\d+)</Maximum>', s, re.S)
    if m:
        out["fdt_max_premises"] = int(m.group(1))
    ratios = re.findall(r"<SplitRatio>(\d+)</SplitRatio>", s)
    if ratios:
        out["fdt_spl_ratio"] = int(ratios[0])
    m = re.search(r"<AverageCableAttenuation>([\d.]+)</AverageCableAttenuation>", s)
    if m:
        out["fiber_db_km"] = float(m.group(1))
    return out


# =============================================================================================
# Temuan (skema tunggal) dan hasil aturan
# =============================================================================================
class Finding(dict):
    """Satu temuan dengan skema tunggal (spesifikasi 13 / bagian G):
    rule_id, case_id, severity, object_type, object_id, cluster, value, threshold, message, recommendation,
    dasar, source, geom (('point', (x, y)) | ('line', [(x, y), ...]) | None), profile_id, rule_version, review."""


def finding(rule_id, severity, message, geom=None, object_type="", object_id="", value=None, threshold=None,
            recommendation="", case_id="", dasar="", source="", scope="", unit="", evidence=""):
    return Finding(rule_id=rule_id, severity=severity, message=message, geom=geom, object_type=object_type,
                   object_id=str(object_id or ""), value=value, threshold=threshold, recommendation=recommendation,
                   case_id=str(case_id or ""), dasar=dasar, source=source, scope=scope, unit=unit,
                   evidence=evidence, source_file="", review="OPEN", note="")


class RuleResult(object):
    """Hasil satu aturan: status agregat + temuan. Status PASS hanya bila aturan benar-benar dijalankan dengan
    data lengkap dan tanpa temuan; data kurang -> UNVERIFIED (bukan PASS)."""

    def __init__(self, rule_id, title, case_id="", spec="", dasar="", sumber=""):
        self.rule_id, self.title, self.case_id, self.spec = rule_id, title, case_id, spec
        self.dasar, self.sumber = dasar, sumber
        self.findings, self.notes, self.stats = [], [], {}
        self.unverified = None       # alasan bila tidak bisa diputuskan

    def add(self, f):
        if not f.get("case_id"):
            f["case_id"] = self.case_id
        if not f.get("dasar"):
            f["dasar"] = self.dasar
        self.findings.append(f)
        return f

    def unverify(self, why):
        self.unverified = why
        return self

    @property
    def status(self):
        if self.findings:
            worst = min((f["severity"] for f in self.findings), key=lambda s: SEV_RANK.get(s, 9))
            if self.unverified and SEV_RANK.get(worst, 9) > SEV_RANK["UNVERIFIED"]:
                return "UNVERIFIED"          # hanya catatan INFO + data kurang -> tetap belum bisa dicek, bukan lolos
            return worst
        return "UNVERIFIED" if self.unverified else "PASS"

    def counts(self):
        c = {}
        for f in self.findings:
            c[f["severity"]] = c.get(f["severity"], 0) + 1
        return c


_EVIDENCE_KEYS = ("NAME", "ELEMENTID", "SUPID", "PREMISES", "SPLITTERS", "MODELNUM", "FIBERS", "LEVEL", "CONNSTATUS", "SERVED",
                  "MAXPPDIST", "COLO", "STATUS", "HEIGHT", "TINGGI")
_TYPE_SOURCE = (("SPAN", ("poles", "cables")), ("HP", ("endpoints",)), ("FAT", ("nodes",)), ("FDT", ("nodes",)), ("KABEL", ("cables",)),
                ("UJUNG_KABEL", ("cables",)), ("POLE", ("poles",)), ("TIANG", ("poles",)), ("CLOSURE", ("closures",)),
                ("COVERAGE", ("polys",)), ("KMZ", ("polys", "poles")))


def _span_ends(sid, idx):
    """'NP-20-EP-11' -> ['NP-20', 'EP-11'] memakai nama tiang yang memang ada di indeks."""
    parts = sid.split("-")
    for k in range(1, len(parts)):
        a, b = "-".join(parts[:k]), "-".join(parts[k:])
        if a in idx and b in idx:
            return [a, b]
    return []


def _evidence_of(o):
    """Ringkasan bukti dari objek sumber: folder KMZ + atribut asli yang relevan (maks. 8 pasang)."""
    parts = []
    fol = [str(x) for x in (o.get("folders") or []) if x]
    if len(fol) > 1:
        fol = fol[1:]                 # folder pertama = nama dokumen KMZ
    if fol:
        parts.append("folder: " + " / ".join(fol)[:120])
    a = o.get("attrs") or {}
    keys = [k for k in a if str(k).upper() in _EVIDENCE_KEYS] or list(a)[:4]
    for k in keys[:8]:
        v = a.get(k)
        if v not in (None, "", "NULL"):
            parts.append("%s=%s" % (k, str(v)[:40]))
    if not parts and o.get("name"):
        parts.append("nama: %s" % o["name"])
    return "; ".join(parts)


def attach_evidence(results, net, extra_sources=None):
    """Isi source_file, evidence dan scope setiap temuan dari objek jaringan yang dirujuknya (audit 6.1:
    temuan memuat objek, sumber data, nilai, ambang, lokasi, bukti). extra_sources: {object_type: file}."""
    idx = {}
    for kind in ("nodes", "endpoints", "cables", "poles", "closures", "polys"):
        for o in getattr(net, kind, []) or []:
            for key in (o.get("name"), o.get("id"), o.get("autodesign_name"), o.get("object_ref")):
                if key:
                    idx.setdefault(str(key), (kind, o))
    extra = dict(extra_sources or {})
    for r in results:
        for f in r.findings:
            hit = idx.get(str(f.get("object_id") or "")) or idx.get(str(f.get("object_ref") or ""))
            kind, o = hit if hit else (None, None)
            if not f.get("source_file"):
                src = f.get("source") or (o or {}).get("src") or ""
                if not src:
                    src = extra.get(f.get("object_type") or "", "")
                if not src:
                    for pre, kinds in _TYPE_SOURCE:
                        if str(f.get("object_type") or "").upper().startswith(pre):
                            src = next((net.sources.get(k) for k in kinds if net.sources.get(k)), "")
                            break
                f["source_file"] = os.path.basename(str(src)) if src else ""
            if not f.get("evidence") and o is None and str(f.get("object_type", "")).upper() == "SPAN":
                ends = [idx.get(x) for x in _span_ends(str(f.get("object_id") or ""), idx)]
                f["evidence"] = "; ".join("%s: %s" % (e[1].get("name"), _evidence_of(e[1])) for e in ends if e)[:300]
            if not f.get("evidence"):
                f["evidence"] = _evidence_of(o) if o else ""
            if not f.get("scope") and o is not None:
                f["scope"] = o.get("scope") or ""
            if not f.get("geom") and o is not None and o.get("x") is not None:
                f["geom"] = ("point", (o["x"], o["y"]))       # lokasi perbaikan untuk temuan tabel (mis. Splice Plan)
            if not f.get("unit") and f.get("threshold") is not None and re.search(r"\d+(?:\.\d+)?\s*m\b", f.get("message", "")):
                f["unit"] = "m"
    return results


def stamp(results, prof, cluster):
    """Lengkapi semua temuan dengan profil, versi aturan, cluster dan nomor temuan stabil."""
    n = 0
    for r in results:
        for f in r.findings:
            n += 1
            f.setdefault("cluster", cluster)
            f["profile_id"] = prof.get("profile_id", "")
            f["rule_version"] = prof.get("rule_version", RULE_VERSION)
            f["finding_id"] = "SER-%s-%05d" % (re.sub(r"[^A-Z0-9]", "", cluster.upper())[:12] or "X", n)
    return results


def review_key(f):
    """Kunci untuk menyinkronkan status review antar run (rule + objek + lokasi dibulatkan ~1 m)."""
    g = f.get("geom")
    loc = ""
    if g and g[0] == "point":
        loc = "%.5f,%.5f" % g[1]
    elif g and g[0] == "line" and g[1]:
        loc = "%.5f,%.5f" % g[1][0]
    return "%s|%s|%s" % (f.get("rule_id", ""), f.get("object_id", ""), loc)


# =============================================================================================
# Geometri (meter lokal; cukup untuk skala cluster < 10 km)
# =============================================================================================
class Proj(object):
    """Proyeksi equirectangular lokal di sekitar lintang acuan: x,y dalam meter."""

    def __init__(self, lat0):
        self.kx = math.cos(math.radians(lat0)) * 111320.0
        self.ky = 110574.0

    def xy(self, p):
        return (p[0] * self.kx, p[1] * self.ky)

    def d(self, a, b):
        return math.hypot((a[0] - b[0]) * self.kx, (a[1] - b[1]) * self.ky)


def haversine(a, b):
    r = 6371008.8
    la1, la2 = math.radians(a[1]), math.radians(b[1])
    dla, dlo = la2 - la1, math.radians(b[0] - a[0])
    h = math.sin(dla / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(dlo / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def seg_proj(P, a, b, pr):
    """(jarak titik P ke ruas a-b, t posisi 0..1 sepanjang ruas) dalam meter."""
    ax, ay = pr.xy(a)
    bx, by = pr.xy(b)
    px, py = pr.xy(P)
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy)), t


def line_len(pts, pr):
    return sum(pr.d(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def point_line(P, pts, pr):
    """(jarak minimum titik ke polyline, chainage meter dari awal garis)."""
    best, ch, acc = float("inf"), 0.0, 0.0
    for i in range(len(pts) - 1):
        L = pr.d(pts[i], pts[i + 1])
        d, t = seg_proj(P, pts[i], pts[i + 1], pr)
        if d < best:
            best, ch = d, acc + t * L
        acc += L
    return best, ch


def pip(x, y, ring):
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-30) + xi:
            inside = not inside
        j = i
    return inside


def in_poly(p, poly):
    outer, holes = poly
    return pip(p[0], p[1], outer) and not any(pip(p[0], p[1], h) for h in holes)


def dist_to_ring(p, ring, pr):
    return min(seg_proj(p, ring[i], ring[i + 1], pr)[0] for i in range(len(ring) - 1)) if len(ring) > 1 else float("inf")


def segs_intersect(a, b, c, d):
    def o(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    d1, d2, d3, d4 = o(c, d, a), o(c, d, b), o(a, b, c), o(a, b, d)
    return (d1 * d2 < 0) and (d3 * d4 < 0)


def seg_intersection(a, b, c, d):
    den = (b[0] - a[0]) * (d[1] - c[1]) - (b[1] - a[1]) * (d[0] - c[0])
    if den == 0:
        return a
    t = ((c[0] - a[0]) * (d[1] - c[1]) - (c[1] - a[1]) * (d[0] - c[0])) / den
    return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))


def deflection_deg(a, c, b, pr):
    """Sudut belok di titik c (0 = lurus, 90 = siku)."""
    ax, ay = pr.xy(a)
    cx, cy = pr.xy(c)
    bx, by = pr.xy(b)
    v1, v2 = (cx - ax, cy - ay), (bx - cx, by - cy)
    n1, n2 = math.hypot(*v1), math.hypot(*v2)
    if not n1 or not n2:
        return 0.0
    cosv = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))
    return math.degrees(math.acos(cosv))


class Grid(object):
    """Indeks titik sederhana (sel ~ cell_m meter) untuk pencarian tetangga terdekat."""

    def __init__(self, items, pr, cell_m=50.0):
        self.pr, self.c = pr, cell_m
        self.cells = {}
        self.items = items              # [(pt, obj)]
        for i, (p, _o) in enumerate(items):
            x, y = pr.xy(p)
            self.cells.setdefault((int(x // cell_m), int(y // cell_m)), []).append(i)

    def near(self, p, r):
        x, y = self.pr.xy(p)
        k = int(r // self.c) + 1
        cx, cy = int(x // self.c), int(y // self.c)
        out = []
        for i in range(cx - k, cx + k + 1):
            for j in range(cy - k, cy + k + 1):
                for idx in self.cells.get((i, j), ()):
                    q, o = self.items[idx]
                    d = self.pr.d(p, q)
                    if d <= r:
                        out.append((d, q, o))
        out.sort(key=lambda t: t[0])
        return out

    def nearest(self, p, rmax=5000.0):
        r = self.c
        while r <= rmax:
            hit = self.near(p, r)
            if hit:
                return hit[0]
            r *= 2
        return None


# =============================================================================================
# Model data jaringan
# =============================================================================================
def _num(v):
    try:
        if v is None or v == "":
            return None
        return float(str(v).replace(",", "."))
    except ValueError:
        return None


def _get(a, *keys):
    """Ambil atribut tanpa peduli huruf besar/kecil; kunci pertama yang ada."""
    if not a:
        return None
    low = {str(k).lower(): v for k, v in a.items()}
    for k in keys:
        v = low.get(k.lower())
        if v not in (None, ""):
            return v
    return None


CORE_RX = re.compile(r"(?<!\d)(12|24|48|96|144|288)\s*(?:D|F|C|CORE|CORES)?(?![\d])", re.IGNORECASE)
DROP_RX = re.compile(r"drop|^\s*(75|100|150|200|250)\s*$|dropcore|\b1\s*D\b|\\1D|/1D", re.IGNORECASE)
FEEDER_RX = re.compile(r"feeder|\b(144|288)\s*F\b|\bF\d{2,3}\b", re.IGNORECASE)
EXIST_RX = re.compile(r"exist|eksist|existing|colo\b|\bcoll?o|\bEP\b|\bEXT\b", re.IGNORECASE)


FEEDER_SCOPE_RX = re.compile(r"^\s*feeder\b", re.I)
DIST_SCOPE_RX = re.compile(r"^\s*(distribution|distribusi)\b", re.I)


def scope_of(folders):
    """Lingkup jaringan dari jalur folder KMZ: FEEDER / DISTRIBUTION / '' (tidak diketahui)."""
    for f in folders or ():
        if FEEDER_SCOPE_RX.search(f or ""):
            return "FEEDER"
        if DIST_SCOPE_RX.search(f or ""):
            return "DISTRIBUTION"
    return ""


def nominal_core(text):
    """Kapasitas nominal kabel dari nama folder/model (mis. 'New Cable 24C', '24D Plan', '48F Plan')."""
    m = CORE_RX.search(text or "")
    return int(m.group(1)) if m else None


class Net(object):
    """Data jaringan satu desain (koordinat lon/lat)."""

    def __init__(self, label=""):
        self.label = label
        self.nodes, self.endpoints, self.cables, self.polys = [], [], [], []
        self.poles, self.closures, self.markers = [], [], []
        self.folders, self.icons, self.files = [], [], []
        self.sources = {}              # jenis -> nama file
        self.has = set()               # jenis data yang benar-benar dibaca
        self.kmz_meta = {}

    def all_points(self):
        for coll in (self.nodes, self.endpoints, self.poles, self.closures):
            for o in coll:
                yield (o["x"], o["y"])
        for c in self.cables:
            for p in c["pts"]:
                yield p

    def proj(self):
        ys = [p[1] for p in self.all_points()]
        return Proj(sum(ys) / len(ys) if ys else 0.0)


def node_kind(a, name, folders):
    s = str(_get(a, "SUPPORT", "TYPE", "KIND", "JENIS") or "").upper()
    lv = _num(_get(a, "LEVEL"))
    eq = str(_get(a, "EQUIPMENT") or "").upper()
    txt = " ".join([name or ""] + list(folders or [])).upper()
    if s in ("POP", "OLT") or lv == 1 or "POP" in eq:
        return "POP"
    if "FDT" in s or lv == 2 or "FDT" in eq or re.search(r"\bFDT\b|ODC", txt):
        return "FDT"
    if "FAT" in s or lv == 3 or "FAT" in eq or re.search(r"\bFAT\b|ODP|-D\d{2}-\d{2}", txt):
        return "FAT"
    return ""


def make_node(a, name, x, y, folders=(), src=""):
    sp = str(_get(a, "SPLITTERS", "SPLITTER") or "")
    m = re.match(r"\s*(\d+)\s*x\s*1\s*x\s*(\d+)", sp, re.I)
    return {"id": str(_get(a, "ELEMENTID", "ELEMENT_ID", "ELEMENT ID", "NODEID", "ID") or name or ""),
            "name": str(_get(a, "FDT-FAT CODE", "FDT_FAT_CODE", "FAT_CODE", "CODE", "KODE", "LABEL") or name or ""),
            "label": str(name or ""), "kind": node_kind(a, name, folders),
            "sup": str(_get(a, "SUPID", "PARENTID", "PARENT", "PARENT_ID") or ""),
            "premises": _num(_get(a, "PREMISES", "HP", "HOMEPASS")),
            "maxpp": _num(_get(a, "MAXPPDIST")), "supdist": _num(_get(a, "SUPDIST")),
            "pridist": _num(_get(a, "PRIDIST")), "conn": _get(a, "CONNSTATUS", "STATUS_CONN"),
            "spl_n": int(m.group(1)) if m else None, "spl_r": int(m.group(2)) if m else None,
            "status": "EXISTING" if EXIST_RX.search(" ".join(list(folders) + [name or "", str(_get(a, "STATUS") or "")]))
            else ("NEW" if re.search(r"\bnew\b", " ".join(folders), re.I) else ""), "x": x, "y": y, "attrs": a or {}, "folders": list(folders), "src": src,
            "scope": scope_of(folders), "packages": {scope_of(folders)} - {""}}


def make_endpoint(a, name, x, y, folders=(), src=""):
    return {"id": str(_get(a, "ELEMENTID", "ELEMENT_ID", "HOMEPASS_ID_PARTNER", "HOMEPASS_I", "ID", "EXTKEY") or name or ""),
            "sup": str(_get(a, "SUPID", "PARENTID", "PARENT", "FAT", "FAT_ID") or ""),
            "conn": _get(a, "CONNSTATUS", "STATUS_CONN"), "served": _get(a, "SERVED", "SERVEDSTATUS", "SERVED_STATUS"),
            "x": x, "y": y, "attrs": a or {}, "name": name or "", "src": src}


ANNOT_RX = re.compile(r"keterangan\s*infra", re.I)


def make_cable(a, name, pts, folders=(), src="", color=None, width=None):
    txt = " ".join(list(folders) + [name or "", str(_get(a, "MODELNUM", "MODEL", "CABLEMODEL", "NAME") or "")])
    # kapasitas nominal (folder/model, mis. 'New Cable 24C') dipisah dari jumlah serat atribut (FIBERS=20 pada kabel
    # 24 core = serat yang dimodelkan/dipakai, bukan kapasitas) - audit 4.2 / UAT S10
    fc = _num(_get(a, "FIBERCOUNT", "FIBERS", "CORE", "CORES"))
    nom = nominal_core(" ".join(list(folders) + [str(_get(a, "MODELNUM", "MODEL", "CABLEMODEL") or ""), name or ""]))
    core = nom or (int(fc) if fc else None)
    kind = "dist"
    if any(ANNOT_RX.search(f or "") for f in folders):
        # garis 'Keterangan Infra' di templat KMZ APD hanya penanda jenis infrastruktur (colo tiang / new infra / galian)
        # yang menumpang di atas kabel sebenarnya: bukan kabel, tidak dinilai sebagai kabel (slack, bentang, BOM, rasio)
        kind = "annot"
    elif DROP_RX.search(txt) or core == 1:
        kind = "drop"
    elif re.search(r"pancingan", txt, re.I):
        kind = "pancingan"
    elif FEEDER_RX.search(txt) or (core and core >= 96) or (_num(_get(a, "LEVEL")) or 9) <= 2:
        kind = "feeder"          # ekspor desain: LEVEL 2 = POP->FDT (feeder), LEVEL 3 = FDT->FAT (distribusi)
    return {"id": str(_get(a, "ELEMENTID", "ID") or name or ""), "name": name or "", "core": core, "kind": kind,
            "status": "EXISTING" if EXIST_RX.search(txt) else ("NEW" if re.search(r"new\s*infra|\bnew\b", txt, re.I) else ""),
            "pts": pts, "color": color, "width": width, "folders": list(folders), "attrs": a or {}, "src": src,
            "desc": str(_get(a, "description", "DESCRIPTION", "KETERANGAN") or ""),
            "scope": scope_of(folders) or {2: "FEEDER", 3: "DISTRIBUTION"}.get(int(_num(_get(a, "LEVEL")) or 0), ""),
            "nominal_core": core, "fibers": int(fc) if fc else None,
            "alloc_fibers": int(_num(_get(a, "ALLOCFIB")) or 0) or None}


# ---------------------------------------------------------------------------------------------
# Pembaca KMZ APD (aplikasi peta KMZ)
# ---------------------------------------------------------------------------------------------
def _t(tag):
    return tag.rsplit("}", 1)[-1]


def _kml_bytes(path):
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if n.lower().endswith(".kml")]
            if not names:
                raise ValueError("KMZ tanpa .kml: %s" % path)
            return z.read("doc.kml" if "doc.kml" in names else names[0]), set(z.namelist())
    with open(path, "rb") as fh:
        return fh.read(), set()


def _coords_txt(t):
    out = []
    for tok in (t or "").split():
        v = tok.split(",")
        if len(v) >= 2:
            try:
                out.append((float(v[0]), float(v[1])))
            except ValueError as _e:
                _log.note(_e)
    return out


def kml_color_to_hex(c):
    """KML aabbggrr -> #rrggbb."""
    c = (c or "").strip().lower()
    if len(c) == 8:
        return "#" + c[6:8] + c[4:6] + c[2:4]
    return None


def classify_folder(folders, gtype, name=""):
    """Jenis objek KMZ APD dari jalur folder (folder terdalam diutamakan)."""
    path = " / ".join(folders).lower()
    nm = (name or "").lower()
    if gtype == "polygon":
        if re.search(r"coverage|voronoi|service ?area", path):
            return "coverage"
        if re.search(r"boundary|batas|funnel", path):
            return "boundary"
        return "polygon"
    if gtype == "line":
        if re.search(r"obstacle|rel\b|kereta|\btol\b|toll", path):
            return "obstacle"
        return "cable" if re.search(r"cable|kabel|\b\d{2,3}\s*[df]\b|dropcore|drop|pancingan|feeder|distribusi|"
                                    r"route|jalur|\bd\d{2}\b|existing", path + " " + nm) else "line"
    for f in reversed([x.lower() for x in folders]):
        if re.search(r"homepass|endpoint|\bhp\b", f):
            return "endpoint"
        if re.search(r"closure|joint|\bjc\b", f):
            return "closure"
        if re.search(r"pole|tiang|\bnp\b|\bep\b", f):
            return "pole"
        if re.search(r"slack", f):
            return "marker"
        if re.search(r"net_?nodes|\bnodes?\b|\bfdt\b|\bfat\b|odp|odc|pop", f):
            return "node"
    if re.search(r"\bfdt\b|\bfat\b|-d\d{2}-\d{2}", nm):
        return "node"
    if re.search(r"slack", nm):
        return "marker"
    return "point"


def read_kmz(path, net=None, role=""):
    """Baca KMZ/KML APD ke objek Net. Mencatat folder, atribut, warna kabel, ikon (cek ikon X)."""
    net = net or Net(os.path.basename(path))
    data, zip_names = _kml_bytes(path)
    root = ET.fromstring(data)  # nosec B314
    styles, smaps = {}, {}
    for el in root.iter():
        tg = _t(el.tag)
        if tg == "Style" and el.get("id"):
            styles["#" + el.get("id")] = el
        elif tg == "StyleMap" and el.get("id"):
            for pair in el:
                if _t(pair.tag) == "Pair":
                    k = next((c.text for c in pair if _t(c.tag) == "key"), "")
                    u = next((c.text for c in pair if _t(c.tag) == "styleUrl"), "")
                    if k == "normal":
                        smaps["#" + el.get("id")] = (u or "").strip()

    def style_of(pm):
        st = None
        for c in pm:
            if _t(c.tag) == "Style":
                st = c
        if st is None:
            u = next(((c.text or "").strip() for c in pm if _t(c.tag) == "styleUrl"), "")
            u = smaps.get(u, u)
            st = styles.get(u)
        col = wid = href = None
        if st is not None:
            for e in st.iter():
                tg = _t(e.tag)
                if tg == "LineStyle":
                    for c in e:
                        if _t(c.tag) == "color":
                            col = kml_color_to_hex(c.text)
                        elif _t(c.tag) == "width":
                            wid = _num(c.text)
                elif tg == "href" and href is None:
                    href = (e.text or "").strip()
        return col, wid, href

    net.files.append(path)
    net.has.add("kmz")

    def walk(el, folders, vis):
        for ch in el:
            tg = _t(ch.tag)
            if tg in ("Folder", "Document"):
                nm = next(((c.text or "").strip() for c in ch if _t(c.tag) == "name"), "")
                v = next(((c.text or "").strip() for c in ch if _t(c.tag) == "visibility"), "1")
                fpath = folders + [nm] if tg == "Folder" else folders
                if tg == "Folder":
                    net.folders.append((tuple(fpath), v != "0"))
                walk(ch, fpath, vis and v != "0")
            elif tg == "Placemark":
                nm = next(((c.text or "").strip() for c in ch if _t(c.tag) == "name"), "")
                attrs = {}
                for e in ch.iter():
                    te = _t(e.tag)
                    if te == "Data" and e.get("name"):
                        attrs[e.get("name")] = next(((c.text or "") for c in e if _t(c.tag) == "value"), "")
                    elif te == "SimpleData" and e.get("name"):
                        attrs[e.get("name")] = e.text or ""
                    elif te == "description" and e.text:
                        attrs.setdefault("description", e.text)
                col, wid, href = style_of(ch)
                if href:
                    net.icons.append((href, nm, tuple(folders), href in zip_names or href.lower().startswith("http")
                                      or os.path.isabs(href)))
                for g in ch.iter():
                    gt = _t(g.tag)
                    if gt == "Point":
                        pts = _coords_txt(" ".join(c.text or "" for c in g.iter() if _t(c.tag) == "coordinates"))
                        if pts:
                            _add_point(net, classify_folder(folders, "point", nm), attrs, nm, pts[0], folders, path)
                    elif gt == "LineString":
                        pts = _coords_txt(" ".join(c.text or "" for c in g.iter() if _t(c.tag) == "coordinates"))
                        if len(pts) >= 2:
                            k = classify_folder(folders, "line", nm)
                            if k == "cable":
                                net.cables.append(make_cable(attrs, nm, pts, folders, path, col, wid))
                            elif k == "obstacle":
                                net.markers.append({"kind": "obstacle", "pts": pts, "name": nm})
                    elif gt == "Polygon":
                        outer, holes = [], []
                        for b in g:
                            bt = _t(b.tag)
                            for r in [r for r in b.iter() if _t(r.tag) == "LinearRing"]:
                                ring = _coords_txt(" ".join(c.text or "" for c in r.iter() if _t(c.tag) == "coordinates"))
                                if len(ring) >= 3:
                                    if ring[0] != ring[-1]:
                                        ring.append(ring[0])
                                    (holes.append(ring) if bt == "innerBoundaryIs" or outer else outer.extend(ring))
                        if len(outer) >= 4:
                            k = classify_folder(folders, "polygon", nm)
                            if k == "coverage":
                                net.polys.append({"id": str(_get(attrs, "ELEMENTID", "NODEID", "ID") or nm),
                                                  "owner": str(_get(attrs, "NODEID", "ELEMENTID", "FAT", "NAME") or nm or ""),
                                                  "poly": (outer, holes), "attrs": attrs, "src": path})
                            elif k == "obstacle":
                                net.markers.append({"kind": "obstacle", "pts": outer, "name": nm})
    walk(root, [], True)
    for k, coll in (("nodes", net.nodes), ("endpoints", net.endpoints), ("cables", net.cables),
                    ("polys", net.polys), ("poles", net.poles), ("closures", net.closures)):
        if coll:
            net.has.add(k)
            net.sources.setdefault(k, os.path.basename(path))
    return net


def _add_point(net, kind, attrs, nm, p, folders, src):
    x, y = p
    if kind == "endpoint":
        net.endpoints.append(make_endpoint(attrs, nm, x, y, folders, src))
    elif kind == "node":
        n = make_node(attrs, nm, x, y, folders, src)
        if n["kind"]:
            net.nodes.append(n)
    elif kind == "pole":
        txt = " ".join(list(folders) + [nm])
        h = re.search(r"(?:^|[^0-9])(6|7|9|11)(?:\s*m\b|\b)", txt, re.I)
        net.poles.append({"id": nm, "name": nm, "x": x, "y": y,
                          "status": "EXISTING" if re.search(r"\bEP\b|exist|eksist|\bTE\b|\bEXT", txt, re.I) else "NEW",
                          "height": float(h.group(1)) if h else None, "src": src, "folders": list(folders),
                          "scope": scope_of(folders)})
    elif kind == "closure":
        ftxt = " ".join(folders)
        cap = re.search(r"closure\s*(\d{2,3})", ftxt + " " + nm, re.I)
        net.closures.append({"id": nm, "name": nm, "x": x, "y": y, "src": src, "attrs": attrs, "folders": list(folders),
                             "scope": scope_of(folders), "cap": int(cap.group(1)) if cap else None,
                             "status": "EXISTING" if re.search(r"exist|eksist|\bEXT\b", ftxt, re.I) else
                             ("NEW" if re.search(r"\bnew\b", ftxt, re.I) else "")})
    elif kind == "marker":
        net.markers.append({"kind": "slack", "x": x, "y": y, "name": nm, "folders": list(folders), "scope": scope_of(folders)})


def read_layer_records(net, kind, records, src):
    """Masukkan rekaman dari pembaca lain (QGIS/shp): records = [(attrs, gtype, geom)] dengan geom lon/lat:
    point (x, y) | line [(x, y)] | polygon (outer, holes)."""
    base = os.path.basename(src)
    for a, gt, g in records:
        if kind == "nodes" and gt == "point":
            n = make_node(a, str(_get(a, "NAME") or ""), g[0], g[1], (), base)
            if n["kind"]:
                net.nodes.append(n)
        elif kind == "endpoints" and gt == "point":
            net.endpoints.append(make_endpoint(a, str(_get(a, "NAME") or ""), g[0], g[1], (), base))
        elif kind == "cables" and gt == "line" and len(g) >= 2:
            net.cables.append(make_cable(a, str(_get(a, "NAME", "MODELNUM") or ""), g, (), base))
        elif kind == "polys" and gt == "polygon":
            net.polys.append({"id": str(_get(a, "ELEMENTID", "NODEID", "ID") or ""),
                              "owner": str(_get(a, "NODEID", "ELEMENTID", "PARENTID", "FAT") or ""),
                              "poly": g, "attrs": a, "src": base})
        elif kind == "closures" and gt == "point":
            net.closures.append({"id": str(_get(a, "ELEMENTID", "NAME") or ""), "name": str(_get(a, "NAME") or ""),
                                 "x": g[0], "y": g[1], "src": base, "attrs": a})
        elif kind == "poles" and gt == "point":
            nm = str(_get(a, "Name", "NAME") or "")
            net.poles.append({"id": nm, "name": nm, "x": g[0], "y": g[1],
                              "status": "EXISTING" if re.search(r"\bEP\b|exist|eksist|\bTE\b|\bEXT", nm, re.I) else "NEW",
                              "height": None, "src": base})
    coll = getattr(net, kind)
    if coll:
        net.has.add(kind)
        net.sources.setdefault(kind, base)
        net.files.append(src)


AUTODESIGN_FILES = [("nodes", r"^net_?nodes\.shp$"), ("endpoints", r"^net_?endpoints?\.shp$"),
                ("cables", r"^net_?cables\.shp$"), ("polys", r"^net_?service_?areas?_?voronoi.*\.shp$"),
                ("closures", r"^net_?splice_?closures?\.shp$")]


def find_autodesign_layers(folder):
    """{jenis: path} file shp keluaran desain otomatis di folder (dan satu tingkat subfolder)."""
    out = {}
    if not folder or not os.path.isdir(folder):
        return out
    for root, dirs, files in os.walk(folder):
        rel = os.path.relpath(root, folder)
        if rel != "." and rel.count(os.sep) >= 1:
            dirs[:] = []
        dirs[:] = [d for d in dirs if not d.upper().startswith(("QC", "HASIL", "INPUT"))]
        for f in sorted(files):
            for k, rx in AUTODESIGN_FILES:
                if k not in out and re.match(rx, f, re.I):
                    out[k] = os.path.join(root, f)
    return out


# =============================================================================================
# Graf jaringan kabel
# =============================================================================================
class CableGraph(object):
    """Graf dari polyline kabel. Simpul = titik sudut (disatukan dalam toleransi snap); ujung kabel yang jatuh di
    tengah ruas kabel lain disambungkan (T-junction). Derajat simpul memisahkan ujung jaringan sebenarnya
    (derajat 1) dari sambungan dua ruas lurus (derajat 2) - spesifikasi X-02/UAT-04."""

    def __init__(self, cables, pr, snap_m=0.5):
        self.pr, self.snap = pr, snap_m
        self.pos, self.adj = [], {}
        self._grid = {}
        self.cable_of_edge = {}
        for ci, c in enumerate(cables):
            ids = [self._node(p) for p in c["pts"]]
            for a, b in zip(ids, ids[1:]):
                if a != b:
                    self._edge(a, b, ci)
        # sambungan T: ujung kabel di tengah ruas kabel lain
        ends = {n for n, nb in self.adj.items() if len(nb) == 1}
        segs = [(a, b) for a in self.adj for b in self.adj[a] if a < b]
        for n in list(ends):
            p = self.pos[n]
            for a, b in segs:
                if n in (a, b):
                    continue
                d, t = seg_proj(p, self.pos[a], self.pos[b], pr)
                if d <= max(snap_m, 0.5) and 0.0 < t < 1.0:
                    self._edge(n, a if t < 0.5 else b, None)
                    break

    def _key(self, p):
        x, y = self.pr.xy(p)
        c = max(self.snap, 0.01) * 2
        return int(x // c), int(y // c)

    def _node(self, p):
        kx, ky = self._key(p)
        for i in range(kx - 1, kx + 2):
            for j in range(ky - 1, ky + 2):
                for n in self._grid.get((i, j), ()):
                    if self.pr.d(self.pos[n], p) <= self.snap:
                        return n
        n = len(self.pos)
        self.pos.append(p)
        self._grid.setdefault((kx, ky), []).append(n)
        self.adj[n] = {}
        return n

    def _edge(self, a, b, ci, L=None):
        L = self.pr.d(self.pos[a], self.pos[b]) if L is None else L
        self.adj[a][b] = min(L, self.adj[a].get(b, L))
        self.adj[b][a] = self.adj[a][b]
        if ci is not None:
            self.cable_of_edge[(min(a, b), max(a, b))] = ci

    def degree(self, n):
        return len(self.adj.get(n, {}))

    def ends(self):
        return [n for n in self.adj if len(self.adj[n]) == 1]

    def nearest_node(self, p, rmax):
        best = (None, float("inf"))
        for n, q in enumerate(self.pos):
            d = self.pr.d(p, q)
            if d < best[1]:
                best = (n, d)
        return best if best[1] <= rmax else (None, best[1])

    def attach(self, p, tol):
        """Simpul graf terdekat ke titik p dalam toleransi (cek juga jarak ke ruas)."""
        n, d = self.nearest_node(p, tol)
        if n is not None:
            return n
        best = (None, float("inf"))
        for a in self.adj:
            for b in self.adj[a]:
                if a < b:
                    dd, t = seg_proj(p, self.pos[a], self.pos[b], self.pr)
                    if dd < best[1]:
                        best = (a if t < 0.5 else b, dd)
        return best[0] if best[1] <= tol else None

    def reachable(self, src):
        seen, st = {src}, [src]
        while st:
            n = st.pop()
            for m in self.adj.get(n, {}):
                if m not in seen:
                    seen.add(m)
                    st.append(m)
        return seen

    def walk_from_end(self, n, stop, max_m=3000.0):
        """Telusuri dari ujung n sepanjang rantai berderajat 2 sampai fungsi stop(titik) benar atau simpang.
        -> (panjang, alasan berhenti 'stop'/'junction'/'end'/'limit', daftar titik)."""
        prev, cur, L, pts = None, n, 0.0, [self.pos[n]]
        while True:
            if stop(self.pos[cur]) and cur != n:
                return L, "stop", pts
            nb = [m for m in self.adj[cur] if m != prev]
            if not nb:
                return L, "end", pts
            if len(self.adj[cur]) > 2 and cur != n:
                return L, "junction", pts
            nxt = nb[0]
            L += self.adj[cur][nxt]
            pts.append(self.pos[nxt])
            prev, cur = cur, nxt
            if L > max_m:
                return L, "limit", pts


# =============================================================================================
# Utilitas kode FDT/FAT
# =============================================================================================
FAT_CODE_RX = re.compile(r"^(?P<fdt>.+?)-D(?P<d>\d{1,3})-(?P<n>\d{1,3})$", re.IGNORECASE)


def parent_from_id(eid):
    """N001.01.05 -> N001.01 (hirarki ELEMENTID desain otomatis)."""
    eid = str(eid or "")
    return eid.rsplit(".", 1)[0] if eid.count(".") >= 2 else ""


def norm_code(s):
    return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())


# =============================================================================================
# ATURAN QC APD
# =============================================================================================
def _pt(o):
    return ("point", (o["x"], o["y"]))


def _fats(net):
    return [n for n in net.nodes if n["kind"] == "FAT"]


def _fdts(net):
    return [n for n in net.nodes if n["kind"] == "FDT"]


def rule_served(net, prof, pr):
    r = RuleResult("SERVED", "Status Served FDT/FAT/HP (hasil desain otomatis)", "-", "P0-01", "INTERNAL",
                   "Handbook Tools desain otomatis: 'pastikan FDT, FAT dan Homepass sudah served semua'")
    eps, fats = net.endpoints, _fats(net)
    if "endpoints" not in net.has:
        return r.unverify("data Homepass/net_endpoints tidak diberikan -> status Served tidak dapat dipastikan")
    has_sup = any(e["sup"] for e in eps)
    has_served = any(e["served"] not in (None, "") for e in eps)
    ids = {}
    for e in eps:
        if e["id"]:
            ids.setdefault(e["id"], []).append(e)
    for k, lst in ids.items():
        if len(lst) > 1:
            for e in lst[1:]:
                r.add(finding("HP_ID_DUPLICATE", "WARNING", "ID homepass %s muncul %d kali (penghitungan bisa ganda)"
                              % (k, len(lst)), _pt(e), "HP", k, len(lst), 1, "hapus duplikat / dummy"))
    fat_ids = {f["id"] for f in fats} | {f["name"] for f in fats}
    n_ns = 0
    if has_served:
        for e in eps:
            v = str(e["served"]).strip().upper()
            if v in ("0", "FALSE", "NO", "N", "NOT SERVED", "NOTSERVED", "UNSERVED", "OUT OF REACH", "OUT_OF_REACH"):
                n_ns += 1
                r.add(finding("SERVED_HP_NOT_SERVED", "ERROR", "HP %s berstatus '%s' di hasil desain otomatis" % (e["id"], e["served"]),
                              _pt(e), "HP", e["id"], recommendation="hubungkan HP ke FAT / perbaiki jalur di desain otomatis"))
    elif has_sup:
        for e in eps:
            if not e["sup"]:
                n_ns += 1
                r.add(finding("SERVED_HP_NOT_SERVED", "ERROR", "HP %s tidak punya node induk (SUPID kosong) -> tidak terlayani"
                              % (e["id"] or e["name"]), _pt(e), "HP", e["id"],
                              recommendation="jalankan ulang Compute/Assign to parent nodes di desain otomatis"))
            elif fat_ids and e["sup"] not in fat_ids:
                r.add(finding("SERVED_HP_PARENT_UNKNOWN", "WARNING", "HP %s menunjuk induk %s yang tidak ada di net_nodes"
                              % (e["id"], e["sup"]), _pt(e), "HP", e["id"]))
    else:
        r.notes.append("Atribut status/induk HP (SERVED/SUPID) tidak ada di data -> status Served per HP UNVERIFIED.")
    for f in fats:
        if "nodes" in net.has and any(n.get("sup") for n in fats) and not f["sup"]:
            r.add(finding("SERVED_FAT_NOT_SERVED", "ERROR", "FAT %s tidak terhubung ke FDT (SUPID kosong)" % (f["name"] or f["id"]),
                          _pt(f), "FAT", f["id"]))
    conn = [str(e["conn"]) for e in eps if e["conn"] not in (None, "")] + [str(n["conn"]) for n in net.nodes if n["conn"] not in (None, "")]
    if conn:
        mode = max(set(conn), key=conn.count)
        odd = [o for o in list(eps) + list(net.nodes) if o.get("conn") not in (None, "") and str(o["conn"]) != mode]
        for o in odd[:200]:
            r.add(finding("SERVED_CONNSTATUS_DIFFERENT", "WARNING", "%s CONNSTATUS=%s berbeda dari mayoritas (%s): cek Results desain otomatis"
                          % (o.get("id"), o["conn"], mode), _pt(o), "HP" if o in eps else o.get("kind"), o.get("id")))
        r.stats["connstatus_mayoritas"] = mode
    r.stats.update(hp=len(eps), fat=len(fats), not_served=n_ns,
                   rasio_served=round(100.0 * (len(eps) - n_ns) / len(eps), 1) if eps else None)
    if not has_sup and not has_served and not conn:
        r.unverify("data tidak memuat SUPID/SERVED/CONNSTATUS - pakai export shp desain otomatis (net_endpoints)")
    return r


def rule_coverage(net, prof, pr):
    r = RuleResult("FAT_COVERAGE", "HP di dalam FAT Coverage (Voronoi)", "8", "P0-02", "INTERNAL",
                   "Handbook KMZ: semua homepass berada di dalam FAT Coverage (kasus 8)")
    if "polys" not in net.has:
        return r.unverify("layer FAT Coverage / net_ServiceAreasVoronoi tidak ada -> tidak bisa dinilai (bukan PASS)")
    if "endpoints" not in net.has:
        return r.unverify("data Homepass tidak ada")
    tol = pv(prof, "coverage_edge_tol_m", 0.5)
    fats = _fats(net)
    owner = []
    for P in net.polys:
        o = P["owner"]
        match = [f for f in fats if o and o in (f["id"], f["name"], f["label"])]
        if not match:
            inside = [f for f in fats if in_poly((f["x"], f["y"]), P["poly"])]
            match = inside if len(inside) == 1 else []
        owner.append(match[0] if match else None)
    n_in = 0
    for e in net.endpoints:
        p = (e["x"], e["y"])
        hit = [i for i, P in enumerate(net.polys) if in_poly(p, P["poly"])
               or dist_to_ring(p, P["poly"][0], pr) <= tol]
        if not hit:
            d = min(dist_to_ring(p, P["poly"][0], pr) for P in net.polys)
            r.add(finding("HP_OUTSIDE_FAT_COVERAGE", "ERROR", "HP %s di luar semua FAT Coverage (%.1f m dari tepi terdekat)"
                          % (e["id"] or e["name"], d), _pt(e), "HP", e["id"], round(d, 1), tol,
                          "perbarui Voronoi / assign HP ke FAT di desain otomatis"))
            continue
        n_in += 1
        inside = [i for i in hit if in_poly(p, net.polys[i]["poly"])]
        if len(inside) > 1:
            r.add(finding("FAT_COVERAGE_OVERLAP", "WARNING", "HP %s berada di %d poligon FAT Coverage (tumpang tindih)"
                          % (e["id"], len(inside)), _pt(e), "HP", e["id"], len(inside), 1))
        if e["sup"] and len(inside) == 1 and owner[inside[0]] is not None:
            own = owner[inside[0]]
            if e["sup"] not in (own["id"], own["name"]):
                r.add(finding("HP_WRONG_FAT_AREA", "WARNING", "HP %s di-assign ke %s tetapi berada di coverage %s"
                              % (e["id"], e["sup"], own["name"] or own["id"]), _pt(e), "HP", e["id"],
                              recommendation="cek grouping (desain otomatis memakai jarak jalur; perlu review)"))
    r.stats.update(hp=len(net.endpoints), tercakup=n_in,
                   persen=round(100.0 * n_in / len(net.endpoints), 1) if net.endpoints else None,
                   poligon=len(net.polys), poligon_tanpa_fat=sum(1 for o in owner if o is None))
    return r


def _dist_cables(net):
    return [c for c in net.cables if c["kind"] in ("dist", "feeder", "pancingan")]


def rule_cable_end(net, prof, pr):
    r = RuleResult("CABLE_END", "FAT di ujung kabel / kabel loop", "1,34", "P0-03", "INTERNAL",
                   "Handbook KMZ: kabel loop & akhir jalur distribusi wajib ada FAT (kasus 1); loop <= 100 m / 2 span (kasus 34)")
    cabs = [c for c in net.cables if c["kind"] in ("dist", "pancingan")]
    if not cabs:
        return r.unverify("kabel distribusi (Net_Cables) tidak ada")
    if "nodes" not in net.has:
        return r.unverify("net_nodes (FAT/FDT) tidak ada")
    tol = pv(prof, "cable_end_tol_m", 3.0)
    g = CableGraph(cabs, pr, pv(prof, "snap_m", 0.5))
    devs = [(n["x"], n["y"], n["kind"], n) for n in net.nodes] + [(c["x"], c["y"], "CLOSURE", c) for c in net.closures]
    fats = [(n["x"], n["y"]) for n in _fats(net)]
    poles = [(p["x"], p["y"]) for p in net.poles]
    loop_m, loop_sp = pv(prof, "loop_max_m", 100), pv(prof, "loop_max_span", 2)
    n_end = 0
    for e in g.ends():
        n_end += 1
        p = g.pos[e]
        near = sorted(((pr.d(p, (x, y)), k, o) for x, y, k, o in devs), key=lambda t: t[0])
        if near and near[0][0] <= tol and near[0][1] in ("FAT", "FDT", "POP"):
            continue
        L, why, pts = g.walk_from_end(e, lambda q: any(pr.d(q, f) <= tol for f in fats))
        n_sp = None
        if len(pts) > 1 and poles:
            # jumlah BENTANG (span) di ekor kabel = tiang berbeda di sepanjang ekor - 1 (tiang berimpit <= 1 m dihitung satu)
            on = []
            for q in poles:
                if point_line(q, pts, pr)[0] <= 3.0 and not any(pr.d(q, o) <= 1.0 for o in on):
                    on.append(q)
            n_sp = max(0, len(on) - 1)
        if near and near[0][0] <= tol and near[0][1] == "CLOSURE":
            r.add(finding("LOOP_TERMINATION_CHECK", "INFO", "Ujung kabel di closure %s (bukan FAT): pastikan memang "
                          "closure/sambungan yang sah" % near[0][2].get("name"), ("point", p), "UJUNG", "", None, None,
                          "abaikan bila closure legal"))
            continue
        msg = "Ujung kabel distribusi tanpa FAT (perangkat terdekat %s %.0f m)" % (
            (near[0][2].get("name") or near[0][1]) if near else "-", near[0][0] if near else -1)
        if why == "stop":
            msg += "; ekor kabel setelah FAT terakhir %.0f m%s" % (L, (" / %d bentang" % n_sp) if n_sp is not None else "")
        # Ekor kabel setelah FAT terakhir yang masih dalam batas loop Handbook (<= 100 m / 2 span) = WARNING untuk
        # ditinjau (bisa cadangan/loop yang sah); di luar batas loop atau tanpa FAT sama sekali = ERROR.
        over = why == "stop" and (L > loop_m or (n_sp is not None and n_sp > loop_sp))
        sev = "WARNING" if why == "stop" and not over else "ERROR"
        if sev == "WARNING":
            msg += " - masih dalam batas loop %d m / %d span" % (loop_m, loop_sp)
        r.add(finding("CABLE_END_WITHOUT_FAT", sev, msg, ("point", p), "UJUNG_KABEL", "",
                      round(L, 1) if why == "stop" else None, loop_m if why == "stop" else tol,
                      "pasang FAT di ujung kabel loop/akhir distribusi, atau catat alasannya bila ekor kabel memang "
                      "disengaja (bukan otomatis menambah tiang)", unit="m"))
        if over:
            r.add(finding("LOOP_LENGTH_OVER_100M" if L > loop_m else "LOOP_SPAN_OVER_2", "WARNING",
                          "Kabel loop %.0f m%s melewati batas %d m / %d span" % (
                              L, (" (%d bentang)" % n_sp) if n_sp is not None else "", loop_m, loop_sp),
                          ("line", pts), "LOOP", "", round(L, 1), loop_m, case_id="34"))
    r.stats.update(ujung_jaringan=n_end, simpul=len(g.pos))
    return r


def _fat_parent(f, fdts_by):
    """Induk FAT dari 3 sumber: SUPID, hirarki ELEMENTID, awalan kode -> (induk, daftar kandidat berbeda)."""
    c = []
    if f["sup"] and f["sup"] in fdts_by:
        c.append(fdts_by[f["sup"]])
    pid = parent_from_id(f["id"])
    if pid and pid in fdts_by:
        c.append(fdts_by[pid])
    m = FAT_CODE_RX.match(f["name"] or "")
    if m:
        k = norm_code(m.group("fdt"))
        if k in fdts_by:
            c.append(fdts_by[k])
    uniq = []
    for x in c:
        if all(x is not y for y in uniq):
            uniq.append(x)
    return (uniq[0] if len(uniq) == 1 else None), uniq


def rule_multi_fdt(net, prof, pr):
    r = RuleResult("MULTI_FDT", "Hirarki FDT-FAT, kapasitas FDT/FAT, premises (semua FDT)", "2,22", "P0-04", "INTERNAL",
                   "config desain otomatis 1x4/1x8 (kapasitas), Handbook KMZ kasus 2 & 22")
    fdts, fats = _fdts(net), _fats(net)
    if "nodes" not in net.has or not fats:
        return r.unverify("net_nodes (FDT/FAT) tidak ada")
    if not fdts:
        r.add(finding("FAT_PARENT_FDT_MISSING", "ERROR", "Tidak ada FDT di data net_nodes (%d FAT)" % len(fats), None, "FDT", ""))
        return r
    by = {}
    for d in fdts:
        for k in (d["id"], d["name"], norm_code(d["name"]), norm_code(d["label"])):
            if k:
                by[k] = d
    per = {id(d): [] for d in fdts}
    for f in fats:
        par, cands = _fat_parent(f, by)
        if par is None and len(cands) > 1:
            r.add(finding("FAT_MULTI_PARENT", "ERROR", "FAT %s diklaim lebih dari satu FDT (%s) - tidak dipilih otomatis"
                          % (f["name"] or f["id"], ", ".join(c["name"] or c["id"] for c in cands)), _pt(f), "FAT", f["id"]))
        elif par is None:
            if len(fdts) == 1 and not f["sup"] and not parent_from_id(f["id"]):
                par = fdts[0]                     # format lama: satu FDT, tanpa relasi -> kompatibel
                r.notes.append("Relasi FAT->FDT tidak ada di data; satu FDT dianggap induk semua FAT (format lama).")
            else:
                r.add(finding("FAT_PARENT_FDT_MISSING", "ERROR", "FAT %s tidak punya induk FDT yang dikenali" % (f["name"] or f["id"]),
                              _pt(f), "FAT", f["id"]))
        if par is not None:
            per[id(par)].append(f)
    mx, mn, cap = pv(prof, "fat_max_hp", 16), pv(prof, "fat_min_hp", 8), pv(prof, "fdt_max_premises", 384)
    ratio, max_spl = pv(prof, "fdt_spl_ratio", 4), pv(prof, "fdt_max_spl", 12)
    eps_by = {}
    for e in net.endpoints:
        if e["sup"]:
            eps_by[e["sup"]] = eps_by.get(e["sup"], 0) + 1
    table = []
    for f in fats:
        n_hp = f["premises"] if f["premises"] is not None else eps_by.get(f["id"]) or eps_by.get(f["name"])
        if n_hp is None:
            continue
        if n_hp > mx:
            r.add(finding("FAT_OVER_CAPACITY", "ERROR", "FAT %s melayani %d HP > %d (2 x splitter 1:8)" % (f["name"] or f["id"], n_hp, mx),
                          _pt(f), "FAT", f["id"], n_hp, mx))
        elif n_hp < mn:
            r.add(finding("FAT_UNDER_MIN", "INFO", "FAT %s hanya %d HP (< %d): cek apakah bisa digabung" % (f["name"] or f["id"], n_hp, mn),
                          _pt(f), "FAT", f["id"], n_hp, mn))
        if f["premises"] is not None and (eps_by.get(f["id"]) or eps_by.get(f["name"])) not in (None, int(f["premises"])):
            got = eps_by.get(f["id"]) or eps_by.get(f["name"])
            r.add(finding("FAT_PREMISES_MISMATCH", "WARNING", "FAT %s PREMISES=%d tetapi %d HP menunjuk FAT ini"
                          % (f["name"] or f["id"], f["premises"], got), _pt(f), "FAT", f["id"], got, f["premises"]))
    for d in fdts:
        lst = per[id(d)]
        prem = sum((f["premises"] or eps_by.get(f["id"]) or 0) for f in lst)
        spl_need = int(math.ceil(sum(2 if (f["premises"] or 0) > 8 else 1 for f in lst) / float(ratio))) if lst else 0
        spl = d["spl_n"] if d["spl_n"] is not None else spl_need
        row = {"fdt": d["name"] or d["id"], "id": d["id"], "status": d["status"] or "?", "fat": len(lst), "hp": prem,
               "premises_attr": d["premises"], "kapasitas": cap, "splitter": spl, "splitter_maks": max_spl}
        table.append(row)
        if prem > cap:
            r.add(finding("FDT_CAPACITY_CHECK", "ERROR", "FDT %s: %d HP > kapasitas %d" % (row["fdt"], prem, cap), _pt(d), "FDT", d["id"], prem, cap))
        if spl and spl > max_spl:
            r.add(finding("FDT_SPLITTER_OVER", "ERROR", "FDT %s: %d splitter 1:%d > maks %d" % (row["fdt"], spl, ratio, max_spl),
                          _pt(d), "FDT", d["id"], spl, max_spl))
        if d["premises"] is not None and lst and int(d["premises"]) != int(prem):
            r.add(finding("FDT_PREMISES_MISMATCH", "ERROR", "Premises pada ikon FDT %s = %d, jumlah HP FAT di bawahnya = %d"
                          % (row["fdt"], d["premises"], prem), _pt(d), "FDT", d["id"], prem, d["premises"],
                          "revisi angka premises FDT (dan BOM)", case_id="22"))
        if not lst:
            r.add(finding("FDT_WITHOUT_FAT", "WARNING", "FDT %s tidak punya FAT" % row["fdt"], _pt(d), "FDT", d["id"]))
    r.stats["per_fdt"] = table
    r.stats["fdt"] = len(fdts)
    r.stats["fat"] = len(fats)
    return r


def rule_fat_hp(net, prof, pr):
    r = RuleResult("FAT_HP_DISTANCE", "Jarak FAT ke homepass (120 m; khusus 150 m)", "15", "P0-02", "INTERNAL",
                   "Handbook KMZ kasus 15; config desain otomatis MAXPPDIST")
    warn, err = pv(prof, "fat_hp_warn_m", 120), pv(prof, "fat_hp_err_m", 150)
    fats = _fats(net)
    if not fats:
        return r.unverify("FAT tidak ada")
    by_sup = {}
    for e in net.endpoints:
        if e["sup"]:
            by_sup.setdefault(e["sup"], []).append(e)
    measured = 0
    for f in fats:
        d, how, far = f["maxpp"], "jalur (MAXPPDIST desain otomatis)", None
        if d is None:
            hs = by_sup.get(f["id"]) or by_sup.get(f["name"]) or []
            if not hs:
                continue
            far = max(hs, key=lambda e: pr.d((f["x"], f["y"]), (e["x"], e["y"])))
            d, how = pr.d((f["x"], f["y"]), (far["x"], far["y"])), "garis lurus (batas bawah; jalur kabel >= nilai ini)"
        measured += 1
        geom = ("line", [(f["x"], f["y"]), (far["x"], far["y"])]) if far else _pt(f)
        if d > err:
            r.add(finding("FAT_HP_OVER_150", "ERROR", "FAT %s: HP terjauh %.0f m > %d m [%s]" % (f["name"] or f["id"], d, err, how),
                          geom, "FAT", f["id"], round(d, 1), err, "pecah FAT / tambah FAT"))
        elif d > warn and how.startswith("jalur"):
            r.add(finding("FAT_HP_120_150", "WARNING", "FAT %s: HP terjauh %.0f m (120-150 m: wajib justifikasi special case) [%s]"
                          % (f["name"] or f["id"], d, how), geom, "FAT", f["id"], round(d, 1), warn,
                          "catat justifikasi geografis (approved exception)"))
        elif d > warn:
            r.add(finding("FAT_HP_120_150", "WARNING", "FAT %s: HP terjauh >= %.0f m garis lurus (> %d m)" % (f["name"] or f["id"], d, warn),
                          geom, "FAT", f["id"], round(d, 1), warn))
    if not measured:
        r.unverify("MAXPPDIST dan relasi HP->FAT tidak ada")
    r.stats["fat_diukur"] = measured
    return r


def rule_fat_order(net, prof, pr):
    r = RuleResult("FAT_CODE", "Kode & urutan FAT/FDT", "11,32", "P1-12", "INTERNAL",
                   "Handbook KMZ kasus 11 (urutan dari keluaran pertama FDT) & 32 (label koding)")
    fats, fdts = _fats(net), _fdts(net)
    coded = [(f, FAT_CODE_RX.match((f["name"] or "").strip())) for f in fats]
    coded = [(f, m) for f, m in coded if m]
    if not coded:
        return r.unverify("FAT belum berkode FDT FAT CODE (jalankan alat 3 / isi kode di net_nodes)")
    groups, seen = {}, {}
    for f, m in coded:
        key = (norm_code(m.group("fdt")), int(m.group("d")))
        groups.setdefault(key, []).append((int(m.group("n")), f))
        c = norm_code(f["name"])
        if c in seen:
            r.add(finding("FAT_CODE_DUPLICATE", "ERROR", "Kode FAT %s dipakai dua kali" % f["name"], _pt(f), "FAT", f["id"]))
        seen[c] = f
    fdt_codes = {norm_code(d["name"]) for d in fdts} | {norm_code(d["label"]) for d in fdts}
    for (fk, dline), lst in sorted(groups.items()):
        nums = sorted(n for n, _ in lst)
        miss = [k for k in range(1, nums[-1] + 1) if k not in nums]
        if miss:
            f0 = sorted(lst, key=lambda t: t[0])[0][1]
            r.add(finding("FAT_LABEL_ORDER_INVALID", "WARNING", "D%02d: nomor FAT melompat, hilang %s" % (
                dline, ", ".join("%02d" % k for k in miss[:10])), _pt(f0), "FAT", f0["name"], len(miss), 0))
        withd = [(n, f) for n, f in lst if f["supdist"] is not None]
        if len(withd) >= 3:
            withd.sort(key=lambda t: t[0])
            inv = [(a, b) for a, b in zip(withd, withd[1:]) if a[1]["supdist"] > b[1]["supdist"] + 20]
            for a, b in inv[:5]:
                r.add(finding("FAT_ORDER_NOT_BY_DISTANCE", "INFO", "%s (%.0f m dari FDT) bernomor lebih kecil dari %s (%.0f m)"
                              % (a[1]["name"], a[1]["supdist"], b[1]["name"], b[1]["supdist"]), _pt(a[1]), "FAT", a[1]["name"],
                              recommendation="urutkan dari keluaran pertama FDT"))
        if fdt_codes and fk not in fdt_codes and not any(fk.startswith(c) or c.startswith(fk) for c in fdt_codes if c):
            f0 = lst[0][1]
            r.add(finding("FDT_CODE_MISMATCH", "WARNING", "Awalan kode FAT %s tidak sama dengan kode FDT mana pun" % f0["name"],
                          _pt(f0), "FAT", f0["name"]))
    lens = {}
    for f, m in coded:
        lens.setdefault(len(f["name"].strip()), []).append(f)
    if len(lens) > 1:
        common = max(lens, key=lambda k: len(lens[k]))
        for L, lst in lens.items():
            if L != common:
                for f in lst[:20]:
                    r.add(finding("FAT_LABEL_LENGTH", "INFO", "Panjang kode %s (%d karakter) beda dari mayoritas (%d)"
                                  % (f["name"], L, common), _pt(f), "FAT", f["name"], case_id="32"))
    r.notes.append("Jumlah karakter baku label (Handbook hlm. 54) tidak tersedia -> hanya konsistensi yang dicek.")
    return r


def rule_fat_on_pole(net, prof, pr):
    r = RuleResult("FAT_ON_POLE", "FAT/FDT presisi di titik tiang (FAT melayang)", "3", "P1-12", "INTERNAL",
                   "Handbook KMZ kasus 3 & Accuracy 'titik FAT/FDT berada di titik pole'")
    if not net.poles:
        return r.unverify("layer Pole tidak ada (sertakan folder Pole di KMZ APD atau POLE.kmz alat 1)")
    tol = pv(prof, "fat_pole_tol_m", 2.0)
    grid = Grid([((p["x"], p["y"]), p) for p in net.poles], pr, 30.0)
    for n in net.nodes:
        if n["kind"] not in ("FAT", "FDT"):
            continue
        hit = grid.nearest((n["x"], n["y"]), 500)
        d = hit[0] if hit else float("inf")
        if d > tol:
            sev = "WARNING" if n["kind"] == "FAT" else "INFO"
            r.add(finding("FAT_NOT_ON_POLE" if n["kind"] == "FAT" else "FDT_NOT_ON_POLE", sev,
                          "%s %s %.1f m dari tiang terdekat (> %.1f m)" % (n["kind"], n["name"] or n["id"], d, tol),
                          _pt(n), n["kind"], n["id"], round(d, 1), tol, "geser ke titik tiang"))
    return r


def rule_pole_idle(net, prof, pr):
    r = RuleResult("POLE_IDLE", "Tiang nganggur (tidak dilewati kabel)", "25", "-", "INTERNAL", "Handbook KMZ kasus 25")
    cabs = _dist_cables(net)
    if not net.poles or not cabs:
        return r.unverify("butuh layer Pole dan kabel")
    tol = pv(prof, "pole_on_line_m", 3.0)
    for p in net.poles:
        d = min(point_line((p["x"], p["y"]), c["pts"], pr)[0] for c in cabs)
        if d > tol:
            r.add(finding("POLE_IDLE", "WARNING" if p["status"] != "EXISTING" else "INFO",
                          "Tiang %s %.1f m dari kabel terdekat (nganggur)" % (p["name"], d), _pt(p), "POLE", p["name"],
                          round(d, 1), tol, "hapus tiang atau lewatkan kabel"))
    return r


def rule_spans(net, prof, pr):
    r = RuleResult("SPAN_APD", "Rentang tiang ke tiang di jalur kabel APD", "9", "-", "INTERNAL",
                   "Handbook KMZ kasus 9 (60 m); Perwal daerah 50 m")
    pscopes = {p.get("scope", "") for p in net.poles}
    cabs = [c for c in net.cables if c["kind"] in ("dist", "feeder")]
    skipped = [c for c in cabs if c.get("scope") and "" not in pscopes and c["scope"] not in pscopes]
    cabs = [c for c in cabs if c not in skipped]
    if skipped:
        r.notes.append("%d kabel lingkup %s tidak dinilai: data tiang lingkup itu tidak ada di KMZ"
                       % (len(skipped), "/".join(sorted({c["scope"] for c in skipped}))))
    if not net.poles or not cabs:
        return r.unverify("butuh layer Pole dan kabel")
    smax, sreg = pv(prof, "span_max_m", 60), pv(prof, "span_reg_m", 50)
    tol = pv(prof, "pole_on_line_m", 3.0)
    done = set()
    grid = Grid([((p["x"], p["y"]), p) for p in net.poles], pr, 50.0)
    for c in cabs:
        L = line_len(c["pts"], pr)
        cand = {}
        for q in c["pts"]:
            for d, _qq, p in grid.near(q, 200.0):
                cand[id(p)] = p
        on = []
        for p in cand.values():
            d, ch = point_line((p["x"], p["y"]), c["pts"], pr)
            if d <= tol:
                on.append((ch, p))
        on.sort(key=lambda t: t[0])
        for (c1, p1), (c2, p2) in zip(on, on[1:]):
            key = tuple(sorted((id(p1), id(p2))))
            if key in done:
                continue
            done.add(key)
            s = c2 - c1
            if p1["status"] == "EXISTING" and p2["status"] == "EXISTING":
                continue
            if s > smax:
                r.add(finding("SPAN_OVER_MAX", "ERROR", "%s - %s: %.1f m > %d m" % (p1["name"], p2["name"], s, smax),
                              ("line", [(p1["x"], p1["y"]), (p2["x"], p2["y"])]), "SPAN", "%s-%s" % (p1["name"], p2["name"]),
                              round(s, 1), smax, "sisipkan tiang"))
            elif s > sreg:
                r.add(finding("SPAN_OVER_REGULATION", "WARNING", "%s - %s: %.1f m > %d m (regulasi daerah)" % (
                    p1["name"], p2["name"], s, sreg), ("line", [(p1["x"], p1["y"]), (p2["x"], p2["y"])]), "SPAN",
                    "%s-%s" % (p1["name"], p2["name"]), round(s, 1), sreg, dasar="REGULASI"))
        if on and L > 0:
            for ch, end in ((on[0][0], c["pts"][0]), (L - on[-1][0], c["pts"][-1])):
                if ch > smax:
                    r.add(finding("SPAN_END_WITHOUT_POLE", "WARNING", "Ujung kabel %.0f m dari tiang terakhir" % ch,
                                  ("point", end), "SPAN", c["name"], round(ch, 1), smax))
    return r


def rule_fat_center(net, prof, pr):
    r = RuleResult("FAT_CENTER", "FAT sentral terhadap HP-nya & grouping", "6,33", "X-09", "RISET",
                   "Handbook KMZ kasus 6 & 33; K-Medoids penempatan ODP (Transient Undip)")
    by = {}
    for e in net.endpoints:
        if e["sup"]:
            by.setdefault(e["sup"], []).append(e)
    if not by:
        return r.unverify("relasi HP->FAT tidak ada (butuh net_endpoints SUPID)")
    ratio = pv(prof, "fat_center_ratio", 1.5)
    fats = _fats(net)
    fat_pts = [(f, (f["x"], f["y"])) for f in fats]
    for f in fats:
        hs = by.get(f["id"]) or by.get(f["name"]) or []
        if len(hs) < 4:
            continue
        P = [(e["x"], e["y"]) for e in hs]
        cur = sum(pr.d((f["x"], f["y"]), q) for q in P) / len(P)
        best = min(sum(pr.d(c, q) for q in P) / len(P) for c in P)
        if cur > ratio * best and cur - best > 15:
            r.add(finding("FAT_NOT_CENTRAL", "INFO", "FAT %s: rata-rata jarak ke HP %.0f m vs %.0f m di titik paling sentral"
                          % (f["name"] or f["id"], cur, best), _pt(f), "FAT", f["id"], round(cur, 1), round(best * ratio, 1),
                          "REVIEW: pertimbangkan tiang yang lebih sentral (arah rumah tidak tersedia -> orientasi UNVERIFIED)"))
        for e in hs:
            own = pr.d((f["x"], f["y"]), (e["x"], e["y"]))
            other = min(((pr.d(q, (e["x"], e["y"])), g) for g, q in fat_pts if g is not f), key=lambda t: t[0], default=None)
            if other and own > 2 * other[0] and own - other[0] > 40:
                r.add(finding("HP_GROUPING_REVIEW", "INFO", "HP %s ke %s %.0f m, padahal %s hanya %.0f m (garis lurus)"
                              % (e["id"], f["name"] or f["id"], own, other[1]["name"] or other[1]["id"], other[0]),
                              ("line", [(e["x"], e["y"]), (f["x"], f["y"])]), "HP", e["id"], round(own, 1), round(other[0], 1),
                              "REVIEW jalur sebenarnya (desain otomatis memakai jarak jalur)", case_id="6"))
    r.notes.append("Arah hadap rumah tidak tersedia di data -> aturan orientasi grouping UNVERIFIED_ORIENTATION.")
    return r


def rule_slack(net, prof, pr):
    r = RuleResult("SLACK", "Slack kabel baru setiap 250 m", "21", "P1-10", "INTERNAL",
                   "Handbook KMZ kasus 21 (aturan internal); hanya kabel baru - kabel existing/colo tidak dinilai")
    marks = [m for m in net.markers if m["kind"] == "slack"]
    labelled = [c for c in _dist_cables(net) if re.search(r"slack", c["name"] + " " + c["desc"], re.I)]
    if not marks and not labelled:
        return r.unverify("UNVERIFIED_SLACK: tidak ada penanda/keterangan slack di data (bukan otomatis pelanggaran)")
    itv = pv(prof, "slack_interval_m", 250)
    # Kabel existing / colo / rencana milik pihak lain bukan bagian pekerjaan ini: slack-nya tidak dinilai.
    new_cabs = [c for c in _dist_cables(net) if c.get("status") != "EXISTING"
                and not re.search(r"colo|collo|eksist|exist", " ".join(c.get("folders") or []) + " " + (c["name"] or ""), re.I)]
    r.stats["kabel_dinilai"] = "%d kabel baru dari %d kabel" % (len(new_cabs), len(_dist_cables(net)))
    for c in new_cabs:
        L = line_len(c["pts"], pr)
        if L <= itv:
            continue
        chs = sorted(point_line((m["x"], m["y"]), c["pts"], pr)[1] for m in marks
                     if point_line((m["x"], m["y"]), c["pts"], pr)[0] <= 10.0)
        cuts = [0.0] + chs + [L]
        gaps = [b - a for a, b in zip(cuts, cuts[1:])]
        if max(gaps) > itv * 1.1:
            need = int(L // itv)
            msg = ("Kabel %s %.0f m belum punya penanda slack sama sekali; butuh minimal %d slack (satu tiap %d m)"
                   % (c["name"] or c["id"], L, need, itv)) if not chs else (
                "Kabel %s %.0f m: ada %d slack, tetapi jarak antar slack terpanjang %.0f m > %d m; tambah slack di ruas itu"
                % (c["name"] or c["id"], L, len(chs), max(gaps), itv))
            r.add(finding("SLACK_GAP_OVER_PROFILE", "WARNING", msg, ("line", c["pts"]), "KABEL", c["name"], round(max(gaps), 1), itv))
    return r


def rule_crossing(net, prof, pr):
    r = RuleResult("CROSSING", "Kabel melintasi rel/tol (perlu review & izin)", "17,19,27", "P1-09", "INTERNAL",
                   "Handbook KMZ kasus 17, 19, 27")
    obs = [m for m in net.markers if m["kind"] == "obstacle"]
    if not obs:
        r.notes.append("Kelas/lebar jalan tidak tersedia -> kebutuhan tiang 9 m di crossing jalan lebar (kasus 27) UNVERIFIED.")
        return r.unverify("UNVERIFIED_REFERENCE: data rel/tol/hambatan tidak diberikan")
    for c in _dist_cables(net):
        for o in obs:
            for a, b in zip(c["pts"], c["pts"][1:]):
                for u, v in zip(o["pts"], o["pts"][1:]):
                    if segs_intersect(a, b, u, v):
                        X = seg_intersection(a, b, u, v)
                        r.add(finding("ROUTE_CROSSING_REVIEW", "WARNING", "Kabel %s memotong %s" % (c["name"] or c["id"], o["name"] or "hambatan"),
                                      ("point", X), "KABEL", c["name"], recommendation="review rute: ikuti crossing existing / izin rel/tol"))
    return r


def rule_fdt_colo_new(fdt_status, feeder, dist, main, prof, pr, status_note=""):
    """Matriks keputusan FDT COLO/NEW (bagian N). feeder/dist: Net atau None (tidak diberikan)."""
    r = RuleResult("FDT_COLO_NEW", "Titik FDT di paket Feeder & Distribusi (COLO/NEW)", "13,14", "P0-05", "INTERNAL",
                   "Review operasional pengguna (USR-FDT) - aturan internal, aktifkan per proyek")
    tol = pv(prof, "fdt_match_tol_m", 5.0)
    fdts = _fdts(main) if main is not None else []
    if feeder is None or dist is None:
        miss = " & ".join(n for n, x in (("Feeder", feeder), ("Distribusi", dist)) if x is None)
        r.add(finding("FDT_DATA_UNVERIFIED", "UNVERIFIED", "UNVERIFIED_DATASET: paket %s tidak diberikan - bukan vonis FDT tidak ada" % miss,
                      None, "FDT", ""))
        if feeder is None and dist is None:
            return r
    ref = fdts or (_fdts(dist) if dist is not None else []) or (_fdts(feeder) if feeder is not None else [])
    if not ref:
        r.add(finding("FDT_DATA_UNVERIFIED", "UNVERIFIED", "Tidak ada titik FDT yang dikenali di data (cek nama layer/atribut FDT)", None, "FDT", ""))
        return r

    def match(fd, net):
        if net is None:
            return None, None
        cands = _fdts(net)
        for c in cands:
            if norm_code(c["name"]) and norm_code(c["name"]) in (norm_code(fd["name"]), norm_code(fd["label"]), norm_code(fd["id"])):
                return c, "id"
        near = sorted(((pr.d((fd["x"], fd["y"]), (c["x"], c["y"])), c) for c in cands), key=lambda t: t[0])
        if near and near[0][0] <= tol:
            return near[0][1], "lokasi"
        return None, (near[0][0] if near else None)

    for fd in ref:
        st = (fdt_status or "AUTO").upper()
        if st == "AUTO":
            st = "COLO" if fd["status"] == "EXISTING" or re.search(r"colo|exist", fd["name"] + fd["label"], re.I) else (
                "NEW" if fd["status"] == "NEW" or re.search(r"new|baru", fd["name"] + fd["label"], re.I) else "UNKNOWN")
        nm = fd["name"] or fd["id"]
        hits = {}
        for lab, net in (("Feeder", feeder), ("Distribusi", dist)):
            c, how = match(fd, net)
            hits[lab] = (c, how)
            if net is None:
                continue
            if c is None:
                r.add(finding("FDT_MISSING_IN_FEEDER" if lab == "Feeder" else "FDT_MISSING_IN_DISTRIBUTION", "ERROR",
                              "FDT %s (%s) tidak ada di paket %s%s" % (nm, st, lab, (" (FDT terdekat %.0f m)" % how) if how else ""),
                              _pt(fd), "FDT", nm, round(how, 1) if how else None, tol,
                              "tambahkan representasi titik FDT pada paket %s & verifikasi ID/koordinat" % lab))
            elif how == "lokasi" and norm_code(c["name"]):
                r.add(finding("FDT_ID_MISMATCH", "WARNING", "FDT %s cocok lokasi tetapi kode di %s = %s" % (nm, lab, c["name"]),
                              _pt(fd), "FDT", nm))
            elif how == "id":
                d = pr.d((fd["x"], fd["y"]), (c["x"], c["y"]))
                if d > tol:
                    r.add(finding("FDT_LOCATION_MISMATCH", "ERROR", "FDT %s di %s bergeser %.1f m (> %.0f m)" % (nm, lab, d, tol),
                                  ("line", [(fd["x"], fd["y"]), (c["x"], c["y"])]), "FDT", nm, round(d, 1), tol, case_id="14"))
        if st == "UNKNOWN":
            r.add(finding("FDT_STATUS_UNKNOWN", "UNVERIFIED", "UNVERIFIED_STATUS: status COLO/NEW FDT %s belum dapat dipastikan "
                          "(isi parameter status FDT)" % nm, _pt(fd), "FDT", nm))
        elif st == "NEW":
            net = dist if dist is not None else main
            cabs = [c for c in (net.cables if net else []) if c["kind"] in ("dist", "pancingan", "feeder")]
            fats = _fats(main) if main is not None else _fats(net)
            if not cabs or not fats:
                r.add(finding("FDT_DATA_UNVERIFIED", "UNVERIFIED", "NEW FDT %s: kabel distribusi/FAT tidak ada -> konektivitas tidak dapat diuji" % nm,
                              _pt(fd), "FDT", nm))
                continue
            g = CableGraph(cabs, pr, pv(prof, "snap_m", 0.5))
            ctol = pv(prof, "cable_end_tol_m", 3.0)
            s = g.attach((fd["x"], fd["y"]), ctol)
            if s is None:
                r.add(finding("FDT_NEW_ROUTE_DISCONNECTED", "ERROR", "FDT %s tidak menempel ke jalur distribusi mana pun" % nm,
                              _pt(fd), "FDT", nm))
                continue
            reach = g.reachable(s)
            my = [f for f in fats if not f["sup"] or f["sup"] in (fd["id"], fd["name"]) or parent_from_id(f["id"]) == fd["id"]]
            for f in my:
                a = g.attach((f["x"], f["y"]), ctol)
                if a is None or a not in reach:
                    r.add(finding("FDT_NEW_ROUTE_DISCONNECTED", "ERROR", "FAT %s tidak tersambung ke FDT %s lewat graf kabel distribusi"
                                  % (f["name"] or f["id"], nm), _pt(f), "FAT", f["name"] or f["id"],
                                  recommendation="sambungkan jalur distribusi FDT -> FAT (bukan sekadar dekat garis lurus)"))
    if status_note:
        r.notes.append(status_note)
    return r


# ---------------------------------------------------------------------------------------------
# BOM / Daily FTTH
# ---------------------------------------------------------------------------------------------
BOM_ITEM_RX = [
    ("HP", re.compile(r"home ?pass|\bhp\b|premises", re.I)),
    ("FAT", re.compile(r"\bfat\b|\bodp\b", re.I)),
    ("FDT", re.compile(r"\bfdt\b|\bodc\b", re.I)),
    ("POLE_9", re.compile(r"(tiang|pole).*(9\s*m|9 ?meter)|9\s*m.*(tiang|pole)", re.I)),
    ("POLE_7", re.compile(r"(tiang|pole).*(7\s*m|7 ?meter)|7\s*m.*(tiang|pole)", re.I)),
    ("POLE_6", re.compile(r"(tiang|pole).*(6\s*m|6 ?meter)|6\s*m.*(tiang|pole)", re.I)),
    ("POLE", re.compile(r"tiang|pole", re.I)),
    ("CLOSURE", re.compile(r"closure|joint ?closure|\bjc\b", re.I)),
    ("CABLE_24", re.compile(r"(kabel|cable).*\b24\b|\b24\s*(c|core|d|f)\b", re.I)),
    ("CABLE_48", re.compile(r"(kabel|cable).*\b48\b|\b48\s*(c|core|d|f)\b", re.I)),
    ("CABLE_96", re.compile(r"(kabel|cable).*\b96\b|\b96\s*(c|core|d|f)\b", re.I)),
    ("CABLE_144", re.compile(r"(kabel|cable).*\b144\b|\b144\s*(c|core|d|f)\b", re.I)),
    ("SPLITTER", re.compile(r"splitter|\b1\s*[x:]\s*(4|8|16)\b", re.I)),
]
QTY_H = re.compile(r"^(qty|quantity|volume|vol|jumlah|jml|total|qty ?plan|qty ?design|kuantitas)\b", re.I)
ITEM_H = re.compile(r"(item|uraian|description|deskripsi|material|designator|nama|jenis|keterangan)", re.I)
UNIT_H = re.compile(r"^(satuan|unit|uom|sat)\b", re.I)


def parse_bom_rows(sheets):
    """sheets = [(nama, baris)] -> (rows[(kategori, item, qty, unit, sheet)], catatan). Kolom dipetakan dari
    judul; baris 'existing/eksisting' dipisahkan (bukan material bangun baru)."""
    rows, notes = [], []
    for sname, data in sheets:
        hdr = None
        for i, r in enumerate(data[:40]):
            cells = [str(c or "").strip() for c in r]
            qi = next((j for j, c in enumerate(cells) if QTY_H.search(c)), None)
            ii = next((j for j, c in enumerate(cells) if ITEM_H.search(c) and not QTY_H.search(c)), None)
            if qi is not None and ii is not None:
                ui = next((j for j, c in enumerate(cells) if UNIT_H.search(c)), None)
                hdr = (i, ii, qi, ui)
                break
        if hdr is None:
            continue
        i0, ii, qi, ui = hdr
        notes.append("sheet '%s': item=kolom %d, qty=kolom %d%s" % (sname, ii + 1, qi + 1, (", satuan=kolom %d" % (ui + 1)) if ui is not None else ""))
        for r in data[i0 + 1:]:
            if len(r) <= max(ii, qi):
                continue
            item = str(r[ii] or "").strip()
            q = _num(r[qi])
            if not item or q is None:
                continue
            unit = str(r[ui] or "").strip().lower() if ui is not None and ui < len(r) else ""
            cat = next((k for k, rx in BOM_ITEM_RX if rx.search(item)), None)
            if cat is None:
                continue
            if re.search(r"exist|eksist", item, re.I):
                cat += "_EXISTING"
            if cat.startswith("CABLE") and (unit in ("km", "kilometer") or re.search(r"\(km\)|\bkm\b", item, re.I)):
                q *= 1000.0
            rows.append((cat, item, q, unit, sname))
    return rows, notes


def read_bom(path):
    """BOM .xlsx/.xlsm/.csv -> (rows, notes) atau ([], [alasan])."""
    if not path or not os.path.isfile(path):
        return [], ["file BOM tidak diberikan"]
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".csv":
            with open(path, encoding="utf-8-sig", errors="ignore") as fh:
                sample = fh.read(4096)
                fh.seek(0)
                dl = ";" if sample.count(";") > sample.count(",") else ","
                sheets = [("csv", list(csv.reader(fh, delimiter=dl)))]
        else:
            try:
                from .buat_input_desain import read_xlsx
            except ImportError:
                from buat_input_desain import read_xlsx
            sheets = read_xlsx(path)
    except Exception as e:
        return [], ["BOM tidak bisa dibaca: %s" % e]
    return parse_bom_rows(sheets)


def rule_bom(net, bom_path, prof, pr):
    r = RuleResult("BOM", "Rekonsiliasi BOM vs desain (HP, FAT, FDT, tiang, closure, kabel)", "22,23,29", "P0-06", "INTERNAL",
                   "Handbook KMZ kasus 22, 23, 29 & Accuracy 'kuantiti homepass KMZ harus sama dengan BOM'")
    rows, notes = read_bom(bom_path)
    r.notes.extend(notes)
    if not bom_path:
        return r.unverify("UNVERIFIED_BOM: file BOM/Daily FTTH tidak diberikan - status keseluruhan tidak boleh PASS")
    if not rows:
        return r.unverify("UNVERIFIED_BOM: kolom item/qty BOM tidak dikenali (%s)" % "; ".join(notes[:2]))
    bom = {}
    for cat, item, q, unit, sh in rows:
        bom.setdefault(cat, [0.0, []])
        bom[cat][0] += q
        bom[cat][1].append(item)
    design = {"HP": len(net.endpoints) if "endpoints" in net.has else None,
              "FAT": len(_fats(net)) if "nodes" in net.has else None,
              "FDT": sum(1 for d in _fdts(net) if d["status"] != "EXISTING") if "nodes" in net.has else None,
              "CLOSURE": len(net.closures) if "closures" in net.has else None}
    newp = [p for p in net.poles if p["status"] != "EXISTING"]
    if net.poles:
        design["POLE"] = len(newp)
        known = sum(1 for p in newp if p["height"])
        # per tinggi hanya bila (hampir) semua tinggi tiang APD diketahui; selain itu bandingkan total saja
        per_ok = bool(newp) and known >= 0.9 * len(newp)
        for h in (6, 7, 9):
            design["POLE_%d" % h] = sum(1 for p in newp if p["height"] == h) if per_ok else None
        if newp and not per_ok:
            r.notes.append("tinggi tiang diketahui pada %d dari %d tiang baru di APD -> BOM dibandingkan pada total tiang"
                           % (known, len(newp)))
    for core in (24, 48, 96, 144):
        cs = [c for c in net.cables if c["core"] == core and c["kind"] not in ("drop", "annot") and c["status"] != "EXISTING"]
        if cs:
            design["CABLE_%d" % core] = sum(line_len(c["pts"], pr) for c in cs)
    table = []
    tol = pv(prof, "bom_cable_tol_pct", 5.0)
    slack = pv(prof, "slack_per_device_m", 10.0)
    if "POLE" not in bom and any(k.startswith("POLE_") and not k.endswith("EXISTING") for k in bom):
        bom["POLE"] = [sum(v[0] for k, v in bom.items() if re.match(r"POLE_\d+$", k)), ["(jumlah tiang per tinggi)"]]
    per_h = [k for k in bom if re.match(r"POLE_\d+$", k) and design.get(k) is not None]
    for cat, val in design.items():
        if val is None or cat not in bom:
            continue
        if cat == "POLE" and per_h:
            continue                      # sudah dibandingkan per tinggi tiang (hindari temuan ganda)
        qb = bom[cat][0]
        if cat.startswith("CABLE"):
            n_dev = len(_fats(net)) + len(net.closures)
            expect = val + slack * n_dev
            diff = qb - expect
            pct = 100.0 * diff / expect if expect else 0
            st = "OK" if abs(pct) <= tol else "WARNING"
            table.append((cat, "m", round(val, 1), round(expect, 1), round(qb, 1), round(diff, 1), round(pct, 1), st))
            if st != "OK":
                r.add(finding("BOM_CABLE_VARIANCE", "WARNING", "%s: BOM %.0f m vs desain %.0f m + slack %.0f m (%.1f%%)"
                              % (cat, qb, val, slack * n_dev, pct), None, "BOM", cat, round(qb, 1), round(expect, 1)))
        else:
            diff = qb - val
            table.append((cat, "unit", val, val, qb, diff, round(100.0 * diff / val, 1) if val else None, "OK" if diff == 0 else "ERROR"))
            if diff:
                rid = {"HP": "BOM_HP_MISMATCH", "FAT": "BOM_FAT_MISMATCH", "FDT": "BOM_FDT_MISMATCH",
                       "CLOSURE": "BOM_CLOSURE_MISMATCH"}.get(cat, "BOM_POLE_MISMATCH")
                r.add(finding(rid, "ERROR", "%s: BOM %g vs desain %g (selisih %+g)" % (cat, qb, val, diff), None, "BOM", cat, qb, val,
                              "samakan BOM dengan APD (existing tidak dihitung material baru)"))
    for k in bom:
        if k.endswith("_EXISTING"):
            r.notes.append("%s di BOM: %g (dipisahkan, tidak dihitung material baru)" % (k, bom[k][0]))
    r.stats["tabel"] = table
    if not table:
        r.unverify("UNVERIFIED_BOM: tidak ada kategori BOM yang bisa dicocokkan dengan data desain")
    return r


def rule_kmz(net, fdt_colo, prof, pr):
    r = RuleResult("KMZ_APD", "KMZ APD: folder, ikon X, warna & keterangan kabel, Existing Cluster", "5,18,20,28,31", "P1-07/12",
                   "INTERNAL", "Handbook KMZ: aturan KMZ, kasus 5, 18, 20, 28, 31; Design Colo FAT (folder Existing)")
    if "kmz" not in net.has:
        return r.unverify("KMZ APD tidak diberikan")
    names = [" / ".join(f).lower() for f, _v in net.folders]
    leaf = [f[-1].lower() for f, _v in net.folders if f]
    need = [("Homepass", r"^homepass|^hp\b"), ("FAT Coverage", r"fat coverage"), ("Net_Nodes", r"net_?nodes|^fdt$|^fat$"),
            ("Net_Cables", r"net_?cables|cable|kabel"), ("Pole", r"^pole|tiang")]
    for lab, rx in need:
        if not any(re.search(rx, x) for x in leaf):
            r.add(finding("KMZ_REQUIRED_LAYER_MISSING", "WARNING", "Folder '%s' tidak ditemukan di KMZ APD" % lab, None, "KMZ", lab, case_id="31"))
    for bad, good in ((r"net_?endpoints?", "Homepass"), (r"net_?service_?areas?_?voronoi|voronoi", "FAT Coverage")):
        for x in leaf:
            if re.search(bad, x):
                r.add(finding("KMZ_FOLDER_INVALID", "WARNING", "Folder '%s' harus di-rename menjadi '%s'" % (x, good), None, "KMZ", x, case_id="31"))
    for f, vis in net.folders:
        lf = f[-1].lower() if f else ""
        if vis and re.search(r"^homepass$|fat coverage|dropcore|\\1d|/1d", lf):
            r.add(finding("KMZ_VISIBILITY", "INFO", "Folder '%s' sebaiknya tidak dicentang saat save APD final" % f[-1], None, "KMZ", f[-1]))
    bad = {}
    for h, n, _f, ok in net.icons:
        if not ok:
            bad.setdefault(h, []).append(n)
    for h, objs in sorted(bad.items()):
        r.add(finding("KMZ_ICON_INVALID", "ERROR", "Ikon '%s' tidak ada di dalam KMZ -> tampil tanda X pada %d objek (mis. %s)"
                      % (h, len(objs), ", ".join(objs[:3])), None, "KMZ", h, len(objs), 0,
                      case_id="18", recommendation="sertakan file ikon di folder files/ KMZ atau pakai URL valid"))
    cols = pv(prof, "cable_colors", {}) or {}
    for c in net.cables:
        if c["kind"] in ("drop", "annot") or c["status"] == "EXISTING" or not c["core"]:
            continue
        want = cols.get(str(c["core"]))
        if want and c["color"] and c["color"].lower() != want.lower():
            r.add(finding("CABLE_COLOR_MISMATCH", "WARNING", "Kabel %s %d core berwarna %s, seharusnya %s" % (
                c["name"] or c["id"], c["core"], c["color"], want), ("line", c["pts"]), "KABEL", c["name"], case_id="28"))
    for c in _dist_cables(net):
        if c["kind"] == "pancingan":
            continue          # pancingan bukan kabel berstatus COLO/NEW INFRA (folder Pancingan sudah menyatakan jenisnya)
        txt = (c["name"] + " " + c["desc"]).strip()
        if not txt:
            r.add(finding("CABLE_LABEL_MISSING", "WARNING", "Kabel tanpa keterangan (nama/deskripsi kosong)", ("line", c["pts"]), "KABEL", "",
                          case_id="20"))
        elif not re.search(r"colo|new ?infra|existing|eksisting|\bnew\b", txt + " " + " ".join(c.get("folders") or []), re.I):
            # status boleh dinyatakan lewat folder templat (mis. 'New Infra Aerial/Udara/New Cable 24C', 'Collo Cable')
            r.add(finding("CABLE_LABEL_NO_STATUS", "INFO", "Keterangan kabel '%s' tanpa status COLO/NEW INFRA" % txt[:40],
                          ("line", c["pts"]), "KABEL", c["name"], case_id="5"))
    if fdt_colo and not any(re.search(r"existing", x) for x in names):
        r.add(finding("KMZ_COLO_MISSING_EXISTING", "WARNING", "Desain COLO tetapi KMZ tidak punya folder 'Existing Cluster'", None, "KMZ", "",
                      case_id="8", recommendation="tambahkan folder Existing Cluster (FDT/FAT/Pole hitam, kabel kuning pucat)"))
    if fdt_colo:
        for d in _fdts(net):
            if d["status"] == "EXISTING" and not re.search(r"colo", d["name"] + d["label"] + str(d["attrs"].get("description", "")), re.I):
                r.add(finding("FDT_COLO_LABEL_MISSING", "WARNING", "FDT existing %s tanpa keterangan COLO pada ikon/label" % (d["name"] or d["id"]),
                              _pt(d), "FDT", d["name"]))
    return r


# =============================================================================================
# Jalankan semua aturan + ringkasan
# =============================================================================================
def run_all(main, prof, feeder=None, dist=None, fdt_status="AUTO", bom_path=None, cluster="", extra_notes=(), paket=None):
    """paket (opsional): dict untuk QC-01..07 = {kmz, codes, splice, master, master_src, ref_pts, ref_src, dl_codes,
    autodesign}. Node dengan kode sama di paket Feeder & Distribution digabung dulu (satu perangkat logis)."""
    pr = main.proj()
    merged = unify_main_nodes(main, prof, pr)
    if merged:
        extra_notes = list(extra_notes) + ["%d perangkat tergambar di dua paket (Feeder & Distribution) dihitung sebagai satu: %s"
                                           % (len(merged), ", ".join(sorted(set(merged))))]
    if feeder is None and any("FEEDER" in (n.get("packages") or {n.get("scope")}) for n in main.nodes):
        feeder = scoped_net(main, "FEEDER")          # KMZ gabungan: paket Feeder = folder Feeder di KMZ yang sama
    if (dist is None or dist is main) and any("DISTRIBUTION" in (n.get("packages") or {n.get("scope")}) for n in main.nodes):
        dist = scoped_net(main, "DISTRIBUTION")      # idem untuk paket Distribution (UAT S04)
    results = []
    for fn in (rule_served, rule_coverage, rule_cable_end, rule_multi_fdt, rule_fat_hp, rule_fat_order,
               rule_fat_on_pole, rule_pole_idle, rule_spans, rule_fat_center, rule_slack, rule_crossing):
        try:
            results.append(fn(main, prof, pr))
        except Exception as e:                       # satu aturan gagal tidak menggagalkan yang lain
            rr = RuleResult(fn.__name__.replace("rule_", "").upper(), fn.__name__, "-", "-")
            rr.unverify("aturan gagal dijalankan: %s" % e)
            results.append(rr)
    colo = (fdt_status or "").upper() == "COLO" or any(d["status"] == "EXISTING" for d in _fdts(main))
    try:
        results.append(rule_fdt_colo_new(fdt_status, feeder, dist, main, prof, pr))
    except Exception as e:
        results.append(RuleResult("FDT_COLO_NEW", "FDT COLO/NEW").unverify("gagal: %s" % e))
    try:
        results.append(rule_bom(main, bom_path, prof, pr))
    except Exception as e:
        results.append(RuleResult("BOM", "BOM").unverify("gagal: %s" % e))
    try:
        results.append(rule_kmz(main, colo, prof, pr))
    except Exception as e:
        results.append(RuleResult("KMZ_APD", "KMZ").unverify("gagal: %s" % e))
    if paket is not None:
        try:
            from . import qc_paket as P
        except ImportError:
            import qc_paket as P
        results.extend(P.run_paket(main, paket.get("kmz"), prof, paket.get("codes"), paket.get("splice"), paket.get("master"),
                                   paket.get("master_src", ""), paket.get("ref_pts"), paket.get("ref_src", ""),
                                   paket.get("dl_codes"), paket.get("autodesign")))
    for n in extra_notes:
        if results:
            results[0].notes.append(n)
    code_of = {}
    for n in main.nodes:                              # objek ekspor (N001.01.05) ditampilkan dengan kode desainnya
        nm = n.get("name") or ""
        if n.get("id") and nm and nm != n["id"]:
            code_of[str(n["id"])] = nm
    for r in results:
        for f in r.findings:
            oid = f.get("object_id")
            if oid in code_of:
                f["object_ref"] = oid
                f["object_id"] = code_of[oid]
    attach_evidence(results, main, extra_sources={"BOM": bom_path or ""})
    stamp(results, prof, cluster or main.label)
    return results


def unify_main_nodes(net, prof, pr):
    """Gabungkan node berkode sama dalam radius fdt_same_m (FDT di folder Feeder dan Distribution)."""
    try:
        from . import qc_paket as P
    except ImportError:
        import qc_paket as P
    return P.unify_nodes(net, pv(prof, "fdt_same_m", 30.0), pr)


def scoped_net(net, scope):
    """Salinan dangkal Net berisi objek satu lingkup (FEEDER / DISTRIBUTION); node gabungan ikut bila paketnya memuat lingkup."""
    s = Net("%s (%s)" % (net.label, scope.title()))
    s.nodes = [n for n in net.nodes if scope in (n.get("packages") or {n.get("scope")})]
    s.cables = [c for c in net.cables if c.get("scope") == scope]
    s.poles = [p for p in net.poles if p.get("scope") == scope]
    s.closures = [c for c in net.closures if c.get("scope") == scope]
    s.has = set(net.has)
    s.sources = dict(net.sources)
    s.files = list(net.files)
    return s


def overall(results):
    """Status keseluruhan: ERROR > WARNING > UNVERIFIED > PASS. Ada UNVERIFIED -> tidak boleh PASS."""
    sts = [r.status for r in results]
    for s in ("ERROR", "WARNING", "UNVERIFIED"):
        if s in sts:
            return s
    return "PASS"


def summary_rows(results):
    return [(r.rule_id, r.title, r.case_id, r.spec, r.status, r.counts(), r.unverified or "", r.notes, r.dasar, r.sumber)
            for r in results]


def findings_of(results):
    return [f for r in results for f in r.findings]


FINDING_COLS = ["finding_id", "rule_id", "rule_version", "profile_id", "case_id", "severity", "object_type", "object_id",
                "scope", "cluster", "value", "threshold", "unit", "message", "evidence", "source_file", "recommendation", "dasar",
                "review", "note", "lon", "lat"]


def write_csv(path, findings):
    cols = FINDING_COLS
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for f in findings:
            g = f.get("geom")
            lon = lat = ""
            if g and g[0] == "point":
                lon, lat = g[1]
            elif g and g[0] == "line" and g[1]:
                lon, lat = g[1][0]
            w.writerow([f.get(c, "") if c not in ("lon", "lat") else (lon if c == "lon" else lat) for c in cols])


def write_json(path, results, prof, meta):
    out = {"meta": meta, "profile_id": prof.get("profile_id"), "rule_version": prof.get("rule_version"),
           "status_keseluruhan": overall(results),
           "aturan": [{"rule_id": r.rule_id, "judul": r.title, "kasus_handbook": r.case_id, "spesifikasi": r.spec,
                       "status": r.status, "jumlah": r.counts(), "alasan_unverified": r.unverified, "catatan": r.notes,
                       "dasar": r.dasar, "sumber": r.sumber,
                       "statistik": {k: v for k, v in r.stats.items() if k != "per_fdt"},
                       "per_fdt": r.stats.get("per_fdt")} for r in results],
           "temuan": [{k: v for k, v in f.items()} for f in findings_of(results)]}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)

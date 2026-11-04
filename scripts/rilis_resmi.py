# -*- coding: utf-8 -*-
"""
Alat rilis & pemeriksa keaslian resmi Joseph Edward Timothy Siahaan untuk plugin QGIS Seranta dan Seuntai.
Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later. Alat ini TIDAK ikut ke zip plugin.

Perintah (Python 3 apa saja, termasuk Python bawaan QGIS / OSGeo4W Shell):
  python rilis_resmi.py cek <plugin.zip | folder plugin> [--online]
      Pemeriksa INDEPENDEN: membawa kunci resmi sendiri (KUNCI_RESMI), membaca paket sebagai data dan TIDAK menjalankan
      kode apa pun dari paket yang diperiksa. Hasil: ASLI / DIMODIFIKASI / PALSU (kunci diganti) / TIDAK RESMI /
      TANPA TANDA TANGAN. --online: juga cocokkan dengan RILIS_RESMI.json di GitHub pembuat.
  python rilis_resmi.py rilis --plugin <folder plugin> --kunci <kunci privat> --keluar <folder> [--registri <json>]
      Membuat <nama>.<versi>.zip bertanda tangan (+ .sha256, izin berkas rw-r--r--) setelah lolos aturan repositori plugin
      QGIS, lalu menambahkan rilis itu ke daftar resmi RILIS_RESMI.json (untuk di-commit ke GitHub).
  python rilis_resmi.py buat-kunci --kunci <kunci privat>
      Sekali saja (sudah dibuat 3.9.0). Mencetak kunci publik & sidik untuk KUNCI_RESMI / SIDIK_RESMI.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile

sys.dont_write_bytecode = True

# Kunci publik resmi pembuat (Ed25519, 8 x 32-bit) dan sidiknya. Sama untuk Seranta dan Seuntai.
KUNCI_RESMI = (1549593263, 1258448507, 3948243780, 1745094294, 3588476158, 1130529245, 3255756279, 3988926214)
SIDIK_RESMI = "92C4-D078-D1FC-1C5B"
PEMBUAT = "Joseph Edward Timothy Siahaan"
REPO = {"seranta": "jetstimo/seranta", "seuntai": "jetstimo/seuntai"}
BERKAS_RILIS = "RILIS.json"
TEKS = (".py", ".md", ".txt", ".json", ".svg", ".js", ".css", ".qml", ".html", ".xml", ".csv")
LEWATI_DIR = {"__pycache__", ".git", "tests", "__MACOSX", ".idea", ".vscode"}
BINER = (".pyc", ".pyo", ".exe", ".dll", ".so", ".pyd", ".dylib", ".bin", ".jar", ".class")
WAJIB_META = ("name", "qgisMinimumVersion", "description", "about", "version", "author", "email", "repository",
              "tracker", "homepage")

# ----------------------------------------------------------------------------- Ed25519 (RFC 8032), salinan mandiri
_P = 2 ** 255 - 19
_Q = 2 ** 252 + 27742317777372353535851937790883648493


def _inv(x):
    return pow(x, _P - 2, _P)


_D = -121665 * _inv(121666) % _P
_I = pow(2, (_P - 1) // 4, _P)


def _add(a, b):
    A = (a[1] - a[0]) * (b[1] - b[0]) % _P
    B = (a[1] + a[0]) * (b[1] + b[0]) % _P
    C = 2 * a[3] * b[3] * _D % _P
    D = 2 * a[2] * b[2] % _P
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F % _P, G * H % _P, F * G % _P, E * H % _P)


def _mul(s, pt):
    q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            q = _add(q, pt)
        pt = _add(pt, pt)
        s >>= 1
    return q


def _eq(a, b):
    return (a[0] * b[2] - b[0] * a[2]) % _P == 0 and (a[1] * b[2] - b[1] * a[2]) % _P == 0


def _x(y, sign):
    if y >= _P:
        return None
    x2 = (y * y - 1) * _inv(_D * y * y + 1) % _P
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P:
        x = x * _I % _P
    if (x * x - x2) % _P:
        return None
    if (x & 1) != sign:
        x = _P - x
    return x


_GY = 4 * _inv(5) % _P
_GX = _x(_GY, 0)
_G = (_GX, _GY, 1, _GX * _GY % _P)


def _enc(pt):
    z = _inv(pt[2])
    x, y = pt[0] * z % _P, pt[1] * z % _P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _dec(b):
    if len(b) != 32:
        return None
    y = int.from_bytes(b, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _x(y, sign)
    return None if x is None else (x, y, 1, x * y % _P)


def _hq(b):
    return int.from_bytes(hashlib.sha512(b).digest(), "little") % _Q


def _expand(secret):
    h = hashlib.sha512(secret).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def public_key(secret):
    return _enc(_mul(_expand(secret)[0], _G))


def sign(secret, msg):
    a, prefix = _expand(secret)
    A = _enc(_mul(a, _G))
    r = _hq(prefix + msg)
    R = _enc(_mul(r, _G))
    s = (r + _hq(R + A + msg) * a) % _Q
    return R + int.to_bytes(s, 32, "little")


def verify(public, msg, sig):
    if len(public) != 32 or len(sig) != 64:
        return False
    A, R = _dec(public), _dec(sig[:32])
    if A is None or R is None:
        return False
    s = int.from_bytes(sig[32:], "little")
    if s >= _Q:
        return False
    return _eq(_mul(s, _G), _add(R, _mul(_hq(sig[:32] + public + msg), A)))


# ----------------------------------------------------------------------------- manifest (identik dengan keaslian.py)
def to_ints(b):
    return [int.from_bytes(b[i:i + 4], "big") for i in range(0, len(b), 4)]


def from_ints(v):
    return b"".join(int(x).to_bytes(4, "big") for x in v)


def sidik(public):
    h = hashlib.sha256(public).hexdigest().upper()[:16]
    return "-".join(h[i:i + 4] for i in range(0, 16, 4))


def file_hash(path):
    with open(path, "rb") as fh:
        b = fh.read()
    if path.lower().endswith(TEKS):
        b = b.replace(b"\r\n", b"\n")
    return to_ints(hashlib.sha256(b).digest())


def list_files(root):
    out = []
    for d, dirs, files in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x not in LEWATI_DIR and not x.startswith("."))
        for f in sorted(files):
            if f == BERKAS_RILIS or f.endswith((".pyc", ".pyo")) or f.startswith("."):
                continue
            out.append(os.path.relpath(os.path.join(d, f), root).replace(os.sep, "/"))
    return out


def canonical(man):
    return json.dumps(man, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def sidik_manifest(man):
    return to_ints(hashlib.sha256(canonical(man)).digest())


def _meta(plugin_dir):
    out = {}
    with open(os.path.join(plugin_dir, "metadata.txt"), encoding="utf-8") as fh:
        for ln in fh:
            if "=" in ln and not ln.startswith(("#", "[")):
                k, v = ln.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def _embedded_key(plugin_dir):
    """Kunci di keaslian.py paket, dibaca sebagai TEKS (tidak dijalankan)."""
    p = os.path.join(plugin_dir, "keaslian.py")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8", errors="replace") as fh:
        m = re.search(r"^KUNCI_PUBLIK = \(([0-9, ]*)\)", fh.read(), re.M)
    return tuple(int(x) for x in m.group(1).split(",") if x.strip()) if m else None


# ----------------------------------------------------------------------------- cek (independen)
def _safe_extract(zp, dst):
    with zipfile.ZipFile(zp) as z:
        for n in z.namelist():
            t = os.path.realpath(os.path.join(dst, n))
            if not t.startswith(os.path.realpath(dst) + os.sep):
                raise SystemExit("Zip berisi jalur berbahaya: %s" % n)
        z.extractall(dst)
    tops = [d for d in os.listdir(dst) if os.path.isdir(os.path.join(dst, d)) and not d.startswith("__")]
    if len(tops) != 1:
        raise SystemExit("Zip plugin harus berisi tepat satu folder plugin (ditemukan: %s)" % tops)
    return os.path.join(dst, tops[0])


def periksa(plugin_dir):
    """-> (kode, teks, info). Tidak menjalankan kode dari plugin_dir."""
    name = os.path.basename(os.path.normpath(plugin_dir))
    p = os.path.join(plugin_dir, BERKAS_RILIS)
    if not os.path.exists(p):
        return "TANPA_TANDA_TANGAN", "TANPA TANDA TANGAN - bukan rilis resmi (tidak ada %s)" % BERKAS_RILIS, {}
    with open(p, encoding="utf-8") as fh:
        data = json.load(fh)
    man, sig = data.get("manifest") or {}, from_ints(data.get("tanda_tangan") or [])
    ver = man.get("versi", "?")
    info = {"plugin": name, "versi": ver, "manifest": man}
    emb = _embedded_key(plugin_dir)
    if emb is not None and tuple(emb) != KUNCI_RESMI:
        return "PALSU", ("PALSU - kunci rilis di paket ini DIGANTI (sidik %s, kunci resmi %s): bukan rilis resmi %s, "
                         "apa pun nama pembuat yang tertulis" % (sidik(from_ints(emb)), SIDIK_RESMI, PEMBUAT)), info
    if not verify(from_ints(KUNCI_RESMI), canonical(man), sig):
        return "TIDAK_RESMI", "TIDAK RESMI - tanda tangan tidak cocok dengan kunci resmi %s (%s)" % (
            PEMBUAT, SIDIK_RESMI), info
    exp = man.get("berkas") or {}
    now = set(list_files(plugin_dir))
    bad = sorted(f for f, h in exp.items() if f not in now or file_hash(os.path.join(plugin_dir, f)) != list(h))
    extra = sorted(now - set(exp))
    if bad or extra:
        det = bad + ["+" + x for x in extra]
        return "DIMODIFIKASI", "DIMODIFIKASI dari rilis resmi %s %s (%s)" % (
            name, ver, ", ".join(det[:6]) + (" ..." if len(det) > 6 else "")), info
    return "ASLI", "ASLI - rilis resmi %s %s ditandatangani %s (kunci %s)" % (name, ver, PEMBUAT, SIDIK_RESMI), info


def cek_online(info):
    from urllib.request import urlopen     # nosec B310 - alat pembuat, URL tetap ke GitHub pembuat
    repo = REPO.get(info.get("plugin", ""), "")
    if not repo:
        return "tidak ada daftar online untuk %s" % info.get("plugin")
    url = "https://raw.githubusercontent.com/%s/main/RILIS_RESMI.json" % repo
    try:
        reg = json.loads(urlopen(url, timeout=15).read().decode("utf-8"))  # nosec B310
    except Exception as e:
        return "daftar online tidak terjangkau (%s)" % str(e)[:80]
    ent = (reg.get("rilis") or {}).get(info.get("versi")) or {}
    if reg.get("kunci_sidik") == SIDIK_RESMI and list(ent.get("manifest") or []) == sidik_manifest(info["manifest"]):
        return "TERDAFTAR di daftar rilis resmi github.com/%s" % repo
    return "TIDAK TERDAFTAR di daftar rilis resmi github.com/%s" % repo


def cek(a):
    p = os.path.abspath(a.target)
    tmp = None
    try:
        if p.lower().endswith(".zip"):
            tmp = tempfile.mkdtemp(prefix="cek_rilis_")
            p = _safe_extract(p, tmp)
        code, text, info = periksa(p)
        print(text)
        if a.online and code == "ASLI":
            print("Online     : " + cek_online(info))
        return code
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


# ----------------------------------------------------------------------------- rilis
def _read_key(path):
    with open(path, encoding="ascii") as fh:
        m = re.search(r"\b([0-9a-fA-F]{64})\b", fh.read())
    if not m:
        raise SystemExit("Berkas kunci privat tidak valid: %s" % path)
    return bytes.fromhex(m.group(1))


def cek_kepatuhan(plugin_dir, meta, version_py):
    err = []
    for f in ("LICENSE", "README.md", "metadata.txt", "__init__.py", "keaslian.py", "NOTICE.md"):
        if not os.path.exists(os.path.join(plugin_dir, f)):
            err.append("berkas wajib tidak ada: %s" % f)
    for k in WAJIB_META:
        if not meta.get(k):
            err.append("metadata.txt: '%s' kosong" % k)
    if version_py and meta.get("version") != version_py:
        err.append("versi metadata.txt (%s) beda dengan __version__ (%s)" % (meta.get("version"), version_py))
    if "plugin" in os.path.basename(plugin_dir.rstrip("\\/")).lower():
        err.append("nama folder plugin tidak boleh memuat kata 'plugin'")
    with open(os.path.join(plugin_dir, "LICENSE"), encoding="utf-8") as fh:
        lic = fh.read()
    if "GNU GENERAL PUBLIC LICENSE" not in lic:
        err.append("LICENSE bukan teks GNU GPL")
    for f in ("metadata.txt", "NOTICE.md", "README.md"):
        fp = os.path.join(plugin_dir, f)
        if os.path.exists(fp) and SIDIK_RESMI not in open(fp, encoding="utf-8").read():
            err.append("%s tidak memuat sidik kunci resmi %s (cek silang)" % (f, SIDIK_RESMI))
    emb = _embedded_key(plugin_dir)
    if emb != KUNCI_RESMI:
        err.append("KUNCI_PUBLIK di keaslian.py bukan kunci resmi")
    for d, dirs, files in os.walk(plugin_dir):
        for x in dirs:
            if x.startswith(".") or x in ("__pycache__", "__MACOSX"):
                err.append("folder terlarang: %s" % os.path.relpath(os.path.join(d, x), plugin_dir))
        for f in files:
            if f.lower().endswith(BINER) or f.startswith("."):
                err.append("berkas biner/tersembunyi: %s" % os.path.relpath(os.path.join(d, f), plugin_dir))
    return err


def _version_py(src):
    for f in sorted(os.listdir(src)):
        if f.endswith(".py"):
            with open(os.path.join(src, f), encoding="utf-8", errors="replace") as fh:
                m = re.search(r'^__version__ = "([^"]+)"', fh.read(), re.M)
            if m:
                return m.group(1)
    return ""


def rilis(a):
    src = os.path.abspath(a.plugin)
    name = os.path.basename(os.path.normpath(src))
    secret = _read_key(a.kunci)
    if public_key(secret) != from_ints(KUNCI_RESMI):
        raise SystemExit("Kunci privat ini bukan pasangan KUNCI_RESMI.")
    meta = _meta(src)
    ver = meta.get("version", "")
    tmp = tempfile.mkdtemp(prefix="rilis_")
    try:
        dst = os.path.join(tmp, name)
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", "tests", ".*",
                                                                BERKAS_RILIS, "integrity.json"))
        err = cek_kepatuhan(dst, meta, _version_py(dst))
        if err:
            raise SystemExit("Belum memenuhi aturan rilis:\n  - " + "\n  - ".join(err))
        when = datetime.datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
        produk = meta.get("name", name)
        man = {"produk": produk, "versi": ver, "pembuat": PEMBUAT, "dibuat": when,
               "berkas": {f: file_hash(os.path.join(dst, f)) for f in list_files(dst)}}
        sig = sign(secret, canonical(man))
        with open(os.path.join(dst, BERKAS_RILIS), "w", encoding="utf-8") as fh:
            json.dump({"manifest": man, "tanda_tangan": to_ints(sig), "kunci_publik": list(KUNCI_RESMI),
                       "algoritma": "Ed25519 (RFC 8032) atas SHA-256 tiap berkas; bilangan 32-bit big-endian"},
                      fh, ensure_ascii=False, indent=None, sort_keys=True, separators=(",", ":"))
        code, text, _i = periksa(dst)
        if code != "ASLI":
            raise SystemExit("Verifikasi setelah tanda tangan gagal: %s" % text)
        os.makedirs(a.keluar, exist_ok=True)
        zp = os.path.join(a.keluar, "%s.%s.zip" % (name, ver))
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
            for d, dirs, files in os.walk(dst):
                dirs.sort()
                for f in sorted(files):
                    full = os.path.join(d, f)
                    zi = zipfile.ZipInfo(os.path.relpath(full, tmp).replace(os.sep, "/"),
                                         datetime.datetime.fromtimestamp(os.path.getmtime(full)).timetuple()[:6])
                    zi.compress_type = zipfile.ZIP_DEFLATED
                    zi.external_attr = 0o100644 << 16
                    with open(full, "rb") as fh:
                        z.writestr(zi, fh.read())
        size = os.path.getsize(zp)
        if size > 25 * 1024 * 1024:
            raise SystemExit("Zip %.1f MB > 25 MB" % (size / 1048576.0))
        with open(zp, "rb") as fh:
            zh = hashlib.sha256(fh.read()).digest()
        with open(zp + ".sha256", "w", encoding="ascii") as fh:
            fh.write("%s  %s\n" % (zh.hex(), os.path.basename(zp)))
        if a.tulis_sumber:
            shutil.copy2(os.path.join(dst, BERKAS_RILIS), os.path.join(src, BERKAS_RILIS))
        if a.registri:
            reg = {}
            if os.path.exists(a.registri):
                with open(a.registri, encoding="utf-8") as fh:
                    reg = json.load(fh)
            reg.update({"produk": produk, "pembuat": PEMBUAT, "kunci_sidik": SIDIK_RESMI,
                        "keterangan": "Daftar rilis resmi. Sidik manifest = SHA-256 RILIS.json/manifest kanonik; "
                                      "zip = SHA-256 berkas zip. Bilangan 32-bit big-endian."})
            reg.setdefault("rilis", {})[ver] = {"manifest": sidik_manifest(man), "zip": to_ints(zh), "tanggal": when}
            with open(a.registri, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(reg, fh, ensure_ascii=False, indent=1, sort_keys=True)
                fh.write("\n")
        print("Rilis      : %s (%.2f MB)\nSHA-256    : %s\nKeaslian   : %s" % (zp, size / 1048576.0, zh.hex(), text))
        return zp
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def daftar(a):
    """Tambahkan rilis yang SUDAH ada (zip resmi lama) ke RILIS_RESMI.json."""
    tmp = tempfile.mkdtemp(prefix="daftar_")
    try:
        p = _safe_extract(a.zip, tmp)
        code, text, info = periksa(p)
        if code != "ASLI":
            raise SystemExit("Bukan rilis resmi: %s" % text)
        with open(a.zip, "rb") as fh:
            zh = hashlib.sha256(fh.read()).digest()
        reg = {}
        if os.path.exists(a.registri):
            with open(a.registri, encoding="utf-8") as fh:
                reg = json.load(fh)
        reg.update({"produk": info["manifest"].get("produk"), "pembuat": PEMBUAT, "kunci_sidik": SIDIK_RESMI,
                    "keterangan": "Daftar rilis resmi. Sidik manifest = SHA-256 RILIS.json/manifest kanonik; "
                                  "zip = SHA-256 berkas zip. Bilangan 32-bit big-endian."})
        reg.setdefault("rilis", {})[info["versi"]] = {"manifest": sidik_manifest(info["manifest"]), "zip": to_ints(zh),
                                                      "tanggal": info["manifest"].get("dibuat", "")}
        with open(a.registri, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(reg, fh, ensure_ascii=False, indent=1, sort_keys=True)
            fh.write("\n")
        print("Didaftarkan: %s %s" % (info["plugin"], info["versi"]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def buat_kunci(a):
    if os.path.exists(a.kunci) and not a.paksa:
        raise SystemExit("Kunci privat sudah ada: %s" % a.kunci)
    secret = os.urandom(32)
    pub = public_key(secret)
    with open(a.kunci, "w", encoding="ascii") as fh:
        fh.write("# KUNCI PRIVAT RILIS - RAHASIA. Milik %s. Jangan dibagikan/di-commit; simpan cadangan offline.\n"
                 "%s\n" % (PEMBUAT, secret.hex()))
    print("KUNCI_RESMI = (%s)\nSIDIK_RESMI = \"%s\"" % (", ".join(str(x) for x in to_ints(pub)), sidik(pub)))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Alat rilis & pemeriksa keaslian resmi (Seranta / Seuntai)")
    sp = ap.add_subparsers(dest="cmd", required=True)
    c = sp.add_parser("cek")
    c.add_argument("target")
    c.add_argument("--online", action="store_true")
    r = sp.add_parser("rilis")
    r.add_argument("--plugin", required=True)
    r.add_argument("--kunci", required=True)
    r.add_argument("--keluar", required=True)
    r.add_argument("--registri", default="")
    r.add_argument("--tulis-sumber", action="store_true")
    d = sp.add_parser("daftar")
    d.add_argument("zip")
    d.add_argument("--registri", required=True)
    b = sp.add_parser("buat-kunci")
    b.add_argument("--kunci", required=True)
    b.add_argument("--paksa", action="store_true")
    a = ap.parse_args(argv)
    res = {"cek": cek, "rilis": rilis, "daftar": daftar, "buat-kunci": buat_kunci}[a.cmd](a)
    if a.cmd == "cek" and res != "ASLI":
        sys.exit(1)


if __name__ == "__main__":
    main()

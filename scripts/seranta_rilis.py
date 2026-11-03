# -*- coding: utf-8 -*-
"""
Alat rilis Seranta (milik pembuat; JANGAN ikut dimasukkan ke zip plugin).
Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later (lihat LICENSE).

Perintah (Python 3 apa saja, termasuk Python bawaan QGIS / OSGeo4W Shell):
  python seranta_rilis.py buat-kunci  --plugin <folder seranta> --kunci <berkas kunci privat>
      Sekali saja. Membuat pasangan kunci Ed25519: kunci privat disimpan di <berkas kunci privat> (RAHASIA - simpan
      cadangan offline, jangan dibagikan, jangan di-commit), kunci publik ditulis ke <folder seranta>/keaslian.py.
  python seranta_rilis.py rilis --plugin <folder seranta> --kunci <berkas kunci privat> --keluar <folder>
      Membuat seranta.<versi>.zip bertanda tangan + .sha256, setelah lolos cek kepatuhan repositori plugin QGIS.
  python seranta_rilis.py cek <seranta.zip | folder seranta>
      Memeriksa keaslian paket (ASLI / DIMODIFIKASI / TIDAK RESMI / pengembangan).
"""
import argparse
import datetime
import hashlib
import importlib.util
import os
import re
import shutil
import sys
import tempfile
import zipfile

sys.dont_write_bytecode = True        # jangan membuat __pycache__ di paket rilis saat memuat keaslian.py

BINER = (".pyc", ".pyo", ".exe", ".dll", ".so", ".pyd", ".dylib", ".bin", ".jar", ".class")
WAJIB_META = ("name", "qgisMinimumVersion", "description", "about", "version", "author", "email", "repository",
              "tracker", "homepage")


def _load_keaslian(plugin_dir):
    spec = importlib.util.spec_from_file_location("seranta_keaslian_rilis", os.path.join(plugin_dir, "keaslian.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _meta(plugin_dir):
    out = {}
    with open(os.path.join(plugin_dir, "metadata.txt"), encoding="utf-8") as fh:
        for ln in fh:
            if "=" in ln and not ln.startswith(("#", "[")):
                k, v = ln.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def _read_key(path):
    with open(path, encoding="ascii") as fh:
        txt = fh.read()
    m = re.search(r"\b([0-9a-fA-F]{64})\b", txt)
    if not m:
        raise SystemExit("Berkas kunci privat tidak valid: %s" % path)
    return bytes.fromhex(m.group(1))


def buat_kunci(a):
    if os.path.exists(a.kunci) and not a.paksa:
        raise SystemExit("Kunci privat sudah ada: %s (pakai --paksa hanya bila memang ingin mengganti kunci; rilis lama "
                         "akan terbaca TIDAK RESMI oleh versi baru)" % a.kunci)
    K = _load_keaslian(a.plugin)
    secret = os.urandom(32)
    pubb = K.public_key(secret)
    pub = pubb.hex()
    os.makedirs(os.path.dirname(os.path.abspath(a.kunci)), exist_ok=True)
    with open(a.kunci, "w", encoding="ascii") as fh:
        fh.write("# KUNCI PRIVAT RILIS SERANTA - RAHASIA. Milik Joseph Edward Timothy Siahaan.\n"
                 "# Jangan dibagikan, jangan di-commit, jangan dimasukkan ke zip. Simpan cadangan offline (flashdisk).\n"
                 "# Siapa pun yang memegang berkas ini dapat menandatangani rilis atas nama Anda.\n"
                 "%s\n# kunci publik: %s\n" % (secret.hex(), pub))
    p = os.path.join(a.plugin, "keaslian.py")
    with open(p, encoding="utf-8") as fh:
        src = fh.read()
    src, n = re.subn(r'^KUNCI_PUBLIK = \([0-9, ]*\)', 'KUNCI_PUBLIK = (%s)' % ", ".join(str(x) for x in K.to_ints(pubb)),
                     src, count=1, flags=re.M)
    if n != 1:
        raise SystemExit("KUNCI_PUBLIK tidak ditemukan di keaslian.py")
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(src)
    print("Kunci privat : %s (RAHASIA)\nKunci publik : %s (ditulis ke keaslian.py)" % (a.kunci, pub))


def cek_kepatuhan(plugin_dir, meta, version_py):
    """Aturan plugins.qgis.org/docs/publish: lisensi GPL-kompatibel + LICENSE, README, metadata wajib, tanpa biner/
    berkas tersembunyi/__pycache__, nama folder tanpa kata 'plugin', ukuran < 25 MB."""
    err = []
    for f in ("LICENSE", "README.md", "metadata.txt", "__init__.py", "keaslian.py"):
        if not os.path.exists(os.path.join(plugin_dir, f)):
            err.append("berkas wajib tidak ada: %s" % f)
    for k in WAJIB_META:
        if not meta.get(k):
            err.append("metadata.txt: '%s' kosong" % k)
    if meta.get("version") != version_py:
        err.append("versi metadata.txt (%s) beda dengan __version__ (%s)" % (meta.get("version"), version_py))
    if "plugin" in os.path.basename(plugin_dir.rstrip("\\/")).lower():
        err.append("nama folder plugin tidak boleh memuat kata 'plugin'")
    with open(os.path.join(plugin_dir, "LICENSE"), encoding="utf-8") as fh:
        lic = fh.read()
    if "GNU GENERAL PUBLIC LICENSE" not in lic:
        err.append("LICENSE bukan teks GNU GPL")
    for d, dirs, files in os.walk(plugin_dir):
        for x in dirs:
            if x.startswith(".") or x in ("__pycache__", "__MACOSX"):
                err.append("folder terlarang: %s" % os.path.relpath(os.path.join(d, x), plugin_dir))
        for f in files:
            if f.lower().endswith(BINER) or f.startswith("."):
                err.append("berkas biner/tersembunyi: %s" % os.path.relpath(os.path.join(d, f), plugin_dir))
    return err


def rilis(a):
    src = os.path.abspath(a.plugin)
    K0 = _load_keaslian(src)
    secret = _read_key(a.kunci)
    if not K0.KUNCI_PUBLIK or K0.public_key(secret) != K0.from_ints(K0.KUNCI_PUBLIK):
        raise SystemExit("Kunci privat tidak cocok dengan KUNCI_PUBLIK di keaslian.py (jalankan buat-kunci dulu).")
    meta = _meta(src)
    m = re.search(r'^__version__ = "([^"]+)"', open(os.path.join(src, "buat_input_desain.py"), encoding="utf-8").read(), re.M)
    ver = m.group(1) if m else ""
    tmp = tempfile.mkdtemp(prefix="seranta_rilis_")
    dst = os.path.join(tmp, "seranta")
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", "tests", ".*", "RILIS.json",
                                                            "integrity.json"))
    err = cek_kepatuhan(dst, meta, ver)
    if err:
        shutil.rmtree(tmp, ignore_errors=True)
        raise SystemExit("Belum memenuhi aturan repositori plugin QGIS:\n  - " + "\n  - ".join(err))
    when = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z") or datetime.datetime.now().isoformat()
    K = _load_keaslian(dst)
    K.write_signed(dst, ver, secret, when)
    K._CACHE.clear()
    code, v2, det = K.check(dst)
    if code != "ASLI":
        raise SystemExit("Verifikasi setelah tanda tangan gagal: %s %s" % (code, det))
    os.makedirs(a.keluar, exist_ok=True)
    zp = os.path.join(a.keluar, "seranta.%s.zip" % ver)
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for d, dirs, files in os.walk(dst):
            dirs[:] = sorted(x for x in dirs if x != "__pycache__")
            for f in sorted(files):
                if f.endswith((".pyc", ".pyo")):
                    continue
                full = os.path.join(d, f)
                zi = zipfile.ZipInfo(os.path.relpath(full, tmp).replace(os.sep, "/"),
                                     datetime.datetime.fromtimestamp(os.path.getmtime(full)).timetuple()[:6])
                zi.compress_type = zipfile.ZIP_DEFLATED
                zi.external_attr = (0o100644 << 16)     # rw-r--r--: tanpa izin eksekusi (peringatan pemindai QGIS)
                with open(full, "rb") as fh:
                    z.writestr(zi, fh.read())
    size = os.path.getsize(zp)
    if size > 25 * 1024 * 1024:
        raise SystemExit("Zip %.1f MB > 25 MB (batas repositori plugin QGIS)" % (size / 1048576.0))
    h = hashlib.sha256(open(zp, "rb").read()).hexdigest()
    with open(zp + ".sha256", "w", encoding="ascii") as fh:
        fh.write("%s  %s\n" % (h, os.path.basename(zp)))
    if getattr(a, "tulis_sumber", False):
        shutil.copy2(os.path.join(dst, "RILIS.json"), os.path.join(src, "RILIS.json"))
    shutil.rmtree(tmp, ignore_errors=True)
    print("Rilis      : %s (%.2f MB)\nSHA-256    : %s\nKeaslian   : %s\nKepatuhan  : lolos (lisensi GPL v3+, LICENSE, "
          "README, metadata, tanpa biner/__pycache__, < 25 MB)" % (zp, size / 1048576.0, h, K.status()))
    return zp


def cek(a):
    p = os.path.abspath(a.target)
    tmp = None
    if p.lower().endswith(".zip"):
        tmp = tempfile.mkdtemp(prefix="seranta_cek_")
        with zipfile.ZipFile(p) as z:
            z.extractall(tmp)
        p = os.path.join(tmp, "seranta")
    K = _load_keaslian(p)
    print(K.status(root=p))
    if tmp:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Alat rilis Seranta (pembuat)")
    sp = ap.add_subparsers(dest="cmd", required=True)
    b = sp.add_parser("buat-kunci")
    b.add_argument("--plugin", required=True)
    b.add_argument("--kunci", required=True)
    b.add_argument("--paksa", action="store_true")
    r = sp.add_parser("rilis")
    r.add_argument("--plugin", required=True)
    r.add_argument("--kunci", required=True)
    r.add_argument("--keluar", required=True)
    r.add_argument("--tulis-sumber", action="store_true",
                   help="salin RILIS.json bertanda tangan ke folder sumber (untuk di-commit ke GitHub, agar zip yang "
                        "dibuat CI/plugins.qgis.org tetap ASLI)")
    c = sp.add_parser("cek")
    c.add_argument("target")
    a = ap.parse_args(argv)
    {"buat-kunci": buat_kunci, "rilis": rilis, "cek": cek}[a.cmd](a)


if __name__ == "__main__":
    main()

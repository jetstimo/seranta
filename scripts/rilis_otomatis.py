"""Seranta - rilis satu perintah dari laptop pembuat (bukan bagian plugin).
Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later.

Kunci privat TIDAK pernah keluar dari laptop: tanda tangan dibuat di sini, lalu GitHub Actions (release.yml) yang
menguji ulang, membuat zip, melampirkannya ke GitHub Release dan mengunggahnya ke plugins.qgis.org.

    python scripts/rilis_otomatis.py              rilis penuh (atau klik dua kali scripts\\rilis_otomatis.bat)
    python scripts/rilis_otomatis.py --coba       periksa saja: uji, validasi, tanda tangan percobaan; tanpa commit/push/tag
    python scripts/rilis_otomatis.py --kunci PATH pakai kunci di PATH (disimpan sebagai lokasi bawaan berikutnya)

Urutan:
  1. git bersih, versi di metadata.txt = __version__, ada catatan versi itu di CHANGELOG.md dan metadata (changelog=)
  2. versi belum pernah dirilis (tag v<versi> belum ada, belum tercatat di RILIS_RESMI.json)
  3. semua uji yang dijalankan workflow release.yml, cek nama merek, validasi aturan plugins.qgis.org
  4. tanda tangan dengan kunci privat (rilis_resmi.py rilis --tulis-sumber), lalu verifikasi keaslian zip = ASLI
  5. commit RILIS.json + RILIS_RESMI.json, push
  6. branch fitur: buat & merge PR lewat GitHub CLI (gh) bila terpasang; lalu tag v<versi> di main dan push tag
     -> release.yml menerbitkan ke plugins.qgis.org. Tanpa gh: branch di-push dan langkah PR ditampilkan.

Lokasi kunci dicari berurutan: --kunci, variabel lingkungan SERANTA_KUNCI, berkas ~/.seranta_rilis.json (hanya LOKASI
kunci yang disimpan, bukan isinya), folder _KUNCI_PRIBADI/*.key di repositori (diabaikan git).
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess  # nosec B404 - alat pembuat, perintah tetap (git/gh/python)
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(ROOT, "seranta")
CONF = os.path.join(os.path.expanduser("~"), ".seranta_rilis.json")
REPO_WEB = "https://github.com/jetstimo/seranta"
PLUGIN_WEB = "https://plugins.qgis.org/plugins/seranta/"


def say(msg):
    print(msg, flush=True)


def stop(msg):
    say("\n[BERHENTI] " + msg)
    sys.exit(1)


def run(cmd, check=True, capture=False):
    """Jalankan perintah tetap (daftar argumen, tanpa shell)."""
    r = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=capture)  # nosec B603
    if check and r.returncode != 0:
        detail = ((r.stderr or "") + (r.stdout or "")).strip() if capture else ""
        stop("perintah gagal: %s%s" % (" ".join(cmd), ("\n" + detail[-1500:]) if detail else ""))
    return r


def out(cmd):
    return run(cmd, check=False, capture=True).stdout.strip()


def have(prog):
    return shutil.which(prog) is not None


# ----------------------------------------------------------------------------- 1-2. pemeriksaan awal
def versi():
    meta = open(os.path.join(PLUGIN, "metadata.txt"), encoding="utf-8").read()
    m = re.search(r"^version=(\S+)", meta, re.M)
    if not m:
        stop("version= tidak ada di seranta/metadata.txt")
    v = m.group(1)
    py = open(os.path.join(PLUGIN, "buat_input_desain.py"), encoding="utf-8").read()
    mp = re.search(r'^__version__ = "([^"]+)"', py, re.M)
    if not mp or mp.group(1) != v:
        stop("__version__ di buat_input_desain.py (%s) beda dengan metadata.txt (%s)" % (mp.group(1) if mp else "-", v))
    if not re.search(r"^changelog=%s\b" % re.escape(v), meta, re.M):
        stop("changelog= di metadata.txt belum diawali catatan versi %s" % v)
    if not re.search(r"^## %s\b" % re.escape(v), open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8").read(), re.M):
        stop("CHANGELOG.md belum punya bagian '## %s'" % v)
    return v


def cek_git(v, coba):
    if not have("git"):
        stop("git tidak ditemukan di PATH")
    kotor = out(["git", "status", "--porcelain"])
    if kotor and not coba:
        stop("masih ada perubahan yang belum di-commit:\n" + kotor)
    if out(["git", "tag", "-l", "v" + v]):
        stop("tag v%s sudah ada: naikkan versi dulu" % v)
    remote = out(["git", "ls-remote", "--tags", "origin", "v" + v])
    if remote:
        stop("tag v%s sudah ada di GitHub: versi ini sudah dirilis" % v)
    reg = os.path.join(ROOT, "RILIS_RESMI.json")
    if os.path.exists(reg) and v in (json.load(open(reg, encoding="utf-8")).get("rilis") or {}):
        stop("versi %s sudah tercatat di RILIS_RESMI.json" % v)
    return out(["git", "rev-parse", "--abbrev-ref", "HEAD"])


# ----------------------------------------------------------------------------- 3. uji & validasi
def uji():
    wf = open(os.path.join(ROOT, ".github", "workflows", "release.yml"), encoding="utf-8").read()
    tests = re.findall(r"^\s*python (seranta/tests/\S+\.py)(.*)$", wf, re.M)
    if not tests:
        stop("daftar uji tidak terbaca dari release.yml")
    for path, args in tests:
        r = subprocess.run([sys.executable, path] + args.split(), cwd=ROOT, text=True, capture_output=True)  # nosec B603
        last = (r.stdout or r.stderr).strip().splitlines()[-1:] or [""]
        say("  %-32s %s  %s" % (path.split("/")[-1], "lulus" if r.returncode == 0 else "GAGAL", last[0][:70]))
        if r.returncode != 0:
            stop("uji %s gagal:\n%s" % (path, ((r.stdout or "") + (r.stderr or ""))[-1500:]))
    run([sys.executable, "scripts/check_neutral.py", "seranta"])
    tmp = tempfile.mkdtemp(prefix="seranta_val_")
    try:
        r = run([sys.executable, "scripts/release.py", "seranta", tmp, "--strict"], capture=True)
        say("  " + next((x for x in r.stdout.splitlines() if x.startswith("VALIDASI")), "validasi plugins.qgis.org lulus"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ----------------------------------------------------------------------------- 4. tanda tangan
def cari_kunci(arg):
    cand = [arg, os.environ.get("SERANTA_KUNCI", "")]
    if os.path.exists(CONF):
        try:
            cand.append(json.load(open(CONF, encoding="utf-8")).get("kunci", ""))
        except Exception:
            pass
    cand += sorted(glob.glob(os.path.join(ROOT, "_KUNCI_PRIBADI", "*.key")))
    for c in cand:
        if c and os.path.isfile(c):
            return os.path.abspath(c)
    stop("kunci privat tidak ditemukan. Jalankan sekali dengan --kunci <berkas kunci>, atau isi SERANTA_KUNCI.")


def tanda_tangan(kunci, v, coba):
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import rilis_resmi as R
    keluar = tempfile.mkdtemp(prefix="seranta_rilis_") if coba else os.path.join(ROOT, "dist")
    a = argparse.Namespace(plugin=PLUGIN, kunci=kunci, keluar=keluar,
                           registri="" if coba else os.path.join(ROOT, "RILIS_RESMI.json"), tulis_sumber=not coba)
    zp = R.rilis(a)
    import zipfile
    chk = tempfile.mkdtemp(prefix="seranta_cek_")
    try:
        with zipfile.ZipFile(zp) as z:          # zip buatan sendiri (rilis_resmi.py), bukan unduhan
            z.extractall(chk)  # nosec B202
        code, text, _info = R.periksa(os.path.join(chk, "seranta"))
    finally:
        shutil.rmtree(chk, ignore_errors=True)
    if code != "ASLI":
        stop("verifikasi zip bertanda tangan gagal: %s" % text)
    say("  keaslian zip: %s" % code)
    if coba:
        shutil.rmtree(keluar, ignore_errors=True)
    return zp


# ----------------------------------------------------------------------------- 5-6. git, PR, tag
def terbitkan(v, branch):
    run(["git", "add", "seranta/RILIS.json", "RILIS_RESMI.json"])
    run(["git", "commit", "-m", "Seranta %s: tanda tangan rilis" % v])
    if branch in ("main", "master"):
        run(["git", "push", "origin", branch])
    else:
        run(["git", "push", "-u", "origin", branch])
        if not (have("gh") and run(["gh", "auth", "status"], check=False, capture=True).returncode == 0):
            say("\nBranch %s sudah di-push. GitHub CLI (gh) tidak tersedia, jadi lanjutkan di browser:" % branch)
            say("  1. buka %s/compare/main...%s lalu buat & merge Pull Request" % (REPO_WEB, branch))
            say("  2. jalankan lagi perintah ini dari branch main (tag v%s dibuat otomatis)" % v)
            say("     atau di GitHub: Actions > Release > Run workflow")
            return False
        if not out(["gh", "pr", "list", "--head", branch, "--state", "open", "--json", "number", "-q", ".[].number"]):
            run(["gh", "pr", "create", "--base", "main", "--head", branch, "--title", "Seranta %s" % v,
                 "--body", "Rilis Seranta %s (lihat CHANGELOG.md). Tanda tangan rilis dibuat di laptop pembuat." % v])
        run(["gh", "pr", "merge", branch, "--merge"])
        run(["git", "checkout", "main"])
        run(["git", "pull", "--ff-only", "origin", "main"])
        if versi() != v:
            stop("main setelah merge tidak berisi versi %s" % v)
    run(["git", "tag", "-a", "v" + v, "-m", "Seranta %s" % v])
    run(["git", "push", "origin", "v" + v])
    return True


def pantau(v):
    if not (have("gh") and run(["gh", "auth", "status"], check=False, capture=True).returncode == 0):
        say("Pantau di %s/actions (workflow Release)." % REPO_WEB)
        return
    rid = out(["gh", "run", "list", "--workflow", "release.yml", "--limit", "1", "--json", "databaseId",
               "-q", ".[0].databaseId"])
    if rid:
        say("Memantau workflow Release (#%s) ..." % rid)
        r = run(["gh", "run", "watch", rid, "--exit-status"], check=False)
        say("Workflow Release %s." % ("SELESAI: versi %s terbit" % v if r.returncode == 0 else
                                       "GAGAL - lihat %s/actions/runs/%s" % (REPO_WEB, rid)))


def main():
    ap = argparse.ArgumentParser(description="Rilis Seranta satu perintah (tanda tangan di laptop pembuat)")
    ap.add_argument("--coba", action="store_true", help="periksa saja; tanpa commit, push, tag")
    ap.add_argument("--kunci", default="", help="berkas kunci privat (lokasinya disimpan untuk rilis berikutnya)")
    ap.add_argument("--ya", action="store_true", help="tanpa pertanyaan konfirmasi")
    a = ap.parse_args()

    say("== Seranta: rilis otomatis%s ==" % (" (COBA, tanpa commit/push/tag)" if a.coba else ""))
    v = versi()
    branch = cek_git(v, a.coba)
    say("Versi %s, branch %s" % (v, branch))
    kunci = cari_kunci(a.kunci)
    if a.kunci:
        with open(CONF, "w", encoding="utf-8") as fh:
            json.dump({"kunci": kunci}, fh)
    say("Kunci: %s" % kunci)
    say("\n[1/3] Uji dan validasi")
    uji()
    say("\n[2/3] Tanda tangan rilis")
    zp = tanda_tangan(kunci, v, a.coba)
    if a.coba:
        say("\nCOBA selesai: semua lulus. Jalankan tanpa --coba untuk menerbitkan %s." % v)
        return
    if not a.ya:
        jawab = input("\nTerbitkan Seranta %s ke GitHub dan plugins.qgis.org? Ketik YA: " % v).strip()
        if jawab.upper() != "YA":
            run(["git", "checkout", "--", "seranta/RILIS.json", "RILIS_RESMI.json"], check=False)
            stop("dibatalkan; RILIS.json dikembalikan. Zip uji: %s" % zp)
    say("\n[3/3] Commit, push, tag")
    if terbitkan(v, branch):
        say("Tag v%s terkirim. GitHub Actions kini menguji ulang dan menerbitkan ke %s" % (v, PLUGIN_WEB))
        pantau(v)


if __name__ == "__main__":
    main()

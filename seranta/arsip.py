# -*- coding: utf-8 -*-
"""3.15.10: bahan survei yang dikirim sebagai arsip (.zip / .rar / .7z) diekstrak otomatis sebelum diperiksa.

Dulu arsip di folder yang dipilih dilewati diam-diam: cluster di dalamnya tidak diperiksa dan tidak disebut di laporan.

Aturan:
- Arsip ASLI tidak diubah atau dihapus.
- Arsip berisi satu/lebih cluster utuh (ada spreadsheet HPDB di dalamnya, atau folder cluster tidak ber-HPDB) ->
  diekstrak ke folder bernama sama di sebelah arsip (seperti "Extract to <nama>\\" di Windows), sehingga hasil QC
  tersimpan di folder cluster dan pemeriksaan lintas cluster tetap membandingkan cluster di sebelahnya.
- Arsip yang hanya memuat sebagian bahan (mis. KMZ/BAKP/TSSR) di folder cluster yang SUDAH ber-HPDB -> isinya
  diletakkan langsung di folder cluster itu; berkas yang sudah ada tidak pernah ditimpa.
- Folder bernama sama yang sudah ada (diekstrak manual) -> tidak diekstrak lagi (supaya cluster tidak dihitung 2x).
- Hanya berkas bahan yang diambil (spreadsheet, KMZ/KML, PDF/DOCX, gambar BAKP, arsip bersarang); foto evidence di
  folder FOTO/EVIDENCE dilewati. Jalur berbahaya ('..', path absolut) ditolak; ukuran dibatasi.
- .zip dibaca Python; .rar/.7z dibuka dengan tar bawaan Windows 10/11 (libarchive), cadangan UnRAR/7-Zip bila
  terpasang. Arsip berpassword / rusak / format tak didukung -> pesan jelas "ekstrak manual", tidak dilewati diam-diam.
- Jalan ulang: arsip yang tidak berubah (ukuran & waktu sama) tidak diekstrak ulang (catatan .seranta_arsip.json).
"""
import json
import os
import re
import shutil
import subprocess  # nosec B404 - hanya menjalankan tar/UnRAR/7z dengan daftar argumen tetap, tanpa shell
import zipfile

ARC_EXT = (".zip", ".rar", ".7z")
KEEP_EXT = (".xlsx", ".xlsm", ".xls", ".csv", ".kmz", ".kml", ".pdf", ".docx", ".doc", ".jpg", ".jpeg", ".png") + ARC_EXT
IMG_EXT = (".jpg", ".jpeg", ".png")
MEDIA_DIR_RX = re.compile(r"EVID|FOTO|PHOTO|DOKUMENTASI|GAMBAR|\bIMG\b|IMAGES?\b", re.I)
BAKP_RX = re.compile(r"BAKP|IZIN|IJIN|PERSETUJUAN|BERITA\s*ACARA", re.I)
MARK = ".seranta_arsip.json"
MAX_TOTAL = 3 * 1024 ** 3          # 3 GB berkas bahan per arsip
MAX_ARCHIVE = 2 * 1024 ** 3        # arsip > 2 GB tidak dibuka otomatis
MAX_ENTRIES = 20000
MAX_DEPTH = 4                      # kedalaman folder yang ditelusuri mencari arsip
MAX_NEST = 2                       # arsip di dalam arsip
TIMEOUT_S = 600


class ArsipError(Exception):
    pass


def _lp(p):
    """Path panjang Windows (\\\\?\\) supaya ekstrak bertingkat > 260 karakter tetap bisa ditulis."""
    if os.name != "nt" or p.startswith("\\\\"):
        return p
    return "\\\\?\\" + os.path.abspath(p)


def _short(p):
    return p[4:] if p.startswith("\\\\?\\") else p


def _safe_rel(name):
    """Nama anggota arsip -> path relatif aman, atau None ('..', absolut, drive)."""
    n = name.replace("\\", "/").strip()
    if not n or n.endswith("/"):
        return None
    if n.startswith("/") or re.match(r"^[A-Za-z]:", n):
        return None
    parts = [x for x in n.split("/") if x not in ("", ".")]
    if not parts or any(x == ".." for x in parts):
        return None
    if any(re.search(r'[<>:"|?*\x00-\x1f]', x) for x in parts):
        return None
    return os.path.join(*parts)


def _wanted(rel):
    base = os.path.basename(rel)
    if base.startswith("~$") or base.lower() in ("thumbs.db", ".ds_store") or base.startswith("._"):
        return False
    parts = rel.replace("\\", "/").split("/")
    if any(p.startswith("__MACOSX") for p in parts):
        return False
    ext = os.path.splitext(base)[1].lower()
    if ext not in KEEP_EXT:
        return False
    if ext in IMG_EXT and any(MEDIA_DIR_RX.search(p) for p in parts[:-1]) and not BAKP_RX.search(base):
        return False      # foto evidence: tidak diperlukan QC
    return True


def _tool_list():
    out = []
    sr = os.environ.get("SystemRoot", r"C:\Windows")
    tar = os.path.join(sr, "System32", "tar.exe")
    if os.path.isfile(tar):
        out.append(("tar", tar))
    for p in (r"C:\Program Files\WinRAR\UnRAR.exe", r"C:\Program Files (x86)\WinRAR\UnRAR.exe"):
        if os.path.isfile(p):
            out.append(("unrar", p))
            break
    for p in (r"C:\Program Files\7-Zip\7z.exe", r"C:\Program Files (x86)\7-Zip\7z.exe"):
        if os.path.isfile(p):
            out.append(("7z", p))
            break
    return out


def _run(args, cwd=None):
    kw = {}
    if os.name == "nt":
        kw["creationflags"] = 0x08000000     # CREATE_NO_WINDOW
    return subprocess.run(args, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,  # nosec B603
                          stderr=subprocess.PIPE, timeout=TIMEOUT_S, **kw)


def _members_zip(path):
    """[(rel, ukuran)] anggota zip yang diambil; ArsipError bila berpassword/berbahaya."""
    try:
        z = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as e:
        raise ArsipError("damaged or unreadable ZIP (%s)" % e)
    with z:
        infos = z.infolist()
        if len(infos) > MAX_ENTRIES:
            raise ArsipError("too many files in the archive (%d)" % len(infos))
        out, total = [], 0
        for i in infos:
            if i.is_dir():
                continue
            rel = _safe_rel(i.filename)
            if rel is None or not _wanted(rel):
                continue
            if i.flag_bits & 0x1:
                raise ArsipError("password-protected ZIP")
            if i.file_size > 50 * 1024 ** 2 and i.compress_size and i.file_size / float(i.compress_size) > 200:
                raise ArsipError("abnormal compression ratio (%s)" % i.filename)
            total += i.file_size
            out.append((i, rel))
        if total > MAX_TOTAL:
            raise ArsipError("archive content too large (%.1f GB)" % (total / 1024.0 ** 3))
        return out


def _extract_zip(path, staging):
    """Ekstrak berkas bahan dari zip ke staging; -> daftar path relatif."""
    mem = _members_zip(path)
    done = []
    with zipfile.ZipFile(path) as z:
        for info, rel in mem:
            dst = os.path.join(staging, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            try:
                with z.open(info) as src, open(dst, "wb") as fh:
                    shutil.copyfileobj(src, fh, 1024 * 1024)
            except RuntimeError as e:          # password
                raise ArsipError("password-protected ZIP (%s)" % e)
            done.append(rel)
    return done


def _extract_tool(path, staging):
    """RAR/7z (dan zip yang gagal dibaca Python) lewat tar bawaan Windows, cadangan UnRAR / 7-Zip."""
    tools = _tool_list()
    if not tools:
        raise ArsipError("no extraction tool found (Windows tar.exe / WinRAR / 7-Zip)")
    errs = []
    for kind, exe in tools:
        if kind == "unrar" and not path.lower().endswith(".rar"):
            continue
        shutil.rmtree(staging, ignore_errors=True)
        os.makedirs(staging, exist_ok=True)
        if kind == "tar":
            args = [exe, "-xf", _short(path), "-C", _short(staging)]
        elif kind == "unrar":
            args = [exe, "x", "-y", "-p-", "-idq", _short(path), _short(staging) + os.sep]
        else:
            args = [exe, "x", "-y", "-pSERANTA_TANPA_PASSWORD", "-o" + _short(staging), _short(path)]
        try:
            r = _run(args)
        except (OSError, subprocess.SubprocessError) as e:
            errs.append("%s: %s" % (kind, e))
            continue
        msg = (r.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        files = []
        for root, _ds, fs in os.walk(staging):
            for f in fs:
                files.append(os.path.relpath(os.path.join(root, f), staging))
        if r.returncode == 0 and files:
            return files
        low = " ".join(msg).lower()
        if "passphrase" in low or "password" in low or "encrypt" in low:
            raise ArsipError("password-protected archive")
        errs.append("%s: %s" % (kind, (msg[-1] if msg else "kode %d" % r.returncode)[:160]))
    raise ArsipError("cannot be opened (" + "; ".join(errs) + ")")


def _sig(path):
    st = os.stat(path)
    return [st.st_size, int(st.st_mtime)]


def _load_mark(d):
    try:
        with open(os.path.join(d, MARK), encoding="utf-8") as fh:
            m = json.load(fh)
        return m if isinstance(m, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_mark(d, m):
    try:
        with open(os.path.join(d, MARK), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(m, fh, ensure_ascii=False, indent=1)
    except OSError:
        pass


def _find_archives(root):
    out = []
    base_depth = root.rstrip("\\/").count(os.sep)
    for r, ds, fs in os.walk(root):
        depth = r.rstrip("\\/").count(os.sep) - base_depth
        ds[:] = [] if depth >= MAX_DEPTH else sorted(
            d for d in ds if not d.upper().startswith(("INPUT", "_")) and not d.startswith("."))
        for f in sorted(fs):
            if f.lower().endswith(ARC_EXT) and not f.startswith("~$"):
                out.append(os.path.join(r, f))
    return out


def _dest_name(path):
    n = os.path.basename(path)
    for e in ARC_EXT:
        if n.lower().endswith(e):
            n = n[:-len(e)]
    # 'X.kmz.zip' / '.part1.rar' -> nama folder rapi
    n = re.sub(r"\.part0*1$", "", n, flags=re.I).rstrip(" .")
    return n or "arsip"


def _is_later_part(path):
    """'X.part2.rar' dst.: bagian lanjutan RAR multi-volume dibuka lewat .part1."""
    m = re.search(r"\.part0*(\d+)\.rar$", path, re.I)
    return bool(m and int(m.group(1)) > 1)


def open_archive(path, has_hpdb, hpdb_name_rx, feedback=None):
    """3.15.10: pengguna memilih SATU berkas arsip (bukan folder) -> hanya arsip itu yang diekstrak (arsip lain di
    folder yang sama, mis. Downloads, tidak disentuh). -> folder yang diperiksa, atau ArsipError dengan alasannya."""
    path = _lp(path)
    if not os.path.isfile(path) or not path.lower().endswith(ARC_EXT):
        raise ArsipError("not a .zip/.rar/.7z file: %s" % _short(path))
    parent, name = os.path.dirname(path), os.path.basename(path)
    notes = prepare(parent, has_hpdb, hpdb_name_rx, feedback, only=path)
    rec = _load_mark(parent).get(name) or {}
    mode = rec.get("mode")
    if mode in ("folder", "ada") and os.path.isdir(os.path.join(parent, rec.get("dest", ""))):
        return os.path.join(parent, rec["dest"])
    if mode == "datar":
        return parent
    bad = [n for n in notes if "NOT OPENED" in n or "larger than" in n or "cannot be read" in n]
    if mode == "kosong":
        raise ArsipError("the archive %s holds no survey files (spreadsheet / KMZ / PDF / DOCX)" % name)
    raise ArsipError(bad[-1] if bad else "the archive %s could not be extracted" % name)


def prepare(root, has_hpdb, hpdb_name_rx, feedback=None, _nest=0, only=None):
    """Ekstrak semua arsip bahan di bawah root (atau hanya arsip 'only'). -> daftar catatan (str) untuk log.
    has_hpdb(dir) -> bool; hpdb_name_rx: regex nama spreadsheet HPDB."""
    notes = []
    root = _lp(root)

    def has_hpdb_safe(d):
        try:
            return bool(has_hpdb(d))
        except Exception:      # noqa: BLE001 - folder aneh: anggap bukan folder cluster
            return False

    def say(msg, warn=False):
        notes.append(msg)
        if feedback is not None:
            (getattr(feedback, "pushWarning", feedback.pushInfo) if warn else feedback.pushInfo)(msg)

    for arc in ([_lp(only)] if only else _find_archives(root)):
        if _is_later_part(arc):
            continue
        name = os.path.basename(arc)
        parent = os.path.dirname(arc)
        try:
            if os.path.getsize(arc) > MAX_ARCHIVE:
                say("Archive %s is larger than 2 GB: not extracted automatically - extract it manually." % name, True)
                continue
            sig = _sig(arc)
        except OSError as e:
            say("Archive %s cannot be read (%s)." % (name, e), True)
            continue
        dest_sub = os.path.join(parent, _dest_name(arc))
        pmark = _load_mark(parent)
        rec = pmark.get(name)
        if rec and rec.get("sig") == sig:
            continue                                  # sudah diekstrak, arsip tidak berubah
        if os.path.isdir(dest_sub) and not rec:
            # diekstrak manual (atau catatan run lama hilang): folder itu yang dipakai, cluster tidak dihitung 2x
            say("Archive %s: folder '%s' already exists (extracted earlier) - using that folder." % (
                name, os.path.basename(dest_sub)))
            pmark[name] = {"sig": sig, "mode": "ada", "dest": os.path.basename(dest_sub), "files": []}
            _save_mark(parent, pmark)
            continue
        staging = os.path.join(parent, "_seranta_ekstrak_tmp")
        shutil.rmtree(staging, ignore_errors=True)
        try:
            os.makedirs(staging, exist_ok=True)
            try:
                if name.lower().endswith(".zip") and zipfile.is_zipfile(arc):
                    files = _extract_zip(arc, staging)
                else:
                    allf = _extract_tool(arc, staging)
                    files = [f for f in allf if _safe_rel(f) and _wanted(f)]
                    for f in set(allf) - set(files):          # foto evidence, berkas lain: tidak ikut dipindah
                        try:
                            os.remove(os.path.join(staging, f))
                        except OSError:
                            pass
            except ArsipError as e:
                say("ARCHIVE NOT OPENED: %s - %s. Extract it manually into this folder, then run again." % (name, e), True)
                continue
            if not files:
                say("Archive %s holds no survey files (spreadsheet/KMZ/PDF/DOCX) - skipped." % name)
                pmark[name] = {"sig": sig, "mode": "kosong", "files": []}
                _save_mark(parent, pmark)
                continue
            sheets = [f for f in files if os.path.splitext(f)[1].lower() in (".xlsx", ".xlsm", ".xls", ".csv")]
            has_named_hpdb = any(hpdb_name_rx.search(os.path.splitext(os.path.basename(f))[0]) for f in sheets)
            flat = (not has_named_hpdb) and has_hpdb_safe(parent)
            moved, skipped = [], []
            if flat:
                # bahan pelengkap cluster (KMZ/BAKP/TSSR): langsung ke folder cluster, tidak menimpa berkas pengguna.
                # Arsip versi baru: berkas yang dulu diekstrak Seranta dari arsip ini diganti.
                if rec and rec.get("mode") == "datar":
                    for f in rec.get("files") or []:
                        try:
                            os.remove(os.path.join(parent, os.path.basename(f)))
                        except OSError:
                            pass
                for f in files:
                    dst = os.path.join(parent, os.path.basename(f))
                    if os.path.exists(dst):
                        skipped.append(os.path.basename(f))
                        continue
                    shutil.move(os.path.join(staging, f), dst)
                    moved.append(os.path.basename(f))
                say("Archive %s extracted into the cluster folder: %s%s" % (
                    name, ", ".join(moved[:6]) + (" ..." if len(moved) > 6 else ""),
                    (" (already present, not overwritten: %s)" % ", ".join(skipped[:4])) if skipped else ""))
                pmark[name] = {"sig": sig, "mode": "datar", "files": moved}
            else:
                # satu folder di dalam arsip berisi semuanya ('X.zip' -> 'X/...') -> tidak dibuat bertingkat 'X/X/...'
                tops = {f.replace("\\", "/").split("/")[0] for f in files}
                src_root = staging
                if len(tops) == 1 and all("/" in f.replace("\\", "/") for f in files):
                    src_root = os.path.join(staging, tops.pop())
                if os.path.isdir(dest_sub) and rec and rec.get("mode") == "folder":
                    shutil.rmtree(_lp(dest_sub), ignore_errors=True)     # versi arsip baru: ganti hasil ekstrak lama
                if os.path.isdir(dest_sub):
                    say("Archive %s: folder '%s' already exists - extract manually or rename it." % (
                        name, os.path.basename(dest_sub)), True)
                    continue
                shutil.move(src_root, dest_sub)
                n_ = sum(len(fs) for _r, _d, fs in os.walk(dest_sub))
                _save_mark(dest_sub, {"_asal": name})
                say("Archive %s extracted to folder '%s' (%d survey files)." % (name, os.path.basename(dest_sub), n_))
                pmark[name] = {"sig": sig, "mode": "folder", "dest": os.path.basename(dest_sub), "files": []}
                if _nest < MAX_NEST:
                    notes += prepare(dest_sub, has_hpdb, hpdb_name_rx, feedback, _nest + 1)
            _save_mark(parent, pmark)
            if flat and _nest < MAX_NEST and any(m.lower().endswith(ARC_EXT) for m in moved):
                notes += prepare(parent, has_hpdb, hpdb_name_rx, feedback, _nest + 1)
        except OSError as e:
            say("ARCHIVE NOT OPENED: %s - %s. Extract it manually, then run again." % (name, e), True)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
    return notes


def origin(cluster_dir, levels=4):
    """Nama arsip asal bahan cluster ini (untuk kepala laporan), atau ''."""
    out = []
    d = cluster_dir
    m = _load_mark(d)
    out += [k for k, v in m.items() if isinstance(v, dict) and v.get("mode") == "datar"]
    for _ in range(levels):
        m = _load_mark(d)
        if m.get("_asal"):
            out.insert(0, m["_asal"])
            break
        nd = os.path.dirname(d.rstrip("\\/"))
        if not nd or nd == d:
            break
        d = nd
    return ", ".join(dict.fromkeys(out))

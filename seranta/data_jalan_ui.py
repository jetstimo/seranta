# -*- coding: utf-8 -*-
"""3.15.10: DATA JALAN OFFLINE - pilihan unduh untuk setiap pengguna Seranta.

Pemeriksaan 'drop lewat jalan depan' dan persilangan tol/rel/jalan besar memakai data jalan OpenStreetMap. Server kueri
publik (Overpass) sering sibuk, sehingga cluster di wilayah yang belum pernah diperiksa bisa 'TIDAK DICEK'. Jalan keluar:
ekstrak OSM dari download.geofabrik.de (server unduhan biasa, stabil, diperbarui harian) disimpan di laptop pengguna
(<cache Seranta>\\pbf, tidak ikut sinkron OneDrive), lalu diubah SEKALI menjadi paket ringkas (akses_drop.build_paket,
jalan_osm.pbf_package). Setelah itu pemeriksaan berjalan tanpa internet.

- Pop-up sekali (beberapa detik setelah QGIS terbuka) bila laptop belum punya data offline: Unduh / Nanti (ditanya lagi
  setelah 7 hari) / Jangan tanya lagi.
- Menu Seranta > 'Offline road data...' untuk mengunduh/memperbarui kapan saja (data per pulau atau seluruh Indonesia).
- Unduhan & konversi berjalan di latar belakang QGIS (Task Manager), pengguna tetap bisa bekerja.
Data (c) OpenStreetMap contributors, ODbL.
"""
import os
import re
import time

try:
    from . import _log
except ImportError:      # modul lepas (uji)
    import _log

BASE = "https://download.geofabrik.de/asia/"
# (kunci, label, path Geofabrik, perkiraan MB per 25-11-2026)
REGIONS = [
    ("indonesia", "Seluruh Indonesia", "indonesia-latest.osm.pbf", 1662),
    ("java", "Jawa", "indonesia/java-latest.osm.pbf", 858),
    ("sumatra", "Sumatra", "indonesia/sumatra-latest.osm.pbf", 270),
    ("kalimantan", "Kalimantan", "indonesia/kalimantan-latest.osm.pbf", 141),
    ("sulawesi", "Sulawesi", "indonesia/sulawesi-latest.osm.pbf", 151),
    ("nusa-tenggara", "Bali & Nusa Tenggara", "indonesia/nusa-tenggara-latest.osm.pbf", 169),
    ("maluku", "Maluku", "indonesia/maluku-latest.osm.pbf", 26),
    ("papua", "Papua", "indonesia/papua-latest.osm.pbf", 35),
]
_TASKS = []
KEY_ASK = "seranta/osm_offline_ask"          # "never" | waktu (epoch) boleh ditanya lagi
LATER_DAYS = 7
OLD_DAYS = 60


def cache_dir():
    try:
        from .buat_input_desain import _cache_root
    except ImportError:
        from buat_input_desain import _cache_root
    return _cache_root()


def pbf_dir():
    return os.path.join(cache_dir(), "pbf")


def installed():
    """[(nama berkas .pbf, MB, tanggal)] di <cache>\\pbf."""
    d = pbf_dir()
    if not os.path.isdir(d):
        return []
    out = []
    for f in sorted(os.listdir(d)):
        if f.lower().endswith(".osm.pbf"):
            p = os.path.join(d, f)
            out.append((f, os.path.getsize(p) / 1048576.0, os.path.getmtime(p)))
    return out


def has_offline():
    if installed():
        return True
    c = cache_dir()
    return os.path.isdir(c) and any(f.startswith("osm_lokal_paket_") for f in os.listdir(c))


def _bar(iface, text):
    from qgis.PyQt.QtWidgets import QProgressBar
    mb = iface.messageBar()
    w = mb.createMessage("Seranta", text)
    pb = QProgressBar()
    pb.setMaximum(100)
    w.layout().addWidget(pb)
    mb.pushWidget(w)
    return w, pb


def _convert(iface, pbf):
    """Konversi .pbf -> paket jalan lokal + paket jalan besar/rel, di latar belakang (QgsTask)."""
    from qgis.core import QgsApplication, QgsTask
    try:
        from . import akses_drop, jalan_osm
    except ImportError:
        import akses_drop
        import jalan_osm
    cd = cache_dir()

    def work(task):
        a = akses_drop.build_paket(pbf, cd)
        task.setProgress(60)
        b = jalan_osm.pbf_package(pbf, cd)
        return bool(a), bool(b)

    def done(exc, result=None):
        mb = iface.messageBar()
        if exc is None and result and result[0]:
            mb.pushSuccess("Seranta", "Offline road data ready (%s): street and crossing checks now work without "
                                      "the OpenStreetMap servers." % os.path.basename(pbf))
        else:
            # berkas rusak/terpotong dibuang: pop-up bisa menawarkan lagi, Seranta tidak mengulang konversi tiap run
            try:
                os.remove(pbf)
            except OSError as e_:
                _log.note(e_)
            mb.pushWarning("Seranta", "Offline road data could not be prepared from %s (%s); the file was removed. "
                                      "The checks keep using the OpenStreetMap servers - try the download again from "
                                      "Vector > Seranta > Offline road data." % (os.path.basename(pbf),
                                                                                 exc or "not a valid OSM file"))
        if t in _TASKS:
            _TASKS.remove(t)
    t = QgsTask.fromFunction("Seranta: preparing offline road data", work, on_finished=done)
    _TASKS.append(t)          # referensi wajib disimpan: tanpa ini QGIS tidak memanggil on_finished
    QgsApplication.taskManager().addTask(t)
    iface.messageBar().pushInfo("Seranta", "Preparing offline road data in the background (a few minutes) ...")
    return t


def download(iface, key):
    """Unduh ekstrak Geofabrik wilayah 'key' ke <cache>\\pbf lalu konversi. Asinkron (QgsFileDownloader)."""
    from qgis.core import QgsFileDownloader
    from qgis.PyQt.QtCore import QUrl
    reg = next(r for r in REGIONS if r[0] == key)
    d = pbf_dir()
    os.makedirs(d, exist_ok=True)
    name = "%s-latest.osm.pbf" % key
    final = os.path.join(d, name)
    part = final + ".part"
    w, pb = _bar(iface, "Downloading offline road data: %s (about %d MB) ..." % (reg[1], reg[3]))
    dl = QgsFileDownloader(QUrl(BASE + reg[2]), part, "", True)

    def prog(rec, tot):
        if tot and tot > 0:
            pb.setValue(int(rec * 100 / tot))

    def ok():
        try:
            iface.messageBar().popWidget(w)
        except Exception as e_:      # noqa: BLE001
            _log.note(e_)
        try:
            if os.path.exists(final):
                os.remove(final)
            os.replace(part, final)
        except OSError as e:
            iface.messageBar().pushWarning("Seranta", "Download saved but could not be renamed: %s" % e)
            return
        _convert(iface, final)

    def err(msgs):
        try:
            iface.messageBar().popWidget(w)
        except Exception as e_:      # noqa: BLE001
            _log.note(e_)
        iface.messageBar().pushWarning("Seranta", "Offline road data download failed: %s. Try again later from "
                                                  "Vector > Seranta > Offline road data." % "; ".join(msgs)[:200])
    dl.downloadProgress.connect(prog)
    dl.downloadCompleted.connect(ok)
    dl.downloadError.connect(err)
    dl.startDownload()
    download._keep = dl          # cegah dibersihkan GC selama berjalan
    return dl


def dialog(iface, first_time=False):
    """Dialog pilihan wilayah. first_time=True: pop-up otomatis (tombol 'Nanti' & 'Jangan tanya lagi')."""
    from qgis.core import QgsSettings
    from qgis.PyQt.QtWidgets import QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout
    dlg = QDialog(iface.mainWindow())
    dlg.setWindowTitle("Seranta - offline road data")
    lay = QVBoxLayout(dlg)
    have = installed()
    txt = ("<b>Offline road data (OpenStreetMap)</b><br>Seranta checks the drop path along the street and the crossings "
           "with toll roads, railways and main roads using OpenStreetMap. The public servers are often busy, so a "
           "cluster in a new area can end up <i>not checked</i>. Download the road data once to this laptop and these "
           "checks work without the servers (source: download.geofabrik.de, updated daily; data &copy; OpenStreetMap "
           "contributors, ODbL).<br><br>")
    if have:
        txt += "Installed: " + ", ".join("%s (%.0f MB, %s)" % (f, mb, time.strftime("%d-%m-%Y", time.localtime(t)))
                                         for f, mb, t in have)
        if any(time.time() - t > OLD_DAYS * 86400 for _f, _mb, t in have):
            txt += " - older than %d days, consider updating." % OLD_DAYS
        txt += "<br>Downloading the same area again updates it.<br>"
    else:
        txt += "Nothing installed yet. Choose the area you work in (smaller = faster download):<br>"
    lab = QLabel(txt)
    lab.setWordWrap(True)
    lab.setMinimumWidth(460)
    lay.addWidget(lab)
    cb = QComboBox()
    for k, l_, _p, mb in REGIONS:
        cb.addItem("%s  (about %s)" % (l_, ("%.1f GB" % (mb / 1024.0)) if mb >= 1000 else "%d MB" % mb), k)
    lay.addWidget(cb)
    row = QHBoxLayout()
    b_dl = QPushButton("Download")
    row.addWidget(b_dl)
    b_later = QPushButton("Later" if first_time else "Close")
    row.addWidget(b_later)
    b_never = None
    if first_time:
        b_never = QPushButton("Don't ask again")
        row.addWidget(b_never)
    lay.addLayout(row)
    st = QgsSettings()
    res = {"k": None}

    def go():
        res["k"] = cb.currentData()
        dlg.accept()

    def later():
        if first_time:
            st.setValue(KEY_ASK, str(int(time.time() + LATER_DAYS * 86400)))
        dlg.reject()

    def never():
        st.setValue(KEY_ASK, "never")
        dlg.reject()
    b_dl.clicked.connect(go)
    b_later.clicked.connect(later)
    if b_never is not None:
        b_never.clicked.connect(never)
    (dlg.exec if hasattr(dlg, "exec") else dlg.exec_)()
    if res["k"]:
        st.setValue(KEY_ASK, "never")      # sudah memilih: tidak ditanya otomatis lagi (menu tetap ada)
        download(iface, res["k"])


def maybe_ask(iface):
    """Pop-up otomatis sekali bila laptop belum punya data offline (dipanggil beberapa detik setelah QGIS terbuka)."""
    from qgis.core import QgsSettings
    try:
        if has_offline():
            return
        v = str(QgsSettings().value(KEY_ASK, "") or "")
        if v == "never" or (re.match(r"^\d+$", v) and time.time() < int(v)):
            return
        dialog(iface, first_time=True)
    except Exception as e_:      # noqa: BLE001 - pop-up tidak boleh mengganggu QGIS
        _log.note(e_)

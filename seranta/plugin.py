# -*- coding: utf-8 -*-
# Seranta - FTTH Design Assistant - menus, toolbar and Processing registration
# Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-2.0-or-later (see LICENSE).
try:
    from . import _log
except ImportError:  # dijalankan sebagai modul lepas (uji unit)
    import _log
import os

from qgis.core import QgsApplication, QgsSettings
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui import QDesktopServices, QIcon

try:                                    # Qt6 / QGIS 4
    from qgis.PyQt.QtGui import QAction
except ImportError:                     # Qt5 / QGIS 3
    from qgis.PyQt.QtWidgets import QAction

from .provider import SerantaProvider

MENU = "&Seranta"
HERE = os.path.dirname(__file__)
TOOLS = [
    ("seranta:buat_input_desain_apd", "1. Siapkan Input Desain Otomatis + QC Survei",
     "HPDB + KMZ survei -> input desain otomatis (HP, tiang, jalur) dan QC 9 standar, satu klik, bisa banyak cluster"),
    ("seranta:alokasi_fdt_fat", "2. Alokasi FDT & FAT (estimasi kebutuhan)",
     "Jumlah FAT, pemakaian FDT existing (COLO) dalam radius, usulan FDT baru, dan link budget"),
    ("seranta:pasca_desain_fdt_fat_code", "3. Pasca-Desain: Kode FDT-FAT, Tabel Closure + QC",
     "Ekspor desain otomatis -> tabel kode FDT-FAT, tabel core closure berwarna, dan QC pasca-desain"),
    ("seranta:qc_apd_pasca_desain", "4. QC APD Pasca-Desain (aturan paket APD + kualitas jaringan)",
     "Ekspor desain / KMZ APD -> 22 aturan QC dengan laporan HTML yang menjelaskan setiap temuan"),
]


class SerantaPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.provider = None
        self.actions = []
        self.nav = None

    def initProcessing(self):  # noqa: N802 - QGIS API name
        self.provider = SerantaProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def _add(self, label, tip, slot, toolbar=False, icon=None):
        act = QAction(icon or QIcon(os.path.join(HERE, "icon.png")), label, self.iface.mainWindow())
        act.setToolTip(tip)
        act.setStatusTip(tip)
        act.triggered.connect(slot)
        if toolbar:
            self.iface.addToolBarIcon(act)
        self.iface.addPluginToVectorMenu(MENU, act)
        self.actions.append(act)
        return act

    def initGui(self):  # noqa: N802 - QGIS API name
        self.initProcessing()
        for i, (alg, label, tip) in enumerate(TOOLS):
            self._add(label, tip, lambda checked=False, a=alg: self.run(a), toolbar=(i == 0))
        self._add("Navigator QC (temuan interaktif)",
                  "Daftar temuan per kategori; klik untuk langsung menuju lokasi masalah di peta", self.show_nav,
                  toolbar=True, icon=QIcon(os.path.join(HERE, "icon_nav.png")))
        try:
            from .qc_navigator import QcNavigator, RIGHT_DOCK
            self.nav = QcNavigator(self.iface)
            self.iface.addDockWidget(RIGHT_DOCK, self.nav)
            self._tabify()
            self.nav.hide()
        except Exception:
            self.nav = None
        self._add("Handbook Seranta", "Panduan lengkap: arti setiap isian, data yang dibutuhkan, hasil, dan arti tiap temuan", self.guide)
        self._add("Tentang dan lisensi", "Versi, pencipta, dan lisensi", self.about)
        self._welcome()

    def _welcome(self):
        st = QgsSettings()
        key = "seranta/welcomed"
        if st.value(key, "") == "1":
            return
        st.setValue(key, "1")
        try:
            self.iface.messageBar().pushInfo(
                "Seranta",
                "Terpasang. Buka menu Vector > Seranta > Handbook untuk mulai, atau klik ikon Seranta di toolbar.")
        except Exception as _e:
            _log.note(_e)

    def _tabify(self):
        """Letakkan panel Navigator sebagai tab di samping Processing Toolbox agar cukup tinggi untuk dibaca."""
        try:
            from qgis.PyQt.QtWidgets import QDockWidget
            for d in self.iface.mainWindow().findChildren(QDockWidget):
                if d.objectName() in ("ProcessingToolbox", "processingToolbox") and d.isVisible():
                    self.iface.mainWindow().tabifyDockWidget(d, self.nav)
                    break
        except Exception as _e:
            _log.note(_e)

    def show_nav(self):
        if self.nav is None:
            from .qc_navigator import QcNavigator, RIGHT_DOCK
            self.nav = QcNavigator(self.iface)
            self.iface.addDockWidget(RIGHT_DOCK, self.nav)
        self.nav.refresh()
        self.nav.show()
        self.nav.raise_()

    def unload(self):
        if self.nav is not None:
            try:
                self.nav.cleanup()
                self.iface.removeDockWidget(self.nav)
                self.nav.deleteLater()
            except Exception as _e:
                _log.note(_e)
            self.nav = None
        for act in self.actions:
            self.iface.removePluginVectorMenu(MENU, act)
            try:
                self.iface.removeToolBarIcon(act)
            except Exception as _e:
                _log.note(_e)
        self.actions = []
        if self.provider:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None

    def run(self, alg):
        import processing
        processing.execAlgorithmDialog(alg, {})

    def guide(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.join(HERE, "help", "handbook.html")))

    def about(self):
        from qgis.PyQt.QtWidgets import QMessageBox
        from .buat_input_desain import __version__, __author__, integrity_status
        QMessageBox.about(
            self.iface.mainWindow(), "Seranta",
            "<b>Seranta&trade; - FTTH Design Assistant</b> v%s<br>Pencipta: %s<br>Integritas file: %s<br><br>"
            "Menyiapkan input desain otomatis, QC desain FTTH per kategori (homepass, tiang, jalur, boundary, FINDIM, colo, "
            "BAKP), navigator temuan interaktif, dan estimasi alokasi FDT/FAT.<br><br>Lisensi GNU GPL v2 atau lebih baru. Hak cipta tetap pada pencipta; "
            "salinan dan modifikasi wajib mencantumkan nama pencipta dan lisensi yang sama. "
            "Seranta&trade; adalah merek milik Joseph Edward Timothy Siahaan."
            % (__version__, __author__, integrity_status()))

# -*- coding: utf-8 -*-
# Seranta - FTTH Design Assistant - menus, toolbar and Processing registration
# Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-2.0-or-later (see LICENSE).
try:
    from . import _log
except ImportError:  # dijalankan sebagai modul lepas (uji unit)
    import _log
import os

from qgis.core import QgsApplication, QgsSettings
from qgis.PyQt.QtGui import QIcon

try:                                    # Qt6 / QGIS 4
    from qgis.PyQt.QtGui import QAction
except ImportError:                     # Qt5 / QGIS 3
    from qgis.PyQt.QtWidgets import QAction

from .provider import SerantaProvider

MENU = "&Seranta"
HERE = os.path.dirname(__file__)
TOOLS = [
    ("seranta:buat_input_desain_apd", "1. Survey QC && Design Input",
     "Pick a survey folder (homepass spreadsheet + KMZ): checks the survey and prepares the auto-design input"),
    ("seranta:alokasi_fdt_fat", "2. FDT && FAT Allocation",
     "Pick a checked cluster folder: estimates FATs, reuse of existing FDTs and new FDTs, with a link budget"),
    ("seranta:pasca_desain_fdt_fat_code", "3. Post-Design Tables",
     "Pick the auto-design output folder: FDT-FAT code table, colour-coded closure tables and post-design checks"),
    ("seranta:qc_apd_pasca_desain", "4. Design Package QC",
     "Pick the final design folder or KMZ: rule-based QC with a plain-language report"),
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
        self._add("QC Findings Navigator",
                  "Browse findings by category and zoom to each one on the map", self.show_nav,
                  toolbar=True, icon=QIcon(os.path.join(HERE, "icon_nav.png")))
        try:
            from .qc_navigator import QcNavigator, RIGHT_DOCK
            self.nav = QcNavigator(self.iface)
            self.iface.addDockWidget(RIGHT_DOCK, self.nav)
            self._tabify()
            self.nav.hide()
        except Exception:
            self.nav = None
        self._add("About Seranta", "Version, author and licence", self.about)
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
                "Installed. Open Vector > Seranta and pick a tool; each tool only needs a folder.")
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

    def about(self):
        from qgis.PyQt.QtWidgets import QMessageBox
        from .buat_input_desain import __version__, __author__, integrity_status
        QMessageBox.about(
            self.iface.mainWindow(), "Seranta",
            "<b>Seranta&trade; - FTTH Design Assistant</b> v%s<br>Author: %s<br>File integrity: %s<br><br>"
            "Four one-folder tools for FTTH/GPON access networks: survey QC and design input, FDT/FAT allocation, "
            "post-design tables, and design package QC. Reports are written in Indonesian.<br><br>"
            "Licence: GNU GPL v2 or later. Copies and modifications must keep the author's name and the same licence. "
            "Seranta&trade; is a trademark of Joseph Edward Timothy Siahaan."
            % (__version__, __author__, integrity_status(en=True)))

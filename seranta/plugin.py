# -*- coding: utf-8 -*-
# Seranta - FTTH Design Assistant - menus, toolbar and Processing registration
# Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later (see LICENSE).
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
        try:
            from qgis.core import QgsProject
            from .qc_navigator import is_qc_layer
            from . import basemap
            if any(is_qc_layer(lyr) for lyr in QgsProject.instance().mapLayers().values()):
                basemap.ensure()
        except Exception as _e:
            _log.note(_e)
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
        box = QMessageBox(self.iface.mainWindow())
        box.setWindowTitle("Seranta")
        box.setText(
            "<b>Seranta&trade; - FTTH Design Assistant</b> v%s<br>Author: %s<br>File integrity: %s<br><br>"
            "Four one-folder tools for FTTH/GPON access networks: survey QC and design input, FDT/FAT allocation, "
            "post-design tables, and design package QC. Reports are written in Indonesian.<br><br>"
            "Licence: GNU GPL v3 or later with the section 7 terms in LICENSE: copies and modifications must keep the "
            "author's name, modified versions must be renamed and marked as modified and may not claim authorship. "
            "Official releases are digitally signed by the author; the official release key fingerprint is "
            "<b>92C4-D078-D1FC-1C5B</b> (also published on plugins.qgis.org and github.com/jetstimo/seranta). "
            "Seranta&trade; is a trademark of Joseph Edward Timothy Siahaan."
            % (__version__, __author__, integrity_status(en=True)))
        role = getattr(getattr(QMessageBox, "ButtonRole", QMessageBox), "ActionRole")
        ok = getattr(getattr(QMessageBox, "StandardButton", QMessageBox), "Ok")
        ver_b = box.addButton("Verify online", role)
        box.addButton(ok)
        (box.exec if hasattr(box, "exec") else box.exec_)()
        if box.clickedButton() is ver_b:
            self._verify_online()

    def _verify_online(self):
        """Lapis 4: cocokkan salinan terpasang dengan RILIS_RESMI.json di GitHub pembuat (lewat proxy QGIS)."""
        from qgis.PyQt.QtWidgets import QMessageBox
        from . import keaslian

        def fetch(url):
            from qgis.core import QgsBlockingNetworkRequest
            from qgis.PyQt.QtCore import QUrl
            from qgis.PyQt.QtNetwork import QNetworkRequest
            req = QgsBlockingNetworkRequest()
            err = req.get(QNetworkRequest(QUrl(url)), True)
            if err != getattr(QgsBlockingNetworkRequest, "NoError", 0):
                raise IOError(req.errorMessage())
            return bytes(req.reply().content())
        try:
            code, text = keaslian.verify_online(fetch)
        except Exception as e:      # verifikasi tidak boleh membuat QGIS galat
            code, text = "GAGAL", str(e)[:120]
        title = "Official release verified" if code == "TERVERIFIKASI" else "Not verified"
        (QMessageBox.information if code == "TERVERIFIKASI" else QMessageBox.warning)(
            self.iface.mainWindow(), "Seranta - " + title, text)

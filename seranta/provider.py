# -*- coding: utf-8 -*-
# Seranta - FTTH Design Assistant - Processing provider
# Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later (see LICENSE).
import os

from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon

from .buat_input_desain import BuatInputDesain, __version__
from .pasca_desain import PascaDesain
from .alokasi_fdt import AlokasiFdtFat
from .qc_apd import QcApd


# 3.15.0: Seranta hanya melayani alat 1 (Survey QC & Design Input). Alat 2-4 tetap ada di paket tetapi tidak
# didaftarkan; untuk menampilkannya lagi di versi berikutnya, ubah SHOW_TOOLS_2_4 menjadi True.
SHOW_TOOLS_2_4 = False


class SerantaProvider(QgsProcessingProvider):
    """Seranta in the Processing Toolbox (3.15.0: Survey QC & Design Input only)."""

    def id(self):
        return "seranta"

    def name(self):
        return "Seranta"

    def longName(self):
        return "Seranta - FTTH Design Assistant v%s" % __version__

    def icon(self):
        return QIcon(os.path.join(os.path.dirname(__file__), "icon.png"))

    def loadAlgorithms(self):
        self.addAlgorithm(BuatInputDesain())
        if SHOW_TOOLS_2_4:
            self.addAlgorithm(PascaDesain())
            self.addAlgorithm(AlokasiFdtFat())
            self.addAlgorithm(QcApd())

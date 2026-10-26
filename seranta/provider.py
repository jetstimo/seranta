# -*- coding: utf-8 -*-
# Seranta - FTTH Design Assistant - Processing provider
# Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-2.0-or-later (see LICENSE).
import os

from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon

from .buat_input_desain import BuatInputDesain, __version__
from .pasca_desain import PascaDesain
from .alokasi_fdt import AlokasiFdtFat
from .qc_apd import QcApd


class SerantaProvider(QgsProcessingProvider):
    """Groups the four tools under 'Seranta' in the Processing Toolbox."""

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
        self.addAlgorithm(PascaDesain())
        self.addAlgorithm(AlokasiFdtFat())
        self.addAlgorithm(QcApd())

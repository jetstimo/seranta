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


EXTRA_KEY = "seranta/show_tools_2_4"


def show_extra_tools():
    """True bila pengguna memunculkan alat 2-4 (bawaan 3.15.0: tersembunyi, hanya alat 1)."""
    try:
        from qgis.core import QgsSettings
        return str(QgsSettings().value(EXTRA_KEY, "0")).lower() in ("1", "true", "yes")
    except Exception:
        return False


def set_extra_tools(on):
    from qgis.core import QgsSettings
    QgsSettings().setValue(EXTRA_KEY, "1" if on else "0")


class SerantaProvider(QgsProcessingProvider):
    """Groups the Seranta tools under 'Seranta' in the Processing Toolbox (tool 1 by default; tools 2-4 on request)."""

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
        # 3.15.0: Seranta fokus pada alat 1. Alat 2-4 tetap ada di paket dan bisa dimunculkan lagi lewat
        # Vektor > Seranta > "Show tools 2-4" (setelan seranta/show_tools_2_4).
        if show_extra_tools():
            self.addAlgorithm(PascaDesain())
            self.addAlgorithm(AlokasiFdtFat())
            self.addAlgorithm(QcApd())

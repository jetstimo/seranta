# -*- coding: utf-8 -*-
# Seranta - FTTH Design Assistant - QGIS plugin
# Copyright (C) 2026 Joseph Edward Timothy Siahaan
# This program is free software; you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation; either version 3 of the
# License, or (at your option) any later version, with the additional terms of section 7 in LICENSE
# (author attribution, no misrepresentation of origin, no trademark licence).


def classFactory(iface):  # noqa: N802 - name required by QGIS
    from .plugin import SerantaPlugin
    return SerantaPlugin(iface)

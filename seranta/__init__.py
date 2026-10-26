# -*- coding: utf-8 -*-
# Seranta - FTTH Design Assistant - QGIS plugin
# Copyright (C) 2026 Joseph Edward Timothy Siahaan
# This program is free software; you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation; either version 2 of the
# License, or (at your option) any later version. See LICENSE.


def classFactory(iface):  # noqa: N802 - name required by QGIS
    from .plugin import SerantaPlugin
    return SerantaPlugin(iface)

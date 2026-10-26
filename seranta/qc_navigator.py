# -*- coding: utf-8 -*-
# Seranta - FTTH Design Assistant - interactive QC navigator (dock panel)
# Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-2.0-or-later (see LICENSE).
"""Panel 'Navigator QC Seranta' (spesifikasi 13): satu panel untuk temuan alat 1 (QC strand), alat 3 (alokasi) dan
alat 4 (QC APD). Klik temuan -> peta zoom ke lokasinya, fitur dipilih dan berkedip. Filter tingkat (ERROR / WARNING /
INFO / UNVERIFIED), aturan, lingkup jaringan (Feeder / Distribution) dan status review; status review (OPEN, VERIFIED, FALSE_POSITIVE, APPROVED_EXCEPTION, RESOLVED) +
catatan disimpan langsung di layer temuan dan dipertahankan saat QC dijalankan ulang; ekspor CSV untuk reviewer."""
try:
    from . import _log
except ImportError:  # dijalankan sebagai modul lepas (uji unit)
    import _log
import os
import re

from qgis.core import QgsProject, QgsRectangle, QgsVectorLayer, QgsCoordinateTransform
from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtGui import QColor, QBrush
from qgis.PyQt.QtWidgets import (QCheckBox, QComboBox, QDockWidget, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                                 QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

REVIEW = ["OPEN", "VERIFIED", "FALSE_POSITIVE", "APPROVED_EXCEPTION", "RESOLVED"]
SEV_COL = {"ERROR": "#c62828", "WARNING": "#d9480f", "UNVERIFIED": "#6b7280", "INFO": "#8a6d00", "CEK": "#c62828"}

ROLE = getattr(Qt, "UserRole", None) or Qt.ItemDataRole.UserRole


def _qt(enum_path, legacy):
    """Ambil enum Qt6 (bertingkat) atau Qt5 (datar)."""
    obj = Qt
    for p in enum_path.split("."):
        obj = getattr(obj, p, None)
        if obj is None:
            return getattr(Qt, legacy)
    return obj


RIGHT_DOCK = _qt("DockWidgetArea.RightDockWidgetArea", "RightDockWidgetArea")


def is_qc_layer(layer):
    """Layer temuan Seranta: folder QC/ hasil alat 1, QC_TEMUAN gabungan, atau hasil ALOKASI_FDT."""
    if not isinstance(layer, QgsVectorLayer):
        return False
    try:
        if layer.customProperty("seranta_qc") == "1":
            return True
    except Exception as _e:
        _log.note(_e)
    src = layer.source().split("|")[0].replace("\\", "/")
    return bool(re.search(r"/QC/[^/]+\.shp$|/QC_APD(_\d{8}_\d{6})?/(?!QC_APD_TEMUAN)[^/]+\.(shp|dbf|csv)$|/ALOKASI_FDT(_\d{8}_\d{6})?/(FAT_ESTIMASI|FDT_ALOKASI)\.shp$", src, re.I))


class QcNavigator(QDockWidget):
    def __init__(self, iface, parent=None):
        super().__init__("Navigator QC Seranta", parent or iface.mainWindow())
        self.iface = iface
        self.setObjectName("SerantaQcNavigator")
        self.setMinimumWidth(340)
        w = QWidget()
        lay = QVBoxLayout(w)
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Cari (mis. H00172, NP6-145, rentang)")
        self.search.textChanged.connect(self.refresh)
        self.only_cek = QCheckBox("Sembunyikan INFO")
        self.only_cek.setToolTip("Sembunyikan temuan INFO (kuning)")
        self.only_cek.stateChanged.connect(self.refresh)
        self.sev = QComboBox()
        self.sev.addItems(["Semua tingkat", "ERROR", "WARNING", "UNVERIFIED", "INFO"])
        self.sev.currentIndexChanged.connect(self.refresh)
        self.rev_f = QComboBox()
        self.rev_f.addItems(["Semua review", "Belum direview (OPEN)", "Sudah direview"])
        self.rev_f.currentIndexChanged.connect(self.refresh)
        self.rule_f = QComboBox()
        self.rule_f.addItem("Semua aturan")
        self.rule_f.setToolTip("Tampilkan temuan satu aturan saja (mis. QC05_RASIO atau SPAN_OVER_MAX)")
        self.rule_f.currentIndexChanged.connect(self.refresh)
        self.scope_f = QComboBox()
        self.scope_f.addItems(["Semua lingkup", "DISTRIBUTION", "FEEDER", "Tanpa lingkup"])
        self.scope_f.setToolTip("Lingkup jaringan temuan: paket Distribution, paket Feeder, atau tidak terikat paket")
        self.scope_f.currentIndexChanged.connect(self.refresh)
        btn = QPushButton("Muat ulang")
        btn.setToolTip("Baca ulang semua layer QC Seranta di proyek")
        btn.clicked.connect(self.refresh)
        top.addWidget(self.search, 1)
        top.addWidget(self.only_cek)
        top.addWidget(btn)
        lay.addLayout(top)
        flt = QHBoxLayout()
        flt.addWidget(self.sev)
        flt.addWidget(self.rev_f)
        lay.addLayout(flt)
        flt2 = QHBoxLayout()
        flt2.addWidget(self.rule_f, 1)
        flt2.addWidget(self.scope_f)
        lay.addLayout(flt2)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Temuan", "Nilai"])
        self.tree.setColumnWidth(0, 300)
        self.tree.itemClicked.connect(self.go)
        self.tree.itemActivated.connect(self.go)
        lay.addWidget(self.tree, 1)
        nav = QHBoxLayout()
        prev_b, next_b = QPushButton("< Sebelumnya"), QPushButton("Berikutnya >")
        prev_b.clicked.connect(lambda: self.step(-1))
        next_b.clicked.connect(lambda: self.step(1))
        self.info = QLabel("")
        self.info.setWordWrap(True)
        nav.addWidget(prev_b)
        nav.addWidget(next_b)
        lay.addLayout(nav)
        rv = QHBoxLayout()
        self.rev = QComboBox()
        self.rev.addItems(REVIEW)
        self.rev.setToolTip("Status review temuan terpilih (spesifikasi 13): VERIFIED = benar masalah, FALSE_POSITIVE = "
                            "bukan masalah, APPROVED_EXCEPTION = pengecualian disetujui (isi alasan/bukti), RESOLVED = sudah diperbaiki")
        self.note = QLineEdit()
        self.note.setPlaceholderText("catatan / bukti / pemberi persetujuan")
        save_b = QPushButton("Simpan review")
        save_b.clicked.connect(self.save_review)
        exp_b = QPushButton("Ekspor CSV")
        exp_b.setToolTip("Ekspor semua temuan yang tampil (dengan status review) ke CSV")
        exp_b.clicked.connect(self.export_csv)
        rv.addWidget(self.rev)
        rv.addWidget(self.note, 1)
        rv.addWidget(save_b)
        lay.addLayout(rv)
        lay.addWidget(exp_b)
        lay.addWidget(self.info)
        self.setWidget(w)
        self._leaves = []
        self._pos = -1
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.refresh)
        QgsProject.instance().layersAdded.connect(self._maybe_refresh)
        QgsProject.instance().layersRemoved.connect(self._on_removed)

    def _on_removed(self, *a):
        self._timer.start(300)

    def cleanup(self):
        for sig, slot in ((QgsProject.instance().layersAdded, self._maybe_refresh),
                          (QgsProject.instance().layersRemoved, self._on_removed)):
            try:
                sig.disconnect(slot)
            except Exception as _e:
                _log.note(_e)

    def _maybe_refresh(self, layers):
        if any(is_qc_layer(lyr_) for lyr_ in layers):
            self._timer.start(800)          # tunggu gaya & sub-grup diterapkan
            self.show()
            self.raise_()

    def refresh(self, *a):
        self.tree.clear()
        self._leaves = []
        self._pos = -1
        q = (self.search.text() or "").strip().lower()
        only = self.only_cek.isChecked()
        sev_want = self.sev.currentText() if self.sev.currentIndex() > 0 else None
        rev_mode = self.rev_f.currentIndex()
        rule_want = self.rule_f.currentText() if self.rule_f.currentIndex() > 0 else None
        scope_mode = self.scope_f.currentIndex()
        scope_want = self.scope_f.currentText() if scope_mode in (1, 2) else None
        layers = [lyr_ for lyr_ in QgsProject.instance().mapLayers().values() if is_qc_layer(lyr_)]
        n_all = 0
        found = []
        rules_seen = set()
        for lyr in layers:
            names = [f.name() for f in lyr.fields()]
            ikode = names.index("kode") if "kode" in names else None
            iscope = names.index("lingkup") if "lingkup" in names else None
            ibukti = names.index("bukti") if "bukti" in names else None
            iket = names.index("keterangan") if "keterangan" in names else None
            ist = names.index("status") if "status" in names else None
            inil = names.index("nilai") if "nilai" in names else None
            isev = names.index("severity") if "severity" in names else None
            irev = names.index("review") if "review" in names else None
            rows = []
            for f in lyr.getFeatures():
                at = f.attributes()
                st = str(at[ist]) if ist is not None and at[ist] is not None else ""
                sv = str(at[isev]) if isev is not None and at[isev] not in (None, "") else ("INFO" if st == "INFO" else "ERROR" if st else "")
                rvv = str(at[irev]) if irev is not None and at[irev] not in (None, "") else "OPEN"
                if only and sv == "INFO":
                    continue
                if sev_want and sv != sev_want:
                    continue
                if (rev_mode == 1 and rvv != "OPEN") or (rev_mode == 2 and rvv == "OPEN"):
                    continue
                rule = str(at[ikode]) if ikode is not None and at[ikode] not in (None, "") else lyr.name()
                rule = rule if ikode is not None else re.sub(r"\s*\(\d+\)\s*$", "", rule)
                rules_seen.add(rule)
                if rule_want and rule != rule_want:
                    continue
                scp = str(at[iscope]) if iscope is not None and at[iscope] not in (None, "") and str(at[iscope]) != "NULL" else ""
                if scope_want and scp != scope_want:
                    continue
                if scope_mode == 3 and scp:
                    continue
                if iket is not None:
                    txt = str(at[iket] or "")
                else:
                    txt = " | ".join("%s=%s" % (n, v) for n, v in zip(names, at) if v not in (None, ""))[:200]
                if q and q not in txt.lower():
                    continue
                nil = at[inil] if inil is not None else None
                bk = str(at[ibukti]) if ibukti is not None and at[ibukti] not in (None, "") and str(at[ibukti]) != "NULL" else ""
                rows.append((txt, sv or st, nil, f.id(), rvv, scp, bk))
            if rows:
                rank = min({"ERROR": 0, "CEK": 0, "WARNING": 1, "UNVERIFIED": 2, "INFO": 3}.get(r[1], 3) for r in rows)
                found.append((rank, lyr.name(), lyr, rows))
        found.sort(key=lambda t: (t[0], not t[1].startswith(("S", "E")), t[1]))
        for _info, _nm, lyr, rows in found:
            top = QTreeWidgetItem(["%s  (%d)" % (lyr.name(), len(rows)), ""])
            top.setData(0, ROLE, (lyr.id(), None))
            red = _info < 2
            top.setForeground(0, QBrush(QColor(SEV_COL.get(["ERROR", "WARNING", "UNVERIFIED", "INFO"][_info], "#8a6d00"))))
            for txt, st, nil, fid, rvv, scp, bk in rows:
                it = QTreeWidgetItem([("[%s] " % rvv if rvv != "OPEN" else "") + txt,
                                      ("%.1f" % nil) if isinstance(nil, (int, float)) else ""])
                it.setToolTip(0, "%s | review: %s%s\n%s%s" % (st, rvv, (" | lingkup: %s" % scp) if scp else "", txt,
                                                              ("\nbukti: %s" % bk) if bk else ""))
                it.setData(0, ROLE, (lyr.id(), fid))
                if st in SEV_COL and st != "INFO":
                    it.setForeground(0, QBrush(QColor(SEV_COL[st])))
                top.addChild(it)
                self._leaves.append(it)
            self.tree.addTopLevelItem(top)
            top.setExpanded(red and len(rows) <= 30)
            n_all += len(rows)
        cur = self.rule_f.currentText()
        self.rule_f.blockSignals(True)
        self.rule_f.clear()
        self.rule_f.addItem("Semua aturan")
        self.rule_f.addItems(sorted(rules_seen))
        self.rule_f.setCurrentIndex(max(0, self.rule_f.findText(cur)))
        self.rule_f.blockSignals(False)
        self.info.setText("%d temuan di %d layer. Klik temuan untuk menuju lokasinya." % (n_all, self.tree.topLevelItemCount())
                          if n_all else "Belum ada layer QC Seranta di proyek. Jalankan alat 1 atau 3.")

    def step(self, d):
        if not self._leaves:
            return
        self._pos = (self._pos + d) % len(self._leaves)
        it = self._leaves[self._pos]
        self.tree.setCurrentItem(it)
        self.go(it)

    def go(self, item, col=0):
        data = item.data(0, ROLE)
        if not data:
            return
        lid, fid = data
        lyr = QgsProject.instance().mapLayer(lid)
        if lyr is None:
            return
        canvas = self.iface.mapCanvas()
        if fid is None:
            try:
                self.iface.setActiveLayer(lyr)
                self.iface.zoomToActiveLayer()
            except Exception as _e:
                _log.note(_e)
            return
        if item in self._leaves:
            self._pos = self._leaves.index(item)
        f = lyr.getFeature(fid)
        g = f.geometry()
        if g is None or g.isEmpty():
            self.info.setText("%s\n%s\n(temuan non-spasial: BOM/KMZ/data - tidak ada lokasi di peta, buka tabelnya)"
                              % (lyr.name(), item.text(0)))
            try:
                lyr.selectByIds([fid])
                ir = lyr.fields().indexOf("review")
                if ir >= 0:
                    self.rev.setCurrentIndex(REVIEW.index(str(f[ir])) if str(f[ir]) in REVIEW else 0)
            except Exception as _e:
                _log.note(_e)
            return
        try:
            ct = QgsCoordinateTransform(lyr.crs(), canvas.mapSettings().destinationCrs(), QgsProject.instance())
            from qgis.core import QgsGeometry
            g2 = QgsGeometry(g)
            g2.transform(ct)
            bb = g2.boundingBox()
        except Exception:
            g2, bb = g, g.boundingBox()
        pad = max(bb.width(), bb.height()) * 0.6
        unit_m = canvas.mapSettings().destinationCrs().isGeographic()
        pad = max(pad, 0.0006 if unit_m else 60.0)
        canvas.setExtent(QgsRectangle(bb.xMinimum() - pad, bb.yMinimum() - pad, bb.xMaximum() + pad, bb.yMaximum() + pad))
        canvas.refresh()
        try:
            lyr.selectByIds([fid])
        except Exception as _e:
            _log.note(_e)
        try:
            canvas.flashFeatureIds(lyr, [fid])
        except Exception as _e:
            _log.note(_e)
        self.info.setText("%s\n%s" % (lyr.name(), item.text(0)))
        try:
            idx = lyr.fields().indexOf("review")
            if idx >= 0:
                v = f[idx]
                self.rev.setCurrentIndex(REVIEW.index(str(v)) if str(v) in REVIEW else 0)
                ic = lyr.fields().indexOf("catatan")
                self.note.setText(str(f[ic] or "") if ic >= 0 and str(f[ic]) != "NULL" else "")
        except Exception as _e:
            _log.note(_e)

    def _current(self):
        it = self.tree.currentItem()
        data = it.data(0, ROLE) if it is not None else None
        if not data or data[1] is None:
            return None, None
        return QgsProject.instance().mapLayer(data[0]), data[1]

    def save_review(self):
        """Tulis status review + catatan ke layer temuan (shp) - bertahan saat QC dijalankan ulang."""
        lyr, fid = self._current()
        if lyr is None:
            self.info.setText("Pilih satu temuan dulu.")
            return
        ir, ic = lyr.fields().indexOf("review"), lyr.fields().indexOf("catatan")
        if ir < 0:
            self.info.setText("Layer ini (versi lama) belum punya kolom review; jalankan ulang QC dengan Seranta terbaru.")
            return
        st = self.rev.currentText()
        note = (self.note.text() or "").strip()
        if st == "APPROVED_EXCEPTION" and not note:
            self.info.setText("APPROVED_EXCEPTION wajib diberi alasan/bukti dan nama pemberi persetujuan (spesifikasi X-04).")
            return
        was = lyr.isEditable()
        if not was and not lyr.startEditing():
            self.info.setText("Layer ini hanya-baca (tabel non-spasial). Isi kolom review/note di QC_APD_TEMUAN.csv; "
                              "nilainya dibaca lagi saat QC dijalankan ulang.")
            return
        lyr.changeAttributeValue(fid, ir, st)
        if ic >= 0:
            lyr.changeAttributeValue(fid, ic, note[:200])
        ok = lyr.commitChanges() if not was else True
        self.info.setText("Review disimpan: %s%s" % (st, "" if ok else " (GAGAL commit - file terkunci?)"))
        pos = self._pos
        self.refresh()
        if self._leaves:
            self._pos = min(max(pos, 0), len(self._leaves) - 1)

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Ekspor temuan QC", "QC_REVIEW.csv", "CSV (*.csv)")
        if not path:
            return
        import csv
        n = 0
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(["layer", "severity", "kode", "lingkup", "keterangan", "nilai", "batas", "bukti", "sumber", "review",
                        "catatan", "lon", "lat"])
            for lyr in [lyr_ for lyr_ in QgsProject.instance().mapLayers().values() if is_qc_layer(lyr_)]:
                nm = [x.name() for x in lyr.fields()]

                def g(ft, k):
                    return ft[k] if k in nm and str(ft[k]) != "NULL" else ""
                for ft in lyr.getFeatures():
                    p = ft.geometry().centroid().asPoint() if ft.geometry() and not ft.geometry().isEmpty() else None
                    w.writerow([lyr.name(), g(ft, "severity") or g(ft, "status"), g(ft, "kode"), g(ft, "lingkup"),
                                g(ft, "keterangan"), g(ft, "nilai"), g(ft, "batas"), g(ft, "bukti"), g(ft, "sumber"),
                                g(ft, "review") or "OPEN", g(ft, "catatan"),
                                round(p.x(), 7) if p else "", round(p.y(), 7) if p else ""])
                    n += 1
        self.info.setText("%d temuan diekspor ke %s" % (n, path))

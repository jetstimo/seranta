# -*- coding: utf-8 -*-
"""
Penulis .docx kecil tanpa pustaka tambahan (zipfile + XML) untuk laporan QC yang bisa langsung diedit di Word:
judul, subjudul, paragraf (tebal/miring/warna), tabel bergaris dengan baris kepala, gambar JPEG/PNG sebaris,
pemisah halaman, kepala dan kaki halaman dengan nomor halaman. Huruf: Calibri (tersedia di Word) dengan cadangan
Inter/Arial.

Part of Seranta - FTTH Design Assistant.
Copyright (C) 2026 Joseph Edward Timothy Siahaan. Licensed under GPL-2.0-or-later (see LICENSE).
"""
import os
import struct
import zipfile

EMU_PER_CM = 360000


def _x(t):
    return (str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def _img_size(data):
    """(lebar, tinggi) piksel dari JPEG atau PNG."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", data[16:24])
    i = 2
    while i < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        mk = data[i + 1]
        if mk in (0xC0, 0xC1, 0xC2):
            h, w = struct.unpack(">HH", data[i + 5:i + 9])
            return w, h
        seg = struct.unpack(">H", data[i + 2:i + 4])[0]
        i += 2 + seg
    return 800, 500


class Doc(object):
    def __init__(self, title="", author=""):
        self.body = []
        self.media = []          # (name, bytes, ext)
        self.title, self.author = title, author
        self.header_text = ""
        self.footer_text = ""

    # ---- teks ----
    @staticmethod
    def _run(text, bold=False, italic=False, color=None, size=None, mono=False):
        rp = []
        if mono:
            rp.append('<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" w:cs="Consolas"/>')
        if bold:
            rp.append("<w:b/>")
        if italic:
            rp.append("<w:i/>")
        if color:
            rp.append('<w:color w:val="%s"/>' % color.lstrip("#"))
        if size:
            rp.append('<w:sz w:val="%d"/><w:szCs w:val="%d"/>' % (int(size * 2), int(size * 2)))
        lines = str(text).split("\n")
        out = []
        for k, ln in enumerate(lines):
            if k:
                out.append("<w:r><w:br/></w:r>")
            out.append('<w:r>%s<w:t xml:space="preserve">%s</w:t></w:r>' % (
                ("<w:rPr>%s</w:rPr>" % "".join(rp)) if rp else "", _x(ln)))
        return "".join(out)

    def para(self, parts, style=None, align=None, space_after=None, keep_next=False):
        """parts: str atau daftar (teks, dict(bold, italic, color, size, mono))."""
        if isinstance(parts, str):
            parts = [(parts, {})]
        ppr = []
        if style:
            ppr.append('<w:pStyle w:val="%s"/>' % style)
        if keep_next:
            ppr.append("<w:keepNext/>")
        if space_after is not None:
            ppr.append('<w:spacing w:after="%d"/>' % int(space_after))
        if align:
            ppr.append('<w:jc w:val="%s"/>' % align)
        runs = "".join(self._run(t, **o) for t, o in parts)
        self.body.append("<w:p>%s%s</w:p>" % (("<w:pPr>%s</w:pPr>" % "".join(ppr)) if ppr else "", runs))

    def heading(self, text, level=1):
        self.para([(text, {})], style="Heading%d" % level, keep_next=True)

    def page_break(self):
        self.body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')

    # ---- tabel ----
    def table(self, rows, widths_cm=None, header=True, shade=None, font_size=9):
        """rows: [[sel,...]]; sel = str atau (str, dict run). shade: {(r,c): 'HEX'}."""
        ncol = max(len(r) for r in rows)
        widths = widths_cm or [16.0 / ncol] * ncol
        tw = int(sum(widths) * 567)
        grid = "".join('<w:gridCol w:w="%d"/>' % int(w * 567) for w in widths)
        trs = []
        for ri, r in enumerate(rows):
            tcs = []
            for ci in range(ncol):
                cell = r[ci] if ci < len(r) else ""
                txt, opt = (cell if isinstance(cell, tuple) else (cell, {}))
                opt = dict(opt)
                opt.setdefault("size", font_size)
                fill = None
                if header and ri == 0:
                    opt["bold"] = True
                    opt["color"] = "FFFFFF"
                    fill = "262626"
                fill = (shade or {}).get((ri, ci), fill)
                tcpr = '<w:tcW w:w="%d" w:type="dxa"/>%s' % (
                    int(widths[ci] * 567), ('<w:shd w:val="clear" w:color="auto" w:fill="%s"/>' % fill) if fill else "")
                tcs.append('<w:tc><w:tcPr>%s</w:tcPr><w:p><w:pPr><w:spacing w:after="0"/></w:pPr>%s</w:p></w:tc>'
                           % (tcpr, self._run(txt, **opt)))
            trpr = "<w:trPr><w:tblHeader/><w:cantSplit/></w:trPr>" if header and ri == 0 else "<w:trPr><w:cantSplit/></w:trPr>"
            trs.append("<w:tr>%s%s</w:tr>" % (trpr, "".join(tcs)))
        b = '<w:%s w:val="single" w:sz="4" w:space="0" w:color="C6C6C6"/>'
        borders = "<w:tblBorders>%s</w:tblBorders>" % "".join(b % s for s in ("top", "left", "bottom", "right", "insideH", "insideV"))
        self.body.append('<w:tbl><w:tblPr><w:tblW w:w="%d" w:type="dxa"/>%s<w:tblLayout w:type="fixed"/>'
                         '<w:tblCellMar><w:left w:w="80" w:type="dxa"/><w:right w:w="80" w:type="dxa"/></w:tblCellMar>'
                         '</w:tblPr><w:tblGrid>%s</w:tblGrid>%s</w:tbl>' % (tw, borders, grid, "".join(trs)))
        self.body.append('<w:p><w:pPr><w:spacing w:after="60"/></w:pPr></w:p>')

    # ---- gambar ----
    def image(self, data, width_cm=16.0, caption=None):
        ext = "png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "jpeg"
        n = len(self.media) + 1
        name = "image%d.%s" % (n, "png" if ext == "png" else "jpg")
        self.media.append((name, data, ext))
        w, h = _img_size(data)
        cx = int(width_cm * EMU_PER_CM)
        cy = int(cx * h / float(w or 1))
        rid = "rIdImg%d" % n
        self.body.append(
            '<w:p><w:pPr><w:keepNext/><w:spacing w:after="40"/></w:pPr><w:r><w:drawing>'
            '<wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="%d" cy="%d"/><wp:docPr id="%d" name="Gambar %d"/>'
            '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
            '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:nvPicPr>'
            '<pic:cNvPr id="%d" name="%s"/><pic:cNvPicPr/></pic:nvPicPr><pic:blipFill><a:blip r:embed="%s"/>'
            '<a:stretch><a:fillRect/></a:stretch></pic:blipFill><pic:spPr><a:xfrm><a:off x="0" y="0"/>'
            '<a:ext cx="%d" cy="%d"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>'
            '</a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>' % (cx, cy, n, n, n, name, rid, cx, cy))
        if caption:
            self.para([(caption, {"italic": True, "size": 8.5, "color": "525252"})], space_after=160)

    # ---- tulis ----
    def save(self, path):
        W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" ' \
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" ' \
            'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"'
        sect = ('<w:sectPr><w:headerReference w:type="default" r:id="rIdHdr"/><w:footerReference w:type="default" r:id="rIdFtr"/>'
                '<w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1021" w:bottom="1134" w:left="1021" '
                'w:header="567" w:footer="567" w:gutter="0"/></w:sectPr>')
        document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document %s><w:body>%s%s</w:body></w:document>'
                    % (W, "".join(self.body), sect))
        styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                  '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                  '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri" '
                  'w:eastAsia="Calibri"/><w:sz w:val="20"/><w:szCs w:val="20"/><w:color w:val="161616"/><w:lang w:val="id-ID"/>'
                  '</w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="100" w:line="264" w:lineRule="auto"/></w:pPr>'
                  '</w:pPrDefault></w:docDefaults>'
                  '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
                  '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:pPr>'
                  '<w:spacing w:after="120"/></w:pPr><w:rPr><w:b/><w:sz w:val="40"/><w:color w:val="161616"/></w:rPr></w:style>'
                  '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/>'
                  '<w:next w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="280" w:after="100"/><w:outlineLvl w:val="0"/>'
                  '<w:pBdr><w:bottom w:val="single" w:sz="6" w:space="2" w:color="0F62FE"/></w:pBdr></w:pPr>'
                  '<w:rPr><w:b/><w:sz w:val="28"/><w:color w:val="161616"/></w:rPr></w:style>'
                  '<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/>'
                  '<w:next w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="200" w:after="60"/><w:outlineLvl w:val="1"/>'
                  '</w:pPr><w:rPr><w:b/><w:sz w:val="23"/><w:color w:val="0F62FE"/></w:rPr></w:style>'
                  '</w:styles>')
        rels_doc = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                    '<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
                    'Target="styles.xml"/>'
                    '<Relationship Id="rIdHdr" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" '
                    'Target="header1.xml"/>'
                    '<Relationship Id="rIdFtr" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" '
                    'Target="footer1.xml"/>']
        for i, (name, _d, _e) in enumerate(self.media, start=1):
            rels_doc.append('<Relationship Id="rIdImg%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                            'relationships/image" Target="media/%s"/>' % (i, name))
        rels_doc.append("</Relationships>")
        hdr = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:hdr %s><w:p><w:pPr><w:jc w:val="right"/></w:pPr>%s</w:p>'
               '</w:hdr>' % (W, self._run(self.header_text, color="6F6F6F", size=8)))
        ftr = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:ftr %s><w:p><w:pPr><w:tabs><w:tab w:val="right" '
               'w:pos="9864"/></w:tabs></w:pPr>%s<w:r><w:rPr><w:color w:val="6F6F6F"/><w:sz w:val="16"/></w:rPr><w:tab/>'
               '<w:t xml:space="preserve">Halaman </w:t></w:r><w:r><w:rPr><w:color w:val="6F6F6F"/><w:sz w:val="16"/></w:rPr>'
               '<w:fldChar w:fldCharType="begin"/></w:r><w:r><w:rPr><w:sz w:val="16"/></w:rPr><w:instrText xml:space="preserve"> '
               'PAGE </w:instrText></w:r><w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:rPr><w:color w:val="6F6F6F"/>'
               '<w:sz w:val="16"/></w:rPr><w:t>1</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p></w:ftr>'
               % (W, self._run(self.footer_text, color="6F6F6F", size=8)))
        ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
              '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
              '<Default Extension="xml" ContentType="application/xml"/>'
              '<Default Extension="jpg" ContentType="image/jpeg"/><Default Extension="png" ContentType="image/png"/>'
              '<Override PartName="/word/document.xml" '
              'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
              '<Override PartName="/word/styles.xml" '
              'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
              '<Override PartName="/word/header1.xml" '
              'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>'
              '<Override PartName="/word/footer1.xml" '
              'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
              '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
              '</Types>')
        root = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
                'Target="word/document.xml"/><Relationship Id="rId2" '
                'Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" '
                'Target="docProps/core.xml"/></Relationships>')
        core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties '
                'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
                'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>%s</dc:title><dc:creator>%s</dc:creator>'
                '</cp:coreProperties>' % (_x(self.title), _x(self.author)))
        tmp = path + ".tmp"
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", ct)
            z.writestr("_rels/.rels", root)
            z.writestr("docProps/core.xml", core)
            z.writestr("word/document.xml", document)
            z.writestr("word/styles.xml", styles)
            z.writestr("word/header1.xml", hdr)
            z.writestr("word/footer1.xml", ftr)
            z.writestr("word/_rels/document.xml.rels", "".join(rels_doc))
            for name, data, _e in self.media:
                z.writestr("word/media/%s" % name, data)
        os.replace(tmp, path)
        return path


SEV_HEX = dict(zip(("ERROR", "WARNING", "UNVERIFIED", "INFO", "PASS", "CEK"), ("DA1E28", "BA4E00", "6F6F6F", "0043CE", "198038", "DA1E28")))
SEV_WORD = dict(zip(("ERROR", "WARNING", "UNVERIFIED", "INFO", "PASS", "CEK"), ("Wajib diperbaiki", "Perlu ditinjau", "Belum bisa dicek", "Catatan", "Lolos", "Perlu dicek")))
SEV_FILL = dict(zip(("ERROR", "WARNING", "UNVERIFIED", "INFO", "PASS", "CEK"), ("FFF1F1", "FFF2E8", "F4F4F4", "EDF5FF", "DEFBE6", "FFF1F1")))


def qc_report(path, title, subtitle, meta_rows, summary_rows, findings, images, footer="", max_findings=150):
    """Laporan QC Word standar Seranta.
    meta_rows: [(label, nilai)]; summary_rows: [(aturan/standar, tingkat, jumlah, keterangan)];
    findings: [dict(fid, sev, title, obj, arti, fix, value, limit, unit, lat, lon, dasar, source)];
    images: {fid: jpeg_bytes}."""
    d = Doc(title=title, author="Seranta")
    d.header_text = title
    d.footer_text = footer
    d.para([(title, {})], style="Title")
    d.para([(subtitle, {"color": "525252", "size": 11})], space_after=200)
    d.table([("Keterangan", "Nilai")] + [(k, str(v)) for k, v in meta_rows if v not in (None, "")], widths_cm=[5.0, 11.8])
    cnt = {}
    for f in findings:
        cnt[f["sev"]] = cnt.get(f["sev"], 0) + 1
    d.heading("Ringkasan", 1)
    d.para([("%d temuan: " % len(findings), {"bold": True}),
            (", ".join("%d %s" % (cnt[s], SEV_WORD[s].lower()) for s in ("ERROR", "WARNING", "UNVERIFIED", "INFO") if cnt.get(s))
             or "tidak ada temuan", {})])
    if summary_rows:
        sh = {}
        for i, r in enumerate(summary_rows, start=1):
            sh[(i, 1)] = SEV_FILL.get(r[1], "FFFFFF")
        d.table([("Aturan / standar", "Status", "Temuan", "Keterangan")] +
                [(a, (SEV_WORD.get(b, b), {"bold": True, "color": SEV_HEX.get(b, "161616")}), str(c), e) for a, b, c, e in summary_rows],
                widths_cm=[5.2, 3.0, 1.6, 7.0], shade=sh)
    d.para([("Cara memakai laporan ini: ", {"bold": True}),
            ("setiap temuan punya ID (mis. F-0001) yang sama dengan laporan HTML dan panel Navigator QC di QGIS. Gambar peta "
             "menyorot lokasi temuan dengan warna tingkatnya. Isi kolom catatan reviewer, lalu kirim dokumen ini bersama "
             "berkas desain.", {"color": "393939"})])
    d.page_break()
    d.heading("Rincian temuan", 1)
    for k, f in enumerate(findings[:max_findings]):
        sev = f["sev"]
        d.heading("%s  ·  %s" % (f["fid"], f.get("title") or ""), 2)
        val = ""
        if f.get("value") not in (None, ""):
            val = "%s%s" % (f["value"], (" " + f["unit"]) if f.get("unit") else "")
            if f.get("limit") not in (None, ""):
                val += "  (batas %s%s)" % (f["limit"], (" " + f["unit"]) if f.get("unit") else "")
        rows = [("Butir", "Isi"),
                ("Tingkat", (SEV_WORD.get(sev, sev), {"bold": True, "color": SEV_HEX.get(sev, "161616")})),
                ("Objek", f.get("obj") or "-"),
                ("Arti temuan", f.get("arti") or "-"),
                ("Yang perlu dilakukan", f.get("fix") or "-")]
        if val:
            rows.append(("Nilai", val))
        if f.get("lat") is not None:
            rows.append(("Lokasi (lat, lon)", ("%.6f, %.6f" % (f["lat"], f["lon"]), {"mono": True})))
        if f.get("dasar"):
            rows.append(("Dasar aturan", f["dasar"]))
        if f.get("source"):
            rows.append(("File sumber", (f["source"], {"mono": True})))
        rows.append(("Catatan reviewer", ""))
        d.table(rows, widths_cm=[4.2, 12.6], shade={(1, 1): SEV_FILL.get(sev, "FFFFFF")})
        img = images.get(f["fid"])
        if img:
            d.image(img, width_cm=15.5, caption="Gambar %s. Lokasi temuan disorot; skala batang di kiri bawah, utara ke atas." % f["fid"])
        if k < len(findings[:max_findings]) - 1 and (k + 1) % 2 == 0:
            d.page_break()
    if len(findings) > max_findings:
        d.para([("+%d temuan lain tidak dimuat di dokumen ini; daftar lengkap ada di laporan HTML/CSV." % (len(findings) - max_findings),
                 {"italic": True})])
    return d.save(path)

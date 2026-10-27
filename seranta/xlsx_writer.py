# -*- coding: utf-8 -*-
"""
Penulis .xlsx kecil tanpa pustaka tambahan (hanya zipfile + XML), cukup untuk daftar kerja reviewer:
beberapa sheet, baris judul tebal dan dibekukan, filter otomatis, lebar kolom, teks terbungkus,
tautan (HYPERLINK) dan daftar pilihan (data validation) untuk kolom status review.

Part of Seranta - FTTH Design Assistant.
Copyright (C) 2026 Joseph Edward Timothy Siahaan. Licensed under GPL-2.0-or-later (see LICENSE).
"""
import zipfile


def escape(text):
    """Escape karakter khusus XML (&, <, >) untuk isi sel dan atribut."""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

_NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" ' \
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'

# gaya: 0 biasa, 1 judul, 2 teks terbungkus, 3 angka 2 desimal, 4 tautan, 5 merah, 6 kuning, 7 abu, 8 biru, 9 hijau
_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="1"><numFmt numFmtId="164" formatCode="0.00"/></numFmts>
<fonts count="4"><font><sz val="10"/><name val="Calibri"/></font><font><b/><sz val="10"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
<font><u/><sz val="10"/><color rgb="FF2F6FB0"/><name val="Calibri"/></font><font><b/><sz val="10"/><name val="Calibri"/></font></fonts>
<fills count="8"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FF0F3D3E"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFFCECEA"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFFFF3DC"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFEDF1F6"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFEAF2FB"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFE6F4EC"/></patternFill></fill></fills>
<borders count="2"><border/><border><bottom style="thin"><color rgb="FFD9E2E0"/></bottom></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="10">
<xf numFmtId="0" fontId="0" fillId="0" borderId="1" applyBorder="1"><alignment vertical="top"/></xf>
<xf numFmtId="0" fontId="1" fillId="2" borderId="0" applyFont="1" applyFill="1"><alignment vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="0" fillId="0" borderId="1" applyBorder="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
<xf numFmtId="164" fontId="0" fillId="0" borderId="1" applyNumberFormat="1" applyBorder="1"><alignment vertical="top"/></xf>
<xf numFmtId="0" fontId="2" fillId="0" borderId="1" applyFont="1" applyBorder="1"><alignment vertical="top"/></xf>
<xf numFmtId="0" fontId="3" fillId="3" borderId="1" applyFont="1" applyFill="1"><alignment vertical="top"/></xf>
<xf numFmtId="0" fontId="3" fillId="4" borderId="1" applyFont="1" applyFill="1"><alignment vertical="top"/></xf>
<xf numFmtId="0" fontId="3" fillId="5" borderId="1" applyFont="1" applyFill="1"><alignment vertical="top"/></xf>
<xf numFmtId="0" fontId="3" fillId="6" borderId="1" applyFont="1" applyFill="1"><alignment vertical="top"/></xf>
<xf numFmtId="0" fontId="3" fillId="7" borderId="1" applyFont="1" applyFill="1"><alignment vertical="top"/></xf>
</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>"""

SEVERITY_STYLE = dict(zip(("ERROR", "WARNING", "UNVERIFIED", "INFO", "PASS"), range(5, 10)))


def _col(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _cell(ref, v, style=0):
    if v is None or v == "":
        return '<c r="%s" s="%d"/>' % (ref, style)
    if isinstance(v, bool):
        v = "ya" if v else "tidak"
    if isinstance(v, (int, float)):
        return '<c r="%s" s="%d"><v>%r</v></c>' % (ref, style, v)
    if isinstance(v, tuple) and v and v[0] == "=":           # ("=", formula, cached_text)
        return '<c r="%s" s="%d" t="str"><f>%s</f><v>%s</v></c>' % (ref, style, escape(v[1]), escape(str(v[2])))
    t = escape(str(v)).replace("\r", "")
    return '<c r="%s" s="%d" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' % (ref, style, t[:32000])


class Sheet(object):
    def __init__(self, name, headers, widths=None):
        self.name = name[:31]
        self.headers = list(headers)
        self.widths = widths or [16] * len(headers)
        self.rows = []                 # list of (values, styles)
        self.validations = []          # (col_index, [choices])

    def add(self, values, styles=None):
        self.rows.append((list(values), list(styles or [])))

    def choices(self, col_index, options):
        self.validations.append((col_index, list(options)))

    def xml(self):
        n = len(self.headers)
        last = _col(n - 1)
        out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>', '<worksheet %s>' % _NS,
               '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" '
               'state="frozen"/></sheetView></sheetViews>', '<cols>']
        for i, w in enumerate(self.widths):
            out.append('<col min="%d" max="%d" width="%s" customWidth="1"/>' % (i + 1, i + 1, w))
        out.append('</cols><sheetData>')
        out.append('<row r="1" ht="30" customHeight="1">%s</row>' % "".join(
            _cell("%s1" % _col(i), h, 1) for i, h in enumerate(self.headers)))
        for ri, (vals, sts) in enumerate(self.rows, start=2):
            out.append('<row r="%d">%s</row>' % (ri, "".join(
                _cell("%s%d" % (_col(i), ri), v, sts[i] if i < len(sts) and sts[i] is not None else
                      (3 if isinstance(v, float) else 2)) for i, v in enumerate(vals))))
        out.append('</sheetData>')
        if self.rows:
            out.append('<autoFilter ref="A1:%s%d"/>' % (last, len(self.rows) + 1))
        if self.validations and self.rows:
            out.append('<dataValidations count="%d">' % len(self.validations))
            for ci, opts in self.validations:
                c = _col(ci)
                out.append('<dataValidation type="list" allowBlank="1" showErrorMessage="1" sqref="%s2:%s%d">'
                           '<formula1>"%s"</formula1></dataValidation>' % (c, c, len(self.rows) + 1, escape(",".join(opts))))
            out.append('</dataValidations>')
        out.append('<pageSetup orientation="landscape" fitToWidth="1" fitToHeight="0"/></worksheet>')
        return "".join(out)


def write(path, sheets, title="", author=""):
    """sheets: [Sheet]. Menulis berkas .xlsx yang terbaca spreadsheet umum dan oleh pembaca xlsx Seranta."""
    wb = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>', '<workbook %s><sheets>' % _NS]
    rels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
    ct = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
          '<Default Extension="xml" ContentType="application/xml"/>',
          '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
          '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>',
          '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>']
    for i, sh in enumerate(sheets, start=1):
        wb.append('<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (escape(sh.name), i, i))
        rels.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                    'Target="worksheets/sheet%d.xml"/>' % (i, i))
        ct.append('<Override PartName="/xl/worksheets/sheet%d.xml" '
                  'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' % i)
    n = len(sheets)
    wb.append('</sheets></workbook>')
    rels.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
                'Target="styles.xml"/></Relationships>' % (n + 1))
    ct.append('</Types>')
    core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties '
            'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>%s</dc:title><dc:creator>%s</dc:creator></cp:coreProperties>'
            % (escape(title), escape(author)))
    root_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
                 'Target="xl/workbook.xml"/><Relationship Id="rId2" '
                 'Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" '
                 'Target="docProps/core.xml"/></Relationships>')
    tmp = path + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "".join(ct))
        z.writestr("_rels/.rels", root_rels)
        z.writestr("docProps/core.xml", core)
        z.writestr("xl/workbook.xml", "".join(wb))
        z.writestr("xl/_rels/workbook.xml.rels", "".join(rels))
        z.writestr("xl/styles.xml", _STYLES)
        for i, sh in enumerate(sheets, start=1):
            z.writestr("xl/worksheets/sheet%d.xml" % i, sh.xml())
    import os
    os.replace(tmp, path)
    return path

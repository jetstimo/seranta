# -*- coding: utf-8 -*-
"""
One-page HTML QC summary (traffic lights, BAKP reminder + checklist, output files, full log).

Part of Seranta - FTTH Design Assistant.
Copyright (C) 2026 Joseph Edward Timothy Siahaan. Licensed under GPL-2.0-or-later (see LICENSE).
"""
import html as _h
import os

_E = _h.escape
_ST = {True: ("OK", "ok"), False: ("CEK", "bad"), None: ("--", "na")}
_SEV = dict(zip(("ERROR", "WARNING", "INFO", "UNVERIFIED", "PASS", "CEK"), ("bad", "wrn", "inf", "unv", "ok", "bad")))
_SEVT = {"ERROR": "bad-t", "WARNING": "wrn-t", "CEK": "bad-t"}
SOFT_STD = {7}          # standar yang "tidak terpenuhi" berarti keputusan perencanaan, bukan kesalahan data

_CSS = """
:root{--ink:#14213d;--mut:#5b6474;--line:#dfe3ea;--ok:#1a7f37;--okb:#e7f5ea;--bad:#c62828;--badb:#fdecec;
--na:#6b7280;--nab:#f1f3f6;--warn:#8a5a00;--warnb:#fff4d6;--brand:#0B2A5B;--teal:#0E6E7E}
*{box-sizing:border-box}body{margin:0;font:14px/1.5 "Segoe UI",Roboto,Arial,sans-serif;color:var(--ink);background:#f6f7f9}
header{background:linear-gradient(120deg,var(--brand),var(--teal));color:#fff;padding:18px 24px}
header h1{margin:0;font-size:20px}header .sub{opacity:.85;font-size:13px}
main{max-width:1100px;margin:0 auto;padding:18px 16px 40px}
.card{background:#fff;border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin:14px 0}
h2{font-size:16px;margin:0 0 10px}
.warn{background:var(--warnb);border:2px solid #f2b705;color:var(--warn)}
.warn h2{color:var(--warn)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:10px}
.std{border-radius:10px;padding:10px 12px;border:1px solid var(--line)}
.std .t{font-weight:600}.std .v{font-size:12.5px;color:var(--mut)}
.std.ok{background:var(--okb);border-color:#b7e1c1}.std.bad{background:var(--badb);border-color:#f3b8b8}.std.na{background:var(--nab)}
.pill{display:inline-block;font-weight:700;font-size:11px;border-radius:99px;padding:1px 8px;margin-right:6px;color:#fff}
.pill.ok{background:var(--ok)}.pill.bad{background:var(--bad)}.pill.na{background:var(--na)}.pill.wrn{background:#e8590c}.pill.inf{background:#b08900}.pill.unv{background:#7c7c7c}
.wrn-t{color:#b54708}.small{font-size:12px;color:var(--mut)}
table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid var(--line);padding:7px 8px;text-align:left;vertical-align:top}
th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--mut)}
td input{transform:scale(1.25)}
ul{margin:6px 0 0 18px;padding:0}li{margin:2px 0}
.std .f{margin-top:8px;font-size:12.5px}.std .f ul{margin:4px 0 0 16px;padding:0}.std .f li{margin:2px 0;word-break:break-word}.go{font-size:11.5px;text-decoration:none;white-space:nowrap;margin-left:4px}.bad-t{color:var(--bad)}.na-t{color:var(--na)}
figure{display:inline-block;margin:6px;vertical-align:top;width:calc(50% - 14px);min-width:280px}
figure img{width:100%;border:1px solid var(--line);border-radius:6px}figcaption{font-size:12px;color:var(--mut);text-align:center}
pre{white-space:pre-wrap;font:12px/1.45 Consolas,monospace;background:#fbfbfc;border:1px solid var(--line);border-radius:8px;padding:10px;max-height:520px;overflow:auto}
.btn{display:inline-block;border:1px solid var(--line);background:#fff;border-radius:8px;padding:6px 12px;cursor:pointer;font:inherit}
.files code{background:#eef1f5;border-radius:4px;padding:1px 5px}
footer{font-size:11.5px;color:var(--mut);text-align:center;margin-top:18px}
@media print{.btn{display:none}body{background:#fff}.card{break-inside:avoid}}
"""


def build(path, meta, std, judul, extra_lines, bakp, files, full_text):
    """meta: dict(product, version, author, cluster, kode, cl_id, date, profile, qc_by_std, qc_counts, qc_params, refs,
    ref_dir, qc_profile_id, rule_version); std: {k: (ok, text)}, judul: {k: title}, bakp: dict dari bakp.check_cluster
    atau None, files: [(label, filename)], full_text: laporan teks lengkap."""
    try:
        from . import report_ui as U
        from . import penjelasan as X
    except ImportError:
        import report_ui as U
        import penjelasan as X
    U.reset_ids()
    by_std = meta.get("qc_by_std") or {}
    fid_map = meta.get("fid_map") or {}          # (kind, lon7, lat7, ket) -> F-0001 (sama dengan QC_TEMUAN & Word)
    snaps = meta.get("snaps") or {}              # F-0001 -> data URI gambar peta
    evid = meta.get("evidence") or {}            # F-0001 -> bukti terstruktur (aturan vs nilai, kutipan data sumber, jejak)
    counts = {}
    for st, _no, _lab, n, _ex, _src, _slug in (meta.get("qc_counts") or []):
        sv = "ERROR" if st == "CEK" else st
        counts[sv] = counts.get(sv, 0) + n

    def std_sev(k):
        ok = std.get(k, (None,))[0]
        if ok is True:
            return "PASS"
        if ok is None:
            return "UNVERIFIED"
        sevs = [t[0] for t in by_std.get(k, [])]
        # standar 7 (colo FDT) adalah keputusan perencanaan (FDT baru / bagi ke beberapa FDT), bukan kesalahan data
        return min(sevs, key=lambda v: U.SEV_ORDER.index(v) if v in U.SEV_ORDER else 9) if sevs else (
            "WARNING" if k in SOFT_STD else "ERROR")

    def finds(lst, limit=40):
        if not lst:
            return ""
        lis = []
        for t in lst[:limit]:
            sev, lab, ket, lat, lon = t[:5]
            kind = t[5] if len(t) > 5 else ""
            arti, aksi = X.tool1_kind_text(kind)
            fid = fid_map.get((kind, lon, lat, ket))
            lis.append(U.finding_li(sev, lab, "", ket, aksi, ("<code>%s</code> %s" % (_E(kind), _E(arti))) if kind else "",
                                    (lon, lat), fid=fid, snap=snaps.get(fid), ev=evid.get(fid)))
        more = ("<li class='more'>+%d titik lain. Semua titik ada di folder QC (QGIS), QC_TEMUAN.kmz dan panel Navigator QC.</li>"
                % (len(lst) - limit)) if len(lst) > limit else ""
        return "<ul class='finds'>%s%s</ul>" % ("".join(lis), more)

    keys = sorted(judul)
    order = sorted(keys, key=lambda k: (U.SEV_ORDER.index(std_sev(k)), k))
    cards, items = [], []
    for k in order:
        sev = std_sev(k)
        ex = X.TOOL1_STD.get(k, {})
        c = {}
        for t in by_std.get(k, []):
            c[t[0]] = c.get(t[0], 0) + 1
        if sev == "PASS" and not c:
            c = {}
        anchor = "s%d" % k
        items.append((anchor, "%d. %s" % (k, judul[k].split(" (")[0][:16]), sev))
        txt = str(std.get(k, (None, "-"))[1])
        cards.append(U.rule_card(anchor, sev, "%d. %s" % (k, judul[k]), U.plain(txt), c, ex.get("cek", ""), ex.get("alasan", ""),
                                 ex.get("tindakan", ""), finds(by_std.get(k, [])), is_open=sev in ("ERROR", "WARNING")))
    gen = by_std.get(0, [])
    if gen:
        c = {}
        for t in gen:
            c[t[0]] = c.get(t[0], 0) + 1
        sev = min(c, key=lambda v: U.SEV_ORDER.index(v) if v in U.SEV_ORDER else 9)
        items.append(("s0", "Jalur & tiang", sev))
        cards.append(U.rule_card(
            "s0", sev, "Jalur kabel dan tiang (pemeriksaan tambahan)", "%d temuan" % len(gen), c,
            "Ujung jalur, belokan dan percabangan tanpa tiang, tiang nganggur, kabel rendah, dan peluang efisiensi.",
            "Hal-hal ini tidak masuk standar review bernomor, tetapi menentukan apakah jalur bisa dibangun dengan rapi.",
            "Perbaiki yang berwarna merah/kuning; yang biru adalah saran penghematan.", finds(gen, 60),
            is_open=sev in ("ERROR", "WARNING")))
    extra = "".join("<li>%s</li>" % _E(x.strip()) for x in extra_lines if x.strip())
    sec = []
    if extra:
        sec.append("<section class='block'><h2>Catatan tambahan</h2><div class='stat'><ul>%s</ul></div></section>" % extra)
    qcc = meta.get("qc_counts") or []
    if qcc:
        rows = "".join("<tr><td>%s</td><td>%s</td><td>%s<br><code>QC/%s.shp</code></td><td class='n'>%d</td><td>%s</td>"
                       "<td>%s</td></tr>" % (U.chip("ERROR" if st == "CEK" else st), no or "-", _E(lab), _E(slug), n, _E(ex_),
                                            _E(srcs)) for st, no, lab, n, ex_, srcs, slug in qcc)
        sec.append("<section class='block'><h2>Ringkasan semua jenis temuan</h2><p class='lead'>Satu baris per jenis temuan. "
                   "Lokasi tiap titik ada di folder <code>QC</code> (satu layer per jenis). Di QGIS, panel <b>Navigator QC</b> "
                   "membawa peta langsung ke titik temuan. Untuk aplikasi peta lain pakai <code>QC_TEMUAN.kmz</code>.</p>"
                   "<div class='scroll'><table><tr><th>Tingkat</th><th>Std</th><th>Jenis dan file</th><th class='n'>Jumlah</th>"
                   "<th>Contoh</th><th>Dasar aturan</th></tr>%s</table></div></section>" % rows)
    refs = meta.get("refs") or []
    if meta.get("ref_dir"):
        rr = "".join("<tr><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            U.chip("PASS", "ada") if fl_ else U.chip("ERROR", "tidak ada"), _E(lab), _E(", ".join(fl_)) if fl_ else "-")
            for lab, fl_ in refs)
        hint = "" if (refs and refs[0][1]) else ("<div class='unvbox'><b>Funnel tidak ditemukan.</b> Tanpa file Funnel, standar 2 "
                                                 "dan 5 tidak dicek. Tambahkan file Funnel ke folder referensi.</div>")
        sec.append("<section class='block'><h2>Data referensi yang dipakai</h2><p class='lead'>Folder <code>%s</code></p>"
                   "<div class='scroll'><table><tr><th>Status</th><th>Data</th><th>File</th></tr>%s</table></div>%s</section>"
                   % (_E(meta["ref_dir"]), rr, hint))
    else:
        sec.append("<section class='block'><h2>Data referensi belum dipilih</h2><div class='unvbox'><b>Beberapa standar belum bisa "
                   "dicek.</b> Isian folder referensi kosong, sehingga Funnel (standar 2 dan 5), jaringan existing (6 dan 7) dan "
                   "data wilayah (3) tidak dicek. Pilih folder referensi tim di isian 2 lalu jalankan ulang.</div></section>")
    bk_html = ""
    if bakp is not None:
        fname = os.path.basename(bakp.get("file") or "") or "Belum ada. Minta BAKP ke vendor survei."
        its = "".join("<li>%s</li>" % _E(U.plain(t)) for _k, o, t in bakp.get("items", []))
        rows = "".join("<tr><td><input type='checkbox' data-k='%d' aria-label='Sudah dicek'></td><td><b>%s</b></td><td>%s</td>"
                       "<td>%s</td></tr>" % (i, _E(a), _E(str(b)), _E(c)) for i, (a, b, c) in enumerate(bakp.get("checklist", [])))
        imgs = "".join("<figure style='margin:8px 0'><img style='max-width:100%%;border:1px solid var(--line);border-radius:8px' "
                       "src='data:image/jpeg;base64,%s' alt='BAKP halaman %s'><figcaption class='src'>BAKP halaman %s</figcaption>"
                       "</figure>" % (b64, no, no) for no, b64 in bakp.get("pages", []))
        bk_html = ("<section class='block' id='bakp'><h2>Periksa BAKP sebelum desain dikirim</h2><p class='lead'>File: <b>%s</b>. "
                   "Bandingkan isian tulisan tangan di BAKP dengan nilai seharusnya, lalu centang. Centang tersimpan di browser ini."
                   "</p>%s<div class='scroll'><table><tr><th>Sudah</th><th>Butir</th><th>Nilai seharusnya</th><th>Catatan</th></tr>"
                   "%s</table></div><p id='bk-done' style='font-weight:600'></p>%s</section>" % (
                       _E(fname), ("<div class='stat'><ul>%s</ul></div>" % its) if its else "", rows,
                       ("<details class='plain'><summary>Lihat halaman BAKP</summary>%s</details>" % imgs) if imgs else ""))
    sec.append(bk_html)
    prm = meta.get("qc_params") or []
    if prm:
        rows_p = "".join("<tr><td><code>%s</code></td><td class='n'>%s %s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            _E(k), _E(str(v)), _E(u or ""), _E(d), _E(src), U.chip("PASS", "disahkan") if st == "APPROVED"
            else U.chip("UNVERIFIED", "parameter rekayasa")) for k, v, u, d, src, st in prm)
        sec.append("<section class='block'><details class='plain'><summary>Profil standar %s (versi aturan %s): dasar setiap "
                   "angka</summary><div class='scroll'><table><tr><th>Parameter</th><th class='n'>Nilai</th><th>Dasar</th>"
                   "<th>Sumber</th><th>Status</th></tr>%s</table></div></details></section>" % (
                       _E(meta.get("qc_profile_id", "")), _E(meta.get("rule_version", "")), rows_p))
    fl = "".join("<tr><td>%s</td><td><code>%s</code></td></tr>" % (_E(a), _E(b)) for a, b in files)
    sec.append("<section class='block'><h2>File input untuk desain otomatis</h2><p class='lead'>Semua file ada di folder yang sama "
               "dengan laporan ini.</p><div class='scroll'><table><tr><th>Isi</th><th>File</th></tr>%s</table></div></section>" % fl)
    sec.append("<section class='block'><details class='plain'><summary>Laporan lengkap (teks)</summary><pre>%s</pre></details>"
               "</section>" % _E(full_text))
    n_bad = sum(1 for k in keys if std_sev(k) in ("ERROR", "WARNING"))
    n_unv = sum(1 for k in keys if std_sev(k) == "UNVERIFIED")
    if n_bad:
        verdict = "<b>%d dari %d standar review perlu dicek</b> sebelum data dipakai untuk desain%s." % (
            n_bad, len(keys), (", dan %d belum bisa dicek" % n_unv) if n_unv else "")
    elif n_unv:
        verdict = "Tidak ada pelanggaran, tetapi <b>%d standar belum bisa dicek</b> karena datanya belum ada." % n_unv
    else:
        verdict = "Semua %d standar review terpenuhi. Data siap dipakai untuk desain." % len(keys)
    js = """<script>(function(){var key="seranta-bakp-"+%s,boxes=[].slice.call(document.querySelectorAll("input[data-k]"));
function load(){try{return JSON.parse(localStorage.getItem(key)||"{}")}catch(e){return {}}}
function save(s){try{localStorage.setItem(key,JSON.stringify(s))}catch(e){}}
function upd(){var n=boxes.filter(function(b){return b.checked}).length,el=document.getElementById("bk-done");
if(el){el.textContent=n===boxes.length&&n?"Semua butir BAKP sudah dicek.":(n+" dari "+boxes.length+" butir sudah dicek.");}}
var s=load();boxes.forEach(function(b){b.checked=!!s[b.dataset.k];b.addEventListener("change",function(){s[b.dataset.k]=b.checked;save(s);upd();});});upd();})();
</script>""" % repr(str(meta.get("kode", "")) + "-" + os.path.basename((bakp or {}).get("file") or ""))
    doc = U.page("QC %s" % meta.get("kode", ""), "QC data survei sebelum desain", meta.get("cluster", ""), verdict,
                 [("Kode cluster", meta.get("kode", "")), ("ID", meta.get("cl_id", "")), ("Dibuat", meta.get("date", "")),
                  ("Profil desain", meta.get("profile", "")), ("Alat", "%s v%s" % (meta.get("product", ""), meta.get("version", "")))],
                 counts, items, (meta.get("map_html") or "") + U.howto() + "".join(cards) + "".join(sec),
                 "%s v%s. &copy; 2026 %s, GPL-2.0-or-later. Hasil QC adalah alat bantu; keputusan desain tetap pada desainer "
                 "dan reviewer." % (_E(meta.get("product", "")), _E(meta.get("version", "")), _E(meta.get("author", ""))),
                 run_key=str(meta.get("kode", "")), word_href=meta.get("word"))
    doc = doc.replace("</body>", js + "</body>")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc)
    return path

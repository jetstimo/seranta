# -*- coding: utf-8 -*-
"""
Komponen tampilan bersama untuk semua laporan HTML Seranta (tool 1, 3, 4).

Prinsip desain:
  * Satu kalimat keputusan di atas (apa yang harus dilakukan pembaca), lalu "jalur aturan": setiap aturan
    digambar sebagai tiang di sepanjang satu kabel, berwarna menurut statusnya. Klik tiang = lompat ke aturan.
  * Setiap aturan menjawab tiga pertanyaan: apa yang dicek, kenapa penting, apa yang perlu dilakukan.
  * Setiap temuan ditulis dalam bahasa sederhana dulu, detail teknis di bawahnya.
  * Berkas mandiri: huruf (Inter, Poppins; SIL Open Font License) tertanam, tanpa internet, bisa dicetak.

Part of Seranta - FTTH Design Assistant.
Copyright (C) 2026 Joseph Edward Timothy Siahaan. Licensed under GPL-2.0-or-later (see LICENSE).
"""
import base64
import html as _h
import os

E = _h.escape
HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(HERE, "assets", "fonts")

SEV_ORDER = ("ERROR", "WARNING", "UNVERIFIED", "INFO", "PASS")
SEV_CLS = {"ERROR": "err", "WARNING": "wrn", "UNVERIFIED": "unv", "INFO": "inf", "PASS": "ok",
           "CEK": "err", "OK": "ok", "--": "unv", None: "unv"}
SEV_WORD = {"ERROR": "Wajib diperbaiki", "WARNING": "Perlu ditinjau", "UNVERIFIED": "Belum bisa dicek",
            "INFO": "Catatan", "PASS": "Lolos"}

_FONT_CACHE = []


def font_css():
    """@font-face dengan huruf tertanam (base64) agar tampilan sama di komputer mana pun, tanpa internet."""
    if _FONT_CACHE:
        return _FONT_CACHE[0]
    out = []
    for fam, fn, w in (("Inter", "inter-400.woff", 400), ("Inter", "inter-600.woff", 600),
                       ("Poppins", "poppins-500.woff", 500), ("Poppins", "poppins-700.woff", 700)):
        p = os.path.join(FONT_DIR, fn)
        if os.path.isfile(p):
            with open(p, "rb") as fh:
                b = base64.b64encode(fh.read()).decode("ascii")
            out.append("@font-face{font-family:'%s';font-weight:%d;font-style:normal;font-display:swap;"
                       "src:url(data:font/woff;base64,%s) format('woff')}" % (fam, w, b))
    _FONT_CACHE.append("\n".join(out))
    return _FONT_CACHE[0]


CSS = r"""
:root{
 --paper:#F6F8F7;--sheet:#FFFFFF;--ink:#13302F;--ink2:#46605E;--mute:#6E8280;--line:#D9E2E0;--line2:#EAF0EE;
 --deep:#0F3D3E;--fiber:#12A4A8;
 --err:#C2362F;--err-bg:#FCECEA;--wrn:#B86E00;--wrn-bg:#FFF3DC;--unv:#5B6B82;--unv-bg:#EDF1F6;
 --inf:#2F6FB0;--inf-bg:#EAF2FB;--ok:#23854A;--ok-bg:#E6F4EC;
 --r-lg:16px;--r-md:10px;--shadow:0 1px 2px rgba(15,61,62,.06),0 8px 24px -12px rgba(15,61,62,.18);
 --sans:'Inter',"Segoe UI",system-ui,-apple-system,Roboto,Arial,sans-serif;
 --head:'Poppins','Inter',"Segoe UI",system-ui,sans-serif;
}
@media (prefers-color-scheme:dark){:root{
 --paper:#0E1A1A;--sheet:#132424;--ink:#E4EFED;--ink2:#B4C8C5;--mute:#8CA3A0;--line:#2A4140;--line2:#1C3231;
 --deep:#0A2C2D;--err-bg:#3A1C1A;--wrn-bg:#3A2C10;--unv-bg:#212C3A;--inf-bg:#16283C;--ok-bg:#163223;
 --err:#F07B72;--wrn:#F2B54A;--unv:#A9B7CC;--inf:#7DB2EA;--ok:#6DCB93;--shadow:none}}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.6 var(--sans);font-feature-settings:"tnum" 1;
 -webkit-font-smoothing:antialiased}
a{color:var(--inf)}
h1,h2,h3{font-family:var(--head);line-height:1.25;margin:0;letter-spacing:-.01em}
h1{font-size:30px;font-weight:700}h2{font-size:20px;font-weight:700}h3{font-size:15.5px;font-weight:500}
p{margin:.4em 0}
code{font-family:"Cascadia Mono",Consolas,"DejaVu Sans Mono",monospace;font-size:.88em;background:var(--line2);
 padding:1px 6px;border-radius:5px}
.wrap{max-width:1020px;margin:0 auto;padding:0 20px}

/* ---------- kepala ---------- */
.top{background:var(--deep);color:#EAF6F5;padding:34px 0 0;position:relative;overflow:hidden}
.top .tool{font:500 14px var(--head);color:#9FD9D6}
.top h1{color:#fff;margin:6px 0 4px;max-width:30ch}
.top .verdict{font-size:18px;max-width:60ch;margin:14px 0 4px;color:#fff}
.top .verdict b{font-weight:600}
.meta{display:flex;flex-wrap:wrap;gap:6px 22px;margin:14px 0 0;font-size:13px;color:#B9DCD9}
.meta div span{display:block;color:#7FB7B3;font-size:12px}
.meta div b{font-weight:600;color:#F1FBFA}
.tally{display:flex;flex-wrap:wrap;gap:10px;margin:20px 0 0}
.tally button{all:unset;cursor:pointer;display:flex;align-items:baseline;gap:8px;padding:8px 14px;border-radius:999px;
 background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.14);color:#fff;font-size:14px}
.tally button b{font:700 20px var(--head)}
.tally button:hover,.tally button:focus-visible{background:rgba(255,255,255,.16)}
.tally button[aria-pressed=true]{background:#fff;color:var(--deep)}
.tally .dot{width:10px;height:10px;border-radius:50%;align-self:center}

/* ---------- jalur aturan (kabel + tiang) ---------- */
.route{position:relative;margin:28px 0 0;padding:0 0 26px}
.route .cable{position:absolute;left:8px;right:8px;top:21px;height:4px;border-radius:4px;
 background:linear-gradient(90deg,var(--fiber),#5FD1C9)}
.route ol{list-style:none;margin:0;padding:0;display:flex;justify-content:space-between;position:relative;gap:4px}
.route li{flex:1 1 0;min-width:0;display:flex;flex-direction:column;align-items:center;text-align:center}
.route a{text-decoration:none;color:#CDEBE8;display:flex;flex-direction:column;align-items:center;gap:6px;font-size:11.5px;
 line-height:1.25;padding:0 2px;border-radius:8px}
.route a:focus-visible{outline:2px solid #fff;outline-offset:3px}
.route .pole{width:18px;height:18px;border-radius:50%;margin-top:14px;border:3px solid var(--deep);box-shadow:0 0 0 2px currentColor}
.route .pole.err{background:var(--err);color:var(--err)}.route .pole.wrn{background:#F2A21B;color:#F2A21B}
.route .pole.unv{background:#9AA9BD;color:#9AA9BD}.route .pole.inf{background:#5D9BDB;color:#5D9BDB}
.route .pole.ok{background:#35B36A;color:#35B36A}
.route .lbl{max-width:11ch;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.route a:hover .lbl{color:#fff}
.route .lbl.quiet{visibility:hidden}.route a:hover .lbl.quiet,.route a:focus-visible .lbl.quiet{visibility:visible}
.route .rcap{margin:14px 0 0;font-size:12.5px;color:#8FC3BF}

/* ---------- isi ---------- */
main{padding:26px 0 60px}
.block{background:var(--sheet);border:1px solid var(--line);border-radius:var(--r-lg);padding:20px 22px;margin:18px 0;
 box-shadow:var(--shadow)}
.block>h2{margin-bottom:8px}
.lead{color:var(--ink2);max-width:72ch}
.howto{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin-top:12px}
.howto div{border-left:4px solid;padding:4px 0 4px 12px}
.howto b{display:block;font-family:var(--head);font-weight:500}
.howto small{color:var(--ink2);font-size:13px;line-height:1.45;display:block}
.howto .err{border-color:var(--err)}.howto .wrn{border-color:var(--wrn)}.howto .unv{border-color:var(--unv)}
.howto .inf{border-color:var(--inf)}
.howto.kpi{grid-template-columns:repeat(auto-fit,minmax(140px,1fr))}
td b{white-space:nowrap}.howto .ok{border-color:var(--ok)}

.tools{position:sticky;top:0;z-index:5;background:var(--paper);padding:12px 0;display:flex;flex-wrap:wrap;gap:10px;
 align-items:center;border-bottom:1px solid var(--line)}
.tools input{flex:1 1 240px;font:inherit;padding:9px 14px;border-radius:999px;border:1px solid var(--line);
 background:var(--sheet);color:var(--ink)}
.tools input:focus{outline:2px solid var(--fiber);outline-offset:1px}
.btn{font:500 13.5px var(--sans);padding:8px 14px;border-radius:999px;border:1px solid var(--line);background:var(--sheet);
 color:var(--ink);cursor:pointer}
.btn:hover{border-color:var(--fiber)}.btn:focus-visible{outline:2px solid var(--fiber);outline-offset:2px}

/* kartu aturan */
.rule{background:var(--sheet);border:1px solid var(--line);border-radius:var(--r-lg);margin:14px 0;overflow:hidden;
 border-left:6px solid var(--unv)}
.rule.err{border-left-color:var(--err)}.rule.wrn{border-left-color:var(--wrn)}.rule.inf{border-left-color:var(--inf)}
.rule.ok{border-left-color:var(--ok)}.rule.unv{border-left-color:var(--unv)}
.rule>summary{list-style:none;cursor:pointer;padding:16px 20px;display:grid;grid-template-columns:auto 1fr auto;gap:4px 14px;
 align-items:center}
.rule>summary::-webkit-details-marker{display:none}
.rule>summary:focus-visible{outline:2px solid var(--fiber);outline-offset:-2px}
.rule>summary h3{font-size:16.5px}
.rule>summary .sub{grid-column:2/4;color:var(--ink2);font-size:13.5px}
.rule>summary .chev{width:22px;height:22px;border-radius:50%;display:grid;place-items:center;background:var(--line2);
 transition:transform .2s;font-size:12px;color:var(--ink2)}
.rule[open]>summary .chev{transform:rotate(90deg)}
.count{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}
.chip{display:inline-flex;align-items:center;gap:6px;font:600 12.5px var(--sans);padding:3px 10px;border-radius:999px;
 white-space:nowrap}
.chip.err{background:var(--err-bg);color:var(--err)}.chip.wrn{background:var(--wrn-bg);color:var(--wrn)}
.chip.unv{background:var(--unv-bg);color:var(--unv)}.chip.inf{background:var(--inf-bg);color:var(--inf)}
.chip.ok{background:var(--ok-bg);color:var(--ok)}
.chip i{width:8px;height:8px;border-radius:50%;background:currentColor;display:inline-block}
.rbody{padding:0 20px 18px}
.why{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;padding:14px 0 6px;border-top:1px solid var(--line2)}
.why div b{display:block;font:500 13px var(--head);color:var(--mute);margin-bottom:2px}
.why div p{margin:0;font-size:14px;line-height:1.5}
.stat{margin:10px 0 2px;padding:10px 14px;background:var(--line2);border-radius:var(--r-md);font-size:14px}
.stat li{margin:2px 0}.stat ul{margin:0;padding-left:18px}
.unvbox{margin:10px 0;padding:10px 14px;border-radius:var(--r-md);background:var(--unv-bg);color:var(--ink);font-size:14px}
.unvbox b{color:var(--unv)}
.src{font-size:12.5px;color:var(--mute);margin-top:8px}

/* daftar temuan */
.finds{list-style:none;margin:12px 0 0;padding:0;border-top:1px solid var(--line2)}
.finds>li{display:grid;grid-template-columns:4px 1fr auto;gap:0 14px;padding:12px 0;border-bottom:1px solid var(--line2)}
.finds>li .bar{border-radius:4px;background:var(--unv)}
.finds>li.err .bar{background:var(--err)}.finds>li.wrn .bar{background:var(--wrn)}.finds>li.inf .bar{background:var(--inf)}
.finds .t{font-weight:600}
.finds .t .obj{font-weight:400;color:var(--ink2)}
.finds .a{margin:2px 0;color:var(--ink)}
.finds .fix{margin:2px 0;color:var(--ink2)}
.finds .fix::before{content:"Yang perlu dilakukan: ";font-weight:600;color:var(--ink)}
.finds details{margin-top:4px;font-size:12.5px;color:var(--mute)}
.finds details summary{cursor:pointer;width:max-content}
.finds .side{display:flex;flex-direction:column;align-items:flex-end;gap:6px}
.map{font-size:13px;text-decoration:none;border:1px solid var(--line);border-radius:999px;padding:3px 10px;white-space:nowrap;
 color:var(--ink)}
.map:hover{border-color:var(--fiber)}
.more{padding:10px 0;color:var(--mute);font-size:13.5px}
.hide{display:none!important}

table{border-collapse:collapse;width:100%;font-size:14px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line2);vertical-align:top}
th{font:500 12.5px var(--head);color:var(--mute)}
td.n,th.n{text-align:right}
.scroll{overflow-x:auto}
details.plain>summary{cursor:pointer;font:500 15px var(--head)}
pre{white-space:pre-wrap;font:12px/1.5 "Cascadia Mono",Consolas,monospace;background:var(--line2);border-radius:var(--r-md);
 padding:12px;max-height:520px;overflow:auto}
footer{color:var(--mute);font-size:12.5px;padding:24px 0;border-top:1px solid var(--line)}
.empty{padding:22px;text-align:center;color:var(--ink2)}

@media (max-width:720px){
 h1{font-size:24px}.why{grid-template-columns:1fr}.route .lbl{display:none}
 .rule>summary{grid-template-columns:auto 1fr}.count{grid-column:1/3;justify-content:flex-start}
 .finds>li{grid-template-columns:4px 1fr}.finds .side{grid-column:2;align-items:flex-start;flex-direction:row}}
@media (prefers-reduced-motion:reduce){*{transition:none!important;scroll-behavior:auto!important}}
@media print{
 body{background:#fff;font-size:12px}.tools,.tally,.route,.btn{display:none!important}
 .top{background:#fff;color:#000;padding-top:0}.top h1,.top .verdict{color:#000}.meta,.meta div b,.top .tool{color:#333}
 .rule,.block{break-inside:avoid;box-shadow:none}.hide{display:block!important}
 details>*{display:block}}
"""

JS = r"""
(function(){
 var q=document.getElementById('q'),bt=[].slice.call(document.querySelectorAll('[data-sev]')),act={};
 function apply(){
  var t=(q&&q.value||'').toLowerCase().trim(),any=Object.keys(act).some(function(k){return act[k]});
  document.querySelectorAll('.rule').forEach(function(r){
   var shown=0;
   r.querySelectorAll('.finds>li[data-s]').forEach(function(li){
    var ok=(!any||act[li.dataset.s])&&(!t||li.textContent.toLowerCase().indexOf(t)>=0);
    li.classList.toggle('hide',!ok);if(ok)shown++;});
   var head=r.textContent.toLowerCase(),rs=r.dataset.s;
   var keep=(!any&&!t)||shown>0||((!any||act[rs])&&t&&r.querySelector('summary').textContent.toLowerCase().indexOf(t)>=0)
     ||(any&&!t&&act[rs]&&!r.querySelector('.finds'));
   r.classList.toggle('hide',!keep);if((any||t)&&shown>0)r.open=true;});
 }
 bt.forEach(function(b){b.addEventListener('click',function(){var s=b.dataset.sev;act[s]=!act[s];
  bt.filter(function(x){return x.dataset.sev===s}).forEach(function(x){x.setAttribute('aria-pressed',act[s]?'true':'false')});apply();});});
 if(q)q.addEventListener('input',apply);
 var ex=document.getElementById('xall');
 if(ex)ex.addEventListener('click',function(){var r=[].slice.call(document.querySelectorAll('.rule')),o=!r.every(function(d){return d.open});
  r.forEach(function(d){d.open=o});ex.textContent=o?'Tutup semua':'Buka semua';});
 window.addEventListener('beforeprint',function(){document.querySelectorAll('details').forEach(function(d){d.open=true})});
})();
"""


def plain(t):
    """Buang awalan kode mesin (UNVERIFIED_BOM: ...) dari kalimat untuk pembaca."""
    import re
    t = re.sub(r"\bUNVERIFIED(?:_[A-Z]+)?:\s*", "", str(t or ""))
    return (t[:1].upper() + t[1:]) if t else t


def chip(sev, text=None):
    c = SEV_CLS.get(sev, "unv")
    return "<span class='chip %s'><i></i>%s</span>" % (c, E(text if text is not None else SEV_WORD.get(sev, str(sev))))


def map_link(lon, lat):
    return ("<a class='map' target='_blank' rel='noopener' title='Buka lokasi di OpenStreetMap' "
            "href='https://www.openstreetmap.org/?mlat=%.7f&amp;mlon=%.7f#map=19/%.7f/%.7f'>Lihat di peta</a>"
            % (lat, lon, lat, lon))


def meta_list(pairs):
    return "<div class='meta'>%s</div>" % "".join(
        "<div><span>%s</span><b>%s</b></div>" % (E(k), E(str(v))) for k, v in pairs if v not in (None, ""))


def tally(counts):
    """Tombol jumlah temuan per tingkat (sekaligus filter)."""
    col = {"ERROR": "#F07B72", "WARNING": "#F2B54A", "UNVERIFIED": "#A9B7CC", "INFO": "#7DB2EA"}
    out = []
    for s in ("ERROR", "WARNING", "UNVERIFIED", "INFO"):
        n = counts.get(s, 0)
        out.append("<button type='button' data-sev='%s' aria-pressed='false' title='Tampilkan hanya: %s'>"
                   "<span class='dot' style='background:%s'></span><b>%d</b>%s</button>" % (
                       s, SEV_WORD[s], col[s], n, E(SEV_WORD[s].lower())))
    return "<div class='tally'>%s</div>" % "".join(out)


def route(items):
    """items: [(anchor_id, label, sev)]. Jalur kabel dengan satu tiang per aturan."""
    if not items:
        return ""
    li = "".join("<li><a href='#%s' title='%s: %s'><span class='pole %s'></span><span class='lbl%s'>%s</span></a></li>" % (
        E(a), E(lab), E(SEV_WORD.get(s, s)), SEV_CLS.get(s, "unv"), " quiet" if s == "PASS" else "", E(lab))
        for a, lab, s in items)
    n_ok = sum(1 for _a, _l, s in items if s == "PASS")
    return ("<nav class='route' aria-label='Jalur aturan'><div class='cable'></div><ol>%s</ol>"
            "<p class='rcap'>Setiap titik adalah satu aturan (%d aturan, %d lolos). Klik titik untuk melompat ke penjelasannya.</p>"
            "</nav>" % (li, len(items), n_ok))


def howto():
    rows = [("err", "Wajib diperbaiki", "Melanggar batas tegas. Perbaiki atau catat pengecualian yang disetujui."),
            ("wrn", "Perlu ditinjau", "Di atas batas anjuran. Periksa, beri alasan bila dipertahankan."),
            ("unv", "Belum bisa dicek", "Data pendukung belum ada. Bukan tanda lolos."),
            ("inf", "Catatan", "Saran efisiensi atau kerapian. Tidak wajib."),
            ("ok", "Lolos", "Dicek dengan data lengkap, tidak ada temuan.")]
    return ("<section class='block'><h2>Cara membaca laporan ini</h2><p class='lead'>Setiap aturan di bawah menjelaskan "
            "<b>apa yang dicek</b>, <b>kenapa penting</b>, dan <b>apa yang perlu dilakukan</b>. Setiap temuan ditulis dalam "
            "kalimat biasa; angka dan kode teknis ada di bagian <i>Detail teknis</i>. Warna menunjukkan tingkat:</p>"
            "<div class='howto'>%s</div></section>" % "".join(
                "<div class='%s'><b>%s</b><small>%s</small></div>" % (c, E(t), E(d)) for c, t, d in rows))


def toolbar(placeholder="Cari kode perangkat, tiang, atau kata kunci"):
    return ("<div class='tools'><input id='q' type='search' placeholder='%s' aria-label='Cari temuan'>"
            "<button class='btn' id='xall' type='button'>Buka semua</button>"
            "<button class='btn' type='button' onclick='window.print()'>Cetak atau simpan PDF</button></div>" % E(placeholder))


def finding_li(sev, title, obj, arti, fix, tech="", lonlat=None, extra=""):
    side = map_link(*lonlat) if lonlat else ""
    return ("<li class='%s' data-s='%s'><span class='bar'></span><div><div class='t'>%s%s</div>"
            "<p class='a'>%s</p>%s%s%s</div><div class='side'>%s%s</div></li>" % (
                SEV_CLS.get(sev, "unv"), E(sev), E(title), (" <span class='obj'>%s</span>" % E(obj)) if obj else "",
                E(arti), ("<p class='fix'>%s</p>" % E(fix)) if fix else "", extra,
                ("<details><summary>Detail teknis</summary>%s</details>" % tech) if tech else "", chip(sev), side))


def rule_card(anchor, sev, title, subtitle, counts, cek, alasan, tindakan, inner="", is_open=False):
    cnt = "".join(chip(s, "%d %s" % (counts[s], SEV_WORD[s].lower())) for s in SEV_ORDER if counts.get(s))
    if not cnt:
        cnt = chip(sev)
    why = ""
    if cek or alasan or tindakan:
        why = "<div class='why'>%s</div>" % "".join(
            "<div><b>%s</b><p>%s</p></div>" % (E(h), E(t)) for h, t in (
                ("Yang dicek", cek), ("Kenapa penting", alasan), ("Bila ada temuan", tindakan)) if t)
    return ("<details class='rule %s' id='%s' data-s='%s'%s><summary><span class='chev' aria-hidden='true'>&#9654;</span>"
            "<h3>%s</h3><span class='count'>%s</span><span class='sub'>%s</span></summary><div class='rbody'>%s%s</div></details>"
            % (SEV_CLS.get(sev, "unv"), E(anchor), E(sev), " open" if is_open else "", E(title), cnt, E(subtitle or ""),
               why, inner))


def page(title, tool_name, heading, verdict_html, meta_pairs, counts, route_items, body, footer_html, with_tools=True):
    return """<!doctype html><html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>%s</title>
<style>%s%s</style></head><body>
<header class="top"><div class="wrap"><div class="tool">%s</div><h1>%s</h1><p class="verdict">%s</p>%s%s%s</div></header>
<main><div class="wrap">%s%s</div></main>
<footer><div class="wrap">%s</div></footer><script>%s</script></body></html>""" % (
        E(title), font_css(), CSS, E(tool_name), E(heading), verdict_html, meta_list(meta_pairs),
        tally(counts) if counts is not None else "", route(route_items),
        toolbar() if with_tools else "", body, footer_html, JS)


def verdict_sentence(counts, n_rules=None):
    """Satu kalimat keputusan untuk pembaca."""
    e, w, u, i = (counts.get(k, 0) for k in ("ERROR", "WARNING", "UNVERIFIED", "INFO"))
    parts = []
    if e:
        parts.append("<b>%d hal wajib diperbaiki</b>" % e)
    if w:
        parts.append("<b>%d perlu ditinjau</b>" % w)
    if u:
        parts.append("%d aturan belum bisa dicek karena datanya belum ada" % u)
    if not parts:
        return "Semua aturan dijalankan dengan data lengkap dan tidak ada yang perlu diperbaiki%s." % (
            " (ada %d catatan saran)" % i if i else "")
    s = ", ".join(parts[:-1]) + (" dan " if len(parts) > 1 else "") + parts[-1]
    lead = "Desain belum siap dikirim: " if e else ("Desain hampir siap: " if w else "Belum dapat dinyatakan lolos: ")
    return lead + s + "."

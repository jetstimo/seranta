# -*- coding: utf-8 -*-
"""
Komponen tampilan bersama untuk semua laporan HTML Seranta (tool 1, 3, 4).

Prinsip desain:
  * Satu kalimat keputusan di atas (apa yang harus dilakukan pembaca), lalu "jalur aturan": setiap aturan
    digambar sebagai tiang di sepanjang satu kabel, berwarna menurut statusnya. Klik tiang = lompat ke aturan.
  * Setiap aturan menjawab tiga pertanyaan: apa yang dicek, kenapa penting, apa yang perlu dilakukan.
  * Setiap temuan ditulis dalam bahasa sederhana dulu, detail teknis di bawahnya.
  * Berkas mandiri: huruf Inter (SIL Open Font License) tertanam, tanpa internet, bisa dicetak.
  * Interaktif: ID tetap per temuan + tautan langsung (#F-0001), pintasan keyboard, status 'sudah dicek' di browser,
    gambar peta per temuan yang bisa diperbesar, unduh laporan Word dan rekap review.

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
SEV_CLS = dict(zip(("ERROR", "WARNING", "UNVERIFIED", "INFO", "PASS", "CEK", "OK", "--", None),
                   ("err", "wrn", "unv", "inf", "ok", "err", "ok", "unv", "unv")))
SEV_WORD = dict(zip(SEV_ORDER, ("Wajib diperbaiki", "Perlu ditinjau", "Belum bisa dicek", "Catatan", "Lolos")))

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
/* Token desain: gaya sistem desain perusahaan besar (netral merek), kontras WCAG 2.2 AA. */
:root{
 --paper:#F4F4F4;--sheet:#FFFFFF;--ink:#161616;--ink2:#525252;--mute:#6F6F6F;--line:#E0E0E0;--line2:#F2F4F8;
 --deep:#161616;--deep2:#262626;--accent:#0F62FE;--accent-bg:#EDF5FF;--fiber:#0F62FE;
 --err:#DA1E28;--err-bg:#FFF1F1;--wrn:#BA4E00;--wrn-bg:#FFF2E8;--unv:#6F6F6F;--unv-bg:#F4F4F4;
 --inf:#0043CE;--inf-bg:#EDF5FF;--ok:#198038;--ok-bg:#DEFBE6;
 --r-lg:8px;--r-md:6px;--shadow:0 1px 2px rgba(0,0,0,.06);
 --sans:'Inter',"Segoe UI",system-ui,-apple-system,Roboto,Arial,sans-serif;
 --head:'Inter',"Segoe UI",system-ui,sans-serif;
 --mono:"Cascadia Mono",Consolas,"DejaVu Sans Mono",ui-monospace,monospace;
}
@media (prefers-color-scheme:dark){:root{
 --paper:#161616;--sheet:#262626;--ink:#F4F4F4;--ink2:#C6C6C6;--mute:#A8A8A8;--line:#393939;--line2:#2E2E2E;
 --deep:#0B0B0B;--deep2:#1C1C1C;--accent:#78A9FF;--accent-bg:#1C2B44;
 --err:#FA4D56;--err-bg:#3A1A1C;--wrn:#FF832B;--wrn-bg:#3A2614;--unv:#A8A8A8;--unv-bg:#2E2E2E;
 --inf:#78A9FF;--inf-bg:#1C2B44;--ok:#42BE65;--ok-bg:#16301F;--shadow:none}}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--paper);color:var(--ink);font:14px/1.55 var(--sans);font-feature-settings:"tnum" 1;
 -webkit-font-smoothing:antialiased}
a{color:var(--accent)}
h1,h2,h3{font-family:var(--head);line-height:1.25;margin:0;letter-spacing:-.005em}
h1{font-size:28px;font-weight:600}h2{font-size:20px;font-weight:600}h3{font-size:15px;font-weight:600}
p{margin:.4em 0}
code{font-family:var(--mono);font-size:.86em;background:var(--line2);padding:1px 5px;border-radius:4px}
.wrap{max-width:1180px;margin:0 auto;padding:0 24px}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}

/* ---------- kepala ---------- */
.top{background:var(--deep);color:#F4F4F4;padding:22px 0 0;border-bottom:4px solid var(--accent)}
.top .tool{font:600 12px var(--sans);letter-spacing:.08em;text-transform:uppercase;color:#A8A8A8}
.top h1{color:#fff;margin:6px 0 2px;max-width:40ch}
.top .verdict{font-size:16px;max-width:80ch;margin:10px 0 2px;color:#E0E0E0}
.top .verdict b{font-weight:600;color:#fff}
.meta{display:flex;flex-wrap:wrap;gap:6px 26px;margin:14px 0 0;font-size:13px;color:#C6C6C6}
.meta div span{display:block;color:#8D8D8D;font-size:11.5px;text-transform:uppercase;letter-spacing:.04em}
.meta div b{font-weight:600;color:#F4F4F4}
.tally{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1px;margin:18px 0 0;background:#393939;
 border:1px solid #393939}
.tally button{all:unset;cursor:pointer;display:flex;flex-direction:column;gap:2px;padding:12px 16px;background:var(--deep2);color:#C6C6C6;
 font-size:12.5px;border-top:3px solid transparent}
.tally button b{font:600 26px var(--sans);color:#fff;letter-spacing:-.01em}
.tally button:hover{background:#333}
.tally button:focus-visible{outline:2px solid #fff;outline-offset:-2px}
.tally button[aria-pressed=true]{background:#F4F4F4;color:#161616}.tally button[aria-pressed=true] b{color:#161616}
.tally .dot{display:none}
.tally button[data-sev=ERROR]{border-top-color:#FA4D56}.tally button[data-sev=WARNING]{border-top-color:#FF832B}
.tally button[data-sev=UNVERIFIED]{border-top-color:#A8A8A8}.tally button[data-sev=INFO]{border-top-color:#78A9FF}

/* ---------- jalur aturan (kabel + tiang) ---------- */
.route{position:relative;margin:20px 0 0;padding:0 0 18px}
.route .cable{position:absolute;left:8px;right:8px;top:21px;height:3px;background:#525252}
.route ol{list-style:none;margin:0;padding:0;display:flex;justify-content:space-between;position:relative;gap:4px}
.route li{flex:1 1 0;min-width:0;display:flex;flex-direction:column;align-items:center;text-align:center}
.route a{text-decoration:none;color:#C6C6C6;display:flex;flex-direction:column;align-items:center;gap:6px;font-size:11px;
 line-height:1.25;padding:0 2px;border-radius:4px}
.route a:focus-visible{outline:2px solid #fff;outline-offset:3px}
.route .pole{width:16px;height:16px;border-radius:50%;margin-top:14px;border:3px solid var(--deep);box-shadow:0 0 0 2px currentColor}
.route .pole.err{background:#FA4D56;color:#FA4D56}.route .pole.wrn{background:#FF832B;color:#FF832B}
.route .pole.unv{background:#A8A8A8;color:#A8A8A8}.route .pole.inf{background:#78A9FF;color:#78A9FF}
.route .pole.ok{background:#42BE65;color:#42BE65}
.route .lbl{max-width:11ch;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.route a:hover .lbl{color:#fff}
.route .lbl.quiet{visibility:hidden}.route a:hover .lbl.quiet,.route a:focus-visible .lbl.quiet{visibility:visible}
.route .rcap{margin:12px 0 0;font-size:12px;color:#A8A8A8}

/* ---------- isi ---------- */
main{padding:20px 0 60px}
.block{background:var(--sheet);border:1px solid var(--line);border-radius:var(--r-lg);padding:18px 20px;margin:16px 0;
 box-shadow:var(--shadow)}
.block>h2{margin-bottom:8px}
.lead{color:var(--ink2);max-width:80ch}
.howto{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin-top:12px}
.howto div{border-left:4px solid;padding:4px 0 4px 12px}
.howto b{display:block;font-weight:600}
.howto small{color:var(--ink2);font-size:12.5px;line-height:1.45;display:block}
.howto .err{border-color:var(--err)}.howto .wrn{border-color:var(--wrn)}.howto .unv{border-color:var(--unv)}
.howto .inf{border-color:var(--inf)}.howto .ok{border-color:var(--ok)}
.howto.kpi{grid-template-columns:repeat(auto-fit,minmax(140px,1fr))}
td b{white-space:nowrap}
kbd{font:600 11px var(--mono);border:1px solid var(--line);border-bottom-width:2px;border-radius:4px;padding:0 5px;background:var(--sheet)}

.tools{position:sticky;top:0;z-index:20;background:var(--paper);padding:10px 0;display:flex;flex-wrap:wrap;gap:8px;
 align-items:center;border-bottom:1px solid var(--line)}
.tools input[type=search]{flex:1 1 200px;min-width:180px;font:inherit;padding:8px 12px;border-radius:0;border:0;border-bottom:2px solid var(--mute);
 background:var(--sheet);color:var(--ink)}
.tools input[type=search]:focus{outline:2px solid var(--accent);outline-offset:-2px}
.tools .prog{font-size:12.5px;color:var(--ink2);white-space:nowrap}
.tools .prog b{color:var(--ink)}
.tools label.tg{display:flex;align-items:center;gap:6px;font-size:13px;color:var(--ink2);cursor:pointer}
.btn{font:500 13px var(--sans);padding:7px 12px;border-radius:0;border:1px solid var(--line);background:var(--sheet);
 color:var(--ink);cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;gap:6px;white-space:nowrap}
.btn:hover{border-color:var(--accent);color:var(--accent)}
.btn.pri{background:var(--accent);border-color:var(--accent);color:#fff}.btn.pri:hover{filter:brightness(1.08);color:#fff}

/* kartu aturan */
.rule{background:var(--sheet);border:1px solid var(--line);border-radius:var(--r-lg);margin:12px 0;overflow:hidden;
 border-left:5px solid var(--unv)}
.rule.err{border-left-color:var(--err)}.rule.wrn{border-left-color:var(--wrn)}.rule.inf{border-left-color:var(--inf)}
.rule.ok{border-left-color:var(--ok)}.rule.unv{border-left-color:var(--unv)}
.rule>summary{list-style:none;cursor:pointer;padding:14px 18px;display:grid;grid-template-columns:auto 1fr auto;gap:4px 14px;
 align-items:center}
.rule>summary::-webkit-details-marker{display:none}
.rule>summary:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}
.rule>summary h3{font-size:16px}
.rule>summary .sub{grid-column:2/4;color:var(--ink2);font-size:13px}
.rule>summary .chev{width:22px;height:22px;display:grid;place-items:center;transition:transform .15s;font-size:11px;color:var(--ink2)}
.rule[open]>summary .chev{transform:rotate(90deg)}
.count{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}
.chip{display:inline-flex;align-items:center;gap:6px;font:600 12px var(--sans);padding:2px 8px;border-radius:999px;
 white-space:nowrap;border:1px solid transparent}
.chip.err{background:var(--err-bg);color:var(--err);border-color:var(--err)}.chip.wrn{background:var(--wrn-bg);color:var(--wrn);border-color:var(--wrn)}
.chip.unv{background:var(--unv-bg);color:var(--unv);border-color:var(--unv)}.chip.inf{background:var(--inf-bg);color:var(--inf);border-color:var(--inf)}
.chip.ok{background:var(--ok-bg);color:var(--ok);border-color:var(--ok)}
.chip i{width:7px;height:7px;border-radius:50%;background:currentColor;display:inline-block}
.chip.err i{border-radius:1px;transform:rotate(45deg)}.chip.wrn i{width:0;height:0;border-radius:0;background:none;
 border-left:4px solid transparent;border-right:4px solid transparent;border-bottom:7px solid currentColor}
.rbody{padding:0 18px 16px}
.why{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;padding:12px 0 6px;border-top:1px solid var(--line)}
.why div b{display:block;font:600 11.5px var(--sans);text-transform:uppercase;letter-spacing:.04em;color:var(--mute);margin-bottom:2px}
.why div p{margin:0;font-size:13.5px;line-height:1.5}
.stat{margin:10px 0 2px;padding:10px 14px;background:var(--line2);border-radius:var(--r-md);font-size:13.5px}
.stat li{margin:2px 0}.stat ul{margin:0;padding-left:18px}
.unvbox{margin:10px 0;padding:10px 14px;border-left:3px solid var(--unv);background:var(--unv-bg);color:var(--ink);font-size:13.5px}
.unvbox b{color:var(--ink)}
.src{font-size:12px;color:var(--mute);margin-top:8px}

/* daftar temuan */
.finds{list-style:none;margin:12px 0 0;padding:0;border-top:1px solid var(--line)}
.finds>li{display:grid;grid-template-columns:4px 1fr auto;gap:0 14px;padding:12px 8px 12px 0;border-bottom:1px solid var(--line);
 scroll-margin-top:70px;transition:background .2s}
.finds>li .bar{background:var(--unv)}
.finds>li.err .bar{background:var(--err)}.finds>li.wrn .bar{background:var(--wrn)}.finds>li.inf .bar{background:var(--inf)}
.finds>li.cur{background:var(--accent-bg)}
.finds>li.flash{animation:fl 1.6s ease-out}
@keyframes fl{0%{background:#FFF1C7}100%{background:transparent}}
.finds>li.done .t,.finds>li.done .a{opacity:.62}
.finds .fid{font:600 11.5px var(--mono);color:var(--ink2);background:var(--line2);padding:1px 6px;border-radius:3px;margin-right:6px;
 text-decoration:none}
.finds .fid:hover{color:var(--accent)}
.finds .t{font-weight:600}
.finds .t .obj{font-weight:400;color:var(--ink2)}
.finds .a{margin:2px 0;color:var(--ink)}
.finds .fix{margin:2px 0;color:var(--ink2)}
.finds .fix::before{content:"Yang perlu dilakukan: ";font-weight:600;color:var(--ink)}
.finds details{margin-top:4px;font-size:12px;color:var(--mute)}
.finds details summary{cursor:pointer;width:max-content}
.finds .side{display:flex;flex-direction:column;align-items:flex-end;gap:6px}
.finds .acts{display:flex;gap:4px;flex-wrap:wrap;justify-content:flex-end}
.finds .acts .btn{padding:3px 8px;font-size:12px}
.finds label.rv{display:flex;gap:6px;align-items:center;font-size:12px;color:var(--ink2);cursor:pointer}
.shot{margin:8px 0 2px;display:block;max-width:420px;border:1px solid var(--line);cursor:zoom-in;background:var(--sheet)}
.shot img{display:block;width:100%;height:auto}
.map{font-size:12px;text-decoration:none;border:1px solid var(--line);padding:3px 8px;white-space:nowrap;color:var(--ink)}
.map:hover{border-color:var(--accent);color:var(--accent)}
.more{padding:10px 0;color:var(--mute);font-size:13px}
.hide{display:none!important}

table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{font:600 12px var(--sans);color:var(--ink2);background:var(--line2)}
td.n,th.n{text-align:right}
.scroll{overflow-x:auto}
details.plain>summary{cursor:pointer;font:600 15px var(--head)}
pre{white-space:pre-wrap;font:12px/1.5 var(--mono);background:var(--line2);border-radius:var(--r-md);padding:12px;max-height:520px;overflow:auto}
footer{color:var(--mute);font-size:12px;padding:24px 0;border-top:1px solid var(--line)}
.empty{padding:22px;text-align:center;color:var(--ink2)}
dialog.lb{border:0;padding:0;max-width:min(1100px,96vw);background:var(--sheet);color:var(--ink)}
dialog.lb::backdrop{background:rgba(0,0,0,.72)}
dialog.lb img{display:block;max-width:100%;max-height:78vh}
dialog.lb .bar2{display:flex;gap:8px;align-items:center;justify-content:space-between;padding:8px 12px;font-size:13px}
dialog.help ul{margin:8px 0;padding-left:18px}dialog.help{max-width:520px;padding:18px 22px}
.toast{position:fixed;bottom:18px;left:50%;transform:translateX(-50%);background:#161616;color:#fff;padding:8px 14px;font-size:13px;
 opacity:0;transition:opacity .2s;pointer-events:none;z-index:50}.toast.on{opacity:1}

@media (max-width:760px){
 h1{font-size:22px}.why{grid-template-columns:1fr}.route .lbl{display:none}
 .rule>summary{grid-template-columns:auto 1fr}.count{grid-column:1/3;justify-content:flex-start}
 .finds>li{grid-template-columns:4px 1fr}.finds .side{grid-column:2;align-items:flex-start;flex-direction:row;flex-wrap:wrap}}
@media (prefers-reduced-motion:reduce){*{transition:none!important;scroll-behavior:auto!important;animation:none!important}}
@media print{
 body{background:#fff;font-size:11.5px;color:#000}.tools,.tally,.route,.btn,.acts,label.rv,.toast{display:none!important}
 .top{background:#fff;color:#000;padding-top:0;border-bottom:2px solid #000}.top h1,.top .verdict,.top .verdict b{color:#000}
 .meta,.meta div b,.top .tool{color:#333}
 .rule,.block,.finds>li{break-inside:avoid;box-shadow:none}.hide{display:block!important}.shot{max-width:320px}
 details>*{display:block}}
"""

JS = r"""
(function(){
 var KEY='seranta-review-'+(document.body.dataset.run||document.title);
 function ld(){try{return JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){return {}}}
 function sv(o){try{localStorage.setItem(KEY,JSON.stringify(o))}catch(e){}}
 var rev=ld(),q=document.getElementById('q'),only=document.getElementById('undone'),
     bt=[].slice.call(document.querySelectorAll('[data-sev]')),act={},cur=-1;
 function toast(t){var el=document.getElementById('toast');if(!el)return;el.textContent=t;el.classList.add('on');
  clearTimeout(el._t);el._t=setTimeout(function(){el.classList.remove('on')},1600);}
 function copy(t){try{navigator.clipboard.writeText(t).then(function(){toast('Disalin')},fb)}catch(e){fb()}
  function fb(){var a=document.createElement('textarea');a.value=t;document.body.appendChild(a);a.select();
   try{document.execCommand('copy');toast('Disalin')}catch(e){}document.body.removeChild(a);}}
 function items(){return [].slice.call(document.querySelectorAll('.finds>li[data-fid]'))}
 function visible(){return items().filter(function(li){return !li.classList.contains('hide')&&!li.closest('.rule.hide')})}
 function prog(){var all=items(),d=all.filter(function(li){return rev[li.dataset.fid]}).length,el=document.getElementById('prog');
  if(el)el.innerHTML='<b>'+d+'</b>/'+all.length+' dicek';}
 function paint(li){var on=!!rev[li.dataset.fid];li.classList.toggle('done',on);var c=li.querySelector('input.rvc');if(c)c.checked=on;}
 function apply(){
  var t=(q&&q.value||'').toLowerCase().trim(),any=Object.keys(act).some(function(k){return act[k]}),u=only&&only.checked;
  document.querySelectorAll('.rule').forEach(function(r){
   var shown=0;
   r.querySelectorAll('.finds>li[data-s]').forEach(function(li){
    var ok=(!any||act[li.dataset.s])&&(!t||li.textContent.toLowerCase().indexOf(t)>=0)&&(!u||!rev[li.dataset.fid]);
    li.classList.toggle('hide',!ok);if(ok)shown++;});
   var rs=r.dataset.s,filt=any||t||u;
   var keep=!filt||shown>0||((!any||act[rs])&&t&&r.querySelector('summary').textContent.toLowerCase().indexOf(t)>=0)
     ||(any&&!t&&!u&&act[rs]&&!r.querySelector('.finds'));
   r.classList.toggle('hide',!keep);if(filt&&shown>0)r.open=true;});
 }
 bt.forEach(function(b){b.addEventListener('click',function(){var s=b.dataset.sev;act[s]=!act[s];
  bt.filter(function(x){return x.dataset.sev===s}).forEach(function(x){x.setAttribute('aria-pressed',act[s]?'true':'false')});apply();});});
 if(q)q.addEventListener('input',apply);if(only)only.addEventListener('change',apply);
 items().forEach(function(li){paint(li);var c=li.querySelector('input.rvc');
  if(c)c.addEventListener('change',function(){if(c.checked)rev[li.dataset.fid]=new Date().toISOString().slice(0,16);
   else delete rev[li.dataset.fid];sv(rev);paint(li);prog();if(only&&only.checked)apply();});});
 prog();
 document.addEventListener('click',function(e){var b=e.target.closest('[data-copy]');if(b){e.preventDefault();
   var v=b.dataset.copy;if(v==='link'){var li=b.closest('li[data-fid]');v=location.href.split('#')[0]+'#'+li.id;}copy(v);}});
 var ex=document.getElementById('xall');
 if(ex)ex.addEventListener('click',function(){var r=[].slice.call(document.querySelectorAll('.rule')),o=!r.every(function(d){return d.open});
  r.forEach(function(d){d.open=o});ex.textContent=o?'Tutup semua':'Buka semua';});
 var xr=document.getElementById('xrev');
 if(xr)xr.addEventListener('click',function(){var rows=[['ID','Tingkat','Judul','Objek','Sudah dicek','Waktu']];
  items().forEach(function(li){var t=li.querySelector('.t');rows.push([li.dataset.fid,li.dataset.s,(t?t.childNodes[1]?t.childNodes[1].textContent:t.textContent:'').trim(),
   (li.querySelector('.obj')||{}).textContent||'',rev[li.dataset.fid]?'ya':'belum',rev[li.dataset.fid]||'']);});
  var csv=rows.map(function(r){return r.map(function(c){return '"'+String(c).replace(/"/g,'""')+'"'}).join(';')}).join('\r\n');
  var a=document.createElement('a');a.href=URL.createObjectURL(new Blob(['﻿'+csv],{type:'text/csv'}));
  a.download=(document.body.dataset.run||'review')+'_REVIEW.csv';document.body.appendChild(a);a.click();a.remove();});
 // pratinjau gambar
 var lb=document.getElementById('lb'),lbi=lb&&lb.querySelector('img'),lbc=lb&&lb.querySelector('.cap'),shots=[],si=0;
 function openShot(i){shots=[].slice.call(document.querySelectorAll('.shot img')).filter(function(im){return !im.closest('.hide')});
  if(!shots.length||!lb)return;si=(i+shots.length)%shots.length;lbi.src=shots[si].src;lbc.textContent=shots[si].alt;
  if(!lb.open)lb.showModal();}
 document.addEventListener('click',function(e){var a=e.target.closest('.shot');if(a){e.preventDefault();
  var all=[].slice.call(document.querySelectorAll('.shot img')).filter(function(im){return !im.closest('.hide')});
  openShot(all.indexOf(a.querySelector('img')));}});
 if(lb){lb.querySelector('[data-prev]').onclick=function(){openShot(si-1)};lb.querySelector('[data-next]').onclick=function(){openShot(si+1)};
  lb.querySelector('[data-close]').onclick=function(){lb.close()};lb.addEventListener('click',function(e){if(e.target===lb)lb.close()});}
 // tautan langsung #ID
 function go(id,flash){var el=id&&document.getElementById(id);if(!el)return;var d=el.closest('details');while(d){d.open=true;d=d.parentElement.closest('details');}
  el.scrollIntoView({block:'center'});if(flash&&el.matches('li')){el.classList.remove('flash');void el.offsetWidth;el.classList.add('flash');}}
 window.addEventListener('hashchange',function(){go(location.hash.slice(1),true)});
 if(location.hash)setTimeout(function(){go(location.hash.slice(1),true)},60);
 // keyboard
 function sel(i){var v=visible();if(!v.length)return;cur=Math.max(0,Math.min(v.length-1,i));items().forEach(function(li){li.classList.remove('cur')});
  var li=v[cur];li.classList.add('cur');var d=li.closest('details');if(d)d.open=true;li.scrollIntoView({block:'center'});
  history.replaceState(null,'','#'+li.id);}
 document.addEventListener('keydown',function(e){
  if(lb&&lb.open){if(e.key==='ArrowRight')openShot(si+1);if(e.key==='ArrowLeft')openShot(si-1);return;}
  var tag=(e.target.tagName||'').toLowerCase();if(tag==='input'||tag==='textarea'||tag==='select'){if(e.key==='Escape'){e.target.blur();
   if(q&&e.target===q){q.value='';apply();}}return;}
  if(e.ctrlKey||e.metaKey||e.altKey)return;
  var v=visible(),li=v[cur];
  if(e.key==='j'){sel(cur+1);e.preventDefault();}else if(e.key==='k'){sel(cur-1);e.preventDefault();}
  else if(e.key==='/'){if(q){q.focus();e.preventDefault();}}
  else if(e.key==='x'&&li){var c=li.querySelector('input.rvc');if(c){c.click();}}
  else if(e.key==='g'&&li){var im=li.querySelector('.shot');if(im)im.click();}
  else if(e.key==='o'&&li){var m=li.querySelector('a.map');if(m)window.open(m.href,'_blank','noopener');}
  else if(e.key==='?'){var h=document.getElementById('help');if(h)h.showModal();}});
 var hb=document.getElementById('hbtn');if(hb)hb.onclick=function(){document.getElementById('help').showModal()};
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
    return ("<a class='map' target='_blank' rel='noopener' title='Buka lokasi di OpenStreetMap (butuh internet)' "
            "href='https://www.openstreetmap.org/?mlat=%.7f&amp;mlon=%.7f#map=19/%.7f/%.7f'>Lihat di peta</a>"
            % (lat, lon, lat, lon))


def meta_list(pairs):
    return "<div class='meta'>%s</div>" % "".join(
        "<div><span>%s</span><b>%s</b></div>" % (E(k), E(str(v))) for k, v in pairs if v not in (None, ""))


def tally(counts):
    """Ubin KPI jumlah temuan per tingkat (sekaligus filter)."""
    out = []
    for s in ("ERROR", "WARNING", "UNVERIFIED", "INFO"):
        n = counts.get(s, 0)
        out.append("<button type='button' data-sev='%s' aria-pressed='false' title='Tampilkan hanya: %s'>"
                   "<b>%d</b>%s</button>" % (s, SEV_WORD[s], n, E(SEV_WORD[s])))
    return "<div class='tally' role='group' aria-label='Saring menurut tingkat'>%s</div>" % "".join(out)


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
    return ("<section class='block'><h2>Cara memakai laporan ini</h2><p class='lead'>Setiap aturan menjelaskan "
            "<b>apa yang dicek</b>, <b>kenapa penting</b>, dan <b>apa yang perlu dilakukan</b>. Setiap temuan punya ID "
            "(mis. <code>F-0001</code>) yang sama dengan laporan Word, tabel temuan dan panel Navigator QC di QGIS; klik ID "
            "untuk menyalin tautan langsung ke temuan itu. Centang <i>Sudah dicek</i> untuk menandai temuan yang selesai "
            "ditinjau (tersimpan di browser ini; unduh rekapnya dengan tombol <i>Rekap review</i>). Tekan <kbd>?</kbd> "
            "untuk pintasan keyboard. Warna menunjukkan tingkat:</p>"
            "<div class='howto'>%s</div></section>" % "".join(
                "<div class='%s'><b>%s</b><small>%s</small></div>" % (c, E(t), E(d)) for c, t, d in rows))


def toolbar(placeholder="Cari ID temuan, kode perangkat, tiang, atau kata kunci", word_href=None):
    return ("<div class='tools'><input id='q' type='search' placeholder='%s' aria-label='Cari temuan'>"
            "<label class='tg'><input type='checkbox' id='undone'> Belum dicek</label>"
            "<span class='prog' id='prog' aria-live='polite'></span>"
            "<button class='btn' id='xall' type='button'>Buka semua</button>%s"
            "<button class='btn' id='xrev' type='button' title='Unduh rekap status review (CSV)'>Rekap review</button>"
            "<button class='btn' type='button' onclick='window.print()'>Cetak / PDF</button>"
            "<button class='btn' id='hbtn' type='button' aria-label='Bantuan pintasan keyboard'>?</button></div>" % (
                E(placeholder),
                ("<a class='btn pri' href='%s' download title='Laporan Word berisi gambar peta setiap temuan'>"
                 "Unduh laporan Word</a>" % E(word_href)) if word_href else ""))


def finding_li(sev, title, obj, arti, fix, tech="", lonlat=None, extra="", fid=None, snap=None):
    """Satu temuan. fid: ID tetap (F-0001 / ID temuan alat 4) untuk tautan langsung, review dan laporan Word;
    snap: data URI gambar peta temuan (opsional)."""
    fid = fid or next_id()
    side = map_link(*lonlat) if lonlat else ""
    acts = ("<div class='acts'><button class='btn' type='button' data-copy='link' title='Salin tautan langsung ke temuan ini'>"
            "Salin tautan</button>%s</div>" % (
                ("<button class='btn' type='button' data-copy='%.6f, %.6f' title='Salin koordinat lat, lon'>Koordinat</button>"
                 % (lonlat[1], lonlat[0])) if lonlat else ""))
    shot = ("<a class='shot' href='#' title='Perbesar gambar (G)'><img loading='lazy' src='%s' alt='%s %s'></a>"
            % (snap, E(fid), E(title))) if snap else ""
    return ("<li class='%s' id='%s' data-fid='%s' data-s='%s'><span class='bar'></span><div><div class='t'>"
            "<a class='fid' href='#%s' data-copy='link' title='Salin tautan'>%s</a>%s%s</div>"
            "<p class='a'>%s</p>%s%s%s%s</div><div class='side'>%s%s<label class='rv'><input type='checkbox' class='rvc'> "
            "Sudah dicek</label>%s</div></li>" % (
                SEV_CLS.get(sev, "unv"), E(fid), E(fid), E(sev), E(fid), E(fid), E(title),
                (" <span class='obj'>%s</span>" % E(obj)) if obj else "",
                E(arti), ("<p class='fix'>%s</p>" % E(fix)) if fix else "", extra, shot,
                ("<details><summary>Detail teknis</summary>%s</details>" % tech) if tech else "", chip(sev), side, acts))


_IDS = [0]


def reset_ids():
    _IDS[0] = 0


def next_id():
    _IDS[0] += 1
    return "F-%04d" % _IDS[0]


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


_DIALOGS = ("<dialog class='lb' id='lb' aria-label='Gambar temuan'><img alt=''><div class='bar2'><span class='cap'></span>"
            "<span><button class='btn' type='button' data-prev>&larr; Sebelumnya</button> <button class='btn' type='button' "
            "data-next>Berikutnya &rarr;</button> <button class='btn' type='button' data-close>Tutup</button></span></div></dialog>"
            "<dialog class='help' id='help'><h3>Pintasan keyboard</h3><ul><li><kbd>j</kbd> / <kbd>k</kbd> temuan berikutnya / "
            "sebelumnya</li><li><kbd>x</kbd> tandai sudah dicek</li><li><kbd>g</kbd> perbesar gambar peta</li><li><kbd>o</kbd> "
            "buka lokasi di peta online</li><li><kbd>/</kbd> cari &nbsp; <kbd>Esc</kbd> keluar dari kotak cari</li></ul>"
            "<form method='dialog'><button class='btn'>Tutup</button></form></dialog><div class='toast' id='toast' role='status'></div>")


def page(title, tool_name, heading, verdict_html, meta_pairs, counts, route_items, body, footer_html, with_tools=True,
         run_key="", word_href=None):
    return """<!doctype html><html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>%s</title>
<style>%s%s</style></head><body data-run="%s">
<header class="top"><div class="wrap"><div class="tool">%s</div><h1>%s</h1><p class="verdict">%s</p>%s%s%s</div></header>
<main><div class="wrap">%s%s</div></main>
<footer><div class="wrap">%s</div></footer>%s<script>%s</script></body></html>""" % (
        E(title), font_css(), CSS, E(run_key or title), E(tool_name), E(heading), verdict_html, meta_list(meta_pairs),
        tally(counts) if counts is not None else "", route(route_items),
        toolbar(word_href=word_href) if with_tools else "", body, footer_html, _DIALOGS, JS)


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

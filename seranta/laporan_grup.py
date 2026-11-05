# -*- coding: utf-8 -*-
"""
Seranta - FTTH Design Assistant
Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later.

LAPORAN HTML GABUNGAN (grup 1 PIC desain / cluster berdampingan / satu batch)
-----------------------------------------------------------------------------
Satu berkas HTML mandiri untuk beberapa cluster sekaligus, agar reviewer tidak membuka laporan satu per satu:
  * ringkasan grup (status, total HP/splitter/FDT, tiang yang tercatat di dua cluster, hubungan antar cluster);
  * tabel REMARKS per cluster: remarks otomatis + kolom REMARKS TAMBAHAN reviewer + pilihan status, dirangkai menjadi
    remarks final dengan penghitung 255 karakter dan tombol salin (isian tersimpan di browser ini);
  * rincian setiap cluster (standar review 1-9, daftar temuan ber-ID F-0001 yang sama dengan laporan per cluster);
  * tombol UNDUH WORD: satu .docx berisi semua cluster beserta remarks final dan catatan reviewer (dibuat di browser,
    tanpa internet, tanpa pustaka luar), tombol CSV remarks dan cetak/PDF.
Modul murni Python (tanpa QGIS) agar bisa diuji otomatis. Masukan: hasil per cluster dari alat 1 (dict _run_cluster).
"""
import html as _h
import json
import os
import re

try:
    from . import report_ui as _ui
except ImportError:          # diuji tanpa paket
    import report_ui as _ui

E = _h.escape
MAX_LEN = 255
PREFIX = {"REJECT": "Reject:", "APPROVE DENGAN CATATAN": "Approve dgn catatan:", "APPROVE": "Approve"}
STD_TITLE = {1: "Jarak HP ke tiang", 2: "Boundary RFS / funnel / cluster lain", 3: "Wilayah HPDB vs FINDIM",
             4: "HPDB vs KMZ + HP duplikat", 5: "HP di luar boundary Funnel", 6: "Status desain cluster",
             7: "Bisa colo FDT", 8: "BAKP (izin warga)", 9: "Jarak tiang ke tiang NP"}
ID_RX = re.compile(r"(?<!\d)(\d{9,12})(?!\d)")


def _sid(r):
    if r.get("cl_id"):
        return str(r["cl_id"])
    m = ID_RX.search(r.get("label") or "")
    if m:
        return m.group(1)
    try:
        from .remarks import short_label
    except ImportError:
        from remarks import short_label
    return short_label(r.get("label")) if r.get("label") else "?"


def _body(text):
    """Isi remarks tanpa awalan status ('Reject: ...' -> '...')."""
    t = (text or "").strip()
    for p in ("Approve dgn catatan:", "Reject:", "Approve"):
        if t.startswith(p):
            return t[len(p):].strip()
    return t


def _rel(target, base_dir):
    if not target:
        return ""
    try:
        return os.path.relpath(target, base_dir).replace(os.sep, "/")
    except ValueError:            # beda drive di Windows
        return "file:///" + os.path.abspath(target).replace(os.sep, "/")


def member_data(r, base_dir):
    """Ringkas hasil satu cluster menjadi data JSON untuk laporan gabungan."""
    rm = r.get("remarks") or {}
    st = rm.get("status") or ("BELUM DIJALANKAN" if r.get("missing") else "-")
    return {
        "id": _sid(r), "label": r.get("label") or "", "hp": r.get("hp"), "poles": r.get("poles"),
        "status": st, "auto": rm.get("text") or "", "body": _body(rm.get("text")),
        "notes": list(rm.get("notes") or []), "dropped": list(rm.get("dropped") or []),
        "kmz_only": bool(r.get("kmz_only")), "missing": bool(r.get("missing")),
        "colo": r.get("colo") or "", "bakp": r.get("bakp") or "", "qc": r.get("qc") or "",
        "std": [list(x) for x in (r.get("std_rows") or [])],
        "find": list(r.get("findings") or []),
        "html": _rel(r.get("laporan"), base_dir), "word": _rel(r.get("word"), base_dir),
        "dir": r.get("dir") or "",
    }


def _std_chip(ok):
    return _ui.chip({True: "PASS", False: "ERROR", None: "UNVERIFIED"}.get(ok, "UNVERIFIED"),
                    {True: "OK", False: "CEK", None: "--"}.get(ok, "--"))


def _status_chip(st):
    sev = "ERROR" if st == "REJECT" else ("WARNING" if st.startswith("APPROVE DENGAN") else
                                          ("PASS" if st == "APPROVE" else "UNVERIFIED"))
    return _ui.chip(sev, st.title() if st not in ("-",) else "Belum dicek")


def _sev_chip(sev):
    return _ui.chip(sev, {"ERROR": "Error", "WARNING": "Warning", "INFO": "Info", "UNVERIFIED": "Belum dicek"}.get(sev, sev))


CSS = r"""
.wrap{max-width:1240px}
.rtab{width:100%;border-collapse:collapse;font-size:13.5px}
.rtab th{background:var(--line2);text-align:left;font:600 12px var(--sans);text-transform:uppercase;letter-spacing:.04em;
 color:var(--ink2);padding:8px 10px;border-bottom:1px solid var(--line)}
.rtab td{padding:10px;border-bottom:1px solid var(--line);vertical-align:top}
.rtab tr:last-child td{border-bottom:0}
.rtab .cl b{display:block;font-weight:600}.rtab .cl small{color:var(--mute)}
.auto{font-size:13px;color:var(--ink2);white-space:pre-wrap}
textarea.add{width:100%;min-height:58px;font:13px var(--sans);padding:8px;border:1px solid var(--line);resize:vertical;
 border-radius:6px;box-sizing:border-box;background:#FFFEF7}
textarea.add:focus,select.st:focus{outline:2px solid var(--accent);outline-offset:1px}
select.st{font:13px var(--sans);padding:5px 6px;border:1px solid var(--line);border-radius:6px;background:#fff;margin-bottom:6px;width:100%}
.final{font-size:13px;background:var(--accent-bg);border-left:3px solid var(--accent);padding:8px 10px;margin-top:6px;
 white-space:pre-wrap;word-break:break-word}
.cnt{font:600 11.5px var(--sans);color:var(--mute);display:flex;justify-content:space-between;align-items:center;margin-top:4px;gap:8px}
.cnt.over{color:var(--err)}
.cnt .btn{padding:3px 8px;font-size:12px}
.links td,.links th{font-size:13px}
.ftab{width:100%;border-collapse:collapse;font-size:13px;margin-top:6px}
.ftab td,.ftab th{padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top;text-align:left}
.ftab th{font:600 11.5px var(--sans);text-transform:uppercase;color:var(--ink2);background:var(--line2)}
.ftab code{font-size:12px}
details.cl{background:var(--sheet);border:1px solid var(--line);border-radius:var(--r-lg);margin:12px 0;padding:0}
details.cl>summary{cursor:pointer;padding:14px 18px;display:flex;gap:12px;align-items:center;flex-wrap:wrap;list-style:none}
details.cl>summary::-webkit-details-marker{display:none}
details.cl>summary h3{margin:0;font-size:17px;flex:1 1 280px}
details.cl[open]>summary{border-bottom:1px solid var(--line)}
details.cl .in{padding:12px 18px 18px}
.notes{font-size:13px;color:var(--ink2);margin:6px 0 0 18px}
.tools2{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0 4px;position:sticky;top:0;z-index:5;background:var(--paper);padding:10px 0}
.gnote{width:100%;min-height:70px}
.saved{font-size:12px;color:var(--mute);margin-left:auto;align-self:center}
nav.tabs{position:sticky;top:0;z-index:20;background:var(--deep);display:flex;gap:2px;overflow-x:auto;padding:0 12px;
 box-shadow:0 2px 8px rgba(6,41,79,.18)}
nav.tabs button{font:600 13px var(--sans);color:#C9DCE6;background:transparent;border:0;border-bottom:3px solid transparent;
 padding:11px 14px;cursor:pointer;white-space:nowrap;display:flex;align-items:center;gap:7px}
nav.tabs button:hover{color:#fff}nav.tabs button[aria-selected=true]{color:#fff;border-bottom-color:#5CF2E8}
nav.tabs .dot{width:8px;height:8px;border-radius:50%;background:#8FB7C6;flex:none}
nav.tabs .dot.err{background:#F97066}nav.tabs .dot.wrn{background:#FDB022}nav.tabs .dot.ok{background:#32D583}
.panel[hidden]{display:none}
.panel.frame{padding:0}.panel.frame iframe{display:block;width:100%;height:calc(100vh - 46px);border:0;background:var(--paper)}
.panel.frame .noemb{max-width:900px;margin:30px auto;padding:0 24px}
.gtag{display:inline-block;font:600 11px var(--sans);color:var(--accent);background:var(--accent-bg);padding:1px 7px;
 border-radius:999px;margin-top:4px}
.gtag.solo{color:var(--unv);background:var(--unv-bg)}
.gcards{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px}
.gcard{border:1px solid var(--line);border-radius:var(--r-md);padding:12px 14px;background:var(--sheet)}
.gcard h3{font-size:15px;margin:0 0 6px}.gcard .meta{margin-top:6px;color:var(--ink2)}
.gcard .meta div span{color:var(--mute)}.gcard .meta div b{color:var(--ink)}
.open{font-size:12px;padding:3px 8px;margin-top:6px}
@media (max-width:820px){.rtab thead{display:none}.rtab tr{display:block;border-bottom:1px solid var(--line);padding:6px 0}
 .rtab td{display:block;border:0;padding:6px 4px}}
@media print{.tools2,.cnt .btn,textarea.add,select.st{display:none!important}details.cl{break-inside:avoid}
 details.cl:not([open])>.in{display:block}}
"""

JS = r"""
(function(){
var D=JSON.parse(document.getElementById('sr-data').textContent);
/* ---- tab: Ringkasan & remarks + laporan lengkap tiap cluster (sama persis dengan laporan 1 cluster, interaktif) ---- */
var tabs=[].slice.call(document.querySelectorAll('nav.tabs button'));
function b64html(id){var el=document.getElementById(id);if(!el)return Promise.resolve(null);var bin=atob(el.textContent.trim());
 var u=new Uint8Array(bin.length);for(var i=0;i<bin.length;i++)u[i]=bin.charCodeAt(i);
 if(!window.DecompressionStream)return Promise.reject(new Error('browser lama'));
 return new Response(new Blob([u]).stream().pipeThrough(new DecompressionStream('gzip'))).text();}
function show(n,noHash){tabs.forEach(function(t){t.setAttribute('aria-selected',t.getAttribute('data-tab')===String(n)?'true':'false');});
 document.querySelectorAll('.panel').forEach(function(p){p.hidden=p.getAttribute('data-panel')!==String(n);});
 var p=document.querySelector('.panel[data-panel="'+n+'"]');
 if(p&&p.classList.contains('frame')&&!p.getAttribute('data-loaded')){p.setAttribute('data-loaded','1');
  p.innerHTML="<div class='noemb block'><p>Memuat laporan cluster...</p></div>";
  b64html('emb-'+n).then(function(h){if(!h)return;var f=document.createElement('iframe');f.title='Laporan cluster';
   f.srcdoc=h;p.innerHTML='';p.appendChild(f);},function(){p.innerHTML="<div class='noemb block'><h2>Browser terlalu lama</h2>"+
   "<p>Buka laporan ini dengan Chrome, Edge atau Firefox versi terbaru, atau buka laporan cluster di folder INPUT-nya.</p></div>";});}
 if(!noHash){try{history.replaceState(null,'',n==='0'||n===0?location.pathname:'#tab='+n);}catch(e){}}
 window.scrollTo(0,0);}
tabs.forEach(function(t){t.addEventListener('click',function(){show(t.getAttribute('data-tab'));});});
document.querySelectorAll('[data-open]').forEach(function(b){b.addEventListener('click',function(){show(b.getAttribute('data-open'));});});
var mh=/#tab=(\d+)/.exec(location.hash);if(mh&&document.querySelector('.panel[data-panel="'+mh[1]+'"]'))show(mh[1],true);
var KEY='seranta-grup:'+D.key, MAX=D.max_len, PFX=D.prefix;
var store={};try{store=JSON.parse(localStorage.getItem(KEY)||'{}')||{};}catch(e){store={};}
function save(){try{localStorage.setItem(KEY,JSON.stringify(store));var s=document.getElementById('saved');
 if(s){s.textContent='Isian tersimpan di browser ini '+new Date().toLocaleTimeString();}}catch(e){}}
function memberById(id){for(var i=0;i<D.members.length;i++){if(D.members[i].id===id)return D.members[i];}return null;}
function finalOf(m){
 var st=(store[m.id]&&store[m.id].st)||m.status, add=((store[m.id]&&store[m.id].add)||'').trim();
 var p=PFX[st]; var body=m.body||'';
 if(add){body=body?(body.replace(/[;\s]+$/,'')+'; '+add):add;}
 if(!p){return body||m.auto||'';}
 if(st==='APPROVE'&&!body)return 'Approve';
 return p+(body?' '+body:'');
}
function refresh(id){
 var m=memberById(id); if(!m)return; var f=finalOf(m);
 var el=document.querySelector('[data-final="'+id+'"]'); if(el)el.textContent=f;
 var c=document.querySelector('[data-cnt="'+id+'"]');
 if(c){c.querySelector('span').textContent=f.length+' / '+MAX+' karakter'+(f.length>MAX?' - terlalu panjang, ringkas remarks tambahan':'');
  c.classList.toggle('over',f.length>MAX);}
}
document.querySelectorAll('textarea.add').forEach(function(t){
 var id=t.getAttribute('data-id'); if(store[id]&&store[id].add)t.value=store[id].add;
 t.addEventListener('input',function(){store[id]=store[id]||{};store[id].add=t.value;save();refresh(id);});
});
document.querySelectorAll('select.st').forEach(function(s){
 var id=s.getAttribute('data-id'); if(store[id]&&store[id].st)s.value=store[id].st;
 s.addEventListener('change',function(){store[id]=store[id]||{};store[id].st=s.value;save();refresh(id);});
});
var gn=document.getElementById('gnote'); if(gn){gn.value=store.__note||'';
 gn.addEventListener('input',function(){store.__note=gn.value;save();});}
D.members.forEach(function(m){refresh(m.id);});
function copy(txt,btn){
 function ok(){if(btn){var o=btn.textContent;btn.textContent='Tersalin';setTimeout(function(){btn.textContent=o;},1200);}}
 if(navigator.clipboard&&window.isSecureContext){navigator.clipboard.writeText(txt).then(ok,fallback);}else{fallback();}
 function fallback(){var a=document.createElement('textarea');a.value=txt;document.body.appendChild(a);a.select();
  try{document.execCommand('copy');ok();}catch(e){}document.body.removeChild(a);}
}
document.querySelectorAll('[data-copy]').forEach(function(b){b.addEventListener('click',function(){
 var m=memberById(b.getAttribute('data-copy')); if(m)copy(finalOf(m),b);});});
var ca=document.getElementById('copyall'); if(ca)ca.addEventListener('click',function(){
 copy(D.members.filter(function(m){return !m.missing;}).map(function(m){return m.id+'\t'+finalOf(m);}).join('\n'),ca);});
var rs=document.getElementById('reset'); if(rs)rs.addEventListener('click',function(){
 if(!window.confirm('Hapus semua remarks tambahan dan status yang tersimpan di browser ini?'))return;
 store={};save();location.reload();});
window.addEventListener('beforeprint',function(){document.querySelectorAll('details.cl').forEach(function(d){d.open=true;});});

function dl(name,blob){var a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name;
 document.body.appendChild(a);a.click();setTimeout(function(){URL.revokeObjectURL(a.href);a.remove();},800);}
function stTitle(s){return ({'REJECT':'Reject','APPROVE DENGAN CATATAN':'Approve dengan catatan','APPROVE':'Approve'})[s]||s;}

/* ---- CSV remarks (Excel: pemisah ';', UTF-8 BOM) ---- */
var cv=document.getElementById('csv'); if(cv)cv.addEventListener('click',function(){
 function q(v){v=String(v==null?'':v);return '"'+v.replace(/"/g,'""')+'"';}
 var rows=[['cluster_id','cluster','hp','status','remarks_final','panjang','remarks_otomatis','remarks_tambahan']];
 D.members.forEach(function(m){var st=(store[m.id]&&store[m.id].st)||m.status,f=finalOf(m);
  rows.push([m.id,m.label,m.hp,st,f,f.length,m.auto,(store[m.id]&&store[m.id].add)||'']);});
 dl(D.file+'_REMARKS.csv',new Blob(['﻿'+rows.map(function(r){return r.map(q).join(';');}).join('\r\n')],{type:'text/csv'}));
});

/* ---- Word .docx (ZIP 'stored' + CRC32, OOXML minimal) ---- */
var CRC=(function(){var t=[],c;for(var n=0;n<256;n++){c=n;for(var k=0;k<8;k++)c=c&1?0xEDB88320^(c>>>1):c>>>1;t[n]=c>>>0;}return t;})();
function crc32(b){var c=0xFFFFFFFF;for(var i=0;i<b.length;i++)c=CRC[(c^b[i])&255]^(c>>>8);return (c^0xFFFFFFFF)>>>0;}
function zip(files){
 var enc=new TextEncoder(),parts=[],cen=[],off=0;
 files.forEach(function(f){
  var nm=enc.encode(f[0]),d=enc.encode(f[1]),cr=crc32(d),h=new DataView(new ArrayBuffer(30));
  h.setUint32(0,0x04034b50,true);h.setUint16(4,20,true);h.setUint16(6,0x0800,true);h.setUint16(8,0,true);
  h.setUint16(10,0,true);h.setUint16(12,0x21,true);h.setUint32(14,cr,true);h.setUint32(18,d.length,true);
  h.setUint32(22,d.length,true);h.setUint16(26,nm.length,true);h.setUint16(28,0,true);
  parts.push(new Uint8Array(h.buffer),nm,d);
  var c=new DataView(new ArrayBuffer(46));
  c.setUint32(0,0x02014b50,true);c.setUint16(4,20,true);c.setUint16(6,20,true);c.setUint16(8,0x0800,true);
  c.setUint16(10,0,true);c.setUint16(12,0,true);c.setUint16(14,0x21,true);c.setUint32(16,cr,true);
  c.setUint32(20,d.length,true);c.setUint32(24,d.length,true);c.setUint16(28,nm.length,true);
  c.setUint32(42,off,true);cen.push(new Uint8Array(c.buffer),nm);
  off+=30+nm.length+d.length;});
 var cs=cen.reduce(function(a,b){return a+b.length;},0),e=new DataView(new ArrayBuffer(22));
 e.setUint32(0,0x06054b50,true);e.setUint16(8,files.length,true);e.setUint16(10,files.length,true);
 e.setUint32(12,cs,true);e.setUint32(16,off,true);
 return new Blob(parts.concat(cen,[new Uint8Array(e.buffer)]),{type:'application/vnd.openxmlformats-officedocument.wordprocessingml.document'});
}
function x(s){return String(s==null?'':s).replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g,'').replace(/&/g,'&amp;')
 .replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function run(t,o){o=o||{};var p='';if(o.b)p+='<w:b/>';if(o.i)p+='<w:i/>';if(o.c)p+='<w:color w:val="'+o.c+'"/>';
 if(o.sz)p+='<w:sz w:val="'+o.sz+'"/>';return '<w:r>'+(p?'<w:rPr>'+p+'</w:rPr>':'')+'<w:t xml:space="preserve">'+x(t)+'</w:t></w:r>';}
function P(runs,st){return '<w:p>'+(st?'<w:pPr><w:pStyle w:val="'+st+'"/></w:pPr>':'')+(typeof runs==='string'?run(runs):runs.join(''))+'</w:p>';}
function H(t,l){return P([run(t)],'Heading'+l);}
function T(rows,w){var tw=w.reduce(function(a,b){return a+b;},0);
 var g='<w:tblGrid>'+w.map(function(v){return '<w:gridCol w:w="'+v+'"/>';}).join('')+'</w:tblGrid>';
 var b='<w:tblBorders>'+['top','left','bottom','right','insideH','insideV'].map(function(s){
  return '<w:'+s+' w:val="single" w:sz="4" w:space="0" w:color="BFBFBF"/>';}).join('')+'</w:tblBorders>';
 return '<w:tbl><w:tblPr><w:tblW w:w="'+tw+'" w:type="dxa"/>'+b+'<w:tblLayout w:type="fixed"/><w:tblCellMar><w:left w:w="70" w:type="dxa"/><w:right w:w="70" w:type="dxa"/></w:tblCellMar></w:tblPr>'+g+
  rows.map(function(r,ri){return '<w:tr>'+(ri===0?'<w:trPr><w:tblHeader/></w:trPr>':'')+r.map(function(c,ci){
   var sh=ri===0?'<w:shd w:val="clear" w:color="auto" w:fill="E3F2F3"/>':'';
   return '<w:tc><w:tcPr><w:tcW w:w="'+w[ci]+'" w:type="dxa"/>'+sh+'</w:tcPr>'+String(c==null?'':c).split('\n').map(function(line){
    return '<w:p><w:pPr><w:spacing w:after="0"/></w:pPr>'+run(line,{b:ri===0,sz:17})+'</w:p>';}).join('')+'</w:tc>';}).join('')+'</w:tr>';}).join('')+
  '</w:tbl>'+P('');}
var wd=document.getElementById('word'); if(wd)wd.addEventListener('click',function(){
 var b=[],W=9638;
 b.push(P([run(D.tool,{c:'0B6E79',b:true,sz:18})]));
 b.push(H(D.title,1));
 b.push(P([run('Status grup: ',{b:true}),run(D.status)]));
 D.meta.forEach(function(kv){b.push(P([run(kv[0]+': ',{b:true}),run(String(kv[1]))]));});
 if(D.links.length){b.push(H('Hubungan antar cluster',2));
  b.push(T([['Cluster','Cluster','Bukti']].concat(D.links),[2300,2300,W-4600]));}
 b.push(H('Remarks per cluster',2));
 var rr=[['Cluster','HP','Status','Remarks final']];
 D.members.forEach(function(m){var st=(store[m.id]&&store[m.id].st)||m.status;
  rr.push([m.id+(m.id!==m.label?'\n'+m.label:''),m.hp==null?'-':m.hp,stTitle(st),finalOf(m)+'\n('+finalOf(m).length+' karakter)']);});
 b.push(T(rr,[2100,700,1500,W-4300]));
 if(store.__note){b.push(H('Catatan reviewer untuk grup',2));store.__note.split('\n').forEach(function(l){b.push(P(l));});}
 D.members.forEach(function(m){
  b.push('<w:p><w:r><w:br w:type="page"/></w:r></w:p>');
  b.push(H(m.id+(m.id!==m.label?' - '+m.label:''),2));
  if(m.missing){b.push(P('Cluster ini terhubung dengan grup tetapi belum dijalankan: '+m.dir));return;}
  var st=(store[m.id]&&store[m.id].st)||m.status,add=(store[m.id]&&store[m.id].add)||'';
  b.push(T([['Data','Nilai'],['Homepass',m.hp],['Tiang',m.poles],['Temuan',m.qc],['BAKP',m.bakp],['Colo FDT',m.colo],
   ['Sumber HP',m.kmz_only?'KMZ saja (tanpa HPDB)':'HPDB']],[2600,W-2600]));
  b.push(P([run('Status: ',{b:true}),run(stTitle(st))]));
  b.push(P([run('Remarks otomatis: ',{b:true}),run(m.auto)]));
  if(add.trim())b.push(P([run('Remarks tambahan reviewer: ',{b:true}),run(add.trim())]));
  b.push(P([run('Remarks final ('+finalOf(m).length+' karakter): ',{b:true}),run(finalOf(m))]));
  if(m.notes.length){b.push(P([run('Catatan (bukan alasan reject):',{b:true})]));m.notes.forEach(function(n){b.push(P('- '+n));});}
  if(m.dropped.length){b.push(P([run('Temuan lain yang tidak muat 255 karakter:',{b:true})]));m.dropped.forEach(function(n){b.push(P('- '+n));});}
  if(m.std.length){b.push(H('Standar review strand',3));
   b.push(T([['No','Standar','Status','Keterangan']].concat(m.std.map(function(s){
    return [s[0],s[1],s[2]===true?'OK':(s[2]===false?'CEK':'--'),s[3]];})),[500,2400,700,W-3600]));}
  if(m.find.length){b.push(H('Temuan ('+m.find.length+')',3));
   b.push(T([['ID','Tingkat','Temuan','Keterangan']].concat(m.find.map(function(f){
    return [f.fid,f.sev,(f.std?'['+f.std+'] ':'')+f.label,f.ket];})),[900,1000,2400,W-4300]));}
 });
 b.push(P([run('Dibuat '+D.tool+' - '+D.when+'. Remarks final memuat remarks tambahan reviewer pada saat diunduh.',{i:true,sz:16,c:'6F6F6F'})]));
 var doc='<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'+
  b.join('')+'<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" w:header="567" w:footer="567" w:gutter="0"/></w:sectPr></w:body></w:document>';
 var sty='<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'+
  '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/><w:sz w:val="20"/><w:lang w:val="id-ID"/></w:rPr></w:rPrDefault>'+
  '<w:pPrDefault><w:pPr><w:spacing w:after="80" w:line="259" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'+
  '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'+
  [[1,32,'06294F'],[2,26,'0B6E79'],[3,22,'161616']].map(function(h){return '<w:style w:type="paragraph" w:styleId="Heading'+h[0]+'"><w:name w:val="heading '+h[0]+'"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="240" w:after="80"/><w:outlineLvl w:val="'+(h[0]-1)+'"/></w:pPr><w:rPr><w:b/><w:color w:val="'+h[2]+'"/><w:sz w:val="'+h[1]+'"/></w:rPr></w:style>';}).join('')+
  '</w:styles>';
 var files=[
  ['[Content_Types].xml','<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>'],
  ['_rels/.rels','<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'],
  ['word/_rels/document.xml.rels','<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'],
  ['word/document.xml',doc],['word/styles.xml',sty]];
 dl(D.file+'.docx',zip(files));
});
})();
"""


def _embed(r, base_dir):
    """Isi RINGKASAN_QC.html cluster (base64) agar laporan gabungan memuat laporan lengkap tiap cluster - interaktif sama
    persis dengan membuka laporan 1 cluster (peta, kartu aturan, filter, gambar temuan). Tautan Word cluster diarahkan ulang
    relatif terhadap laporan gabungan. None bila laporan cluster tidak ada."""
    import base64

    def quote(t, safe="/:"):
        """Percent-encoding UTF-8 untuk tautan berkas lokal (tanpa pustaka luar)."""
        ok = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~" + safe)
        return "".join(ch if ch in ok else "".join("%%%02X" % b for b in ch.encode("utf-8")) for ch in t)
    p = r.get("laporan") or ""
    if not p.lower().endswith(".html") or not os.path.isfile(p):
        return None
    with open(p, "r", encoding="utf-8") as fh:
        h = fh.read()
    w = r.get("word") or ""
    if w:
        bn = os.path.basename(w)
        h = h.replace("href='%s'" % E(bn), "href='%s'" % E(quote(_rel(w, base_dir), safe="/:")))
    import gzip
    # gzip: laporan gabungan 7 cluster +-20 MB -> +-10 MB; dibuka dengan DecompressionStream (browser modern)
    return base64.b64encode(gzip.compress(h.encode("utf-8"), 9, mtime=0)).decode("ascii")


def build(path, title, status, meta, links, members, tool="Seranta", when="", kind="grup", groups=None, embed=True):
    """Tulis satu HTML gabungan.
    title  : judul (mis. 'Grup 1 PIC: LINGKUNGAN 1 + ... (7 cluster)')
    status : status grup (teks)
    meta   : [(label, nilai)] ringkasan grup
    links  : [(cluster_a, cluster_b, 'bukti; bukti')] hubungan antar cluster
    members: [hasil _run_cluster] (atau dict 'missing' dari grup.groups)
    """
    base = os.path.dirname(os.path.abspath(path))
    mem = [member_data(r, base) for r in members]
    # grup tiap cluster (laporan batch): label kecil di tabel remarks
    gof = {}
    for gi, g in enumerate(groups or [], 1):
        for i in g.get("ids") or []:
            gof[i] = "Grup %d" % gi
    embs = [(_embed(r, base) if embed and not r.get("missing") else None) for r in members]
    fname = os.path.splitext(os.path.basename(path))[0]
    data = {"key": fname, "file": fname, "title": title, "status": status, "meta": [list(m) for m in meta],
            "links": [list(lk) for lk in links], "members": mem, "max_len": MAX_LEN, "prefix": PREFIX,
            "tool": tool, "when": when}
    n_rej = sum(1 for m in mem if m["status"] == "REJECT")
    n_ok = sum(1 for m in mem if m["status"].startswith("APPROVE"))
    verdict = "%d cluster: <b>%d reject</b>, %d approve%s. Lengkapi remarks tambahan bila perlu, lalu unduh Word atau CSV." % (
        len(mem), n_rej, n_ok, (", %d belum dijalankan" % sum(1 for m in mem if m["missing"]))
        if any(m["missing"] for m in mem) else "")

    rows = []
    for mi, m in enumerate(mem):
        opts = "".join("<option value='%s'%s>%s</option>" % (E(k), " selected" if k == m["status"] else "", E(v))
                       for k, v in (("REJECT", "Reject"), ("APPROVE DENGAN CATATAN", "Approve dgn catatan"),
                                    ("APPROVE", "Approve")))
        if m["missing"]:
            rows.append("<tr><td class='cl'><b>%s</b><small>%s</small></td><td>-</td><td colspan='2'>%s</td></tr>" % (
                E(m["id"]), E(m["label"] if m["label"] != m["id"] else ""),
                E("Terhubung dengan grup tetapi belum dijalankan: %s" % m["dir"])))
            continue
        rows.append(
            "<tr><td class='cl'><b>%s</b><small>%s%s</small><div style='margin-top:6px'>%s</div>%s%s</td>"
            "<td>%s</td>"
            "<td><div class='auto'>%s</div></td>"
            "<td><select class='st' data-id='%s' aria-label='Status %s'>%s</select>"
            "<textarea class='add' data-id='%s' placeholder='Remarks tambahan reviewer (opsional), mis. BAKP cluster lain; "
            "minta revisi tiang ganda' aria-label='Remarks tambahan %s'></textarea>"
            "<div class='final' data-final='%s'>%s</div>"
            "<div class='cnt' data-cnt='%s'><span>%d / %d karakter</span><button class='btn' type='button' data-copy='%s'>"
            "Salin</button></div></td></tr>" % (
                E(m["id"]), E(m["label"] if m["label"] != m["id"] else ""),
                ((" &middot; " if m["label"] != m["id"] else "") + "KMZ saja") if m["kmz_only"] else "",
                _status_chip(m["status"]),
                ("<span class='gtag'>%s</span>" % E(gof[m["id"]])) if m["id"] in gof else
                ("<span class='gtag solo'>Berdiri sendiri</span>" if groups is not None else ""),
                ("<div><button class='btn open' type='button' data-open='%d'>Laporan lengkap &rarr;</button></div>"
                 % (mi + 1)) if embs[mi] else "",
                E(str(m["hp"] if m["hp"] is not None else "-")), E(m["auto"] or "-"),
                E(m["id"]), E(m["id"]), opts, E(m["id"]), E(m["id"]), E(m["id"]), E(m["auto"]), E(m["id"]),
                len(m["auto"]), MAX_LEN, E(m["id"])))

    link_html = ""
    if links:
        link_html = ("<section class='block'><h2>Hubungan antar cluster</h2><p class='lead'>Bukti yang membuat cluster-cluster "
                     "ini dikelompokkan. <b>Tiang sama koordinat</b> = tiang tercatat di dua KMZ (BOQ ganda); <b>jalur "
                     "tersambung/berimpit</b> = satu jaringan; <b>BOUNDARY bersinggungan</b> = berdampingan.</p>"
                     "<table class='rtab links'><thead><tr><th>Cluster</th><th>Cluster</th><th>Bukti</th></tr></thead>"
                     "<tbody>%s</tbody></table></section>" % "".join(
                         "<tr><td>%s</td><td>%s</td><td>%s</td></tr>" % (E(a), E(b), E(s)) for a, b, s in links))

    gcards = ""
    if groups:
        gcards = ("<section class='block'><h2>Grup 1 PIC desain / cluster berdampingan</h2><p class='lead'>Cluster yang "
                  "terhubung (tiang bersama, jalur tersambung, BOUNDARY bersinggungan, BAKP sama) direview sebagai satu paket. "
                  "Cluster lain di batch ini berdiri sendiri.</p><div class='gcards'>%s</div></section>" % "".join(
                      "<div class='gcard'><span class='gtag'>Grup %d</span><h3>%s</h3><div>Status: <b>%s</b></div>%s</div>"
                      % (gi, E(g.get("title") or ""), E(g.get("status") or ""), _ui.meta_list(g.get("meta") or []))
                      for gi, g in enumerate(groups, 1)))
    details = []
    for m in mem:
        if m["missing"]:
            continue
        std_rows = "".join("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            E(str(s[0])), E(s[1]), _std_chip(s[2]), E(s[3])) for s in m["std"])
        f_rows = "".join("<tr><td><code>%s</code></td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            E(f["fid"]), _sev_chip(f["sev"]), E(("[%s] " % f["std"] if f.get("std") else "") + f["label"]), E(f["ket"]),
            _ui.map_link(f["lon"], f["lat"]) if f.get("lon") is not None else "") for f in m["find"])
        lk = []
        if m["html"]:
            lk.append("<a class='btn' href='%s' target='_blank' rel='noopener'>Laporan HTML cluster</a>" % E(m["html"]))
        if m["word"]:
            lk.append("<a class='btn' href='%s'>Word cluster (dengan gambar peta)</a>" % E(m["word"]))
        notes = "".join("<li>%s</li>" % E(n) for n in m["notes"])
        dropped = "".join("<li>%s</li>" % E(n) for n in m["dropped"])
        details.append(
            "<details class='cl' id='c-%s'><summary><h3>%s%s</h3>%s<span class='chip unv'>%s HP</span>"
            "<span class='chip unv'>%s tiang</span><span class='chip unv'>Temuan %s</span></summary><div class='in'>"
            "<div class='tools2' style='position:static;background:none;padding:0'>%s</div>"
            "<p><b>Remarks otomatis:</b> %s</p>%s%s"
            "<h4>Standar review strand</h4><table class='ftab'><thead><tr><th>No</th><th>Standar</th><th>Status</th>"
            "<th>Keterangan</th></tr></thead><tbody>%s</tbody></table>"
            "<h4>Temuan (%d)</h4><table class='ftab'><thead><tr><th>ID</th><th>Tingkat</th><th>Temuan</th><th>Keterangan</th>"
            "<th>Peta</th></tr></thead><tbody>%s</tbody></table></div></details>" % (
                E(re.sub(r"[^A-Za-z0-9_-]", "_", m["id"])), E(m["id"]),
                (" &middot; " + E(m["label"])) if m["label"] and m["label"] != m["id"] else "",
                _status_chip(m["status"]), E(str(m["hp"])), E(str(m["poles"])), E(m["qc"]), "".join(lk),
                E(m["auto"] or "-"),
                ("<p><b>Catatan (bukan alasan reject):</b></p><ul class='notes'>%s</ul>" % notes) if notes else "",
                ("<p><b>Tidak muat 255 karakter:</b></p><ul class='notes'>%s</ul>" % dropped) if dropped else "",
                std_rows or "<tr><td colspan='4'>-</td></tr>", len(m["find"]),
                f_rows or "<tr><td colspan='5'>Tidak ada temuan</td></tr>"))

    body = (
        "<div class='tools2'><button class='btn pri' id='word' type='button' title='Satu dokumen Word berisi semua cluster, "
        "remarks final (termasuk remarks tambahan) dan catatan grup'>Unduh Word (semua cluster + remarks)</button>"
        "<button class='btn' id='csv' type='button' title='Remarks final semua cluster untuk Excel'>Unduh CSV remarks</button>"
        "<button class='btn' id='copyall' type='button' title='ID cluster + remarks final, satu baris per cluster'>"
        "Salin semua remarks</button><button class='btn' type='button' onclick='window.print()'>Cetak / PDF</button>"
        "<button class='btn' id='reset' type='button' title='Hapus remarks tambahan & status yang tersimpan di browser ini'>"
        "Kosongkan isian</button><span class='saved' id='saved'></span></div>"
        "<section class='block'><h2>Remarks per cluster</h2><p class='lead'>Remarks otomatis dari Seranta (maks %d karakter). "
        "Tambahkan <b>remarks tambahan</b> atau ubah status bila keputusan review berbeda; <b>remarks final</b> dirangkai "
        "otomatis dan dihitung panjangnya. Isian tersimpan di browser ini dan ikut ke Word/CSV saat diunduh.</p>"
        "<table class='rtab'><thead><tr><th style='width:17%%'>Cluster</th><th style='width:6%%'>HP</th>"
        "<th style='width:35%%'>Remarks otomatis</th><th>Status, remarks tambahan &amp; final</th></tr></thead>"
        "<tbody>%s</tbody></table></section>"
        "<section class='block'><h2>Catatan reviewer untuk grup</h2><textarea id='gnote' class='add gnote' "
        "placeholder='Mis. tiang bersama L4-L6 dihitung di L4; minta BAKP mencantumkan semua ID cluster grup'></textarea>"
        "</section>%s%s<details class='cl'><summary><h3>Ringkasan temuan per cluster (versi ringkas untuk cetak)</h3>"
        "</summary><div class='in'>%s</div></details>" % (MAX_LEN, "".join(rows), gcards, link_html, "".join(details)))
    # tab: 0 = ringkasan & remarks; 1..n = laporan lengkap tiap cluster (tertanam)
    def _dot(st):
        return "err" if st == "REJECT" else ("wrn" if st.startswith("APPROVE DENGAN") else ("ok" if st == "APPROVE" else ""))
    tabbar = "<nav class='tabs' role='tablist' aria-label='Laporan'><button role='tab' data-tab='0' aria-selected='true'>" \
             "Ringkasan &amp; remarks</button>%s</nav>" % "".join(
                 "<button role='tab' data-tab='%d' aria-selected='false' title='%s'><span class='dot %s'></span>%s</button>"
                 % (i + 1, E(m["label"]), _dot(m["status"]), E(m["id"] if len(m["id"]) <= 26 else m["id"][:25] + "…"))
                 for i, m in enumerate(mem) if not m["missing"])
    panels = "".join(
        "<section class='panel frame' data-panel='%d' hidden>%s</section>" % (
            i + 1, "" if embs[i] else "<div class='noemb block'><h2>%s</h2><p>Laporan HTML cluster ini tidak tersedia. "
                                      "Remarks dan temuan ringkasnya ada di tab Ringkasan.</p></div>" % E(m["id"]))
        for i, m in enumerate(mem) if not m["missing"])
    blobs = "".join("<script type='application/octet-stream' id='emb-%d'>%s</script>" % (i + 1, b)
                    for i, b in enumerate(embs) if b)
    doc = ("<!doctype html><html lang='id'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,"
           "initial-scale=1'><title>%s</title><style>%s%s%s</style></head><body>"
           "%s<section class='panel' data-panel='0'>"
           "<header class='top'><div class='wrap'><div class='tool'>%s</div><h1>%s</h1><p class='verdict'>%s</p>%s"
           "<p class='verdict' style='font-size:14px'>Status: <b>%s</b></p></div></header>"
           "<main><div class='wrap'>%s</div></main><footer><div class='wrap'>Dibuat %s &middot; %s. Tab di atas memuat "
           "laporan lengkap tiap cluster (sama dengan laporan 1 cluster); berkas aslinya tetap ada di folder INPUT "
           "masing-masing.</div></footer></section>%s%s"
           "<script type='application/json' id='sr-data'>%s</script><script>%s</script></body></html>" % (
               E(title), _ui.font_css(), _ui.CSS, CSS, tabbar, E("%s · laporan gabungan %s" % (tool, kind)), E(title),
               verdict, _ui.meta_list(meta), E(status), body, E(tool), E(when), panels, blobs,
               json.dumps(data, ensure_ascii=False).replace("</", "<\\/"), JS))
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(doc)
    os.replace(tmp, path)
    return path


def from_group(path, g, s, tool="Seranta", when="", ratio=4, hp_per_spl=32):
    """HTML gabungan satu grup 1 PIC (g dari grup.groups, s dari grup.summarize)."""
    try:
        from . import grup as _g
    except ImportError:
        import grup as _g
    by = g["by"]
    links = []
    for a, b, p in sorted(g["links"], key=lambda t: (t[0], t[1])):
        ra, rb = by[a], by[b]
        links.append((_g.short_id(ra.get("label"), ra.get("cl_id")), _g.short_id(rb.get("label"), rb.get("cl_id")),
                      "; ".join(p.get("signals") or []) or "-"))
    kind_t = {"jaringan": "Satu jaringan (1 PIC desain)", "paket": "Paket survei 1 PIC",
              "berdampingan": "Cluster berdampingan"}.get(s.get("kind"), "Grup 1 PIC")
    meta = ([("Wilayah induk", s["wilayah"])] if s.get("wilayah") else []) + [
        ("Jenis grup", kind_t), ("Cluster", len(g["members"])), ("Total HP", s["n_hp"]),
        ("Splitter 1x%d" % ratio, "%d (%d HP/splitter)" % (s["spl"], hp_per_spl)), ("FDT", s["fdt"]),
        ("Tiang di dua cluster", s["shared"])] + (
        [("BOUNDARY identik", "%d cluster" % s["bnd_same"])] if s.get("bnd_same") else []) + (
        [("BAKP identik", "%d cluster" % s["bakp_same"])] if s.get("bakp_same") else []) + (
        [("TSSR identik", "%d cluster" % s["tssr_same"])] if s.get("tssr_same") else []) + (
        [("BOUNDARY tumpang tindih", "%d pasang, %d HP di irisan" % (s["overlap_pairs"], s["overlap_hp"]))]
        if s.get("overlap_pairs") else []) + (
        [("Rencana FDT grup", "tidak terpadu (%d rencana)" % s["plan"]["n_target"])]
        if (s.get("plan") or {}).get("terpadu") is False else []) + (
        [("Remarks grup", s["remarks"])] if s.get("remarks") else []) + [("Dibuat", when)]
    title = "%s: %s" % (kind_t, s["wilayah"] or " + ".join(s["ids"]))
    if len(title) > 160:
        title = "%s: %s + %d cluster lain" % (kind_t, " + ".join(s["ids"][:3]), len(s["ids"]) - 3)
    return build(path, title, s["status"], meta, links, g["members"], tool, when, kind="grup 1 PIC")

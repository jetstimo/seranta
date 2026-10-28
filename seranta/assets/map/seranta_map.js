/* Seranta - peta temuan interaktif untuk laporan HTML (offline; peta dasar satelit/jalan opsional saat online).
   Data: window.SERANTA_MAP = {L:[{k,t,c,n,a}], F:[{id,s,c,ln}]}. Detail temuan diambil dari daftar temuan di halaman
   (li[data-fid]) sehingga isi peta selalu sama dengan laporan. (c) 2026 Joseph Edward Timothy Siahaan, GPL-2.0+ */
(function(){
"use strict";
function boot(){
var D=window.SERANTA_MAP;if(!D||!window.L)return;
var box=document.getElementById("smap");if(!box)return;
function $(s,r){return (r||document).querySelector(s)}
function $$(s,r){return Array.prototype.slice.call((r||document).querySelectorAll(s))}
function esc(t){return String(t==null?"":t).replace(/[&<>"']/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]})}
function cssv(n,d){var v=getComputedStyle(document.documentElement).getPropertyValue(n);return (v&&v.trim())||d}
var SEV={ERROR:["Wajib diperbaiki",cssv("--err","#DA1E28")],WARNING:["Perlu ditinjau",cssv("--wrn","#BA4E00")],
 UNVERIFIED:["Belum bisa dicek",cssv("--unv","#6F6F6F")],INFO:["Catatan",cssv("--inf","#0043CE")]};
var ORDER={ERROR:0,WARNING:1,UNVERIFIED:2,INFO:3};
var KIND={hp:["Homepass","#2EC4B6","pt",3.5,"obj"],pole_new:["Tiang baru (NP)","#FF9F1C","pt",5,"pole"],pole_ext:["Tiang existing (EP)","#B8C2CC","pt",5,"pole"],
 fat:["FAT","#3A86FF","pt",7,"dev"],fdt:["FDT","#8338EC","pt",8,"dev"],closure:["Closure","#FF006E","pt",6,"dev"],
 route:["Jalur kabel","#5CF2E8","ln",3,"cab"],cable_new:["Kabel baru","#5CF2E8","ln",3,"cab"],cable:["Kabel existing/colo","#F7D774","ln",3,"cab"],
 feeder:["Kabel feeder","#FB5607","ln",3.5,"cab"],drop:["Kabel drop","#7FDBFF","ln",1,"drop"],pancingan:["Pancingan","#FFBE0B","ln",3,"cab"],
 boundary:["BOUNDARY cluster","#FFFFFF","pg",2,"area"],funnel:["Funnel / coverage","#9AE6B4","pg",1.5,"area"],coverage:["FAT coverage","#9AE6B4","pg",1,"area"]};
var GROUP={obj:"Homepass",pole:"Tiang",dev:"FAT / FDT / closure",cab:"Kabel / jalur",drop:"Kabel drop",area:"Batas area"};
function hav(a,b){var R=6371008.8,r=Math.PI/180,dl=(b[0]-a[0])*r,dp=(b[1]-a[1])*r,p1=a[1]*r,p2=b[1]*r;
  var h=Math.sin(dp/2)*Math.sin(dp/2)+Math.cos(p1)*Math.cos(p2)*Math.sin(dl/2)*Math.sin(dl/2);return 2*R*Math.asin(Math.sqrt(h))}
function segd(p,a,b){var kx=111320*Math.cos(p[1]*Math.PI/180),ky=110540,ax=(a[0]-p[0])*kx,ay=(a[1]-p[1])*ky,bx=(b[0]-p[0])*kx,by=(b[1]-p[1])*ky,
  dx=bx-ax,dy=by-ay,l=dx*dx+dy*dy,t=l?Math.max(0,Math.min(1,-(ax*dx+ay*dy)/l)):0;return Math.hypot(ax+t*dx,ay+t*dy)}
function dist(p,o){if(o.t==="pt")return hav(p,o.c);var c=o.t==="pg"?o.c:o.c,m=1e12;for(var i=0;i<c.length-1;i++)m=Math.min(m,segd(p,c[i],c[i+1]));return m}
function ll(c){return [c[1],c[0]]}
function len(c){var s=0;for(var i=0;i<c.length-1;i++)s+=hav(c[i],c[i+1]);return s}
function fmt(n,d){return Number(n).toLocaleString("id-ID",{maximumFractionDigits:d==null?1:d,minimumFractionDigits:0})}
function dms(v,pos,neg){var s=v<0?neg:pos;v=Math.abs(v);var d=Math.floor(v),m=Math.floor((v-d)*60),x=((v-d)*60-m)*60;return d+"°"+m+"'"+x.toFixed(2)+'"'+s}
/* ---- peta ---- */
var map=L.map($(".smap-map",box),{preferCanvas:true,zoomControl:true,attributionControl:true,maxZoom:22});
var base={none:null,sat:L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
  {maxZoom:22,maxNativeZoom:19,attribution:"Citra &copy; Esri, Maxar, Earthstar Geographics, GIS User Community"}),
 osm:L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:22,maxNativeZoom:19,attribution:"&copy; kontributor OpenStreetMap"})};
var curBase=null,off=$(".smap-off",box),failN=0;
Object.keys(base).forEach(function(k){if(base[k])base[k].on("tileerror",function(){if(++failN>3)off.classList.add("on")}).on("tileload",function(){failN=0;off.classList.remove("on")})});
function setBase(k){if(curBase)map.removeLayer(curBase);curBase=base[k]||null;off.classList.remove("on");failN=0;
  box.classList.toggle("light",k==="osm");if(curBase)curBase.addTo(map).bringToBack();try{localStorage.setItem("seranta-map-base",k)}catch(e){}}
/* ---- objek jaringan ---- */
var groups={},objs=[];
Object.keys(GROUP).forEach(function(g){groups[g]=L.layerGroup()});
D.L.forEach(function(o,i){var st=KIND[o.k]||["Objek","#ccc",o.t,3,"obj"],g=st[4],lay;o.i=i;
  if(o.t==="pt")lay=L.circleMarker(ll(o.c),{radius:st[3],color:"#0b1d2e",weight:1,fillColor:st[1],fillOpacity:.95});
  else if(o.t==="ln")lay=L.polyline(o.c.map(ll),{color:st[1],weight:st[3],opacity:.9});
  else lay=L.polygon(o.c.map(ll),{color:st[1],weight:st[3],fill:o.k!=="boundary",fillOpacity:.06,dashArray:o.k==="boundary"?"8 6":null});
  if(o.n)lay.bindTooltip(esc((st[0])+": "+o.n),{sticky:true,direction:"top"});
  lay.on("click",function(e){L.DomEvent.stopPropagation(e);if(meas.on){addMeas(e.latlng);return}showObj(o)});
  o.lay=lay;groups[g].addLayer(lay);objs.push(o)});
var gOrder=["area","drop","cab","obj","pole","dev"];
gOrder.forEach(function(g){if(groups[g].getLayers().length)groups[g].addTo(map)});
/* ---- temuan ---- */
var fl=L.layerGroup().addTo(map),hl=L.layerGroup().addTo(map),fx={},sevOn={ERROR:1,WARNING:1,UNVERIFIED:1,INFO:1};
D.F.forEach(function(f){var col=(SEV[f.s]||SEV.INFO)[1],g=L.featureGroup();
  if(f.ln&&f.ln.length>1)L.polyline(f.ln.map(ll),{color:col,weight:4,opacity:.7,dashArray:"9 7"}).addTo(g);
  L.circleMarker(ll(f.c),{radius:f.s==="ERROR"?9:7.5,color:"#fff",weight:2.5,fillColor:col,fillOpacity:1}).addTo(g);
  g.on("click",function(e){L.DomEvent.stopPropagation(e);if(meas.on){addMeas(e.latlng);return}select(f.id,true)});
  g.bindTooltip(function(){return esc(f.id+" · "+ftitle(f).slice(0,80))},{direction:"top"});
  f.g=g;fx[f.id]=f});
function refreshF(){fl.clearLayers();D.F.forEach(function(f){if(sevOn[f.s])fl.addLayer(f.g)});fl.eachLayer(function(l){l.bringToFront&&l.bringToFront()})}
refreshF();
var all=[];D.L.forEach(function(o){(o.t==="pt"?[o.c]:o.c).forEach(function(c){all.push(ll(c))})});D.F.forEach(function(f){all.push(ll(f.c))});
function fit(){if(all.length)map.fitBounds(L.latLngBounds(all).pad(.06))}
fit();
/* ---- panel ---- */
var pt=$(".smap-pt",box),pb=$(".smap-pb",box),nav=$(".smap-nav",box),curF=null;
function visF(){var seen={},ids=$$(".finds>li[data-fid]").map(function(li){return li.id}).filter(function(id){return fx[id]&&sevOn[fx[id].s]});
  ids.forEach(function(i){seen[i]=1});
  D.F.filter(function(f){return sevOn[f.s]&&!seen[f.id]}).sort(function(a,b){return (ORDER[a.s]||9)-(ORDER[b.s]||9)}).forEach(function(f){ids.push(f.id)});return ids}
function ftitle(f){var li=document.getElementById(f.id);return li&&$(".t",li)?$(".t",li).textContent.replace(f.id,"").trim():((f.ti||"")+(f.ob?" "+f.ob:""))}
function links(c){var la=c[1].toFixed(7),lo=c[0].toFixed(7);
  return "<div class='links'><a target='_blank' rel='noopener' href='https://www.google.com/maps/@?api=1&map_action=map&center="+la+","+lo+"&zoom=20&basemap=satellite'>Google Maps satelit</a>"+
   "<a target='_blank' rel='noopener' href='https://earth.google.com/web/@"+la+","+lo+",30a,180d,35y,0h,45t,0r'>Google Earth 3D</a>"+
   "<a target='_blank' rel='noopener' href='https://www.google.com/maps/@?api=1&map_action=pano&viewpoint="+la+","+lo+"'>Street View</a>"+
   "<a href='#' data-copy-c='"+la+", "+lo+"'>Salin koordinat</a></div>"}
function coordTable(c){return "<tr><td>Koordinat (lat, lon)</td><td>"+c[1].toFixed(7)+", "+c[0].toFixed(7)+"</td></tr><tr><td>DMS</td><td>"+dms(c[1],"LU","LS")+" "+dms(c[0],"BT","BB")+"</td></tr>"}
function nearObjs(c,r,skip){return objs.filter(function(o){return o!==skip&&o.k!=="boundary"&&o.k!=="funnel"&&o.k!=="coverage"}).map(function(o){return [dist(c,o),o]})
  .filter(function(x){return x[0]<=r}).sort(function(a,b){return a[0]-b[0]}).slice(0,8)}
function nearF(c,r,skip){return D.F.filter(function(f){return f.id!==skip}).map(function(f){return [Math.min(hav(c,f.c),f.ln?dist(c,{t:"ln",c:f.ln}):1e9),f]})
  .filter(function(x){return x[0]<=r}).sort(function(a,b){return a[0]-b[0]}).slice(0,8)}
function objRow(x){var o=x[1],st=KIND[o.k]||["Objek"];return "<button type='button' data-obj='"+o.i+"'><span class='sev-chip' style='background:"+(st[1]||"#888")+";color:#06121f'>"+esc(st[0])+"</span><span>"+esc(o.n||"(tanpa nama)")+" · "+fmt(x[0])+" m</span></button>"}
function fRow(x){var f=x[1],s=SEV[f.s]||SEV.INFO,t=ftitle(f);
  return "<button type='button' data-f='"+esc(f.id)+"'><span class='sev-chip' style='background:"+s[1]+"'>"+esc(f.id)+"</span><span>"+esc(t.slice(0,90))+" · "+fmt(x[0])+" m</span></button>"}
function pulse(c,col){hl.clearLayers();L.circleMarker(ll(c),{radius:20,color:col,weight:3,fill:false,opacity:.9}).addTo(hl);
  L.circleMarker(ll(c),{radius:30,color:col,weight:1.5,fill:false,opacity:.5}).addTo(hl)}
function select(id,fromMap){var f=fx[id];if(!f)return;curF=id;var s=SEV[f.s]||SEV.INFO,li=document.getElementById(id);
  pulse(f.c,s[1]);if(f.ln&&f.ln.length>1){hl.addLayer(L.polyline(f.ln.map(ll),{color:"#fff",weight:10,opacity:.35}))}
  var b=f.ln&&f.ln.length>1?L.latLngBounds(f.ln.map(ll)).pad(.6):null;
  if(b)map.flyToBounds(b,{maxZoom:20,duration:.6});else map.flyTo(ll(f.c),Math.max(map.getZoom(),19),{duration:.6});
  var title=ftitle(f)||id,arti=li&&$(".a",li)?$(".a",li).textContent:(f.ms||""),fix=li&&$(".fix",li)?$(".fix",li).textContent:(f.fx||"");
  var img=li&&$(".shot img",li)?$(".shot img",li).getAttribute("src"):"",tech=li&&$("details",li)?$("details",li).innerHTML.replace(/<summary>[\s\S]*?<\/summary>/,""):"";
  var rv=li?$(".rvc",li):null;
  pt.innerHTML="<div class='k'><span class='sev-chip' style='background:"+s[1]+"'>"+esc(s[0])+"</span> &nbsp;"+esc(id)+"</div><h3>"+esc(title)+"</h3>";
  var near=nearObjs(f.c,25),nf=nearF(f.c,30,id),h=[];
  if(arti)h.push("<div class='sec'><h4>Temuan</h4><p>"+esc(arti)+"</p></div>");
  if(fix)h.push("<div class='sec'><h4>Yang harus dilakukan</h4><p>"+esc(fix)+"</p></div>");
  if(f.v!=null||f.lim!=null)h.push("<div class='vs'><div><span>Nilai</span><b>"+(f.v!=null?fmt(f.v,2):"-")+"</b>"+esc(f.u||"")+"</div><div><span>Batas</span><b>"+(f.lim!=null?fmt(f.lim,2):"-")+"</b>"+esc(f.u||"")+"</div></div>");
  if(f.ln&&f.ln.length>1)h.push("<p>Panjang garis temuan: <b>"+fmt(len(f.ln))+" m</b></p>");
  if(img)h.push("<div class='sec'><h4>Gambar temuan</h4><img src='"+img+"' alt='Gambar "+esc(id)+"' data-zoom='"+esc(id)+"'></div>");
  if(rv)h.push("<label style='display:flex;gap:8px;align-items:center;font-weight:600'><input type='checkbox' data-rv='"+esc(id)+"'"+(rv.checked?" checked":"")+"> Tandai sudah dicek</label>");
  h.push("<div class='sec'><h4>Lokasi</h4><table>"+coordTable(f.c)+"</table></div>"+links(f.c));
  if(near.length)h.push("<div class='sec'><h4>Objek di sekitar (≤ 25 m)</h4><div class='near'>"+near.map(objRow).join("")+"</div></div>");
  if(nf.length)h.push("<div class='sec'><h4>Temuan lain di sekitar (≤ 30 m)</h4><div class='near'>"+nf.map(fRow).join("")+"</div></div>");
  if(tech)h.push("<details><summary>Detail teknis</summary>"+tech+"</details>");
  if(li)h.push("<p><a href='#"+esc(id)+"' data-tolist='"+esc(id)+"'>Lihat di daftar temuan &rarr;</a></p>");
  pb.innerHTML=h.join("");pb.scrollTop=0;navCount();
  if(!fromMap)box.scrollIntoView({behavior:"smooth",block:"start"})}
function showObj(o){var st=KIND[o.k]||["Objek","#888"],c=o.t==="pt"?o.c:o.c[Math.floor(o.c.length/2)];curF=null;
  hl.clearLayers();if(o.t==="pt")pulse(o.c,st[1]);else hl.addLayer(L.polyline(o.c.map(ll),{color:"#fff",weight:9,opacity:.45}));
  pt.innerHTML="<div class='k'>"+esc(st[0])+"</div><h3>"+esc(o.n||"(tanpa nama)")+"</h3>";
  var rows=[];Object.keys(o.a||{}).forEach(function(k){rows.push("<tr><td>"+esc(k)+"</td><td>"+esc(o.a[k])+"</td></tr>")});
  if(o.t==="ln")rows.push("<tr><td>Panjang</td><td>"+fmt(len(o.c))+" m ("+(o.c.length-1)+" ruas)</td></tr>");
  if(o.t==="pg")rows.push("<tr><td>Keliling</td><td>"+fmt(len(o.c))+" m</td></tr>");
  var nf=nearF(c,o.t==="pt"?20:5),near=o.t==="pt"?nearObjs(o.c,30,o):[],h=[];
  h.push("<div class='sec'><h4>Atribut</h4><table>"+rows.join("")+(o.t==="pt"?coordTable(o.c):"")+"</table></div>");
  h.push("<div class='sec'><h4>Temuan QC pada objek ini</h4>"+(nf.length?"<div class='near'>"+nf.map(fRow).join("")+"</div>":"<p>Tidak ada temuan di objek ini. ✔</p>")+"</div>");
  if(near.length)h.push("<div class='sec'><h4>Objek terdekat</h4><div class='near'>"+near.map(objRow).join("")+"</div></div>");
  h.push(links(c));pb.innerHTML=h.join("");pb.scrollTop=0}
function intro(){pt.innerHTML="<div class='k'>Panel detail</div><h3>Klik titik temuan atau objek di peta</h3>";
  var n={};D.F.forEach(function(f){n[f.s]=(n[f.s]||0)+1});
  pb.innerHTML="<p>Peta memuat <b>"+D.F.length+"</b> temuan dan <b>"+objs.length+"</b> objek jaringan. Klik titik berwarna untuk melihat isi temuan, nilai vs batas, gambar, objek di sekitarnya, dan tautan ke Google Earth/Maps. Klik tiang, HP, perangkat, atau kabel untuk melihat atributnya dan temuan yang melekat.</p>"+
   "<div class='near'>"+Object.keys(SEV).filter(function(s){return n[s]}).map(function(s){return "<button type='button' data-first='"+s+"'><span class='sev-chip' style='background:"+SEV[s][1]+"'>"+n[s]+"</span><span>"+SEV[s][0]+": buka temuan pertama</span></button>"}).join("")+"</div>"+
   "<p style='color:var(--mute,#6b7280);font-size:12.5px'>Pintasan: <b>[</b> / <b>]</b> temuan sebelumnya/berikutnya, <b>M</b> ukur jarak, <b>F</b> layar penuh. Peta dasar satelit/jalan butuh internet; tanpa internet peta tetap jalan dengan data jaringan.</p>";navCount()}
function navCount(){var ids=visF(),i=ids.indexOf(curF);$(".c",nav).textContent=curF?(i+1)+" / "+ids.length+" temuan":ids.length+" temuan tampil"}
function step(d){var ids=visF();if(!ids.length)return;var i=ids.indexOf(curF);i=i<0?(d>0?0:ids.length-1):(i+d+ids.length)%ids.length;select(ids[i],true)}
pb.addEventListener("click",function(e){var t=e.target.closest("[data-f],[data-obj],[data-first],[data-copy-c],[data-zoom],[data-tolist]");if(!t)return;
  if(t.dataset.f){select(t.dataset.f,true)}else if(t.dataset.obj){var o=objs[+t.dataset.obj];showObj(o);map.flyTo(ll(o.t==="pt"?o.c:o.c[0]),Math.max(map.getZoom(),19))}
  else if(t.dataset.first){var f=D.F.filter(function(x){return x.s===t.dataset.first}).map(function(x){return x.id});var ids=visF().filter(function(i){return f.indexOf(i)>=0});if(ids[0])select(ids[0],true)}
  else if(t.dataset.copyC){e.preventDefault();try{navigator.clipboard.writeText(t.dataset.copyC);t.textContent="Tersalin ✔"}catch(x){}}
  else if(t.dataset.zoom){var li=document.getElementById(t.dataset.zoom),a=li&&$(".shot",li);if(a)a.click()}
  else if(t.dataset.tolist){e.preventDefault();var l2=document.getElementById(t.dataset.tolist);if(l2){var d=l2.closest("details");if(d)d.open=true;l2.scrollIntoView({behavior:"smooth",block:"center"});history.replaceState(null,"","#"+t.dataset.tolist)}}});
pb.addEventListener("change",function(e){var id=e.target.dataset&&e.target.dataset.rv;if(!id)return;var li=document.getElementById(id),c=li&&$(".rvc",li);
  if(c&&c.checked!==e.target.checked){c.checked=e.target.checked;c.dispatchEvent(new Event("change",{bubbles:true}))}});
/* ---- kontrol kepala ---- */
var head=$(".smap-head",box);
var bs=$("select[data-base]",head);var b0="none";try{b0=localStorage.getItem("seranta-map-base")||"none"}catch(e){}bs.value=b0;setBase(b0);
bs.addEventListener("change",function(){setBase(bs.value)});
var cnt={};D.F.forEach(function(f){cnt[f.s]=(cnt[f.s]||0)+1});
var sevBox=$(".sevs",head);sevBox.innerHTML=Object.keys(SEV).filter(function(s){return cnt[s]}).map(function(s){return "<button type='button' class='sbtn on' data-sev='"+s+"' title='Tampilkan/sembunyikan: "+SEV[s][0]+"'><i class='dot' style='background:"+SEV[s][1]+"'></i>"+cnt[s]+"</button>"}).join("");
sevBox.addEventListener("click",function(e){var b=e.target.closest("[data-sev]");if(!b)return;var s=b.dataset.sev;sevOn[s]=sevOn[s]?0:1;b.classList.toggle("on",!!sevOn[s]);refreshF();navCount()});
var lyBox=$(".lys",head);lyBox.innerHTML=gOrder.filter(function(g){return groups[g].getLayers().length}).map(function(g){return "<button type='button' class='sbtn"+(map.hasLayer(groups[g])?" on":"")+"' data-g='"+g+"'>"+GROUP[g]+"</button>"}).join("");
lyBox.addEventListener("click",function(e){var b=e.target.closest("[data-g]");if(!b)return;var g=groups[b.dataset.g];if(map.hasLayer(g)){map.removeLayer(g);b.classList.remove("on")}else{g.addTo(map);b.classList.add("on");fl.eachLayer(function(l){l.bringToFront&&l.bringToFront()})}});
var q=$("input[data-q]",head);q.addEventListener("keydown",function(e){if(e.key!=="Enter")return;var v=q.value.trim().toLowerCase();if(!v)return;
  var f=D.F.filter(function(x){return x.id.toLowerCase()===v||x.id.toLowerCase().indexOf(v)>=0})[0];if(f){select(f.id,true);return}
  var o=objs.filter(function(x){return (x.n||"").toLowerCase()===v})[0]||objs.filter(function(x){return (x.n||"").toLowerCase().indexOf(v)>=0})[0];
  if(o){showObj(o);map.flyTo(ll(o.t==="pt"?o.c:o.c[0]),19)}else{q.setCustomValidity("Tidak ditemukan");q.reportValidity();setTimeout(function(){q.setCustomValidity("")},1500)}});
/* ---- ukur jarak ---- */
var meas={on:false,pts:[],lay:L.layerGroup().addTo(map)},mtxt=$(".smap-meas",box);
function addMeas(latlng){meas.pts.push(latlng);meas.lay.clearLayers();L.polyline(meas.pts,{color:"#FFBE0B",weight:3,dashArray:"6 5"}).addTo(meas.lay);
  meas.pts.forEach(function(p){L.circleMarker(p,{radius:4,color:"#FFBE0B",fillOpacity:1}).addTo(meas.lay)});
  var s=0;for(var i=0;i<meas.pts.length-1;i++)s+=hav([meas.pts[i].lng,meas.pts[i].lat],[meas.pts[i+1].lng,meas.pts[i+1].lat]);
  mtxt.textContent="Jarak: "+fmt(s)+" m ("+Math.max(0,meas.pts.length-1)+" ruas) · klik untuk menambah titik · Esc selesai"}
function toggleMeas(on){meas.on=on==null?!meas.on:on;$("[data-meas]",head).classList.toggle("on",meas.on);mtxt.classList.toggle("on",meas.on);
  map.getContainer().style.cursor=meas.on?"crosshair":"";if(meas.on){meas.pts=[];meas.lay.clearLayers();mtxt.textContent="Klik titik awal di peta"}else{meas.lay.clearLayers()}}
map.on("click",function(e){if(meas.on)addMeas(e.latlng)});
$("[data-meas]",head).addEventListener("click",function(){toggleMeas()});
$("[data-fit]",head).addEventListener("click",fit);
/* ---- tangkapan gambar tampilan peta (tanpa peta dasar online agar tidak terblokir CORS) ---- */
function snap(mode){var mc=map.getContainer(),r=mc.getBoundingClientRect(),W=Math.round(r.width),H=Math.round(r.height),hb=46,sc=2;
  var c=document.createElement("canvas");c.width=W*sc;c.height=(H+hb)*sc;var g=c.getContext("2d");g.scale(sc,sc);
  g.fillStyle=box.classList.contains("light")?"#eef3f6":"#0f2236";g.fillRect(0,hb,W,H);
  var tiles=curBase?$$(".leaflet-tile-pane img.leaflet-tile-loaded",mc):[];var tainted=false;
  tiles.forEach(function(im){var b=im.getBoundingClientRect();try{g.drawImage(im,b.left-r.left,b.top-r.top+hb,b.width,b.height);g.getImageData(0,0,1,1)}catch(e){tainted=true}});
  if(tainted){g.fillStyle=box.classList.contains("light")?"#eef3f6":"#0f2236";g.fillRect(0,hb,W,H)}
  $$(".leaflet-overlay-pane canvas, .leaflet-overlay-pane svg",mc).forEach(function(cv){var b=cv.getBoundingClientRect();
    if(cv.tagName.toLowerCase()==="canvas")g.drawImage(cv,b.left-r.left,b.top-r.top+hb,b.width,b.height)});
  g.fillStyle="#06294F";g.fillRect(0,0,W,hb);g.fillStyle="#fff";g.font="600 14px Inter,Segoe UI,sans-serif";
  var f=curF&&fx[curF],t=f?(curF+" \u00b7 "+(SEV[f.s]||SEV.INFO)[0]+" \u00b7 "+ftitle(f)):"Peta temuan QC";g.fillText(t.slice(0,110),12,19);
  g.font="12px Inter,Segoe UI,sans-serif";g.fillStyle="#9FE8E2";var ce=map.getCenter();
  g.fillText("Pusat "+ce.lat.toFixed(6)+", "+ce.lng.toFixed(6)+" \u00b7 zoom "+map.getZoom()+" \u00b7 "+new Date().toLocaleString("id-ID")+(tainted?" \u00b7 peta dasar online tidak ikut tergambar":""),12,37);
  /* skala 50/100 m dan panah utara */
  var p0=map.containerPointToLatLng([20,H-24]),mpp=hav([p0.lng,p0.lat],[map.containerPointToLatLng([120,H-24]).lng,p0.lat])/100,len=[10,20,50,100,200,500,1000].filter(function(m){return m/mpp<=180}).pop()||10,px=len/mpp;
  g.fillStyle="rgba(255,255,255,.9)";g.fillRect(14,hb+H-34,px+52,22);g.fillStyle="#0b1d2e";g.fillRect(20,hb+H-22,px,3);g.font="11px Inter,sans-serif";g.fillText(len+" m",24+px,hb+H-16);
  g.fillStyle="rgba(255,255,255,.9)";g.beginPath();g.moveTo(W-24,hb+12);g.lineTo(W-32,hb+32);g.lineTo(W-16,hb+32);g.closePath();g.fill();
  c.toBlob(function(b){var nm=(curF||"peta_temuan")+"_peta.png";
    if(mode==="png"){var a=document.createElement("a");a.href=URL.createObjectURL(b);a.download=nm;document.body.appendChild(a);a.click();a.remove();note("Gambar peta diunduh: "+nm)}
    else{try{navigator.clipboard.write([new ClipboardItem({"image/png":b})]).then(function(){note("Gambar peta tersalin. Tempel di Word dengan Ctrl+V")},function(){note("Browser menolak menyalin; pakai Unduh gambar")})}catch(x){note("Browser belum mendukung salin gambar; pakai Unduh gambar")}}},"image/png")}
function note(t){var el=document.getElementById("toast");if(el){el.textContent=t;el.classList.add("on");setTimeout(function(){el.classList.remove("on")},2600)}else{mtxt.textContent=t;mtxt.classList.add("on");setTimeout(function(){if(!meas.on)mtxt.classList.remove("on")},2600)}}
$("[data-snap]",head).addEventListener("click",function(){snap("copy")});$("[data-snapd]",head).addEventListener("click",function(){snap("png")});
function full(){box.classList.toggle("full");setTimeout(function(){map.invalidateSize()},50)}
$("[data-full]",head).addEventListener("click",full);
$("[data-prev]",nav).addEventListener("click",function(){step(-1)});$("[data-next]",nav).addEventListener("click",function(){step(1)});
var co=$(".smap-coord",box);map.on("mousemove",function(e){co.textContent=e.latlng.lat.toFixed(6)+", "+e.latlng.lng.toFixed(6)});
document.addEventListener("keydown",function(e){var tg=e.target.tagName;if(/INPUT|TEXTAREA|SELECT/.test(tg))return;
  if(e.key==="]"){step(1)}else if(e.key==="["){step(-1)}else if(e.key==="m"||e.key==="M"){var r=box.getBoundingClientRect();if(r.bottom>0&&r.top<innerHeight)toggleMeas()}
  else if(e.key==="f"||e.key==="F"){var r2=box.getBoundingClientRect();if(r2.bottom>0&&r2.top<innerHeight)full()}else if(e.key==="Escape"){if(meas.on)toggleMeas(false);if(box.classList.contains("full"))full()}});
/* ---- sambungan ke daftar temuan ---- */
$$(".finds>li[data-fid]").forEach(function(li){if(!fx[li.id])return;var acts=$(".acts",li);if(!acts)return;
  var b=document.createElement("button");b.type="button";b.className="btn";b.textContent="Tampilkan di peta";b.title="Tampilkan temuan ini di peta QC beserta detailnya";
  b.addEventListener("click",function(){select(li.id,false)});acts.insertBefore(b,acts.firstChild)});
window.SerantaMap={select:select,fit:fit};
intro();setTimeout(function(){map.invalidateSize();fit()},120);
}
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",boot);else boot();
})();

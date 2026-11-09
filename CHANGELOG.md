# Changelog

## 3.15.0 – fokus alat 1, standar 10 persilangan tol/rel/jalan besar (revisi pembuat 10 November 2026)

- **Fokus alat 1**: alat 2-4 disembunyikan (menu dan Processing Toolbox). Munculkan lagi kapan saja dengan mencentang
  **Vektor > Seranta > Show tools 2-4**; hapus centang untuk menyembunyikan. Kode alat 2-4 tetap ada di paket.
- **Standar 10 – persilangan jalan tol / rel / jalan besar** (tambahan Seranta di luar 9 standar Review Strand), dari
  kajian regulasi resmi:
  - `JALUR_MELINTAS_TOL` (**ERROR**, alasan Reject): izin rumija tol dari Dirjen Bina Marga atas rekomendasi teknis BPJT
    & BUJT (PP 23/2024; Permen PU 6/2025; portal Perizinan PU "Crossing Utilitas (Pipa/Kabel)"); kabel udara melintang tol
    praktis tidak disetujui, metode lazim boring/HDD dengan pit di luar rumija tol (>= 30 m, PP 34/2006 Ps. 40).
  - `JALUR_MELINTAS_REL` (**ERROR**): izin Dirjen Perkeretaapian + izin prinsip KAI (PM 36/2011 Ps. 7, 8, 11-12; PP
    56/2009 Ps. 82): >= 6,20 m dari kepala rel & tiang >= 10 m dari as rel terluar, atau >= 150 cm di bawah subgrade.
  - `WARN_JALUR_MELINTAS_JALAN_BESAR`: jalan nasional/arteri (OSM trunk/primary) **atau lebar terbaca >= 4 lajur /
    >= 14 m** (PP 34/2006 Ps. 32: jalan raya minimal 2 lajur per arah @ 3,5 m + median); izin penyelenggara jalan
    (Permen PU 20/PRT/M/2010 Ps. 4, 5, 12: kabel udara >= 5 m, tanah >= 1,5 m, tiang >= 1 m dari tepi bahu/trotoar).
  - `WARN_TIANG_DEKAT_JALAN_TOL` (< 15 m dari jalur tol = di rumija 30 m) dan `WARN_TIANG_DEKAT_REL` (< 10 m dari as rel)
    untuk rute sejajar yang tidak memotong.
  - `INFO_JALUR_MELINTAS_JALAN_SEDANG` (kolektor) dan `INFO_JALUR_MELINTAS_SUNGAI` (Permen PUPR 28/2015 Ps. 22).
  - Lebar jalan (`width`) dan jumlah lajur (`lanes`, `lanes:forward/backward`) dari OSM kini dibaca. Rute yang menyusuri
    jalan (memotong garis as jalan dengan sudut < 25°) tidak lagi dihitung sebagai menyeberang (jalan tol/rel tetap).
- **Perbaikan unduhan data jalan**: di 3.14.1 cek persilangan selalu "tidak dicek" di banyak jaringan (overpass-api.de
  menjawab 406, server lain tidak menjawab; laporan Bitung: "Expecting value"). Kini: 3 server Overpass dengan validasi
  jawaban, lalu cadangan API utama OpenStreetMap 0.6 untuk kotak cluster kecil; hasil di-cache 30 hari.
- **RT/RW di nama berkas** (`WARN_NAMA_BERKAS_WILAYAH_BEDA`): mis. folder & HPDB "RT 17" tetapi BAKP bernama "RT_023".
  Temuan RT/RW kini membuat standar 3 **[CEK]** (sebelumnya tetap "--" bila FINDIM tidak ada sehingga kartu HTML tampil
  "belum diverifikasi").
- Uji nyata: Bitung Kakenturan Satu Lingk. 2 & 3 (Jalan Tol Manado-Bitung), Tegal Dukuhwringin RW 03 (Jalur KA
  Tegal-Prupuk), Pasir Putih RT 17 (CLUSTER_NAME "RT 23", BAKP "RT_023").

## 3.14.1 – ringkasan standar lebih jelas, cek RT/RW HPDB, persilangan jalan tol/rel (revisi pembuat 9 November 2026)

- **Ringkasan 9 standar ditulis per bagian**, tiap bagian punya status sendiri, sehingga terlihat bagian mana yang membuat
  standar [CEK]. Standar 4: "HP duplikat" (koordinat/label/ID sama, juga lintas cluster) dipisah dari "Kecocokan HPDB-KMZ".
  Standar 2: Funnel/RFS, HP masuk BOUNDARY cluster lain, BOUNDARY tumpang tindih, tiang ganda (jumlah tiang kini sama dengan
  remarks). Standar 5: HP di luar Funnel dipisah dari HP di luar BOUNDARY KMZ. Standar 9: rentang > 60 m dipisah dari
  rentang 50-60 m. Alasan "tidak dicek" selalu ditulis; ada baris arti status. Status standar dan keputusan review tidak
  berubah (uji 13 cluster nyata: Kediri, Minahasa, Pasir Putih).
- **RT/RW-lingkungan HPDB** (WARN_HPDB_RT_RW_TIDAK_SESUAI): kolom RT, RW/lingkungan dan CLUSTER_NAME dibandingkan dengan
  nomor wilayah di nama Funnel/folder cluster dan dengan tetangga terdekat (rumah RT 24 di tengah rumah RT 17, radius 60 m).
- **Persilangan jalan tol / rel / jalan arteri** (WARN_JALUR_MELINTAS_TOL, WARN_JALUR_MELINTAS_REL,
  INFO_JALUR_MELINTAS_JALAN_BESAR) dari data jalan OpenStreetMap: file *OSM* di folder referensi atau unduhan Overpass
  (cache 30 hari; offline = tidak dicek). Dasar resmi: PP 23/2024 Pasal 71 & 75 dan SE Dirjen Bina Marga 11/SE/Db/2017
  (tol; angka 5 m Permen PU 20/2010 tidak dipakai karena Pasal 3 mengecualikan jalan tol), PM Perhubungan 36/2011
  Pasal 7, 8, 11 (rel: >= 6,20 m dari kepala rel, tiang >= 10 m dari as rel, >= 150 cm di bawah subgrade), Permen PU
  20/PRT/M/2010 Pasal 12 ayat (6) (jalan non-tol, tetap berlaku menurut Permen PU 6/2025).
- **Perbaikan**: garis temuan CLUSTER_LAIN_DIGABUNG dulu menyambung semua HP urut baris HPDB (garis silang-menyilang di
  peta), kini garis tepi sebaran HP; labelnya jumlah HP, bukan meter. Bentangan jalur di luar BOUNDARY tidak lagi
  digabung lintas garis jalur yang tidak bersambung.

## 3.14.0 – berkas dikenali dari isi, remarks sederhana, jenis data otomatis (revisi pembuat 8 November 2026)

- **Remarks sederhana (bawaan)**: kalimat pendek tanpa nomor baris/angka, mis. "Reject: Ada tiang duplikat dengan cluster
  X, dan ada garis jalur yang digambar dobel. Mohon dicek kembali keseluruhannya." Status & urutan sama dengan remarks
  rinci; rincian tetap di REMARKS.txt dan kolom `remarks_rinci` REMARKS_BATCH.csv. Gaya lama: Advanced > Detailed.
- **Jenis data otomatis**: tiap cluster dinyatakan "1 PIC / berdampingan dengan ..." atau "cluster mandiri".
- **Berkas dikenali dari isinya**: HPDB dari kolom LATITUDE/LONGITUDE walau nama tanpa HPDB/salah ketik (HPBD, HDPB,
  HOMEPAS); salinan cadangan dilewati; KMZ cluster lain yang tersalin tidak terpilih; Design Lite/Funnel/attributes,
  TSSR dan BAKP yang namanya diubah/salah ketik dikenali dari isi.
- **Satu folder berisi banyak cluster** (banyak KMZ, atau banyak HPDB+KMZ+dokumen) dipecah otomatis ke `_PER_BERKAS/`
  dan diperiksa per cluster. Uji folder '1 pic design' (13 KMZ Suka Karya + KMZ 1 PIC Tomohon): dulu berhenti, kini 20
  cluster diperiksa di QGIS pengguna dengan data funnel asli.
- Diuji dan ditolak: nama wilayah induk sebagai bukti satu funnel (Tomohon: tiap lingkungan funnel sendiri).
- Istilah perusahaan dihapus dari teks pengguna. Data Suka Karya ber-HPDB: temuan identik 3.13.0.

## 3.13.0 – integritas jalur: satu jaringan kabel utuh yang ditumpu tiang (revisi pembuat 6 November 2026)

- **Jalur tanpa tiang** (JALUR_TANPA_TIANG, reject): bagian jalur tanpa tiang diukur SEPANJANG JALUR sampai tiang terdekat
  dan dinilai dengan batas bentang yang sama (USDA RUS 1751F-630): jalur tanpa satu pun tiang, ujung jalur > 60 m dari tiang
  terakhir, dua tiang lewat percabangan tanpa tiang. Lingkar jalur tanpa titik tiang kini ditelusuri.
- **Jalur terputus** (JALUR_TERPUTUS, reject): bagian jalur bertiang yang tidak tersambung ke jaringan cluster (ITU-T G.984.1).
- **Percabangan tanpa simpul/tiang**: ujung atau titik sudut garis yang menempel di garis lain tanpa disambung; percabangan
  dan ujung jalur tanpa tiang kini masuk remarks sebagai alasan reject (FOA Aerial Workmanship; RUS 1751F-650).
- Catatan baru: garis bersilang tanpa simpul, garis bertumpuk/bolak-balik (BOQ kabel ganda), tiang NP & jalur di luar
  BOUNDARY (di boundary cluster saudara 1 PIC = catatan), HP di bagian jalur yang tidak tersambung ke titik masuk colo FDT.
- KMZ tanpa tiang/tanpa jalur kini mendapat remarks Reject di rekap batch. Rentang yang dihitung ulang dengan tiang saudara
  menyebut semua bagian > 60 m.
- Saklar profil `route_integrity`; false = identik 3.12.0 (Suka Karya 458 temuan; remarks identik pada 5.200 kombinasi).

## 3.12.0 – jalur ditumpu tiang cluster saudara 1 PIC, setiap aturan bersumber (kajian REVIEW STRAND Suka Karya, November 2026)

- **Rentang lewat tiang saudara**: bentang = jarak titik tumpu berurutan (USDA RUS Bulletin 1751F-630 "Span Length";
  Corning AEN 14). Tiang cluster saudara 1 PIC/satu funnel yang dilewati jalurnya (<= 5 m) dan <= 3 m dari garis rentang
  (aturan tiang sendiri) memecah rentang; rentang terpanjang dinilai ulang. Suka Karya: KOTA RT 04 240 m -> 53 m; RT 10
  547 m -> 154 m.
- **Belokan/ujung/percabangan di tiang saudara** (<= snap_m) -> INFO_TITIK_JALUR_DI_TIANG_SAUDARA + pengingat treklam/tambat
  (USDA RUS 1751F-650). Suka Karya: 23 titik.
- Tiang saudara dihitung bila <= 5 m dari jalurnya (GPS.gov 4,9 m; data: 98 % tiang <= 5 m, 68 % <= 2 m). HP > 50 m:
  39 HP tercover (3.11: 27 dengan syarat 2 m yang terlalu ketat).
- Pengaman: bila bagian 1 PIC gagal, temuan dikembalikan dan cek inti tetap utuh (bug akar negatif ditemukan di RT 03).
- Saklar profil baru `cross_1pic_route_support`; semua saklar 1 PIC false = identik 3.10.0.
- Sumber setiap aturan 1 PIC dicantumkan di DASAR_ATURAN.md dan profil (kebijakan internal ditandai INTERNAL).

## 3.11.0 – 1 PIC / berdampingan dinilai sebagai satu wilayah (revisi pembuat, 5 November 2026)

- **Boundary bertumpuk diterima**: irisan BOUNDARY dan HP di BOUNDARY cluster saudara dalam 1 PIC / berdampingan yang satu
  funnel (atau, tanpa data referensi, satu wilayah induk: BAKP/TSSR identik, BOUNDARY induk sama) menjadi catatan
  (INFO_BOUNDARY_BERIRISAN_1PIC, INFO_HP_DI_BOUNDARY_SAUDARA_1PIC), bukan alasan reject.
- **Lintas funnel tetap ERROR**: boundary/HP yang masuk funnel lain tetap penghalang, ditandai "LINTAS FUNNEL".
- **HP > 50 m tercover tiang saudara** (INFO_HP_TERCOVER_TIANG_SAUDARA): HP > batas ke tiang sendiri tetapi <= batas ke
  tiang cluster saudara yang dilewati jalur kabel -> catatan + saran desain; standar 1 dihitung ulang. Suka Karya: 39 HP
  > 50 m, 27 tercover, 12 tetap reject. Peringatan akses lewat jalur tetap, dengan tiang saudara sebagai alternatif.
- Rekap grup/strand memisahkan irisan diterima vs perlu diperbaiki, dan menghitung HP tercover tiang saudara.
- Saklar profil `cross_1pic_overlap_ok`, `cross_1pic_pole_cover` (bawaan true); false = hasil identik 3.10.0.
- Uji `tests/test_v311.py` (sama funnel, lintas funnel, tanpa data funnel, saklar mati, remarks, rekap grup).

## 3.10.0 – analisis 1 PIC / cluster berdampingan lebih cerdas (review strand Jambi Suka Karya, 13 cluster RT, November 2026)

Status review tidak bergeser: batch Suka Karya 3.9.5 vs 3.10.0 hanya berubah pada temuan yang dimaksud; 5.200 kombinasi
temuan nyata memberi status yang sama, dan teks remarks identik untuk jenis temuan yang tidak diubah.

- **Strand / wilayah induk** (`grup.strands`, `REKAP_STRAND_*.txt/.csv`): cluster dengan funnel sama, BAKP identik atau
  TSSR identik disatukan di atas grup 1 PIC (Suka Karya: 13 cluster, 2 sub-jaringan). Isinya sub-jaringan, rekonsiliasi
  HP TSSR/BAKP/HPDB (TSSR 1.242 HP vs HPDB 1.029 HP) dan remarks strand <= 255 karakter.
- **TSSR strand**: TSSR identik di beberapa cluster -> WARN_TSSR_DIPAKAI_BERSAMA, menggantikan "TSSR 1242 HP vs HPDB n HP".
- **Rekap grup**: irisan BOUNDARY per pasangan dengan baris HP di irisan; irisan < 100 m2 tanpa HP = bersinggungan;
  tiang bersama baru (BOQ ganda) vs eksisting (dicatat dua kali); rencana FDT grup terpadu/tidak terpadu + kapasitas colo
  bersama + sisa kapasitas; remarks grup <= 255 karakter; "file BAKP identik" per pasangan diringkas sekali.
- **Remarks**: HP di boundary tetangga yang seluruhnya di irisan digabung ke frasa tumpang tindih (kedua cluster menyebut
  baris yang sama); irisan urut luas terbesar dengan tiga tingkat; versi rinci tidak menggeser alasan reject berikutnya;
  nama cluster seragam (bug "dgn cluster X" / "dgn X").
- **Jalur berimpit simetris** (A->B = B->A).
- **Cek baru**: WARN_HPDB_CLUSTER_NAME_CAMPUR (label cluster campur, HP pindahan), WARN_BOUNDARY_TIDAK_VALID (poligon
  memotong diri), INFO_NAMA_FILE_HP_BEDA (jumlah HP di nama berkas), kolom wilayah sheet lain yang tertukar (tidak lagi
  dicocokkan ke FINDIM wilayah jauh).
- Modul baru `konsistensi.py` (murni Python); uji `tests/test_v310.py` (29 pemeriksaan).

## 3.9.5 – cek tambahan dari review Jambi, Tegal, Minahasa dan Cianjur (November 2026)

Semua cek lama tetap sama (diuji ulang pada 7 set data: hasil 3.9.4 vs 3.9.5 hanya bertambah temuan baru).

- **TSSR vs HPDB** (baru, `tssr.py`): ID cluster di nama file TSSR, jumlah homepass ("Home Pass and Occupation", juga
  format ribuan `1,242 HP`), dan kelurahan di alamat dibandingkan dengan HPDB. Contoh: TSSR Argenta 6 ber-ID 21100218859
  (HPDB 21100232646); TSSR Nyalindung 177 HP (HPDB 169); TSSR Suka Karya 1.242 HP (TSSR induk RT 014).
- **Area tanpa izin di folder BOUNDARY**: poligon bernama/ber-subfolder `TIDAK DAPAT IZIN`, `NO SPACE`, `tanpa izin`,
  `dilarang`, dsb. tidak lagi dihitung sebagai cakupan cluster. HP di dalamnya = ERROR (standar 5), tiang di dalamnya =
  ERROR, jalur kabel >= 5 m melintasinya = WARNING.
- **Foto evidence**: HP tanpa foto di dekatnya tetapi ada foto berlabel SAMA berjarak > 30 m = WARNING "koordinat HP
  kemungkinan salah" (Minahasa: '?-28' 150 m, '?-29' 202 m). Foto rumah tanpa pasangan HP di HPDB = INFO (Minahasa: 7
  foto). Label dibandingkan ketat ('?-1' bukan '1').
- **Karakter tak terlihat di HPDB** (zero-width space, U+FFFD, kontrol) = WARNING (Tegal: 5 baris).
- **BAKP hasil scan**: INFO + catatan REMARKS bahwa tulisan tangan (Cluster ID/HP, RT/RW, kompensasi, centang verifikasi,
  tanda tangan) wajib dibaca manual. Status remarks tidak berubah karena catatan ini.
- **NP bisa dihapus**: bila dua NP calon hapus bersebelahan dan rentang gabungannya > 60 m, keterangannya diberi
  "jangan dihapus bersamaan dengan ...". Jumlah temuan tetap.
- Daftar periksa BAKP: nama vendor juga diambil dari nama folder cluster (`..._50HP_EKSPANINDO IOH PULSAR`).
- Versi aturan 2026.11-r13.

## 3.9.4 – peta dasar satelit tanpa tulisan "Map data not yet available"
- Penyebab: Esri World Imagery tidak punya citra di semua zoom (Tomohon: ada s.d. zoom 18). Untuk ubin yang tidak ada,
  server mengirim gambar pengganti bertulisan "Map data not yet available"; layer 3.9.2–3.9.3 (zmax 19) menampilkannya.
- Perbaikan: layer dipasang dengan zoom aman 17, lalu Seranta menanyakan zoom asli tertinggi di wilayah QC ke layanan
  `tilemap` Esri (JSON kecil, di latar belakang, QGIS tidak menunggu) dan menaikkan zmax ke 18/19 bila memang ada. Di atas
  zoom asli, ubin diperbesar dengan interpolasi bilinear (halus). Hasil disimpan per wilayah (~150 km).
- Lebih cepat: cache jaringan QGIS minimal 1 GB (bawaan 256 MB), sehingga ubin yang pernah dilihat tampil seketika.
  Layer peta dasar dari versi sebelumnya otomatis diperbaiki.
- Peta laporan HTML: perbaikan yang sama (maxNativeZoom dari tilemap Esri, keepBuffer, tanpa unduh ulang saat zoom).
- Tidak ada perubahan analisis.

## 3.9.3 – pengamanan rilis berlapis
- Uji serangan pada 3.9.2: orang yang membuat kunci sendiri, lalu mengganti kunci dan nama pembuat di `keaslian.py`,
  bisa membuat salinan tampil "ASLI ... ditandatangani <nama lain>". Celah ini ditutup:
  - setiap status keaslian menyebut **sidik kunci** rilis; sidik resmi `92C4-D078-D1FC-1C5B` juga diterbitkan di
    metadata (halaman plugins.qgis.org), NOTICE.md, README.md dan GitHub;
  - cek silang: kunci di `keaslian.py` harus cocok dengan `SIDIK_RESMI` dan dengan sidik di metadata.txt, NOTICE.md dan
    README.md, kalau tidak → TIDAK RESMI (kunci diganti);
  - verifikasi online di dialog About: isi salinan dicocokkan dengan `RILIS_RESMI.json` di GitHub pembuat;
  - pemeriksa independen `scripts/rilis_resmi.py` (pengganti `seranta_rilis.py`) membawa kunci resmi sendiri, tidak
    menjalankan kode paket yang diperiksa, dan menyatakan salinan berkunci lain sebagai PALSU. Juga dipakai untuk Seuntai.
- Tidak ada perubahan analisis.

## 3.9.2 – label umum (RUKO-1) & peta dasar satelit
- Label umum = kata generik + nomor unit (RUKO-1, Toko 2, KIOS A3, Kos No 12) diperlakukan sebagai pengenal lemah, karena
  penomoran seperti ini diulang di setiap deret/lingkungan. Label sama di dua cluster: ERROR hanya bila <= 5 m
  (`generic_label_match_m`); 5–25 m menjadi WARNING "cek citra"; > 25 m tidak dilaporkan. Keterangan menyebut apakah deret
  kedua cluster saling tumpang (kemungkinan disurvei dua kali) atau bersambung (kemungkinan unit berbeda). Berlaku juga di
  dalam satu cluster. Kasus nyata: Tomohon "RUKO-1" L3 vs "Ruko-1" L7, 17 m, deret bersambung → WARNING (sebelumnya ERROR).
- Nama usaha khas, nomor urut survei (?327, ? -37) dan nomor rumah biasa tidak berubah. Uji regresi 3.9.1 vs 3.9.2 pada
  TOMOHON (KMZ saja), JAMBI dan TOMOHON mode HPDB: hanya temuan RUKO di atas yang berubah.
- Peta dasar pembuktian di QGIS: satu layer XYZ Esri World Imagery di dasar daftar layer saat hasil QC dimuat, dipakai ulang
  untuk semua cluster; pilihan Satelit / Peta jalan (OSM) / Tanpa di panel QC Navigator (tersimpan). Ikut di "Copy picture"
  dan laporan Word Navigator. Peta HTML langsung membuka citra satelit bila online.
- Keterangan temuan panjang di shapefile QC dipotong rapi (batas 254 byte), tanpa karakter rusak.

## 3.9.1 – perbaikan paket rilis
- Berkas di dalam zip tidak lagi membawa izin eksekusi (rw-r--r--), sehingga pemeriksaan *File Permissions*
  plugins.qgis.org lolos (skor pindai 100%). Tidak ada perubahan analisis; hasil QC sama dengan 3.9.0.

## 3.9.0 – wilayah induk / paket 1 PIC, lisensi GPL v3 + pasal 7, rilis bertanda tangan
- BOUNDARY yang identik (poligon yang sama disalin ke KMZ beberapa cluster) dilaporkan sekali sebagai boundary induk:
  "boundary KMZ = boundary induk '<nama>' (sama di N cluster lain)". Remarks tidak lagi habis untuk mendaftar cluster
  satu per satu, dan ratusan catatan "HP di tepi BOUNDARY cluster saudara" tidak muncul lagi.
- Ringkasan grup menyebut wilayah induk dan jenis grup: satu jaringan (1 PIC desain), paket survei 1 PIC
  (dokumen/boundary sama, jaringan terpisah), atau berdampingan. Dokumen bersama (BOUNDARY/BAKP identik) disebut dengan
  jumlah clusternya.
- Nama pendek cluster tanpa ID mempertahankan bagian pembeda (RT/RW/lingkungan); frasa tiang ganda punya versi pendek
  agar tetap masuk 255 karakter.
- Lisensi GPL-3.0-or-later dengan syarat tambahan pasal 7: nama pembuat dipertahankan, versi modifikasi berganti nama &
  ditandai, tidak boleh mengaku sebagai pembuat; merek Seranta tidak dilisensikan. Versi s.d. 3.8.2: GPL-2.0-or-later.
- Rilis resmi ditandatangani digital (Ed25519, `RILIS.json`); kepala laporan dan dialog About menampilkan ASLI /
  DIMODIFIKASI / TIDAK RESMI. Kunci, sidik dan tanda tangan disimpan sebagai bilangan (lolos pemindai rahasia
  plugins.qgis.org). Alat rilis: `scripts/seranta_rilis.py`.

## 3.8.2 – lintas cluster mode KMZ saja / KMZ 1 PIC, laporan gabungan
- Cek lintas cluster berjalan pada mode tanpa HPDB dan KMZ 1 PIC yang dipecah per area (tiang ganda, HP di BOUNDARY
  cluster lain, BOUNDARY tumpang tindih, grup 1 PIC); BOUNDARY di akar folder area terbaca; label survei '? -37'
  dicek; penomoran label yang diulang per area tidak dianggap duplikat lintas cluster; jalur berimpit dicatat sebagai info.
- Laporan HTML gabungan REKAP_GRUP_1PIC_*.html / REKAP_BATCH_*.html: tab laporan lengkap tiap cluster, remarks tambahan
  + status per cluster, catatan grup, unduh Word semua cluster + CSV remarks.
- BAKP PDF dengan object stream (CamScanner) terbaca per halaman; ID cluster lain di judul PDF BAKP ditandai; vendor
  tanpa ekstensi file; ID cluster yang belum ada di FINDIM lama (> 90 hari) menjadi catatan; folder EVIDEN dikenali;
  REKAP batch memisahkan kolom Proses dan Remarks; HP yang sudah disebut "> 50 m" tidak diulang sebagai akses.

## 3.8.1 – QC survei tetap jalan tanpa HPDB (QC KMZ saja)
- Alat 1: folder cluster tanpa HPDB (mis. hanya `1 PIC TOMOHON.kmz`) tidak lagi gagal "No homepass spreadsheet". Titik HP
  diambil dari folder HP di KMZ dan hanya cek berbasis KMZ yang dijalankan: tiang, jalur, rentang, jarak dan akses rumah ke
  tiang, HP duplikat koordinat, boundary/Funnel, Design Lite dan lintas cluster.
- Satu KMZ berisi beberapa area (mis. KMZ "1 PIC" dengan beberapa lingkungan, masing-masing punya folder HP, tiang,
  jalur dan BOUNDARY) dipecah otomatis ke `_KMZ_PER_AREA\<area>` dan diperiksa per area, lalu direkap di REKAP_BATCH.
- Cek yang memakai HPDB dilewati: HPDB vs KMZ, ID/alamat, administrasi FINDIM, BAKP otomatis. `HP.csv` dan
  `manifest_input.json` tidak dibuat; titik HP disimpan sebagai `HP_KMZ.shp` (hanya peta/QC, bukan input desain).
- Peringatan jelas di log QGIS, laporan, ringkasan standar dan REMARKS ("TANPA HPDB – bukan review lengkap"); nomor temuan
  memakai urutan titik KMZ (`titik KMZ n`), bukan baris HPDB.
- Mode ini hanya aktif bila tidak ada satu pun HPDB; run dengan HPDB tidak berubah (temuan identik dengan 3.8.0).

## 3.8.0 – anggota FAT dari FAT Coverage, jarak sepanjang jalur, tiang seberang jalan, akses rumah
- QC APD (alat 4) *Rumah terlalu jauh dari FAT*: anggota FAT = HP (endpoint keluaran desain) di dalam poligon FAT Coverage
  milik FAT; jarak diukur sepanjang jalur kabel (graf kabel + drop dari tiang/garis drop), garis temuan mengikuti jalur.
  HP ber-SUPID salah tidak lagi membuat FAT lain "terlalu jauh" (tetap dilaporkan HP_WRONG_FAT_AREA).
- *Rentang tiang ke tiang*: tiang sampai 7 m dari garis kabel (tiang di seberang jalan; lebar jalur jalan sedang 2 × 3,5 m)
  dihitung tiang penopang, sehingga kabel yang menyeberang kiri-kanan jalan tidak menjadi bentang palsu.
- *Tiang nganggur*: NP tidak dilewati kabel = ERROR dengan tikor (lintang, bujur); EP dan tiang yang dilewati kabel feeder
  boleh. Alat 1: NP = WARNING dengan tikor, EP = INFO; tikor juga di remarks.
- Alat 1 – akses rumah (`akses.py`): WARN_HP_JAUH_LEWAT_JALUR (tiang → jalur → rumah > 55 m walau garis lurus ≤ 50 m) dan
  WARN_HP_AKSES_DALAM (rumah > 40 m dari jalur survei: rumah di belakang rumah lain, akses masuk perlu dicek). HP jauh dari
  tiang kini juga mencantumkan tikor.
- Lebih cepat: indeks poligon, ruas kabel dan FAT (6.000 HP / 300 FAT: aturan inti 10,2 s → 1,4 s; FAT_COVERAGE 10 s → 0,1 s).
- Profil: parameter baru `span_side_tol_m` (7 m) dan `hp_access_max_m` (40 m). Versi aturan 2026.11-r10.

## 3.7.0 – menu berbahasa Inggris, satu isian per alat
- Menu, form, opsi, pesan proses dan panel Navigator QC berbahasa Inggris; laporan dan remarks tetap berbahasa Indonesia.
- Setiap alat cukup satu isian (folder); pengaturan lain dipindah ke Advanced dengan nilai bawaan yang sama.
- Handbook bawaan dihapus; deskripsi plugin dipersingkat; changelog di metadata hanya versi terbaru.

## 3.6.2 – siap Qt6 / QGIS 4
- Modul gambar peta (`snapshot.py`) mengimpor Qt hanya lewat `qgis.PyQt`; impor cadangan PyQt5 langsung dihapus sehingga cek Qt6 plugins.qgis.org lulus.
- Tidak ada perubahan aturan atau hasil QC (versi aturan tetap 2026.10-r9).

## 3.6.1 – stabil dan sama hasilnya di semua wilayah
- Jarak pendek di modul murni Python memakai jari-jari ellipsoid WGS84 di lintang setempat (`geodesi.py`), selaras pengukuran ellipsoid QGIS (galat 1,3e-8 terhadap Vincenty, 11 LS – 60 LU).
- Grid pencarian tetangga berukuran meter (sel bujur diperlebar 1/cos lintang, indeks floor): pasangan di tepi radius tidak terlewat; toleransi snap jalur ke tiang dihitung di lintang cluster.
- Urutan tetap: cluster saudara dibandingkan menurut kode/nama/folder, kecocokan setara dipilih menurut urutan baris, penelusuran folder diurutkan; temuan dan remarks tidak bergantung urutan folder, ZIP, atau hash seed Python.
- Luas irisan BOUNDARY dibulatkan sesuai resolusi sampel; shapefile hasil yang tidak lengkap (file lama terkunci di Windows) dilaporkan sebagai gagal tulis.
- Diuji: grup Minahasa dan Jambi dipindah ke 5 wilayah + urutan acak + ulang (0 beda); di QGIS 3.40.14 cluster 209/210/213 dijalankan dua kali dengan urutan terbalik, semua hasil identik. Versi aturan 2026.10-r9.

## 3.6.0 – 1 PIC desain, cluster digabung, remarks otomatis
- Deteksi cluster satu jaringan / satu PIC (tiang bersama, kabel tersambung, sub-folder KMZ cluster lain, BAKP identik, BOUNDARY berdampingan) dan cek grup sekaligus (REKAP_GRUP_1PIC_<ID>.txt/.csv).
- BOUNDARY induk yang memuat cluster saudara (BOUNDARY_MEMUAT_CLUSTER_LAIN), cluster lain yang digabung ke satu HPDB/KMZ (CLUSTER_LAIN_DIGABUNG), folder cluster bertingkat, perbaikan cache batch.
- Cek baru: tiang ganda di KMZ, sheet Pole HPDB vs KMZ, HP tanpa foto evidence, CLUSTER_NAME kosong, nomor rumah beda blok; BAKP dibaca semua halaman.
- Remarks review otomatis (maks 255 karakter, Reject / Approve dgn catatan / Approve, nomor baris HPDB asli). Versi aturan 2026.10-r8.

## 3.5.9 – deteksi duplikat berdasarkan label survei
- Pencocokan bertingkat berdasarkan koordinat, label survei, nama usaha, nomor rumah dan jalan, kemiripan nama, serta jarak antartitik.
- Label survei yang sama diperiksa juga dalam satu cluster (HP_DUPLIKAT_LABEL); parameter toleransi tersedia di profil.
- Versi aturan 2026.10-r7; kategori dasar INTERNAL+RISET dikenali oleh inti QC.

## 3.5.8 – QC lintas cluster
- Pemeriksaan duplikat homepass, homepass di boundary cluster saudara, boundary bertumpuk, dan kode cluster berulang.
- Boundary dan homepass pembanding ditampilkan pada gambar temuan dan peta interaktif.

## 3.5.7 – bukti temuan langsung di laporan
- Panel bukti bertab di setiap temuan HTML: Gambar (statis; salin/unduh PNG) · Aturan vs nilai (syarat, nilai, selisih, %) ·
  Data sumber (kutipan baris HPDB / atribut tiang, FAT/FDT, HP, kabel; kolom penentu disorot; nama berkas) · Jejak (audit).
- Peta interaktif: tombol Salin gambar / Unduh gambar tampilan saat ini (judul, koordinat pusat, skala, utara).
- HP duplikat: baris ganda yang tidak punya titik KMZ tidak lagi dilaporkan terpisah (satu akar masalah, satu temuan).
- Token desain diselaraskan dengan pola sistem desain telco besar (netral merek): aksen petrol-teal, warna status
  fungsional, ikon tingkat berbentuk berbeda (aman buta warna), IBM Plex Mono (OFL) untuk kutipan data.
- 62 uji otomatis.

## 3.5.6 – peta temuan interaktif di setiap laporan
- Laporan HTML alat 1 dan alat 4 kini memuat peta temuan (Leaflet 1.9.4, BSD-2, disematkan; jalan tanpa internet).
- Klik temuan: isi, tindakan, nilai vs batas, panjang garis, gambar, centang review (sinkron), koordinat desimal & DMS,
  objek di sekitar (≤ 25 m), temuan lain di sekitar (≤ 30 m), tautan citra satelit / Earth 3D / Street View.
- Klik objek: atribut lengkap (HP dari HPDB, tinggi tiang, premises & splitter FAT, core kabel, folder KMZ) dan temuan
  yang melekat.
- Peta dasar citra satelit / jalan opsional saat online (atribusi tampil); saring tingkat, lapisan, cari, ukur jarak,
  layar penuh, navigasi keyboard; tombol "Tampilkan di peta" di setiap temuan.
- Tampilan laporan diperbarui: kepala navy–teal, Poppins + Inter tertanam, ubin KPI membulat, mode gelap.

## 3.5.5 – nomor menu sesuai urutan kerja
- Menu: 1 Siapkan Input + QC Survei → 2 Alokasi FDT & FAT (sebelum desain) → (desain otomatis) → 3 Pasca-Desain → 4 QC APD.
- ID algoritma Processing tidak berubah (skrip/model lama tetap jalan); teks bantuan, handbook dan README disesuaikan.

- Handbook interaktif: peta perjalanan Alat 1 → 2 → desain otomatis → 3 → 4 yang bisa diklik (daftar periksa tersimpan),
  pemandu langkah, kamus temuan (125 kode, bisa dicari), uji pemahaman, pencarian, tema terang/gelap, cetak PDF.
## 3.5.4 – koreksi hasil tinjauan ulang data nyata
- BAKP: lencana aplikasi pemindai ("Dipindai dengan CamScanner") yang tertanam kecil di setiap halaman tidak lagi dilaporkan
  sebagai stempel/tanda tangan ditempel digital (sebelumnya positif palsu ERROR pada BAKP Minahasa Roong).
- Alat 1: rentang tiang yang muncul dua kali karena dua garis jalur bertumpuk dinilai sekali (temuan bentang 50–60 m dan
  kabel rendah tidak lagi ganda); jumlah rentang ganda dicatat di laporan.
- 60 uji otomatis.

## 3.5.3 – hasil QC lebih tepat dan jelas
- Alat 1 standar 4: rumah yang sama (no. rumah HPDB = nama titik KMZ) dengan koordinat bergeser 5–30 m dilaporkan sekali
  sebagai `HP_BERGESER` (perlu ditinjau), bukan dua temuan "tidak ada" (galat GPS ponsel 7–13 m di permukiman).
- Titik di folder DUPLIKAT/ERROR KMZ hanya dihitung sebagai duplikat, tidak lagi sebagai "KMZ tidak ada di HPDB".
- Catatan cakupan bila KMZ ≥ 1,5× HPDB dan bila CLUSTER_NAME HPDB bercampur.
- Alat 4: garis folder "Keterangan Infra" adalah penanda, bukan kabel (slack, BOM, rasio pancingan tidak lagi terpengaruh).
- Pancingan tidak ditandai "tanpa status COLO/NEW INFRA".
- QC-06: bila sebagian perangkat belum bisa dicek, status "Belum bisa dicek" (bukan "Lolos").
- Aturan lolos yang punya keterbatasan cakupan ditulis "Lolos dengan catatan" di HTML dan Word.
- Versi aturan di laporan = versi logika kode (2026.10-r5), bukan angka lama di file profil.
- 59 uji otomatis (uji baru `tests/test_v353.py`).

## 3.5.2 – laporan interaktif, gambar temuan dan laporan Word
- Setiap temuan punya ID tetap (F-0001 di alat 1, ID temuan di alat 4) yang sama di HTML, Word, layer temuan dan Navigator QC.
- Gambar peta per temuan (sorotan geometri, label tiang/perangkat, skala, arah utara; tanpa peta dasar/internet) di
  folder `QC_GAMBAR`, tertanam di HTML dan Word.
- Laporan Word (`<KODE>_LAPORAN_QC.docx`, `QC_APD_LAPORAN.docx`): ringkasan per aturan/standar, lalu satu bagian per temuan
  (arti, tindakan, nilai vs batas, lokasi, dasar aturan, kolom catatan reviewer, gambar peta).
- Laporan HTML bergaya sistem desain perusahaan (netral merek, huruf Inter, warna kontras WCAG AA, mode gelap): ubin KPI,
  tautan langsung `#F-0001`, pintasan keyboard (j/k/x/g/o/?), status "sudah dicek" per temuan + rekap review CSV, gambar
  bisa diperbesar, tombol unduh Word.
- Navigator QC: tombol "Salin gambar" (tempel langsung di Word) dan "Laporan Word" untuk temuan yang tampil (gambar dari
  peta QGIS saat itu).
- Tinggi kabel tengah bentang: tanam tiang 1/6 panjang (standar konstruksi jaringan distribusi nasional), lendutan desain
  1,5 %, pita tinjau 4,7–5 m (NESC 232-1) hanya diringkas, catatan per rentang hanya bila < 4,7 m.
- Label bentang dan tinggi kabel tidak lagi menyatu (bentang di atas garis, tinggi kabel di bawah garis putus-putus).
- Alat 1 yang dijalankan dua kali dalam satu sesi QGIS tidak lagi gagal menulis ulang QC_TEMUAN (status review lama
  dibaca langsung dari .dbf, tanpa mengunci file).
- Standar 7 (colo FDT) yang tidak terpenuhi kini "perlu ditinjau" (keputusan perencanaan), bukan "wajib diperbaiki".
- 55 uji otomatis.

## 3.5.1 – toleransi berbasis acuan (lolos / tinjau / gagal)
- Alat 1: HP yang hanya beberapa meter di luar garis BOUNDARY KMZ dicatat INFO "di tepi BOUNDARY" (toleransi GPS ponsel,
  bawaan 10 m; GPS.gov 4,9 m langit terbuka, Merry & Bettinger PLOS ONE 2019 7–13 m urban). Lebih jauh dari itu tetap
  "wajib diperbaiki". Jarak dan batas kini tercatat di setiap temuan BOUNDARY, Funnel dan jarak HP ke tiang.
- Alat 1: double tagging Design Lite punya pita tinjau (HP 2–5 m, tiang baru 1,5–10 m); tiang survei yang tidak dilewati
  jalur menjadi WARNING (tinjau), bukan wajib diperbaiki.
- Alat 3: vonis link budget memakai nilai redaman desain (1:4 7,25 dB, 1:8 10,38 dB, konektor 0,25 dB) + margin 3 dB;
  nilai maksimum komponen (worst-case) dilaporkan sebagai "budget tipis" agar cadangan tidak dihitung dua kali.
- Alat 4: jarak slack hanya dinilai pada kabel baru (kabel existing/colo diabaikan); ekor kabel setelah FAT terakhir yang
  masih dalam batas loop (100 m / 2 bentang) menjadi WARNING; jumlah bentang dihitung sebagai bentang, bukan tiang.
- Alat 2: toleransi FAT melayang diambil dari profil.
- QC-01 grouping: FDT desain ini yang sudah tercatat di data jaringan existing terbaru (lokasi sama) atau di rekap kode
  tidak lagi dianggap "kelompok dipakai di tempat lain".
- Parameter profil baru beserta sumbernya; 54 uji otomatis.

## 3.5.0 – daftar kerja reviewer & kelengkapan audit
- `QC_APD_TEMUAN.xlsx`: sheet Ringkasan, Temuan (arti, tindakan, bukti, file sumber, tautan peta, pilihan status review yang dibaca kembali saat QC diulang), Kelengkapan input, Grouping FDT.
- Tabel kelengkapan data masukan di laporan HTML dan JSON.
- Setiap temuan berisi bukti, file sumber, lingkup jaringan dan lokasi.
- QC-01: kandidat grouping FDT dari jaringan existing (kelompok area, FDT terdekat, kode kandidat).
- Navigator QC: filter per aturan dan per lingkup Feeder/Distribution.
- Aturan yang datanya kurang tetap "Belum bisa dicek" walau hanya menambah catatan INFO.

## 3.4.1
Lolos pemindaian keamanan plugins.qgis.org (Bandit, detect-secrets, flake8, Qt6); metadata teks biasa.

## 3.4.0 – edisi publik
- Laporan HTML baru untuk alat 1–4: kalimat keputusan, jalur aturan, penjelasan "yang dicek / kenapa penting / yang
  dilakukan" per aturan, setiap temuan dalam bahasa sederhana dengan tautan peta, saring dan cari, huruf tertanam,
  mode gelap, siap cetak PDF.
- Tujuh aturan paket APD (QC-01..QC-07) dengan pemisahan lingkup Feeder/Distribution dan satu FDT logis lintas paket.
- Objek temuan memakai kode perangkat; nama proyek dari folder.
- Parameter profil baru beserta sumbernya; profil organisasi dapat disimpan di luar plugin.
- Teks dan profil netral; ikon KMZ tertanam; tautan peta OpenStreetMap.
- 42 uji otomatis termasuk skenario penerimaan S01–S10; CI dan rilis otomatis.

## 3.3.0
Alat 4 (QC paket desain), profil standar JSON bersumber, status review di Navigator QC, perbaikan hasil uji lapangan.

# Dasar Teknis Aturan QC — Seranta - FTTH Design Assistant (v3.3.0)

Copyright (C) 2026 Joseph Edward Timothy Siahaan (GPL-3.0-or-later + syarat tambahan pasal 7, lihat LICENSE). Dokumen ini menjelaskan **untuk apa** setiap
pemeriksaan dilakukan dan **dari mana** setiap ambang berasal. Nilai yang dipakai plugin tersimpan di
`profiles/*.json` (profil standar). Setiap parameter di sana memuat nilai, kategori dasar, sumber, dan status
pengesahan. Setiap temuan mencatat `profile_id` dan `rule_version` (2026.10-r1).

## Kontrak keluaran QC (spesifikasi O.2, selaras ISO 19157)
| Tingkat | Arti | Dihitung lolos? |
|---|---|---|
| **ERROR** | Pelanggaran terverifikasi terhadap aturan yang berlaku. Wajib diperbaiki atau disetujui sebagai pengecualian. | tidak |
| **WARNING** | Potensi ketidaksesuaian atau aturan yang perlu ditinjau, mis. 50–60 m di atas Perwal, atau 120–150 m yang butuh justifikasi. | tidak (perlu review) |
| **INFO** | Petunjuk atau peluang optimasi. | — |
| **UNVERIFIED** | Data atau aturan belum cukup untuk memutuskan, mis. BOM, paket Feeder, atau layer Voronoi tidak ada. | **tidak pernah** |
| **PASS** | Aturan dijalankan dengan data lengkap dan tidak ada temuan. | ya |

ISO 19157:2013 / 19157-1:2023 menetapkan bahwa hasil kesesuaian (`DQ_ConformanceResult.pass`) hanya boleh berasal
dari evaluasi yang benar-benar dijalankan. Karena itu UNVERIFIED tidak pernah ditulis sebagai lolos.

Status review temuan dicatat di Navigator QC: OPEN, VERIFIED, FALSE_POSITIVE, APPROVED_EXCEPTION, RESOLVED.
APPROVED_EXCEPTION wajib disertai alasan dan nama pemberi persetujuan (X-04).

## Kategori dasar
- **REGULASI**: regulasi Indonesia.
- **STANDAR**: ITU-T, GR-1209, atau standar konstruksi jaringan distribusi.
- **PRAKTIK**: praktik industri (operator/vendor) yang dikutip jurnal atau dokumen teknis.
- **RISET**: jurnal peer-review.
- **INTERNAL**: kebijakan internal, yaitu Handbook KMZ dan config desain otomatis. Sah sebagai kebijakan proyek, tetapi bukan standar nasional.

Parameter berstatus **NOT_APPROVED** adalah parameter rekayasa yang masih harus dikalibrasi atau disahkan,
mis. sudut belok, toleransi snap, dan toleransi FAT ke tiang.

## Referensi utama
- **Permen PU 20/PRT/M/2010** Ps. 12(6): utilitas di atas tanah ≥ 5 m dari permukaan jalan tertinggi. Status "Berlaku" di JDIH BPK dan NSPK Bina Marga; tidak ditemukan Permen PUPR pengganti. PP 34/2006: ruang bebas jalan arteri/kolektor ≥ 5 m.
- **Perwal Yogyakarta 13/2018**, **Perwal Pekalongan 21/2024** (lendutan kabel ≥ 6 m), **Perwal Tangerang Selatan 3/2019 jo. 47/2019** Ps. 5J: jarak antar tiang ≤ 50 m. **Rancangan Permenkominfo 2018** (Pedoman Teknis Infrastruktur Bersama): ≤ 50 m, belum diundangkan sehingga hanya acuan. **Buku pedoman konstruksi jaringan distribusi TR (2010)**: span TR ≤ 50 m; tiang sudut > 30° wajib tambat.
- **ITU-T G.984.2 (08/2019, in force)**: B+ 13–28 dB, C+ 17–32 dB. **ITU-T G.9807.1** (XGS-PON): N1 29, N2 31, E1 33 dB.
- **GR-1209** (datasheet splitter PLC): 1:4 7,0–7,3 dB (maks 7,7), 1:8 10,2–10,5 (maks 11,2), 1:16 13,5–13,7 (maks 14,2). Nilai **maks** dipakai sebagai worst-case.
- **Farooq dkk., arXiv:1509.05958**: serat 0,35 dB/km, konektor ≈ 0,2 dB, splice 0,1 dB, margin 3 dB.
- **spesifikasi teknis FTTH operator nasional** (PED F-002-2015; Dokumen Instalasi PPJ FTTH 2013): kelenturan kabel 2 % panjang gawang; ODP-8/16; slack 5 m sebelum dan sesudah closure; tiang 7 m di sisi jalan dan 9 m saat melintas jalan (juga RKS FO Diskominfo Jateng 2024).
- **GPS.gov**: GPS ponsel ±4,9 m di langit terbuka. **Merry & Bettinger, PLOS ONE 14(7) e0219890 (2019)**: galat 7–13 m di perkotaan.
- **K-Means/K-Medoids penempatan ODP** (Transient Undip 2019, 2023): mendukung FAT di medoid HP yang digeser ke tiang.
- **Handbook KMZ internal** (34 kasus QC hlm. 22–40) dan **config desain otomatis** splitter 1x4 / 1x8: FAT 8–16 (target 15), MAXPPDIST 120/130 m, FDT 384/480 HP, splitter 1:4 maks 12 / 1:8 maks 8, COLO ≤ 1 km, slack 250 m, loop ≤ 100 m / 2 span.

## Alat 1 — QC strand
| Pemeriksaan | Nilai (profil APD_1X4) | Tingkat | Dasar |
|---|---|---|---|
| Jarak HP ke tiang terdekat | > 50 m | ERROR | INTERNAL (Handbook kasus 12), sejalan span 50 m |
| HP di RFS DONE / RFS EXT / funnel aktif lain | ada | ERROR | Standar Review Strand |
| Wilayah HPDB vs FINDIM | beda | ERROR | data resmi operator |
| HP duplikat koordinat (≤ 0,5 m) / ID | ada | ERROR | satu rumah satu homepass |
| Kemungkinan duplikat | 0,5–**5 m** (naik dari 3 m), nomor rumah sama/kosong | INFO | RISET: GPS ponsel 4,9 m |
| HP duplikat **lintas cluster** (folder cluster saudara di folder induk) | koordinat ≤ 0,5 m; label survei ?NNN / nama usaha sama ≤ **25 m** (25–50 m WARNING); no. rumah biasa sama ≤ **15 m** (≤ 30 m bila nama jalan sama) | ERROR | pola temuan tim QC (review Jambi 2026); RISET: GPS ponsel 7–13 m urban |
| HP duplikat **label** di dalam satu cluster (HP_DUPLIKAT_LABEL) | aturan label yang sama, titik bergeser > 0,5 m | ERROR | pola temuan tim QC |
| Mungkin duplikat lintas cluster | nama mirip ≥ 85 % ≤ 30 m; dua titik ≤ 2 m beda label; label umum (RUKO-1, TOKO 2) sama 5–25 m | WARNING | salah ketik / satu bangunan / nomor unit dipakai ulang per deret |
| Label umum sama (kata generik + nomor unit) | ERROR hanya ≤ **5 m** (`generic_label_match_m`); 5–25 m WARNING cek citra; > 25 m tidak dilaporkan | ERROR / WARNING | review Tomohon 2026 (RUKO-1 L3 vs Ruko-1 L7, 17 m, deret bersambung); RISET: GPS ponsel 4,9 m langit terbuka |
| Kemungkinan duplikat lintas cluster | 0,5–5 m, no. rumah kosong | INFO | GPS.gov 4,9 m |
| HP di dalam BOUNDARY cluster saudara | > 10 m dari garis = ERROR; ≤ 10 m = INFO tepi | ERROR/INFO | Standar Review Strand; toleransi GPS ponsel |
| BOUNDARY tumpang tindih dengan cluster saudara | irisan berisi HP dan lebar > 10 m = WARNING; irisan tipis = INFO | WARNING/INFO | satu rumah satu cluster |
| ID cluster dipakai cluster lain | ID 9–12 digit di nama file HPDB/KMZ sama | WARNING/INFO | ID cluster unik |
| HP di luar Funnel | > **15 m** dari tepi = ERROR; ≤ 15 m = INFO tepi (naik dari 10 m) | ERROR/INFO | RISET: 7–13 m urban |
| Rentang tiang NP–NP / NP–EP (sepanjang jalur) | > 60 m | ERROR | INTERNAL (Handbook kasus 9) |
| Rentang 50–60 m | di atas Perwal | **WARNING** (sebelumnya info) | REGULASI daerah |
| Profil "Perwal ketat" | > 50 m | ERROR | Perwal Yogyakarta/Pekalongan |
| Kabel rendah tengah bentang | tinggi klem − **2 %**·L < 5 m (6 m pada profil Perwal) | INFO | Permen PU 20/2010; praktik operator 2 % |
| Ujung jalur tanpa tiang (derajat 1) | ada | ERROR | praktik operator: tambat akhir di tiang |
| Belokan tanpa tiang | ≥ 30° WARNING; 15–30° INFO; sambungan lurus **tidak** ditandai | WARNING/INFO | pedoman konstruksi jaringan distribusi TR (NOT_APPROVED, kalibrasi) |
| Percabangan tanpa tiang | ada | WARNING | Handbook: jalur harus ada akses pole |
| Tiang nganggur | NP tidak dilewati jalur = WARNING (tahap survei; tikor di keterangan); EP = INFO (boleh) | WARNING/INFO | Handbook kasus 25; aturan tim QC: NP tidak boleh nganggur, EP/tiang feeder boleh |
| HP jauh lewat jalur/akses | garis lurus ≤ 50 m tetapi tiang → jalur → rumah > 55 m (50 m + galat GPS 5 m) | WARNING | Handbook 50 m; drop mengikuti akses ke tiang (lead-in path, Biarri FOND) |
| HP akses dalam | rumah > 40 m dari jalur survei terdekat (rumah lapis kedua/ketiga; 30 m + galat GPS 10 m) | WARNING | izin warga/BAKP; parameter desain (NOT_APPROVED) |
| BAKP | tidak ada sumber = UNVERIFIED (BAKP_NOT_SUPPLIED); dikenali dari isi/ID cluster = UNVERIFIED kandidat (BAKP_UNRECOGNIZED); dipilih manual = BAKP_MAPPED | — | spesifikasi O.1 / X-01 |
| Manifest input | jumlah HP shp = csv = HPDB, ID unik dengan format H00001, koordinat di Indonesia, ROADS tidak kosong | PASS/ERROR/UNVERIFIED | Langkah Input Desain Otomatis APD |

### Turunan teori (kabel tengah bentang, lendutan 2 %)
| Tiang | Tinggi klem* | Tengah bentang 40 m | Tengah bentang 50 m | vs 5,0 m |
|---|---|---|---|---|
| 6 m | ±4,5 m | ±3,7 m | ±3,5 m | hanya gang |
| 7 m | ±5,4 m | ±4,6 m | ±4,4 m | tidak untuk crossing → tiang 9 m |
| 9 m | ±7,2 m | ±6,4 m | ±6,2 m | lolos (juga 6 m Perwal) |

\*Tinggi klem = H − (10 % H + 0,6 m) − 0,3 m. Rumus tanam 10 % + 0,6 m (RUS 1724E-200) memberi hasil yang mirip dengan aturan tanam 1/6 panjang tiang.

### Mengapa perlu cek lintas cluster (3.5.8)
Sub-cluster satu wilayah survei (contoh review Jambi: Pasir Putih RT 05, RT 22, RT 23, RT 24) berada di dalam **satu**
poligon Funnel induk ("RT 023 PASIR PUTIH", HP plan 2192) dan memakai BAKP induk yang sama. Cek Funnel (standar 2 dan 5)
karena itu selalu lolos, padahal titik HP yang sama disalin ke dua cluster dan BOUNDARY KMZ saling tumpang tindih.
Pembanding yang benar adalah HPDB + KMZ cluster saudara. Saran cluster pemilik: (1) cluster yang BOUNDARY-nya memuat rumah;
(2) bila keduanya/tidak satu pun, cluster yang rumahnya lebih dalam di BOUNDARY (selisih ≥ 3 m); (3) bila setara, cluster
dengan tiang terdekat (kabel drop lebih pendek). Parameter `cross_name_match_m` berstatus NOT_APPROVED (perlu kalibrasi).

## Alat 2 — Alokasi FDT & FAT (estimasi)
| Langkah | Nilai | Dasar |
|---|---|---|
| FAT minimum | ceil(HP/16); 16 = 2 × 1:8 (ODP-16) | PRAKTIK operator; INTERNAL config 8–16 |
| HP–FAT | drop + jalur ≤ 120 m (path length seperti MAXPPDIST desain otomatis) | INTERNAL config |
| Satu FAT per tiang | FAT tidak bertumpuk di tiang yang sama | Handbook kasus 30 |
| Kapasitas FDT | 24 FAT = 384 HP; dibatasi juga oleh output splitter tersisa | INTERNAL |
| Penugasan | FDT terdekat ≤ 1 km diisi penuh dulu | RISET (Kim dkk., EJOR 2011); INTERNAL |
| Minimum FAT per FDT existing | FDT existing dengan sisa < 4 FAT dilewati (kecuali cukup untuk semua sisa FAT) | INTERNAL, NOT_APPROVED: satu rute 24D (±12 FAT) dari FDT jauh untuk 1–3 FAT tidak efisien; Handbook "penuhi satu FDT dulu" |
| FDT kode sama | ikon dengan kode sama ≤ 150 m = satu perangkat; desain cluster sendiri di Design Lite tidak dihitung dua kali | Handbook kasus 14; kode FDT unik per perangkat |
| Link budget | serat 0,35 dB/km + splitter **worst-case** 1:4 7,7 + 1:8 11,2 dB + 4 × 0,5 + 10 × 0,1 + margin 3 dB ≤ B+ 28 / C+ 32 dB | STANDAR ITU-T G.984.2, GR-1209 |

Dengan feeder 5 km, konfigurasi 1:4 × 1:8 (1:32) menghasilkan ±26,7 dB. Hasil ini masih ≤ 28 dB, tetapi sisa margin hanya ±1,3 dB.

## Alat 1 — catatan hasil uji lapangan 3.3.0
- Rentang yang melebihi batas kurang dari akurasi GPS ponsel (±5 m) tetap CEK, tetapi diberi catatan "ukur ulang di lapangan" (selisih ukur bukan bukti pelanggaran; GPS.gov, Merry & Bettinger 2019).
- Titik foto bukti (sub-folder EVIDANCE/EVIDENCE di dalam folder HP) dipakai untuk memasangkan HPDB, tetapi tidak dilaporkan sebagai HP lebih.

## Alat 4 — QC APD pasca-desain (34 kasus Handbook KMZ)
| Aturan (rule_id) | Kasus | Logika ringkas | Tingkat | Data kurang → |
|---|---|---|---|---|
| SERVED | Tools hlm. 3–4 | SERVED tidak terlayani / SUPID kosong / CONNSTATUS beda dari mayoritas | ERROR / WARNING | UNVERIFIED |
| FAT_COVERAGE | 8 | HP di luar semua poligon (toleransi tepi 0,5 m), tumpang tindih, HP di coverage FAT lain | ERROR / WARNING | UNVERIFIED |
| CABLE_END | 1, 34 | Graf kabel: ujung derajat 1 tanpa FAT ≤ 3 m. Closure = INFO. Ekor > 100 m atau > 2 span = WARNING | ERROR / WARNING | UNVERIFIED |
| MULTI_FDT | 2, 22 | Induk FAT dari SUPID, hirarki ELEMENTID, dan awalan kode. Klaim ganda = ERROR. Per FDT: HP ≤ 384, splitter ≤ 12, premises ikon = jumlah HP | ERROR | UNVERIFIED |
| FAT_HP_DISTANCE | 15 | Anggota FAT = HP (endpoint keluaran desain) di dalam poligon FAT Coverage milik FAT itu (tanpa coverage: SUPID). MAXPPDIST > 150 m ERROR; 120–150 m WARNING. Tanpa MAXPPDIST: jarak **sepanjang jalur kabel** (Dijkstra) + drop dari tiang/garis drop ke rumah; garis lurus hanya bila jalur tidak tersambung (batas bawah) | ERROR / WARNING | UNVERIFIED |
| FAT_CODE | 11, 32 | Nomor D-xx melompat, kode ganda, awalan beda dari FDT, urutan vs SUPDIST, panjang label | WARNING / INFO | UNVERIFIED |
| FAT_ON_POLE | 3 | FAT > 2 m dari tiang (FAT melayang) | WARNING | UNVERIFIED |
| POLE_IDLE | 25 | Tiang **NP** > 7 m dari semua kabel distribusi/feeder = ERROR dengan tikor. EP boleh nganggur (dicatat, bukan temuan); tiang yang dilewati feeder dan tiang di seberang jalan (3–7 m) dihitung dipakai | ERROR | UNVERIFIED |
| SPAN_APD | 9 | Rentang antar tiang berurutan di sepanjang kabel > 60 m ERROR, > 50 m WARNING. Tiang penopang = tiang ≤ 7 m dari garis kabel (lebar jalur jalan sedang 2 × 3,5 m), termasuk tiang di seberang jalan (kabel menyeberang kiri-kanan) | ERROR / WARNING | UNVERIFIED |
| FAT_CENTER | 6, 33 | Rata-rata jarak HP ke FAT > 1,5 × titik paling sentral; grouping melewati FAT lain | INFO (REVIEW) | UNVERIFIED |
| SLACK | 21 | Jarak antar penanda slack > 250 m | WARNING | UNVERIFIED_SLACK |
| CROSSING | 17, 19, 27 | Kabel memotong layer rel/tol | WARNING | UNVERIFIED_REFERENCE |
| FDT_COLO_NEW | 13, 14 | Matriks bagian N: FDT hilang di Feeder/Distribusi = ERROR; posisi bergeser > 5 m = ERROR; NEW: FAT tak tersambung graf = ERROR; status UNKNOWN = UNVERIFIED | ERROR | UNVERIFIED_DATASET |
| BOM | 22, 23, 29 | HP/FAT/FDT/tiang/closure harus sama persis. Kabel: desain + slack 10 m per perangkat ± 5 %. Satuan km dinormalkan ke meter. Item existing dipisahkan | ERROR / WARNING | UNVERIFIED_BOM |
| KMZ_APD | 5, 18, 20, 28, 31 | Folder wajib dan rename (Homepass, FAT Coverage), ikon X, warna kabel 24/48/96/144, keterangan kabel, folder Existing untuk COLO, visibilitas | ERROR / WARNING / INFO | UNVERIFIED |

Kasus 16 (COLO ke cluster DROP), 24 (jenis tiang vs strand), 26 (alokasi tube), 27 (tiang 9 m di jalan lebar) dan 30
(tumpang tindih dengan existing) membutuhkan data Macro, splice plan, atau kelas jalan. Tanpa data tersebut kasus
ini dilaporkan **UNVERIFIED**, bukan lolos. Kasus 23/26 dicek oleh alat 3 dari splice plan.


## Tambahan 3.6.0 (review Jambi, Tegal, Minahasa — Oktober 2026)
| Kode | Logika | Tingkat | Dasar |
|---|---|---|---|
| CLUSTER_LAIN_DIGABUNG | ≥ 5 HP (dan ≥ 10 % HP) di satu Funnel aktif milik cluster lain (bukan RFS, bukan reject). Dilaporkan sekali, HP itu tidak dilaporkan lagi sebagai HP_DI_FUNNEL_LAIN/HP_LUAR_FUNNEL | ERROR | Satu cluster satu ID/Funnel; FINDIM OLT CLUSTER |
| BOUNDARY_MEMUAT_CLUSTER_LAIN | BOUNDARY KMZ cluster ini memuat ≥ 50 % (min. 5) HP cluster saudara = BOUNDARY induk/gabungan yang belum dipotong setelah split. Cluster saudara mendapat satu INFO_HP_DI_BOUNDARY_INDUK_CLUSTER_LAIN (bukan ERROR per HP) | ERROR | Satu rumah satu cluster; review Jambi 2026 (Bagan Pete RT 04 memuat 158/212 HP Pinang Merah, 85/93 HP Simpang Rimbo) |
| INFO_SATU_PIC_DESAIN | Cluster saudara ≤ 2 km dengan: tiang sama koordinat (≤ 1 m), jalur kabel tersambung (≤ 1,5 m), atau sub-folder KMZ ber-ID cluster lain = satu jaringan; BAKP identik atau BOUNDARY ≤ 5 m (jarak ≤ 300 m) = kemungkinan 1 PIC | INFO | Review paket bersama |
| WARN_TIANG_GANDA_LINTAS_CLUSTER | Tiang cluster ini ≤ 1 m dari tiang cluster saudara | WARNING (menghalangi Approve di remarks) | Satu tiang satu catatan BOQ |
| INFO_HP_TEPI_FUNNEL_LAIN | HP ≤ toleransi Funnel (15 m) di dalam Funnel lain dan ≤ 15 m dari/di dalam Funnel sendiri | INFO | Galat GPS ponsel 4,9 m (GPS.gov), 7–13 m urban (PLOS ONE 2019) |
| WARN_TIANG_DUPLIKAT_KMZ | Titik tiang di KMZ koordinat sama atau ≤ 1 m (dua folder) | WARNING | BOQ |
| WARN_POLE_SHEET_BEDA_KMZ | Sheet tiang HPDB: tinggi beda, posisi > 5 m, baris koordinat ganda | WARNING | Konsistensi HPDB-KMZ |
| WARN_HP_TANPA_EVIDENCE | HP tanpa foto ≤ 5 m atau berlabel sama ≤ 30 m (Evidence*.xlsx + folder EVIDENCE KMZ) | WARNING | Standar Review Strand |
| WARN_CLUSTER_NAME_KOSONG | CLUSTER_NAME kosong/'-' | WARNING | Format HPDB |
| WARN_ADMIN_ID_CLUSTER_TIDAK_TERDAFTAR | ID tidak ada di OLT CLUSTER dan lebih besar dari ID terbesar berawalan 7 digit sama | WARNING | Data referensi tertinggal |
| Duplikat label | Nomor rumah sama di blok berbeda (HOMEPASS_ADDRESS_BLOCK terisi keduanya) bukan duplikat | — | Alamat |
| Tinggi tiang | 'NP-11' (tanda hubung) = nomor urut; NP+angka tanpa 'M' hanya 6/7/9 m | — | Review Jambi |
| BAKP | Semua halaman (maks 40); set baru = halaman mirip halaman 1 (beda hash ≤ 50 dari 256 bit; uji: awal set 11–38, lainnya ≥ 87) | — | — |

Remarks otomatis (remarks.py): status Reject bila ada ERROR atau WARNING penghalang (BOUNDARY tumpang tindih ber-HP, tiang
dua cluster, ID ganda); temuan berselisih ≤ 1 m dari batas (rentang, jarak HP-tiang) dan FINDIM yang tertinggal hanya menjadi
catatan; stempel tempelan di BAKP gabungan yang hanya ada di sebagian set dicantumkan sebagai "cek", bukan otomatis reject;
belokan tepat di batas sudut (≤ batas + 1°) dengan tiang ≤ 25 m dari belokan hanya catatan. Pasangan label survei sama dan
irisan BOUNDARY ditulis dengan nomor baris HPDB asli (baris HP cluster saudara disebut dengan ID cluster-nya).

Cek grup 1 PIC (grup.py): anggota grup = cluster yang terhubung sinyal INFO_SATU_PIC_DESAIN secara berantai (A-B dan
B-C = satu grup). Status grup Reject bila salah satu anggota Reject; Belum lengkap bila ada anggota yang folder-nya tidak
ada; total HP grup menentukan kebutuhan splitter/FDT bersama; tiang yang tercatat di dua KMZ dihitung sekali.

Mode batch: hasil "cluster jauh" (> 2 km, HPDB tidak dibaca) disimpan bersama kotak batasnya dan dihitung ulang untuk
cluster berikutnya, sehingga cluster yang jauh dari cluster pertama tetap dibandingkan dengan tetangganya.

## Batasan
- Dokumen operator asli tidak tersedia daring. Angka operator diambil dari salinan dan kutipan jurnal, dan nilainya bervariasi (drop 100–200 m).
- Lampiran Kominfo 2018 masih berupa rancangan, dan Perwal hanya berlaku di kotanya masing-masing. Karena itu nilai 50 m dijadikan WARNING pada profil bawaan dan ERROR pada profil "Perwal ketat". Sebelum go-live, tim perizinan perlu memastikan Perda/Perwal di kota proyek.
- Toleransi BOM (5 %) dan sudut belok (15°/30°) adalah parameter rekayasa (NOT_APPROVED). Keduanya harus dikalibrasi dengan desain nyata dan disahkan reviewer.
- Arti kode CONNSTATUS desain otomatis belum terdokumentasi di handbook. Plugin hanya menandai nilai yang berbeda dari mayoritas.
- Semua hasil adalah alat bantu. Keputusan desain dan pengecualian tetap berada pada desainer dan reviewer.

## Tambahan 3.6.1 — stabilitas dan invariansi wilayah

- **Jarak**: semua jarak pendek di modul murni Python (lintas cluster, sheet Pole, evidence, grup) memakai jari-jari kelengkungan ellipsoid WGS84 di lintang setempat (`geodesi.py`), sama dengan pengukuran ellipsoid QGIS. Galat maks 1,3e-8 terhadap Vincenty di 11 LS – 60 LU (sebelumnya konstanta ekuator, galat s.d. 0,04 %). Toleransi 0,5 m / 1 m / 5 m / 25 m bermakna sama di Aceh, Jawa, NTT maupun Papua.
- **Grid pencarian tetangga** berukuran meter: sel bujur diperlebar 1/cos(lintang terjauh), indeks memakai floor; pasangan di tepi radius tidak pernah terlewat (240 kasus uji tepi radius, 0 terlewat).
- **Toleransi snap jalur ke tiang** dikonversi ke derajat dari skala WGS84 di lintang cluster.
- **Urutan tetap**: cluster saudara dibandingkan berurutan (kode, nama, folder); kecocokan setara dipilih berdasarkan urutan baris; penelusuran folder (referensi, BAKP, evidence) diurutkan. Temuan dan remarks tidak bergantung urutan folder di disk/ZIP maupun hash seed Python.
- **Luas irisan BOUNDARY** dibulatkan sesuai resolusi sampel (1 / 5 / 10 / 100 m²) agar tidak menampilkan ketelitian semu.
- **Penulisan hasil**: shapefile hasil yang .shx/.dbf-nya tidak terbentuk (file lama masih dipegang koneksi OGR di Windows) dilaporkan sebagai gagal tulis, tidak lolos diam-diam.
- **Uji di QGIS 3.40.14**: 209 (+210 lewat grup), 213, 210 dijalankan dua kali dengan urutan terbalik → semua QC_TEMUAN, layer QC/*, REMARKS, LAPORAN_INPUT dan REKAP_GRUP identik.
- **Uji**: grup Minahasa (209/210, 211/213) dan Jambi (Pinang Merah, Simpang Rimbo, Bagan Pete) dipindah ke Aceh, Papua, NTT, Kalimantan, Jakarta + 5 urutan acak + ulang + 4 hash seed → 33 + 4 run, 0 beda temuan dan remarks.

## Tambahan 3.8.0 — anggota FAT dari FAT Coverage, jarak sepanjang jalur, tiang seberang jalan, akses rumah

Permintaan tim QC (dokumen *improve QC QGIS*) dan kasus grup lapangan (HP > 50 m dari tiang; rumah di belakang rumah lain):

- **Rumah terlalu jauh dari FAT (alat 4)**: anggota FAT kini ditentukan oleh **poligon FAT Coverage** milik FAT (endpoint
  keluaran desain otomatis). HP yang SUPID-nya menunjuk FAT jauh tetapi letaknya di coverage FAT lain tidak lagi membuat
  FAT itu "terlalu jauh" (kesalahan SUPID tetap dilaporkan oleh FAT_COVERAGE sebagai HP_WRONG_FAT_AREA). Jarak diukur
  **sepanjang jalur kabel** (graf kabel distribusi/pancingan/drop, Dijkstra) sampai tiang drop terdekat lalu ke rumah, atau
  sampai ujung garis drop bila digambar. Garis temuan di peta mengikuti jalur itu. Dasar: desain otomatis menghitung
  MAXPPDIST lewat jalur; drop mengikuti *lead-in path* ke tiang/struktur terdekat (Biarri FOND, *drop tier settings*).
- **Rentang tiang (alat 4)**: tiang sampai **7 m** dari garis kabel dihitung tiang penopang (tiang di seberang jalan, kabel
  menyeberang kiri-kanan). 7 m = lebar jalur jalan sedang 2 × 3,50 m (Permen PU 19/PRT/M/2011 Lampiran, telah diganti
  Permen PUPR 5/2023 — acuan orde besaran). Contoh dokumen: tiang tengah 4–5 m dari garis tidak lagi menghasilkan bentang palsu.
- **Tiang nganggur**: NP yang tidak dilewati kabel = ERROR (alat 4) / WARNING (alat 1, tahap survei) dengan **tikor**
  (lintang, bujur) di keterangan dan remarks. EP dan tiang yang dilewati kabel feeder boleh (aturan tim QC).
- **Akses rumah (alat 1, `akses.py`)**: jarak tiang → rumah dihitung juga lewat jalur survei (menyusuri jalur lalu masuk ke
  rumah). WARN_HP_JAUH_LEWAT_JALUR bila > 55 m (50 m + galat GPS 5 m) padahal garis lurusnya ≤ 50 m; WARN_HP_AKSES_DALAM bila
  rumah > 40 m (asumsi desain rumah lapis pertama < 30 m dari jalan, perlu kalibrasi, + galat GPS urban 10 m) dari jalur survei terdekat (rumah lapis kedua/ketiga — akses masuk drop perlu dicek, izin melintas pekarangan / BAKP).
  Batasan: hanya jalan/gang yang digambar sebagai jalur survei yang dikenal; gang yang belum digambar membuat rumah tampak
  "dalam" (karena itu WARNING, bukan ERROR).
- **Kecepatan**: titik-dalam-poligon memakai indeks kotak-batas (FAT_COVERAGE 6.000 HP × 300 poligon: 10,1 s → 0,1 s),
  jarak titik-ke-kabel memakai indeks ruas (`SegGrid`), FAT_CENTER memakai indeks FAT. Seluruh aturan inti untuk 6.000 HP
  / 1.052 tiang / 300 FAT: 10,2 s → 1,4 s; hasil aturan lain tidak berubah (5 berkas uji lama tetap lulus).

## Tambahan 3.8.2 — lintas cluster mode KMZ saja / KMZ 1 PIC (review Tomohon & Pematangsiantar, November 2026)
- **Cluster saudara mode KMZ saja**: pada folder tanpa HPDB (termasuk KMZ "1 PIC" yang dipecah ke `_KMZ_PER_AREA`), folder
  saudara yang hanya berisi KMZ survei ikut dibandingkan. Sebelumnya saudara wajib ber-HPDB sehingga 7 lingkungan Kakaskasen
  tercatat "Cluster saudara dibandingkan: 0" dan 15 tiang yang sama koordinat di Lingk. 4 & 6 lolos. Mode ber-HPDB tidak berubah.
- **BOUNDARY di akar area**: placemark poligon yang diletakkan langsung di folder area (tanpa folder BOUNDARY) dibungkus folder
  BOUNDARY saat KMZ dipecah, bila area itu belum punya folder BOUNDARY.
- **Label survei mode KMZ saja**: nama titik KMZ (`? -37`) dipakai sebagai label untuk cek label sama di dalam cluster dan lintas
  cluster (aturan 25 m / 25–50 m tidak berubah).
- **Penomoran label urut diulang** (`seq_labels_restart`): bila ≥ 5 label ?NNN dan ≥ 50 % label urut cluster yang lebih kecil juga
  ada di cluster saudara, tetapi median jarak pasangan berlabel sama > 2 × 50 m, label urut tidak dipakai sebagai pengenal
  lintas cluster untuk pasangan itu (KMZ 1 PIC Tomohon: 72–98 % label sama, median 116–699 m). Duplikat tetap dinilai dari
  koordinat (≤ 0,5 m ERROR, 0,5–5 m INFO) dan nama usaha/bangunan.
- **Jalur berimpit (info)**: panjang ruas jalur yang searah (≤ 20°) dan ≤ 2 m dari jalur cluster saudara, dilaporkan bila ≥ 30 m.
  Bukan kesalahan: dua kabel boleh lewat ruas tiang yang sama; kesalahan BOQ adalah tiang yang dicatat di dua KMZ
  (WARN_TIANG_GANDA_LINTAS_CLUSTER, tetap ≤ 1 m).
- **Remarks**: HP yang sudah disebut "> 50 m ke tiang" tidak disebut lagi sebagai "jauh dari jalur/akses"; kelebihan < 0,05 m dari
  batas ditulis "< 0,1 m"; ID cluster yang belum ada di FINDIM berumur > 90 hari menjadi catatan (findim_stale), bukan alasan reject.
- **BAKP**: PDF dengan object stream terkompresi (PDF 1.5+, CamScanner) kini terbaca per halaman; ID 9–12 digit di judul/subjek
  PDF yang berbeda dari ID cluster → WARN_BAKP_ID_METADATA_BEDA (bukan penghalang, wajib dicocokkan manual).
- **Evidence**: folder `EVIDEN` dikenali; folder foto di luar folder HP (mis. `Dokumentasi`) dilaporkan sebagai foto umum, tidak
  dipakai untuk cek "HP tanpa foto".

## Tambahan 3.9.2 — label umum & peta dasar (review Tomohon, November 2026)
- **Label umum** (`generic_unit`): kata generik (RUKO, TOKO, KIOS, KOS, WARUNG, RUMAH, KANTOR, ...) + nomor unit
  ('RUKO-1', 'Toko 2', 'KIOS A3', 'Kos No 12'). Nomor seperti ini diulang di tiap deret bangunan/lingkungan, jadi label sama
  bukan bukti rumah yang sama: ERROR hanya ≤ 5 m, 5–25 m WARNING "cek citra", > 25 m tidak dilaporkan. Hanya mempersempit
  jenis 'nama usaha'; nama khas, nomor urut survei dan nomor rumah biasa memakai aturan lama.
- **Hubungan deret** (`series_relation`): bila kedua cluster punya ≥ 2 unit berlabel umum yang sama, celah terdekat antarderet
  dibandingkan dengan jarak antarunit (median tetangga terdekat). Celah > 1,5 × jarak antarunit = deret bersambung (kemungkinan
  unit berbeda); selain itu deret saling tumpang (kemungkinan disurvei dua kali). Hanya keterangan; tingkat tetap WARNING.
- **Peta dasar** QGIS (Esri World Imagery / OpenStreetMap) hanya latar pembuktian; tidak dipakai dalam perhitungan QC.

## Tambahan 3.10.0 — strand, grup 1 PIC dan konsistensi (review strand Jambi Suka Karya, 13 cluster RT, November 2026)
- **Strand / wilayah induk** (`grup.strands`): cluster dengan funnel cluster sama, file BAKP identik, file TSSR identik, atau
  satu grup 1 PIC disatukan (union-find, transitif) menjadi satu strand. Strand bisa berisi beberapa sub-jaringan yang
  terpisah jauh (Suka Karya: 10 + 3 cluster, terpisah +-300 m). Dokumen (BAKP/TSSR) dinilai di level strand, desain
  (boundary, tiang, FDT) per sub-jaringan. Laporan `REKAP_STRAND_<nama>.txt/.csv` + remarks strand <= 255 karakter.
  Strand tidak mengubah status cluster.
- **TSSR strand**: TSSR yang identik (SHA-256) dengan TSSR cluster lain tidak lagi dibandingkan jumlah HP-nya dengan HPDB
  cluster ini (dulu 13 cluster tertulis "TSSR 1242 HP vs HPDB n HP"); temuan WARN_TSSR_DIPAKAI_BERSAMA (catatan, bukan
  penghalang, sama dengan WARN_TSSR_HP_BEDA). Rekap strand membandingkan HP TSSR dengan total HPDB strand.
- **HP di irisan BOUNDARY**: satu sumber angka per pasangan. "n HP masuk boundary X" yang seluruhnya berada di irisan
  dengan X digabung ke frasa "boundary tumpang tindih dgn X", memakai prioritas & sifat penghalang frasa HP di boundary.
  Kedua cluster kini menyebut baris HP yang sama (dulu RT 03 "4 HP" karena ambang 10 m, RT 11 "8 HP"). Ambang 10 m tetap
  menentukan ERROR per HP. Frasa irisan diurutkan dari luas terbesar dan punya tiga tingkat (rinci / ringkas / jumlah).
- **Penyusunan remarks**: versi rinci sebuah alasan penghalang tidak dipakai bila menutup versi terpendek alasan penghalang
  berikutnya. Diuji pada 5.200 kombinasi temuan nyata: status tidak pernah berubah; jenis temuan lain menghasilkan teks
  identik dengan 3.9.5.
- **Irisan vs bersinggungan (grup)**: irisan < 100 m2 tanpa HP (+-2 m x 50 m garis batas yang digambar tangan) dicatat
  "bersinggungan", tidak dihitung sebagai pasangan tumpang tindih.
- **Tiang ganda lintas cluster**: jenis tiang dibaca seperti cek span (EP/EXT/TE = eksisting, NP/T6/baru = baru). Tiang BARU
  di dua KMZ = BOQ tiang baru ganda; tiang EKSISTING di kedua KMZ = catatan sewa/attachment ganda (bukan BOQ tiang baru).
  Kode temuan & tingkat tidak berubah.
- **Jalur berimpit simetris**: dihitung dua arah (A->B dan B->A), diambil yang terbesar, sehingga kedua cluster menyebut
  angka yang sama.
- **Rencana FDT grup** (`grup.fdt_plan`): colo setiap anggota satu jaringan dibandingkan; lebih dari satu rencana (FDT
  existing berbeda dan/atau FDT baru) = TIDAK TERPADU; dua anggota ke FDT yang sama dicek terhadap kapasitas FDT. Sisa
  kapasitas FDT grup < 5 % ditandai "cadangan tipis".
- **CLUSTER_NAME campur** (WARN_HPDB_CLUSTER_NAME_CAMPUR, standar 3): nama dibandingkan setelah normalisasi penulisan
  ('RT16' = 'RT 016' = 'RT 16'); cluster pemilik = nama dengan RT yang sama dengan nama folder, lalu terbanyak. Label minoritas
  yang sama dengan cluster saudara disebut "kemungkinan HP pindahan". Variasi penulisan saja = info di laporan.
- **BOUNDARY memotong diri** (WARN_BOUNDARY_TIDAK_VALID, standar 2): uji silang antarruas tidak bersebelahan (OGC Simple
  Features: poligon sah tanpa sisi bersilang); titik potong dilaporkan.
- **Nama berkas** (INFO_NAMA_FILE_HP_BEDA): jumlah HP di nama KMZ/TSSR/BAKP dibandingkan dengan isi HPDB (info, tidak masuk
  remarks).
- **Wilayah sheet lain** (standar 3, info): kombinasi kelurahan/kecamatan/kota sheet tiang dibandingkan dulu dengan sheet
  homepass yang sudah sesuai FINDIM; isi kolom yang tertukar (KECAMATAN berisi nama kelurahan) dilaporkan "tertukar", tidak
  lagi dicocokkan ke FINDIM (dulu menghasilkan wilayah jauh seperti 'Kabupaten Kerinci').

## Tambahan 3.11.0 — 1 PIC / berdampingan sebagai satu wilayah (revisi pembuat, 5 November 2026)
- **Boundary bertumpuk diterima**: dalam pasangan cluster 1 PIC / berdampingan (satu jaringan, BOUNDARY bersinggungan/
  berdampingan <= 5 m, atau BAKP identik dalam 300 m) yang **satu funnel** (funnel cluster = funnel aktif/RFS EXT yang memuat
  HP terbanyak, dari data referensi), irisan BOUNDARY (INFO_BOUNDARY_BERIRISAN_1PIC) dan HP di BOUNDARY saudara
  (INFO_HP_DI_BOUNDARY_SAUDARA_1PIC) menjadi catatan, bukan alasan reject. Tanpa data referensi funnel, toleransi hanya
  berlaku bila ada bukti satu wilayah induk (BAKP identik, TSSR identik, atau BOUNDARY induk sama).
- **Lintas funnel tetap salah**: funnel kedua cluster diketahui dan berbeda -> HP_DI_BOUNDARY_CLUSTER_LAIN /
  WARN_BOUNDARY_BERIRISAN_CLUSTER_LAIN tetap (ERROR/penghalang) dengan keterangan "LINTAS FUNNEL". Cek HP di funnel lain,
  cluster lain digabung, RFS DONE/EXT tidak berubah.
- **Tetap dikaji**: HP duplikat lintas cluster (rumah sama di dua HPDB), tiang ganda, BOUNDARY induk yang memuat sebagian
  besar HP cluster lain (belum dipotong) dan BOUNDARY identik tetap seperti 3.10 - itu bukan "bertumpuk", melainkan satu rumah
  di dua cluster atau boundary yang belum dibuat per cluster.
- **HP > 50 m tercover tiang saudara** (INFO_HP_TERCOVER_TIANG_SAUDARA): HP yang garis lurusnya > batas (hp_pole_max_m) ke
  semua tiang cluster sendiri, tetapi <= batas yang sama ke tiang cluster saudara yang ditoleransi (satu funnel/wilayah induk)
  **yang dilewati jalur kabel cluster itu (<= 5 m dari ruas sejak 3.12.0; 3.11.0: 2 m)**, menjadi catatan dengan nama tiang, jenis tiang dan saran desain
  (drop dari tiang bersama atau pindahkan HP). Tiang saudara yang tidak dilewati jalur tidak dihitung (review Suka Karya: 39
  HP > 50 m; 27 tercover tiang ber-jalur, 12 tetap reject; tanpa syarat jalur 39 akan lolos semua). Standar 1 dihitung ulang.
- **Akses lewat jalur** (WARN_HP_JAUH_LEWAT_JALUR) tetap peringatan, karena graf akses hanya memuat jalur cluster sendiri;
  tiang saudara <= batas dicatat sebagai alternatif.
- Saklar profil `cross_1pic_overlap_ok` dan `cross_1pic_pole_cover` (bawaan true). Bila false, hasil identik dengan 3.10.0
  (diuji pada batch Suka Karya).

## Tambahan 3.12.0 — jalur cluster ditumpu tiang cluster saudara 1 PIC (kajian folder REVIEW STRAND Suka Karya, 5 Nov 2026)
Dasar (sumber dapat diperiksa):
- **Bentang = jarak dua titik tumpu kabel berurutan.** USDA Rural Utilities Service, Bulletin 1751F-630 *Design of Aerial
  Plant* (1996), Definitions: "Span Length: The horizontal distance between two adjacent supporting points of a cable";
  Corning Cable Systems, Application Engineering Note AEN 14 *Sag and Tension - General* (rev. 5): "Span length - the
  straight line-of-sight distance between consecutive poles". Tiang cluster saudara yang menumpu kabel memutus bentang.
- **Tiang sudut & ujung bertreklam.** USDA RUS Bulletin 1751F-650 *Aerial Plant Guying and Anchoring* (1996) ps. 3.1-3.5
  (guy untuk sudut 5-60 derajat, dua head guy >= 60 derajat; "deadend guy ... to hold the pole at the end of a line"). Standar
  tidak mensyaratkan tiang milik cluster/penyelenggara yang sama.
- **Pemanfaatan bersama tiang.** UU 36/1999 tentang Telekomunikasi ps. 34A-34B (sisipan UU 11/2020 Cipta Kerja jo. UU 6/2023):
  pemilik infrastruktur pasif wajib membuka akses pemanfaatan bersama; SE Kepala Otorita IKN 011/SE/Kepala-Otorita IKN/X/2023
  Lampiran I B.4: tiang "dimanfaatkan secara bersama".
- **Batas bentang regulasi daerah 50 m**: contoh Peraturan Wali Kota Tangerang Selatan 47/2019 ps. 5J ("jarak antara tiang
  penyangga fiber optik paling jauh 50 meter").
- **Toleransi posisi**: GPS ponsel 4,9 m di langit terbuka (GPS.gov), 7-13 m di permukiman (Merry & Bettinger, PLOS ONE
  14(7) e0219890, 2019). Data REVIEW STRAND: 296 dari 303 tiang (98 %) <= 5 m dari jalur KMZ-nya sendiri, hanya 68 % <= 2 m.

Aturan (saklar profil `cross_1pic_route_support`, bawaan true; berlaku hanya untuk pasangan yang ditoleransi 3.11:
1 PIC/berdampingan & satu funnel/wilayah induk):
- Tiang cluster saudara dihitung bila <= 5 m (POLE_ROUTE_M) dari jalur cluster saudara itu (bagian jaringannya).
- **Rentang**: tiang saudara <= 3 m (POLE_ON_LINE_M, sama dengan tiang cluster sendiri) dari garis rentang memecah rentang;
  rentang terpanjang yang tersisa dinilai ulang dengan batas yang sama (<= 50 m INFO_RENTANG_DITUMPU_TIANG_SAUDARA,
  50-60 m WARN_RENTANG_REGULASI, > 60 m RENTANG_* dengan nilai baru dan panjang tanpa tiang saudara di keterangan).
- **Belokan / ujung jalur / percabangan tanpa tiang**: simpul <= snap_m (parameter snap yang sama untuk tiang cluster sendiri)
  dari tiang saudara -> INFO_TITIK_JALUR_DI_TIANG_SAUDARA dengan pengingat treklam/tambat akhir di tiang itu.
- Bila bagian 1 PIC gagal dihitung, semua temuan dikembalikan seperti sebelum bagian itu (cek inti tidak ikut gagal).
Hasil REVIEW STRAND: KOTA RT 04 NP-08 - NP-06 240 m -> 53 m (5 tiang RT 05); RT 10 NP6-10 - NP6-12 547 m -> 154 m (6 tiang
RT 07); 23 belokan/ujung jalur di tiang saudara; tidak ada rentang lain yang lolos, karena tiang saudara terdekat 3,2-5,8 m dari
garis (di luar toleransi 3 m tiang sendiri).
Saklar ketiga aturan 1 PIC false -> hasil identik dengan 3.10.0 (diuji pada batch Suka Karya).

## Tambahan 3.13.0 — integritas jalur: satu jaringan kabel utuh yang ditumpu tiang (revisi pembuat 6 Nov 2026)
Masalah: cek rentang lama hanya menilai bagian jalur yang **kedua ujungnya tiang**. Bagian jalur yang berujung di titik tanpa
tiang (ujung jalur, percabangan) atau yang tidak punya tiang sama sekali tidak pernah diukur sepanjang jalurnya; lingkar jalur
yang semua titiknya bukan tiang tidak ditelusuri sama sekali; garis yang bersilang tanpa simpul, garis yang terputus, dan garis
yang digambar dua kali tidak terdeteksi. Ujung jalur dan percabangan tanpa tiang sudah tercatat di QC_TEMUAN tetapi tidak
masuk remarks, sehingga cluster bisa 'Approve' walau jalurnya tidak bisa dibangun.

Dasar (sumber dapat diperiksa):
- **Bentang = jarak dua titik tumpu kabel berurutan** (USDA RUS Bulletin 1751F-630, Definitions; Corning AEN 14). Kabel di
  antara tiang dan titik tanpa tiang tetap kabel tanpa tumpuan; panjangnya diukur **sepanjang jalur** sampai tiang terdekat
  dan dinilai dengan batas bentang yang sama (Handbook 60 m; regulasi daerah 50 m).
- **Ujung jalur di tiang tambat akhir**: USDA RUS Bulletin 1751F-650 ps. 3.5 (deadend guy "to hold the pole at the end of a
  line").
- **Sambungan/percabangan di tiang**: Fiber Optic Association, *Aerial Workmanship* (foa.org/tech/ref/OSP_Construction/
  Aerial_Workmanship.html): "Splice closures should be attached to poles"; "All loops of cable must be secured to a pole at
  the end of the span"; "no loose hanging cables along the span".
- **Satu jaringan**: ITU-T G.984.1 ps. 1 ("one-to-many relationship between the OLT and the ONU/ONTs") dan ps. 3.6 (ODN
  "realizes the optical transmission from the OLT towards the users"): bagian jalur yang tidak tersambung ke jaringan
  cluster tidak bisa dialiri serat dari FDT cluster itu.
- **BOQ kabel**: panjang kabel dihitung dari panjang garis jalur; garis yang digambar dua kali menggandakan panjang kabel.

Aturan (saklar profil `route_integrity`, bawaan true; false = perilaku 3.12, termasuk remarks):
| Kode | Tingkat | Aturan |
|---|---|---|
| JALUR_TANPA_TIANG | ERROR (reject) | (a) bagian jalur tanpa satu pun tiang (berapa pun panjangnya >= 1 m); (b) ujung jalur > 60 m sepanjang jalur dari tiang terakhir; (c) dua tiang yang dihubungkan lewat percabangan tanpa tiang > 60 m (50-60 m = WARN_RENTANG_REGULASI; EP-EP tidak dinilai, sama dengan rentang biasa). Tiang <= 3 m dari garis memecah bagian ini (aturan tiang sendiri). |
| JALUR_TERPUTUS | ERROR (reject) | bagian jalur yang bertiang tetapi celahnya ke jalur cluster lain > snap_m (10 m). Cluster > 1 FDT (HP > kapasitas FDT) -> WARN_JALUR_TERPUTUS. Celah <= snap_m = celah gambar: ujungnya sudah dinilai sebagai ujung jalur. |
| UJUNG_JALUR_TANPA_TIANG | ERROR (reject, baru masuk remarks) | sama dengan sebelumnya; keterangan ditambah panjang kabel sepanjang jalur dari tiang terakhir. |
| WARN_SIMPANG_TANPA_TIANG | WARNING penghalang (reject, baru masuk remarks) | percabangan > snap_m dari tiang = sambungan tergantung di bentang. Juga percabangan yang tidak disatukan di simpul: ujung garis yang berhenti/melewati <= 3 m (POLE_ON_LINE_M) dari garis lain, atau titik sudut garis yang diletakkan <= 0,5 m di garis lain (menggantikan temuan ujung jalur di titik itu). Derajat simpul dihitung dari tetangga BERBEDA: garis rangkap yang berakhir di titik sudut garis lain bukan percabangan; ujung bolak-balik = ujung jalur. |
| WARN_JALUR_BERSILANG_TANPA_TIANG | WARNING (catatan) | dua garis jalur menyilang/menempel (sudut >= 10 derajat) tanpa simpul bersama dan > snap_m dari tiang: bisa percabangan tanpa tiang atau dua kabel terpisah -> ditinjau. |
| WARN_JALUR_BERTUMPUK | WARNING (catatan) | ruas jalur sejajar (sudut < 10 derajat) berjarak <= 1 m sepanjang >= 5 m (galat GPS ponsel 4,9 m, GPS.gov): garis digambar dua kali/bolak-balik; panjang jalur tanpa tumpukan dicatat di laporan. |
| INFO_JALUR_TERSAMBUNG_LEWAT_SAUDARA | INFO | jalur terputus yang <= snap_m dari jalur cluster saudara 1 PIC (pasangan yang ditoleransi 3.11). |

1 PIC (aturan 3.12 berlaku sama): JALUR_TANPA_TIANG dipotong di tiang cluster saudara yang dilewati jalurnya dan <= 3 m dari
garis; bagian terpanjang yang tersisa dinilai ulang (<= 50 m INFO_RENTANG_DITUMPU_TIANG_SAUDARA, 50-60 m WARN_RENTANG_REGULASI,
> 60 m tetap JALUR_TANPA_TIANG). Persilangan <= snap_m dari tiang saudara -> INFO_TITIK_JALUR_DI_TIANG_SAUDARA.
KMZ tanpa titik tiang atau tanpa garis jalur (alat berhenti) kini menghasilkan remarks **Reject** di rekap batch, bukan hanya
'GAGAL'.

Uji (data REVIEW STRAND Suka Karya, 13 cluster, dan 7 skenario sintetis dari RT 07 asli):
- Bentangan tanpa tumpuan > 60 m diperiksa ulang secara independen (geopandas, geometri ROADS tersnap, tumpuan = tiang
  sendiri/saudara <= 3 m): semua bentangan terdeteksi Seranta (RENTANG_* / JALUR_TANPA_TIANG); bagian lain di rentang yang
  sama kini disebut di keterangan (RT 16: 109,1 m dan 65,6 m).
- RT 18: ujung jalur 72 m garis lurus = 237 m kabel tanpa tiang sendiri; ditumpu 4 tiang RT 06/RT 10, terpanjang 53,6 m
  (WARN regulasi, bukan reject). RT 11: span NP6-22 ke tiang T6 KOTA RT 04 61,8 m dan ujung jalur 56,8 m tanpa tiang (kini
  masuk remarks). RT 03: 3 percabangan tanpa simpul (2 di tiang RT 11 = catatan, 1 berjarak 49 m dari tiang = reject).
- Garis bertumpuk: KOTA RT 04 71 m, RT 03 49/59/78 m (cabang digambar bolak-balik), RT 05 11 m, RT 09 50 m, RT 11 92 m,
  RT 16 59 m = sama dengan audit geometri independen.
- Sintetis: garis 150 m tanpa tiang, garis putus 85 m di antara dua tiang (tiang di celah jadi nganggur), ujung diperpanjang
  120 m, garis rangkap 212 m, cabang dari tengah bentang, KMZ tanpa tiang -> semua terdeteksi sesuai kode di atas; RT 07 asli
  tanpa temuan jalur.
- Saklar `route_integrity` false -> 13 cluster, 458 temuan identik 3.12.0; remarks identik pada 5.200 kombinasi temuan;
  dua kali jalan -> identik.

### Tambahan 3.13.0 (lanjutan): jaringan sampai ke FDT, tiang & jalur di luar BOUNDARY
| Kode | Tingkat | Aturan dan dasar |
|---|---|---|
| COLO_TITIK_MASUK_TIDAK_DI_JALUR | WARNING (std 7) | tiang terdekat ke FDT colo (titik masuk kabel) tidak dilewati jalur cluster: kabel dari FDT tidak tersambung ke jaringan (ITU-T G.984.1 ps. 1 & 3.6). |
| COLO_HP_TIDAK_TERJANGKAU_JALUR | WARNING (std 7) | HP yang tiang terdekatnya ada di bagian jalur yang tidak tersambung ke tiang titik masuk colo: serat dari FDT tidak sampai. Bagian yang tersambung lewat jalur cluster saudara 1 PIC dikecualikan. Hanya bila ada rekomendasi colo (Design Lite di folder referensi). |
| WARN_TIANG_LUAR_BOUNDARY | WARNING (std 2) | tiang NP > 10 m (bnd_tol, toleransi yang sama dengan HP: GPS ponsel + garis tangan) di luar BOUNDARY cluster: izin warga (BAKP) berlaku untuk wilayah cluster (Standar Review Strand). EP -> INFO_TIANG_EP_LUAR_BOUNDARY (tidak ada tiang baru). |
| WARN_JALUR_LUAR_BOUNDARY | WARNING (std 2) | bentangan jalur >= 10 m yang > 10 m di luar BOUNDARY: boleh bila feeder ke FDT/cluster lain (sebutkan di desain), bukan alasan reject. |
| INFO_TIANG_JALUR_DI_BOUNDARY_SAUDARA | INFO | tiang/jalur di atas yang berada di BOUNDARY cluster saudara 1 PIC (pasangan yang ditoleransi 3.11). |
Uji: KOTA RT 04 2 tiang (37,9 m dan 25,7 m) + 100 m jalur di luar boundary sendiri, semuanya di boundary RT 03 -> catatan
(sama dengan ukuran geopandas independen); RT 09 10 m -> catatan. Sintetis: jalur + tiang 55 m keluar boundary -> kedua
peringatan; FDT di dekat bagian utama jalur yang terputus -> 8 HP bagian lain tidak terjangkau; FDT di jaringan utuh -> tanpa
temuan. Belokan >= 30 derajat tanpa tiang tetap peringatan seperti sebelumnya (keputusan kebijakan pembuat; mengubahnya
menggeser hasil lama).


## Tambahan 3.14.0 — berkas dikenali dari isinya, remarks sederhana, jenis data otomatis (revisi pembuat 8 Nov 2026)
**Pengenalan berkas (kenali.py)** — nama dipakai lebih dulu bila jelas (hasil lama tidak bergeser); isi dipakai bila nama
tidak ada, salah ketik, atau lebih dari satu kandidat. Berkas dibaca sebagai DATA (zip + XML/teks, batas ukuran).
| Berkas | Ciri isi (= syarat pembacanya) | Nama yang juga dikenali |
|---|---|---|
| Daftar homepass (HPDB) | baris judul berisi LATITUDE & LONGITUDE dalam 20 baris pertama (syarat pembaca HPDB) | HPDB, HPBD, HDPB, HPDP, HP DB, HP DATABASE, HOMEPASS, HOMEPAS (jarak edit Damerau <= 1) |
| KMZ survei | titik di folder HP/HOMEPASS (+ garis jalur / folder tiang), atau tiang + jalur | — |
| Design Lite | folder FDT dengan data SPLITTERS | DESIGN LITE |
| Funnel | poligon tanpa titik/garis, folder funnel/RFS | FUNNEL |
| attributes | workbook dengan sheet FINDIM / OLT CLUSTER | attribut/atribut/FINDIM |
| TSSR | teks .docx memuat TSSR / Site Survey / Site Profile | TSSR, SITE PROFILE/SURVEY |
| BAKP | (sudah ada sejak 3.5) teks PDF Berita Acara/Kesepakatan/Perijinan | BAKP, BKAP, BAPK (jarak edit 1) |
Cadangan (OLD, LAMA, BACKUP, COPY, '(1)') dibuang bila masih ada kandidat lain. KMZ cluster lain yang tersalin ke folder
tidak dipilih bila kemiripan nama dengan HPDB jelas menunjuk KMZ lain (ID cluster sama = cocok; nomor RT/RW beda = bukan
pasangan; jumlah HP di nama diabaikan karena berubah setelah revisi).

**Satu folder berisi banyak cluster** (banyak KMZ survei, atau banyak HPDB + KMZ + dokumen): disalin ke
`_PER_BERKAS/<nama>/` dan diperiksa per cluster (cluster lain = saudara). Pasangan HPDB–KMZ–BAKP–TSSR dari kemiripan
nama; bila ragu (selisih skor < 0,15 atau skor < 0,5) tidak dipasangkan. Uji: folder '1 pic design' (13 KMZ Suka Karya +
1 KMZ 1 PIC Tomohon 7 lingkungan) dulu berhenti 'More than one KMZ'; kini 20 cluster diperiksa. Folder campuran 3 cluster
(HPDB+KMZ+BAKP+TSSR): 3 pasangan benar.

**Remarks sederhana (bawaan)** — masukan pengguna: kalimat pendek seperti "ada homepass duplikat dengan cluster X, ada
homepass dari tiang lebih 50 meter, ada tiang duplikat dengan cluster X, mohon dicek kembali keseluruhannya". Status dan
urutan SAMA dengan remarks rinci (alasan reject dulu); rincian (baris, jarak, nilai) tetap di REMARKS.txt, laporan, dan
kolom `remarks_rinci` REMARKS_BATCH.csv. Pilihan "Detailed" di Advanced = gaya lama.

**Jenis data dinilai otomatis** — tiap cluster: "1 PIC / berdampingan dengan ..." (satu jaringan: tiang sama / jalur
tersambung / KMZ memuat folder cluster lain; berdampingan: BAKP sama atau boundary <= 5 m dan dekat) atau "cluster
mandiri". Aturan reject sama untuk keduanya; toleransi 1 PIC (3.11-3.12) hanya berlaku bila terdeteksi 1 PIC.

**Diuji dan DITOLAK: nama wilayah induk sebagai bukti satu funnel.** Usulan: tanpa data funnel/dokumen, cluster
bertetangga dengan nama induk sama ('SUKA KARYA KOTA BARU RT 09/16', 'LINGKUNGAN 1..7-KAKASKASEN') dianggap satu wilayah.
Uji di QGIS pengguna dengan data funnel asli (08-11-2026): 13 RT Suka Karya memang satu funnel, tetapi 7 lingkungan
KAKASKASEN masing-masing funnel SENDIRI. Dengan aturan nama, LINGKUNGAN 7 lolos 'Approve dgn catatan' (tiang lintas funnel
ikut dihitung) padahal dengan data funnel hasilnya Reject. Nama tidak membedakan kedua kasus -> tidak dipakai. Tanpa data
funnel/BAKP/TSSR, boundary bertumpuk tetap tidak ditoleransi (aman) dan laporan menyebut funnel belum dicek; jalankan dengan
folder data referensi untuk keputusan 1 PIC yang benar.

# Dasar Teknis Aturan QC — Seranta - FTTH Design Assistant (v3.3.0)

Copyright (C) 2026 Joseph Edward Timothy Siahaan (GPL-2.0-or-later). Dokumen ini menjelaskan **untuk apa** setiap
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
| Mungkin duplikat lintas cluster | nama mirip ≥ 85 % ≤ 30 m; dua titik ≤ 2 m beda label | WARNING | salah ketik / satu bangunan |
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
| Tiang nganggur | ada | ERROR | Handbook kasus 25 |
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
| FAT_HP_DISTANCE | 15 | MAXPPDIST > 150 m ERROR; 120–150 m WARNING (special case). Tanpa MAXPPDIST, garis lurus dipakai sebagai batas bawah | ERROR / WARNING | UNVERIFIED |
| FAT_CODE | 11, 32 | Nomor D-xx melompat, kode ganda, awalan beda dari FDT, urutan vs SUPDIST, panjang label | WARNING / INFO | UNVERIFIED |
| FAT_ON_POLE | 3 | FAT > 2 m dari tiang (FAT melayang) | WARNING | UNVERIFIED |
| POLE_IDLE | 25 | Tiang > 3 m dari kabel | WARNING | UNVERIFIED |
| SPAN_APD | 9 | Rentang antar tiang di sepanjang kabel > 60 m ERROR, > 50 m WARNING | ERROR / WARNING | UNVERIFIED |
| FAT_CENTER | 6, 33 | Rata-rata jarak HP ke FAT > 1,5 × titik paling sentral; grouping melewati FAT lain | INFO (REVIEW) | UNVERIFIED |
| SLACK | 21 | Jarak antar penanda slack > 250 m | WARNING | UNVERIFIED_SLACK |
| CROSSING | 17, 19, 27 | Kabel memotong layer rel/tol | WARNING | UNVERIFIED_REFERENCE |
| FDT_COLO_NEW | 13, 14 | Matriks bagian N: FDT hilang di Feeder/Distribusi = ERROR; posisi bergeser > 5 m = ERROR; NEW: FAT tak tersambung graf = ERROR; status UNKNOWN = UNVERIFIED | ERROR | UNVERIFIED_DATASET |
| BOM | 22, 23, 29 | HP/FAT/FDT/tiang/closure harus sama persis. Kabel: desain + slack 10 m per perangkat ± 5 %. Satuan km dinormalkan ke meter. Item existing dipisahkan | ERROR / WARNING | UNVERIFIED_BOM |
| KMZ_APD | 5, 18, 20, 28, 31 | Folder wajib dan rename (Homepass, FAT Coverage), ikon X, warna kabel 24/48/96/144, keterangan kabel, folder Existing untuk COLO, visibilitas | ERROR / WARNING / INFO | UNVERIFIED |

Kasus 16 (COLO ke cluster DROP), 24 (jenis tiang vs strand), 26 (alokasi tube), 27 (tiang 9 m di jalan lebar) dan 30
(tumpang tindih dengan existing) membutuhkan data Macro, splice plan, atau kelas jalan. Tanpa data tersebut kasus
ini dilaporkan **UNVERIFIED**, bukan lolos. Kasus 23/26 dicek oleh alat 3 dari splice plan.

## Batasan
- Dokumen operator asli tidak tersedia daring. Angka operator diambil dari salinan dan kutipan jurnal, dan nilainya bervariasi (drop 100–200 m).
- Lampiran Kominfo 2018 masih berupa rancangan, dan Perwal hanya berlaku di kotanya masing-masing. Karena itu nilai 50 m dijadikan WARNING pada profil bawaan dan ERROR pada profil "Perwal ketat". Sebelum go-live, tim perizinan perlu memastikan Perda/Perwal di kota proyek.
- Toleransi BOM (5 %) dan sudut belok (15°/30°) adalah parameter rekayasa (NOT_APPROVED). Keduanya harus dikalibrasi dengan desain nyata dan disahkan reviewer.
- Arti kode CONNSTATUS desain otomatis belum terdokumentasi di handbook. Plugin hanya menandai nilai yang berbeda dari mayoritas.
- Semua hasil adalah alat bantu. Keputusan desain dan pengecualian tetap berada pada desainer dan reviewer.

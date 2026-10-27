# Changelog

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

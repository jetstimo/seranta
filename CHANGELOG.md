# Changelog

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

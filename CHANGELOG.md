# Changelog

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

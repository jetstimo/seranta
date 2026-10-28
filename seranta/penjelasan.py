# -*- coding: utf-8 -*-
"""
Penjelasan bahasa sederhana untuk setiap aturan dan setiap jenis temuan QC.

Dipakai laporan HTML (tool 1, 3, 4) agar setiap pembaca, termasuk yang bukan desainer, paham:
  * apa yang dicek,
  * mengapa itu penting di lapangan,
  * apa arti temuan ini untuk objek tersebut,
  * apa yang perlu dilakukan.

Teks sengaja netral (tanpa nama merek atau perusahaan). Angka batas diambil dari profil standar yang
dipakai saat QC dijalankan, bukan ditulis tetap di sini.

Part of Seranta - FTTH Design Assistant.
Copyright (C) 2026 Joseph Edward Timothy Siahaan. Licensed under GPL-2.0-or-later (see LICENSE).
"""

# ---------------------------------------------------------------------------------------------
# Tingkat temuan (bahasa awam)
# ---------------------------------------------------------------------------------------------
SEVERITY = {
    "ERROR": ("Wajib diperbaiki",
              "Desain melanggar batas tegas. Perbaiki sebelum desain dikirim, atau catat pengecualian yang disetujui."),
    "WARNING": ("Perlu ditinjau",
                "Belum tentu salah, tetapi di luar kebiasaan atau di atas batas anjuran. Periksa dan beri alasan bila dipertahankan."),
    "UNVERIFIED": ("Belum bisa dicek",
                   "Data pendukung tidak tersedia atau tidak terbaca. Ini BUKAN tanda lolos: lengkapi data lalu jalankan ulang."),
    "INFO": ("Catatan",
             "Petunjuk untuk efisiensi atau kerapian. Tidak wajib diubah."),
    "PASS": ("Lolos",
             "Aturan dijalankan dengan data lengkap dan tidak ada temuan."),
}

# ---------------------------------------------------------------------------------------------
# Penjelasan per aturan (tool 4 - QC APD Pasca-Desain)
#   cek     : apa yang diperiksa
#   alasan  : mengapa penting
#   tindakan: apa yang dilakukan bila ada temuan
# ---------------------------------------------------------------------------------------------
RULES = {
    "SERVED": dict(
        cek="Setiap homepass (HP), FAT dan FDT di hasil desain otomatis harus berstatus terlayani dan punya induk yang jelas.",
        alasan="HP yang tidak terlayani berarti rumah itu tidak mendapat port, padahal dihitung sebagai target. Jumlah HP terjual bisa meleset.",
        tindakan="Buka hasil desain otomatis, cari objek yang disebut, lalu hubungkan ke FAT/FDT terdekat atau jalankan ulang penugasan HP."),
    "FAT_COVERAGE": dict(
        cek="Setiap HP berada di dalam satu poligon FAT Coverage, dan poligon yang dipakai sama dengan FAT yang melayaninya.",
        alasan="Coverage adalah peta wilayah layanan. HP di luar coverage atau di coverage FAT lain membuat tim lapangan menarik kabel drop ke FAT yang salah.",
        tindakan="Perbarui poligon coverage atau pindahkan HP ke FAT yang wilayahnya mencakup rumah tersebut."),
    "CABLE_END": dict(
        cek="Ujung kabel distribusi harus berakhir di FAT (bukan menggantung), dan kabel loop tidak terlalu panjang.",
        alasan="Kabel yang berakhir tanpa perangkat adalah biaya material tanpa pelanggan, dan bisa jadi tanda jalur terputus.",
        tindakan="Potong kabel sampai FAT terakhir, atau tambahkan FAT bila memang ada HP di ujung jalur."),
    "MULTI_FDT": dict(
        cek="Hirarki FDT ke FAT benar, kapasitas FDT dan FAT tidak terlampaui, dan premises di ikon sama dengan jumlah HP.",
        alasan="Kapasitas berlebih berarti ada rumah yang tidak kebagian port splitter. Premises yang salah membuat BOM dan laporan penjualan tidak cocok.",
        tindakan="Pindahkan sebagian FAT ke FDT lain, tambah splitter sesuai batas, atau perbaiki angka premises pada ikon."),
    "FAT_HP_DISTANCE": dict(
        cek="Jarak dari FAT ke HP terjauh yang dilayaninya, diukur sepanjang jalur tiang bila tersedia.",
        alasan="Kabel drop yang terlalu panjang menambah redaman, biaya, dan risiko gangguan. Batas ini biasanya tertulis di kontrak desain.",
        tindakan="Geser FAT lebih ke tengah kelompok HP, atau pecah kelompok menjadi dua FAT."),
    "FAT_CODE": dict(
        cek="Kode FAT unik, berurutan tanpa lompatan, panjang kode seragam, dan awalan kode FAT sama dengan kode FDT induknya.",
        alasan="Kode adalah alamat perangkat di sistem inventori. Kode ganda atau acak membuat aktivasi pelanggan dan perbaikan gangguan salah alamat.",
        tindakan="Beri ulang nomor FAT sesuai urutan dari FDT, lalu samakan di KMZ, tabel kode dan hasil desain otomatis."),
    "FAT_ON_POLE": dict(
        cek="Titik FAT dan FDT tepat di atas titik tiang (tidak 'melayang').",
        alasan="Perangkat udara harus dipasang di tiang. Titik yang melayang membuat tim pemasang tidak tahu tiang mana yang dipakai.",
        tindakan="Seret titik perangkat ke titik tiang terdekat, atau tambahkan tiang bila memang belum ada."),
    "POLE_IDLE": dict(
        cek="Setiap tiang baru dilewati kabel. Tiang yang tidak dilalui kabel disebut tiang nganggur.",
        alasan="Tiang baru yang tidak dipakai adalah biaya pemasangan dan izin tanpa manfaat.",
        tindakan="Hapus tiang yang tidak diperlukan, atau perbaiki jalur kabel agar melewatinya."),
    "SPAN_APD": dict(
        cek="Jarak antar tiang di sepanjang jalur kabel tidak melebihi batas tegas maupun batas regulasi daerah.",
        alasan="Bentang terlalu panjang membuat kabel melendut rendah di atas jalan dan sering ditolak saat perizinan.",
        tindakan="Sisipkan tiang di tengah bentang yang terlalu panjang."),
    "FAT_CENTER": dict(
        cek="Posisi FAT kira-kira di tengah kelompok HP-nya, dan HP tidak dilayani FAT yang jauh padahal ada FAT yang lebih dekat.",
        alasan="FAT di tengah membuat kabel drop rata-rata lebih pendek dan pekerjaan instalasi lebih cepat.",
        tindakan="Pertimbangkan menggeser FAT atau menukar kelompok HP. Ini saran efisiensi, bukan kesalahan."),
    "SLACK": dict(
        cek="Cadangan kabel (slack) dicatat secara berkala di sepanjang kabel.",
        alasan="Slack dipakai saat perbaikan atau relokasi tiang. Tanpa slack, kabel putus harus disambung dengan biaya lebih besar.",
        tindakan="Tambahkan keterangan slack pada kabel di jarak yang diminta profil."),
    "CROSSING": dict(
        cek="Kabel yang memotong rel kereta, jalan tol atau hambatan besar lain.",
        alasan="Penyeberangan seperti ini butuh izin khusus dan metode pemasangan khusus.",
        tindakan="Pastikan izin tersedia, atau ubah rute mengikuti penyeberangan yang sudah ada."),
    "FDT_COLO_NEW": dict(
        cek="FDT yang dipakai sama di paket Feeder dan Distribution (kode dan lokasi), dan status COLO/NEW-nya jelas.",
        alasan="Jika FDT di dua paket berbeda, kabel feeder bisa ditarik ke titik yang salah.",
        tindakan="Samakan kode dan koordinat FDT di kedua paket, lalu tandai statusnya (COLO memakai FDT yang ada, NEW memasang FDT baru)."),
    "BOM": dict(
        cek="Jumlah material di BOM sama dengan jumlah di desain: HP, FAT, FDT, tiang, closure dan panjang kabel (termasuk slack).",
        alasan="BOM yang tidak cocok menyebabkan kekurangan material di lapangan atau tagihan berlebih.",
        tindakan="Perbaiki BOM atau desain hingga selisihnya nol (atau dalam toleransi untuk kabel)."),
    "KMZ_APD": dict(
        cek="Struktur folder KMZ, ikon yang ikut tersimpan, warna dan keterangan kabel sesuai aturan penulisan KMZ.",
        alasan="KMZ adalah dokumen serah terima. Folder salah nama atau ikon hilang (tanda X) membuat pemeriksa kesulitan membaca desain.",
        tindakan="Ganti nama folder sesuai saran, simpan ulang KMZ dengan ikon tertanam, dan lengkapi keterangan kabel."),
    "QC01_KODE_FDT": dict(
        cek="Kode FDT sesuai format, tidak dipakai dua kali, tidak bentrok dengan FDT existing lain, kode FDT baru sudah tercatat di rekap kode, dan kelompok kodenya sama dengan kelompok FDT existing di sekitarnya (kandidat grouping).",
        alasan="Kode FDT dipakai sebagai kunci di seluruh dokumen. Kode ganda atau belum terdaftar membuat desain tidak bisa diaktivasi.",
        tindakan="Minta kode resmi dari pengelola rekap kode, lalu samakan di KMZ dan tabel kode."),
    "QC02_PREMISES_SPLITTER": dict(
        cek="Premises FDT sama dengan jumlah premises FAT di bawahnya; jumlah splitter sesuai batas; output FDT cukup untuk input FAT; jumlah splitter FAT sesuai jumlah HP; fiber/tube di Splice Plan cocok dengan tabel kode.",
        alasan="Ini memastikan setiap rumah benar-benar mendapat jalur serat dari FDT sampai FAT, dan dokumen sambungan (Splice Plan) sama dengan desain.",
        tindakan="Perbaiki angka premises/splitter di tabel kode, atau perbaiki Splice Plan agar fiber/tube dan jumlah splitter sama."),
    "QC03_PROPERTIES": dict(
        cek="Isi properties FDT/FAT di KMZ sama dengan tabel kode FDT-FAT (premises, splitter, koordinat, F/T); FDT COLO punya info cluster colo, FDT NEW tidak.",
        alasan="Properties di KMZ dibaca oleh tim inventori. Beda angka antara KMZ dan tabel membuat data aset tidak bisa dipercaya.",
        tindakan="Salin nilai yang benar dari tabel kode ke properties KMZ (atau sebaliknya), lalu simpan ulang."),
    "QC04_TIANG_REFERENSI": dict(
        cek="Tiang existing di desain berada dekat titik tiang existing di data referensi kota.",
        alasan="Tiang existing yang bergeser jauh kemungkinan salah gambar, sehingga perhitungan bentang dan izin sewa tiang ikut salah.",
        tindakan="Pindahkan tiang ke titik referensi, atau ubah menjadi tiang baru bila memang tidak ada tiang existing di situ."),
    "QC05_RASIO": dict(
        cek="Panjang kabel pancingan tidak melebihi persentase tertentu dari panjang kabel baru, dan jumlah closure 96 tidak melebihi persentase tertentu dari jumlah FAT AE (lingkup Distribution).",
        alasan="Rasio ini adalah indikator efisiensi desain. Rasio tinggi biasanya berarti rute berputar-putar atau sambungan berlebih.",
        tindakan="Sederhanakan rute pancingan atau kurangi closure dengan memindahkan titik percabangan."),
    "QC06_TIANG_PERANGKAT": dict(
        cek="FDT baru, FAT AE dan closure 96 baru berdiri tepat di tiang.",
        alasan="Perangkat udara tanpa tiang tidak bisa dipasang sesuai gambar.",
        tindakan="Letakkan perangkat di titik tiang terdekat atau tambahkan tiang baru."),
    "QC07_PANCINGAN": dict(
        cek="Kedua ujung kabel pancingan bertumpu pada tiang.",
        alasan="Pancingan yang tidak ditopang tiang tidak dapat dipasang dan membahayakan pengguna jalan.",
        tindakan="Geser ujung pancingan ke tiang terdekat atau tambahkan tiang penopang."),
}

# ---------------------------------------------------------------------------------------------
# Penjelasan per jenis temuan: (judul sederhana, arti, cara memperbaiki)
#   {obj} = kode/nama objek, {v} = nilai terukur, {t} = batas
# ---------------------------------------------------------------------------------------------
FINDINGS = {
    # --- served / coverage ---
    "HP_ID_DUPLICATE": ("ID homepass dipakai dua kali", "Satu ID homepass muncul lebih dari sekali, sehingga jumlah HP bisa terhitung ganda.",
                        "Hapus salah satu titik atau beri ID baru yang unik."),
    "SERVED_HP_NOT_SERVED": ("Rumah tidak terlayani", "HP {obj} tidak mendapat port FAT di hasil desain otomatis.",
                             "Hubungkan HP ke FAT terdekat yang masih punya port, lalu jalankan ulang penugasan."),
    "SERVED_HP_PARENT_UNKNOWN": ("Induk HP tidak ditemukan", "HP {obj} menunjuk ke perangkat yang tidak ada di data node.",
                                 "Periksa apakah FAT induknya terhapus; tugaskan ulang HP."),
    "SERVED_FAT_NOT_SERVED": ("FAT tidak tersambung ke FDT", "FAT {obj} tidak punya FDT induk, jadi seluruh rumah di bawahnya tidak dapat sinyal.",
                              "Sambungkan FAT ke FDT lewat kabel distribusi dan jalankan ulang desain."),
    "SERVED_CONNSTATUS_DIFFERENT": ("Status sambungan berbeda", "Status sambungan {obj} berbeda dari mayoritas perangkat.",
                                    "Cek tab hasil di aplikasi desain otomatis untuk objek ini."),
    "HP_OUTSIDE_FAT_COVERAGE": ("Rumah di luar wilayah FAT", "HP {obj} berada di luar semua poligon FAT Coverage ({v} m dari tepi terdekat).",
                                "Perluas poligon coverage FAT terdekat atau periksa koordinat rumah."),
    "FAT_COVERAGE_OVERLAP": ("Wilayah FAT tumpang tindih", "HP {obj} berada di lebih dari satu poligon coverage.",
                             "Rapikan batas poligon agar setiap rumah hanya masuk satu wilayah FAT."),
    "HP_WRONG_FAT_AREA": ("Rumah dilayani FAT tetangga", "HP {obj} dilayani satu FAT tetapi letaknya di wilayah FAT lain.",
                          "Pindahkan HP ke FAT pemilik wilayah, atau sesuaikan poligon coverage."),
    # --- ujung kabel / loop ---
    "LOOP_TERMINATION_CHECK": ("Ujung kabel di closure", "Kabel berakhir di closure, bukan di FAT.",
                               "Pastikan memang sengaja (titik sambung ke depan). Bila tidak, potong sampai FAT terakhir."),
    "CABLE_END_WITHOUT_FAT": ("Kabel berakhir tanpa FAT", "Ujung kabel {obj} tidak menempel ke FAT mana pun.",
                              "Potong kabel sampai FAT terakhir atau tambahkan FAT di ujungnya. Ekor kabel yang masih dalam batas "
                              "loop (100 m / 2 bentang) hanya perlu ditinjau dan dicatat alasannya."),
    "LOOP_LENGTH_OVER_100M": ("Kabel loop terlalu panjang", "Kabel loop {v} m, melebihi batas {t} m.",
                              "Pendekkan loop atau ubah rute agar tidak memutar."),
    "LOOP_SPAN_OVER_2": ("Kabel loop melewati terlalu banyak tiang", "Kabel loop melewati {v} bentang, batas {t}.",
                         "Pendekkan loop sampai batas bentang yang diizinkan."),
    # --- hirarki & kapasitas ---
    "FAT_PARENT_FDT_MISSING": ("FAT tanpa FDT induk", "Tidak ditemukan FDT induk untuk {obj}.",
                               "Pastikan FDT tergambar dan FAT tersambung kepadanya."),
    "FAT_MULTI_PARENT": ("FAT diklaim dua FDT", "FAT {obj} terhubung ke lebih dari satu FDT.",
                         "Pilih satu FDT induk dan putuskan sambungan yang lain."),
    "FAT_OVER_CAPACITY": ("FAT kelebihan rumah", "FAT {obj} melayani {v} HP, melebihi kapasitas {t} HP.",
                          "Pindahkan sebagian HP ke FAT tetangga atau tambah FAT baru."),
    "FAT_UNDER_MIN": ("FAT sepi pelanggan", "FAT {obj} hanya melayani {v} HP, di bawah minimum {t} HP.",
                      "Pertimbangkan menggabungkan dengan FAT tetangga. Boleh dipertahankan bila jaraknya tidak memungkinkan."),
    "FAT_PREMISES_MISMATCH": ("Premises FAT tidak cocok", "Angka premises pada FAT {obj} berbeda dari jumlah HP yang benar-benar dilayani.",
                              "Perbarui angka premises pada ikon FAT sesuai jumlah HP."),
    "FDT_CAPACITY_CHECK": ("FDT kelebihan rumah", "FDT {obj} melayani {v} HP, melebihi kapasitas {t} HP.",
                           "Pindahkan sebagian FAT ke FDT lain atau rencanakan FDT baru."),
    "FDT_SPLITTER_OVER": ("Splitter FDT berlebih", "FDT {obj} butuh {v} splitter, melebihi batas {t}.",
                          "Kurangi FAT di bawah FDT ini atau tambah FDT."),
    "FDT_PREMISES_MISMATCH": ("Premises FDT tidak cocok", "Premises pada ikon FDT {obj} ({v}) berbeda dari jumlah HP di bawahnya ({t}).",
                              "Perbarui premises ikon FDT."),
    "FDT_WITHOUT_FAT": ("FDT tanpa FAT", "FDT {obj} tidak punya FAT di bawahnya.",
                        "Periksa apakah FDT ini memang belum dipakai; hapus atau sambungkan FAT."),
    # --- jarak FAT ke HP ---
    "FAT_HP_OVER_150": ("Rumah terlalu jauh dari FAT", "HP terjauh dari FAT {obj} berjarak {v} m, melebihi batas {t} m.",
                        "Geser FAT mendekati rumah terjauh atau pecah kelompok HP."),
    "FAT_HP_120_150": ("Rumah agak jauh dari FAT", "HP terjauh dari FAT {obj} berjarak {v} m (zona khusus).",
                       "Boleh dipertahankan hanya dengan justifikasi khusus; lebih baik geser FAT."),
    # --- kode ---
    "FAT_CODE_DUPLICATE": ("Kode FAT ganda", "Kode {obj} dipakai lebih dari satu FAT.", "Beri nomor ulang sehingga setiap FAT punya kode unik."),
    "FAT_LABEL_ORDER_INVALID": ("Nomor FAT melompat", "Ada nomor FAT yang hilang di urutan ({obj}).", "Beri nomor ulang FAT secara berurutan."),
    "FAT_ORDER_NOT_BY_DISTANCE": ("Urutan nomor FAT tidak mengikuti jarak", "FAT {obj} bernomor lebih kecil padahal lebih jauh dari FDT.",
                                  "Opsional: urutkan nomor FAT dari yang terdekat ke FDT."),
    "FDT_CODE_MISMATCH": ("Awalan kode FAT tidak sesuai FDT", "Awalan kode {obj} tidak sama dengan kode FDT mana pun.",
                          "Samakan awalan kode FAT dengan kode FDT induknya."),
    "FAT_LABEL_LENGTH": ("Panjang kode tidak seragam", "Panjang kode {obj} berbeda dari mayoritas.", "Periksa salah ketik pada kode."),
    # --- tiang ---
    "FAT_NOT_ON_POLE": ("FAT melayang", "FAT {obj} berjarak {v} m dari tiang terdekat (batas {t} m).", "Seret FAT ke titik tiang."),
    "FDT_NOT_ON_POLE": ("FDT melayang", "FDT {obj} berjarak {v} m dari tiang terdekat (batas {t} m).", "Seret FDT ke titik tiang."),
    "POLE_IDLE": ("Tiang tidak dilewati kabel", "Tiang {obj} berjarak {v} m dari kabel terdekat.",
                  "Hapus tiang baru yang tidak perlu, atau rutekan kabel melewatinya. Tiang existing cukup dicatat."),
    "SPAN_OVER_MAX": ("Bentang tiang terlalu panjang", "Jarak tiang {obj} = {v} m, melebihi batas tegas {t} m.",
                      "Sisipkan tiang di tengah bentang."),
    "SPAN_OVER_REGULATION": ("Bentang di atas batas regulasi daerah", "Jarak tiang {obj} = {v} m, di atas batas regulasi {t} m.",
                             "Sisipkan tiang bila daerah tersebut menegakkan batas ini; bila tidak, cukup dicatat."),
    "SPAN_END_WITHOUT_POLE": ("Ujung kabel jauh dari tiang", "Ujung kabel berjarak {v} m dari tiang terakhir.",
                              "Tambahkan tiang di ujung kabel atau pendekkan kabel."),
    "FAT_NOT_CENTRAL": ("FAT kurang di tengah", "Rata-rata jarak HP ke FAT {obj} lebih jauh dibanding titik paling tengah.",
                        "Opsional: geser FAT ke tiang yang lebih di tengah kelompok."),
    "HP_GROUPING_REVIEW": ("Pengelompokan HP bisa lebih baik", "HP {obj} dilayani FAT yang lebih jauh padahal ada FAT yang lebih dekat.",
                           "Opsional: pindahkan HP ke FAT terdekat bila port masih tersedia."),
    "SLACK_GAP_OVER_PROFILE": ("Slack kabel baru terlalu jarang", "Kabel baru {obj}: jarak antar slack terpanjang {v} m, batas {t} m.",
                               "Tambahkan keterangan slack di tengah bentang kabel yang panjang."),
    "ROUTE_CROSSING_REVIEW": ("Kabel menyeberang rel/tol", "Kabel {obj} memotong hambatan besar.",
                              "Siapkan izin penyeberangan atau ubah rute."),
    # --- FDT dua paket ---
    "FDT_DATA_UNVERIFIED": ("Data FDT belum lengkap", "Data yang dibutuhkan untuk menguji FDT belum tersedia.",
                            "Lengkapi paket Feeder/Distribution lalu jalankan ulang."),
    "FDT_MISSING_IN_FEEDER": ("FDT tidak ada di paket Feeder", "FDT {obj} ada di Distribution tetapi tidak ada di Feeder.",
                              "Tambahkan FDT di paket Feeder dengan kode dan lokasi yang sama."),
    "FDT_MISSING_IN_DISTRIBUTION": ("FDT tidak ada di paket Distribution", "FDT {obj} ada di Feeder tetapi tidak ada di Distribution.",
                                    "Tambahkan FDT di paket Distribution."),
    "FDT_ID_MISMATCH": ("Kode FDT berbeda antar paket", "Lokasi FDT sama tetapi kodenya berbeda ({obj}).", "Samakan kode di kedua paket."),
    "FDT_LOCATION_MISMATCH": ("Lokasi FDT bergeser antar paket", "FDT {obj} bergeser {v} m antara dua paket (batas {t} m).",
                              "Samakan koordinat FDT di kedua paket."),
    "FDT_STATUS_UNKNOWN": ("Status COLO/NEW belum jelas", "Status FDT {obj} tidak bisa dipastikan dari data.",
                           "Isi status FDT (COLO/NEW) di parameter atau beri keterangan pada ikon."),
    "FDT_NEW_ROUTE_DISCONNECTED": ("FDT baru tidak tersambung jalur", "FDT/FAT {obj} tidak terhubung ke jalur kabel distribusi.",
                                   "Sambungkan perangkat ke kabel distribusi."),
    # --- BOM ---
    "BOM_CABLE_VARIANCE": ("Panjang kabel BOM berbeda", "Panjang kabel di BOM berbeda dari desain lebih dari toleransi.",
                           "Hitung ulang kabel (termasuk slack) dan perbarui BOM."),
    "BOM_HP_MISMATCH": ("Jumlah HP di BOM berbeda", "Jumlah HP di BOM tidak sama dengan desain.", "Samakan BOM dengan desain."),
    "BOM_FAT_MISMATCH": ("Jumlah FAT di BOM berbeda", "Jumlah FAT di BOM tidak sama dengan desain.", "Samakan BOM dengan desain."),
    "BOM_FDT_MISMATCH": ("Jumlah FDT di BOM berbeda", "Jumlah FDT di BOM tidak sama dengan desain.", "Samakan BOM dengan desain."),
    "BOM_POLE_MISMATCH": ("Jumlah tiang di BOM berbeda", "Jumlah tiang di BOM tidak sama dengan desain.", "Samakan BOM dengan desain."),
    "BOM_CLOSURE_MISMATCH": ("Jumlah closure di BOM berbeda", "Jumlah closure di BOM tidak sama dengan desain.", "Samakan BOM dengan desain."),
    # --- KMZ ---
    "KMZ_REQUIRED_LAYER_MISSING": ("Folder wajib tidak ada", "Folder {obj} tidak ditemukan di KMZ.", "Tambahkan folder tersebut sesuai struktur KMZ."),
    "KMZ_FOLDER_INVALID": ("Nama folder tidak baku", "Folder {obj} perlu diganti nama.", "Ganti nama folder sesuai saran di detail."),
    "KMZ_VISIBILITY": ("Folder sebaiknya disembunyikan", "Folder {obj} sebaiknya tidak dicentang saat KMZ final disimpan.", "Hilangkan centang lalu simpan ulang."),
    "KMZ_ICON_INVALID": ("Ikon hilang (tanda X)", "Ikon tidak ikut tersimpan di dalam KMZ sehingga tampil sebagai tanda X.",
                         "Simpan ulang KMZ dengan ikon tertanam (pilih format KMZ, bukan KML)."),
    "CABLE_COLOR_MISMATCH": ("Warna kabel salah", "Warna kabel {obj} tidak sesuai jumlah core-nya.", "Ganti warna garis sesuai tabel warna kabel."),
    "CABLE_LABEL_MISSING": ("Kabel tanpa keterangan", "Kabel tidak punya nama atau deskripsi.", "Isi keterangan kabel (core, panjang, status)."),
    "CABLE_LABEL_NO_STATUS": ("Keterangan kabel tanpa status", "Keterangan kabel {obj} tidak menyebut COLO atau NEW INFRA.", "Tambahkan status pada keterangan kabel."),
    "KMZ_COLO_MISSING_EXISTING": ("Folder Existing Cluster tidak ada", "Desain COLO tetapi KMZ tidak punya folder Existing Cluster.",
                                  "Tambahkan folder Existing Cluster berisi perangkat existing yang dipakai."),
    "FDT_COLO_LABEL_MISSING": ("FDT existing tanpa keterangan COLO", "FDT existing {obj} tidak diberi keterangan COLO.", "Tambahkan keterangan COLO pada ikon/label."),
    # --- QC-01..07 ---
    "FDT_CODE_DUPLICATE": ("Kode FDT ganda", "Kode {obj} dipakai lebih dari satu FDT.", "Pastikan setiap FDT memakai kode unik."),
    "FDT_CODE_FORMAT": ("Format kode FDT tidak baku", "Kode {obj} tidak mengikuti pola kode FDT.", "Perbaiki penulisan kode."),
    "FAT_CODE_PARENT_UNKNOWN": ("FAT tidak mengikuti kode FDT", "Awalan kode FAT {obj} tidak sama dengan FDT mana pun di desain.",
                                "Samakan awalan kode FAT dengan FDT induk."),
    "FDT_CODE_EXISTS_ELSEWHERE": ("Kode FDT sudah dipakai di lokasi lain", "Kode {obj} sudah dipakai FDT existing di tempat lain.",
                                  "Minta kode baru atau pastikan FDT ini memang FDT existing yang sama (COLO)."),
    "FDT_GROUP_MISMATCH": ("Kelompok kode FDT berbeda dengan sekitarnya", "Kode {obj} memakai kelompok area yang sudah dipakai di lokasi lain, padahal FDT existing di sekitarnya berkelompok lain.",
                           "Periksa kelompok kode area; bila memang salah, pakai kode kandidat yang disarankan di tabel grouping."),
    "FDT_GROUP_NEW": ("Kelompok kode FDT baru", "Kode {obj} membuka kelompok area baru yang belum dipakai FDT existing di sekitarnya.",
                      "Pastikan kelompok area baru ini memang disengaja dan sudah didaftarkan di rekap kode."),
    "FDT_NEW_NOT_IN_REKAP": ("Kode FDT baru belum terdaftar", "Kode FDT baru {obj} belum ada di rekap kode.", "Daftarkan kode ke pengelola rekap."),
    "FDT_PREMISES_NE_SUM_FAT": ("Premises FDT ≠ jumlah premises FAT", "Premises FDT {obj} = {v}, jumlah premises FAT di bawahnya = {t}.",
                                "Samakan premises FDT dengan jumlah premises FAT."),
    "FDT_SPLITTER_MISSING": ("Splitter FDT kosong", "Jumlah splitter FDT {obj} tidak terisi di tabel kode.", "Isi kolom splitter FDT."),
    "FDT_SPLITTER_OVER_MAX": ("Splitter FDT melebihi batas", "FDT {obj} memakai {v} splitter, batas {t}.", "Kurangi splitter atau pecah FDT."),
    "FDT_OUTPUT_SHORT": ("Output FDT kurang", "Output splitter FDT {obj} ({v}) lebih sedikit dari kebutuhan input FAT ({t}).",
                         "Tambah splitter FDT atau kurangi FAT di bawahnya."),
    "FAT_SPLITTER_TIER": ("Jumlah splitter FAT tidak sesuai HP", "FAT {obj} punya {v} HP, tetapi jumlah splitternya tidak sesuai aturan (1-8 HP = 1 splitter, 9-16 HP = 2 splitter).",
                          "Sesuaikan jumlah splitter FAT dengan jumlah HP."),
    "FAT_PREMISES_OVER_16": ("FAT lebih dari 16 HP", "FAT {obj} memiliki {v} premises.", "Pecah FAT menjadi dua."),
    "SPLICE_SHEET_MISSING": ("Splice Plan tidak memuat FAT ini", "Tidak ada sheet Splice Plan untuk FAT {obj}.", "Tambahkan FAT ke Splice Plan."),
    "SPLICE_SPLITTER_COUNT": ("Jumlah splitter beda dengan Splice Plan", "Tabel kode menyebut {t} splitter untuk {obj}, Splice Plan berisi {v}.",
                              "Samakan jumlah splitter di tabel kode dan Splice Plan (lihat juga jumlah HP FAT)."),
    "FIBER_TUBE_MISMATCH": ("Fiber/tube beda dengan Splice Plan", "Nomor fiber/tube {obj} di tabel kode berbeda dengan Splice Plan.",
                            "Ambil nomor fiber/tube dari sheet Route optique Splice Plan."),
    "FDT_COLO_INFO_MISSING": ("Info cluster COLO tidak ada", "FDT COLO {obj} tidak menyebut cluster asal FDT.", "Isi kolom COLO dengan cluster asal."),
    "FDT_NEW_HAS_COLO": ("FDT baru berisi kolom COLO", "FDT NEW {obj} mengisi kolom COLO, padahal FDT baru tidak memakai cluster lain.",
                         "Kosongkan kolom COLO untuk FDT baru."),
    "PROP_CODE_NOT_IN_TABLE": ("Perangkat tidak ada di tabel kode", "{obj} ada di KMZ tetapi tidak ada di tabel kode FDT-FAT.", "Tambahkan ke tabel kode."),
    "PROP_CODE_NOT_IN_KMZ": ("Kode di tabel tidak ada di KMZ", "{obj} ada di tabel kode tetapi tidak ditemukan di KMZ.", "Tambahkan perangkat ke KMZ atau hapus dari tabel."),
    "PROP_MISMATCH": ("Properties KMZ ≠ tabel kode", "Nilai properties {obj} di KMZ berbeda dengan tabel kode.", "Samakan nilai di KMZ dan tabel."),
    "AUTODESIGN_VS_TABLE": ("Hasil desain otomatis ≠ tabel kode", "Jumlah splitter/premises {obj} di hasil desain otomatis berbeda dengan tabel kode.",
                            "Periksa mana yang benar, lalu samakan."),
    "EXT_POLE_FAR_FROM_REF": ("Tiang existing tidak cocok dengan referensi", "Tiang existing {obj} berjarak {v} m dari tiang referensi terdekat (batas {t} m).",
                              "Pindahkan ke titik referensi, atau ubah statusnya menjadi tiang baru."),
    "PANCINGAN_RATIO_OVER": ("Kabel pancingan terlalu banyak", "Pancingan = {v}% dari panjang kabel baru (batas {t}%).", "Sederhanakan rute pancingan."),
    "CLOSURE_RATIO_OVER": ("Closure 96 terlalu banyak", "Closure 96 = {v}% dari jumlah FAT AE (batas {t}%).", "Kurangi closure atau gabungkan titik sambung."),
    "DEVICE_WITHOUT_POLE": ("Perangkat tidak di tiang", "{obj} berjarak {v} m dari tiang terdekat (batas {t} m).", "Letakkan perangkat tepat di tiang."),
    "PANCINGAN_END_NO_POLE": ("Ujung pancingan tanpa tiang", "Ujung pancingan {obj} berjarak {v} m dari tiang (batas {t} m).", "Tambahkan atau geser ke tiang."),
}

# Bila jenis temuan belum ada di daftar, tampilkan pesan teknis apa adanya.
DEFAULT_FINDING = ("Temuan", "{msg}", "Periksa objek di peta dan sesuaikan dengan aturan yang disebut.")


def finding_text(f):
    """(judul sederhana, arti, cara memperbaiki) untuk satu temuan (dict dari qc_core.finding)."""
    rid = f.get("rule_id", "")
    j, a, p = FINDINGS.get(rid, DEFAULT_FINDING)

    def num(x):
        if isinstance(x, float):
            return ("%.1f" % x).rstrip("0").rstrip(".")
        return "" if x is None else str(x)
    vals = {"obj": f.get("object_id") or f.get("object_type") or "objek", "v": num(f.get("value")),
            "t": num(f.get("threshold")), "msg": f.get("message", "")}
    try:
        a2 = a.format(**vals)
    except (KeyError, IndexError, ValueError):
        a2 = a
    if ("{v}" in a and not vals["v"]) or ("{t}" in a and not vals["t"]):
        a2 = f.get("message", a2)        # angka tidak tersedia -> pesan teknis lebih akurat
    if rid not in FINDINGS and f.get("recommendation"):
        p = f["recommendation"][0].upper() + f["recommendation"][1:]
    return j, a2, p


# ---------------------------------------------------------------------------------------------
# Tool 1 - Standar review survei (Strand)
# ---------------------------------------------------------------------------------------------
TOOL1_STD = {
    1: dict(cek="Setiap rumah (HP) cukup dekat ke tiang terdekat agar kabel drop bisa ditarik.",
            alasan="Rumah yang terlalu jauh dari tiang butuh tiang tambahan atau tidak bisa dilayani.",
            tindakan="Tambahkan tiang baru di dekat rumah tersebut, atau keluarkan rumah dari daftar HP."),
    2: dict(cek="Rumah tidak berada di cluster yang sudah dibangun (RFS) atau di funnel cluster lain.",
            alasan="Rumah yang sudah dilayani cluster lain akan dihitung dua kali (double tagging).",
            tindakan="Hapus HP yang sudah menjadi milik cluster lain dari HPDB dan KMZ."),
    3: dict(cek="Nama kelurahan/kecamatan/kota di HPDB sama dengan data wilayah resmi (FINDIM).",
            alasan="Wilayah yang salah membuat laporan penjualan dan perizinan salah alamat.",
            tindakan="Perbaiki kolom wilayah HPDB mengikuti data wilayah resmi."),
    4: dict(cek="HPDB dan KMZ berisi rumah yang sama, satu rumah satu homepass, tanpa duplikat dan koordinat yang tertukar.",
            alasan="Duplikat membuat jumlah HP terlihat lebih besar dari kenyataan.",
            tindakan="Hapus duplikat, lengkapi HP yang hilang di salah satu file, dan perbaiki koordinat."),
    5: dict(cek="Rumah berada di dalam batas Funnel dan BOUNDARY cluster (rumah yang hanya beberapa meter di luar garis "
                "dicatat sebagai 'di tepi', karena GPS ponsel meleset 5-13 m).",
            alasan="Rumah di luar batas bukan bagian dari target cluster ini.",
            tindakan="Keluarkan HP di luar batas, atau ajukan perubahan boundary bila memang masuk area."),
    6: dict(cek="Status cluster di Funnel tidak reject/drop, dan HP/tiang belum ada di jaringan existing.",
            alasan="Mendesain cluster yang sudah ditolak atau sudah terbangun adalah pekerjaan sia-sia.",
            tindakan="Konfirmasi status cluster sebelum melanjutkan desain."),
    7: dict(cek="Ada FDT existing dalam radius yang diizinkan yang masih bisa dipakai bersama (COLO).",
            alasan="Memakai FDT existing jauh lebih murah dan cepat daripada memasang FDT baru.",
            tindakan="Pilih FDT existing dengan slot terbanyak, atau rencanakan FDT baru bila tidak ada."),
    8: dict(cek="Berita acara izin warga (BAKP) ada dan isiannya sesuai jumlah HP dan tiang.",
            alasan="Tanpa izin warga, pemasangan tiang dan kabel bisa ditolak di lapangan.",
            tindakan="Minta atau lengkapi BAKP ke vendor survei, lalu centang butir di daftar periksa."),
    9: dict(cek="Jarak antar tiang (sepanjang jalur kabel) tidak melebihi batas tegas maupun batas regulasi daerah.",
            alasan="Bentang terlalu panjang membuat kabel melendut dan sering ditolak saat izin.",
            tindakan="Sisipkan tiang baru di tengah bentang yang terlalu panjang."),
}

# Tool 1 - arti jenis temuan (cocokkan dengan awalan kode, urutan penting)
TOOL1_KIND = [
    ("HP_JAUH_DARI_TIANG", "Rumah terlalu jauh dari tiang terdekat.", "Tambahkan tiang di dekat rumah atau periksa koordinat rumah."),
    ("HP_DI_RFS_DONE", "Rumah berada di cluster yang sudah terbangun.", "Keluarkan dari HPDB/KMZ cluster ini."),
    ("HP_DI_RFS_EXT", "Rumah berada di wilayah perluasan cluster lain.", "Koordinasikan dengan pemilik cluster; biasanya dikeluarkan."),
    ("HP_DI_FUNNEL_LAIN", "Rumah masuk funnel cluster lain.", "Keluarkan dari cluster ini atau koordinasikan batas funnel."),
    ("ADMIN_", "Nama wilayah di HPDB berbeda dengan data wilayah resmi.", "Perbaiki kolom wilayah di HPDB."),
    ("HP_DUPLIKAT_KOORDINAT", "Dua atau lebih baris HPDB memakai koordinat yang sama (satu rumah tercatat lebih dari sekali). "
     "Akibatnya baris ganda juga tidak punya pasangan titik di KMZ; itu sudah dihitung di temuan ini.",
     "Bila satu rumah: hapus baris ganda dari HPDB. Bila memang rumah berbeda (bersebelahan/bertingkat): perbaiki koordinat "
     "baris itu ke rumahnya sendiri dan tambahkan titiknya di KMZ."),
    ("HP_DUPLIKAT_ID", "Dua atau lebih HP memakai ID operator yang sama.", "Beri ID unik atau hapus duplikat."),
    ("HP_HPDB_TIDAK_ADA_DI_KMZ", "HP ada di HPDB tetapi tidak tergambar di KMZ.", "Tambahkan titik di KMZ atau hapus dari HPDB."),
    ("HP_BERGESER", "Rumah yang sama (nomor rumah HPDB = nama titik KMZ) tetapi koordinatnya berbeda lebih dari toleransi.",
     "Samakan koordinat HPDB dengan titik survei KMZ (atau sebaliknya bila survei yang salah)."),
    ("HP_KMZ_TIDAK_ADA_DI_HPDB", "HP tergambar di KMZ tetapi tidak ada di HPDB.", "Tambahkan baris di HPDB atau hapus titik di KMZ."),
    ("LAT_LONG_TERTUKAR", "Kolom latitude dan longitude tampaknya tertukar.", "Tukar nilai kedua kolom pada baris tersebut."),
    ("HP_LUAR_FUNNEL", "Rumah di luar batas Funnel.", "Keluarkan HP atau ajukan perubahan batas."),
    ("HP_LUAR_BOUNDARY", "Rumah jelas di luar BOUNDARY KMZ (lebih jauh dari toleransi GPS).",
     "Pastikan rumah memang masuk cluster: bila ya, lebarkan BOUNDARY; bila tidak, keluarkan HP."),
    ("FUNNEL_SENDIRI_REJECT", "Cluster ini berstatus reject/drop di Funnel.", "Konfirmasi status sebelum desain dilanjutkan."),
    ("INFO_HP_MUNGKIN_DI_DESIGN_LITE", "Rumah 2-5 m dari HP jaringan existing, mungkin rumah yang sama.",
     "Cek nomor rumah/alamat; bila sama, keluarkan HP (double tagging)."),
    ("INFO_TIANG_BARU_DEKAT_EXISTING", "Tiang baru beberapa meter dari tiang jaringan existing.",
     "Cek di lapangan: bila tiangnya sama, jadikan tiang existing."),
    ("HP_SUDAH_ADA_DI_DESIGN_LITE", "Rumah sudah tercatat di jaringan existing (double tagging).", "Keluarkan HP dari cluster ini."),
    ("TIANG_BARU_SUDAH_ADA", "Tiang baru ternyata sudah ada di jaringan existing.", "Ubah menjadi tiang existing."),
    ("COLO_", "Catatan kemungkinan COLO FDT existing.", "Bandingkan pilihan FDT di tabel colo."),
    ("RENTANG_NP_NP", "Jarak antar tiang baru melebihi batas.", "Sisipkan tiang baru di tengah."),
    ("RENTANG_NP_EP", "Jarak tiang baru ke tiang existing melebihi batas.", "Geser tiang baru atau sisipkan tiang."),
    ("BAKP_", "Isian BAKP perlu dicek.", "Bandingkan dengan nilai seharusnya di daftar periksa BAKP."),
    ("INFO_BAKP_", "Catatan BAKP.", "Tidak wajib diubah."),
    ("UNV_BAKP", "BAKP belum dapat diverifikasi otomatis.", "Periksa BAKP secara manual."),
    ("TIANG_NGANGGUR", "Tiang survei tidak dilewati jalur kabel.", "Tinjau: hapus bila tidak dipakai, atau lewatkan jalur bila memang dibutuhkan."),
    ("UJUNG_JALUR_TANPA_TIANG", "Jalur berakhir tanpa tiang untuk menambat kabel.", "Tambahkan tiang di ujung jalur."),
    ("WARN_BELOKAN_TANPA_TIANG", "Belokan tajam tanpa tiang (kabel butuh tiang tambat di belokan).", "Tambahkan tiang di titik belokan."),
    ("WARN_SIMPANG_TANPA_TIANG", "Percabangan jalur tanpa tiang.", "Tambahkan tiang di percabangan."),
    ("INFO_BELOKAN_KECIL_TANPA_TIANG", "Belokan kecil tanpa tiang.", "Opsional: pertimbangkan tiang sudut."),
    ("WARN_RENTANG_REGULASI", "Bentang di atas batas regulasi daerah.", "Sisipkan tiang bila daerah menegakkan batas ini."),
    ("INFO_RENTANG_REGULASI", "Bentang di atas batas regulasi daerah (catatan).", "Cukup dicatat."),
    ("INFO_HP_TEPI_BOUNDARY", "Rumah beberapa meter di luar garis BOUNDARY, masih dalam toleransi GPS ponsel.",
     "Tidak perlu dikeluarkan; bila mau rapi, lebarkan sedikit poligon BOUNDARY."),
    ("INFO_HP_TEPI_FUNNEL", "Rumah tepat di tepi luar Funnel (masih dalam toleransi GPS).", "Cukup dicatat."),
    ("INFO_HP_ALAMAT_SAMA", "Beberapa HP memakai alamat lengkap yang sama.", "Periksa apakah memang rumah berbeda (mis. kos/ruko)."),
    ("INFO_HP_MUNGKIN_DUPLIKAT", "Dua HP sangat berdekatan, mungkin rumah yang sama.", "Periksa di lapangan atau citra satelit."),
    ("INFO_KABEL_RENDAH", "Kabel di tengah bentang mungkin terlalu rendah di atas jalan.", "Pakai tiang lebih tinggi atau perpendek bentang."),
    ("INFO_TIANG_BISA_DIHAPUS", "Tiang baru di jalan lurus yang bisa dihapus tanpa melanggar batas bentang.", "Opsional: hapus untuk hemat biaya."),
    ("INFO_UJUNG_JALUR_TANPA_HP", "Ujung jalur tidak melayani rumah mana pun.", "Opsional: pendekkan jalur."),
]


def tool1_kind_text(kind):
    for pre, arti, aksi in TOOL1_KIND:
        if kind.startswith(pre):
            return arti, aksi
    return "", ""


# ---------------------------------------------------------------------------------------------
# Tool 2 - Alokasi FDT/FAT: istilah
# ---------------------------------------------------------------------------------------------
TOOL3_TERMS = [
    ("FAT minimum", "Jumlah FAT paling sedikit agar semua rumah kebagian port: jumlah HP dibagi kapasitas satu FAT, dibulatkan ke atas."),
    ("FAT estimasi", "Jumlah FAT bila rumah dikelompokkan sepanjang jalur kabel dengan batas jarak HP ke FAT. Biasanya sedikit di atas FAT minimum."),
    ("Slot FDT", "Sisa kapasitas FDT existing (dalam satuan FAT) yang masih bisa dipakai cluster ini."),
    ("COLO", "Memakai FDT yang sudah ada milik cluster lain. Lebih murah dan cepat daripada memasang FDT baru."),
    ("Link budget", "Perkiraan total redaman sinyal dari pusat ke rumah. Harus di bawah batas kelas optik agar layanan stabil."),
]


# Nama pendek untuk jalur aturan (kepala laporan)
SHORT = {
    "SERVED": "Terlayani", "FAT_COVERAGE": "Coverage", "CABLE_END": "Ujung kabel", "MULTI_FDT": "Kapasitas",
    "FAT_HP_DISTANCE": "Jarak HP", "FAT_CODE": "Kode FAT", "FAT_ON_POLE": "FAT di tiang", "POLE_IDLE": "Tiang nganggur",
    "SPAN_APD": "Bentang", "FAT_CENTER": "FAT sentral", "SLACK": "Slack", "CROSSING": "Rel/tol",
    "FDT_COLO_NEW": "FDT 2 paket", "BOM": "BOM", "KMZ_APD": "KMZ", "QC01_KODE_FDT": "Kode FDT",
    "QC02_PREMISES_SPLITTER": "Premises", "QC03_PROPERTIES": "Properties", "QC04_TIANG_REFERENSI": "Tiang ref.",
    "QC05_RASIO": "Rasio", "QC06_TIANG_PERANGKAT": "Perangkat", "QC07_PANCINGAN": "Pancingan",
}

# Mengembangkan dan merilis Seranta

## Struktur
```
seranta/                 plugin QGIS (isi ZIP rilis)
  qc_core.py qc_paket.py aturan QC (Python murni, bisa diuji tanpa QGIS)
  penjelasan.py          teks bahasa sederhana untuk setiap aturan dan temuan
  report_ui.py           tampilan laporan HTML bersama (alat 1-4)
  profiles/*.json        profil standar bawaan (netral)
  tests/                 uji otomatis (tidak ikut ZIP)
scripts/release.py       validasi aturan plugins.qgis.org + buat ZIP
scripts/upload_plugin.py unggah ZIP ke plugins.qgis.org (XML-RPC)
scripts/check_neutral.py cegah nama merek/perusahaan masuk ke rilis publik
.github/workflows/       CI (setiap push) dan rilis (setiap tag v*)
```

## Menambah aturan QC baru
1. Tulis fungsi `rule_...` di `qc_core.py` atau `qc_paket.py` yang mengembalikan `RuleResult` berisi `finding(...)`.
2. Tambahkan penjelasannya di `penjelasan.py` (`RULES` untuk aturan, `FINDINGS` untuk setiap kode temuan, `SHORT`
   untuk nama pendek). Uji `test_explanations_cover_all_rules_and_findings` gagal bila ada yang terlewat, sehingga
   laporan HTML selalu bisa menjelaskan setiap temuan.
3. Angka batas baru masuk ke `profiles/*.json` lengkap dengan `dasar`, `sumber`, `status`.
4. Tambahkan uji di `seranta/tests/`.

## Tanda tangan rilis (wajib sejak 3.9.0)
Rilis resmi memuat `seranta/RILIS.json` yang ditandatangani kunci privat Ed25519 pembuat (`seranta/keaslian.py`).
Setiap laporan mencetak status ASLI / DIMODIFIKASI / TIDAK RESMI beserta sidik kunci (resmi: `92C4-D078-D1FC-1C5B`).
`RILIS_RESMI.json` di akar repositori adalah daftar rilis resmi untuk verifikasi online (About → Verify online).
Pemeriksa independen: `python scripts/rilis_resmi.py cek <zip> [--online]`. Sebelum membuat tag:
```
python scripts/rilis_resmi.py rilis --plugin seranta --kunci <kunci privat> --keluar dist --tulis-sumber --registri RILIS_RESMI.json
git add seranta/RILIS.json RILIS_RESMI.json && git commit -m "Tanda tangan rilis <versi>"
```
Kunci privat hanya dipegang pembuat dan **tidak pernah** di-commit (`*.key` ada di `.gitignore`). Setelah RILIS.json
di-commit, jangan mengubah berkas plugin lagi sebelum tag, karena status rilis akan menjadi DIMODIFIKASI.

## Merilis versi baru (otomatis)
1. Naikkan `version=` di `seranta/metadata.txt` dan `__version__` di `seranta/buat_input_desain.py`, tulis baris
   pertama `changelog=` untuk versi itu, dan perbarui `CHANGELOG.md`.
2. Commit, lalu buat tag yang sama dengan versi:
   ```
   git tag v3.4.1
   git push origin main v3.4.1
   ```
3. Workflow **Release** menguji, membuat `seranta.3.4.1.zip`, melampirkannya ke GitHub Release, dan mengunggahnya ke
   plugins.qgis.org. Pengguna QGIS melihat pembaruan di tab **Upgradeable** Plugin Manager.

## Secrets repositori (GitHub: Settings → Secrets and variables → Actions)
| Nama | Isi |
|---|---|
| `OSGEO_USER`, `OSGEO_PASSWORD` | akun OSGeo pemilik plugin (untuk unggah otomatis) |
| `BRAND_DENYLIST` | daftar nama merek/perusahaan yang tidak boleh muncul, dipisah koma (tidak disimpan di repo publik) |

## Rilis pertama (sekali, manual)
plugins.qgis.org mewajibkan unggahan pertama lewat web: login dengan akun OSGeo di https://plugins.qgis.org/plugins/add/,
unggah ZIP dari GitHub Release, lalu tunggu persetujuan tim QGIS. Setelah itu rilis berikutnya berjalan otomatis.

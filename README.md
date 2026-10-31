# Seranta™ – FTTH Design Assistant

![Seranta](seranta/icon.png)

**Seranta** = *serat* (fibre) + *Nusantara*: fibre that connects the archipelago.
A QGIS plugin for FTTH/GPON access-network design. It turns field-survey data (homepass spreadsheet + KMZ) into
ready-to-use input for automatic network-design software, checks the survey before design, estimates FDT/FAT
allocation, produces post-design tables, and checks the final design package — with reports anyone can understand.

Copyright © 2026 **Joseph Edward Timothy Siahaan** · code: GNU GPL v2 or later · QGIS 3.22 LTR – 4.x
Seranta™ and the Seranta logo are trademarks of Joseph Edward Timothy Siahaan.

## Install
QGIS → **Plugins → Manage and Install Plugins → All** → search **Seranta** → **Install**.
New versions appear under **Upgradeable**; no ZIP needed.

## The four tools (Processing Toolbox → Seranta, or menu Vector → Seranta)
| Tool | When | What you get |
|---|---|---|
| 1. Survey QC & Design Input | before design | homepass layer, pole KMZ, road layer, survey checks incl. cross-cluster duplicates, review remarks, `RINGKASAN_QC.html` |
| 2. FDT & FAT Allocation | planning | FAT groups along the route, colocation vs new FDT, link budget, `ALOKASI_FDT.html` |
| 3. Post-Design Tables | after design | FDT-FAT code table, colour-coded closure tables (KMZ/HTML) |
| 4. Design Package QC | before hand-over | 22 rules incl. seven package rules, one layer per rule, `QC_APD.html`, reviewer worklist `QC_APD_TEMUAN.xlsx`, CSV/JSON |

Each tool needs only **one folder**: pick it and click **Run**. Optional settings sit under **Advanced**.

Every HTML report starts with one sentence telling the reader what to do. Each rule explains **what was checked**,
**why it matters** and **what to do**; each finding is written in plain language with a map link, and the technical
detail is one click below. Fonts are embedded, so reports look the same offline and print cleanly to PDF.

The QC Findings Navigator panel (Vector → Seranta) takes the map straight to each finding and stores a review status
(verified, false positive, approved exception, resolved) that survives re-runs.

## Your own standards (profiles)
Thresholds live in JSON profiles (`profiles/`): every number carries its basis, source and approval status.
Bundled profiles: `APD_1X4` (default), `APD_1X8`, `REGULASI_KETAT`.

Organisation-specific profiles should be kept **outside** the plugin so updates never overwrite them. Seranta reads
extra profiles from, in order:
1. the folder in the environment variable `SERANTA_PROFILE_DIR`,
2. the QGIS setting `seranta/profile_dir`,
3. `<QGIS profile folder>/seranta/profiles/`,
4. `Documents/Seranta/profiles/` (or `~/Seranta/profiles/`) in your home folder.

A profile with `"default": true` is selected first. A profile with the same `profile_id` as a bundled one replaces it.

## Reference data
Service boundaries, existing-network KMZ, administrative-area attributes and design-software configs belong to your
team and are **not shipped with the plugin**. Seranta finds the reference folder near your survey folders, or you pick it once under Advanced in tool 1; the reports list what was found
and mark rules that could not be checked as *Belum bisa dicek* (UNVERIFIED) — never as a pass.

## Requirements
No extra Python packages, no internet, no account. The automatic design software is a separate product.
Menus, forms and messages are in English; reports and review remarks are in Indonesian.

## Development
See [CONTRIBUTING.md](CONTRIBUTING.md): tests,
release by git tag, automatic upload to the QGIS plugin repository.

## License and trademark
Code: GPL-2.0-or-later – see [LICENSE](LICENSE). Embedded fonts Inter and Poppins: SIL Open Font License 1.1
(`seranta/assets/fonts/OFL.txt`). Copies and modified versions must keep the author's name and the same licence, and must use
a different name and logo (the GPL does not cover the Seranta trademark).

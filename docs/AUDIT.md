# NESTfetch — Laporan Audit & Perbaikan

_Tanggal audit: 2026-07-21 · Versi yang diaudit: 4.8.0_

Dokumen ini merangkum hasil audit menyeluruh terhadap proyek **NESTfetch**
(sebelumnya "SwitchRoms scraper"), akar masalah yang ditemukan, dan perbaikan
yang sudah diterapkan. Tujuannya agar temuan bisa ditelusuri kembali dan tidak
terulang.

---

## 1. Ringkasan Eksekutif

NESTfetch adalah scraper metadata unduhan game multi-situs yang rapi dan modular:
pemisahan lapisan yang jelas (config → parser → engine → exporter → webapp),
66 unit test, arsitektur adapter berbasis JSON yang elegan, serta dokumentasi
yang kaya.

Namun ada **satu bug kritis yang membuat produk tidak sesuai dokumentasi**: 8 dari
9 situs yang "seharusnya" didukung sebenarnya **tidak ikut terpaket** karena aturan
`.gitignore` yang terlalu luas. Akibatnya `--list-sites` hanya menampilkan 1 situs
(`switchroms`), dan 8 test `test_real_*` gagal begitu file config JSON tidak ada.

Setelah perbaikan: **`--list-sites` = 9 situs**, dan **seluruh 72 test lulus**
(66 asli + 6 smoke test registry baru).

---

## 2. Temuan Kritis (sudah diperbaiki)

### C-1. Config situs tidak ikut terpaket karena `.gitignore` (BLOCKER)

- **Gejala:** `available_sites()` / `site_names()` hanya mengembalikan
  `['switchroms']`. Folder `sites/configs/` hanya berisi `README.md` — 8 file
  JSON hilang total.
- **Akar masalah:** `.gitignore` memuat aturan gebyah-uyah `*.json`. Karena file
  config situs berlokasi di `sites/configs/*.json`, semuanya ikut terabaikan dan
  tidak pernah masuk ke repositori/arsip.
- **Dampak:** Fitur inti v4.5–v4.8 (situs berbasis config) tidak berfungsi di
  luar mesin pengembang. 8 test `test_real_<site>_config` gagal.
- **Perbaikan:**
  - `.gitignore` diberi pengecualian eksplisit:
    ```gitignore
    *.json
    !requirements*.txt
    # ...but the shipped site configs ARE part of the package
    !sites/configs/
    !sites/configs/*.json
    ```
  - Ke-8 config JSON + 1 preset direkonstruksi ulang persis sesuai spesifikasi
    di `tests/test_config_adapter.py` (lihat bagian 5).
  - Ditambah **smoke test** (`tests/test_registry_smoke.py`) yang gagal keras bila
    registry turun di bawah 9 situs — supaya regresi kelas ini ketahuan langsung.
- **Verifikasi:** `site_names()` → 9 situs; seluruh test lulus.

---

## 3. Temuan Sedang (sudah diperbaiki)

### M-1. Versi tidak konsisten di dashboard web
- `webapp.py` menuliskan `APP_VERSION = "4.4"` dan footer `v4.4`, padahal
  `pyproject.toml`, `scraper.py`, dan `cli.py` semuanya `4.8`.
- **Perbaikan:** `APP_VERSION` → `"4.8"` dan footer dashboard → `v4.8`.

### M-2. Placeholder `USERNAME` di URL proyek
- `pyproject.toml` dan `CHANGELOG.md` masih memakai
  `github.com/USERNAME/nestfetch`.
- **Perbaikan:** diganti `github.com/CitraGivenchyA/nestfetch`.

### M-3. Sisa penamaan lama ("switchroms") di tempat generik
- `logger.py`: `setup_logger(name="switchroms")` → nama logger default proyek
  seharusnya netral.
- `config.py`: docstring "Central configuration for the SwitchRoms scraper."
- **Perbaikan:** logger default → `"nestfetch"`; docstring → "NESTfetch scraper".
  Catatan: `config.py::BASE_URL = "https://switchroms.io/"` **sengaja dibiarkan**
  karena itu memang base URL adapter bawaan `switchroms`, bukan branding.

### M-4. Dokumentasi "Project Structure" usang
- README masih menggambarkan pohon `switchroms-scraper/` era satu-situs (tanpa
  `sites/`, `webapp.py`, `tests/`, dll).
- **Perbaikan:** pohon struktur diperbarui agar mencerminkan layout multi-situs
  saat ini, termasuk `sites/configs/` yang kini dipaket.

---

## 4. Temuan Rendah / Catatan (belum diubah — disengaja)

Hal-hal berikut **bukan bug** tetapi layak dicatat. Sengaja tidak diubah agar
tidak mengganggu perilaku yang sudah stabil; didokumentasikan sebagai pekerjaan
lanjutan.

- **L-1. Dashboard `allow_actions=True` secara default.** Dashboard bisa memicu
  job scraping dari browser. Karena dashboard hanya mengikat ke `127.0.0.1`
  (localhost) secara default, risikonya rendah. Direkomendasikan: jangan expose
  ke jaringan/publik tanpa autentikasi. Didokumentasikan, bukan dinonaktifkan,
  demi UX.
- **L-2. ~41 blok `except Exception` yang menelan error.** Banyak yang memang
  disengaja (mis. "jangan biarkan satu config rusak mematikan CLI"). Mengubah
  massal berisiko menyembunyikan/menggeser perilaku. Rekomendasi lanjutan:
  persempit tipe exception dan tambahkan log level debug per kasus.
- **L-3. Beberapa URL search-result / full-site situs baru bersifat
  best-effort** (sudah ditandai di README/CHANGELOG). Parsing listing + detail
  sudah terverifikasi lewat sampel HTML; URL pencarian perlu verifikasi live.
- **L-4. Dependensi opsional** (`aiohttp`, `playwright`) tidak wajib; kode sudah
  punya fallback (mis. `async_client` jatuh ke mode threaded). Tetap disarankan
  mengunci versi di `requirements.txt` untuk reprodusibilitas.

---

## 5. Config Situs yang Direkonstruksi

Semua ditulis ulang agar **lolos persis** assertion di
`tests/test_config_adapter.py::test_real_*`:

| File | Situs | Catatan kunci |
|------|-------|---------------|
| `_preset_wordpress-repack.json` | (preset) | listing/detail WordPress, mirror `labeled_group`, `full_site` sitemap, filter hoster (TORRENT/ONEDRIVE/…). |
| `dodi.json` | DODI Repacks | `extends: wordpress-repack`, sweep sitemap seluruh situs. |
| `freelinuxpcgames.json` | Free Linux PC Games | kategori linux, link magnet/torrent. |
| `skidrowcodex.json` | SKIDROW CODEX | satu link gated, hoster dari host URL. |
| `ovagames.json` | OvaGames | judul dari atribut `title`, mirror filecrypt. |
| `romsfun.json` | RomsFun | dua langkah: `{base}download/{slug}-{post_id}`. |
| `coolrom.json` | CoolROM | dua langkah: `{base}dlpop.php?id={id}`, listing grid+list. |
| `nxbrew.json` | NXBrew | URL unduhan dari `onclick="window.open('…')"`. |
| `elamigos.json` | ElAmigos | multi-mirror, pembersihan simbol `★`. |

---

## 6. Verifikasi Akhir

- `site_names()` → `['coolrom','dodi','elamigos','freelinuxpcgames','nxbrew',`
  `'ovagames','romsfun','skidrowcodex','switchroms']` (9).
- Seluruh modul `.py` lolos `py_compile`.
- **72/72 test lulus** (66 asli + 6 smoke test registry).
- Tidak ditemukan pola berbahaya: tidak ada `eval(`, `exec(`, `shell=True`,
  atau `verify=False`.

> Catatan lingkungan: `pytest` tidak tersedia/tidak bisa dipasang di sandbox audit
> (jaringan mati). Test dijalankan lewat runner offline sederhana yang mengimpor
> tiap `tests/test_*.py` dan memanggil setiap fungsi `test_*`. Di lingkungan normal,
> `pytest` tetap berjalan seperti biasa.

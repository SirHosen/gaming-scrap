# 🚀 Major Update Roadmap — from "SwitchRoms Scraper" to a Multi-Site Game Download Platform

> Tujuan: mengubah scraper 1-situs (switchroms.io) menjadi **platform multi-situs**
> untuk situs-situs download game (ROM, game Windows, emulator, Linux, dll),
> lengkap dengan database + histori, otomatisasi + notifikasi, dan UI.
>
> Catatan: **Download manager TIDAK termasuk** (sesuai keputusan).

---

## 🎯 Visi arsitektur akhir

```
core/            # engine generik, tidak tahu-menahu soal situs tertentu
  engine.py      # orkestrasi: listing -> detail -> mirror -> final link
  http_client.py # HTTP + retry + (nanti) async
  models.py      # Game / Mirror / (baru) source_site, category, platform
sites/           # 1 file = 1 situs (PLUGIN)
  base.py        # SiteAdapter (antarmuka wajib tiap situs)
  registry.py    # daftar & lookup adapter by name
  switchroms.py  # switchroms.io (hasil migrasi kode sekarang)
  <site_baru>.py # situs lain (Windows/emulator/Linux) ditambah belakangan
storage/         # SQLite: simpan game, mirror, histori status link
linkcheck/       # link checker (sudah ada, dirapikan)
notify/          # backend notifikasi (Telegram / Discord / email)
ui/              # web dashboard atau GUI desktop
cli.py           # entry point terminal (pilih --site)
```

Inti perubahan: **`SiteAdapter`** — antarmuka seragam yang wajib dipenuhi tiap situs:

```python
class SiteAdapter:
    name: str            # "switchroms"
    base_url: str
    category: str        # "switch-rom" | "windows" | "emulator" | "linux" ...
    def build_listing_url(page, query) -> str
    def discover_all_urls() -> list[str]      # via sitemap / pagination
    def parse_listing(html) -> list[Game]
    def parse_detail(html) -> dict            # judul, metadata bersih
    def parse_mirrors(html, detail_url) -> list[Mirror]
    def resolve_final_link(html) -> str
```

Engine jadi generik: cukup di-inject sebuah adapter, sisanya jalan sama untuk
semua situs. Nambah situs baru = bikin 1 file di `sites/`, tanpa menyentuh engine.

---

## 🗺️ Tahapan (dikerjakan satu per satu)

### Phase 1 — Fondasi multi-situs (WAJIB pertama) ⭐ ✅ SELESAI (v4.0)
Merombak core jadi arsitektur adapter. Tanpa ini, fitur lain sulit dibangun.
- [x] Bikin `SiteAdapter` base class (`sites/base.py`) + `sites/registry.py`.
- [x] Migrasi seluruh logika switchroms.io ke `sites/switchroms.py` (kode lama tetap jalan, delegasi ke `parsers.py` + discovery sitemap pindah ke adapter).
- [x] Jadikan `engine.py` site-agnostic (di-inject `SiteAdapter`, tidak lagi import parser switchroms langsung).
- [x] Tambah field data model: `source_site`, `category`, `platform` (+ kolom baru di CSV/JSON).
- [x] CLI: pemilih situs interaktif + `--site switchroms` (default) + `--list-sites`.
- [x] Output CSV/JSON + link checker tetap jalan seperti sebelumnya (diverifikasi via test offline).
**Hasil:** program berperilaku persis sama, tapi kini siap ditambah situs lain — cukup bikin 1 file di `sites/`.

### Phase 2 — Database & histori (SQLite) 🗄️ ✅ SELESAI (v4.1)
- [x] Skema SQLite: `scrape_runs`, `games`, `mirrors`, `link_checks` (+ timestamp).
- [x] Simpan tiap hasil scrape ke DB (di samping CSV/JSON) — `output/nestfetch.db`.
- [x] Deteksi perubahan antar-scrape: game **baru / berubah / hilang** (removed hanya saat full scrape).
- [x] Lacak kapan sebuah link **mulai mati** (`first_dead_at` + histori status).
- [x] Export CSV/JSON ditarik dari DB (`--db-export`), plus `--history` & `--no-db`.
**Hasil:** tiap scrape kini punya memori — bisa lihat apa yang baru/berubah/hilang dan kapan link mulai mati.

### Phase 3 — Performa & kualitas ⚡
- [ ] Migrasi HTTP ke async (`aiohttp`) — jauh lebih cepat untuk ratusan halaman.
- [ ] Retry pintar + caching + rate-limit sopan per-situs.
- [ ] Test suite (pytest) untuk parser tiap situs + link checker (fixtures HTML offline).
- [ ] Packaging: `pip install .` / bundling `.exe` (opsional).

### Phase 4 — Otomatisasi & notifikasi 🔔
- [ ] Scheduler: cek link / scan game baru secara berkala.
- [ ] Notifikasi ke Telegram / Discord / email saat: link baru mati, atau game baru muncul.
- [ ] File konfigurasi (`.env` / `config.yaml`) untuk token & jadwal.

### Phase 5 — UI 🖥️
- [ ] Pilih: **web dashboard** (Flask/FastAPI + tabel filter/search) atau **GUI desktop**.
- [ ] Jalankan scrape & link-check lewat klik, lihat hasil + histori, filter per situs/kategori.

### (Berjalan paralel) Menambah situs baru ➕
Setelah Phase 1 selesai, situs baru bisa ditambah kapan saja (butuh contoh HTML
live dari tiap situs — sama seperti proses Gemini sebelumnya):
- [ ] Situs game Windows
- [ ] Situs emulator
- [ ] Situs game Linux
- [ ] dst.

---

## 📌 Rekomendasi urutan
**Phase 1 → 2 → 3 → 4 → 5**, sambil menambah situs baru begitu Phase 1 kelar.
Alasan: tiap fase membangun di atas fase sebelumnya, jadi meminimalkan rework.

---

## 🔤 Rename ✅ SELESAI
Nama proyek resmi kini: **NESTfetch** (dulu "SwitchRoms Scraper").
Banner, README, CLI, dan docstring sudah memakai branding NESTfetch v4.0.

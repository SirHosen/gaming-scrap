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

### Phase 3 — Performa & kualitas ⚡ ✅ SELESAI (v4.2)
- [x] Migrasi HTTP ke async (`aiohttp`) — opsional `--async`, fallback ke threaded jika tak terpasang.
- [x] Retry pintar (backoff + jitter, hormati `Retry-After`) + caching on-disk (`--cache`) + rate-limit sopan per-host (`--rate-limit`).
- [x] Test suite (pytest) untuk HTTP client, async fetcher, engine, exporter, database, link resolver (fixtures offline).
- [x] Packaging: `pip install .` → command `nestfetch` (`pyproject.toml`, extras `[async]/[browser]/[dev]`).
**Hasil:** scrape besar jadi lebih cepat & sopan, plus jaring pengaman test sebelum tiap rilis.

### Phase 4 — Otomatisasi & notifikasi 🔔 ✅ SELESAI (v4.3)
- [x] Scheduler (`--watch`): scrape/cek link berkala (`--interval`, `--task`, `--iterations`) — pure stdlib, clock injectable (teruji).
- [x] Notifikasi ke Telegram / Discord / email saat game baru muncul atau link baru mati (`--notify`, transport injectable & teruji offline).
- [x] File konfigurasi (`.env` / `config.yaml` / `config.json`) untuk token & jadwal — precedence env > .env > file > default, channel auto-aktif bila kredensial ada; `--notify-test` untuk uji setup.
**Hasil:** NESTfetch bisa jalan sendiri berkala dan langsung memberi tahu kamu saat ada game baru atau link mati — tanpa re-run manual.

### Phase 5 — UI 🖥️ ✅ SELESAI (v4.4)
- [x] **Web dashboard** dibangun di atas `http.server` standar (ZERO dependency — tanpa Flask/FastAPI), jalan offline: `python scraper.py --serve` (default http://127.0.0.1:8787).
- [x] Jalankan scrape & link-check lewat klik (job berjalan di background, status di-poll), lihat catalogue + histori + dead-links, filter/search per situs/kategori.
- [x] Fungsi data (stats/games/runs/dead-links/sites) dipisah dari layer HTTP sehingga teruji penuh offline (`tests/test_webapp.py`).
**Hasil:** seluruh fitur NESTfetch kini bisa dijalankan & dipantau dari browser, bukan hanya terminal.

### Phase 6 — Multi-site depth 🎯 ✅ SELESAI (v4.7)
- [x] **Filter format/hoster per-situs** — `--format`/`--hoster`, menu interaktif, dan `--list-sites` kini menampilkan pilihan milik situs terpilih (dari `filters` di config), bukan daftar Switch yang di-hardcode. Nilai tak dikenal lolos dengan peringatan (non-fatal).
- [x] **Mode full-catalogue DODI** — `full_site` di preset WordPress-repack: `--all` tanpa query menyapu seluruh situs via XML sitemap, fallback ke paginasi bila sitemap tak terjangkau.
- [x] **Fix `--all --search`** — kombinasi ini kini auto-paginasi hasil *pencarian*, bukan malah men-crawl seluruh situs.
- [x] **Link checker lebih pintar** — `--check-links` menghormati `--rate-limit` (jeda sopan per-host) dan `--cache` (cache verdict on-disk; hanya ACTIVE/DEAD yang di-cache).
**Hasil:** mesin multi-situs benar-benar terasa multi-situs — filter, full-scrape, dan cek link semuanya menyesuaikan situs yang dipilih.

### (Berjalan paralel) Menambah situs baru ➕
**Pondasi config-driven ✅ SELESAI (v4.5):** situs standar kini bisa ditambah
**tanpa nulis kode** — cukup drop file JSON di `sites/configs/` (dibaca otomatis
oleh `GenericConfigAdapter`). Situs yang terlalu "liar" (JS berat / ad-gate aneh)
tetap bisa pakai adapter Python sebagai escape hatch. Lihat
`sites/configs/README.md` untuk skema-nya. Tetap butuh contoh HTML live per situs
(dari proses Gemini) untuk mengisi selector-nya.

**Preset config ✅ SELESAI (v4.6):** situs sejenis kini berbagi satu "patokan"
(preset) lewat `extends`, jadi tiap situs baru cukup file ~4 baris. Ditambah
dukungan token `{base}`, mode mirror `labeled_group` (nama hoster = teks di depan
link), dan `resolve.mode: "none"` untuk situs yang link-nya lewat shortener/captcha.

Situs yang masih mau ditambah (butuh sampel HTML):
- [x] Situs game Windows — **DODI Repacks** (`--site dodi`) via preset `_preset_wordpress-repack.json`
- [ ] Situs game Windows lain (tinggal file ~4 baris `extends`)
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

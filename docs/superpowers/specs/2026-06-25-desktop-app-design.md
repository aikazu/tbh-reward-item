# TBH Desktop App — Design

Date: 2026-06-25
Status: Approved (brainstormed)

## Goal

Simple desktop GUI untuk TBH reward proxy: edit `config.json` (rules + port), pilih replacement reward ID dari list gear obtainable, dan run/stop `run_proxy.py` dengan log viewer real-time. Stack: Python + PySide6/Qt.

## Context

Project TBH adalah mitmproxy addon (`src/tbh_reward_hook.py`) yang me-rewrite `rewardItemId` response game Task Bar Hero. Saat ini config di-edit manual via `config.json`, proxy dijalankan via `scripts/run_proxy.sh` / `windows/run_proxy.bat`. Desktop app menyatukan workflow edit→run→debug.

List gear obtainable bersumber dari `https://taskbarhero.wiki/gear` (5760 total, filter obtainable only). Wiki render via JS — perlu verifikasi metode scrape (lihat Risk). Material/stage box bersumber dari `https://taskbarhero.org/en/tools/drops/` (domain beda, 115 material + 59 stage box + 20 gear, HTML table static — scrape mudah). Kedua sumber di-cache terpisah. Selain picker, setiap cell replacement ID bisa diketik manual untuk ID custom di luar kedua list.

## Architecture

```
tbh_desktop/
├── main.py                  # entry, QApplication
├── config_io.py             # load/save config.json (import ProxyConfig dari src/tbh_reward_hook.py)
├── gear_scraper.py          # fetch+parse wiki gear + drops tool, cache lokal
├── gear_cache.json          # cache gear obtainable (generated, gitignored)
├── drops_cache.json         # cache material/stage box dari drops tool (generated, gitignored)
├── proxy_runner.py          # subprocess run_proxy.py, stream stdout via Qt signal
└── ui/
    ├── main_window.py       # QMainWindow, layout 3 panel + toolbar
    ├── config_editor.py     # tab edit specific_queue_rules + range_replacement + port
    ├── gear_picker.py       # dialog pilih reward ID dari list gear obtainable
    ├── drops_picker.py       # dialog pilih reward ID dari material/stage box (drops tool)
    └── log_panel.py         # log viewer real-time, auto-scroll, cap 10k lines
```

App ditempatkan di root repo (`tbh_desktop/`), import `src.tbh_reward_hook` via path manipulation (`sys.path.insert` repo root) — gak duplikasi schema `ProxyConfig`/`QueueRule`/`RangeRule`.

## Components

### config_io
- Load `src/config.json` via `ProxyConfig.load()` dari `tbh_reward_hook`.
- Save: serialize kembali ke JSON, preserve key order + formatting (4-space indent) sesuai file existing. Tulis atomic (write temp + rename) supaya proxy hot-reload (mtime check di hook) gak baca file setengah tulis.
- Fallback: config invalid → pakai `_empty_config()`, tampilkan warning.

### gear_scraper
- **Gear source**: fetch `https://taskbarhero.wiki/gear` via `requests` (sudah available via mitmproxy dep).
  - Filter gear obtainable only. Wiki punya toggle "Obtainable only" yang di-render sebagai class/atribut HTML pada item card — scraper select item card yang ber-mark obtainable (verifikasi selector saat implementasi, fallback: fetch via toggle URL param kalau ada).
  - Extract per item: `(id, name, rarity, type, level)`.
  - Cache ke `gear_cache.json` dengan timestamp.
- **Drops source**: fetch `https://taskbarhero.org/en/tools/drops/`. HTML table static (lihat verify), parse tabel "By item": `(name, type, rarity)` + ID dari link href pattern `/en/items/.../<id>-<slug>/` atau dari asset image path `Item_<id>.png`.
  - Filter: Material + Stage box (skip gear — sudah ada di gear source).
  - Cache ke `drops_cache.json` dengan timestamp.
- Tombol "Refresh gear" + "Refresh drops" re-fetch masing-masing. Kalau gagal: pakai cache lama kalau ada, kalau kosong disable picker terkait + pesan error di log.
- `gear_cache.json` + `drops_cache.json` di-gitignore (generated, bisa besar). Tambah entry `tbh_desktop/gear_cache.json` dan `tbh_desktop/drops_cache.json` ke `.gitignore`.
- Manual input: setiap cell replacement ID (di specific_queue_rules dan range_replacement) editable langsung — ketik ID bebas, gak harus dari picker. Picker hanya convenience, bukan gate.

### proxy_runner
- `subprocess.Popen([sys.executable, "src/run_proxy.py"], cwd=repo_root, stdout=PIPE, stderr=STDOUT, bufsize=1, text=True)`.
- Thread baca stdout line-by-line, emit Qt signal `log_line(str)` ke log panel (thread-safe via signal/slot).
- `start()` → spawn, set status running. `stop()` → `proc.terminate()`, wait 3s, `kill()` kalau perlu.
- Cleanup saat app close: stop proxy kalau masih running.
- Status signal `running(bool)` untuk update tombol Start/Stop + dot indikator.

### main_window
- `QMainWindow`. Toolbar atas: [Start/Stop] [Refresh gear] [Refresh drops] [port field] [status dot].
- Layout: `QSplitter` horizontal — kiri `config_editor`, kanan `log_panel`. Splitter drag-resize.
- Menu: File (Save config, Exit), Help (About).

### config_editor
- Port field (`listen_port`) di toolbar (bukan di editor — satu field).
- Section "Specific Queue Rules": `QTableWidget` kolom [enabled (checkbox), name, item_id, replacement IDs (comma-join)]. Tombol [Add rule] [Remove rule] [Pick gear] [Pick material].
- Section "Range Replacement": checkbox enabled, field min_item_id, max_item_id, replacement IDs, [Pick gear] [Pick material].
- "Pick gear" → buka `gear_picker`, "Pick material" → buka `drops_picker`. Kembalikan list ID, tambah ke cell terpilih (merge, bukan overwrite).
- Advanced field (`only_post`, `require_boxes_marker`, `url_contains`) gak diekspos editor — tetap di config, app preserve saat save. Catatan: kalau user mau edit, langsung edit `config.json` (didokumentasikan di README).
- Save: validasi via `run_self_test` fixture? Tidak — self-test pakai fixture sendiri. Validasi: load ulang config setelah save, kalau `ProxyConfig.load()` raise → error dialog, jangan overwrite backup.

### gear_picker
- `QDialog` modal. Search box (filter name/id realtime) + `QListWidget` multi-select dengan icon gear.
- Data dari `gear_cache.json`.
- [OK] kembalikan list ID terpilih ke caller. [Cancel] batal.

### drops_picker
- `QDialog` modal. Identik dengan gear_picker tapi data dari `drops_cache.json` (material + stage box).
- Filter tambahan: dropdown Type (All/Material/Stage box), Rarity (All + tiers).
- [OK] kembalikan list ID terpilih. [Cancel] batal.

### log_panel
- `QPlainTextEdit` read-only, monospace, dark theme.
- Append line via slot `log_line(str)`. Auto-scroll ke bottom.
- Cap 10k line (FIFO, buang line tertua). Konteks menu: Clear, Save to file.

## Data Flow

```
config.json --load--> config_editor --save--> config.json (atomic write)
                          |
                   [Pick gear]     --> gear_picker  --> gear_cache.json
                   [Pick material] --> drops_picker --> drops_cache.json
                   [manual type]   --> ketik ID bebas di cell
                          |
                   [Start] --> proxy_runner --> run_proxy.py
                                 | stdout (QIODevice)
                                 v
                              log_panel
```

Hot-reload: proxy hook cek mtime `config.json` tiap request + SIGHUP. Save dari app → mtime change → proxy reload otomatis. Gak perlu restart proxy untuk apply config.

## Error Handling

- **Config invalid**: load `_empty_config()` fallback, warning dialog. Save gagal → jangan overwrite, simpan backup `.bak`.
- **Scrape gagal**: warning di log, pakai cache lama. Cache kosong → picker terkait disabled + pesan. Manual input tetap jalan terlepas dari cache.
- **Proxy crash / port dipakai**: stderr muncul di log, status set stopped, Start re-enabled.
- **App close saat proxy running**: konfirmasi dialog → stop proxy → exit.

## Testing

- **Unit** (`tests/`):
  - `config_io`: round-trip load/save preserve key order + field. Save atomic (file gak corrupt saat crash mid-write — test dengan mock interrupt).
  - `gear_scraper`: parse fixture HTML (simpan sample wiki page), assert list gear obtainable benar. Parse fixture drops table, assert material/stage box + ID benar.
  - `proxy_runner`: mock subprocess, assert signal emit saat line masuk, cleanup saat stop.
- **Manual**:
  - Edit config → Start → kirim fake request (curl ke proxy) → lihat log rewrite.
  - Save config saat proxy running → konfirmasi hot-reload (log "TBH Reward Proxy reloaded").
  - Start/Stop berkali-kali → gak zombie process.

## Scope (YAGNI)

- Gak buat installer/package (.exe/.AppImage) — jalankan via `python tbh_desktop/main.py`. Bisa ditambah nanti.
- Gak auto-update gear cache — manual via tombol Refresh.
- Gak multi-proxy / multi-profile — satu proxy instance.
- Gak edit advanced config field via GUI.
- Gak theme customizer — pakai Qt default atau flat dark.

## Risks

- **Wiki JS-rendered**: `requests.get` mungkin dapat HTML tanpa list gear (rendered client-side). Verifikasi pertama: fetch wiki, cek apakah list gear ada di HTML static. Kalau tidak, opsi: (a) pakai mitmproxy headless yang sudah jalan untuk fetch, (b) cari endpoint JSON API wiki, (c) user import manual. Decide saat implementasi `gear_scraper`.
- **Drops tool domain**: `.org` beda dengan gear `.wiki`. Drops tool HTML table static (verified via fetch), scrape rendah risiko. Tetap verifikasi selector + ID extraction pattern saat implementasi.
- **PySide6 dep size**: ~50MB. Tambah ke `requirements.txt` terpisah `requirements-desktop.txt` supaya install proxy gak berat.

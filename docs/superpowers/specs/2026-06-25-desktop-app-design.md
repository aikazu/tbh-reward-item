# TBH Desktop App — Design

Date: 2026-06-25
Status: Approved (brainstormed)

## Goal

Simple desktop GUI untuk TBH reward proxy: edit `config.json` (rules + port), pilih replacement reward ID dari list gear obtainable, dan run/stop `run_proxy.py` dengan log viewer real-time. Stack: Python + PySide6/Qt.

## Context

Project TBH adalah mitmproxy addon (`src/tbh_reward_hook.py`) yang me-rewrite `rewardItemId` response game Task Bar Hero. Saat ini config di-edit manual via `config.json`, proxy dijalankan via `scripts/run_proxy.sh` / `windows/run_proxy.bat`. Desktop app menyatukan workflow edit→run→debug.

List gear obtainable bersumber dari `https://taskbarhero.wiki/gear` (5760 total, filter obtainable only). Wiki render via JS — perlu verifikasi metode scrape (lihat Risk).

## Architecture

```
tbh_desktop/
├── main.py                  # entry, QApplication
├── config_io.py             # load/save config.json (import ProxyConfig dari src/tbh_reward_hook.py)
├── gear_scraper.py          # fetch+parse wiki, cache lokal
├── gear_cache.json          # cache gear obtainable (generated, gitignored)
├── proxy_runner.py          # subprocess run_proxy.py, stream stdout via Qt signal
└── ui/
    ├── main_window.py       # QMainWindow, layout 3 panel + toolbar
    ├── config_editor.py     # tab edit specific_queue_rules + range_replacement + port
    ├── gear_picker.py       # dialog pilih reward ID dari list gear obtainable
    └── log_panel.py         # log viewer real-time, auto-scroll, cap 10k lines
```

App ditempatkan di root repo (`tbh_desktop/`), import `src.tbh_reward_hook` via path manipulation (`sys.path.insert` repo root) — gak duplikasi schema `ProxyConfig`/`QueueRule`/`RangeRule`.

## Components

### config_io
- Load `src/config.json` via `ProxyConfig.load()` dari `tbh_reward_hook`.
- Save: serialize kembali ke JSON, preserve key order + formatting (4-space indent) sesuai file existing. Tulis atomic (write temp + rename) supaya proxy hot-reload (mtime check di hook) gak baca file setengah tulis.
- Fallback: config invalid → pakai `_empty_config()`, tampilkan warning.

### gear_scraper
- Fetch `https://taskbarhero.wiki/gear` via `requests` (sudah available via mitmproxy dep).
- Filter gear obtainable only. Wiki punya toggle "Obtainable only" yang di-render sebagai class/atribut HTML pada item card — scraper select item card yang ber-mark obtainable (verifikasi selector saat implementasi, fallback: fetch via toggle URL param kalau ada).
- Extract per item: `(id, name, rarity, type, level)`.
- Cache ke `gear_cache.json` dengan timestamp. Cache dipakai saat picker dibuka.
- Tombol "Refresh gear" re-fetch. Kalau gagal: pakai cache lama kalau ada, kalau kosong disable picker + pesan error di log.
- `gear_cache.json` di-gitignore (generated, bisa besar).

### proxy_runner
- `subprocess.Popen([sys.executable, "src/run_proxy.py"], cwd=repo_root, stdout=PIPE, stderr=STDOUT, bufsize=1, text=True)`.
- Thread baca stdout line-by-line, emit Qt signal `log_line(str)` ke log panel (thread-safe via signal/slot).
- `start()` → spawn, set status running. `stop()` → `proc.terminate()`, wait 3s, `kill()` kalau perlu.
- Cleanup saat app close: stop proxy kalau masih running.
- Status signal `running(bool)` untuk update tombol Start/Stop + dot indikator.

### main_window
- `QMainWindow`. Toolbar atas: [Start/Stop] [Refresh gear] [port field] [status dot].
- Layout: `QSplitter` horizontal — kiri `config_editor`, kanan `log_panel`. Splitter drag-resize.
- Menu: File (Save config, Exit), Help (About).

### config_editor
- Port field (`listen_port`) di toolbar (bukan di editor — satu field).
- Section "Specific Queue Rules": `QTableWidget` kolom [enabled (checkbox), name, item_id, replacement IDs (comma-join)]. Tombol [Add rule] [Remove rule] [Pick rewards].
- Section "Range Replacement": checkbox enabled, field min_item_id, max_item_id, replacement IDs, [Pick rewards].
- "Pick rewards" → buka `gear_picker`, kembalikan list ID, tulis ke cell terpilih.
- Advanced field (`only_post`, `require_boxes_marker`, `url_contains`) gak diekspos editor — tetap di config, app preserve saat save. Catatan: kalau user mau edit, langsung edit `config.json` (didokumentasikan di README).
- Save: validasi via `run_self_test` fixture? Tidak — self-test pakai fixture sendiri. Validasi: load ulang config setelah save, kalau `ProxyConfig.load()` raise → error dialog, jangan overwrite backup.

### gear_picker
- `QDialog` modal. Search box (filter name/id realtime) + `QListWidget` multi-select dengan icon gear.
- Data dari `gear_cache.json`.
- [OK] kembalikan list ID terpilih ke caller. [Cancel] batal.

### log_panel
- `QPlainTextEdit` read-only, monospace, dark theme.
- Append line via slot `log_line(str)`. Auto-scroll ke bottom.
- Cap 10k line (FIFO, buang line tertua). Konteks menu: Clear, Save to file.

## Data Flow

```
config.json --load--> config_editor --save--> config.json (atomic write)
                          |
                   [Pick rewards] --> gear_picker --> gear_cache.json
                          |
                   [Start] --> proxy_runner --> run_proxy.py
                                 | stdout (QIODevice)
                                 v
                              log_panel
```

Hot-reload: proxy hook cek mtime `config.json` tiap request + SIGHUP. Save dari app → mtime change → proxy reload otomatis. Gak perlu restart proxy untuk apply config.

## Error Handling

- **Config invalid**: load `_empty_config()` fallback, warning dialog. Save gagal → jangan overwrite, simpan backup `.bak`.
- **Scrape gagal**: warning di log, pakai cache lama. Cache kosong → picker disabled + pesan.
- **Proxy crash / port dipakai**: stderr muncul di log, status set stopped, Start re-enabled.
- **App close saat proxy running**: konfirmasi dialog → stop proxy → exit.

## Testing

- **Unit** (`tests/`):
  - `config_io`: round-trip load/save preserve key order + field. Save atomic (file gak corrupt saat crash mid-write — test dengan mock interrupt).
  - `gear_scraper`: parse fixture HTML (simpan sample wiki page), assert list gear obtainable benar.
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
- **PySide6 dep size**: ~50MB. Tambah ke `requirements.txt` terpisah `requirements-desktop.txt` supaya install proxy gak berat.

# TBH Desktop App — Design

Date: 2026-06-25
Status: Approved (brainstormed)

## Goal

Simple desktop GUI untuk TBH reward proxy: edit `config.json` (rules + port), pilih replacement reward ID dari list gear obtainable, dan run/stop `run_proxy.py` dengan log viewer real-time. Stack: Python + PySide6/Qt.

## Context

Project TBH adalah mitmproxy addon (`src/tbh_reward_hook.py`) yang me-rewrite `rewardItemId` response game Task Bar Hero. Saat ini config di-edit manual via `config.json`, proxy dijalankan via `scripts/run_proxy.sh` / `windows/run_proxy.bat`. Desktop app menyatukan workflow edit→run→debug.

List gear obtainable bersumber dari `https://taskbarhero.wiki/gear` (5760 total, filter obtainable only). Gear wiki menyatukan multi-grade (semua tier/level jadi satu entry per item) — dipakai untuk replacement gear. Material/basic loot per-box bersumber dari page box spesifik `https://taskbarhero.org/en/items/chests/<item_id>-<slug>/` yang punya "Loot table" akurat (item + drop rate). Wiki gear render via JS — perlu verifikasi metode scrape (lihat Risk). Page box HTML static — scrape mudah. Selain picker, setiap cell replacement ID bisa diketik manual untuk ID custom.

Dua mode pemilihan replacement:
- **White/Blue box (specific_queue_rules)**: per-box akurat. Replacement = campuran loot table box (material/basic, ID yang memang ada di box itu — mencegah gagal) + gear dari wiki gear (multi-grade, digabung). Tidak pakai drops tool global.
- **range_replacement**: bebas. Replacement = manual / picker gear wiki / picker material — tidak terikat box tertentu.

## Architecture

```
tbh_desktop/
├── main.py                  # entry, QApplication
├── config_io.py             # load/save config.json (import ProxyConfig dari src/tbh_reward_hook.py)
├── gear_scraper.py          # fetch+parse wiki gear + page box loot table, cache lokal
├── gear_cache.json          # cache gear obtainable (generated, gitignored)
├── box_loot_cache/          # cache per-box loot table (generated, gitignored, key by box id)
├── proxy_runner.py          # subprocess run_proxy.py, stream stdout via Qt signal
└── ui/
    ├── main_window.py       # QMainWindow, layout 3 panel + toolbar
    ├── config_editor.py     # tab edit specific_queue_rules + range_replacement + port
    ├── gear_picker.py       # dialog pilih reward ID dari list gear obtainable (wiki gear)
    ├── box_loot_picker.py    # dialog pilih reward ID dari loot table box spesifik (akurat per-box)
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
  - Extract per item: `(id, name, rarity, type, level)`. Gear wiki menyatukan multi-grade jadi satu entry per nama item (semua tier/level digabung) — ini yang dipakai replacement gear.
  - Cache ke `gear_cache.json` dengan timestamp.
- **Box loot source**: fetch `https://taskbarhero.org/en/items/chests/<item_id>-<slug>/` per box ID (slug di-resolve via search/redirect, atau pattern dari box name). HTML static, parse section "Loot table": `(name, rate)` + ID dari link href `/en/items/.../<id>-<slug>/` atau asset image `Item_<id>.png` / `<SLOT>_<id>.png` (gear dalam loot pakai gear ID, link ke gear page).
  - Cache per box ke `box_loot_cache/<box_id>.json` dengan timestamp. Reuse kalau box sama.
  - Hanya item yang tercantum di loot table yang valid — mencegah replacement ID melenceng (gagal rewrite).
- Tombol "Refresh gear" (global) + refresh otomatis saat buka box_loot_picker kalau cache box itu belum ada/expired. Kalau gagal: pakai cache lama kalau ada, kalau kosong disable picker terkait + pesan error di log.
- `gear_cache.json` + `box_loot_cache/` di-gitignore (generated, bisa besar). Tambah entry ke `.gitignore`.
- Manual input: setiap cell replacement ID (di specific_queue_rules dan range_replacement) editable langsung — ketik ID bebas, gak harus dari picker. Picker hanya convenience, bukan gate.

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
- Section "Specific Queue Rules": `QTableWidget` kolom [enabled (checkbox), name, item_id, replacement IDs (comma-join)]. Tombol [Add rule] [Remove rule] [Pick from box loot] [Pick gear]. "Pick from box loot" pakai `item_id` row terpilih sebagai box ID → fetch loot table box itu.
- Section "Range Replacement": checkbox enabled, field min_item_id, max_item_id, replacement IDs, [Pick gear] [Pick material manual]. Range bebas: tombol [Pick gear] buka gear_picker; ID lain diketik manual (gak terikat box).
- "Pick from box loot" → buka `box_loot_picker` (item akurat dari box terpilih). "Pick gear" → buka `gear_picker` (multi-grade wiki). Kembalikan list ID, tambah ke cell terpilih (merge, bukan overwrite).
- Advanced field (`only_post`, `require_boxes_marker`, `url_contains`) gak diekspos editor — tetap di config, app preserve saat save. Catatan: kalau user mau edit, langsung edit `config.json` (didokumentasikan di README).
- Save: validasi via `run_self_test` fixture? Tidak — self-test pakai fixture sendiri. Validasi: load ulang config setelah save, kalau `ProxyConfig.load()` raise → error dialog, jangan overwrite backup.

### gear_picker
- `QDialog` modal. Search box (filter name/id realtime) + `QListWidget` multi-select dengan icon gear.
- Data dari `gear_cache.json`.
- [OK] kembalikan list ID terpilih ke caller. [Cancel] batal.

### box_loot_picker
- `QDialog` modal. Dibuka dengan box ID dari row terpilih (`item_id` rule White/Blue).
- Fetch + parse page box `https://taskbarhero.org/en/items/chests/<box_id>-<slug>/` (cache per-box). Tampilkan "Loot table": `QListWidget` multi-select, tiap row `(name, type, rate)` + icon. Hanya item di loot table yang muncul — akurat, mencegah ID melenceng.
- Search box filter name/id realtime.
- [OK] kembalikan list ID terpilih ke caller. [Cancel] batal.
- Error: box ID tidak valid / page tidak ada → pesan, fallback ke cache lama kalau ada.

### log_panel
- `QPlainTextEdit` read-only, monospace, dark theme.
- Append line via slot `log_line(str)`. Auto-scroll ke bottom.
- Cap 10k line (FIFO, buang line tertua). Konteks menu: Clear, Save to file.

## Data Flow

```
config.json --load--> config_editor --save--> config.json (atomic write)
                          |
   specific_queue_rules:
     [Pick from box loot] --> box_loot_picker --> box_loot_cache/<box_id>.json  (akurat per-box)
     [Pick gear]          --> gear_picker     --> gear_cache.json              (multi-grade)
   range_replacement:
     [Pick gear]          --> gear_picker
     [manual type]        --> ketik ID bebas di cell                            (bebas)
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
  - `gear_scraper`: parse fixture HTML (simpan sample wiki page), assert list gear obtainable benar. Parse fixture page box, assert loot table + ID benar (material + gear dalam loot).
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
- **Box page slug resolution**: URL butuh slug (`910801-normal-monster-box-lv80`). Slug bisa di-resolve via: (a) search endpoint wiki, (b) redirect dari URL tanpa slug, (c) pattern dari box name di config. Verifikasi saat implementasi. Page box HTML static (verified via fetch), scrape rendah risiko.
- **PySide6 dep size**: ~50MB. Tambah ke `requirements.txt` terpisah `requirements-desktop.txt` supaya install proxy gak berat.

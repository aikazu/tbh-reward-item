# TBH Reward Proxy

> **⚠️ DWYOR — Do With Your Own Risk**
>
> Tools ini memodifikasi traffic jaringan game. Penggunaannya dapat melanggar
> Terms of Service game dan **berisiko akun di-banned**. Pembuat tidak
> bertanggung jawab atas konsekuensi apa pun. Gunakan dengan risiko sendiri.

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![mitmproxy](https://img.shields.io/badge/mitmproxy-12%2B-E66733?logo=mitmproxy&logoColor=white)
![PySide6](https://img.shields.io/badge/PySide6-6.6%2B-41CD52?logo=qt&logoColor=white)
![platform](https://img.shields.io/badge/platform-Linux%20%7C%20Windows-blue)

[Bahasa Indonesia](README.id.md) · [English](README.md)

## ❤️ Dukungan

Kalau proyek ini membantu, dukung pengembangannya — scan QRIS di bawah atau kunjungi [qrisly.net/kcmon](https://qrisly.net/kcmon):

<img src="qris.webp" alt="QRIS" width="240" />

Man-in-the-middle proxy yang me-rewrite field `rewardItemId` pada response
backend game TBH. Berjalan di atas [mitmproxy](https://mitmproxy.org/),
dengan opsi GUI desktop [PySide6](https://www.qt.io/) untuk edit rule
visual, pemilihan reward-ID dari wiki, dan kontrol proxy live.

Addon berada di antara klien game dan backend TBH — menukar reward item
sesuai aturan di `config.json`, lalu meneruskan response yang sudah
dimodifikasi kembali. Tanpa patching, tanpa injeksi — murni proxy
jaringan.

---

## Daftar Isi

- [Cara Kerja](#cara-kerja)
- [Mulai Cepat](#mulai-cepat)
- [Konfigurasi](#konfigurasi)
  - [Rule Spesifik](#rule-spesifik)
  - [Rule Range](#rule-range)
- [Menjalankan Proxy](#menjalankan-proxy)
  - [Hot Reload](#hot-reload)
- [Kesadaran Anti-Cheat](#kesadaran-anti-cheat)
  - [Sistem Suffix](#sistem-suffix)
  - [Picker Suffix-Aware](#picker-suffix-aware)
  - [Monitoring Tamper](#monitoring-tamper)
- [Aplikasi Desktop](#aplikasi-desktop)
  - [Instalasi & Menjalankan](#desktop-install-id)
  - [Tur UI](#ui-tour-id)
  - [Fitur](#fitur)
  - [Interaksi Hot-Reload](#interaksi-hot-reload)
  - [Keterbatasan](#keterbatasan)
- [Setup Klien Steam (TaskBarHero via Proton)](#setup-klien-steam)
- [Sertifikat CA](#sertifikat-ca)
- [Self-Test](#self-test)
- [Pemecahan Masalah](#pemecahan-masalah)
- [Peringatan Keamanan](#peringatan-keamanan)
- [Struktur File](#struktur-file)
- [Ucapan Terima Kasih](#ucapan-terima-kasih)

---

## Cara Kerja

Addon hook event `response` dari mitmproxy. Pipeline filter:

1. **Filter method** — bila `only_post: true`, hanya POST yang diproses.
2. **Filter URL** — URL response harus mengandung salah satu marker di `url_contains`.
3. **Filter body marker** — bila `require_boxes_marker: true`, body harus mengandung literal `"boxes"`.
4. **Rewrite** — regex cari `"itemId":<n>` lalu `"rewardItemId":<m>` setelahnya. Bila itemId cocok rule, ganti `rewardItemId` dengan nilai dari `replacement_reward_item_ids` (siklis per kecocokan).
5. **Tulis balik** — `response.set_text()` dengan body baru.

```
Klien --POST--> [mitmproxy:8877] --forward--> Backend TBH
                      |
                      v
                 response (JSON boxes)
                      |
                 hook: rewrite rewardItemId
                      |
Klien <--mod response-- [mitmproxy:8877]
```

Prioritas rule: **rule spesifik dulu, baru range**. Rule spesifik cocokkan
`itemId` persis; range cocokkan rentang `[match_min_item_id, match_max_item_id]`.

Regex memakai escape backslash untuk menangani JSON yang mungkin ter-escape
(`\"itemId\"` maupun `"itemId"`).

---

## Mulai Cepat

```bash
# 1. Install mitmproxy (Arch / CachyOS)
sudo pacman -S mitmproxy

# 2. Verifikasi
mitmdump --version
python3 src/tbh_reward_hook.py --self-test

# 3. Jalankan proxy
mitmdump -s src/tbh_reward_hook.py --listen-port 8877 \
    --set block_global=false -q

# 4. Arahkan klien game ke 127.0.0.1:8877 (HTTP/HTTPS proxy)
```

Untuk alur kerja visual dengan edit rule dan pemilihan reward-ID, lihat
[Aplikasi Desktop](#aplikasi-desktop).

---

## Konfigurasi

Edit `src/config.json`. Bentuk:

```json
{
  "listen_port": 8877,
  "only_post": true,
  "require_boxes_marker": true,
  "url_contains": ["/backend-function/base/v1"],
  "specific_queue_rules": [
    {
      "enabled": true,
      "name": "Normal Box",
      "item_id": 910801,
      "level": 12,
      "replacement_reward_item_ids": [135001, 605041, 605051]
    }
  ],
  "range_replacement": {
    "enabled": false,
    "name": "Range replacement",
    "match_min_item_id": 500000,
    "match_max_item_id": 950000,
    "replacement_reward_item_ids": [529191, 419191, 409191]
  }
}
```

`level` opsional (dipakai picker desktop untuk mencocokkan gear ke rentang
level box; addon-nya sendiri mengabaikannya).

### Rule Spesifik

Cocokkan `itemId` secara persis. Setiap match mengonsumsi satu nilai dari
`replacement_reward_item_ids` secara siklis (index modulo panjang list).

Contoh: Normal Box `910801` dengan replacements `[135001, 605041, 605051]`.
Hit Normal Box pertama jadi `135001`, kedua `605041`, ketiga `605051`,
keempat wrap kembali ke `135001`, dan seterusnya.

### Rule Range

`enabled: false` default. Bila aktif, cocokkan `itemId` dalam rentang
`[match_min_item_id, match_max_item_id]`. Prioritas: rule spesifik
dievaluasi dulu; bila tidak cocok, cek range.

Siklis sama: satu nilai per match, modulo panjang list.

---

## Menjalankan Proxy

```bash
./scripts/run_proxy.sh          # Linux
windows\run_proxy.bat           # Windows
```

Atau langsung:

```bash
mitmdump -s src/tbh_reward_hook.py --listen-port 8877 \
    --set block_global=false -q
```

Contoh output:

```
[TBH] TBH Reward Proxy loaded: 1 specific rules active, range=off.
[TBH] TBH Reward Proxy replaced [Normal Box] itemId=910801: rewardItemId=1001->135001
[TBH] TBH Reward Proxy wrote 1 replacement(s).
```

Stop dengan `Ctrl+C`. Arahkan klien target ke proxy `127.0.0.1:8877`.

### `--mode local` (spawn scoped, tanpa Steam Launch Options)

`--mode local:NAME` mitmproxy men-spawn executable bernama `NAME` dengan
proxy env + CA auto-inject, lalu cuma intercept traffic proses itu. Berguna
di Windows yang edit Steam Launch Options ribet, atau kapanpun lo mau
scoping tanpa sentuh system proxy.

```bash
# CLI
./scripts/run_proxy.sh --mode local --name TaskBarHero.exe
windows\run_proxy.bat --mode local --name TaskBarHero.exe
```

Atau di `src/config.json`:

```json
{
    "mode": "local",
    "local_process_name": "TaskBarHero.exe",
    "listen_port": 8877
}
```

- **Windows**: jalan out of the box. Direkomendasikan daripada Steam Launch Options.
- **Linux**: local redirector mitmproxy pakai helper setuid, jadi mitmdump
  akan prompt `sudo` saat startup. Jalankan sebagai root atau pre-elevate:
  `sudo -E ./scripts/run_proxy.sh --mode local --name <proc>`.

### Hot Reload

`config.json` di-**hot-reload** — tanpa restart proxy. Addon cek mtime
file di setiap response yang di-intercept dan reload otomatis saat
berubah.

- Edit `config.json`, simpan → request berikutnya pakai rule baru. Log:
  `TBH Reward Proxy reloaded: ...`.
- Reload manual tanpa edit: `pkill -HUP -f mitmdump`.
- **Safety config corrupt**: bila `config.json` invalid (JSON rusak,
  tipe salah), addon tetap pakai **config terakhir yang valid** dan log
  `kept previous config (config.json invalid)`. Edit salah tidak pernah
  mematikan intercept aktif. Perbaiki file lalu simpan untuk reload.
- Bila `config.json` hilang/corrupt saat startup, proxy start dengan
  fallback config kosong (tanpa rule) dan log `using fallback empty config`.

Restart proxy hanya perlu untuk mengganti `listen_port` (mitmproxy bind
port saat startup).

---

## Kesadaran Anti-Cheat <a id="kesadaran-anti-cheat"></a>

Klien TBH punya **validator anti-cheat sisi-klien**. Setelah
`processBoxV2` membuat reward tertunda, klien menyimpan cache
`<itemKey, rewardItemId>`. Saat operasi inventory berikutnya
(`consume`, `exchange`, atau membuka box lain), klien cross-check
`rewardItemId` yang di-cache terhadap nilai kebenaran dari
`pendingTx.tid`. Jika beda, klien mengirim:

```
POST /data/gameLog/v2/TemperedItem/90
{"msg":"TamperedItemIdDetected","data":{"mismatches":["<itemKey>:<orig>-><used>", ...]}}
```

Server mengembalikan `204 No Content` — hanya dicatat. **Belum ada ban
yang teramati**, tapi laporan berulang mengakumulasi jejak. Forensik
lengkap di [`docs/analysis/tbh-network-forensics.md`](docs/analysis/tbh-network-forensics.md).

### Sistem Suffix <a id="sistem-suffix"></a>

Validator klien hanya mengecek **3 digit terakhir** dari `rewardItemId`
(rarity × 100 + tier), bukan ID 6-digit penuh. Struktur ItemId:

```
ABCDEF where:
  AB  = kategori 2-digit (30=sword, 50=helmet, 60=amulet, dll.)
  C   = rarity (0=Common ... 9=Cosmic) ← ini yang dicek validator
  DEF = tier + slot (3-digit)
```

**Aturan**: pilih replacement yang 3 digit terakhirnya cocok dengan
3 digit terakhir drop asli. Kategori (2 digit pertama) bebas berubah.

| Drop asli | Replacement aman | Suffix |
|---|---|---|
| `319171` (Cosmic Bow) | `419171` (Cosmic Axe) | `171` ✓ |
| `190004` (Soulstone Torment) | `114004` (Emerald) | `004` ✓ |
| `311171` (Uncommon Bow) | `419171` (Cosmic Axe) | `171` ✓ |

| Drop asli | Replacement berbahaya | Kenapa |
|---|---|---|
| `190004` | `419171` | suffix `004`→`171` = MISMATCH = tamper report |

Pool suffix box (diverifikasi dari capture):

| Jenis box | Suffix dominan |
|---|---|
| Normal Box (`910801`) | `171`, `017`, `004`, `003`, `001` |
| Stage Boss Box (`920801`) | `004` (dominan), `017`, `171` |

### Picker Suffix-Aware <a id="picker-suffix-aware"></a>

Dialog **BoxLootPicker** dan **GearPicker** punya checkbox baru
"Suffix-aware". Saat diaktifkan:

- Tiap baris menampilkan badge `~XXX` (3 digit terakhir)
- Dropdown "Suffix:" muncul — filter item berdasarkan suffix
- Gunakan untuk mempersempit ke item yang suffix-nya cocok dengan
  drop asli, sehingga hanya memilih replacement yang validator-safe

Saat dimatikan, picker berperilaku seperti biasa (tanpa noise suffix).

**Alur kerja rekomendasi**:
1. Cek suffix reward asli (dari data capture atau tabel di atas)
2. Aktifkan "Suffix-aware" di picker
3. Pilih suffix yang cocok di dropdown
4. Pilih item high-value dari list yang sudah difilter

### Monitoring Tamper <a id="monitoring-tamper"></a>

Addon punya **TamperDetector pasif** yang:

- Memantau response `POST /data/gameLog/v2/TemperedItem/90`
- Mencatat tiap mismatch ke `logs/tamper-events.jsonl` dengan field
  terstruktur: `itemKey`, `original_id`, `used_id`, `original_rarity`,
  `used_rarity`, `original_tier`, `used_tier`, `last3_preserved`
- Mencetak `TAMPER WARNING: N mismatch(es)... Session total: M` ke
  stdout (terlihat di log panel desktop)

Di **aplikasi desktop**, status bar menampilkan counter live:
`⚠ Tamper reports this session: M`. Counter reset ke 0 saat sesi proxy
baru dimulai.

Jika muncul tamper report: ID replacement kamu suffix-nya tidak cocok.
Gunakan suffix-aware picker untuk memperbaiki config.

---

## Aplikasi Desktop

GUI PySide6 opsional yang membungkus `config.json` dan `run_proxy.py`
yang sama dengan CLI. Memungkinkan mengedit rule secara visual, memilih
reward ID dari wiki/loot table TBH, dan menjalankan proxy tanpa
meninggalkan window.

GUI **tidak** menggantikan addon proxy — ia menjalankan `src/run_proxy.py`
sebagai subprocess dan me-stream stdout-nya. Aturan hot-reload yang sama
tetap berlaku.

### Instalasi & Menjalankan <a id="desktop-install-id"></a>

Dependensi desktop sengaja dipisah dari `requirements.txt` (mitmproxy)
agar install proxy tetap ringan. Aplikasi desktop butuh:

| Paket | Fungsi |
|---|---|
| `PySide6` | Framework GUI |
| `requests` + `beautifulsoup4` + `lxml` | Scraping HTML wiki |
| `playwright` + `cloakbrowser` | Engine browser stealth untuk gear scrape |
| `pytest-qt` | Tes GUI |
| `Pillow` | Image cache (untuk ikon ItemCard) |

#### Linux (Arch / CachyOS / distro apapun)

Launcher (`scripts/launch_desktop.sh`) **tidak** mengharuskan venv.
Ia resolve interpreter Python di repo root dengan urutan:

  1. `<repo>/.venv/bin/python` — kalau kamu bikin venv, itu yang dipakai
  2. `python3` di PATH
  3. `python` di PATH

Pilih cara yang sesuai setup kamu:

**Opsi A — system Python (tanpa venv):** install deps desktop secara
global lalu jalankan langsung. Cocok di Arch karena mayoritas deps
sudah dipaketkan:

```bash
sudo pacman -S python-pyside6 python-requests python-beautifulsoup4
python -m pip install --break-system-packages -r requirements-desktop.txt
./scripts/launch_desktop.sh
```

> `playwright` dan `cloakbrowser` cuma ada di pip — tidak ada paket
> pacman-nya. Pakai `--break-system-packages` (atau `pipx`) karena
> PEP 668 memblokir pip install ke system secara default di Arch.

**Opsi B — virtual environment (direkomendasikan untuk isolasi):**

```bash
cd TBH
python -m venv .venv
.venv/bin/pip install -r requirements-desktop.txt
./scripts/launch_desktop.sh          # cek + jalankan
./scripts/launch_desktop.sh --check  # cek saja, tidak menjalankan
```

Launcher memverifikasi Python, deps, mitmproxy, `config.json`, dan
binary CloakBrowser sebelum memulai. Bila ada yang kurang, ia menampilkan
command fix yang tepat — menggunakan interpreter yang ter-resolve (venv
atau system), jadi hint-nya selalu bisa langsung dijalankan.

**Atau jalankan manual** (lewati readiness check):

```bash
.venv/bin/python -m tbh_desktop.main
```

**Langkah 3 — (Opsional) Install browser engine Playwright untuk fallback:**

CloakBrowser mengunduh binary Chromium stealth-nya sendiri saat first
launch (~200 MB, di-cache lokal). Kamu hanya perlu `playwright install
chromium` jika ingin fallback stock-Playwright (dipakai saat CloakBrowser
tidak terinstall):

```bash
.venv/bin/playwright install chromium
```

> **Catatan untuk Arch users:** PySide6, python-requests, dan
> python-beautifulsoup4 juga tersedia via pacman (`sudo pacman -S
> pyside6 python-requests python-beautifulsoup4`), tapi memakai venv
> lebih simpel dan menghindari masalah PEP 668. `playwright` dan
> `cloakbrowser` hanya tersedia via pip — tidak ada paket pacman.

#### Windows

Launcher (`windows\launch_desktop.bat`) **tidak** mengharuskan venv.
Ia resolve interpreter Python di repo root dengan urutan:

  1. `<repo>\.venv\Scripts\python.exe` — kalau kamu bikin venv, itu yang dipakai
  2. `py` (Windows Python Launcher) di PATH
  3. `python` di PATH

Pilih cara yang sesuai setup kamu:

**Opsi A — system Python (tanpa venv):** install deps desktop secara
global lalu jalankan langsung.

```bat
python -m pip install -r requirements-desktop.txt
windows\launch_desktop.bat
```

**Opsi B — virtual environment (direkomendasikan untuk isolasi):**

```bat
cd TBH
python -m venv .venv
.venv\Scripts\pip install -r requirements-desktop.txt
windows\launch_desktop.bat            :: cek + jalankan
windows\launch_desktop.bat --check   :: cek saja
```

> Jika `python` tidak ditemukan, coba `py -3 -m venv .venv` (memakai py launcher).

Launcher memverifikasi Python, deps, mitmproxy, `config.json`, dan
binary CloakBrowser sebelum memulai. Bila ada yang kurang, ia menampilkan
command fix yang tepat.

**Atau jalankan manual:**

```bat
.venv\Scripts\python -m tbh_desktop.main
```

**Langkah 3 — (Opsional) Install browser engine Playwright untuk fallback:**

```bat
.venv\Scripts\playwright install chromium
```

Sama seperti Linux — hanya dibutuhkan untuk fallback stock-Playwright.
CloakBrowser mengelola binary-nya sendiri.

#### CloakBrowser (mesin stealth scraping)

Mulai v0.4+, gear scraper memakai
[CloakBrowser](https://github.com/CloakHQ/CloakBrowser) — build Chromium
stealth dengan 58 patch anti-detection level C++ source — sebagai mesin
scraping. Drop-in replacement untuk `chromium.launch()` Playwright dan
mengunduh binary patched-nya sendiri saat first use (~200 MB, di-cache
lokal, Ed25519-verified). Tidak perlu `playwright install` terpisah
untuk CloakBrowser, tapi paket `playwright` Python tetap harus terinstall
(CloakBrowser bergantung padanya untuk API kompatibel-Playwright).

Keunggulan CloakBrowser dibanding Playwright biasa untuk scraping:

- Lewat Cloudflare Turnstile, reCAPTCHA v3 (skor 0.9), FingerprintJS, BrowserScan
- `humanize=True` — gerakan mouse Bézier seperti manusia, timing keyboard per-karakter, scroll realistis
- `navigator.webdriver` di-patch ke `false` di level C++ source
- TLS fingerprint identik dengan Chrome asli (ja3n/ja4/akamai match)

Bila CloakBrowser tidak terinstall (`pip install cloakbrowser`), scraper
otomatis fallback ke stock Playwright `chromium.launch()`. Langkah
`playwright install chromium` hanya dibutuhkan untuk fallback tersebut.

Addon proxy (`requirements.txt` / `mitmproxy`) tetap dibutuhkan agar
Start/Stop berfungsi — lihat [Mulai Cepat](#mulai-cepat) di atas.

### Tur UI <a id="ui-tour-id"></a>

![Aplikasi Desktop — main window](desktop-app.webp)

Shell tersusun dari empat zone, masing-masing dengan tugas berbeda:

| Zone | Lokasi | Fungsi |
|---|---|---|
| **Toolbar** | Atas | Start/Stop proxy · Scrape data · Check data · Save · Reset · Copy Steam launch option · Buka catalog popup · Field port · Status badge |
| **Panel RULES** (kiri) | Splitter 30% | Daftar `specific_queue_rules` sebagai kartu, plus form `range_replacement` di bawah. Klik rule untuk memuatnya ke panel detail. |
| **Panel DETAIL** (kanan) | Splitter 70% | Editor per-rule: item ID, level, tiga tombol Pick (box / loot / gear), dan baris chip replacement-ID. Klik chip untuk menghapus ID tersebut. |
| **Log dock** | Bawah (collapsible, 80px max) | Stdout ter-stream dari subprocess proxy + event scrape. Toggle via `View → Log panel`. |

**Status badge** (kanan-atas toolbar) adalah indikator state proxy yang
otoritatif: dot berwarna + label `STOPPED` / `RUNNING`. Tombol Start
hanya aktif saat proxy berhenti; Stop hanya aktif saat proxy berjalan.

![Aplikasi Desktop — Catalog popup](desktop-app-catalog.webp)

**Catalog popup** adalah browser item catalog in-game satu-halaman dengan
search-first. Klik tombol `Catalog` di toolbar untuk membukanya; klik di
luar untuk menutup. Ia menggabungkan tiga sumber data menjadi satu list
datar:

- Gear cache (`tbh_desktop/gear/{category}/{rarity}.json`)
- Drops index (`tbh_desktop/drops_index.json` — materials + boxes)
- Box slug cache (`tbh_desktop/box_slug_cache.json`)

Chip filter (`All` / `Gear` / `Materials` / `Boxes`) mempersempit list
hasil. Baris diurutkan berdasarkan rarity (Cosmic → Common) dan di-tint
berdasarkan rarity agar drop high-tier tampak visual. Klik tunggal atau
double-click baris untuk route ID item ke target aktif (rule yang sedang
diedit, atau form range bila form tersebut punya fokus).

### Fitur

- **Dark theme** — palet Catppuccin Mocha diterapkan ke seluruh app.
  Warna konsisten untuk tombol, tabel, list, input, log panel, dan
  picker. Log panel memakai font monospace FiraCode/JetBrainsMono di
  atas background crust yang lebih gelap untuk keterbacaan
  terminal-like.

- **Shell 2-pane** — `RULES` (kiri, ~30%) + `DETAIL` (kanan, ~70%)
  dengan splitter draggable 6px. Drag untuk resize; splitter punya
  background surface1 yang terlihat agar benar-benar bisa di-grab
  (handle default 4px invisible Qt membingungkan user yang menganggap
  layout-nya fixed).

- **Detail panel** — permukaan edit utama. Berisi nama rule yang
  dipilih, item ID, level, dan baris chip replacement. Tiga tombol Pick
  membuka picker modal terkait:
  - **Pick box** → `BoxPicker` (pilih stage chest via id)
  - **Pick loot** → `BoxLootPicker` scoped ke drop table box tersebut
  - **Pick gear** → `GearPicker` difilter berdasarkan rentang level box

- **Rule list** — setiap rule adalah `RuleCard` mandiri dengan toggle
  enable, field name, field item_id, badge REPLACES, dan baris chip.
  Baris chip mirror apa yang ada di detail panel — keduanya tetap sinkron
  karena berbagi sumber data `RuleCard` yang sama.

- **Range form** — berada di bawah panel kiri (tunggal, karena
  `range_replacement` adalah singleton). Fokuskan form untuk
  mengalihkan panel detail ke state summary "Range replacement".

- **Save atomic** — memvalidasi dengan `ProxyConfig.load` sebelum dan
  sesudah tulis. Backup file sebelumnya sebagai `config.json.bak`,
  tulis via temp + rename, restore dari backup bila re-validasi gagal.
  Save yang gagal tidak pernah mematikan intercept aktif.

- **Edit `src/config.json` visual** — editor hanya mengelola
  `specific_queue_rules` dan `range_replacement`. Field advanced
  (`only_post`, `require_boxes_marker`, `url_contains`) **tidak**
  diekspos di GUI tapi **dipertahankan** saat save: editor membaca file
  sebagai raw dict dan hanya menyentuh field yang ia miliki.

- **Pilih reward ID** — setiap cell `Replacement IDs` mendukung input
  manual, ditambah:
  - **Pick box loot** — menyelesaikan slug box dengan mencari `box_id`
    di tabel items wiki (`https://taskbarhero.org/en/items` tabel
    "Stage chests"), fetch loot table per-box dari
    `https://taskbarhero.org/en/items/chests/<id>-<slug>/`, parse, dan
    izinkan multi-select. Map id→slug di-cache di
    `tbh_desktop/box_slug_cache.json`; loot di-cache per-box di
    `tbh_desktop/box_loot_cache/<box_id>.json`.
  - **Pick gear** — membaca dari file cache per-kategori×rarity di
    `tbh_desktop/gear/` (layout nested:
    `tbh_desktop/gear/{category}/{rarity}.json`, mis.
    `tbh_desktop/gear/weapon/legendary.json`). Tiga filter:
    **Kategori** (Weapon / Off-hand / Armor / Accessory / All),
    **Grade** (Legendary / Immortal / Arcana / Beyond / Celestial /
    Divine / Cosmic / All — Legendary ke atas saja), dan **Rentang
    level** (min/max 1-100). Multi-select list dan search box
    dipertahankan.
  - **Pick dari catalog** — popup `Catalog` toolbar menggabungkan gear
    + drops index + box slugs menjadi satu list search-first dengan
    chip filter rarity. Klik baris untuk route ID-nya ke target aktif
    seperti picker khusus.

- **Scrape data** — satu tombol yang menjalankan gear scrape (stealth
  browser, semua grade Legendary+ × semua kategori, "Obtainable only")
  dan fetch drops index secara paralel. Log total count saat selesai.
  Fallback ke stock Playwright bila CloakBrowser tidak terinstall.

- **Check data** — menampilkan count, timestamp last-fetched, dan
  penggunaan disk untuk tiap cache (drops index, gear cache, box drop
  map) tanpa scrape. Berguna untuk "apa perlu re-scrape?" secara
  sekilas.

- **Suffix-aware picker** — BoxLootPicker dan GearPicker punya checkbox
  "Suffix-aware". Saat aktif, tiap baris menampilkan badge `~XXX`
  (3 digit terakhir = rarity+tier) dan dropdown memfilter item berdasarkan
  suffix. Gunakan untuk memilih replacement yang validator-safe (suffix
  sama = tidak ada `TamperedItemIdDetected`). Lihat
  [Kesadaran Anti-Cheat](#kesadaran-anti-cheat).

- **Tamper counter** — status bar menampilkan `⚠ Tamper reports this
  session: M`, di-parse dari stdout `TAMPER WARNING` addon. Reset ke 0
  saat sesi proxy baru dimulai. Memberi visibilitas live ke perilaku
  anti-cheat tanpa scroll log panel.

- **Start / Stop proxy** — jalankan `src/run_proxy.py` sebagai
  subprocess (cwd = repo root, process group sendiri). Status badge
  jadi `RUNNING` dengan dot hijau; log dock stream stdout secara real
  time (FIFO capped di 10k baris). Stop kirim SIGTERM ke seluruh
  process group, escalate ke SIGKILL setelah 3 detik. Bila field port
  toolbar berbeda dari `listen_port` yang tersimpan saat Start diklik,
  app memprompt "Port changed. Save config first?" — Yes simpan lalu
  start, No batalkan. Ini mencegah desync senyap di mana proxy
  berjalan di port lama sementara UI menampilkan port baru.

- **Copy Steam launch option** — menyalin port saat ini ke string
  `HTTP_PROXY=... HTTPS_PROXY=... %command%`, siap di-paste ke Steam →
  TaskBarHero → Properties → Launch Options. Tooltip update live saat
  kamu edit port.

- **Save config** — atomic, tervalidasi (lihat di atas). mtime-based
  hot-reload yang sama seperti edit manual.

- **Reset config** — kembalikan template default (setelah prompt
  konfirmasi). Bila proxy berjalan, tanya untuk menghentikannya dulu.

- **Close confirm** — bila proxy atau gear scraper berjalan, menutup
  window akan konfirmasi sebelum menghentikannya.

- **Menu** — File (Save config, Reset config to default, Exit). View
  (toggle Log panel, Item browser — buka Catalog popup). Help (About).

### Interaksi Hot-Reload

GUI mengedit **`config.json` yang sama** yang dibaca addon. Save dari
GUI mengubah mtime file, sehingga cek mtime per-response addon langsung
mengambil rule baru pada request berikutnya — tanpa restart proxy.

Pengecualian: `listen_port`. Field toolbar menulis ke `config.json`,
tapi mitmproxy bind port saat startup, jadi menggantinya perlu restart
proxy (Stop → Start). Tombol Start sekarang menjaga terhadap desync:
bila port toolbar berbeda dari `listen_port` yang tersimpan saat Start
diklik, ia memprompt untuk save dulu (Yes simpan lalu start, No
batalkan) alih-alih start di port tersimpan yang basi.

### Keterbatasan

- **Box loot butuh `item_id` valid** di baris rule yang dipilih, dan
  box harus ada di tabel "Stage chests" wiki di
  `https://taskbarhero.org/en/items`. Slug diselesaikan via lookup
  `box_id` terhadap tabel tersebut (di-cache di
  `tbh_desktop/box_slug_cache.json`), sehingga `name` yang cocok tidak
  lagi dibutuhkan. Box langka atau baru yang belum ada di wiki akan
  gagal lookup — fallback dengan mengetik ID langsung di cell.

- **Scrape data butuh CloakBrowser + browser engine** terinstall (`pip
  install cloakbrowser`). CloakBrowser mengunduh binary Chromium
  patched ~200 MB saat first launch (di-cache lokal). Tanpa itu,
  scraper fallback ke stock Playwright (`playwright install chromium`
  dibutuhkan).

- **Gear scrape hanya mencakup grade Legendary ke atas** (Legendary /
  Immortal / Arcana / Beyond / Celestial / Divine / Cosmic) pada empat
  kategori (Weapon / Off-hand / Armor / Accessory). Grade lebih rendah
  (Common / Uncommon / Rare) tidak di-scrape GUI — ketik ID-nya
  langsung bila perlu.

- **Picker butuh network** untuk fetch data segar; fallback ke cache
  bila fetch gagal (silent — lihat log panel untuk warning-nya).

- GUI hanya-baca terhadap config di disk; edit bersamaan dari tool lain
  tidak terdeteksi. Bila kamu edit file di luar GUI saat ia terbuka,
  restart app untuk membaca ulang.

---

## Setup Klien Steam <a id="setup-klien-steam"></a>

TaskBarHero adalah game Unity Windows (Steam AppId 3678970) yang berjalan
via Proton + SteamLinuxRuntime_4 + pressure-vessel di Linux. Sandbox
mengisolasi network namespace dan tidak meneruskan env proxy host
secara default.

### Metode yang berhasil: Steam Launch Options (dites, konfirmasi jalan)

Steam → klik kanan **TaskbarHero** → Properties → **Launch Options**,
isi:

```
HTTP_PROXY=http://127.0.0.1:8877 HTTPS_PROXY=http://127.0.0.1:8877 %command%
```

![Steam Launch Options](steam-launch-options.webp)

Proton meneruskan env var ini ke proses Wine, di mana `HttpClient` Unity
membacanya.

Tombol `Copy Steam` di aplikasi desktop menyalin string yang sama untuk
port toolbar saat ini — tanpa edit manual.

### Trust CA di prefix Proton

Unity/Proton memakai **cert store Wine/Proton Windows**, bukan Linux
system trust. Install CA mitmproxy ke prefix Proton (AppId 3678970):

```bash
WINEPREFIX=~/.local/share/Steam/steamapps/compatdata/3678970/pfx \
  wine certmgr -add -c -root ~/.mitmproxy/mitmproxy-ca-cert.cer
```

Bila `certmgr` tidak tersedia di prefix tersebut, salin cert ke
direktori CA Wine:

```bash
PFX=~/.local/share/Steam/steamapps/compatdata/3678970/pfx
cp ~/.mitmproxy/mitmproxy-ca-cert.cer "$PFX/drive_c/windows/system32/cert/CA/"
```

### Catatan

- Native Unity socket (bukan HttpClient) bisa mengabaikan env proxy
  terlepas dari metode.
- AppId 3678970 adalah judul Steam komersial — intercept/modifikasi
  traffic-nya dapat melanggar ToS Steam dan/atau game. Hanya untuk akun
  sendiri di environment terkontrol.
- Bila env Launch Options diabaikan, alternatif: transparent iptables
  redirect (host layer, perlu bypass isolasi network pressure-vessel)
  atau Wine proxy registry
  (`HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings`).

---

## Sertifikat CA

mitmproxy intercept HTTPS dengan CA miliknya sendiri. Klien harus trust
CA ini, jika tidak akan muncul error sertifikat. CA di-generate otomatis
saat `mitmdump` pertama jalan, lokasi `~/.mitmproxy/`.

### Linux (system trust)

Install:

```bash
./scripts/install_cert.sh
```

Script auto re-exec via sudo, pakai `trust anchor --store` +
`update-ca-trust extract`. Verifikasi:

```bash
trust list | grep -i mitmproxy
```

Hapus (setelah selesai intercept):

```bash
./scripts/remove_cert.sh
```

### Windows (system trust)

Install (auto-elevate ke admin via prompt UAC):

```bat
windows\install_cert.bat
```

Pakai `certutil -addstore -f "Root"` untuk menambah cert (default:
`%USERPROFILE%\.mitmproxy\mitmproxy-ca-cert.cer`) ke store Trusted Root
Certification Authorities. Override path cert via env var
`MITMPROXY_CA_CERT`. Verifikasi:

```bat
certutil -store Root | findstr /i mitmproxy
```

Kalau PowerShell tidak tersedia dan script belum elevated, script akan
print instruksi untuk klik kanan → "Run as administrator".

> Catatan: belum ada `windows\remove_cert.bat` — untuk hapus, buka
> `certmgr.msc` → Trusted Root Certification Authorities →
> Certificates → cari `mitmproxy` → Delete.

### Firefox

Firefox punya store sendiri dan tidak baca system trust.

1. `about:preferences#privacy`
2. Certificates → View Certificates → tab **Authorities**
3. Import → `~/.mitmproxy/mitmproxy-ca-cert.pem`
4. Centang "Trust this CA to identify websites" → OK

### Chromium / Chrome

Membaca system trust (langkah Linux di atas cukup). Atau bypass via
flag:

```bash
chromium --ignore-certificate-errors-spki-list=$(openssl x509 -in ~/.mitmproxy/mitmproxy-ca-cert.pem -pubkey -noout | openssl pkey -pubin -outform der | openssl dgst -sha256 -binary | base64)
```

### Klien Lain

- **Electron/Node**: `NODE_EXTRA_CA_CERTS=~/.mitmproxy/mitmproxy-ca-cert.pem`
- **Python (requests/urllib)**: `SSL_CERT_FILE=~/.mitmproxy/mitmproxy-ca-cert.pem` atau `REQUESTS_CA_BUNDLE=...`
- **Android emulator**: push cert ke `/system/etc/security/cacerts/` (proses berbeda).
- **Windows klien**: import `.cer` via `certmgr.msc` → Trusted Root.

---

## Self-Test

Tes rewrite offline tanpa proxy berjalan. Memvalidasi logika regex + rule
terhadap fixture internal (TIDAK membaca `config.json` live):

```bash
./scripts/self_test.sh          # Linux
windows\self_test.bat           # Windows
```

Output sukses (satu baris):

```
Self-test OK.
```

Self-test memakai fixture hard-coded untuk menguji rule engine end-to-end.
Perbarui `run_self_test()` di `src/tbh_reward_hook.py` bila mengubah
logika rule agar test tetap relevan.

---

## Pemecahan Masalah

| Gejala | Penyebab | Solusi |
|---|---|---|
| `ModuleNotFoundError: mitmproxy` | mitmproxy belum terinstall | `sudo pacman -S mitmproxy` / `./scripts/install_requirements.sh` |
| Proxy jalan tapi response tidak berubah | URL/body tidak match filter | Cek `url_contains`, pastikan body mengandung `"boxes"`. Lihat log `[TBH] matched URL but found no replaceable` |
| Klien error sertifikat HTTPS | CA belum di-trust | Jalankan `./scripts/install_cert.sh` (lihat [Sertifikat CA](#sertifikat-ca)) |
| `AssertionError` di self-test | Fixture mismatch setelah ubah rule | Perbarui expected value di `run_self_test()` |
| Port 8877 dipakai | Konflik port | Ubah `listen_port` di `config.json` |
| Firefox tetap error | Store terpisah | Import manual via `about:preferences#privacy` |
| `sudo: a terminal is required` | sudo non-interaktif tanpa TTY | Jalankan via prefix `!` di prompt, atau `echo PASS \| sudo -S ...` |
| GUI desktop crash saat launch di Plasma Wayland | Bug PySide6 / driver Xe | Selalu export `QT_QPA_PLATFORM=offscreen` di CachyOS meski jalan interaktif |

Debug verbose (tanpa `-q`):

```bash
mitmdump -s src/tbh_reward_hook.py --listen-port 8877 \
    --set block_global=false --flow-detail 2
```

---

## Peringatan Keamanan

**CA mitmproxy bisa menandatangani HTTPS apapun.** Bila mesin ini trust
CA tersebut, siapa pun yang menjalankan proxy di mesin ini bisa
intercept seluruh traffic terenkripsi.

- Hanya install CA pada environment yang kamu kontrol (dev/test).
- Hapus CA setelah tidak dipakai: `./scripts/remove_cert.sh`.
- Jangan commit file `~/.mitmproxy/mitmproxy-ca*.pem` ke repo apapun.
- Jangan bagikan CA private key (`mitmproxy-ca.pem`, `mitmproxy-ca.p12`).
- Penggunaan pada layanan/game pihak ketiga dapat melanggar ToS.
  Tanggung jawab pengguna.

---

## Struktur File

```
TBH/
├── src/                              # addon mitmproxy (pure stdlib + mitmproxy)
│   ├── tbh_reward_hook.py            # TBHRewardHook + RewardRewriter + TamperDetector
│   ├── tbh_proxy_config.py           # dataclass ProxyConfig / QueueRule / RangeRule
│   ├── run_proxy.py                  # launcher (mitmdump atau python -m mitmproxy)
│   ├── config_setup.py               # ensure_config() — copy default → live
│   ├── config.default.json           # template seed (box IDs: 910801, 920801)
│   └── config.json                   # di-generate first run, hot-reloaded
├── tbh_desktop/                      # GUI PySide6 opsional
│   ├── main.py                       # entry: QApplication + theme + handler SIGINT
│   ├── paths.py                      # re-export dari src/config_setup.py
│   ├── config_io.py                  # load/save (validate → atomic temp+rename → re-validate → restore .bak)
│   ├── proxy_runner.py               # subprocess + group SIGTERM/SIGKILL + stdout→Qt signal
│   ├── scraper.py                    # gear + box loot + drops index scrape
│   ├── gear_scraper_runner.py        # wrapper thread QObject di sekitar scraper.refresh_gear_full
│   └── ui/
│       ├── main_window.py            # shell 2-pane (RULES + DETAIL) + toolbar + menu
│       ├── config_editor.py          # membungkus RuleListView + RangeForm
│       ├── rule_list.py              # list scrollable widget RuleCard
│       ├── rule_card.py              # rule tunggal: toggle, name, id, baris chip
│       ├── rule_detail_panel.py      # editor panel kanan untuk rule aktif
│       ├── active_target.py          # union RuleTarget | RangeTarget
│       ├── item_browser.py           # konten catalog (di-embed di popup)
│       ├── catalog_popup.py          # wrapper QMenu yang meng-host ItemBrowser
│       ├── item_card.py              # chip item tunggal border rarity
│       ├── gear_picker.py            # GearView (GearPicker dialog = shim)
│       ├── box_picker.py             # BoxView
│       ├── box_loot_picker.py        # BoxLootView
│       ├── status_badge.py           # pill dot berlabel (STOPPED / RUNNING)
│       ├── log_panel.py              # dock bawah, monospace
│       ├── theme.py                  # palet Catppuccin Mocha + rarity + ornament
│       └── image_cache.py            # loader ikon async
├── scripts/                          # run_proxy, install_requirements, self_test,
│                                     #   install_cert, remove_cert, launch_desktop
├── windows/                          # ekuivalen Windows + install_cert.bat
├── tests/                            # config_io, scraper, proxy_runner,
│                                     #   gear_picker, main_window (gui-marked),
│                                     #   reward_rewriter (Rewriter + TamperDetector)
├── docs/                             # specs + plans
│   └── analysis/                     # forensik jaringan + write-up capture
│       ├── tbh-network-forensics.md  # notebook berjalan (suffix system, tid mapping, §10.12)
│       └── capture-20260628-193055.md # forensik capture pertama
├── requirements.txt                  # mitmproxy
├── requirements-desktop.txt          # PySide6, requests, bs4, lxml, pytest-qt,
│                                     #   playwright, cloakbrowser, Pillow
├── desktop-app.webp                  # screenshot hero main window
├── desktop-app-catalog.webp          # screenshot catalog popup
├── steam-launch-options.webp         # referensi Steam launch options
├── README.md
└── README.id.md
```

Cache `tbh_desktop/gear/` (JSON gear per kategori×rarity, nested),
`tbh_desktop/item/` (JSON material per family×rarity, nested),
`tbh_desktop/box_slug_cache.json` (map box_id → slug), dan
`tbh_desktop/box_loot_cache/` pada aplikasi desktop bersifat generated
tapi **di-track di git** agar deploy baru tidak perlu scrape ulang. Hapus
untuk memaksa re-fetch dari wiki. Layout lama flat-file
`tbh_desktop/gear/{category}_{rarity}.json` sudah digantikan oleh layout
nested `gear/{category}/{rarity}.json` dan tidak lagi ditulis oleh
picker.

---

## Sangkalan

Perangkat lunak ini disediakan **hanya untuk tujuan edukasi dan riset**.
Dengan menggunakannya Anda menyetujui ketentuan berikut:

- **Tanpa jaminan.** Perangkat lunak disediakan "SEBAGAIMANA ADANYA", tanpa
  jaminan apa pun, tersurat maupun tersirat. Seluruh risiko ada pada Anda.
- **Tanpa tanggung jawab.** Pembuat dan kontributor **tidak bertanggung jawab**
  atas kerusakan, kehilangan akun, ban, atau konsekuensi lain dari penggunaan.
- **Ketentuan layanan.** Memintercept dan memodifikasi traffic game dapat
  melanggar ToS game dan/atau Steam dan berisiko **ban akun atau tindakan
  hukum** dari pihak terkait.
- **Akun milik sendiri.** Gunakan hanya pada akun dan perangkat yang Anda
  miliki atau secara eksplisit berwenang untuk diuji.
- **Ganti rugi.** Anda setuju membebaskan pembuat dari klaim atau tanggung
  jawab apa pun yang timbul dari penggunaan Anda.

Lihat file [LICENSE](LICENSE) untuk teks lengkap lisensi MIT.

---

## Ucapan Terima Kasih

Proyek ini dibangun di atas teknik **Persistent Reward Item Generator**
yang diteliti dan dibagikan oleh komunitas UnknownCheats. Thread asli:
[TBH - Persistent Reward Item Generator](https://www.unknowncheats.me/forum/other-games/758547-tbh-persistent-reward-item-generator.html).
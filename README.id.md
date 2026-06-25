# TBH Reward Proxy

[Bahasa Indonesia](README.id.md) · [English](README.md)

Man-in-the-middle proxy yang me-rewrite field `rewardItemId` pada response backend game TBH. Berjalan di atas [mitmproxy](https://mitmproxy.org/).

Mengintercept response POST ke endpoint tertentu, mengganti reward item sesuai aturan pada `config.json`, lalu meneruskan hasil modifikasi ke klien.

---

## Daftar Isi

- [Komponen](#komponen)
- [Cara Kerja](#cara-kerja)
- [Persyaratan](#persyaratan)
- [Instalasi](#instalasi)
  - [Linux (Arch / CachyOS)](#linux-arch--cachyos)
  - [Windows](#windows)
- [Konfigurasi](#konfigurasi)
  - [Rule Spesifik (specific_queue_rules)](#rule-spesifik-specific_queue_rules)
  - [Rule Range (range_replacement)](#rule-range-range_replacement)
- [Menjalankan Proxy](#menjalankan-proxy)
  - [Reload config](#reload-config)
- [Aplikasi Desktop](#aplikasi-desktop)
  - [Instalasi](#desktop-install-id)
  - [Menjalankan](#desktop-launch-id)
  - [Fitur](#desktop-features-id)
  - [Interaksi Hot-Reload](#desktop-hot-reload-id)
  - [Keterbatasan](#desktop-limitations-id)
- [Setup Klien Steam (TaskBarHero via Proton)](#setup-klien-steam-taskbarhero-via-proton)
- [Sertifikat CA](#sertifikat-ca)
  - [Linux (system trust)](#linux-system-trust)
  - [Firefox](#firefox)
  - [Chromium / Chrome](#chromium--chrome)
  - [Klien Lain](#klien-lain)
- [Self-Test](#self-test)
- [Pemecahan Masalah](#pemecahan-masalah)
- [Peringatan Keamanan](#peringatan-keamanan)
- [Struktur File](#struktur-file)
- [Ucapan Terima Kasih](#ucapan-terima-kasih)

---

## Komponen

| File | Fungsi |
|---|---|
| `tbh_reward_hook.py` | Addon mitmproxy. Logika intercept + rewrite. Platform-agnostic, pure Python stdlib. |
| `config.json` | Aturan rewrite: port dengar, filter URL, rule spesifik, rule range. |
| `run_proxy.py` | Launcher: cari `mitmdump`, fallback ke modul `mitmproxy.tools.main`. |
| `run_proxy.sh` / `run_proxy.bat` | Wrapper shell menjalankan `run_proxy.py`. |
| `install_requirements.sh` / `.bat` | Install dependensi (`mitmproxy`). |
| `self_test.sh` / `.bat` | Jalankan tes rewrite offline (tanpa proxy berjalan). |
| `install_cert.sh` | Install CA mitmproxy ke system trust store (Linux). |
| `remove_cert.sh` | Hapus CA mitmproxy dari system trust store (Linux). |
| `requirements.txt` | Dependensi: `mitmproxy`. |
| `requirements-desktop.txt` | Dep opsional desktop: `PySide6`, `requests`, `beautifulsoup4`, `pytest-qt`. |
| `tbh_desktop/` | GUI PySide6 opsional: edit `config.json`, pilih reward ID, jalankan/stop proxy, stream log. Lihat [Aplikasi Desktop](#aplikasi-desktop). |
| `tests/` | Suite pytest untuk aplikasi desktop (`config_io`, `scraper`, `proxy_runner`). |
| `docs/` | Specs + implementation plans. |

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

Regex menggunakan escape backslash untuk menangani JSON yang mungkin ter-escape (`\"itemId\"` maupun `"itemId"`).

---

## Persyaratan

- Python 3.10+ (typing modern `dict[str, Any]`, `tuple[str, ...]`).
- `mitmproxy` 10+ (dites pada 12.2.3).
- Akses sudo (Linux) untuk install cert + dependensi.

---

## Instalasi

### Linux (Arch / CachyOS)

Dependensi `mitmproxy` tersedia di repo `extra`:

```bash
sudo pacman -S mitmproxy
```

Atau lewat skrip (otomatis cek + install via pip bila `mitmdump` tidak ada — pada Arch pip diblokir PEP 668, jadi pacman lebih disarankan):

```bash
./scripts/install_requirements.sh
```

Verifikasi:

```bash
mitmdump --version
python3 src/tbh_reward_hook.py --self-test
```

### Windows

```bat
windows\install_requirements.bat
```

Memakai `py` bila ada, fallback `python`. Install `mitmproxy` via pip.

---

## Konfigurasi

Edit `config.json`. Format:

```json
{
  "listen_port": 8877,
  "only_post": true,
  "require_boxes_marker": true,
  "url_contains": ["/backend-function/base/v1"],
  "specific_queue_rules": [
    {
      "enabled": true,
      "name": "White box",
      "item_id": 910801,
      "replacement_reward_item_ids": [519171, 519171, 519171]
    }
  ],
  "range_replacement": {
    "enabled": false,
    "name": "Range replacement",
    "match_min_item_id": 500000,
    "match_max_item_id": 950000,
    "replacement_reward_item_ids": [529191, 419191, 409191, 619191, 429191, 509191]
  }
}
```

### Rule Spesifik (specific_queue_rules)

Cocokkan `itemId` secara persis. Setiap match mengonsumsi satu nilai dari `replacement_reward_item_ids` secara siklis (index modulo panjang list).

Contoh: White box `910801` → ganti reward jadi `519171`. Bila ada 3 box White, semuanya jadi `519171` (list punya 3 elemen identik).

### Rule Range (range_replacement)

`enabled: false` default. Bila aktif, cocokkan `itemId` dalam rentang `[match_min_item_id, match_max_item_id]`. Prioritas: rule spesifik dievaluasi lebih dulu; bila tidak match, cek range.

Siklis sama: satu nilai per match, modulo panjang list.

---

## Menjalankan Proxy

```bash
./scripts/run_proxy.sh          # Linux
windows\run_proxy.bat           # Windows
```

Atau langsung:

```bash
mitmdump -s src/tbh_reward_hook.py --listen-port 8877 --set block_global=false -q
```

Output (hanya log TBH):

```
[TBH] TBH Reward Proxy loaded: 2 queue rules, range mode=off.
[TBH] TBH Reward Proxy replaced White box: itemId=910801, rewardItemId=1001->519171
[TBH] TBH Reward Proxy wrote 3 replacement(s).
```

Stop: `Ctrl+C`.

Arahkan klien target ke proxy `127.0.0.1:8877` (HTTP/HTTPS proxy).

### Reload config (hot reload)

`config.json` di-**hot-reload** — tanpa restart proxy. Addon cek mtime file di setiap response yang di-intercept dan reload otomatis saat berubah.

- Edit `config.json`, simpan → request berikutnya pakai rule baru. Log: `TBH Reward Proxy reloaded: ...`.
- Reload manual tanpa edit: `pkill -HUP -f mitmdump` (kirim SIGHUP).
- **Safety config corrupt**: bila `config.json` invalid (JSON rusak, tipe salah), addon tetap pakai **config terakhir yang valid** dan log `kept previous config (config.json invalid)`. Edit salah tidak pernah mematikan intercept aktif. Perbaiki file lalu simpan untuk reload.
- Bila `config.json` hilang/corrupt saat startup, proxy start dengan fallback config kosong (tanpa rule) dan log `using fallback empty config`.

Restart proxy hanya perlu untuk mengganti `listen_port` (mitmproxy bind port saat startup).

---

## Aplikasi Desktop

GUI PySide6 opsional yang membungkus `config.json` dan `run_proxy.py` yang sama dengan CLI. Memungkinkan mengedit rule secara visual, memilih reward ID dari wiki/loot table TBH, dan menjalankan proxy tanpa meninggalkan window.

GUI **tidak** menggantikan addon proxy — ia menjalankan `src/run_proxy.py` sebagai subprocess dan me-stream stdout-nya. Aturan hot-reload yang sama tetap berlaku.

### Instalasi <a id="desktop-install-id"></a>

Dependensi desktop sengaja dipisah dari `requirements.txt` (mitmproxy) agar install proxy tetap ringan. Arch Linux (PEP 668 memblokir pip):

```bash
sudo pacman -S python-pyside6 python-requests python-beautifulsoup4 python-pytest-qt
```

Atau via pip di venv:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-desktop.txt
```

Addon proxy (`requirements.txt`) sendiri tetap dibutuhkan agar Start/Stop berfungsi.

### Menjalankan <a id="desktop-launch-id"></a>

```bash
.venv/bin/python -m tbh_desktop.main
```

Main window punya toolbar (Start / Stop / Refresh gear / Save config / port / status dot) dan layout dua panel: editor di kiri, log live di kanan.

### Fitur <a id="desktop-features-id"></a>

- **Edit `src/config.json` secara visual**
  - Tabel `specific_queue_rules` — kolom enabled / name / item_id / replacement IDs. Tambah / Hapus baris.
  - `range_replacement` — enabled, min/max item_id, replacement IDs.
  - `listen_port` — field toolbar.
  - Field advanced (`only_post`, `require_boxes_marker`, `url_contains`) **tidak** diekspos di GUI tapi **dipertahankan** saat save: editor membaca file sebagai raw dict dan hanya menyentuh field yang ia miliki.
- **Save atomic** — memvalidasi dengan `ProxyConfig.load` sebelum dan sesudah tulis. Backup file sebelumnya sebagai `config.json.bak`, tulis via temp + rename, restore dari backup bila re-validasi gagal. Save yang gagal tidak pernah mematikan intercept aktif.
- **Pilih reward ID** — setiap cell `Replacement IDs` mendukung input manual, ditambah:
  - **Pick from box loot** — fetch loot table per-box dari `https://taskbarhero.org/en/items/chests/<id>-<slug>/`, parse, dan izinkan multi-select. Cache per-box di `tbh_desktop/box_loot_cache/<box_id>.json`.
  - **Pick gear** — fetch `https://taskbarhero.wiki/gear`, cache ke `tbh_desktop/gear_cache.json`. Multi-grade gear (rarity + type ditampilkan).
- **Refresh gear** — scrape ulang wiki, timpa cache. Bisa kapan saja, bahkan sebelum membuka picker.
- **Start / Stop proxy** — jalankan `src/run_proxy.py` sebagai subprocess (cwd = repo root). Status dot berubah hijau saat berjalan. Stdout ter-stream (stderr digabung) ke log panel via Qt signal — real-time, FIFO capped di 10k baris. Stop kirim SIGTERM, escalate ke SIGKILL setelah 3 detik.
- **Save config** — atomic, tervalidasi (lihat di atas). mtime-based hot-reload yang sama seperti edit manual.
- **Close confirm** — bila proxy berjalan, menutup window akan konfirmasi sebelum menghentikannya.
- **Menu** — File (Save config, Exit). Help (About).

### Interaksi Hot-Reload <a id="desktop-hot-reload-id"></a>

GUI mengedit **`config.json` yang sama** yang dibaca addon. Save dari GUI mengubah mtime file, sehingga cek mtime per-response addon langsung mengambil rule baru pada request berikutnya — tanpa restart proxy.

Pengecualian: `listen_port`. Field toolbar menulis ke `config.json`, tapi mitmproxy bind port saat startup, jadi menggantinya perlu restart proxy (Stop → Start).

### Keterbatasan <a id="desktop-limitations-id"></a>

- **Picker gear hanya menampilkan batch pertama.** Halaman wiki me-render ~60 kartu pada paint pertama (~21 obtainable setelah filter kartu `is-deleted`, total ~5760 item obtainable). Daftar lengkap butuh infinite-scroll / pagination yang **belum diimplementasikan** di sini — lihat docstring `parse_gear_page()` di `tbh_desktop/scraper.py`. Bila reward yang kamu mau tidak ada di cache, ketik ID-nya langsung di cell; akan diterima.
- **Box loot butuh `item_id` + `name` valid** di baris rule yang dipilih. Dialog memakai `name` rule untuk menurunkan URL slug (`"Normal Monster Box Lv80"` → `normal-monster-box-lv80`) — bila penamaan kamu berbeda dari konvensi wiki TBH, fetch loot akan 404 dan picker akan laporkan `No loot for box ...`.
- **Picker butuh network** untuk fetch data segar; fallback ke cache bila fetch gagal (silent — lihat log panel untuk warning-nya).
- GUI hanya-baca terhadap config di disk; edit bersamaan dari tool lain tidak terdeteksi. Bila kamu edit file di luar GUI saat ia terbuka, restart app untuk membaca ulang.

---

## Setup Klien Steam (TaskBarHero via Proton)

TaskBarHero adalah game Unity Windows (Steam AppId 3678970) yang berjalan via Proton + SteamLinuxRuntime_4 + pressure-vessel di Linux. Sandbox mengisolasi network namespace dan tidak meneruskan env proxy host secara default.

### Metode yang berhasil: Steam Launch Options (dites, konfirmasi jalan)

Steam → klik kanan **TaskbarHero** → Properties → **Launch Options**, isi:

```
HTTP_PROXY=http://127.0.0.1:8877 HTTPS_PROXY=http://127.0.0.1:8877 %command%
```

Proton meneruskan env var ini ke proses Wine, di mana `HttpClient` Unity membacanya.

### Trust CA di prefix Proton

Unity/Proton memakai **cert store Wine/Proton Windows**, bukan Linux system trust. Install CA mitmproxy ke prefix Proton (AppId 3678970):

```bash
WINEPREFIX=~/.local/share/Steam/steamapps/compatdata/3678970/pfx \
  wine certmgr -add -c -root ~/.mitmproxy/mitmproxy-ca-cert.cer
```

Bila `certmgr` tidak tersedia di prefix tersebut, salin cert ke direktori CA Wine:

```bash
PFX=~/.local/share/Steam/steamapps/compatdata/3678970/pfx
cp ~/.mitmproxy/mitmproxy-ca-cert.cer "$PFX/drive_c/windows/system32/cert/CA/"
```

### Catatan

- Native Unity socket (bukan HttpClient) bisa mengabaikan env proxy terlepas dari metode.
- AppId 3678970 adalah judul Steam komersial — intercept/modifikasi traffic-nya dapat melanggar ToS Steam dan/atau game. Hanya untuk akun sendiri di environment terkontrol.
- Bila env Launch Options diabaikan, alternatif: transparent iptables redirect (host layer, perlu bypass isolasi network pressure-vessel) atau Wine proxy registry (`HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings`).

---

## Sertifikat CA

mitmproxy intercept HTTPS dengan CA miliknya sendiri. Klien harus trust CA ini, jika tidak akan muncul error sertifikat. CA di-generate otomatis saat `mitmdump` pertama jalan, lokasi `~/.mitmproxy/`.

### Linux (system trust)

Install:

```bash
./scripts/install_cert.sh
```

Skrip auto-re-exec sudo, memakai `trust anchor --store` + `update-ca-trust extract`. Verifikasi:

```bash
trust list | grep -i mitmproxy
```

Hapus (bila tidak intercept lagi):

```bash
./scripts/remove_cert.sh
```

### Firefox

Firefox punya store sendiri, tidak baca system trust.

1. `about:preferences#privacy`
2. Certificates → View Certificates → tab **Authorities**
3. Import → `~/.mitmproxy/mitmproxy-ca-cert.pem`
4. Centang "Trust this CA to identify websites" → OK

### Chromium / Chrome

Membaca system trust (langkah Linux di atas cukup). Atau bypass via flag:

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

Tes rewrite offline tanpa proxy berjalan. Memvalidasi logika regex + rule terhadap `config.json`.

```bash
./scripts/self_test.sh          # Linux
windows\self_test.bat           # Windows
```

Output sukses:

```
[TBH] TBH Reward Proxy loaded: 2 queue rules, range mode=off.
Self-test OK.
```

Self-test membaca `config.json` dan membandingkan hasil rewrite dengan expected value. Bila mengubah rule di config, perbarui expected value di fungsi `run_self_test()` (`tbh_reward_hook.py`) agar test tetap relevan.

---

## Pemecahan Masalah

| Gejala | Penyebab | Solusi |
|---|---|---|
| `ModuleNotFoundError: mitmproxy` | mitmproxy belum terinstall | `sudo pacman -S mitmproxy` / `./scripts/install_requirements.sh` |
| Proxy jalan tapi response tidak berubah | URL/body tidak match filter | Cek `url_contains`, pastikan body mengandung `"boxes"`. Lihat log `[TBH] matched URL but found no replaceable` |
| Klien error sertifikat HTTPS | CA belum di-trust | Jalankan `./scripts/install_cert.sh` (lihat [Sertifikat CA](#sertifikat-ca)) |
| `AssertionError` di self-test | Expected value tidak match config | Sejajarkan expected di `run_self_test()` dengan `config.json` |
| Port 8877 dipakai | Konflik port | Ubah `listen_port` di `config.json` |
| Firefox tetap error | Store terpisah | Import manual via `about:preferences#privacy` |
| `sudo: a terminal is required` | sudo non-interaktif tanpa TTY | Jalankan via prefix `!` di prompt, atau `echo PASS \| sudo -S ...` |

Debug verbose (tanpa `-q`):

```bash
mitmdump -s src/tbh_reward_hook.py --listen-port 8877 --set block_global=false --flow-detail 2
```

---

## Peringatan Keamanan

**CA mitmproxy bisa menandatangani HTTPS apapun.** Bila mesin ini trust CA tersebut, siapa pun yang menjalankan proxy di mesin ini bisa intercept seluruh traffic terenkripsi.

- Hanya install CA pada environment yang kamu kontrol (dev/test).
- Hapus CA setelah tidak dipakai: `./scripts/remove_cert.sh`.
- Jangan commit file `~/.mitmproxy/mitmproxy-ca*.pem` ke repo apapun.
- Jangan bagikan CA private key (`mitmproxy-ca.pem`, `mitmproxy-ca.p12`).
- Penggunaan pada layanan/game pihak ketiga dapat melanggar ToS. Tanggung jawab pengguna.

---

## Struktur File

```
TBH/
├── src/                    # addon mitmproxy (tbh_reward_hook.py, run_proxy.py, config.json)
├── scripts/                # wrapper Linux
├── windows/                # wrapper Windows
├── tbh_desktop/            # GUI PySide6 desktop (opsional)
│   ├── main.py             # entry point
│   ├── config_io.py        # load/save config (atomic + validate)
│   ├── scraper.py          # gear wiki + box loot scrape, cache
│   ├── proxy_runner.py     # subprocess + stdout stream
│   ├── paths.py            # path resolution
│   └── ui/                 # main_window, config_editor, gear_picker, box_loot_picker, log_panel
├── tests/                  # pytest (config_io, scraper, proxy_runner)
├── docs/                   # specs + plans
├── requirements.txt            # mitmproxy
├── requirements-desktop.txt    # PySide6, requests, bs4, pytest-qt
├── README.md
└── README.id.md
```

Skrip memakai path absolut (`REPO_ROOT` di shell, `%~dp0..` di bat) sehingga jalan dari cwd mana pun. File source (`src/`) saling mereferensikan via `Path(__file__).resolve().parent`, jadi `tbh_reward_hook.py`, `run_proxy.py`, dan `config.json` harus tetap satu direktori.

Cache `tbh_desktop/gear_cache.json` dan `tbh_desktop/box_loot_cache/` pada aplikasi desktop bersifat generated dan masuk `.gitignore` — hapus untuk memaksa re-fetch dari wiki.

---

## Ucapan Terima Kasih

Proyek ini dibangun di atas teknik **Persistent Reward Item Generator** yang diteliti dan dibagikan oleh komunitas UnknownCheats. Thread asli: [TBH - Persistent Reward Item Generator](https://www.unknowncheats.me/forum/other-games/758547-tbh-persistent-reward-item-generator.html).

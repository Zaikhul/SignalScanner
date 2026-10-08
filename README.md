# Pemindai Area - Sistem Pengukuran Kekuatan Sinyal WiFi, Bluetooth, dan Radio

Sistem instrumen pengukuran kekuatan sinyal multi-mode real-time dengan antarmuka web modern (*dark-tech instrument-grade*), backend pengolahan sinyal berbasis Python FastAPI, dan daemon collector lokal lintas platform.

---

## 🚀 Fitur Utama

- **Multi-Mode Scanning**:
  - **WiFi (802.11)**: Pemindaian Access Point, RSSI (dBm), visualisasi kepadatan kanal (*channel occupancy*) 2.4 GHz & 5 GHz, band filtering, rekomendasi kesehatan kanal, dan deteksi SSID/BSSID.
  - **Bluetooth Low Energy (BLE)**: Pemantauan beacon pasif (`Bleak`), pelacakan pergerakan RSSI, filter manufacturer data, dan UUID service.
  - **Ghost Web Scanner & 3D Globe Topologi**:
    - Audit keamanan web terisolasi dengan 7 modul deteksi (recon, security headers, cookie audit, HTML forms/CSRF, parameter diagnostics, header injection probes, dan load resilience).
    - Stress resilience testing terikat (*bounded DDoS load testing*) dengan token-bucket rate limiting dan mitigasi SSRF berbasis DNS pinning terisolasi.
    - **Visualisasi 3D Globe Interaktif**: Visualisasi spasial node dan busur relasi host/IP berbasis Three.js dengan filter koneksi, inspektur detail relasi, dan integrasi geolokasi IP real-time.
    - Live event streaming via Server-Sent Events (SSE) dan ekspor hasil audit bertanda tangan SHA-256.
- **Channel Health & Recommendations**:
  - Deteksi interferensi co-channel dan adjacent-channel secara cerdas.
  - Perhitungan ketidakstabilan temporal multi-AP (*temporal instability score*).
  - Rekomendasi kanal terbaik 2.4 GHz dan 5 GHz untuk meminimalkan tabrakan sinyal.
- **Instrument Visuals**:
  - **ScanField Polar**: Visual koordinat polar radar presisi dengan sudut beacon deterministik stabil (bukan kompas/arah fisik semu) dan *Sweep Arm* animasi halus.
  - **Dukungan Aksesibilitas Penuh**: Kepatuhan `prefers-reduced-motion` dan WCAG 2.2 AA.
- **Privacy & Security First**:
  - Pseudonimisasi BSSID & alamat MAC menggunakan HMAC tenant-scoped sebelum persistensi/transmisi.
  - Tidak menyimpan isi paket komunikasi (*receive-only*).
  - Redaksi query sensitif pada rekaman temuan dan live event stream.
- **Resilient Streaming & Concurrency**:
  - Komunikasi data real-time berbasis WebSocket dengan sequence tracking, gap recovery, dan buffer offline SQLite (`aiosqlite`) dengan antrean *dead-letter* pada collector saat jaringan terputus.
  - Mode **SQLite WAL (Write-Ahead Logging)** aktif otomatis pada backend untuk mengeliminasi *lock contention* dan penundaan saat pembuatan sesi baru secara bersamaan dengan operasi polling.
  - Mekanisme **Startup Auto-Retry (15x)** pada daemon collector untuk menjamin sinkronisasi otomatis yang tangguh saat seluruh subsistem dihidupkan bersamaan.
- **Riwayat & Ekspor Data**:
  - Manajemen sesi (Mulai, Jeda, Lanjut, Selesai, Tambah Marker Kejadian).
  - Ekspor dataset ke format **JSON** dan **RFC-4180 CSV** berstandar schema v1.0 dengan checksum SHA-256 dan verifikasi otentikasi unduhan.
- **Zero-Dependency Quickstart**:
  - Dilengkapi generator simulasi virtual (*Fidelity Mock Adapter*) sehingga pengembang dapat langsung menjalankan dan menguji aplikasi secara penuh tanpa memerlukan dongle SDR atau adapter Bluetooth khusus.

---

## 📁 Struktur Monorepo

```text
signal-scanner/
├── docker-compose.yml                          # Deployment TimescaleDB, Redis, API, Collector & Web
├── .env.example                                # Template konfigurasi environment terpadu
├── backend/                                   # Backend FastAPI & Signal Processor
│   ├── app/
│   │   ├── api/v1/                            # REST Endpoints (collectors, sessions, channel-health, web-scans, exports, ingest)
│   │   ├── api/ws/                            # WebSocket /ws/v1/sessions stream hub
│   │   ├── core/                              # Signal math (EMA, FFT peaks), Channel Health & Web Scan Engine (hardening, geolocation)
│   │   ├── db/                                # SQLAlchemy 2 async models & session factory
│   │   ├── schemas/                           # Pydantic v2 data contracts (signals, web scan, geography)
│   │   └── services/                          # Session state machine, web scan scheduler, geography & export services
│   ├── migrations/                            # Alembic database migration scripts (0001 - 0005)
│   ├── scripts/                               # Utilitas koneksi database & preflight_deploy_check.py
│   └── tests/                                 # Pytest unit & integration tests
├── collector/                                 # Daemon Collector & Hardware Adapters
│   ├── app/
│   │   ├── adapters/                          # Windows WiFi, Bleak BLE, SoapySDR & Mock Simulators
│   │   ├── core/                              # SignalAdapter protocol, aiosqlite buffer queue, dead-letter uploader
│   │   └── main.py                            # Collector CLI runner & local healthz agent
│   └── tests/                                 # Unit tests for buffer queue & mock adapters
└── frontend/                                  # Next.js 15 Standalone + Tailwind CSS Web UI
    ├── app/                                   # App Router (Live Scan, Sessions History, Collectors, Web Scanner)
    ├── components/
    │   ├── controls/                          # ModeRail, CollectorPicker, SessionControls, MarkerModal
    │   ├── visualizers/                       # ScanField, SweepArm, ChannelOccupancy, SpectrumWaterfall, MetricStrip
    │   ├── web-scanner/                       # WebScanControls, WebScanSummary, StatusBadge, FindingCard, WebScanGlobe, WebScanGeographyPanel
    │   ├── inspector/                         # TargetInspector, TargetTable
    │   └── layout/                            # AppShell, Header, ConnectionBanner
    ├── hooks/                                 # useSessionStream WebSocket hook
    ├── lib/                                   # Zustand store, REST apiClient, TypeScript types
    └── tests/                                 # Vitest frontend tests
```

---

## ⚡ Panduan Menjalankan Aplikasi

### 🚀 Cara Menjalankan Dalam "Satu Pintu" (Rekomendasi Lokal)

Anda dapat menjalankan seluruh subsistem (**Backend**, **Frontend**, dan **Collector**) sekaligus hanya dengan **satu perintah**:

#### Opsi A: Runner Lokal Windows (Paling Direkomendasikan untuk Hardware Scan)
Mendukung akses penuh ke adapter WiFi native Windows, Bluetooth LE (`Bleak`), dan USB SDR dongle:

```pwsh
# Cara 1 (Python)
python run.py

# Atau Cara 2 (PowerShell Script)
.\run.ps1

# Atau Cara 3 (One-Click Windows Batch / Double-click di File Explorer)
run.bat

# Atau Cara 4 (via pnpm/npm dari root)
pnpm dev
```

> **Catatan Fitur Runner**:
> - **Dependency-Aware**: Menunggu database & backend sehat (`/healthz`) sebelum mengaktifkan collector dan frontend.
> - **Auto Browser**: Otomatis membuka `http://localhost:3000` ketika frontend telah siap.
> - **Unified Clean Teardown**: Menekan `Ctrl+C` akan mematikan seluruh proses anak (*process tree*) di Windows tanpa meninggalkan proses zombie yang mengunci port `8000` atau `3000`.

**Opsi Argumen Tambahan:**
```pwsh
# Mode Simulasi Virtual (tanpa adapter hardware fisik)
python run.py --mock

# Mode Bluetooth LE
python run.py --mode bluetooth

# Mode Radio Spektrum (SDR)
python run.py --mode radio --mock

# Mode Backend + Frontend saja (tanpa collector)
python run.py --no-collector

# Membuka terminal terpisah (3 split-panes di Windows Terminal wt.exe)
.\launch-split.ps1
```

---

## 🚢 Panduan Deployment Produksi (Docker Compose & Enterprise Stack)

Sistem Signal Scanner telah dioptimalkan untuk orkestrasi container production menggunakan **Docker Compose**, **TimescaleDB** (PostgreSQL 16), **Redis 7**, **FastAPI Backend**, **Collector Daemon**, dan **Next.js 15 Standalone**.

### 1. Arsitektur Komponen Deployment

| Service | Port Default | Host Binding Rekomendasi | Keterangan |
| :--- | :--- | :--- | :--- |
| `timescaledb` | `5432` | `127.0.0.1:5432` | TimescaleDB (PostgreSQL 16) untuk data time-series sinyal |
| `redis` | `6379` | `127.0.0.1:6379` | Event stream broker & pub/sub |
| `backend` | `8000` | `127.0.0.1:8000` | REST API FastAPI & WebSocket server |
| `collector` | `8001` | `127.0.0.1:8001` | Daemon penangkap sinyal WiFi/SDR |
| `frontend` | `3000` | `0.0.0.0:3000` | Next.js 15 Standalone UI (image ~150MB) |

### 2. Konfigurasi Environment & Rahasia Kriptografis

1. **Salin Template Environment**:
   ```bash
   cp .env.example .env
   ```

2. **Generate Token & Rahasia Kriptografis**:
   ```bash
   python -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32)); print('API_AUTH_TOKEN=' + secrets.token_urlsafe(32)); print('COLLECTOR_API_KEY=' + secrets.token_urlsafe(32)); print('NEXT_PUBLIC_LOCAL_COLLECTOR_TOKEN=' + secrets.token_urlsafe(32))"
   ```

3. **Perbarui Nilai `.env`**:
   Atur `ENVIRONMENT=production`, masukkan password database yang kuat pada `POSTGRES_PASSWORD`, dan tempelkan token rahasia yang telah di-generate.

> [!CAUTION]
> Jangan pernah menggunakan token default dev (`signal-scanner-dev-token-2026`) atau password default di lingkungan production.

### 3. Menjalankan Container Production
```bash
# Build dan jalankan seluruh container secara otomatis
docker compose up -d --build

# Periksa status container & healthcheck
docker compose ps
```

### 4. Manajemen Migrasi Database (Alembic)
```bash
# Terapkan migrasi terbaru ke database TimescaleDB
docker compose exec backend alembic upgrade head

# Periksa status migrasi aktif
docker compose exec backend alembic current

# Rollback satu revisi jika diperlukan
docker compose exec backend alembic downgrade -1
```

### 5. Verifikasi Kesiapan Otomatis (Preflight Check)
Jalankan skrip preflight readiness untuk memvalidasi keamanan kredensial, konektivitas database async, sinkronisasi migrasi Alembic, dan konektivitas Redis:
```bash
docker compose exec backend python scripts/preflight_deploy_check.py --strict
```

### 6. Endpoint Healthcheck
- Backend: `GET http://127.0.0.1:8000/healthz`
- Collector: `GET http://127.0.0.1:8001/healthz`
- Frontend: `GET http://localhost:3000`

---

## 🛠️ Cara Menjalankan Manual (Per Modul Tanpa Docker)

Jika ingin menjalankan atau men-debug modul tertentu secara terpisah di terminal:

#### 1. Menjalankan Backend (FastAPI)
```pwsh
uvicorn app.main:app --app-dir backend --reload --port 8000
```

#### 2. Menjalankan Frontend (Next.js 15)
```pwsh
cd frontend
pnpm dev
```

#### 3. Menjalankan Collector Daemon
```pwsh
# Mode WiFi (Adapter Windows / Mock)
python -m collector.app.main --mode wifi

# Mode Bluetooth LE (Bleak)
python -m collector.app.main --mode bluetooth

# Mode Radio SDR (SoapySDR / Virtual RF)
python -m collector.app.main --mode radio --mock
```

---

## 🧪 Menjalankan Pengujian Otomatis (Tests)

### Backend Tests (Pytest)
```pwsh
pytest -q backend/tests
```

### Collector Tests (Pytest)
```pwsh
pytest -q collector/tests
```

### Frontend Tests (Vitest)
```pwsh
cd frontend
pnpm test -- --run
```

### Frontend Lint & Typecheck
```pwsh
cd frontend
pnpm lint
```

---

## 📊 API & WebSocket Contracts

| Method | Path | Keterangan |
| --- | --- | --- |
| `GET` | `/healthz` | Health check endpoint publik backend |
| `GET` | `http://127.0.0.1:8001/healthz` | Health check endpoint publik collector |
| `GET` | `/api/v1/collectors` | Daftar collector terdaftar & kapabilitas |
| `POST` | `/api/v1/collectors/{id}/commands/diagnose` | Menjalankan uji diagnostik adapter |
| `POST` | `/api/v1/sessions` | Membuat sesi pemindaian baru |
| `POST` | `/api/v1/sessions/{id}/start` | Memulai live scanning |
| `POST` | `/api/v1/sessions/{id}/pause` | Menjeda live scanning (sequence dipertahankan) |
| `POST` | `/api/v1/sessions/{id}/resume` | Melanjutkan live scanning |
| `POST` | `/api/v1/sessions/{id}/stop` | Menghentikan & finalisasi summary sesi |
| `POST` | `/api/v1/sessions/{id}/markers` | Menambahkan marker kejadian bertimestamp |
| `GET` | `/api/v1/sessions/{id}/targets` | Daftar target terdeteksi & statistik |
| `GET` | `/api/v1/channel-health/recommendations` | Analisis interferensi & rekomendasi kanal WiFi optimal |
| `POST` | `/api/v1/sessions/exports` | Membuat job ekspor dataset (JSON/CSV) |
| `GET` | `/api/v1/exports/{id}/download` | Mengunduh file ekspor (authenticated) |
| `WS` | `/ws/v1/sessions/{session_id}` | WebSocket stream real-time batch & sequence replay |
| `POST` | `/api/v1/web-scans` | Membuat job pemindaian web baru (URL, fuzzer, stress limit) |
| `GET` | `/api/v1/web-scans` | Daftar riwayat job pemindaian web |
| `GET` | `/api/v1/web-scans/{id}` | Detail status, temuan kerentanan, dan metrik scan |
| `GET` | `/api/v1/web-scans/{id}/stream` | Server-Sent Events (SSE) live streaming progres scan |
| `POST` | `/api/v1/web-scans/{id}/cancel` | Membatalkan pemindaian web yang sedang aktif |
| `GET` | `/api/v1/web-scans/{id}/export` | Ekspor hasil temuan dan metrik web scan (JSON/CSV) |
| `GET` | `/api/v1/web-scans/{id}/geography` | Topologi geolokasi IP, node target, busur koneksi, dan relasi endpoint scan |

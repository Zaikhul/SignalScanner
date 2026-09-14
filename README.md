# Pemindai Area - Sistem Pengukuran Kekuatan Sinyal WiFi, Bluetooth, dan Radio

Sistem instrumen pengukuran kekuatan sinyal multi-mode real-time dengan antarmuka web modern (*dark-tech instrument-grade*), backend pengolahan sinyal berbasis Python FastAPI, dan daemon collector lokal lintas platform.

---

## 🚀 Fitur Utama

- **Multi-Mode Scanning**:
  - **WiFi (802.11)**: Pemindaian Access Point, RSSI (dBm), visualisasi kepadatan kanal (*channel occupancy*) 2.4 GHz & 5 GHz, band filtering, dan deteksi SSID/BSSID.
  - **Bluetooth Low Energy (BLE)**: Pemantauan beacon pasif (`Bleak`), pelacakan pergerakan RSSI, filter manufacturer data, dan UUID service.
  - **Radio (SDR)**: Penerima spektrum RF (`SoapySDR`) dengan tampilan garis FFT (*dBFS power*) dan **Spectrum Waterfall 2D** real-time.
- **Instrument Visuals**:
  - **ScanField Polar**: Visual koordinat polar radar presisi dengan sudut beacon deterministik stabil (bukan kompas/arah fisik semu) dan *Sweep Arm* animasi halus.
  - **Dukungan Aksesibilitas Penuh**: Kepatuhan `prefers-reduced-motion` dan WCAG 2.2 AA.
- **Privacy & Security First**:
  - Pseudonimisasi BSSID & alamat MAC menggunakan HMAC tenant-scoped sebelum persistensi/transmisi.
  - Tidak menyimpan isi paket komunikasi (*receive-only*).
- **Resilient Streaming**:
  - Komunikasi data real-time berbasis WebSocket dengan sequence tracking, gap recovery, dan buffer offline SQLite (`aiosqlite`) pada collector saat jaringan terputus.
- **Riwayat & Ekspor Data**:
  - Manajemen sesi (Mulai, Jeda, Lanjut, Selesai, Tambah Marker Kejadian).
  - Ekspor dataset ke format **JSON** dan **RFC-4180 CSV** berstandar schema v1.0 dengan checksum SHA-256.
- **Zero-Dependency Quickstart**:
  - Dilengkapi generator simulasi virtual (*Fidelity Mock Adapter*) sehingga pengembang dapat langsung menjalankan dan menguji aplikasi secara penuh tanpa memerlukan dongle SDR atau adapter Bluetooth khusus.

---

## 📁 Struktur Monorepo

```text
signal-scanner/
├── PRD_Sistem_Pengukuran_Kekuatan_Sinyal.md   # Dokumen PRD acuan
├── docker-compose.yml                          # Deployment TimescaleDB, Redis, API & Web
├── backend/                                   # Backend FastAPI & Signal Processor
│   ├── app/
│   │   ├── api/v1/                            # REST Endpoints (collectors, sessions, targets, exports, ingest)
│   │   ├── api/ws/                            # WebSocket /ws/v1/sessions stream hub
│   │   ├── core/                              # Signal math (EMA, FFT peaks, SNR) & Security HMAC
│   │   ├── db/                                # SQLAlchemy 2 async models & session factory
│   │   ├── schemas/                           # Pydantic v2 data contracts
│   │   └── services/                          # Session state machine, collector & export services
│   └── tests/                                 # Pytest unit & integration tests
├── collector/                                 # Daemon Collector & Hardware Adapters
│   ├── app/
│   │   ├── adapters/                          # Windows WiFi, Bleak BLE, SoapySDR & Mock Simulators
│   │   ├── core/                              # SignalAdapter protocol, aiosqlite buffer queue, uploader
│   │   └── main.py                            # Collector CLI runner
│   └── tests/                                 # Unit tests for buffer queue & mock adapters
└── frontend/                                  # Next.js 15 + Tailwind CSS v4 Web UI
    ├── app/                                   # App Router (Live Scan, Sessions History, Collectors)
    ├── components/
    │   ├── controls/                          # ModeRail, CollectorPicker, SessionControls, MarkerModal
    │   ├── visualizers/                       # ScanField, SweepArm, ChannelOccupancy, SpectrumWaterfall, MetricStrip
    │   ├── inspector/                         # TargetInspector, TargetTable
    │   └── layout/                            # AppShell, Header, ConnectionBanner
    ├── hooks/                                 # useSessionStream WebSocket hook
    ├── lib/                                   # Zustand store, REST apiClient, TypeScript types
    └── tests/                                 # Vitest frontend tests
```

---

## ⚡ Panduan Menjalankan Aplikasi

### 1. Menjalankan Backend (FastAPI)

```pwsh
# 1. Masuk ke direktori root / backend
cd backend

# 2. Jalankan server FastAPI (port 8000)
uvicorn app.main:app --reload --port 8000
```
Backend akan otomatis menginisialisasi database lokal SQLite (`signal_scanner.db`) dan siap menerima koneksi REST serta WebSocket.

### 2. Menjalankan Frontend (Next.js 15)

```pwsh
# 1. Masuk ke direktori frontend
cd frontend

# 2. Jalankan development server (port 3000)
pnpm dev
```
Buka browser pada `http://localhost:3000`.

### 3. Menjalankan Collector Daemon (Opsional / Hardware Scan)

Collector dapat dijalankan secara terpisah untuk memindai adapter lokal pada host:

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

### Backend & Collector Tests (Python)
```pwsh
pytest backend/tests collector/tests -v
```

### Frontend Tests (Vitest)
```pwsh
cd frontend
pnpm test
```

---

## 📊 API & WebSocket Contracts

| Method | Path | Keterangan |
| --- | --- | --- |
| `GET` | `/healthz` | Health check endpoint |
| `GET` | `/api/v1/collectors` | Daftar collector terdaftar & kapabilitas |
| `POST` | `/api/v1/collectors/{id}/commands/diagnose` | Menjalankan uji diagnostik adapter |
| `POST` | `/api/v1/sessions` | Membuat sesi pemindaian baru |
| `POST` | `/api/v1/sessions/{id}/start` | Memulai live scanning |
| `POST` | `/api/v1/sessions/{id}/pause` | Menjeda live scanning |
| `POST` | `/api/v1/sessions/{id}/resume` | Melanjutkan scanning |
| `POST` | `/api/v1/sessions/{id}/stop` | Menghentikan & finalisasi summary sesi |
| `POST` | `/api/v1/sessions/{id}/markers` | Menambahkan marker kejadian bertimestamp |
| `GET` | `/api/v1/sessions/{id}/targets` | Daftar target terdeteksi & statistik |
| `POST` | `/api/v1/sessions/{id}/exports` | Membuat job ekspor dataset (JSON/CSV) |
| `GET` | `/api/v1/exports/{id}/download` | Mengunduh file ekspor |
| `WS` | `/ws/v1/sessions/{session_id}` | WebSocket stream real-time batch & sequence replay |

# Update PRD — ScanField sebagai Instrumen Pemindaian Responsif

**Produk:** Pemindai Area / SignalScanner  
**Versi usulan:** v1.2.1 — Pembaruan visual ScanField  
**Tanggal:** 2026-09-14  
**Status:** Spesifikasi usulan untuk implementasi; belum merupakan hasil pengujian atau rilis.  
**Pemilik:** Product, UI/UX, Frontend, QA; Backend/Collector untuk validasi kontrak aktivitas dan usia data.  
**Dokumen induk:** `PRD_Sistem_Pengukuran_Kekuatan_Sinyal.md`, Unified PRD v1.0 + v1.1A + v1.2.

Pembaruan ini membuat ScanField terasa hidup melalui perubahan data yang terbaca, respons seleksi yang jelas, dan sweep yang mengikuti keadaan pemindaian. Seluruh gerak mempunyai pemicu dan arti yang dapat dijelaskan.

## Dasar peninjauan dan cara integrasi

PRD lampiran dan screenshot pengguna menjadi acuan produk dan visual. Kode ditinjau pada commit [`79c1b409bfc11017b9dc02edc40d1058ef5ac90d`](https://github.com/Zaikhul/SignalScanner/tree/79c1b409bfc11017b9dc02edc40d1058ef5ac90d), yaitu HEAD `main` yang diambil saat peninjauan. Penilaian implementasi berasal dari pembacaan kode, bukan pengujian aplikasi berjalan.

| Temuan pada baseline | Implikasi pembaruan |
| :--- | :--- |
| ScanField telah memakai hash `target_id`, skala −100 sampai −30 dBm, radius terbalik, dan seleksi melalui klik. | Pertahankan determinisme dan orientasi skala; perjelas kontrak numerik serta akses interaksi. |
| Ukuran beacon ikut berubah menurut kekuatan; target terpilih memakai shadow/glow. | Gunakan ukuran inti tetap dan outline seleksi agar pembacaan radial menjadi fokus. |
| Sweep berputar 4 detik dan hanya memeriksa status sesi `active`; cakupan overlay mengikuti kontainer. | Ikat aktivitas pada kondisi collector/stream/adapter dan samakan geometri sweep dengan plot. |
| Filter, pengelompokan, dan usia target dihitung di TargetTable; ScanField memetakan seluruh `targets`. | Gunakan satu hasil seleksi data untuk plot, daftar, dan hitungan target. |
| Tooltip/badge serta overlay masih memuat blur, glow, dan gradient. | Terapkan permukaan solid dan satu aksen signal-lime. |
| PRD menyebut canvas; konfigurasi ECharts saat ini memakai `renderer: "svg"`. | Spesifikasi perilaku berlaku untuk ECharts polar pada kedua renderer. Pilihan renderer dibuktikan melalui uji kinerja, tanpa menganggap migrasi canvas telah terjadi. |

Sumber kode: [ScanField.tsx](https://github.com/Zaikhul/SignalScanner/blob/79c1b409bfc11017b9dc02edc40d1058ef5ac90d/frontend/components/visualizers/ScanField.tsx), [SweepArmOverlay.tsx](https://github.com/Zaikhul/SignalScanner/blob/79c1b409bfc11017b9dc02edc40d1058ef5ac90d/frontend/components/visualizers/SweepArmOverlay.tsx), [TargetTable.tsx](https://github.com/Zaikhul/SignalScanner/blob/79c1b409bfc11017b9dc02edc40d1058ef5ac90d/frontend/components/inspector/TargetTable.tsx), dan [globals.css](https://github.com/Zaikhul/SignalScanner/blob/79c1b409bfc11017b9dc02edc40d1058ef5ac90d/frontend/app/globals.css).

| Bagian PRD induk | Tindakan integrasi |
| :--- | :--- |
| 1. Ringkasan Eksekutif | Ganti dengan teks Bagian 1 di bawah. |
| 2. Riwayat Versi & Changelog | Tambahkan baris v1.2.1 setelah v1.2. |
| 11. Functional Requirements | Tambahkan 11.8; requirement 11.1–11.7 tetap menjadi dependensi. |
| 13. Component Inventory & UI Standards | Ganti 13.1–13.3 dan tambahkan 13.4–13.9. |
| 19. Testing Strategy & DoD | Tambahkan 19.3 sebagai gate pembaruan ScanField. |

`Must` adalah syarat rilis pembaruan ini. Seluruh angka durasi, toleransi, dan beban uji baru di bawah adalah target requirement yang diusulkan. Cakupan utamanya Discover WiFi/BLE; batas untuk SDR dan Associated dijelaskan dalam 11.8 dan 13.5.

---

## 1. Ringkasan Eksekutif — pengganti

**Pemindai Area** adalah sistem pengukuran kekuatan sinyal multi-mode untuk WiFi, Bluetooth Low Energy (BLE), dan radio berbasis Software Defined Radio (SDR). Sistem menampilkan pengukuran langsung, menyimpan sesi, membandingkan perubahan sinyal, mengekspor hasil, menilai kesehatan kanal WiFi, serta menghubungkan collector ke jaringan WiFi lokal dan menginventarisasi host LAN yang terjangkau.

Aplikasi web Next.js terhubung ke backend Python dan collector lokal. Operasi pengukuran hardware dan asosiasi jaringan tetap dilakukan melalui collector.

Visual utama Discover menggunakan **ScanField berupa instrumen polar yang responsif terhadap data**. Cincin berskala, penanda radial, sweep tipis, beacon, dan pembacaan numerik membantu pengguna memahami kekuatan relatif, perubahan sampel, usia data, serta status pemindaian. Beacon berpindah secara halus sepanjang radius ketika nilai tampilan berubah; pemilihan target menghubungkan beacon, daftar, Inspector, dan grafik waktu.

**Kejujuran semantik merupakan aturan produk:** radius mewakili nilai kekuatan/kualitas relatif dengan metrik dan unit yang disebutkan; sudut adalah tata letak hash deterministik. Untuk Discover WiFi/BLE, metrik radial default adalah RSSI dalam dBm, dengan sinyal lebih kuat berada lebih dekat pusat. Sudut, pusat, sweep, serta pergerakan beacon tidak menyatakan lokasi, arah datang sinyal, jarak meter, atau perpindahan fisik perangkat. RSSI juga tidak diperlakukan sebagai skor kesehatan kanal.

Karakter visual tetap graphite/zinc dengan satu aksen dekoratif signal-lime. Rasa hidup berasal dari feedback perubahan data dan interaksi, serta sweep aktivitas yang terkendali. Data terukur, pemrosesan sinyal, kesegaran data, dan simulasi harus dapat dibedakan secara eksplisit.

## 2. Riwayat Versi & Changelog — baris tambahan

| Versi | Tanggal | Perubahan Utama |
| :--- | :--- | :--- |
| **v1.2.1 — usulan** | 2026-09-14 | Pembaruan ScanField: pemetaan polar deterministik, beacon responsif terhadap sampel, seleksi terhubung, sweep berbasis status aktivitas, freshness bersama, akses keyboard, reduced motion, dan pengetatan standar anti-slop. |

## 11.8 Visualisasi ScanField dan Interaksi Pengukuran — tambahan

| ID | Requirement | Prioritas | Acceptance Criteria |
| :--- | :--- | :--- | :--- |
| **FR-SCN-01** | Menjaga pemetaan radial dan sudut yang jujur. | Must | Nilai, unit, dan sudut mengikuti 13.5; perubahan urutan, filter, ukuran panel, atau seleksi tidak mengubah sudut target yang sama. Penjelasan semantik selalu terlihat. |
| **FR-SCN-02** | Menampilkan skala tetap, batas nilai, dan nilai unavailable secara eksplisit. | Must | Skala tidak berubah otomatis mengikuti target terkuat/terlemah. Nilai di luar rentang diberi penanda batas; nilai kosong/nonfinite tidak diplot sebagai 0 atau sebagai sinyal lemah. |
| **FR-SCN-03** | Memberikan feedback pada observasi baru yang valid. | Must | Perubahan nilai menggerakkan beacon hanya sepanjang radius selama maksimal 220 ms. Data identik yang dikirim ulang tidak memicu feedback observasi baru. Sampel tidak menunggu dilintasi sweep untuk muncul. |
| **FR-SCN-04** | Mengendalikan sweep berdasarkan keadaan pemindaian aktual. | Must | Sweep hanya bergerak pada state Memindai, termasuk hasil scan kosong terkonfirmasi, atau Simulasi aktif sesuai 13.6. Jeda, gangguan stream/collector, konflik adapter, dan sesi selesai menghentikannya. Putaran tidak ditampilkan sebagai persentase penyelesaian. |
| **FR-SCN-05** | Menyamakan freshness dan keberadaan target di seluruh tampilan. | Must | Plot, TargetTable, Inspector, dan hitungan memakai kebijakan usia yang sama. Usia bertambah ketika data berhenti; event lama tidak mereset usia menjadi fresh. |
| **FR-SCN-06** | Menghubungkan seleksi beacon, daftar, Inspector, dan timeline. | Must | Klik/tap atau pemilihan keyboard menetapkan `selectedTargetId` yang sama dan memperbarui penekanan visual dalam ≤100 ms p95. Target tetap terpilih ketika urutan RSSI berubah. |
| **FR-SCN-07** | Menyinkronkan filter dan pengelompokan tanpa mengubah arti beacon. | Must | Pencarian/filter berlaku pada plot dan daftar. Satu beacon WiFi tetap mewakili satu BSSID terpseudonimisasi; mode Per SSID hanya mengelompokkan daftar, dengan jumlah BSSID disebutkan. |
| **FR-SCN-08** | Menangani beacon bertumpuk tanpa memalsukan koordinat. | Must | Semua anggota dapat dipilih lewat daftar kandidat; tidak ada jitter acak, orbit, atau penggeseran titik untuk memisahkan target. |
| **FR-SCN-09** | Menyediakan pembacaan numerik dan provenance yang dapat diaudit. | Must | Inspector menyebut nilai tampilan, nilai sumber bila tersedia, unit, waktu observasi, usia, metode pemrosesan, dan quality flags. Nilai nol seperti SNR 0 dB tetap ditampilkan. |
| **FR-SCN-10** | Mendukung keyboard, sentuhan, pembaca layar, dan reduced motion. | Must | Seluruh aksi pemilihan memiliki padanan HTML yang dapat difokuskan. Mode reduced motion menghapus sweep berputar, tween posisi, serta feedback sementara; data dan seleksi tetap lengkap. |
| **FR-SCN-11** | Menampilkan mode dan kondisi kosong secara benar. | Must | Menunggu data, hasil scan kosong, hasil filter kosong, data unavailable, dan gangguan collector mempunyai pesan berbeda. Simulasi ditandai terus-menerus. |
| **FR-SCN-12** | Mempertahankan batas semantik antar-mode dan fase. | Must | Associated menghentikan ScanField AP pada adapter yang sama dan memakai NetworkField. SDR tidak mewarisi sumbu dBm WiFi tanpa kontrak unit/kalibrasi yang sesuai. |
| **FR-SCN-13** | Menjaga sinkronisasi render dan respons saat streaming. | Must | Ring, beacon, sweep, dan hit area berbagi geometri. Lulus gate beban, latensi, resize, dan sesi 30 menit pada 19.3. |

## 13. Component Inventory & UI Standards — revisi

### 13.1 Komponen Frontend Utama — pengganti

| Komponen | Tanggung jawab |
| :--- | :--- |
| **AppShell / ModeRail** | Layout, navigasi, tema, dan pemilihan WiFi/BLE/SDR. |
| **ScanField** | Koordinator plot polar ECharts, skala, seleksi, data terlihat, state tampilan, dan alternatif aksesibel. |
| **ScanGrid** | Cincin dan tick skala statis, pusat matematis, serta penanda tata letak sudut. |
| **SweepArmOverlay** | Satu lengan sweep dan sektor pendek; mengikuti state aktivitas serta geometri ScanField. |
| **SignalBeaconLayer** | Beacon dengan identitas stabil, transisi radial, status freshness, dan penanda nilai di batas skala. |
| **TargetFocusOverlay** | Outline target terpilih, satu cincin pandu pada radius pilihannya, dan label terhubung. |
| **ScanStatusStrip / MeasurementQualityStrip** | Status operasi, usia data, interval aktual, sumber, dan pemrosesan sinyal; berbagi sumber state. |
| **ScanLegend** | Penjelasan radius, hash sudut, arti sweep, dan simbol status; selalu terlihat. |
| **TargetTable / TargetInspector / SignalTimeline** | Pemilihan HTML/keyboard, detail sumber pengukuran, pin target, dan riwayat nilai. |
| **TargetOverlapList** | Daftar kandidat ketika hit area beacon beririsan; mengembalikan seleksi ke identitas aslinya. |
| **ConnectAction / AuthorizedUseGate / WifiCredentialModal** | Aksi koneksi, gerbang wewenang, dan input kredensial sesuai requirement koneksi yang berlaku. |
| **AdapterConflictBanner / InterfaceSummary** | Penjelasan jeda adapter dan informasi interface associated. |
| **NetworkField / HostInventory** | Representasi inventaris LAN dan tabel host ter-virtualisasi. |
| **ChannelRecommendationCard / ChannelEvidenceDrawer** | Rekomendasi read-only beserta confidence, provenance, dan missing evidence. |

Nama komponen baru menyatakan pemisahan tanggung jawab, bukan kewajiban membuat satu file untuk setiap nama. State data terlihat, freshness, dan seleksi harus bersumber dari model tampilan bersama.

### 13.2 Tailwind CSS v4 Theme Tokens — pengganti

```css
@import "tailwindcss";

@theme {
  --color-canvas: #090b0c;
  --color-surface: #111416;
  --color-surface-raised: #171b1d;
  --color-line: #2a3033;
  --color-instrument-mark: #78837f;
  --color-signal-lime: #a8d94f;
  --color-signal: var(--color-signal-lime); /* Alias kompatibilitas */
  --color-ink: #f2f4ef;
  --color-muted: #9aa3a0;
  --color-status-warning: #e7ad52;
  --color-status-error: #ed7c8d;
  --font-sans: "Geist", ui-sans-serif, system-ui, sans-serif;
  --font-mono: "Geist Mono", ui-monospace, monospace;
  --radius-panel: 1rem;
  --radius-control: 0.625rem;
}

:root {
  --scan-motion-feedback: 140ms;
  --scan-motion-position: 220ms;
  --scan-sweep-period: 4s;
  --scan-sweep-opacity: 0.06;
  --scan-easing-feedback: cubic-bezier(0.2, 0, 0, 1);
}
```

`signal` dan `signal-lime` adalah warna yang sama. `line` digunakan untuk struktur dekoratif; tick, outline, dan teks yang diperlukan untuk membaca data memakai token dengan kontras memadai. Amber/Rose khusus peringatan/error dengan ikon dan teks. Driver, metadata, dan tautan biasa menggunakan warna netral atau signal-lime, tanpa menambah aksen cyan/ungu/emerald.

### 13.3 Anti-AI Slop Standards — pengganti dan pengetatan

- **Warna:** graphite/zinc neutral dan satu aksen dekoratif signal-lime. Tidak ada AI-purple, pelangi kategori target, atau gradient text.
- **Permukaan:** panel, tooltip, badge, dan Inspector memakai latar solid. Glassmorphism, `backdrop-filter`, blur, bloom, serta glow dekoratif dilarang pada ScanField dan elemen pendampingnya.
- **Struktur instrumen:** hierarki berasal dari skala, ketebalan garis, kontras, jarak, dan angka. Hindari ornamen HUD, reticle tambahan, teks acak, maupun cincin tanpa fungsi pengukuran/status.
- **Tipografi:** Geist Sans untuk UI; Geist Mono dengan `tabular-nums` untuk pengukuran, waktu, dan identifier. Heading tidak oversized. Label penting minimal 12 px pada zoom 100% dan tetap terbaca saat diperbesar.
- **Motion:** hanya feedback perubahan state data/interaksi dan sweep saat pemindaian aktif. Dilarang idle breathing, twinkling, partikel, orbit, parallax, gelombang ekspansi berulang, serta animasi entrance bertingkat yang dekoratif.
- **Sweep:** satu garis tegas dan satu sektor pendek berwarna datar. Tanpa gradient/conic glow, jejak panjang, atau cahaya yang menyelimuti plot.
- **Informasi:** gerak dan warna bukan satu-satunya pembeda. Setiap state penting mempunyai teks, bentuk, atau ikon. Status pengukuran tidak dianimasikan terus-menerus dengan `animate-pulse`.

Ketentuan ini juga berlaku untuk strip kualitas, label, dan kontrol yang mengapit ScanField agar keseluruhan instrumen tetap konsisten.

### 13.4 Anatomi visual ScanField — tambahan

Urutan baca: status scan → skala dan sebaran target → target terpilih → konteks numerik. Komposisi berisi lapisan berikut.

| Lapisan | Spesifikasi |
| :--- | :--- |
| **Header instrumen** | Judul “Pemindaian sinyal”, mode, state operasi, interval aktual jika tersedia, dan hitungan `Diplot X / Tersedia Y`. Jumlah data lama, usia unknown, dan riwayat disebutkan terpisah. |
| **Grid polar** | Latar canvas solid; cincin RSSI per 10 dB dari −30 sampai −100 dBm. Tick minor opsional jika tidak menambah kepadatan. Garis dekoratif 1 CSS px; label skala tetap terbaca. |
| **Orientasi tata letak** | Pusat merupakan acuan skala. Tidak memakai N/E/S/W atau ikon lokasi collector. Bila angka sudut ditampilkan, labelnya “Sudut tata letak (hash)”; tanda 0°/90°/180°/270° cukup pada ukuran kompak. |
| **Sweep** | Garis 1–2 CSS px, sektor belakang 12°, opacity default 6% dan maksimal 8%. Terpotong tepat pada batas annulus plot. |
| **Beacon** | Inti lingkaran diameter tetap 8 CSS px; radius titik pusat ditentukan nilai. Ukuran tidak mengikuti RSSI. Hit area minimum 24 × 24 CSS px; kontrol sentuh utama ditargetkan 44 × 44 CSS px. |
| **Seleksi** | Outline signal-lime 2 CSS px dengan celah 3 px dari inti. Satu cincin pandu tipis pada radius terpilih dan label nilai memperjelas hubungan dengan skala. Tidak ada glow/pulse terus-menerus. |
| **Readout target** | Baris ringkas: nama, RSSI tampilan, perubahan dari observasi valid sebelumnya, usia, dan status. Detail provenance serta sparkline tetap di Inspector/timeline. |
| **Legenda** | Diletakkan dalam aliran layout di bawah plot, tidak menutupi beacon: “Radius: RSSI relatif, kuat ke pusat. Sudut: hash tetap, bukan arah/lokasi. Sweep: aktivitas scan.” |

Label penuh default hanya untuk target terpilih dan maksimal tiga target yang dipin. Jika ruang habis, tampilkan penanda pin dan detail di daftar. Label boleh digeser untuk menghindari tabrakan dengan connector pendek; pusat beacon tetap di koordinat aslinya.

`Y` menghitung target unik dalam mode dan pilihan riwayat saat ini sebelum filter pencarian/band. `X` menghitung target yang lolos seluruh filter dan mempunyai nilai radial valid untuk diplot. Hitungan selalu per BSSID/identitas BLE, bukan jumlah baris kelompok SSID. Target dengan nilai unavailable tetap ada di daftar dengan alasan tidak diplot. Label “tersedia” tidak mengklaim seluruh target fresh atau sedang memancarkan sinyal.

### 13.5 Kontrak kejujuran semantik — tambahan

#### A. Radius, nilai, dan unit

Untuk Discover WiFi/BLE, tentukan nilai tampilan `v` dari `signal.smoothed_value` yang valid bila tersedia; jika tidak, gunakan `signal.value`. Saat memakai `smoothed_value`, beri label “Diperhalus aplikasi” dan sediakan nilai sumber beserta metode aslinya di Inspector. Ini mempertahankan pilihan nilai yang sudah dipakai store saat ini; frontend tidak menambahkan smoothing numerik kedua.

Dengan `r_inner` dan `r_outer` sebagai batas area data:

```text
v_clamped = clamp(v, -100, -30)
u = (-30 - v_clamped) / 70
r = r_inner + u × (r_outer - r_inner)
```

| Nilai contoh | Posisi yang diharapkan |
| :--- | :--- |
| −30 dBm | `r_inner`, sisi sinyal kuat. |
| −65 dBm | Tengah annulus. |
| −100 dBm | `r_outer`, sisi sinyal lemah. |
| −20 / −110 dBm | Ditahan pada batas dalam/luar, disertai penanda “Di luar skala”; readout tetap −20 / −110 dBm. |
| Unavailable / NaN / unit tidak cocok | Tidak dipetakan ke radius; tersedia di daftar dengan alasan. |

Skala linear terhadap nilai dBm ini merupakan representasi visual relatif, bukan jarak atau daya linear. Nilai sumber, angka readout, dan ekspor tidak diganti dengan hasil clamp atau nilai interpolasi animasi. Tidak ada auto-rescale mengikuti komposisi target. Bila preset skala lain ditambahkan, pengguna memilihnya secara eksplisit dan rentangnya selalu terlihat.

Tampilkan angka ringkas dengan maksimal satu desimal; Inspector menyediakan nilai sumber beserta resolusi/metode yang tersedia. Desimal dari smoothing tidak boleh disajikan sebagai klaim ketelitian hardware. Perubahan `Δ` memakai dua observasi valid terakhir pada basis pemrosesan yang sama, diberi unit dB dan label “perubahan RSSI”. Jangan menghitung delta melintasi pergantian metode, mode, atau sesi.

#### B. Sudut dan identitas

Pertahankan algoritma tata letak baseline, diberi nama `hash31-v1`: mulai `h = 0`, iterasi unit kode UTF-16 dari `target_id`, gunakan `h = int32(31 × h + codeUnit)`, lalu `θ = abs(h) mod 360`. Posisi 0° berada di atas dan sudut meningkat searah jarum jam.

Input adalah identifier stabil yang telah mengikuti kebijakan pseudonimisasi produk. Hash tata letak bukan pengganti HMAC privasi. Nama SSID, urutan array, RSSI, waktu, dan status seleksi tidak menjadi input sudut. Beacon memakai identitas ECharts stabil berdasarkan `target_id` agar penyortiran tidak menukar animasi antar-target.

Stabilitas berlaku selama identitas sumber dan versi algoritma sama. Rotasi identitas BLE tidak boleh disamarkan sebagai kesinambungan perangkat yang pasti. Bila identitas baru belum terhubung secara sah, tampilkan sebagai target baru dengan batas identitas/provenance yang tersedia.

#### C. Batas representasi

- Satu beacon WiFi adalah satu BSSID dan satu beacon BLE adalah satu identitas observasi yang berlaku. Ringkasan SSID menyebut jumlah BSSID; tidak menciptakan beacon agregat dengan radius campuran.
- Ukuran inti menandai target, outline menandai seleksi, dan glyph/status menandai freshness. Warna lime tidak menyatakan confidence atau Channel Health score.
- SNR dan Channel Health tetap menjadi metrik tersendiri. RSSI kuat tidak otomatis berarti kanal sehat.
- SDR tetap mengutamakan spectrum/waterfall. Jika polar SDR dipertahankan, skala dan unitnya harus terpisah: dBFS untuk sumber tidak terkalibrasi, dBm hanya dengan kalibrasi yang sah. Skala WiFi tidak boleh diwariskan diam-diam.
- NetworkField Associated memakai legenda reachability/RTT sesuai data host; host tanpa RSSI tidak ditempatkan pada skala RSSI. Transisi fase tidak mengubah beacon AP menjadi host lewat morphing posisi.

### 13.6 Aktivitas scan, freshness, dan state visual — tambahan

**Aktivitas scan dan usia observasi target adalah dua hal berbeda.** Collector dapat terus memindai sementara target tertentu tidak teramati kembali. Satu target stale tidak menghentikan sweep seluruh sesi.

Sumber state memanfaatkan `activeSession.status`, keadaan adapter/association, status collector, koneksi stream, serta metadata scan/measurement. `active` pada sesi dan koneksi WebSocket saja belum cukup menjadi bukti scan menghasilkan aktivitas.

| State tampilan | Sweep dan beacon | Teks/aksi utama |
| :--- | :--- | :--- |
| **Siap / belum ada sesi** | Grid statis; tanpa beacon contoh. | “Siap memindai” dan Mulai Pindai. |
| **Memulai / menunggu data pertama** | Penanda perimeter statis; tidak berputar. | “Menunggu hasil collector”; jangan memakai angka kualitas default. |
| **Memindai** | Sweep aktif; beacon merespons observasi valid. | “Memindai”, usia data, interval aktual atau “Tidak tersedia”. |
| **Hasil scan kosong** | Sweep boleh aktif jika ada bukti siklus scan sukses, termasuk siklus kosong. | “Belum ada target terdeteksi” dan waktu scan terakhir. |
| **Menunggu pembaruan** | Sweep berhenti; koordinat terakhir dipertahankan, usia terus berjalan. | “Belum ada pembaruan collector”; tampilkan usia aktivitas terakhir. |
| **Dijeda pengguna / adapter** | Sweep berhenti; data terakhir tetap dapat diperiksa. | “Dijeda” dengan alasan; gunakan AdapterConflictBanner untuk mutex. |
| **Koneksi terputus / collector bermasalah** | Sweep berhenti; marker mengikuti usia data. | Pesan spesifik offline, reconnecting, permission denied, atau adapter off; aksi pemulihan kontekstual. |
| **Selesai / historis** | Tampilan snapshot statis; tanpa feedback kedatangan sampel. | “Sesi selesai” dan waktu snapshot; freshness dinilai pada waktu snapshot, tidak terus menghapus isi arsip. |
| **Simulasi** | Perilaku setara pemindaian selama generator aktif. | Badge “SIMULASI” persisten pada status dan detail sumber; bukan “Hardware”. |

**Bukti aktivitas:** siklus selesai dengan `scan_id` baru dan waktu selesai yang valid, atau event status collector yang secara eksplisit menyatakan aktivitas scan berjalan. Measurement batch kosong dapat menjadi bukti hanya jika membawa metadata aktivitas tersebut. Observasi target yang dikirim ulang tidak dihitung sebagai temuan baru. Bila kontrak collector belum dapat membuktikan aktivitas kosong, tampilkan “Menunggu hasil collector”.

Watchdog aktivitas berhenti mengizinkan sweep setelah `max(10 detik, 3 × interval aktual)` tanpa bukti baru; ketika interval tidak tersedia, gunakan 10 detik sebagai batas UI dan jangan tampilkan itu sebagai cadence terukur. Pengakuan pause, terminal state, stream terputus, atau konflik adapter menghentikan sweep segera, paling lambat 200 ms setelah state diterima UI. State terminal didahulukan, kemudian gangguan koneksi/collector, jeda, menunggu, dan memindai.

**Aturan usia target:** gunakan waktu observasi, bukan waktu kedatangan WebSocket. Jika `quality.age_ms` tersedia, tambahkan waktu monotonic sejak penerimaan agar usia tetap bertambah; cocokkan dengan `observed_at`/`captured_at` bila dapat dibandingkan. Usia harus memperhitungkan keterlambatan data buffered/replay; `age_ms` lama yang tidak mencakup keterlambatan tersebut tidak membuktikan data fresh. Jangan mengasumsikan jam collector dan browser tersinkronisasi. Timestamp meragukan atau usia yang tidak dapat ditentukan menghasilkan `unknown`, bukan `fresh`.

| Status target | Aturan usia default ketika usia valid | Bentuk visual |
| :--- | :--- | :--- |
| **Fresh** | WiFi ≤30 detik; BLE ≤3 detik. | Inti lime solid; pembacaan usia tersedia. |
| **Stale** | WiFi >30 sampai 60 detik; BLE >3 sampai 10 detik. | Outline/ikon peringatan dengan label “Data lama”; koordinat terakhir tetap. |
| **Expired** | WiFi >60 detik; BLE >10 detik. | Keluar dari himpunan live; tetap tersedia melalui “Tampilkan riwayat” sebagai marker hollow netral. |
| **Unknown** | Usia/provenance tidak dapat ditentukan. | Marker hollow dengan tanda tanya dan label “Usia tidak diketahui”. |

Ambang di atas mempertahankan baseline WiFi daftar dan kebijakan freshness collector BLE. Quality flag sumber yang lebih buruk harus dihormati; timer lokal tidak boleh membuat data kembali fresh. Penggantian ambang merupakan perubahan kebijakan bersama yang eksplisit, bukan penyesuaian lokal per komponen. Presence BLE seperti `fading/lost` ditampilkan terpisah dari freshness pengukurannya.

Cache, replay, atau batch baru dengan `observed_at` yang sama tidak mereset usia maupun memicu indikator sampel baru. `cache_possible` diberi label dan tidak diubah menjadi kepastian pengukuran baru. Observasi lebih lama dapat mengisi riwayat, tetapi tidak menimpa nilai terbaru target. Saat stream pulih, terapkan keadaan terkini; jangan memutar ulang rangkaian animasi backlog. Deduplikasi memerlukan identitas observasi per target, bukan hanya `scan_id` atau sequence batch.

Target terpilih yang expired tetap tersedia di Inspector sebagai data historis; bila penanda historis tidak ditampilkan, beri keterangan “Target terpilih berada di riwayat”. Status pin tidak membuat target expired terlihat sebagai aktif. Jeda tidak membekukan usia observasi live.

### 13.7 Interaksi dan penanganan kepadatan — tambahan

| Pemicu | Respons wajib |
| :--- | :--- |
| **Hover / focus** | Outline sementara dan tooltip solid berisi nama, identifier singkat, nilai/unit, usia, serta kanal/band bila tersedia. Tidak memperbesar beacon atau mengubah radius. Tooltip tidak menjadi satu-satunya akses detail. |
| **Klik / tap / Enter / Space** | Pilih identitas target; tampilkan outline persisten, cincin pandu, readout, Inspector, dan penekanan baris yang sama. Pointer selection tidak merampas fokus keyboard. |
| **Escape / tutup detail** | Tutup lapisan sementara terlebih dahulu; jika Inspector ditutup, kembalikan fokus ke kontrol pemicunya. |
| **Pin** | Tambahkan glyph pin statis. Pin memudahkan menemukan target tanpa mengubah koordinat, ukuran inti, atau kebijakan usia. |
| **Pencarian / filter** | Terapkan hasil yang sama pada plot dan daftar; tampilkan `Diplot X / Tersedia Y` sesuai definisi 13.4. Target terpilih yang tersembunyi oleh filter tidak diganti otomatis: jelaskan kondisinya dan sediakan “Hapus filter”. |
| **Per SSID / Per BSSID** | Ubah pengelompokan daftar. Per SSID dapat dibuka untuk memilih BSSID tertentu; beacon tetap per BSSID. Nama tersembunyi tidak digabung hanya karena sama-sama tanpa nama. |
| **Beacon bertumpuk** | Bila hit area beririsan, buka daftar kandidat bernama dengan nilai dan identifier. Hit area boleh besar; koordinat data tidak digeser. Counter “N target” menyatakan kepadatan lokal, bukan satu hasil pengukuran gabungan. |
| **Update sampel** | Readout berganti ke nilai observasi valid terbaru; posisi mengikuti transisi radial. Untuk target terpilih, satu garis kecil pada readout boleh memberi feedback sekali saat observasi baru diterima. |

Tidak ada drag bebas untuk memindahkan beacon, auto-rotation plot, atau zoom yang mengubah skala diam-diam. Perubahan nama, sort, pin, dan filter tidak diperlakukan sebagai target RF baru. SSID/nama perangkat dirender sebagai teks aman, termasuk di tooltip; konten nama tidak ditafsirkan sebagai HTML.

### 13.8 Motion contract — tambahan

| Elemen/peristiwa | Motion default | Reduced motion |
| :--- | :--- | :--- |
| **Sweep aktif** | Satu putaran 4 detik, linear; tanpa percepatan untuk menandai RSSI/throughput. | Penanda perimeter tetap dengan teks “Memindai”; tidak berputar. |
| **Target pertama kali teramati** | Muncul langsung pada radius benar, fade-in 140 ms. Tidak muncul dari pusat. | Muncul langsung. |
| **Nilai sampel berubah** | Tween radius maksimal 220 ms, ease-out tanpa overshoot; sudut tetap. Nilai yang sama tidak memindahkan titik. | Posisi langsung diperbarui. |
| **Hover / seleksi / pin** | Transisi outline atau warna 140 ms; tanpa perubahan ukuran data. | Perubahan statis langsung. |
| **Observasi baru target terpilih** | Garis acknowledgement pada readout muncul lalu padam satu kali dalam 140 ms; maksimal sekali per detik. | Usia/waktu observasi diperbarui; tanpa efek sementara. |
| **Fresh → stale / expired** | Pergantian glyph/outline 140 ms; penghapusan dari live mengikuti state, tanpa perjalanan ke tepi. | Perubahan langsung. |
| **Pause / gangguan / selesai** | Hentikan sweep, ganti dengan penanda perimeter statis dan teks state. | State statis yang sama. |

Satu putaran sweep **hanya indikator aktivitas**. Durasi 4 detik bukan estimasi scan selesai, sampling interval, progres kanal, atau bukti arah deteksi. Perlintasan lengan tidak boleh memicu nyala beacon, mengubah freshness, atau menunda data. Cadence terukur ditampilkan terpisah.

Nilai antara selama tween adalah feedback presentasi, bukan sampel tersimpan. Jika sampel tiba sebelum tween selesai, arahkan dari posisi tampilan saat ini ke nilai valid terbaru tanpa antrean animasi. Jika perubahan basis/identitas terjadi, jangan tween di antara dua makna yang berbeda. Efek acknowledgement dapat dilewati saat pembaruan padat; data tetap diproses.

Ketika tab tersembunyi, hentikan loop visual; ingesti mengikuti mekanisme streaming yang berlaku. Saat kembali terlihat, tampilkan state terkini tanpa replay animasi. Pengaturan reduced motion berlaku untuk ECharts, CSS, dan overlay secara menyeluruh; bukan hanya kelas animasi sweep.

### 13.9 Geometri, responsivitas, dan aksesibilitas — tambahan

- **Geometri tunggal:** pusat, `r_inner`, `r_outer`, orientasi sudut, dan transform resize dipakai bersama oleh grid, titik, guide seleksi, sweep, dan hit testing. Baseline annulus ECharts 8%–86% dari radius tersedia dapat dipertahankan. Overlay tidak menggunakan radius penuh kontainer. Selisih alignment maksimal 1 CSS px pada DPR 1 dan 2.
- **Ukuran panel:** pada desktop, plot lingkaran menyesuaikan lebar dan tinggi ruang yang tersedia setelah header, readout, dan legenda. Lingkaran beserta skalanya harus utuh pada viewport referensi 1366 × 768; jangan mengandalkan kontainer square besar yang memotong bagian bawah instrumen.
- **Layar kecil:** pada lebar 360 CSS px, rail/detail tersusun vertikal atau memakai sheet. Dokumen boleh bergulir vertikal; plot, label utama, dan legenda tidak terpotong atau menimbulkan scroll horizontal. Kurangi label sudut/tick minor sebelum mengurangi ukuran teks penting.
- **Kontras:** target verifikasi 4,5:1 untuk teks biasa dan 3:1 untuk penanda/kontrol grafis esensial. Grid dekoratif boleh lebih redup apabila skala tetap dapat dibaca lewat label/tick utama. Freshness tidak dibedakan hanya melalui penurunan opacity.
- **Keyboard dan pembaca layar:** sediakan nama/deskripsi plot serta daftar HTML terhubung. Gunakan fokus stabil dengan navigasi target yang terdokumentasi; Enter/Space memilih. Jangan menjadikan seluruh piksel canvas satu-satunya jalur interaksi atau memaksa ratusan tab stop. Urutan fokus tidak meloncat saat RSSI berubah.
- **Pengumuman:** gunakan live region untuk perubahan operasi dan hasil aksi, bukan tiap sampel RSSI. Detail numerik dapat diminta melalui target terpilih. Tooltip mengikuti hover/focus dan tersedia melalui aksi sentuh/detail.
- **Render:** gunakan ID data stabil, pembaruan incremental, serta komputasi data terpisah dari loop sweep. Beban besar boleh mengurangi label dan feedback sementara, tetapi tidak menghapus target secara diam-diam atau mengubah koordinat. Jika batas tampilan diperlukan, nyatakan jumlah yang tidak diplot dan pertahankan akses daftar lengkap.

## 19.3 Acceptance Test & DoD Pembaruan ScanField — tambahan

Gate berikut berlaku bersama DoD induk. Target kinerja adalah requirement baru, bukan klaim performa kode saat ini. QA mencatat hardware, OS, browser, versi renderer, viewport, serta fixture yang dipakai; hardware referensi ditetapkan sebelum pengukuran pembanding.

| ID | Skenario uji | Hasil wajib |
| :--- | :--- | :--- |
| **SCN-AT-01** | Target sama menerima −90 → −60 → −40 dBm; lakukan sort, filter, select, resize, dan reload snapshot yang sama. | Radius mengikuti rumus; sudut `hash31-v1` tetap. −65 dBm tepat di tengah annulus. Tidak ada perpindahan melingkar. |
| **SCN-AT-02** | Uji −20, −110, null, NaN, SNR 0, serta unit tidak cocok. | Clamping hanya pada posisi dan diberi label; data kosong/unit salah tidak diplot; nilai sumber dan SNR 0 tetap terbaca benar. |
| **SCN-AT-03** | Kirim observasi baru dengan RSSI sama, duplikasi observasi, data cache dengan sequence batch baru, dan replay lama. | Observasi baru boleh memperbarui usia; duplikasi/cache/replay tidak menjadi temuan baru atau mengembalikan marker menjadi fresh. |
| **SCN-AT-04** | Stop input, lakukan pause/resume, putus stream, matikan collector, lalu mulai association pada adapter yang sama. | Sweep berhenti sesuai state/watchdog; usia live terus berjalan. Setelah pulih, tidak ada rentetan animasi backlog; konflik adapter dijelaskan. |
| **SCN-AT-05** | Scan kosong dengan metadata valid; sesi aktif tanpa metadata aktivitas; filter menyingkirkan semua target; data tanpa RSSI. | Masing-masing menampilkan empty state yang tepat; tidak ada beacon sintetis atau informasi kualitas default yang dianggap terukur. |
| **SCN-AT-06** | Jalankan umur WiFi melewati 30/60 detik dan BLE melewati 3/10 detik; pin/pilih target lalu biarkan expired. | Plot, daftar, Inspector, dan count konsisten; expired tersedia sebagai riwayat dan tidak dinyatakan aktif. Snapshot historis tidak hilang karena jam live. |
| **SCN-AT-07** | Pilih lewat plot, daftar Per SSID/BSSID, sentuhan, dan keyboard; uji target bertumpuk dan perubahan sort. | Identitas seleksi sama di seluruh komponen; tiap target dapat diakses tanpa penggeseran koordinat. Respons seleksi ≤100 ms p95. |
| **SCN-AT-08** | Aktifkan reduced motion, buka-tutup tab, dan amati satu menit. | Tidak ada putaran sweep, tween, pulse, atau feedback sementara. Data, status, dan pemilihan tetap bekerja. |
| **SCN-AT-09** | Periksa 360 px, 1366 × 768, 1920 × 1080, zoom 200%, serta DPR 1/2. | Skala/legenda terbaca, plot utuh, fokus terlihat, kontrol terjangkau; alignment plot-overlay ≤1 CSS px dan tidak ada scroll horizontal akibat instrumen. |
| **SCN-AT-10** | Audit visual dan aksesibilitas pada fresh, stale, unknown, selected, paused, disconnected, dan simulation. | Patuh 13.3; kontras dan alur keyboard sesuai target; tidak ada blur/glow/gradient, fake compass, pulse idle, atau ketergantungan warna saja. |
| **SCN-AT-11** | Beban referensi 500 target pada 2 batch/detik selama 30 menit, disertai interaksi dan resize. | Latensi dari batch diterima browser ke posisi stabil ≤500 ms p95; frame time ≤33 ms p95 saat sweep aktif; KPI collector-ke-visual ≤1 detik p95 tetap menjadi gate end-to-end. Tidak ada duplikasi target atau pertumbuhan memori berkelanjutan akibat handler/animasi. |
| **SCN-AT-12** | Uji tekanan 1.000 target pada 5 batch/detik, lalu kembali ke beban referensi. | UI tetap dapat dihentikan dan daftar dapat dipakai; sistem mengurangi detail/feedback sebelum mengorbankan state data. Tidak ada antrean tween tanpa batas, crash, atau perubahan makna radius/sudut. |
| **SCN-AT-13** | Uji pemahaman pada sedikitnya 5 pengguna sasaran dengan pertanyaan tentang radius, sudut, sweep, usia data, dan seleksi. | Sedikitnya 4 dari 5 menjelaskan radius sebagai kekuatan relatif, sudut sebagai layout, dan sweep sebagai aktivitas; sedikitnya 4 dari 5 dapat memilih serta menemukan nilai/usia target tanpa bantuan. Salah tafsir lokasi/progres dicatat untuk revisi desain. |

**DoD pembaruan:** seluruh requirement Must dan gate di atas telah diverifikasi, penyimpangan ditangani, serta Product/Design/Engineering menyepakati hasil dengan bukti uji. Artefak implementasi minimal mencakup state matrix, fixture semantik, rekaman interaksi normal/reduced motion, dan hasil kinerja. Pembuatan PRD ini sendiri tidak menyatakan gate tersebut telah lulus.

## Catatan implementasi untuk penelusuran

Kontrak data yang sudah tersedia mencakup `signal.value`, `smoothed_value`, `captured_at`, `observed_at`, `age_ms`, `actual_interval_ms`, freshness, source method, dan processing. Model tampilan baru perlu mempertahankan metadata per target agar label global tidak menggantikan provenance target terpilih. Ketiadaan field ditampilkan sebagai unavailable/unknown.

Sumber: [types.ts](https://github.com/Zaikhul/SignalScanner/blob/79c1b409bfc11017b9dc02edc40d1058ef5ac90d/frontend/lib/types.ts), [store.ts](https://github.com/Zaikhul/SignalScanner/blob/79c1b409bfc11017b9dc02edc40d1058ef5ac90d/frontend/lib/store.ts), [useSessionStream.ts](https://github.com/Zaikhul/SignalScanner/blob/79c1b409bfc11017b9dc02edc40d1058ef5ac90d/frontend/hooks/useSessionStream.ts), dan [ble_adapter.py](https://github.com/Zaikhul/SignalScanner/blob/79c1b409bfc11017b9dc02edc40d1058ef5ac90d/collector/app/adapters/ble_adapter.py).

Jika status aktivitas scan kosong atau metadata usia belum dapat disalurkan secara konsisten, Backend/Collector melengkapi kontrak itu sebagai dependensi FR-SCN-04/05. Sampai tersedia, frontend memakai state menunggu/unknown yang sesuai. Tidak ada angka sintetis yang dipakai untuk membuat instrumen terlihat aktif.

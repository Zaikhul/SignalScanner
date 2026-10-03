# Laporan Analisis QA — SignalScanner

Tanggal pemeriksaan: **3 Oktober 2026** (UTC). Repositori: [Zaikhul/SignalScanner](https://github.com/Zaikhul/SignalScanner). Target: **`main`**, commit **`823ec1a98f1fd5a5b768436fe0181f33bcf0c42a`**.

## Ringkasan Eksekutif

**Kesimpulan QA: tunda penggunaan pada jaringan yang tidak tepercaya dan penggunaan hasil sebagai bukti pengukuran operasional sampai temuan prioritas diperbaiki.** Frontend berhasil dibangun dan lolos pemeriksaan tipe, tetapi keberhasilan tersebut tidak membuktikan kebenaran alur collector, keamanan API, atau akurasi pengukuran.

Laporan memuat **29 temuan: 8 Tinggi dan 21 Sedang**. Tidak ada temuan yang dinilai Kritis berdasarkan bukti yang diperiksa. Risiko utama adalah kontrol perangkat dan ingest tanpa autentikasi, publikasi layanan database dengan konfigurasi kredensial bawaan, duplikasi pengukuran saat retry, data simulasi yang diberi label hardware, serta rekomendasi kanal yang mengabaikan RSSI terukur. Terdapat pula penghambat instalasi backend dan packaging frontend Docker.

Beberapa hasil konkret dari pemeriksaan lokal:

- Register collector, membuat/memulai sesi, dan ingest berhasil tanpa header autentikasi.
- Dua pengiriman batch identik, masing-masing berisi dua pengukuran, menghasilkan empat baris tersimpan.
- Dua kali stop menghasilkan dua manifest; pembacaan manifest berikutnya mengembalikan HTTP 500.
- Pengukuran `-40 dBm` menghasilkan laporan kanal dengan `max_rssi=-90 dBm` dan skor 98.
- Perbandingan kanal menyatakan sinyal turun 55 dB walaupun window sesudah tidak berisi sampel.
- Saat SoapySDR tidak tersedia, adapter menghasilkan 1.024 bin acak dengan `source_method="soapysdr_rx"`.
- Timestamp SQLite kehilangan offset UTC; di zona Jakarta, sampel berumur satu detik dibaca berumur 25.201 detik dan dianggap expired.

Pemeriksaan memakai kode pada commit tetap, ASGI dalam proses, database sintetis, serta mock transport/adapters. **Tidak ada pengujian pada layanan live, eksploitasi sistem, akses data pihak lain, atau pemindaian jaringan/hardware.**

## Cakupan dan Metode

- **Repositori:** `https://github.com/Zaikhul/SignalScanner`.
- **Cabang/commit yang dianalisis:** `main` pada SHA di atas; `git ls-remote` dan HEAD clone memberikan SHA yang sama.
- **Riwayat yang tersedia:** dua commit pada riwayat `main`: `79c1b409bfc11017b9dc02edc40d1058ef5ac90d` dan `823ec1a98f1fd5a5b768436fe0181f33bcf0c42a`. Diff commit terakhir dan metadata keduanya diperiksa. Branch lain, PR, issue, dan konfigurasi GitHub di luar berkas repositori tidak dianalisis.
- **Inventaris:** 122 berkas terlacak, 18.426 baris berdasarkan `wc -l`. Tidak ada `AGENTS.md` terlacak. Seluruh 56 berkas Python berhasil diparse sebagai AST.
- **Berkas yang ditinjau manual:** README, `.gitignore`, manifest dependensi, konfigurasi env, seluruh Dockerfile, Compose, `run.py`; backend entry point, konfigurasi/security, model/session database, router REST dan WebSocket, schema measurement/session/manifest/export, layanan session/collector/association/export/channel health, mesin signal/stream/channel health, dan migrasi; collector daemon, buffer/uploader/pseudonymizer/radio mutex, kontrak adapter, serta bagian relevan WiFi Windows, asosiasi WiFi, BLE, SDR, mock, LAN inventory, dan diagnostik; frontend API client, hook WebSocket, store, matematika polar, halaman live/channel health/history, kontrol sesi/collector, modal kredensial, dan aksi asosiasi. Kedalaman pembacaan bervariasi; seluruh komponen visual tidak diaudit manual baris demi baris.
- **Metode:** penelusuran alur lintas berkas, penilaian kontrak, pemeriksaan konfigurasi, parsing sintaks, build/typecheck, dan 30 observasi reproduksi terarah. Observasi reproduksi bukan suite test milik proyek, bukan angka cakupan, dan bukan 30 temuan independen.
- **Integritas sumber:** clone yang diperiksa tidak diedit. Instalasi Python dilakukan dalam venv terpisah; frontend dibangun pada salinan sementara. Data uji hanya dalam memory atau SQLite sementara. `git status --porcelain --untracked-files=all` tetap kosong setelah pemeriksaan.
- **Akses:** Git clone berhasil. Pembacaan halaman GitHub melalui alat web gagal dengan `DisabledError`; analisis kode menggunakan clone, bukan hasil halaman web yang gagal.
- **Pemeriksaan/perintah:** tercatat beserta hasil pada bagian [Pengujian dan Pemeriksaan](#pengujian-dan-pemeriksaan).
- **Batasan:** tidak tersedia Docker daemon/CLI, PostgreSQL/Redis uji, Windows, atau perangkat WiFi/BLE/SDR. Tidak dilakukan uji performa, uji penetrasi live, audit WCAG menyeluruh, pengukuran cakupan, atau pencocokan seluruh dependensi dengan advisory/CVE. Tidak ada klaim bahwa dependensi tertentu mempunyai CVE aktif.

Semua nomor baris adalah **1-based pada commit yang dianalisis**. Sumber dapat diaudit melalui [pohon kode pada SHA tetap](https://github.com/Zaikhul/SignalScanner/tree/823ec1a98f1fd5a5b768436fe0181f33bcf0c42a); perubahan `main` sesudah SHA tersebut berada di luar laporan.

**Dasar tingkat keparahan:** Tinggi berarti kontrol/data dapat diakses tanpa identitas pada deployment yang terjangkau, instalasi/deployment utama terhambat, atau integritas hasil utama rusak pada skenario yang telah direproduksi. Sedang berarti kegagalan fungsi atau integritas yang lebih terbatas atau membutuhkan kondisi khusus. Penilaian paparan jaringan bersyarat pada reachability; laporan tidak menyatakan layanan produksi tertentu telah terekspos.

## Gambaran Proyek

SignalScanner merupakan aplikasi pengukuran sinyal WiFi, BLE, dan spektrum radio dengan UI web, backend pengolah sinyal, serta daemon collector. Versi konfigurasi API adalah `1.0.0`; collector mengiklankan `1.1.0`, sementara sejumlah kontrak pengukuran dan fitur kanal memakai versi `2.0`/`1.2`. Perbedaan versi tersebut dipetakan sebagai metadata, bukan otomatis dianggap cacat.

| Subsistem | Teknologi dan lokasi | Tanggung jawab yang dikonfirmasi |
|---|---|---|
| Backend | Python, FastAPI, Pydantic, SQLAlchemy async; `backend/app` | Sesi, collector/command polling, ingest, statistik, rekomendasi kanal, WebSocket, ekspor dan manifest |
| Penyimpanan | SQLite default; PostgreSQL/TimescaleDB pada Compose | Pengukuran, target, marker, asosiasi, inventory, snapshot kanal dan ekspor |
| Collector | Python, HTTPX, aiosqlite; `collector/app` | Pemindaian adapter, heartbeat, penerimaan perintah, buffer offline, asosiasi WiFi dan inventory LAN |
| Hardware | WlanApi/netsh Windows, Bleak, SoapySDR | Implementasi adapter yang ditinjau secara statis; hardware nyata tidak diuji |
| Frontend | Next.js 15, React 19, TypeScript, Zustand, Tailwind, ECharts | Live scan, visualisasi polar/spectrum, inspector, kontrol sesi, history dan channel health |
| Orkestrasi | `run.py`, package scripts, Docker Compose | Menjalankan backend, collector, frontend, serta layanan data untuk jalur Docker |

Alur utama: collector register → UI membuat sesi → backend menyimpan sesi dan antrean `start_scan` → heartbeat mengambil perintah → collector menghasilkan batch → uploader mengirim/buffer → backend memproses dan menyimpan → stream in-memory meneruskan event ke UI → stop menyusun manifest → ekspor membuat JSON/CSV/ZIP. Asosiasi WiFi mempunyai dua jalur pemicu: direct local agent untuk kredensial dan command backend tanpa kredensial; interaksi keduanya menimbulkan F-13.

Perintah yang ditentukan proyek adalah `python run.py`, `docker compose up --build`, `uvicorn app.main:app --app-dir backend`, `python -m collector.app.main`, `pytest backend/tests collector/tests -v`, serta script frontend `next build`, `next lint`, dan `vitest run`. README juga merujuk script Windows dan direktori tests yang tidak tersedia pada commit ini.

Ada penggunaan SQLAlchemy dan parameter SQL pada buffer yang mengurangi risiko interpolasi SQL di jalur tersebut. Pseudonimisasi dilakukan pada ID collector sebelum upload, backend memakai perbandingan HMAC constant-time dalam helper, dan beberapa prefix IPv4 dibatasi pada kode inventory. Namun helper signature tidak dihubungkan ke ingest, konfigurasi privasi belum seluruhnya ditegakkan, dan kontrol ini tidak menggantikan autentikasi.

## Ringkasan Temuan

| ID | Temuan | Kategori | Keparahan | Lokasi utama |
|---|---|---|---|---|
| F-01 | API backend dan WebSocket tidak mengautentikasi pemanggil | Keamanan | Tinggi | `backend/app/main.py:45–57`; `api/v1/ingest.py:15–25` |
| F-02 | Local agent menerima kontrol tanpa pairing/auth dengan CORS wildcard | Keamanan perangkat lokal | Tinggi | `collector/app/main.py:403–446` |
| F-03 | Compose mempublikasikan database/Redis dengan konfigurasi keamanan bawaan | Keamanan deployment | Tinggi | `docker-compose.yml:4–29` |
| F-04 | Requirements backend tidak memenuhi kebutuhan SQLAlchemy asyncio yang ter-resolve | Build/runtime | Tinggi | `backend/requirements.txt:5`; `app/db/session.py:2` |
| F-05 | Dockerfile frontend menyalin direktori `public` yang tidak tersedia | Deployment | Tinggi | `frontend/Dockerfile:19–22` |
| F-06 | Retry ingest dan drain paralel menggandakan pengukuran | Integritas data | Tinggi | `session_manager.py:419–488`; `uploader.py:34–37,62–80` |
| F-07 | Data sintetis dapat dilaporkan sebagai pemindaian hardware | Integritas pengukuran | Tinggi | `sdr_adapter.py:94–107,118–165`; `collector/app/main.py:251–259` |
| F-08 | Channel health memakai RSSI default dan mengabaikan lebar kanal terukur | Logika analitik | Tinggi | `channel_health_service.py:54–68` |
| F-09 | Isi event tidak divalidasi konsisten dengan envelope batch | Validasi/kontrak | Sedang | `schemas/measurement.py:94–122`; `session_manager.py:330–355` |
| F-10 | Cursor sequence melewatkan pengukuran satu batch | Fungsional/API | Sedang | `api/v1/measurements.py:14–28` |
| F-11 | Perintah pause tidak ditangani collector | Fungsional/state | Sedang | `session_manager.py:128–142`; `collector/app/main.py:122–216` |
| F-12 | Transisi sesi tidak dijaga; stop berulang merusak pembacaan manifest | Fungsional/state | Sedang | `session_manager.py:90–268,495–503` |
| F-13 | Alur kredensial menelan error dan memicu asosiasi kedua tanpa password | Fungsional/orchestrasi | Sedang | `WifiCredentialModal.tsx:94–114`; `collector/app/main.py:169–180` |
| F-14 | SSID/password tidak di-escape saat membangun XML profil WiFi | Fungsional/validasi | Sedang | `wifi_associate_windows.py:462–540` |
| F-15 | `--backend-url` tidak diteruskan ke uploader global | Konfigurasi/runtime | Sedang | `collector/app/main.py:43–44,279,555–558`; `uploader.py:134` |
| F-16 | URL/port frontend dan runner tidak mengikuti konfigurasi secara konsisten | Konfigurasi/integrasi | Sedang | `useSessionStream.ts:42–46`; `run.py:297–312` |
| F-17 | Durasi dan konfigurasi radio sesi tidak diteruskan ke adapter | Fungsional/konfigurasi | Sedang | `session_manager.py:74–78,102–111`; `collector/app/main.py:122–155,264–268` |
| F-18 | Window kosong menghasilkan kesimpulan perubahan sinyal numerik | Logika analitik | Sedang | `channel_health_service.py:324–407` |
| F-19 | Manifest tidak diverifikasi; informasi gap/clock diisi tanpa bukti | Integritas/audit | Sedang | `session_manager.py:220–241,490–503` |
| F-20 | `mask_ssid=true` tidak mencegah penyimpanan/paparan SSID | Keamanan/privasi | Sedang | `schemas/session.py:18–21`; `session_manager.py:388–398` |
| F-21 | HMAC memakai key dan salt bawaan yang diketahui dari kode | Keamanan/privasi | Sedang | `backend/app/config.py:14–15`; `collector/app/config.py:13–14` |
| F-22 | Field median sebenarnya berisi rata-rata | Logika statistik | Sedang | `session_manager.py:632–644,675` |
| F-23 | EMA target tercampur antarsesi | Logika pengolahan sinyal | Sedang | `core/signal_processor.py:10–26`; `session_manager.py:367` |
| F-24 | Snapshot dan replay menggandakan hitungan target UI | Fungsional/streaming | Sedang | `api/ws/session_stream.py:27–51`; `store.ts:236–246` |
| F-25 | ID adapter global bertabrakan antarcollector | Model data | Sedang | `collector/app/main.py:64–83`; `collector_service.py:93–111` |
| F-26 | Timestamp SQLite tanpa offset menyebabkan freshness salah | Integritas waktu/UI | Sedang | `session_manager.py:663–669`; `scanfieldMath.ts:116–142` |
| F-27 | Startup `create_all` tidak memigrasi database lama | Deployment/migrasi | Sedang | `backend/app/db/session.py:27–30` |
| F-28 | Test terdokumentasi tidak tersedia dan lint belum dapat dijalankan otomatis | Pengujian/kualitas | Sedang | `.gitignore:44,51,84,97–98`; `frontend/package.json:9–10` |
| F-29 | Collector yang ditampilkan dapat berbeda dari collector yang dipakai memulai sesi | Fungsional/UI | Sedang | `CollectorPicker.tsx:21–23,43`; `SessionControls.tsx:55–79` |

Path singkat di tabel adalah suffix berkas; lokasi lengkap dicantumkan di setiap temuan.

## Temuan Terperinci

### [F-01] API backend dan WebSocket tidak mengautentikasi pemanggil

- **Kategori:** Keamanan — autentikasi, otorisasi, integritas ingest.
- **Keparahan:** Tinggi. Pemanggil yang dapat menjangkau API dapat mengontrol sesi dan mengirim data atas nama collector lain.
- **Lokasi:** `backend/app/main.py:29–57`; `backend/app/api/v1/collectors.py:25–62`; `backend/app/api/v1/sessions.py:18–23,57–90`; `backend/app/api/v1/ingest.py:15–25`; `backend/app/api/ws/session_stream.py:15–30`; `backend/app/core/security.py:25–28`.
- **Bukti dan perilaku yang diamati:** V-01, tanpa `Authorization`, memperoleh register 200, list 200, create session 201, start 200, dan ingest 200. Dependency router hanya database; WebSocket langsung `accept()`. Helper `verify_device_signature` ditemukan tetapi tidak dipanggil pada alur ingest. Binding `collector_id` hanya membandingkan string yang disuplai pemanggil.
- **Dampak/skenario:** Pada API yang terjangkau pihak lain, ID yang diperoleh dari list dapat dipakai untuk perubahan sesi, command polling/ack palsu, pengiriman pengukuran, dan pembacaan data. Tidak ada pengujian terhadap sistem produksi; tidak diklaim terjadi kompromi nyata.
- **Rekomendasi:** Tambahkan autentikasi operator dan collector yang terpisah. Ikat session/collector/export ke principal/tenant; verifikasi signature atau kredensial collector, timestamp dan replay protection. Terapkan otorisasi per aksi termasuk WebSocket. Hapus wildcard CORS default (`backend/app/config.py:16–22`) dan gunakan allowlist.
- **Verifikasi ulang:** Request tanpa kredensial harus 401; principal tanpa hak harus 403; collector A tidak boleh mengirim ke sesi collector B; WS anonim ditolak sebelum snapshot. Ulangi V-01 pada ASGI/database uji.
- **Keyakinan:** Tinggi untuk ketiadaan kontrol pada kode dan perilaku ASGI. Reachability deployment eksternal tidak diuji.

### [F-02] Local agent menerima kontrol perangkat tanpa pairing atau autentikasi

- **Kategori:** Keamanan perangkat lokal — trust boundary browser/agent.
- **Keparahan:** Tinggi. Endpoint dapat mengubah koneksi WiFi host dan melewati konfirmasi wewenang backend/UI.
- **Lokasi:** `collector/app/main.py:403–446`, khususnya CORS `408–411`, direct associate `423–438` dan disconnect `440–443`; `frontend/lib/apiClient.ts:190–196`.
- **Bukti dan perilaku yang diamati:** V-15 menangkap aplikasi local agent dengan server Uvicorn diganti stub; preflight dari origin tidak tepercaya memperoleh 200 dan origin tersebut pada `Access-Control-Allow-Origin`. POST disconnect tanpa autentikasi memperoleh 200 dan memanggil fungsi disconnect yang dimock. Direct associate tidak memerlukan pairing token, principal, atau `authorized_use_confirmed`.
- **Dampak/skenario:** Aplikasi lokal atau halaman yang diizinkan browser mengakses loopback dapat meminta perubahan koneksi perangkat. Binding `127.0.0.1` membatasi akses jaringan langsung, tetapi tidak menyediakan identitas atau otorisasi pemanggil. Perilaku Private Network Access/browser tertentu tidak diuji; keberhasilan serangan lewat semua browser tidak diasumsikan.
- **Rekomendasi:** Terapkan pairing/session token lokal, validasi Origin/Host, allowlist origin yang diperlukan, dan izin operasi dari sesi operator yang terverifikasi. Bind association ke collector/session yang benar. Tolak panggilan asing sebelum membuat task hardware.
- **Verifikasi ulang:** Origin asing dan token kosong/salah ditolak; direct associate tanpa association terotorisasi tidak menjalankan adapter; disconnect hanya berlaku pada association milik sesi pemanggil. Gunakan stub adapter dan jangan ubah jaringan live saat menguji.
- **Keyakinan:** Tinggi untuk perilaku endpoint/CORS; skenario lintas browser bersyarat.

### [F-03] Compose mempublikasikan layanan data dengan konfigurasi keamanan bawaan

- **Kategori:** Keamanan deployment.
- **Keparahan:** Tinggi bila host terjangkau jaringan tidak tepercaya; dampaknya mencakup akses langsung data melalui database.
- **Lokasi:** `docker-compose.yml:4–15,22–29,42–48`.
- **Bukti dan perilaku yang diamati:** PostgreSQL dikonfigurasi dengan username/password literal bawaan di Compose. Pemetaan `5432:5432` dan `6379:6379` tidak membatasi host IP. Tidak ada konfigurasi kata sandi/ACL Redis di Compose. Kredensial tidak disalin utuh ke laporan ini.
- **Dampak/skenario:** Menjalankan konfigurasi ini pada host dengan port yang dapat dijangkau memperluas trust boundary di luar API. Firewall atau kebijakan image/runtime dapat membatasi akses, tetapi tidak tersedia bukti deployment demikian. Tidak dilakukan koneksi ke port tersebut.
- **Rekomendasi:** Hapus publikasi port database/Redis jika hanya dipakai service Compose. Untuk kebutuhan lokal, bind loopback; gunakan akun database berhak minimum dan secret unik di luar source. Konfigurasikan autentikasi Redis bila service dapat diakses lintas trust boundary. Ganti kredensial bawaan pada instalasi yang pernah menggunakannya.
- **Verifikasi ulang:** Render konfigurasi Compose pada lingkungan uji; pastikan port internal tidak terpublikasi ke semua interface. Uji akses dengan identitas tidak sah pada layanan uji terisolasi, bukan produksi.
- **Keyakinan:** Tinggi untuk konfigurasi berkas; eksposur jaringan aktual dan konfigurasi efektif image tidak diuji.

### [F-04] Requirements tidak menyediakan dependensi asyncio SQLAlchemy yang diperlukan

- **Kategori:** Build/runtime — reproduksibilitas dependensi.
- **Keparahan:** Tinggi. Instalasi yang mengikuti requirements dapat gagal bahkan sebelum backend start.
- **Lokasi:** `backend/requirements.txt:5`; `backend/app/db/session.py:2`; `backend/app/api/v1/associations.py:3`.
- **Bukti dan perilaku yang diamati:** Instalasi requirements backend/collector ter-resolve ke SQLAlchemy `2.1.3` tanpa `greenlet`. Import `app.main` gagal dengan `ImportError: The SQLAlchemy asyncio module requires that the Python 'greenlet' library is installed`. Requirements menulis `sqlalchemy>=2.0.36`, tanpa extra `[asyncio]`. `greenlet` ditambahkan hanya pada venv audit agar pemeriksaan berikutnya dapat berjalan.
- **Dampak/skenario:** Fresh setup atau build container dengan resolver yang menghasilkan kombinasi tersebut tidak dapat menjalankan API. Instalasi lama yang sudah mempunyai greenlet mungkin tidak terpengaruh; tidak semua resolusi versi diasumsikan gagal.
- **Rekomendasi:** Deklarasikan `sqlalchemy[asyncio]` dengan rentang versi yang diuji dan simpan constraints/lock yang konsisten. Tambahkan smoke check import serta startup database sementara pada pipeline.
- **Verifikasi ulang:** Instalasi dari nol tanpa paket global harus berhasil mengimpor `app.main` dan menginisialisasi SQLite/PostgreSQL uji. Catat versi hasil resolusi.
- **Keyakinan:** Tinggi untuk kombinasi versi yang diuji; bergantung resolver/lingkungan pada instalasi lain.

### [F-05] Packaging frontend Docker bergantung pada direktori yang tidak tersedia

- **Kategori:** Deployment/build image.
- **Keparahan:** Tinggi. Jalur Compose yang direkomendasikan terhambat pada tahap packaging image frontend.
- **Lokasi:** `frontend/Dockerfile:19–22`, khususnya `COPY --from=builder /app/public ./public` pada baris 21.
- **Bukti dan perilaku yang diamati:** `frontend/public` tidak ada pada checkout. Setelah `npm run build` berhasil pada salinan frontend, direktori `public` tetap tidak ada. Dockerfile menyalinnya tanpa kondisi.
- **Dampak/skenario:** Build image dari checkout ini tidak memiliki sumber `/app/public` untuk instruksi COPY. Ini merupakan ketidaksesuaian packaging yang terkonfirmasi secara statis; log kegagalan Docker tidak tersedia karena Docker tidak terpasang.
- **Rekomendasi:** Jika tidak memakai aset public, hapus COPY tersebut. Jika diperlukan, tambahkan aset/direktori terlacak atau buat direktori secara eksplisit pada builder sebelum COPY. Tambahkan verifikasi build image dari clean checkout.
- **Verifikasi ulang:** `docker compose build frontend` harus selesai pada lingkungan Docker uji; image yang dihasilkan dapat start dan melayani halaman serta aset.
- **Keyakinan:** Tinggi terhadap sumber COPY yang hilang; container belum dibangun/dijalankan dalam audit ini.

### [F-06] Retry dan drain paralel menggandakan pengukuran tersimpan

- **Kategori:** Integritas data — idempotensi dan concurrency.
- **Keparahan:** Tinggi. Jalur pemulihan koneksi dapat merusak statistik serta dataset bukti tanpa error bagi pengguna.
- **Lokasi:** `backend/app/services/session_manager.py:419–488`; `backend/app/db/models.py:151–182`; `collector/app/core/uploader.py:34–37,62–80`; `collector/app/core/buffer_queue.py:125–146`.
- **Bukti dan perilaku yang diamati:** V-02: batch identik berisi dua event dikirim dua kali; keduanya 200 dan jumlah baris menjadi empat. Tidak ada deduplikasi/constraint unik identitas event. V-18: dua drain coroutine membaca satu row buffered yang sama, lalu mengirim dua request sebelum row dihapus. Drain dijadwalkan pada setiap keberhasilan upload tanpa lock.
- **Dampak/skenario:** Timeout sesudah backend commit tetapi sebelum client menerima response menyebabkan retry; reconnect juga dapat menjalankan beberapa drain bersamaan. Total sampel, EMA, ringkasan, dan analitik dihitung dari data ganda.
- **Rekomendasi:** Definisikan identitas event/batch stabil dan unique constraint yang sesuai. Jangan membuat sequence saja unik karena satu siklus berisi beberapa target. Terapkan idempotent upsert/ack dan satu drain worker dengan claim/lease transaksi per row.
- **Verifikasi ulang:** Kirim batch sama berkali-kali dan simulasikan response timeout setelah commit; jumlah event tetap sama. Jalankan dua drain terhadap satu queue row dan pastikan satu pengiriman/efek penyimpanan efektif.
- **Keyakinan:** Tinggi; kedua kegagalan direproduksi dengan ASGI/MockTransport dan data sementara.

### [F-07] Kegagalan hardware atau fallback dapat menghasilkan data sintetis berlabel hardware

- **Kategori:** Integritas/provenance pengukuran.
- **Keparahan:** Tinggi. Data yang dibuat secara acak dapat dipercaya sebagai observasi radio nyata.
- **Lokasi:** `collector/app/adapters/sdr_adapter.py:57–63,73–107,118–165`; `collector/app/main.py:251–259,273–279`; `collector/app/adapters/mock_adapter.py:88–114`; `frontend/components/controls/SessionControls.tsx:74–80,157–160`.
- **Bukti dan perilaku yang diamati:** X-04, pada cabang `SOAPY_AVAILABLE=False`, menghasilkan 1.024 bin sintetis dengan `source_type="collector"`, `source_method="soapysdr_rx"` dan freshness fresh. `run_scan` tidak memanggil `adapter.validate()`. Pada Linux, mode WiFi tanpa `--mock` memilih `MockSignalAdapter`; V-17 menunjukkan kontrak mock tetap `collector` dan source method unknown.
- **Dampak/skenario:** Driver/perangkat tidak tersedia atau pembacaan IQ gagal, tetapi layar tetap menampilkan data aktif dan badge hardware. Dataset ekspor/provenance kehilangan pembedaan penting antara hasil terukur dan hasil sintetis.
- **Rekomendasi:** Pada mode hardware, fail closed dengan state unsupported/failed jika validasi gagal. Jangan mengganti error baca dengan noise acak tanpa provenance simulator eksplisit. Label setiap batch/event sintetis sebagai simulator dan tampilkan label tersebut berdasarkan sumber aktual, bukan hanya toggle UI.
- **Verifikasi ulang:** Tanpa driver/perangkat, mode hardware harus menampilkan error dan tidak menghasilkan pengukuran hardware. Mode mock harus menghasilkan `virtual_simulator`/simulator pada data, UI, ekspor, dan manifest. Gunakan adapter stub untuk pengujian awal.
- **Keyakinan:** Tinggi untuk cabang kode dan output sintetis; hardware nyata tidak diuji.

### [F-08] Rekomendasi kanal mengabaikan RSSI dan lebar kanal yang masuk melalui measurement

- **Kategori:** Logika analitik.
- **Keparahan:** Tinggi. Rekomendasi fitur utama dapat berlandaskan input berbeda dari hasil pengukuran sebenarnya.
- **Lokasi:** `backend/app/services/channel_health_service.py:54–68`; `backend/app/services/session_manager.py:383–398,419–439`; `backend/app/core/channel_health_engine.py:209–241`.
- **Bukti dan perilaku yang diamati:** Service mengambil RSSI dari `TargetModel.metadata_json["latest_rssi"]` atau default `-90.0`, dan width dari metadata atau default 20. Ingest tidak memindahkan RSSI/`radio.channel_width_mhz` ke metadata tersebut. V-08 memasukkan `-40 dBm`, width 40 MHz, tetapi snapshot melaporkan `max_rssi=-90.0` dan health score 98. Adapter Windows/mock juga tidak mengisi `latest_rssi` pada extra metadata.
- **Dampak/skenario:** AP kuat dapat diberi bobot hampir nol; overlap dan pemilihan kanal tidak mencerminkan daya/lebar kanal sebenarnya. Query target mencakup seluruh sesi tanpa menyaring last_seen pada observation window, sehingga AP lama juga dapat tetap dihitung.
- **Rekomendasi:** Bentuk input dari measurement terbaru yang valid per target dalam window, simpan field radio yang diperlukan, dan bedakan missing data dari nilai default. Filter target stale/expired serta dokumentasikan agregasi waktunya.
- **Verifikasi ulang:** Input `-40` dan `-90 dBm` pada AP sama harus memberi max_rssi dan penalti yang berbeda secara benar. Bandingkan 20/40 MHz; AP di luar window tidak dipakai sebagai observasi terkini.
- **Keyakinan:** Tinggi; ketidaksesuaian RSSI direproduksi, jalur width/window dikonfirmasi melalui kode.

### [F-09] Event dapat bertentangan dengan identitas dan sequence envelope batch

- **Kategori:** Validasi input/kontrak data.
- **Keparahan:** Sedang. Ingest yang diterima dapat menghasilkan database dan stream dengan identitas/sequence tidak konsisten.
- **Lokasi:** `backend/app/schemas/measurement.py:94–122`; `backend/app/services/session_manager.py:330–355,424,443–444,481–484`.
- **Bukti dan perilaku yang diamati:** V-03 menerima HTTP 200 untuk envelope sequence `-8`, event sequence `999`, serta inner `session_id`/`collector_id` berbeda dari envelope. Validasi service memeriksa source, outer collector binding dan mode, tetapi tidak relasi field inner/outer atau range sequence. Row database memakai outer session, sementara payload event yang dipublikasikan mempertahankan inner session.
- **Dampak/skenario:** Bug adapter atau client dapat membuat pagination, replay, tracing, dan manifest bekerja pada sequence/identitas yang berbeda. Ini berbeda dari F-01: autentikasi saja tidak memperbaiki kontrak yang rusak.
- **Rekomendasi:** Tambahkan model validator batch: identitas inner harus sama, sequence non-negatif sesuai definisi, range terurut dan cocok dengan isi, timestamp/angka finite valid. Nyatakan schema version yang diterima secara eksplisit.
- **Verifikasi ulang:** Variasi identitas, range negatif/terbalik, dan sequence di luar range ditolak 422/400; batch normal dengan banyak target pada sequence sama tetap diterima.
- **Keyakinan:** Tinggi; kasus kontradiktif direproduksi.

### [F-10] Pagination measurements kehilangan event ketika satu sequence memiliki banyak target

- **Kategori:** Fungsional/API — completeness data.
- **Keparahan:** Sedang. Client tidak dapat menjamin pengambilan seluruh pengukuran dengan cursor yang tersedia.
- **Lokasi:** `backend/app/api/v1/measurements.py:14–28`; `collector/app/adapters/wifi_windows.py:114,156,203–204`; `frontend/lib/apiClient.ts:130–139`.
- **Bukti dan perilaku yang diamati:** Query diurutkan hanya oleh sequence dan dibatasi jumlah row; halaman berikut memakai `sequence > after_sequence`. Dalam V-04, limit satu mengambil satu row sequence 1, padahal empat row mempunyai sequence tersebut; halaman berikut langsung ke sequence 999 dan melewatkan tiga row lainnya. Tanpa duplikasi pun satu siklus WiFi memang berisi beberapa AP pada sequence sama.
- **Dampak/skenario:** Recovery/data extraction dengan page limit yang memotong siklus menghasilkan dataset tidak lengkap. Tidak perlu outage atau data berbahaya untuk memicu masalah.
- **Rekomendasi:** Gunakan cursor komposit `(sequence, measurement_id)` dengan ordering stabil dan kembalikan next cursor; atau paginate per batch dengan seluruh event siklus sebagai unit atomik.
- **Verifikasi ulang:** Banyak AP pada satu sequence, limit kecil, dan pengambilan sampai habis harus menghasilkan tepat semua row unik tanpa gap/duplikasi.
- **Keyakinan:** Tinggi; direproduksi pada ASGI/database memory.

### [F-11] Pause mengubah status backend tetapi tidak menghentikan collector

- **Kategori:** Fungsional/state dan penanganan error.
- **Keparahan:** Sedang. Pause UI menghasilkan penolakan batch dan pekerjaan collector terus berjalan.
- **Lokasi:** `backend/app/services/session_manager.py:128–142,330–334`; `collector/app/main.py:122–216`; `collector/app/core/uploader.py:44–55`.
- **Bukti dan perilaku yang diamati:** Backend mengantrekan `pause_scan`, tetapi `handle_command` tidak memiliki cabang tersebut. V-05: pause endpoint 200, ingest berikutnya 400; adapter stub tidak dihentikan dan command tidak di-ack. Uploader memasukkan 400 ke dead-letter queue.
- **Dampak/skenario:** Pengguna melihat paused sementara perangkat tetap scan/upload. Command pause tetap pending pada heartbeat; data saat pause dikarantina dan disk dapat terus bertambah. Resume hanya mengirim start_scan, tanpa protokol pause/resume yang konsisten.
- **Rekomendasi:** Implementasikan pause/resume dengan state collector dan acknowledgement hasil operasi. Tentukan kebijakan data in-flight dan koordinasikan perubahan status backend dengan keberhasilan command.
- **Verifikasi ulang:** Pada pause, produksi/upload berhenti, command selesai sekali, dan tidak ada pertumbuhan DLQ. Resume melanjutkan sequence/adapter dengan benar; uji juga pause saat batch sedang dikirim.
- **Keyakinan:** Tinggi untuk command handler dan response backend; hardware diganti stub.

### [F-12] State machine sesi tidak menjaga transisi dan stop tidak idempotent

- **Kategori:** Fungsional/state, integritas finalisasi.
- **Keparahan:** Sedang. Request ulang yang wajar dapat mengakibatkan manifest tidak dapat dibaca.
- **Lokasi:** `backend/app/services/session_manager.py:90–99,128–135,158–165,193–254,495–503`; `backend/app/db/models.py:212–227`.
- **Bukti dan perilaku yang diamati:** Tidak ada guard status asal untuk start/pause/resume/stop. V-06: stop dua kali sama-sama 200, membuat dua manifest; `get_session_manifest` kemudian HTTP 500 karena `scalar_one_or_none()` memperoleh lebih dari satu row. Start pada sesi completed diterima, dan `ended_at` lama tetap ada.
- **Dampak/skenario:** Double-click, retry response, atau client terlambat dapat menggandakan finalisasi. Membuka kembali sesi completed mengubah data setelah evidence dibuat dan menghasilkan durasi/status tidak konsisten.
- **Rekomendasi:** Definisikan tabel transisi, reject transisi ilegal dengan 409, dan jadikan stop idempotent. Gunakan constraint unik atau versi manifest eksplisit; pilih manifest terbaru dengan `limit(1)` bila versioning memang didukung. Sesi completed dibuat baru, bukan diaktifkan kembali diam-diam.
- **Verifikasi ulang:** Stop dua kali menghasilkan satu finalisasi dan manifest tetap dapat dibaca. Resume dari draft/completed dan start ulang active/completed mengikuti kontrak yang terdokumentasi; timestamp tetap konsisten.
- **Keyakinan:** Tinggi; rangkaian request direproduksi.

### [F-13] Pengiriman kredensial menyembunyikan kegagalan dan command backend memicu asosiasi kedua

- **Kategori:** Fungsional/integrasi, error handling.
- **Keparahan:** Sedang. Koneksi WiFi utama dapat gagal atau mengalami race meskipun UI telah menganggap perintah berhasil.
- **Lokasi:** `frontend/components/modals/WifiCredentialModal.tsx:94–125`; `frontend/lib/apiClient.ts:181–202`; `backend/app/services/association_service.py:124–138`; `collector/app/main.py:169–180,289–300`; `collector/app/core/radio_mutex.py:51–61`.
- **Bukti dan perilaku yang diamati:** J-01: fetch local agent yang gagal menghasilkan `null` tanpa exception; J-02: HTTP 400 tetap dikembalikan sebagai hasil biasa karena `res.ok` tidak diperiksa. Modal meneruskan `connectAssociation`. Pada jalur sukses direct associate sudah memulai task berkredensial, tetapi backend juga mengantrekan `associate_wifi`; X-02 membuktikan command tersebut memanggil asosiasi terpisah dengan `password=None`. Tidak ada deduplikasi association aktif di daemon.
- **Dampak/skenario:** Local agent tidak tersedia → fallback tidak mempunyai password untuk WPA. Saat tersedia, direct request dan heartbeat dapat memulai dua task terhadap radio/profile yang sama. Kegagalan koneksi Windows akibat race belum diuji pada hardware dan tidak dinyatakan pasti terjadi setiap saat.
- **Rekomendasi:** Jadikan satu jalur sebagai pemilik eksekusi association, gunakan ID operasi idempotent, dan koordinasikan credential handoff dengan command tanpa mengirim secret ke backend. Throw pada HTTP/network error; UI hanya mengubah status setelah acknowledgement yang benar.
- **Verifikasi ulang:** Agent unreachable/400 menampilkan error dan tidak menampilkan keberhasilan palsu. Direct submit plus heartbeat untuk association sama hanya mengeksekusi sekali dan mempertahankan kredensial secara ephemeral.
- **Keyakinan:** Tinggi untuk penelanan error dan pemicu kedua; dampak hardware/race bersyarat.

### [F-14] Karakter XML pada SSID atau password merusak profil WiFi

- **Kategori:** Fungsional/validasi encoding.
- **Keparahan:** Sedang. SSID/password valid dengan karakter khusus tidak dapat menghasilkan profil XML valid.
- **Lokasi:** `collector/app/adapters/wifi_associate_windows.py:462–540`, termasuk interpolasi `<name>` dan `<keyMaterial>`.
- **Bukti dan perilaku yang diamati:** V-13 menggunakan SSID sintetis `QA & Lab` atau password sintetis dengan `&`; hasil `_build_profile_xml` gagal diparse oleh XML parser. Nilai ditempel melalui f-string tanpa escaping.
- **Dampak/skenario:** Jaringan dengan `&`/`<` pada SSID/password dapat gagal pada impor profil. Kesalahan ini terkonfirmasi sebagai malformed XML; laporan tidak menyimpulkan command injection/RCE.
- **Rekomendasi:** Bangun XML memakai serializer seperti ElementTree, set nilai sebagai text node, dan validasi batas SSID/key sesuai kontrak jaringan. Jangan mencetak password dalam log error.
- **Verifikasi ulang:** Round-trip XML untuk karakter khusus, Unicode, SSID tersembunyi, WPA2/WPA3/open; text node hasil parse harus identik dengan input. Impor profil nyata hanya pada host Windows uji yang diizinkan.
- **Keyakinan:** Tinggi untuk encoding; netsh/hardware tidak dijalankan.

### [F-15] Override alamat backend CLI tidak memengaruhi uploader

- **Kategori:** Konfigurasi/runtime.
- **Keparahan:** Sedang. Registration/heartbeat dan pengukuran dapat dikirim ke backend berbeda.
- **Lokasi:** `collector/app/main.py:43–44,279,555–558`; `collector/app/core/uploader.py:14–21,134`; `run.py:266–274`.
- **Bukti dan perilaku yang diamati:** V-14 membuat daemon dengan URL sintetis custom; `daemon.backend_url` mengikuti override, tetapi uploader global tetap memakai URL dari settings. `run_scan` memanggil global uploader, tidak instance yang dikonfigurasi daemon.
- **Dampak/skenario:** `--backend-url` atau `run.py --port-backend` custom dapat menunjukkan collector online tetapi pengukuran tidak sampai. Jika backend default lain tersedia, data bahkan dapat menuju proses yang salah; skenario salah proses tersebut tidak diuji live.
- **Rekomendasi:** Injeksi satu konfigurasi/client ke daemon, uploader dan diagnostics; hindari instance global yang menangkap settings sebelum argumen CLI diterapkan.
- **Verifikasi ulang:** MockTransport mencatat register, heartbeat, ingest dan diagnostics ke base URL custom yang sama. Uji tanpa environment BACKEND_URL agar override CLI benar-benar diuji.
- **Keyakinan:** Tinggi; perbedaan object URL direproduksi tanpa koneksi eksternal.

### [F-16] URL dan port tidak konsisten antara REST, WebSocket, halaman kanal dan runner

- **Kategori:** Konfigurasi/integrasi deployment.
- **Keparahan:** Sedang. Konfigurasi port/host selain default tidak berlaku untuk seluruh fungsi.
- **Lokasi:** `frontend/lib/apiClient.ts:13–16`; `frontend/hooks/useSessionStream.ts:42–46`; `frontend/app/channel-health/page.tsx:38–55,77–78,110–111`; `frontend/next.config.ts:8–9`; `run.py:298–312`; `frontend/Dockerfile:10–11`; `docker-compose.yml:80–83`.
- **Bukti dan perilaku yang diamati:** REST memakai `NEXT_PUBLIC_API_URL`, WS memakai hostname halaman dan port literal 8000, halaman channel health memakai literal loopback 8000, dan rewrite memakai loopback 8000. Runner membentuk URL dari `--port-frontend` tetapi command `next dev` tidak mendapat port tersebut. NEXT_PUBLIC_API_URL di Compose diberikan pada runtime, bukan input builder; ekspresi client telah dibundel saat build.
- **Dampak/skenario:** Remote UI atau port custom dapat berhasil memanggil satu subsistem tetapi gagal streaming/channel health. Dalam container frontend, rewrite loopback menunjuk container sendiri. `--port-frontend` juga dapat menunggu/membuka port yang berbeda dari server yang diluncurkan.
- **Rekomendasi:** Pusatkan konfigurasi URL dan derive WS dari URL API yang sama; gunakan route/proxy yang sadar container bila dipilih. Berikan variabel publik saat build atau gunakan konfigurasi runtime yang dirancang khusus. Teruskan port runner melalui argumen/env ke Next.js.
- **Verifikasi ulang:** Build/start pada port non-default dan hostname uji; semua REST/WS/channel health harus menuju backend yang sama. Periksa hasil bundle untuk literal alamat default yang tidak diinginkan.
- **Keyakinan:** Tinggi terhadap konstruksi kode; deployment remote/TLS/Compose tidak dijalankan.

### [F-17] Konfigurasi radio dan batas durasi tersimpan tetapi tidak diterapkan

- **Kategori:** Fungsional/konfigurasi perangkat.
- **Keparahan:** Sedang. API menerima konfigurasi yang tidak sesuai dengan pemindaian yang dijalankan.
- **Lokasi:** `backend/app/services/session_manager.py:74–78,102–111,168–176`; `collector/app/main.py:122–155,264–268`; `collector/app/core/adapter_base.py:15–24`; `collector/app/adapters/mock_adapter.py:66–74`.
- **Bukti dan perilaku yang diamati:** X-01 membuat sesi radio dengan durasi satu detik, center 915 MHz, FFT 2.048 dan gain nol. Data disimpan, tetapi command mempunyai `parameters=null`; pemanggilan `run_scan` hanya menerima session, mode, mock dan interval. `ScanConfig` memakai nilai radio default. Batas duration juga tidak diterapkan pada loop mock yang diperiksa.
- **Dampak/skenario:** Pemindaian dapat terus berjalan dan menggunakan frekuensi/gain/FFT yang berbeda dari manifest/config yang dipercaya operator. Dampak hardware tidak diukur; ketidakselarasan kontrak dan argumen nyata telah dikonfirmasi.
- **Rekomendasi:** Teruskan seluruh config tervalidasi dan hash config efektif, bedakan nilai nol dari None, serta tegakkan deadline menggunakan monotonic time pada daemon. Laporkan effective configuration yang dikonfirmasi adapter.
- **Verifikasi ulang:** Adapter stub menerima semua nilai custom termasuk gain 0; sesi berhenti setelah durasi yang ditentukan. Manifest mencerminkan effective configuration dan bukan sekadar request awal.
- **Keyakinan:** Tinggi untuk propagasi argumen; hardware tidak diuji.

### [F-18] Analisis sebelum/sesudah mengisi window kosong dengan nilai sinyal buatan

- **Kategori:** Logika analitik dan kualitas bukti.
- **Keparahan:** Sedang. Sistem menghasilkan kesimpulan numerik dari data yang tidak tersedia.
- **Lokasi:** `backend/app/services/channel_health_service.py:324–354,357–407`; `backend/app/core/channel_health_engine.py:181–187,282–289`.
- **Bukti dan perilaku yang diamati:** V-09 menjalankan validasi tanpa marker sesaat setelah satu sampel `-40 dBm`. Window after berisi nol sampel, tetapi fallback mean `-95` menghasilkan delta `-55` dan teks sinyal menurun 55 dB. Reference default adalah waktu sekarang sehingga sebagian besar window after masih berada di masa depan. X-03 juga menunjukkan statistik instability 2.4 GHz memakai pengukuran 6 GHz dengan nomor kanal sama, karena agregasi hanya berdasarkan channel.
- **Dampak/skenario:** Pengguna dapat menyimpulkan perpindahan kanal memperburuk/memperbaiki jaringan tanpa bukti after yang cukup; hasil juga dapat tercampur lintas band. Kesalahan ini terpisah dari F-08 yang menyangkut input RSSI target.
- **Rekomendasi:** Tandai metrik unavailable/insufficient jika salah satu window kosong atau terlalu sedikit; tunggu window selesai sebelum menghitung. Validasi kepemilikan marker, filter band/target, dan pisahkan dua interval agar sampel batas tidak terhitung ganda.
- **Verifikasi ulang:** After kosong menghasilkan status insufficient, tanpa delta/klaim arah. Data 6 GHz tidak memengaruhi instability 2.4 GHz. Uji marker, interval lengkap, dan batas timestamp.
- **Keyakinan:** Tinggi; kedua perhitungan bermasalah direproduksi.

### [F-19] Manifest dibaca tanpa pemeriksaan checksum dan memuat metadata bukti yang tidak dihitung

- **Kategori:** Integritas/audit provenance.
- **Keparahan:** Sedang. Konsumen manifest dapat menerima record korup atau informasi kelengkapan yang menyesatkan.
- **Lokasi:** `backend/app/services/session_manager.py:208–241,490–503`; `backend/app/schemas/manifest.py:14–18,40–47`; `backend/app/api/v1/manifests.py:29,44–49,58–59`.
- **Bukti dan perilaku yang diamati:** V-12 mengubah `collector_version` hanya pada record database sintetis, tanpa memperbarui checksum. `get_session_manifest` tetap mengembalikannya walaupun `compute_checksum()` berbeda. Service juga selalu mengisi `missing_ranges=[]`, clock offset 0/uncertainty 2 ms, dan menghitung `total_received` sebagai jumlah row measurement, bukan jumlah sequence/siklus unik.
- **Dampak/skenario:** Korupsi penyimpanan tidak dideteksi oleh jalur yang mengklaim verifikasi. Satu siklus multi-AP dapat terlihat sebagai beberapa frame; gap tidak dihitung dan ketidakpastian clock tampak terukur. Checksum biasa bukan bukti autentisitas digital; laporan tidak menganggap hash tanpa signature sebagai jaminan terhadap semua manipulasi.
- **Rekomendasi:** Verifikasi checksum kanonik pada read/export; bedakan jumlah event dan siklus, hitung gap dari sequence unik, serta tandai clock unknown bila belum diukur. Jika membutuhkan bukti autentisitas, rancang signing/immutable storage sesuai kebutuhan, bukan hanya menamai hash sebagai verifikasi.
- **Verifikasi ulang:** Perubahan satu field tanpa checksum baru harus ditolak/ditandai invalid. Sequence 1 dan 3 melaporkan gap 2; satu siklus dengan dua AP mempunyai dua event dan satu siklus. Clock tanpa telemetry tidak menampilkan ketidakpastian terukur.
- **Keyakinan:** Tinggi; bypass pemeriksaan checksum direproduksi, metadata statis dikonfirmasi dari kode.

### [F-20] Konfigurasi mask SSID tidak ditegakkan pada ingest dan keluaran

- **Kategori:** Keamanan/privasi.
- **Keparahan:** Sedang. Pilihan privasi yang diterima API tidak mengendalikan data yang disimpan/ditampilkan.
- **Lokasi:** `backend/app/schemas/session.py:18–21`; `backend/app/services/session_manager.py:74–78,388–398,443–444,664–666`; `backend/app/services/export_service.py:105–115`.
- **Bukti dan perilaku yang diamati:** V-11 membuat sesi dengan `privacy_config.mask_ssid=true`; sesudah ingest, endpoint targets tetap mengembalikan nama SSID sintetis secara utuh. Ingest menyimpan display_name dan memublikasikan event tanpa menerapkan mask; ekspor JSON menyertakan display_name.
- **Dampak/skenario:** Operator yang mengandalkan mask dapat merekam/membagikan nama jaringan sensitif. Pengaturan pseudonymize/collect_payload juga tidak mempunyai enforcement alur lengkap; laporan tidak menyatakan payload paket benar-benar dikumpulkan.
- **Rekomendasi:** Terapkan kebijakan privasi sebelum persistence/fanout dan audit seluruh export path. Tolak opsi yang belum didukung; jangan menerima konfigurasi yang hanya disimpan sebagai metadata. Audit existing data jika mask pernah dianggap aktif.
- **Verifikasi ulang:** Dengan mask aktif, SSID asli sintetis tidak ditemukan pada target, measurement extras, replay, ekspor dan evidence bundle. Dengan mask nonaktif, perilaku mengikuti kontrak yang jelas.
- **Keyakinan:** Tinggi untuk display_name/targets yang direproduksi; seluruh tipe data sensitif belum diaudit menyeluruh.

### [F-21] Key dan salt HMAC bawaan membuat pseudonim dapat dihitung ulang lintas instalasi

- **Kategori:** Keamanan/privasi, pengelolaan konfigurasi rahasia.
- **Keparahan:** Sedang. Perlindungan terhadap korelasi/dictionary kandidat ID melemah jika deployment memakai default.
- **Lokasi:** `backend/app/config.py:14–15`; `collector/app/config.py:13–14`; `backend/app/core/security.py:14–22`; `collector/app/core/pseudonymizer.py:11–16`; template env backend/collector pada bagian key/salt.
- **Bukti dan perilaku yang diamati:** Kedua subsistem memiliki key dan tenant salt literal bawaan yang sama dan dapat start tanpa menggantinya. Pseudonim deterministik memakai nilai tersebut. Compose tidak menyediakan override key/salt. Nilai key/salt tidak disalin ke laporan.
- **Dampak/skenario:** Pihak yang mengetahui source dapat menghitung pseudonim untuk kandidat MAC/BSSID dan mencocokkannya; instalasi dengan default dapat dikorelasikan. Ini bukan bukti kredensial produksi aktif bocor, dan tidak membuka password WiFi dengan sendirinya.
- **Rekomendasi:** Wajibkan key unik dan salt/scope tenant yang nyata di deployment non-demo, dengan validasi startup. Sinkronkan versi key collector/backend melalui konfigurasi aman. Rotasi default yang pernah dipakai serta tetapkan kebijakan terhadap dataset pseudonim lama.
- **Verifikasi ulang:** Mode produksi dengan key kosong/bawaan gagal startup; MAC sintetis sama pada tenant berbeda menghasilkan pseudonim berbeda, tetapi tetap konsisten dalam tenant/versi key yang sama.
- **Keyakinan:** Tinggi untuk penggunaan default; pemakaian default pada deployment nyata tidak diverifikasi.

### [F-22] `median_signal` mengembalikan rata-rata aritmetika

- **Kategori:** Logika statistik/kontrak API.
- **Keparahan:** Sedang. Statistik yang dilabeli median salah, terutama bila distribusi mempunyai outlier.
- **Lokasi:** `backend/app/services/session_manager.py:632–644,675`; `backend/app/schemas/measurement.py:136`; `backend/app/services/session_manager.py:545–551`.
- **Bukti dan perilaku yang diamati:** Aggregate memakai `func.avg(signal_value)` lalu dimasukkan ke `median_signal`. V-10: sampel `[-90,-90,-30]` mempunyai median `-90`, tetapi response adalah `-70`. Median summary sesi juga selalu None.
- **Dampak/skenario:** Client yang memakai median sebagai ukuran sinyal tipikal menerima mean; satu spike dapat mengubah hasil secara tidak diharapkan.
- **Rekomendasi:** Hitung median yang sebenarnya dengan metode sesuai database/window, atau ubah nama field menjadi mean melalui versi kontrak yang jelas. Jangan mengisi statistik unavailable dengan nama metrik lain.
- **Verifikasi ulang:** Uji distribusi ganjil/genap, satu sampel, outlier, dan kosong; nama/statistik pada API serta UI harus selaras.
- **Keyakinan:** Tinggi; hasil numerik direproduksi.

### [F-23] State EMA tidak dibatasi pada sesi pengukuran

- **Kategori:** Logika pengolahan sinyal/isolation state.
- **Keparahan:** Sedang. Pengukuran awal sesi baru dipengaruhi data sesi lain.
- **Lokasi:** `backend/app/core/signal_processor.py:10–26,28–32`; `backend/app/services/session_manager.py:367`.
- **Bukti dan perilaku yang diamati:** Cache EMA global berkey hanya target_id; ingest tidak menyertakan session_id dan lifecycle sesi tidak memanggil reset EMA. V-16: target yang sebelumnya `-90` kemudian mendapat sample awal sesi lain `-30`; hasil menjadi `-69`, bukan inisialisasi `-30`.
- **Dampak/skenario:** Sesi bersamaan dengan target sama saling memengaruhi; sesi baru dapat tampak memiliki kualitas sinyal lama. Cache juga bertahan selama proses hidup tanpa batas per sesi.
- **Rekomendasi:** Scope state dengan session/collector/target dan parameter processing. Bersihkan saat finalisasi dan pastikan perubahan state dilakukan setelah validasi/commit atau dipulihkan bila transaksi gagal.
- **Verifikasi ulang:** Target sama pada dua sesi menghasilkan EMA independen. First sample sesi baru sama dengan raw sample; sesi gagal ingest tidak mengubah state sesi berhasil.
- **Keyakinan:** Tinggi untuk keying dan hasil perhitungan; cache global dikonfirmasi pada callsite.

### [F-24] Reconnect melakukan snapshot lalu replay tanpa deduplikasi hitungan UI

- **Kategori:** Fungsional/stream recovery.
- **Keparahan:** Sedang. Jumlah sampel target dapat membengkak setelah reconnect meskipun database tidak berubah.
- **Lokasi:** `backend/app/api/ws/session_stream.py:27–51`; `frontend/hooks/useSessionStream.ts:72–98`; `frontend/lib/store.ts:216–220,236–246`.
- **Bukti dan perilaku yang diamati:** Server mengirim snapshot target berisi aggregate seluruh data, lalu replay event sesudah cursor lama. Client memasang target snapshot dan menaikkan sample_count untuk setiap replay. J-04: snapshot count satu, lalu event sama diputar ulang, menghasilkan count dua. Hook juga tidak menolak batch dengan sequence yang telah diterima.
- **Dampak/skenario:** Disconnect sementara/replay menggandakan aggregate UI dan timeline; angka layar berbeda dari sumber database. Race antara snapshot/replay dan registrasi subscriber juga perlu pengujian lanjutan.
- **Rekomendasi:** Berikan watermark konsisten pada snapshot; replay hanya event di atas watermark atau gunakan baseline snapshot sesuai cursor. Pisahkan rebuilding timeline dari aggregate target, dan deduplikasi dengan identitas event stabil.
- **Verifikasi ulang:** Reconnect berulang tanpa measurement baru tidak mengubah count/min/max. Batch overlap/out-of-order dan event baru saat handshake harus menghasilkan state tepat sekali dan lengkap.
- **Keyakinan:** Tinggi untuk penghitungan ganda pada kontrak snapshot/store; handshake jaringan browser belum diuji end-to-end.

### [F-25] ID adapter sama digunakan oleh semua collector sehingga metadata saling menimpa

- **Kategori:** Model data/multi-collector.
- **Keparahan:** Sedang. Data adapter dan ownership tidak akurat ketika lebih dari satu collector terdaftar.
- **Lokasi:** `collector/app/main.py:64–83`; `backend/app/services/collector_service.py:93–111`; `backend/app/db/models.py:48–59`.
- **Bukti dan perilaku yang diamati:** Daemon mengirim ID tetap `win_wlan_01`, `ble_bleak_01`, `sdr_mock_01`; model memakai ID global sebagai primary key. Registration mencari adapter hanya berdasarkan ID. V-07 mendaftarkan dua collector dengan ID adapter sama: satu row tetap dimiliki collector A tetapi namanya berubah ke metadata collector B.
- **Dampak/skenario:** Inventory/diagnostics/provenance dapat mengaitkan perangkat satu host dengan host lain. Collector kedua tidak mendapatkan adapter row miliknya secara benar.
- **Rekomendasi:** Gunakan ID namespace collector atau kunci komposit `(collector_id, adapter_local_id)`. Filter update berdasarkan ownership dan migrasikan referensi association/provenance yang memakai ID tersebut.
- **Verifikasi ulang:** Dua collector dengan local adapter ID sama mempunyai dua row terpisah; update satu tidak memengaruhi yang lain.
- **Keyakinan:** Tinggi; registration ganda direproduksi pada database memory.

### [F-26] Timestamp dari SQLite kehilangan offset dan salah diinterpretasi browser Jakarta

- **Kategori:** Integritas waktu/freshness.
- **Keparahan:** Sedang. Jalur default SQLite membuat hasil baru terlihat stale/expired pada zona waktu non-UTC.
- **Lokasi:** `backend/app/db/models.py:136–140,163–165`; `backend/app/services/session_manager.py:663–669`; `backend/app/api/v1/measurements.py:35`; `frontend/lib/scanfieldMath.ts:116–142`.
- **Bukti dan perilaku yang diamati:** X-06: input `2026-10-03T03:00:00Z` menjadi response target `2026-10-03T03:00:00`. J-05 menjalankan helper produksi dengan `TZ=Asia/Jakarta`: pada waktu UTC satu detik setelah input, string tanpa offset menghasilkan expired/25.201 detik; string berakhiran Z menghasilkan fresh/satu detik.
- **Dampak/skenario:** Snapshot setelah reconnect dan data history dari SQLite berbeda interpretasi waktu dari live event yang masih ber-offset. Target dapat hilang dari tampilan/filter freshness dan waktu audit menjadi ambigu.
- **Rekomendasi:** Normalisasi timestamp hasil ORM ke aware UTC sebelum serialization; wajibkan offset/Z pada kontrak API. Jangan menambahkan offset lokal berdasarkan asumsi browser. Uji kedua database yang didukung.
- **Verifikasi ulang:** Round-trip UTC melalui SQLite dan PostgreSQL mempertahankan instant yang sama; helper freshness menghasilkan usia identik pada UTC/Jakarta/zona negatif, termasuk reconnect snapshot.
- **Keyakinan:** Tinggi; perubahan timestamp backend dan efek helper timezone direproduksi.

### [F-27] Startup membuat tabel tetapi tidak mengupgrade schema database lama

- **Kategori:** Deployment/migrasi.
- **Keparahan:** Sedang. Upgrade dengan database persisten dapat start tanpa menambahkan kolom yang diperlukan lalu gagal saat query/ingest.
- **Lokasi:** `backend/app/main.py:22–26`; `backend/app/db/session.py:27–30`; `backend/Dockerfile:16`; `docker-compose.yml:36–58`; `backend/migrations/versions/0003_measurement_trust_layer.py:18–24`; `backend/migrations/versions/0002_alter_frequency_hz_to_bigint.py:20–28`.
- **Bukti dan perilaku yang diamati:** Startup hanya `Base.metadata.create_all`; command deployment tidak menjalankan Alembic. X-05 memakai schema lama minimal sintetis dalam memory: tabel measurements yang sudah ada tetap tidak mendapatkan kolom scan_id setelah `init_db()`. Migrasi 0002 memakai operasi ALTER dengan parameter PostgreSQL; jalur upgrade SQLite belum dibuktikan kompatibel.
- **Dampak/skenario:** Volume lama yang belum mempunyai kolom baru tidak diperbaiki otomatis. Fresh database dapat bekerja sesudah masalah dependensi diatasi, tetapi itu bukan verifikasi upgrade. Schema sintetis yang diuji bukan salinan database produksi atau eksekusi penuh migrasi historis.
- **Rekomendasi:** Tetapkan satu strategi schema/versioning; jalankan migrasi terkontrol sebelum API, verifikasi revision saat startup, dan dokumentasikan upgrade SQLite/PostgreSQL. Hindari kombinasi create_all dengan migrasi add-column tanpa guard/version yang konsisten.
- **Verifikasi ulang:** Upgrade snapshot schema sebelumnya pada dua database uji; migration selesai, kolom/constraint sesuai model, existing data utuh dan ingestion berhasil. Jangan menjalankan percobaan ini pada database produksi tanpa prosedur backup yang sesuai.
- **Keyakinan:** Tinggi terhadap tidak adanya upgrade startup dan reproduksi create_all; migrasi PostgreSQL penuh tidak dijalankan.

### [F-28] Artefak pengujian yang dijanjikan tidak tersedia dan lint tidak siap untuk CI

- **Kategori:** Pengujian/kualitas, reproduksibilitas.
- **Keparahan:** Sedang. Regresi pada alur inti tidak memiliki gate otomatis yang dapat dijalankan dari checkout ini.
- **Lokasi:** `README.md:43,49,59,151–162`; `package.json:13–15`; `.gitignore:44,51,84,97–98`; `frontend/package.json:9–10`; `frontend/vitest.config.ts:5–8`; `backend/requirements.txt:1–16`.
- **Bukti dan perilaku yang diamati:** Perintah pytest terdokumentasi keluar kode 4 karena backend/tests tidak ada, collected zero. Vitest keluar kode 1 karena tidak ada test files. Lint meminta konfigurasi ESLint interaktif dan keluar kode 1. `.gitignore` mengabaikan tests, pnpm lock, PRD dan script Windows; berkas lock dan konfigurasi workflow `.github` tidak ditemukan pada inventaris. Ini tidak membuktikan tests pernah ada lalu dihapus.
- **Dampak/skenario:** Clean checkout tidak menyediakan skenario regresi sesi/ingest/privacy/streaming. Rentang versi dependensi yang longgar tanpa lock membuat hasil setup berubah; F-04 menunjukkan contoh konkret. Build frontend yang berhasil tidak merupakan bukti coverage atau audit lint.
- **Rekomendasi:** Lacak tests/fixtures, konfigurasi lint non-interaktif dan lock/constraints; revisi ignore rule spesifik. Tambahkan pipeline minimum: clean install, import/startup, test fungsi kritis, typecheck/build, serta build image. Sesuaikan README dengan artefak yang benar-benar tersedia; `run.ps1`, `run.bat`, `launch-split.ps1` dan PRD yang disebut juga tidak ada.
- **Verifikasi ulang:** Perintah README pada clean checkout mengumpulkan test nyata dan berakhir 0; lint berjalan tanpa prompt. Test harus mendeteksi regresi F-01/F-06/F-11/F-12/F-26, bukan hanya meniru implementasi.
- **Keyakinan:** Tinggi untuk inventaris dan hasil perintah. Cakupan tidak dapat dihitung karena suite proyek tidak tersedia.

### [F-29] Sesi hardware dapat memakai collector berbeda dari yang ditampilkan UI

- **Kategori:** Fungsional/UI — pemilihan perangkat.
- **Keparahan:** Sedang. Pada beberapa collector, identitas perangkat di layar dan pelaksana scan dapat tidak selaras.
- **Lokasi:** `frontend/components/controls/CollectorPicker.tsx:21–23,43,93–103`; `frontend/components/controls/SessionControls.tsx:9–12,55–79`; `frontend/app/page.tsx:55–56,181–183`.
- **Bukti dan perilaku yang diamati:** Picker mempertahankan selectedCollectorId bila sudah bukan default dan menampilkan nama collector itu. `handleStart` justru memilih `freshCollectors.find` pertama yang ready/busy, tanpa menggunakan selectedCollectorId. Backend mengurutkan list collector dari created_at terbaru (`collector_service.py:147`).
- **Dampak/skenario:** UI terbuka saat collector A aktif; collector B kemudian register. Picker dapat tetap menampilkan A, tetapi start berikutnya memakai B. Diagnostics di halaman tetap merujuk selectedCollectorId, sehingga perangkat yang diperiksa juga dapat berbeda dari pelaksana sesi.
- **Rekomendasi:** Resolve selectedCollectorId terhadap daftar terbaru, validasi liveness/capability/mutex, dan gunakan ID yang sama untuk UI, preflight dan createSession. Bila auto-switch dibutuhkan, perbarui selection serta tampilkan perubahan secara eksplisit.
- **Verifikasi ulang:** Dua collector dengan ordering list berubah; start harus memakai yang ditampilkan/dipilih. Selected offline/unsupported menghasilkan pesan yang jelas dan tidak diam-diam mengganti perangkat.
- **Keyakinan:** Tinggi untuk ketidaksesuaian callsite; reproduksi interaktif multi-host tidak dilakukan.

## Risiko yang Belum Terverifikasi

Bagian ini bukan daftar kerentanan/cacat yang sudah terbukti end-to-end. Dugaan berikut membutuhkan bukti tambahan sebelum penetapan dampak/keparahan final.

| ID | Dugaan beralasan dan lokasi | Yang belum diketahui / pemeriksaan tambahan |
|---|---|---|
| R-01 | Native WiFi memakai array interface berukuran satu lalu mengakses berdasarkan dwNumberOfItems (`collector/app/adapters/wifi_windows.py:41–46,231–235`); call WlanScan langsung diikuti query BSS (`237–247`). | Perilaku pada Windows dengan beberapa interface, ABI ctypes, driver throttling dan umur cache hasil. Perlu fixture Win32 yang valid serta pengujian host Windows uji; hasil native/calibrated/fresh tidak disertifikasi oleh audit ini. |
| R-02 | Klasifikasi BLE address diduga menganggap tipe address cukup dari bit string (`collector/app/adapters/ble_adapter.py:40–63`); sumber aktual/metadata address type tidak diteruskan. | Ketepatan terhadap public/random address dan UUID address platform tertentu. Perlu metadata backend Bleak serta corpus perangkat/platform, bukan menebak identitas dari string. |
| R-03 | Setter setActiveSession sendiri mempertahankan association, hosts dan recommendation (`frontend/lib/store.ts:129–150`); J-03 membuktikan perilaku tersebut. | Dampak pada alur normal belum terbukti karena semua callsite start saat ini melakukan resetLiveState terlebih dahulu. Tidak dihitung sebagai temuan tersendiri. Perlu test recovery/switch/history sebelum menambah jalur penggantian sesi. |
| R-04 | STREAM_BACKEND=redis di Compose tidak dibaca mesin stream yang hanya in-memory (`docker-compose.yml:44–45`; `backend/app/core/stream_engine.py:9–22,97`). Command queues juga in-memory (`collector_service.py:19–21`). | Tidak ada deployment multi-worker/restart yang diuji. Publikasi, replay dan command recovery lintas proses berisiko tidak konsisten; jangan menganggap Redis yang berjalan sudah menyediakan sinkronisasi. Perlu uji dua worker dan restart terkontrol atau pembatasan eksplisit satu proses. |
| R-05 | Ekspor materialisasi seluruh measurements ke memory/file_content dan list_targets menjalankan query per target (`export_service.py:35–55`; `session_manager.py:625–655`); fanout WebSocket menunggu send tiap subscriber (`stream_engine.py:61–65`). | Batas dataset, latensi subscriber, kebutuhan memori dan throughput nyata belum diukur. Perlu benchmark sintetis lokal dan batas operasional sebelum menyatakan DoS/performa produksi bermasalah. |
| R-06 | CSV menulis session name/hostname sebagai cell tanpa sanitasi formula (`export_service.py:154`; `association_service.py:518–524`). | Evaluasi formula tergantung spreadsheet client dan cara import. Perlu fixture teks aman pada spreadsheet uji; tidak dilakukan payload berbahaya atau klaim eksploitasi. |

Tidak ada secret produksi aktif yang diverifikasi. Nilai yang ditemukan pada source/config adalah default/template; tidak dilakukan pengecekan validitas kredensial ke layanan mana pun. Kepatuhan WCAG 2.2 AA pada README juga belum diverifikasi melalui audit aksesibilitas.

## Pengujian dan Pemeriksaan

### Lingkungan dan dependensi

Linux, Python **3.12.14**, Node **24.19.0**. Frontend Dockerfile menggunakan Node 20; hasil build lokal tidak otomatis membuktikan seluruh perilaku image Node 20.

Requirements Python dan package.json tidak mematok hasil resolusi. Kombinasi utama yang benar-benar diuji adalah:

| Komponen | Versi audit |
|---|---|
| FastAPI / Pydantic / pydantic-settings | 0.142.2 / 2.13.5 / 2.15.0 |
| SQLAlchemy / aiosqlite | 2.1.3 / 0.22.1 |
| Greenlet | 3.5.6; tambahan audit setelah kegagalan import awal |
| HTTPX / pytest / pytest-asyncio | 0.28.1 / 9.1.1 / 1.4.0 |
| Bleak / NumPy / SciPy | 3.0.2 / 2.3.5 / 1.17.0 |
| Next.js / React / TypeScript | 15.5.27 / 19.3.0 / 5.9.3 |
| Vitest / Zustand | 3.2.7 / 5.0.15 |

### Perintah dan hasil

Alias path pemeriksaan: `SRC` adalah clone lokal `SignalScanner-review`; `CHECK` adalah direktori sementara `qa-checks`; `PY` adalah interpreter venv audit. Alias ini hanya mempersingkat tabel, bukan environment variable proyek.

| Pemeriksaan/perintah yang dijalankan | Hasil | Arti/batas |
|---|---|---|
| `git ls-remote https://github.com/Zaikhul/SignalScanner.git refs/heads/main` | Berhasil; SHA 823ec1a… | Identitas main pada saat akses |
| `git clone --single-branch --branch main --no-tags … SignalScanner-review` | Berhasil | Membaca repository; tidak push atau edit source |
| `git rev-parse HEAD`, `git branch --show-current`, `git log`, `git diff --stat 79c1b40..HEAD`, `git ls-files`, `rg`, `nl -ba` | Berhasil | Inventaris, riwayat, bukti baris dan penelusuran kode |
| `python3 -m venv --system-site-packages qa-runtime` lalu `PY -m pip install --disable-pip-version-check --only-binary=:all: -r SRC/backend/requirements.txt -r SRC/collector/requirements.txt` | Instalasi berhasil | Wheel/dependensi; tidak menjalankan daemon/hardware |
| `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=SRC/backend:SRC PY` untuk import `app.main` | Gagal awal karena greenlet tidak ada | F-04; bukan syntax error |
| `PY -m pip install --disable-pip-version-check --only-binary=:all: greenlet` | Berhasil | Suplementasi hanya di venv audit; source tidak diperbaiki |
| `ast.parse` seluruh berkas `.py` | 56 berkas, nol syntax error | Hanya sintaks, bukan kebenaran runtime |
| `PYTHONDONTWRITEBYTECODE=1 PY -m pytest backend/tests collector/tests -v -p no:cacheprovider` dari SRC | Exit 4; backend/tests tidak ditemukan; nol tests | Suite README tidak tersedia; tidak dinyatakan lulus |
| `npm install --ignore-scripts --no-audit --no-fund --prefix CHECK/frontend` | Berhasil; 116 packages added | Pada salinan frontend; package lifecycle scripts dinonaktifkan |
| `npm test` dari CHECK/frontend | Exit 1; No test files found | Vitest terpasang, tetapi suite tidak ada |
| `npm run lint` dari CHECK/frontend | Exit 1; meminta konfigurasi ESLint | Tidak ada pemeriksaan lint non-interaktif yang selesai |
| `NEXT_TELEMETRY_DISABLED=1 npm run build` dari CHECK/frontend | Exit 0; compiled; tujuh halaman statis | Build frontend berhasil; bukan container/e2e/security test |
| `./node_modules/.bin/tsc --noEmit --incremental false` dari CHECK/frontend | Exit 0, tanpa diagnostic | Pemeriksaan TypeScript berhasil |
| `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=SRC/backend:SRC PY CHECK/reproduce.py` | Final run exit 0; 19 observasi | ASGITransport, database memory, MockTransport/stub; tanpa live network |
| `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=SRC/backend:SRC PY CHECK/reproduce_extra.py` | Final run exit 0; enam observasi | Config handoff, band, SDR unavailable, schema memory dan timestamp |
| `TZ=Asia/Jakarta node CHECK/reproduce_frontend.cjs` | Exit 0; lima observasi | Kode TypeScript asli ditranspilasi dan dijalankan dengan fetch stub; tanpa browser/hardware |
| `git status --porcelain --untracked-files=all` sesudah pemeriksaan | Kosong | Source clone tetap tidak berubah |

Script reproduksi dibuat sebagai alat audit sementara di luar clone. Assertions mengonfirmasi **perilaku bermasalah yang diamati**, sehingga exit 0 pada script tersebut **tidak berarti aplikasi lulus QA**. Satu eksekusi awal harness berhenti karena benturan nama argumen pada helper laporan; helper diperbaiki dan final run selesai. Error harness itu tidak dihitung sebagai bug proyek.

### Katalog observasi lokal

| Observasi | Parameter/hasil yang dapat direproduksi | Temuan terkait |
|---|---|---|
| V-01 | Anonymous register/list/create/start/ingest berhasil; CORS menerima origin sintetis asing | F-01 |
| V-02, V-18 | Dua batch identik → empat event; satu row queue + dua drain → dua request | F-06 |
| V-03 | Outer sequence -8, inner 999/identitas berbeda → 200 | F-09 |
| V-04 | limit satu memotong empat row sequence sama; cursor berikut melewatkan sisanya | F-10 |
| V-05 | pause 200, ingest 400; command tidak menghentikan/ack adapter stub | F-11 |
| V-06 | Dua stop → dua manifest; read 500; completed dapat start lagi | F-12 |
| V-07 | Dua collector memakai local ID adapter sama → satu row dengan ownership A/metadata B | F-25 |
| V-08 | RSSI -40, width 40 → max_rssi -90, score 98 | F-08 |
| V-09 | After nol sampel → teks penurunan 55 dB | F-18 |
| V-10 | [-90,-90,-30] → median API -70 | F-22 |
| V-11 | mask_ssid true → display_name tetap utuh | F-20 |
| V-12 | Manifest DB sintetis berubah tanpa checksum baru → diterima | F-19 |
| V-13, dua kasus | Ampersand pada SSID/password → XML gagal parse | F-14 |
| V-14 | Daemon override URL berbeda dari uploader settings URL | F-15 |
| V-15 | Agent preflight/disconnect anonymous berhasil; body forget_profile=false efektif tetap true | F-02; catatan kontrak di bawah |
| V-16 | Cache EMA -90 lalu raw -30 pada target sama → -69 | F-23 |
| V-17, X-04 | Mock collector/source unknown; SDR tidak tersedia → random bins/source soapysdr_rx | F-07 |
| J-01, J-02, X-02 | Local fetch gagal/400 tidak throw; command backend memulai task tanpa password | F-13 |
| J-03 | Setter session sendiri mempertahankan data sesi lama; alur start normal melakukan reset | R-03, bukan temuan tambahan |
| J-04 | Snapshot count satu + replay event yang sama → count dua | F-24 |
| J-05, X-06 | UTC suffix hilang; Jakarta membaca usia 25.201 detik alih-alih satu detik | F-26 |
| X-01 | Duration/radio config tersimpan, tetapi parameter command null/run_scan tidak menerima config | F-17 |
| X-03 | Sampel 6 GHz kanal 1 memengaruhi instability evaluasi 2.4 GHz kanal 1 | F-18 |
| X-05 | init_db pada tabel lama sintetis tidak menambah scan_id | F-27 |

**Catatan kontrak yang teramati, tidak diberi ID risiko terpisah:** `frontend/lib/apiClient.ts:205–212` mengirim `forget_profile` dalam JSON, sedangkan `collector/app/main.py:440–442` mendeklarasikannya sebagai query parameter. V-15 dengan body false tetap memanggil disconnect menggunakan true. Backend queue mempunyai parameter yang benar, tetapi direct call yang sudah menghapus profil tidak dapat membatalkan penghapusan tersebut. Selaraskan transport/body model dan tambahkan kasus save-profile/forget-profile pada perbaikan alur asosiasi F-13. UI disconnect saat ini memang memanggil true, sehingga dampak permintaan false dari UI normal belum ditunjukkan.

### Pemeriksaan yang tidak dijalankan

- **Docker Compose/build image:** Docker tidak tersedia. Ketidaksesuaian COPY F-05 bersumber dari instruksi Dockerfile dan isi builder hasil build, bukan log Docker rekaan.
- **PostgreSQL/TimescaleDB, Redis dan migrasi database sungguhan:** tidak tersedia layanan uji; seluruh operasi database dinamis memakai data sintetis. Tidak menjalankan `backend/scripts/test_postgres_connection.py` karena script tersebut menginisialisasi schema dan menulis ke database yang dikonfigurasi (`61–104`).
- **Runner keseluruhan dan daemon hardware:** tidak dijalankan karena akan membuka server/subprocess dan dapat mengubah jaringan/hardware host. Fungsi tertentu diuji dengan dependency mock; `run.py` ditinjau statis.
- **WiFi association, bounded LAN probe, BLE scan dan SDR nyata:** tidak dijalankan. Tidak ada ping/ARP scan/netsh connect terhadap jaringan pengguna atau pihak lain.
- **Browser e2e, TLS, Private Network Access, aksesibilitas, throughput dan reconnect lintas proses:** tidak diuji; reproduksi store/helper tidak diklaim sebagai browser e2e.
- **Vulnerability advisory/dependency audit lengkap:** tidak dijalankan. Versi yang disebut adalah versi audit, bukan daftar kerentanan.

## Rekomendasi Prioritas

| Urutan | Tindakan konkret | ID | Kriteria selesai |
|---|---|---|---|
| P0 | Lindungi operator/collector/WS dan local agent; batasi publikasi layanan data | F-01–F-03 | Anonymous/foreign principal ditolak; local pairing berlaku; database/Redis internal tidak terbuka tanpa kebutuhan |
| P0 | Pulihkan clean install dan packaging Docker | F-04–F-05 | Import/startup berhasil dari requirements saja; image frontend berhasil dibangun dari checkout bersih |
| P1 | Pastikan sumber pengukuran aktual dan correctness input analitik | F-07–F-08, F-17–F-18, F-26 | Hardware unavailable tidak menghasilkan data hardware palsu; RSSI/width/window/timezone sesuai observasi |
| P1 | Perbaiki idempotensi, kontrak sequence dan lifecycle | F-06, F-09–F-12, F-19, F-24 | Retry/reconnect/stop ulang tidak menggandakan data; pagination lengkap; manifest valid dan dapat dibaca |
| P1 | Perbaiki alur asosiasi dan konfigurasi lintas proses | F-13–F-16 | Satu eksekusi association, error terlihat, XML valid, semua komponen memakai endpoint yang dikonfigurasi |
| P2 | Tegakkan privasi, statistik dan isolation multi-sesi/multi-collector | F-20–F-23, F-25, F-29 | Mask/key scope berlaku; median/EMA benar; ownership perangkat dan pilihan UI konsisten |
| P2, prasyarat rilis berulang | Lacak suite/lock/lint dan verifikasi upgrade database | F-27–F-28 | Clean CI dapat menguji perbaikan di atas, build image, dan upgrade schema tanpa kehilangan data |

Setelah perbaikan P0/P1, lakukan penerimaan pada **lingkungan uji terisolasi** dengan Windows/WiFi, BLE dan SDR yang benar-benar didukung, dua collector, outage terkontrol, restart backend dan database persisten. Keputusan rilis sebaiknya didasarkan pada kriteria selesai tersebut, bukan hanya status build.

## Kesimpulan

SignalScanner mempunyai struktur monorepo dan jalur frontend yang dapat dibangun, tetapi trust boundary, integritas pengukuran dan sejumlah kontrak runtime belum konsisten. Ketiadaan suite test yang dapat dijalankan memperbesar risiko regresi pada area tersebut. Temuan paling mendesak adalah kontrol tanpa autentikasi, konfigurasi layanan data, penghambat setup/deployment, duplikasi data, serta pengukuran sintetis dan rekomendasi kanal yang salah.

Laporan ini merupakan audit kode/config dan reproduksi lokal pada satu commit. Hasilnya cukup untuk menetapkan pekerjaan perbaikan yang spesifik, tetapi **tidak menyertifikasi keamanan produksi, akurasi hardware, dukungan semua platform, atau kualitas seluruh alur end-to-end**. Evaluasi ulang harus menguji perbaikan pada commit baru dan mencatat lingkungan/versi dependensi yang digunakan.

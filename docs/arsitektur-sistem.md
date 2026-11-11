# Arsitektur Sistem — SENTINEL
Kartika Cyber Hackathon 2026 · Kategori Siber Sosial

## 1. Masalah
Operasi pengaruh di media sosial Indonesia memakai puluhan akun palsu yang memposting narasi
yang sama secara serentak agar terlihat seperti opini publik (astroturfing). Contoh yang relevan
bagi TNI AD: **hoaks/penipuan rekrutmen "jalur khusus" yang mencatut nama TNI AD**, disinformasi
yang memicu kepanikan publik, dan phishing berkedok program pemerintah. Analis kewalahan karena
alat monitoring biasa hanya menunjukkan *volume*, sehingga tidak bisa membedakan
**viral organik** dan **viral rekayasa**.

## 2. Prinsip desain
1. **Behavior-based** — yang dinilai adalah *cara* akun bertindak (serentak, berulang, seragam), bukan isi opini.
2. **Explainable** — setiap skor punya alasan & bukti; bisa dipertanggungjawabkan ke pimpinan.
3. **Ringan & on-premise** — tanpa GPU/internet; cocok untuk jaringan tertutup satuan. 1.700 post diproses ±0,3 detik.
4. **Human-in-the-loop** — sistem memberi rekomendasi; analis memutuskan (flagged → reviewed/escalated/dismissed).

## 3. Pipeline deteksi (`src/detection_engine.py`)

| # | Tahap | Implementasi | Alasan |
|---|---|---|---|
| 1 | Normalisasi | NFKC (huruf unicode "fancy" `𝐆𝐀𝐌𝐄𝟏𝟗𝟏` → `game191`), angka dekoratif `➋➐` → `27`, semua aksara dipertahankan (Thai, Arab, …), hapus URL/emoji, kamus slang (`yg→yang`, `gak→tidak`) | Operator dan spammer judol sengaja memvariasikan ejaan |
| 2 | Representasi teks | TF-IDF `char_wb` n-gram 3–5, sublinear TF | Tahan typo/parafrase ringan, tanpa model besar |
| 3 | Co-action | Sliding window ≤ 20 menit, O(n·k): cosine ≥ 0,60, URL ternormalisasi sama, atau target promosi langka sama (tagar, mention, kode merek; dipakai ≤ 40 akun). Kode merek dicocokkan lewat kunci skeleton (`VlKlNG27` = `VIKING27`); kata ulang (`laki2`) dan satuan (`5kg`) dikecualikan | Koordinasi = aksi yang hampir bersamaan |
| 4 | Graf koordinasi | Bobot edge = jumlah **episode** co-action terpisah (> 40 menit); episode hanya-tagar = 0,5; edge dipakai bila bobot ≥ 2. Pengulangan **level motif**: episode-episode yang berbagi target kuat (mention/kode/URL) atau templat mirip (cosine templat ≥ 0,40) membentuk motif; motif ≥ 2 gelombang & ≥ 3 akun → semua akunnya terhubung | Satu kebetulan/event viral tidak cukup; operasi selalu berulang, di level pasangan atau kelompok |
| 5 | Clustering | Louvain (networkx) + 2-core | Memisahkan operasi berbeda, membuang akun yang "nyangkut" via 1 edge |
| 5b | Operasi templat | Graf bipartit templat ↔ target; operasi bila ≥ 3 akun, ≥ 2 target yang masing-masing didorong ≥ 2 akun, dan ada rotasi (satu templat → ≥ 2 merek, atau satu merek ← ≥ 2 templat) | Spam judol "tetes lambat" yang tersebar berhari-hari tanpa keserempakan; kutipan/meme organik (1 target, 1 templat) tidak lolos |
| 6 | Scoring | 5 sinyal 0–1 berbobot (lihat bawah) | Skor transparan & dapat di-tuning |
| 7 | Persistensi | SQLite: campaigns, campaign_accounts, campaign_posts, campaign_edges, detection_runs | Bukti terhubung ke campaign; run idempoten; keputusan analis dipertahankan |

### Sinyal skor
| Sinyal | Bobot | Cara hitung |
|---|---|---|
| Keseragaman narasi | 30 % | Rata-rata cosine antar post bukti dari akun berbeda, dikalibrasi 0,15→0 dan 0,75→1 |
| Sinkronisasi waktu | 25 % | 65 % × proporsi post yang punya pasangan akun lain ≤ 10 menit + 35 % × jumlah gelombang/4 |
| Anomali profil akun | 20 % | Umur akun < 90 hari, follower < 50, rasio following/follower > 10, username generik+angka, narasi berulang |
| Kepadatan jaringan | 15 % | 60 % densitas graf + 40 % rata-rata episode per pasangan/4 |
| Amplifikasi | 10 % | Proporsi post bukti yang membawa tagar/URL dominan |

Bila mayoritas anggota tidak punya data profil (mis. data komentar), sinyal akun tidak dipakai dan bobot
lain dinormalisasi ulang. Untuk operasi templat: keseragaman = porsi post yang templatnya dipakai ≥ 2 akun,
waktu = ½ × persistensi lintas hari (tanpa bukti keserempakan), amplifikasi = porsi post yang mendorong target.

Risiko: **TINGGI** ≥ 0,75 · **SEDANG** ≥ 0,55 (di-flag) · **RENDAH** < 0,55 (dismissed otomatis).

## 4. Data
- `src/data_ingestion.py` — generator skenario sintetis berlabel (3 operasi + ~1.300 post organik +
  event viral gempa sebagai *hard negative*), parameter `difficulty` untuk stress-test.
- Loader CSV/JSON/JSONL dengan pemetaan kolom otomatis (format ekspor X/Twitter, Reddit, TikTok scraper umum).

## 5. Evaluasi
- **Data asli** (`docs/uji-data-asli.md`): komentar TikTok Indonesia, label manual, set held-out dengan kode
  dibekukan. SENTINEL F1 94 % (precision 100 %) vs duplicate filter 18 % dan burst monitor 8 %. Juga uji
  Cresci-2017 beserta kegagalannya.
- **Sintetis** (`src/evaluation.py`, `docs/benchmark.md`): precision/recall/F1 level akun, 5 seed × 3 tingkat
  kesulitan; dipakai sebagai pagar regresi.

## 6. Dashboard (`app/dashboard.py`)
Alur analis mengikuti pola tools CIB profesional: antrean ancaman → berkas kasus → tindakan.
1. **Ancaman** — status ancaman, 4 angka kunci, timeline organik vs terkoordinasi, antrean kasus terurut skor (klik untuk membuka kasus).
2. **Kasus** — skor dan kontribusi 5 sinyal, *barcode* sinkronisasi akun × waktu, temuan, tab Bukti (cari, unduh CSV + hash SHA-256), Jaringan (penggerak/penguat), Akun (avatar inisial buatan, umur akun, indikator anomali), Tindakan dan laporan.
3. **Profil akun** — lembar konteks per akun (`src/buzzer.py`): identitas, ritme, pola konten, kewajaran interaksi, keterlibatan jaringan, peta jam aktivitas 7×24, cek akun TikTok live. Skor per akun bersifat indikatif (tidak lolos uji Cresci-2017); bukti yang tervalidasi adalah keanggotaan dalam operasi.
4. **Sumber data** — Data live (ScrapeCreators: TikTok, YouTube, X, Threads, Instagram; Mastodon gratis) dengan Indeks Potensi Viral dan akun tunggal mencurigakan, skenario demo, unggah file, parameter deteksi.
5. **Metodologi** — pipeline, benchmark sintetis, dan hasil uji data asli.

Tema gelap "ruang komando": netral grafit, satu aksen amber untuk hal terpenting, merah hanya untuk risiko tinggi, IBM Plex Sans + Mono, ikon garis Material. Metode desain: unslop (Damir Sokolovsky, CC BY 4.0).

## 7. Pengembangan lanjutan (realistis)
- Konektor data: X/Twitter API, YouTube comment, TikTok, Telegram channel publik.
- Jendela koordinasi adaptif & deteksi *slow-burn* (operasi yang menyebar jadwal berhari-hari).
- Embedding semantik Bahasa Indonesia (IndoBERT/sentence-transformers) sebagai opsi untuk parafrase berat.
- Deteksi gambar/meme duplikat (perceptual hash).
- Mode near-real-time (stream per 5 menit) + notifikasi ke analis.
- RBAC & audit log untuk penggunaan multi-analis di satuan.

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
| 1 | Normalisasi | Lowercase, hapus URL/emoji, kamus slang (`yg→yang`, `gak→tidak`, `udh→sudah`, …) | Operator sengaja memvariasikan ejaan |
| 2 | Representasi teks | TF-IDF `char_wb` n-gram 3–5, sublinear TF | Tahan typo/parafrase ringan, tanpa model besar |
| 3 | Co-action | Sliding window ≤ 20 menit, O(n·k): cosine ≥ 0,60, URL ternormalisasi sama, atau tagar langka sama (dipakai ≤ 40 akun) | Koordinasi = aksi yang hampir bersamaan |
| 4 | Graf koordinasi | Bobot edge = jumlah **episode** co-action terpisah (> 40 menit); episode hanya-tagar = 0,5; edge dipakai bila bobot ≥ 2 | Satu kebetulan/event viral tidak cukup; operasi selalu berulang |
| 5 | Clustering | Louvain (networkx) + 2-core | Memisahkan operasi berbeda, membuang akun yang "nyangkut" via 1 edge |
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

Risiko: **TINGGI** ≥ 0,75 · **SEDANG** ≥ 0,55 (di-flag) · **RENDAH** < 0,55 (dismissed otomatis).

## 4. Data
- `src/data_ingestion.py` — generator skenario sintetis berlabel (3 operasi + ~1.300 post organik +
  event viral gempa sebagai *hard negative*), parameter `difficulty` untuk stress-test.
- Loader CSV/JSON/JSONL dengan pemetaan kolom otomatis (format ekspor X/Twitter, Reddit, TikTok scraper umum).

## 5. Evaluasi (`src/evaluation.py`)
Precision/recall/F1 level akun terhadap ground truth, 5 seed × 3 tingkat kesulitan, dibandingkan
dengan baseline *burst monitor* dan *duplicate filter*. Hasil: `docs/benchmark.md`.

## 6. Dashboard (`app/dashboard.py`)
1. **Ringkasan Situasi** — KPI, timeline organik vs terkoordinasi + penanda lonjakan, kartu campaign prioritas.
2. **Investigasi Campaign** — radar 5 sinyal, tabel kontribusi skor, temuan berbahasa Indonesia,
   *barcode* sinkronisasi akun×waktu, graf hub/amplifier, konten bukti (cari & unduh CSV),
   profil akun (histogram tanggal pembuatan), triage + catatan analis, **Laporan Intelijen** (Markdown).
3. **Peta Jaringan** — seluruh jaringan koordinasi berwarna per campaign.
4. **Data & Deteksi** — muat skenario (seed/kesulitan), unggah dataset sendiri, tuning parameter.
5. **Evaluasi Akurasi** — benchmark interaktif.
6. **Metodologi**.

## 7. Pengembangan lanjutan (realistis)
- Konektor data: X/Twitter API, YouTube comment, TikTok, Telegram channel publik.
- Jendela koordinasi adaptif & deteksi *slow-burn* (operasi yang menyebar jadwal berhari-hari).
- Embedding semantik Bahasa Indonesia (IndoBERT/sentence-transformers) sebagai opsi untuk parafrase berat.
- Deteksi gambar/meme duplikat (perceptual hash).
- Mode near-real-time (stream per 5 menit) + notifikasi ke analis.
- RBAC & audit log untuk penggunaan multi-analis di satuan.

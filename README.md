# 🛡️ SENTINEL — Deteksi Operasi Pengaruh Terkoordinasi di Ruang Siber Sosial

**Kartika Cyber Hackathon 2026 · Kategori: Siber Sosial**

🔗 **Demo online:** https://sentinel-kartika-cyber.streamlit.app/

SENTINEL membantu analis siber TNI AD menemukan **jaringan akun yang bergerak terorkestrasi**
(buzzer, sockpuppet, bot) yang menyebarkan hoaks, penipuan, atau disinformasi — misalnya
**hoaks rekrutmen "jalur khusus" yang mencatut nama TNI AD**, astroturfing tagar
yang memicu kepanikan, dan phishing berkedok bansos.

Berbeda dengan dashboard monitoring biasa (yang hanya menghitung volume/sentimen),
SENTINEL mendeteksi **perilaku terkoordinasi** (*Coordinated Inauthentic Behavior*) dan
**menjelaskan alasannya** dalam Bahasa Indonesia, lengkap dengan bukti dan laporan siap kirim.

| | Dashboard monitoring biasa | **SENTINEL** |
|---|---|---|
| Yang dideteksi | Lonjakan volume / sentimen | **Jaringan akun yang bertindak serentak & berulang** |
| Event viral organik (mis. gempa) | Ikut ter-flag (false positive) | **Tidak di-flag** — tidak ada koordinasi berulang |
| Variasi teks, huruf unicode "fancy", homoglyph | Lolos filter duplikat | **Tertangkap** (NFKC + char n-gram + kunci skeleton) |
| Output | Grafik | **Campaign + skor + alasan + bukti + laporan intelijen** |
| F1 pada **komentar TikTok asli** (held-out, label manual) | 8–18 % | **94 %** (precision 100 %, 0 akun dituduh salah) |

## 💡 Kebaruan

1. **Tidak butuh data latih, justru itu kekuatannya.** Model ber-label (seperti Botometer) hanya mengenali
   pola yang pernah dilihat dan membawa bias pelabelnya. SENTINEL menilai *perilaku* (serentak, berulang,
   seragam), sehingga langsung bekerja pada narasi baru hari ini, dan netral terhadap isi opini.
2. **Kriteria "koordinasi berulang".** Dua akun baru dianggap terhubung bila ber-co-action di ≥2 episode
   terpisah. Ini yang membedakan viral rekayasa dari viral organik (uji: berita gempa tidak ter-flag).
3. **Tiga pola operasi nyata**: gelombang serentak, motif yang berulang lintas gelombang (templat + kode
   merek berganti), dan operasi templat "tetes lambat" berhari-hari tanpa keserempakan. Ketiganya
   ditemukan di spam judi online asli di TikTok Indonesia.
4. **Dibuat untuk medsos Indonesia**: slang (`yg`, `gak`), kata ulang (`laki2`), huruf unicode "fancy"
   (`𝐆𝐀𝐌𝐄𝟏𝟗𝟏`), angka dekoratif (`➋➐`), dan homoglyph (`VlKlNG27` = `VIKING27`).
5. **Diuji di data asli, termasuk kegagalannya**: dari **0 tertangkap** pada versi awal ke F1 94 % pada
   komentar TikTok held-out, dengan setiap perbaikan diuji ulang pada data segar. Skor per akun **tidak**
   lolos uji Cresci-2017 dan kami nyatakan terbuka. Lihat [docs/uji-data-asli.md](docs/uji-data-asli.md).
6. **Siap operasi**: data live TikTok/YouTube/X/Threads/Instagram, Indeks Potensi Viral, hash SHA-256 bukti
   (*chain of custody*), laporan intelijen, keputusan analis tercatat.

## ⚡ Menjalankan (± 1 menit)

```bash
./run.sh
```

atau manual:

```bash
pip install -r requirements.txt
python src/data_ingestion.py        # muat dataset skenario (sintetis berlabel)
python src/detection_engine.py      # jalankan deteksi
streamlit run app/dashboard.py      # buka http://localhost:8501
```

Tanpa browser: `python app/dashboard_cli.py` · Laporan: `python app/dashboard_cli.py --report CMP-XXXXXX`
Benchmark akurasi: `python src/evaluation.py` · Tes: `python -m pytest -q`

### 🌐 Data asli (live)
Halaman **Sumber data → Data live** menarik post publik terbaru berdasarkan kata kunci/tagar, menghitung
**Indeks Potensi Viral**, lalu menjalankan deteksi koordinasi pada data nyata.
- **Mastodon**: gratis, tanpa API key.
- **TikTok, X, Threads, YouTube, Instagram** via [ScrapeCreators](https://scrapecreators.com): isi
  `SCRAPECREATORS_API_KEY` di `.streamlit/secrets.toml` (lokal) atau di *Settings → Secrets* (Streamlit Cloud).
- **Mode Presentasi** (aktif secara default) menyamarkan username dan tidak menyimpan avatar/URL.

Data nyata (CSV/JSON/JSONL dengan kolom `text`, `username`, `created_at`, opsional
`user_created_at`, `followers_count`) bisa diunggah dari halaman **Sumber data → Unggah file** atau:
`python src/data_ingestion.py --file data/raw/dataset.csv`

## 🧠 Cara kerja

```
Post medsos ─► Normalisasi (NFKC, slang, homoglyph) ─► TF-IDF char n-gram ─► Co-action (≤20 menit):
                                                    • narasi mirip  • URL sama  • tagar/mention/kode merek langka sama
          ┌───────────────────────────────────────────────────────────┘
          ▼
 Graf koordinasi akun (edge hanya jika BERULANG: pasangan ≥2 episode, atau motif sama ≥2 gelombang)
          ▼
 + Operasi templat "tetes lambat" (templat ↔ kode merek berputar, tanpa keserempakan)
          ▼
 Louvain community detection + k-core ─► kandidat campaign
          ▼
 Skor 5 sinyal (konten 30% · timing 25% · profil akun 20% · jaringan 15% · amplifikasi 10%)
          ▼
 Dashboard: Ancaman (antrean terurut) → Kasus (barcode sinkronisasi, bukti + hash SHA-256, jaringan, akun) → tindakan & laporan
```

Detail: [docs/arsitektur-sistem.md](docs/arsitektur-sistem.md) · Uji data asli: [docs/uji-data-asli.md](docs/uji-data-asli.md) · Benchmark sintetis: [docs/benchmark.md](docs/benchmark.md)

## 📈 Hasil uji

**Data asli** — komentar TikTok Indonesia, held-out (kode dibekukan sebelum data ditarik), 2.002 komentar,
69 akun spam judol berlabel manual:

| Metode | Precision | Recall | F1 | Akun dituduh salah |
|---|---|---|---|---|
| **SENTINEL** | **100 %** | **88 %** | **94 %** | **0** |
| Duplicate filter | 13 % | 28 % | 18 % | 124 |
| Burst monitor | 4 % | 99 % | 8 % | 1.617 |

Di seluruh 8.000+ komentar asli yang diuji, tidak ada akun organik yang dituduh; slogan politik yang
diulang banyak akun tidak di-flag tanpa bukti koordinasi. Batas yang ditemukan (Cresci-2017): bot
retweet yang tidak serentak baru tertangkap 29 %, dan kerumunan asli yang menjawab satu akun pemancing
bisa memicu alarm palsu. Detail: [docs/uji-data-asli.md](docs/uji-data-asli.md).

**Skenario sintetis berlabel** (pagar regresi, 5 seed × 3 tingkat penyamaran):

| Kesulitan | SENTINEL F1 | Burst monitor F1 | Duplicate filter F1 |
|---|---|---|---|
| 0.0 (normal) | **100 %** | 22 % | 36 % |
| 0.5 | **100 %** | 18 % | 35 % |
| 1.0 (operator sangat rapi) | **95 %** (precision 100 %) | 16 % | 34 % |

## 📁 Struktur

```
src/   config.py · database.py · data_ingestion.py · feature_extraction.py
       detection_engine.py · buzzer.py · evaluation.py · report.py · connectors.py
app/   dashboard.py (Streamlit) · dashboard_cli.py
tests/ test_pipeline.py · test_connectors.py (17 tes)
data/  raw/sample_social_posts.csv · processed/detection.db
docs/  arsitektur-sistem.md · uji-data-asli.md · benchmark.md
proposal/ SENTINEL-proposal.pdf · slides/ SENTINEL-slides.pdf · video/ naskah-video.md
assets/ thumbnail.png · screenshots/ (5 tangkapan layar)
```

## ⚖️ Etika & kepatuhan
- Menilai **perilaku**, bukan opini/afiliasi politik → menjaga netralitas institusi.
- Demo memakai **data sintetis**: seluruh akun, nomor, URL fiktif (tidak ada data pribadi pihak ketiga — sesuai rulebook & UU PDP).
- Human-in-the-loop: skor adalah rekomendasi, keputusan tetap di tangan analis.
- Library pihak ketiga open-source: pandas, numpy, scikit-learn, networkx, streamlit, plotly.
- Desain antarmuka mengikuti metode [unslop](https://github.com/heydamir/unslop) oleh Damir Sokolovsky (CC BY 4.0).

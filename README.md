# 🛡️ SENTINEL — Deteksi Operasi Pengaruh Terkoordinasi di Ruang Siber Sosial

**Kartika Cyber Hackathon 2026 · Kategori: Siber Sosial**

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
| Variasi teks/typo operator | Lolos filter duplikat | **Tertangkap** (char n-gram + normalisasi slang) |
| Output | Grafik | **Campaign + skor + alasan + bukti + laporan intelijen** |
| F1-score (benchmark) | 22–36 % | **100 % (normal), 95 % (operator rapi)** |

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

Data nyata (CSV/JSON/JSONL dengan kolom `text`, `username`, `created_at`, opsional
`user_created_at`, `followers_count`) bisa diunggah dari halaman **📥 Data & Deteksi** atau:
`python src/data_ingestion.py --file data/raw/dataset.csv`

## 🧠 Cara kerja

```
Post medsos ─► Normalisasi slang ─► TF-IDF char n-gram ─► Co-action (≤20 menit):
                                                           • narasi mirip  • URL sama  • tagar langka sama
          ┌───────────────────────────────────────────────────────────┘
          ▼
 Graf koordinasi akun (edge hanya jika co-action BERULANG ≥2 episode)
          ▼
 Louvain community detection + k-core ─► kandidat campaign
          ▼
 Skor 5 sinyal (konten 30% · timing 25% · profil akun 20% · jaringan 15% · amplifikasi 10%)
          ▼
 Dashboard: ringkasan · investigasi (radar, barcode sinkronisasi, graf, bukti) · triage · laporan
```

Detail: [docs/arsitektur-sistem.md](docs/arsitektur-sistem.md) · Hasil uji: [docs/benchmark.md](docs/benchmark.md)

## 📈 Hasil benchmark (5 seed × 3 tingkat kesulitan)

| Kesulitan | SENTINEL F1 | Burst monitor F1 | Duplicate filter F1 |
|---|---|---|---|
| 0.0 (normal) | **100 %** | 22 % | 36 % |
| 0.5 | **95 %** | 18 % | 35 % |
| 1.0 (operator sangat rapi) | **68 %** (precision tetap 100 %) | 16 % | 34 % |

Precision tetap 100 % di semua tingkat: sistem **tidak pernah menuduh akun organik**, termasuk saat
ada event viral (gempa) yang memicu lonjakan besar. Penurunan recall pada tingkat 1.0 adalah
keterbatasan yang kami ungkap secara jujur dan menjadi bahan pengembangan (jendela adaptif).

## 📁 Struktur

```
src/   config.py · database.py · data_ingestion.py · feature_extraction.py
       detection_engine.py · evaluation.py · report.py
app/   dashboard.py (Streamlit) · dashboard_cli.py
tests/ test_pipeline.py (8 tes)
data/  raw/sample_social_posts.csv · processed/detection.db
docs/  arsitektur-sistem.md · benchmark.md
```

## ⚖️ Etika & kepatuhan
- Menilai **perilaku**, bukan opini/afiliasi politik → menjaga netralitas institusi.
- Demo memakai **data sintetis**: seluruh akun, nomor, URL fiktif (tidak ada data pribadi pihak ketiga — sesuai rulebook & UU PDP).
- Human-in-the-loop: skor adalah rekomendasi, keputusan tetap di tangan analis.
- Library pihak ketiga open-source: pandas, numpy, scikit-learn, networkx, streamlit, plotly.

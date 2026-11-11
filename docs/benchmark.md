# Hasil Benchmark Deteksi (akun-level)

Dibuat otomatis oleh `python src/evaluation.py` — 5 seed per tingkat kesulitan.

| Kesulitan | Metode | Precision | Recall | F1 |
|---|---|---|---|---|
| 0.0 | SENTINEL | 100.0% | 100.0% | 100.0% |
| 0.0 | Baseline A (burst monitor) | 17.2% | 32.6% | 22.5% |
| 0.0 | Baseline B (duplicate filter) | 22.1% | 96.8% | 36.0% |
| 0.5 | SENTINEL | 100.0% | 100.0% | 100.0% |
| 0.5 | Baseline A (burst monitor) | 13.3% | 26.3% | 17.6% |
| 0.5 | Baseline B (duplicate filter) | 21.3% | 92.6% | 34.7% |
| 1.0 | SENTINEL | 100.0% | 90.0% | 94.6% |
| 1.0 | Baseline A (burst monitor) | 12.3% | 24.2% | 16.3% |
| 1.0 | Baseline B (duplicate filter) | 21.0% | 90.5% | 34.1% |

## Buzzer detector per akun (HANYA data sintetis)

Tanpa sinyal jaringan, ambang skor 25: precision 99.4%, recall 88.4%, F1 93.6%.

**Tidak berlaku di data asli**: pada Cresci-2017 AUC lensa ini 0,32–0,55 (tidak lebih baik dari acak). Lihat [uji-data-asli.md](uji-data-asli.md) untuk hasil pada data asli.

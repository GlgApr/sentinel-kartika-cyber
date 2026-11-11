# Evaluation Module
# SENTINEL · Kartika Cyber Hackathon 2026
#
# Mengukur akurasi deteksi secara OBJEKTIF terhadap ground-truth dataset
# sintetis, dan membandingkannya dengan dua baseline yang umum dipakai
# dashboard monitoring biasa:
#   - Baseline A "Burst monitor": flag semua akun yang posting di jam lonjakan
#   - Baseline B "Duplicate filter": flag akun yang memposting teks identik
#     dengan akun lain (exact match setelah lowercase)
#
# Jalankan:  python src/evaluation.py            (5 seed x 3 tingkat kesulitan)

import argparse
import tempfile
from collections import defaultdict
from pathlib import Path

from config import Config
from data_ingestion import generate_synthetic_dataset
from detection_engine import DetectionEngine
from feature_extraction import FeatureExtractor, parse_ts


def prf(pred, truth):
    tp = len(pred & truth)
    p = tp / len(pred) if pred else 0.0
    r = tp / len(truth) if truth else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {"precision": p, "recall": r, "f1": f, "tp": tp, "fp": len(pred - truth), "fn": len(truth - pred)}


def baseline_burst(posts):
    starts, series = FeatureExtractor.hourly_activity(posts)
    bursts = FeatureExtractor.detect_bursts(starts, series)
    hours = {b["window_start"][:13] for b in bursts}
    out = set()
    t0 = starts[0] if starts else None
    for p in posts:
        t = parse_ts(p["timestamp"])
        bucket = t0 + (t - t0) // (starts[1] - starts[0]) * (starts[1] - starts[0]) if len(starts) > 1 else t
        if bucket.isoformat()[:13] in hours:
            out.add(p["account_id"])
    return out


def baseline_duplicate(posts):
    by_text = defaultdict(set)
    for p in posts:
        by_text[p["content"].strip().lower()].add(p["account_id"])
    return {a for accs in by_text.values() if len(accs) >= 2 for a in accs}


class _MemDB:
    """DB in-memory minimal agar evaluasi tidak menyentuh database dashboard."""

    def __init__(self, posts, accounts):
        self.posts, self.accounts = posts, {a["account_id"]: a for a in accounts}

    def get_all_posts(self):
        return self.posts

    def get_accounts(self):
        return self.accounts


def evaluate_once(seed=42, difficulty=0.0):
    posts, accounts = generate_synthetic_dataset(seed=seed, difficulty=difficulty)
    truth = {a["account_id"] for a in accounts if a["metadata"]["label"].startswith("OP-")}
    label = {a["account_id"]: a["metadata"]["label"] for a in accounts}

    engine = DetectionEngine(db=_MemDB(posts, accounts))
    campaigns = engine.detect(posts, engine.db.get_accounts())
    flagged = [c for c in campaigns if c["flag_score"] >= Config.FLAG_THRESHOLD]
    pred = {a for c in flagged for a in c["accounts"]}

    # per-operasi: berapa % akun operasi tertangkap & apakah satu operasi = satu campaign
    per_op = {}
    for op in {l for l in label.values() if l.startswith("OP-")}:
        members = {a for a, l in label.items() if l == op}
        per_op[op] = len(members & pred) / len(members)

    return {
        "SENTINEL": prf(pred, truth),
        "Baseline A (burst monitor)": prf(baseline_burst(posts), truth),
        "Baseline B (duplicate filter)": prf(baseline_duplicate(posts), truth),
        "per_op_recall": per_op,
        "n_campaigns_flagged": len(flagged),
        "n_ops": len(per_op),
    }


def evaluate_buzzer(seeds=(1, 7, 42, 99, 2026), threshold=25):
    """Lensa per akun TANPA sinyal jaringan (independen dari detection engine)."""
    from buzzer import analyze_account
    tp = fp = fn = 0
    for s in seeds:
        posts, accounts = generate_synthetic_dataset(seed=s)
        by = defaultdict(list)
        for p in posts:
            by[p["account_id"]].append(p)
        for a in accounts:
            m = a["metadata"]
            score = analyze_account({"username": a["account_id"], **m}, by[a["account_id"]], None)["score"]
            truth, pred = m["label"].startswith("OP-"), score >= threshold
            tp += truth and pred
            fp += pred and not truth
            fn += truth and not pred
    p = tp / max(tp + fp, 1)
    r = tp / max(tp + fn, 1)
    return {"precision": p, "recall": r, "f1": 2 * p * r / max(p + r, 1e-9)}


def run_benchmark(seeds=(1, 7, 42, 99, 2026), difficulties=(0.0, 0.5, 1.0)):
    rows = []
    for d in difficulties:
        agg = defaultdict(lambda: defaultdict(list))
        for s in seeds:
            r = evaluate_once(seed=s, difficulty=d)
            for m in ("SENTINEL", "Baseline A (burst monitor)", "Baseline B (duplicate filter)"):
                for k in ("precision", "recall", "f1"):
                    agg[m][k].append(r[m][k])
        for m, ks in agg.items():
            rows.append({"difficulty": d, "method": m,
                         **{k: sum(v) / len(v) for k, v in ks.items()}})
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="1 seed saja")
    args = ap.parse_args()
    seeds = (42,) if args.quick else (1, 7, 42, 99, 2026)
    rows = run_benchmark(seeds=seeds)
    print(f"\nBenchmark akun-level ({len(seeds)} seed per tingkat kesulitan)\n")
    print(f"{'kesulitan':>9} | {'metode':32} | {'precision':>9} | {'recall':>7} | {'F1':>6}")
    print("-" * 75)
    for r in rows:
        print(f"{r['difficulty']:>9.1f} | {r['method']:32} | {r['precision']:>9.2%} | {r['recall']:>7.2%} | {r['f1']:>6.2%}")
    bz = evaluate_buzzer(seeds=seeds)
    print(f"\nBuzzer detector per akun (tanpa sinyal jaringan): precision {bz['precision']:.1%}, "
          f"recall {bz['recall']:.1%}, F1 {bz['f1']:.1%}")
    out = Path(__file__).resolve().parent.parent / "docs" / "benchmark.md"
    with open(out, "w") as f:
        f.write("# Hasil Benchmark Deteksi (akun-level)\n\n")
        f.write(f"Dibuat otomatis oleh `python src/evaluation.py` — {len(seeds)} seed per tingkat kesulitan.\n\n")
        f.write("| Kesulitan | Metode | Precision | Recall | F1 |\n|---|---|---|---|---|\n")
        for r in rows:
            f.write(f"| {r['difficulty']:.1f} | {r['method']} | {r['precision']:.1%} | {r['recall']:.1%} | {r['f1']:.1%} |\n")
        f.write(f"\n## Buzzer detector per akun\n\nTanpa sinyal jaringan, ambang skor 25: precision "
                f"{bz['precision']:.1%}, recall {bz['recall']:.1%}, F1 {bz['f1']:.1%}.\n")
    print(f"\nTabel disimpan ke {out}")

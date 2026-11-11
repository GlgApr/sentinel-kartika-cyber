# Unit & integration tests — jalankan: python -m pytest -q
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from config import Config  # noqa: E402
from data_ingestion import generate_synthetic_dataset, ingest, load_dataframe  # noqa: E402
from database import Database  # noqa: E402
from detection_engine import DetectionEngine  # noqa: E402
from evaluation import evaluate_once  # noqa: E402
from feature_extraction import normalize_text  # noqa: E402
from report import campaign_brief  # noqa: E402


@pytest.fixture
def db(tmp_path):
    d = Database(str(tmp_path / "t.db"))
    posts, accounts = generate_synthetic_dataset(seed=42)
    ingest(posts, accounts, d)
    yield d
    d.close()


def test_normalize_slang():
    assert normalize_text("BBM udh naik yg bener gak??") == "bbm sudah naik yang benar tidak"
    assert "bit" not in normalize_text("cek bit.ly/abc sekarang")


def test_detects_all_operations_without_false_positive():
    r = evaluate_once(seed=42)
    assert r["SENTINEL"]["precision"] >= 0.95
    assert r["SENTINEL"]["recall"] >= 0.95
    assert r["n_campaigns_flagged"] == r["n_ops"]  # 1 operasi = 1 campaign


def test_beats_baselines():
    r = evaluate_once(seed=7)
    assert r["SENTINEL"]["f1"] > r["Baseline A (burst monitor)"]["f1"] + 0.3
    assert r["SENTINEL"]["f1"] > r["Baseline B (duplicate filter)"]["f1"] + 0.3


def test_organic_viral_event_not_flagged(db):
    camps = DetectionEngine(db).run_detection_pipeline(verbose=False)
    acc = db.get_accounts()
    for c in camps:
        if c["status"] == "flagged":
            labels = {acc[a]["metadata"]["label"] for a in c["accounts"]}
            assert labels != {"organic"}


def test_pipeline_is_idempotent_and_keeps_triage(db):
    eng = DetectionEngine(db)
    eng.run_detection_pipeline(verbose=False)
    first = db.get_campaigns()
    db.update_campaign_status(first[0]["campaign_id"], "escalated", "sudah dilaporkan")
    eng.run_detection_pipeline(verbose=False)
    second = db.get_campaigns()
    assert len(second) == len(first)  # tidak menumpuk duplikat
    c = db.get_campaign_by_id(first[0]["campaign_id"])
    assert c["status"] == "escalated" and c["analyst_note"] == "sudah dilaporkan"


def test_campaign_evidence_and_report(db):
    DetectionEngine(db).run_detection_pipeline(verbose=False)
    c = db.get_campaigns()[0]
    posts = db.get_posts_by_campaign(c["campaign_id"])
    accs = db.get_campaign_accounts(c["campaign_id"])
    assert len(posts) == c["post_count"] and len(accs) == c["account_count"]
    assert db.get_campaign_edges(c["campaign_id"])
    md = campaign_brief(c, accs, posts)
    assert c["campaign_id"] in md and "Rekomendasi" in md


def test_load_generic_csv_columns():
    df = pd.DataFrame({
        "username": ["a", "b"], "full_text": ["halo #Tes bit.ly/x", "hai"],
        "created_at": ["2026-11-01T10:00:00Z", "2026-11-01T10:05:00Z"], "followers_count": [10, 20]})
    posts, accounts = load_dataframe(df)
    assert len(posts) == 2 and posts[0]["hashtags"] == ["#Tes"] and posts[0]["urls"]
    assert accounts[0]["metadata"]["followers"] == 10


def test_scoring_weights_sum_to_one():
    assert abs(sum(Config.SCORING_WEIGHTS.values()) - 1.0) < 1e-9


def test_buzzer_lens_separates_operations_without_network():
    from evaluation import evaluate_buzzer
    r = evaluate_buzzer(seeds=(42,))
    assert r["precision"] >= 0.95 and r["recall"] >= 0.8


def test_buzzer_flags_scheduled_copypasta_bot():
    from buzzer import analyze_account
    posts = [{"timestamp": f"2026-11-0{1 + i // 24}T{i % 24:02d}:00:00", "content": "BBM naik besok #BBMNaikBesok #a #b #c"}
             for i in range(30)]
    r = analyze_account({"username": "netizen_88231", "created_at": "2026-10-25", "followers": 3, "following": 900,
                         "bio": ""}, posts, [])
    assert r["score"] >= 50 and r["verdict"] in ("Bot atau akun otomatis", "Akun spam atau promosi")

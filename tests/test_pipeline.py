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


def test_promoted_entities_real_world_tricks():
    from feature_extraction import promoted_entities
    # huruf unicode "fancy" & mention dinormalisasi ke kode merek yang sama
    assert "game191" in promoted_entities({"content": "@𝐆𝐀𝐌𝐄𝟏𝟗𝟏🤎❤"})
    assert promoted_entities({"content": "XV99 คืออะไรหรอค่ะ💜"}) == {"xv99"}
    # homoglyph & angka dekoratif: tiga ejaan ini merek yang sama
    assert promoted_entities({"content": "@VlKlNG27_ happy"}) == promoted_entities({"content": "@𝐕𝐈𝐊𝐈𝐍𝐆➋➐_ hi"}) == {"viking27"}
    # kata ulang & satuan Indonesia BUKAN kode merek
    assert promoted_entities({"content": "laki2 tiba2 beli beras 5kg 80rb"}) == set()


def test_motif_links_slot_spam_across_waves_but_not_slogans(tmp_path):
    """Pola spam komentar asli: tiap akun muncul sekali, kode merek berganti,
    tapi templatnya berulang di beberapa gelombang -> satu operasi.
    Slogan organik tanpa target promosi tidak boleh ter-flag."""
    from evaluation import _MemDB
    posts, n = [], 0
    waves = [("2026-11-05T15:0", "MMM5", ["a1", "a2", "a3"]), ("2026-11-05T23:2", "XV99", ["b1", "b2", "b3"]),
             ("2026-11-06T00:1", "8DDD", ["c1", "c2"]), ("2026-11-07T11:1", "XV99", ["d1", "d2"])]
    for t0, code, accs in waves:
        for k, a in enumerate(accs):
            posts.append({"post_id": f"p{n}", "account_id": a, "content": f"@{code} คืออะไรหรอ🫶🫶",
                          "timestamp": f"{t0}{k}:00", "hashtags": [], "urls": []}); n += 1
    for t0 in ("2026-11-05T10:0", "2026-11-06T10:0", "2026-11-07T10:0"):
        for k, a in enumerate(["s1", "s2", "s3"]):
            posts.append({"post_id": f"p{n}", "account_id": f"{a}{t0[9]}", "content": "nkri harga mati",
                          "timestamp": f"{t0}{k}:00", "hashtags": [], "urls": []}); n += 1
    accs = [{"account_id": a, "metadata": {}} for a in {p["account_id"] for p in posts}]
    eng = DetectionEngine(db=_MemDB(posts, accs))
    flagged = [c for c in eng.detect(posts, eng.db.get_accounts()) if c["status"] == "flagged"]
    assert len(flagged) == 1
    assert set(flagged[0]["accounts"]) == {"a1", "a2", "a3", "b1", "b2", "b3", "c1", "c2", "d1", "d2"}


def test_slow_drip_template_operation_without_sync():
    """Spam judol 'tetes lambat': berhari-hari, tidak serentak, templat diulang sambil
    memutar kode merek. Kutipan meme (1 target, 1 templat) tidak boleh ter-flag."""
    from evaluation import _MemDB
    tpl = ["@{} MAIN SANTAI AJA BG, YANG PENTING ADA SENSASI PECAH🥰", "@{} Yang penting bukti nyata boss🔥"]
    plan = [("SENJA57", 0), ("SENJA57", 1), ("PANDA40", 0), ("PANDA40", 1), ("PETIR84", 0), ("SENJA57", 0)]
    posts = [{"post_id": f"s{i}", "account_id": f"spam{i}", "content": tpl[t].format(code),
              "timestamp": f"2026-10-{10 + 3 * i:02d}T0{i}:00:00", "hashtags": [], "urls": []}
             for i, (code, t) in enumerate(plan)]
    posts += [{"post_id": f"m{i}", "account_id": f"fan{i}", "content": "@akun_kutipan: aku cinta negeri ini tapi masa depanku belum jelas",
               "timestamp": f"2026-10-{11 + 4 * i:02d}T10:00:00", "hashtags": [], "urls": []} for i in range(4)]
    accs = [{"account_id": a, "metadata": {}} for a in {p["account_id"] for p in posts}]
    eng = DetectionEngine(db=_MemDB(posts, accs))
    flagged = [c for c in eng.detect(posts, eng.db.get_accounts()) if c["status"] == "flagged"]
    assert len(flagged) == 1 and flagged[0]["pattern"] == "template"
    assert set(flagged[0]["accounts"]) == {f"spam{i}" for i in range(6)}

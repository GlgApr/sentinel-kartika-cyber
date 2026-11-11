# Database helper — SQLite
# SENTINEL · Kartika Cyber Hackathon 2026

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from config import Config

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    post_id    TEXT PRIMARY KEY,
    platform   TEXT,
    account_id TEXT,
    content    TEXT,
    timestamp  TEXT,
    hashtags   TEXT,          -- JSON list
    urls       TEXT,          -- JSON list
    mentions   TEXT,          -- JSON list
    metadata   TEXT           -- JSON (mis. label ground-truth untuk data sintetis)
);
CREATE INDEX IF NOT EXISTS idx_posts_ts ON posts(timestamp);
CREATE INDEX IF NOT EXISTS idx_posts_acc ON posts(account_id);

CREATE TABLE IF NOT EXISTS accounts (
    account_id TEXT PRIMARY KEY,
    platform   TEXT,
    metadata   TEXT,          -- JSON: username, created_at, followers, following, label
    features   TEXT           -- JSON: fitur hasil ekstraksi
);

CREATE TABLE IF NOT EXISTS campaigns (
    campaign_id    TEXT PRIMARY KEY,
    run_id         TEXT,
    detected_at    TEXT,
    description    TEXT,
    flag_score     REAL,
    risk_level     TEXT,
    status         TEXT,       -- flagged / reviewed / dismissed / escalated
    topic_keywords TEXT,
    account_count  INTEGER,
    post_count     INTEGER,
    first_seen     TEXT,
    last_seen      TEXT,
    signals        TEXT,       -- JSON {content, timing, account, network, amplification}
    signal_summary TEXT,       -- penjelasan human-readable (JSON list of str)
    analyst_note   TEXT
);

CREATE TABLE IF NOT EXISTS campaign_accounts (
    campaign_id TEXT,
    account_id  TEXT,
    role        TEXT,          -- hub / amplifier
    degree      REAL,
    PRIMARY KEY (campaign_id, account_id)
);

CREATE TABLE IF NOT EXISTS campaign_posts (
    campaign_id TEXT,
    post_id     TEXT,
    PRIMARY KEY (campaign_id, post_id)
);

CREATE TABLE IF NOT EXISTS campaign_edges (
    campaign_id TEXT,
    source      TEXT,
    target      TEXT,
    weight      REAL,
    evidence    TEXT           -- JSON: jenis co-action (content/url/hashtag)
);

CREATE TABLE IF NOT EXISTS detection_runs (
    run_id      TEXT PRIMARY KEY,
    started_at  TEXT,
    duration_s  REAL,
    post_count  INTEGER,
    account_count INTEGER,
    campaign_count INTEGER,
    params      TEXT
);
"""


def _dumps(v):
    return json.dumps(v, ensure_ascii=False) if v is not None else None


def _loads(v, default=None):
    if v in (None, ""):
        return default
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return default


class Database:
    def __init__(self, db_path=None):
        self.db_path = db_path or Config.DATABASE_PATH
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: Streamlit menjalankan callback di thread berbeda
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._migrate_legacy()
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def _migrate_legacy(self):
        """Skema versi lama tidak punya kolom baru — drop tabel campaign lama."""
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(campaigns)")}
        if cols and "signals" not in cols:
            self.conn.execute("DROP TABLE campaigns")
        pcols = {r[1] for r in self.conn.execute("PRAGMA table_info(posts)")}
        if pcols and "urls" not in pcols:
            self.conn.execute("DROP TABLE posts")
            self.conn.execute("DROP TABLE IF EXISTS accounts")
        self.conn.commit()

    # ------------------------------------------------------------------ ingest
    def reset_data(self):
        for t in ("posts", "accounts", "campaigns", "campaign_accounts",
                  "campaign_posts", "campaign_edges", "detection_runs"):
            self.conn.execute(f"DELETE FROM {t}")
        self.conn.commit()

    def insert_posts(self, posts, platform="sample"):
        rows = [(
            p["post_id"], p.get("platform", platform), p["account_id"], p["content"],
            str(p["timestamp"]), _dumps(p.get("hashtags") or []), _dumps(p.get("urls") or []),
            _dumps(p.get("mentions") or []), _dumps(p.get("metadata") or {}),
        ) for p in posts]
        self.conn.executemany(
            "INSERT OR REPLACE INTO posts VALUES (?,?,?,?,?,?,?,?,?)", rows)
        self.conn.commit()

    def insert_accounts(self, accounts, platform="sample"):
        rows = [(a["account_id"], a.get("platform", platform), _dumps(a.get("metadata") or {}),
                 _dumps(a.get("features"))) for a in accounts]
        self.conn.executemany("INSERT OR REPLACE INTO accounts VALUES (?,?,?,?)", rows)
        self.conn.commit()

    # Kompatibilitas API lama
    def insert_post(self, post_id, platform, account_id, content, timestamp,
                    hashtags=None, mentions=None, metadata=None, urls=None):
        self.insert_posts([dict(post_id=post_id, platform=platform, account_id=account_id,
                                content=content, timestamp=timestamp, hashtags=hashtags,
                                mentions=mentions, metadata=metadata, urls=urls)])

    def insert_account(self, account_id, platform, metadata=None, features=None):
        self.insert_accounts([dict(account_id=account_id, platform=platform,
                                   metadata=metadata, features=features)])

    # ------------------------------------------------------------------ read
    def get_all_posts(self, limit=None):
        q = "SELECT * FROM posts ORDER BY timestamp"
        rows = self.conn.execute(q + (" LIMIT ?" if limit else ""), (limit,) if limit else ())
        out = []
        for r in rows:
            d = dict(r)
            d["hashtags"] = _loads(d["hashtags"], [])
            d["urls"] = _loads(d["urls"], [])
            d["mentions"] = _loads(d["mentions"], [])
            d["metadata"] = _loads(d["metadata"], {})
            out.append(d)
        return out

    def get_accounts(self):
        out = {}
        for r in self.conn.execute("SELECT * FROM accounts"):
            d = dict(r)
            d["metadata"] = _loads(d["metadata"], {})
            d["features"] = _loads(d["features"], {})
            out[d["account_id"]] = d
        return out

    def count(self, table):
        return self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    # ------------------------------------------------------------------ campaigns
    def save_detection_run(self, run, campaigns):
        """Simpan hasil 1 run deteksi. Run sebelumnya dihapus (idempoten),
        tapi status & catatan analis untuk campaign yang sama dipertahankan."""
        prev = {r["fingerprint"]: (r["status"], r["analyst_note"]) for r in self.conn.execute(
            "SELECT topic_keywords AS fingerprint, status, analyst_note FROM campaigns")}
        for t in ("campaigns", "campaign_accounts", "campaign_posts", "campaign_edges", "detection_runs"):
            self.conn.execute(f"DELETE FROM {t}")
        self.conn.execute("INSERT INTO detection_runs VALUES (?,?,?,?,?,?,?)", (
            run["run_id"], run["started_at"], run["duration_s"], run["post_count"],
            run["account_count"], len(campaigns), _dumps(run.get("params"))))
        for c in campaigns:
            status, note = c["status"], None
            if c["topic_keywords"] in prev and prev[c["topic_keywords"]][0] in ("reviewed", "escalated", "dismissed"):
                status, note = prev[c["topic_keywords"]]
            self.conn.execute(
                "INSERT INTO campaigns VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                    c["campaign_id"], run["run_id"], run["started_at"], c["description"],
                    c["flag_score"], c["risk_level"], status, c["topic_keywords"],
                    len(c["accounts"]), len(c["posts"]), c["first_seen"], c["last_seen"],
                    _dumps(c["signals"]), _dumps(c["explanations"]), note))
            self.conn.executemany("INSERT INTO campaign_accounts VALUES (?,?,?,?)",
                                  [(c["campaign_id"], a, c["roles"].get(a, "amplifier"),
                                    c["degrees"].get(a, 0)) for a in c["accounts"]])
            self.conn.executemany("INSERT INTO campaign_posts VALUES (?,?)",
                                  [(c["campaign_id"], p) for p in c["posts"]])
            self.conn.executemany("INSERT INTO campaign_edges VALUES (?,?,?,?,?)",
                                  [(c["campaign_id"], e["source"], e["target"], e["weight"],
                                    _dumps(e["evidence"])) for e in c["edges"]])
        self.conn.commit()

    def _campaign_row(self, r):
        d = dict(r)
        d["signals"] = _loads(d["signals"], {})
        d["signal_summary"] = _loads(d["signal_summary"], [])
        return d

    def get_campaigns(self, score_threshold=0.0, status_list=None, limit=500):
        q = "SELECT * FROM campaigns WHERE flag_score >= ?"
        params = [score_threshold]
        if status_list:
            q += f" AND status IN ({','.join('?' * len(status_list))})"
            params.extend(status_list)
        q += " ORDER BY flag_score DESC LIMIT ?"
        params.append(limit)
        return [self._campaign_row(r) for r in self.conn.execute(q, params)]

    def get_campaign_by_id(self, campaign_id):
        r = self.conn.execute("SELECT * FROM campaigns WHERE campaign_id=?", (campaign_id,)).fetchone()
        return self._campaign_row(r) if r else None

    def get_campaign_accounts(self, campaign_id):
        rows = self.conn.execute("""
            SELECT ca.account_id, ca.role, ca.degree, a.metadata
            FROM campaign_accounts ca LEFT JOIN accounts a USING(account_id)
            WHERE ca.campaign_id=? ORDER BY ca.degree DESC""", (campaign_id,))
        out = []
        for r in rows:
            d = dict(r)
            d["metadata"] = _loads(d["metadata"], {})
            out.append(d)
        return out

    def get_posts_by_campaign(self, campaign_id):
        rows = self.conn.execute("""
            SELECT p.* FROM campaign_posts cp JOIN posts p USING(post_id)
            WHERE cp.campaign_id=? ORDER BY p.timestamp""", (campaign_id,))
        out = []
        for r in rows:
            d = dict(r)
            d["hashtags"] = _loads(d["hashtags"], [])
            d["urls"] = _loads(d["urls"], [])
            out.append(d)
        return out

    def get_campaign_edges(self, campaign_id):
        rows = self.conn.execute("SELECT * FROM campaign_edges WHERE campaign_id=?", (campaign_id,))
        return [dict(r, evidence=_loads(r["evidence"], {})) for r in rows]

    def get_all_campaign_accounts(self):
        return [dict(r) for r in self.conn.execute(
            "SELECT campaign_id, account_id, role FROM campaign_accounts")]

    def get_last_run(self):
        r = self.conn.execute("SELECT * FROM detection_runs ORDER BY started_at DESC LIMIT 1").fetchone()
        return dict(r) if r else None

    def update_campaign_status(self, campaign_id, status, note=None):
        self.conn.execute("UPDATE campaigns SET status=?, analyst_note=COALESCE(?, analyst_note) WHERE campaign_id=?",
                          (status, note, campaign_id))
        self.conn.commit()

    # ------------------------------------------------------------------ misc
    def close(self):
        if self.conn:
            self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def now_iso():
    return datetime.now().isoformat(timespec="seconds")

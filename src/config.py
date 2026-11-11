# Kartika Cyber Hackathon 2026 — SENTINEL
# Coordinated Campaign & Astroturfing Detection Platform
# Konfigurasi aplikasi (semua path absolut relatif ke root proyek,
# sehingga aman dijalankan dari direktori mana pun).

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Config:
    APP_NAME = "SENTINEL"
    APP_TAGLINE = "Deteksi Coordinated Inauthentic Behavior di Ruang Siber Sosial"

    # ---------- Paths ----------
    DATABASE_PATH = str(PROJECT_ROOT / "data" / "processed" / "detection.db")
    RAW_DATA_DIR = str(PROJECT_ROOT / "data" / "raw")
    PROCESSED_DATA_DIR = str(PROJECT_ROOT / "data" / "processed")

    # ---------- Content similarity (TF-IDF char n-gram) ----------
    # Char n-gram tahan terhadap variasi ejaan/singkatan khas medsos Indonesia
    # ("yg", "gak", "bgt", typo sengaja) yang dipakai operator untuk mengelabui
    # filter duplikat.
    NGRAM_RANGE = (3, 5)
    SIMILARITY_THRESHOLD = 0.60     # cosine minimum agar dua post dianggap "naratif sama"

    # ---------- Coordination window ----------
    # Dua akun dianggap ber-koordinasi bila memposting konten mirip / URL sama /
    # tagar langka sama dalam rentang waktu ini.
    COORDINATION_WINDOW_MIN = 20
    MIN_EDGE_WEIGHT = 2             # minimal 2 kejadian co-action agar edge dihitung (kurangi kebetulan)
    MIN_CLUSTER_SIZE = 3            # minimal akun per campaign
    RARE_HASHTAG_MAX_ACCOUNTS = 40  # tagar dipakai <= N akun dianggap "langka" (bukan tagar umum)

    # ---------- Burst detection ----------
    BURST_WINDOW_MINUTES = 60
    BURST_Z_SCORE_THRESHOLD = 2.5

    # ---------- Campaign scoring (harus berjumlah 1.0) ----------
    SCORING_WEIGHTS = {
        "content": 0.30,     # keseragaman narasi antar akun
        "timing": 0.25,      # sinkronisasi waktu posting
        "account": 0.20,     # anomali profil akun (umur, follower, pola username)
        "network": 0.15,     # kepadatan jaringan co-action
        "amplification": 0.10,  # konsentrasi tagar/URL yang didorong
    }

    # Ambang flag: >= FLAG_THRESHOLD -> "flagged" (perlu review analis)
    FLAG_THRESHOLD = 0.55
    HIGH_RISK_THRESHOLD = 0.75

    # ---------- Reddit API (opsional, isi via environment variable) ----------
    REDDIT_USER_AGENT = "SentinelCIB/1.0"

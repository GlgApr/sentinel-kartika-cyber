# Feature Extraction Module
# SENTINEL · Kartika Cyber Hackathon 2026
#
# Berisi blok-blok fitur yang dipakai detection engine:
#   - normalisasi teks Bahasa Indonesia informal (slang medsos)
#   - TF-IDF char n-gram untuk kemiripan narasi (tahan typo/variasi ejaan)
#   - deteksi co-action antar akun (konten mirip / URL sama / tagar langka
#     dalam jendela waktu sempit) -> dasar graf koordinasi
#   - burst detection (z-score) untuk timeline
#   - skor anomali profil akun

import math
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from config import Config

URL_RE = re.compile(r"(https?://\S+|\b[\w-]+\.(?:com|id|xyz|net|org|ly|co)/\S*)", re.I)
MULTI_SPACE = re.compile(r"\s+")
MENTION = re.compile(r"@(\w+)")
# huruf dieja terpisah untuk mengelabui filter: "u b e t 9 6" -> "ubet96"
SPACED = re.compile(r"(?<!\S)(?:\w ){2,}\w(?!\S)")
# kode merek/promosi: token campuran huruf+angka (xv99, mmm5, game191, slot88)
CODE = re.compile(r"^(?=[a-z0-9]*[a-z])(?=[a-z0-9]*\d)[a-z0-9]{3,12}$")
# angka + satuan bukan kode merek: 5kg, 80rb, 5jt, 2x, 14pro, 2026an
# kata ulang informal Indonesia bukan kode merek: laki2, orang2, tiba2, bener2
REDUP = re.compile(r"^[a-z]{2,}2$")
UNIT = re.compile(r"^\d+(?:kg|g|gr|rb|ribu|jt|juta|k|m|t|gb|mb|tb|km|cm|mm|ml|l|jam|hari|th|thn|tahun|an|x|pk|am|pm|s|an|nya|pro|max|plus)$")

# Normalisasi slang umum medsos Indonesia -> bentuk baku
SLANG_MAP = {
    "yg": "yang", "gak": "tidak", "ga": "tidak", "nggak": "tidak", "tdk": "tidak", "udah": "sudah",
    "udh": "sudah", "sdh": "sudah", "skrg": "sekarang", "bgt": "banget", "bener": "benar",
    "dgn": "dengan", "utk": "untuk", "krn": "karena", "jg": "juga", "aja": "saja", "dah": "sudah",
    "tau": "tahu", "gk": "tidak", "blm": "belum", "sm": "sama", "dpt": "dapat", "dapet": "dapat",
}

STOPWORDS = set("""yang dan di ke dari untuk dengan ini itu ada pada juga sudah tidak akan atau
saja sama karena jadi lagi kalian kamu aku saya kita mereka sih ya dong deh nya banget aja
udah gak yg bisa mau harus lebih masih tapi kalau kalo biar semua sebelum sekarang besok tadi
jangan buat dalam the a cek info""".split())


def parse_ts(s):
    if isinstance(s, datetime):
        return s
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _keep(ch):
    # pertahankan huruf/angka SEMUA aksara (Latin, Thai, Arab, Jawa, ...) + tanda vokal;
    # buang emoji, simbol, tanda baca
    return ch in "# " or unicodedata.category(ch)[0] in "LMN"


def fold(text):
    """NFKC + angka dekoratif -> angka biasa. 𝐆𝐀𝐌𝐄𝟏𝟗𝟏 -> game191, VIKING➋➐ -> viking27."""
    t = unicodedata.normalize("NFKC", str(text)).lower()
    return "".join(str(unicodedata.digit(ch)) if not ch.isascii() and unicodedata.digit(ch, None) is not None
                   else ch for ch in t)


DISPLAY = {}  # kunci skeleton -> ejaan asli pertama yang terlihat (untuk ditampilkan ke analis)


def skeleton(code):
    """Kunci pembanding kode merek tahan homoglyph: vlklng27 / viking27 -> viking27."""
    key = code.replace("l", "i").replace("|", "i")
    DISPLAY.setdefault(key, code)
    return key


def display_entity(key):
    return DISPLAY.get(key, key)


def normalize_text(text):
    # NFKC: huruf "fancy" unicode (𝐆𝐀𝐌𝐄𝟏𝟗𝟏, ｓｌｏｔ) -> ASCII biasa; trik umum spammer judol
    t = fold(text)
    t = URL_RE.sub(" ", t)
    t = "".join(ch if _keep(ch) else " " for ch in t)
    t = SPACED.sub(lambda m: m.group(0).replace(" ", ""), MULTI_SPACE.sub(" ", t))
    words = [SLANG_MAP.get(w, w) for w in t.split() if any(unicodedata.category(c)[0] in "LN" or c == "#" for c in w)]
    return " ".join(words)


def promoted_entities(post):
    """Target promosi dalam post: tagar, mention, kode merek, dan URL ternormalisasi.
    Operasi selalu MENDORONG sesuatu; ini yang membedakannya dari slogan organik."""
    raw = fold(post.get("content") or "")
    ents = {h.lower() for h in (post.get("hashtags") or [])}
    # mention & kode merek disatukan: "@MMM5" dan "MMM5" adalah target yang sama;
    # kunci skeleton menyamakan homoglyph (VlKlNG27 = VIKING27)
    ents |= {skeleton(m.strip("_")) for m in MENTION.findall(raw)}
    ents |= {skeleton(w) for w in normalize_text(raw).split() if CODE.match(w) and not UNIT.match(w) and not REDUP.match(w)}
    ents |= {"url:" + normalize_url(u) for u in (post.get("urls") or [])}
    return ents


def normalize_url(u):
    u = re.sub(r"^https?://", "", u.lower()).rstrip("/.,!")
    return re.sub(r"^www\.", "", u)


class FeatureExtractor:
    def __init__(self, config=Config):
        self.cfg = config
        self.vectorizer = None
        self.X = None

    # ------------------------------------------------------------------ text
    def fit_text(self, posts):
        """TF-IDF char n-gram (char_wb). Hasil baris sudah ter-normalisasi L2,
        sehingga dot product = cosine similarity."""
        docs = [normalize_text(p["content"]).replace("#", "") for p in posts]
        self.vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=self.cfg.NGRAM_RANGE,
                                          sublinear_tf=True, min_df=1)
        self.X = self.vectorizer.fit_transform(docs).tocsr()
        return self.X

    # ------------------------------------------------------------------ co-action
    def find_coactions(self, posts):
        """Cari pasangan post dari akun berbeda yang ber-co-action dalam jendela waktu.

        posts HARUS sudah terurut waktu dan sejajar dengan matriks self.X.
        Return: dict[(acc_a, acc_b)] -> list event {episode, type, sim, posts}
        Kompleksitas ~ O(n * k) dengan k = jumlah post dalam jendela (sliding window),
        bukan O(n^2) seperti versi lama.
        """
        cfg = self.cfg
        win = cfg.COORDINATION_WINDOW_MIN * 60
        ts = np.array([parse_ts(p["timestamp"]).timestamp() for p in posts])
        accs = [p["account_id"] for p in posts]
        urls = [{normalize_url(u) for u in (p.get("urls") or [])} for p in posts]

        # target promosi langka (tagar, mention, kode merek) — dipakai 2..N akun
        ents_all = [{e for e in promoted_entities(p) if not e.startswith("url:")} for p in posts]
        ent_accounts = defaultdict(set)
        for p, es in zip(posts, ents_all):
            for e in es:
                ent_accounts[e].add(p["account_id"])
        rare = {e for e, s in ent_accounts.items() if 2 <= len(s) <= cfg.RARE_HASHTAG_MAX_ACCOUNTS}
        self.rare_entities = rare
        tags = [es & rare for es in ents_all]

        events = defaultdict(list)
        n = len(posts)
        j_end = 0
        for i in range(n):
            while j_end < n and ts[j_end] - ts[i] <= win:
                j_end += 1
            if j_end - i <= 1:
                continue
            cand = np.arange(i + 1, j_end)
            sims = (self.X[cand] @ self.X[i].T).toarray().ravel()
            for k, j in enumerate(cand):
                if accs[j] == accs[i]:
                    continue
                types, sim = [], float(sims[k])
                if sim >= cfg.SIMILARITY_THRESHOLD:
                    types.append("content")
                if urls[i] & urls[j]:
                    types.append("url")
                shared = tags[i] & tags[j]
                if any(e.startswith("#") for e in shared):
                    types.append("hashtag")
                if any(not e.startswith("#") for e in shared):
                    types.append("entity")
                if not types:
                    continue
                pair = tuple(sorted((accs[i], accs[j])))
                # episode = blok waktu jendela-koordinasi; co-action berulang di
                # episode berbeda adalah sinyal kuat (bukan kebetulan sekali).
                events[pair].append({"t": float(ts[i]), "types": types, "sim": sim,
                                     "posts": (posts[i]["post_id"], posts[j]["post_id"]),
                                     "dt": abs(ts[j] - ts[i])})
        return events

    @staticmethod
    def pair_weight(evts):
        """Bobot edge = jumlah EPISODE co-action yang terpisah waktu.
        Event yang berjarak < 2x jendela koordinasi digabung menjadi satu episode,
        sehingga satu event viral (mis. gempa) hanya dihitung sekali.
        Episode yang hanya berbagi tagar/mention/kode dihitung 0.5 (sinyal lebih lemah)."""
        gap = 2 * Config.COORDINATION_WINDOW_MIN * 60
        ws, last_t, cur = [], None, 0.0
        for e in sorted(evts, key=lambda e: e["t"]):
            w = 1.0 if ("content" in e["types"] or "url" in e["types"]) else 0.5
            if last_t is None or e["t"] - last_t > gap:
                if last_t is not None:
                    ws.append(cur)
                cur = 0.0
            cur, last_t = max(cur, w), e["t"]
            e["episode"] = len(ws)
        ws.append(cur)
        return sum(ws), len(ws)

    # ------------------------------------------------------------------ timing
    @staticmethod
    def hourly_activity(posts, bucket_minutes=None):
        bucket = (bucket_minutes or Config.BURST_WINDOW_MINUTES) * 60
        ts = [parse_ts(p["timestamp"]) for p in posts]
        ts = [t for t in ts if t]
        if not ts:
            return [], []
        t0 = min(ts).timestamp()
        counts = Counter(int((t.timestamp() - t0) // bucket) for t in ts)
        n = max(counts) + 1
        series = [counts.get(i, 0) for i in range(n)]
        starts = [datetime.fromtimestamp(t0 + i * bucket) for i in range(n)]
        return starts, series

    @staticmethod
    def detect_bursts(starts, series, z_thr=None):
        z_thr = z_thr or Config.BURST_Z_SCORE_THRESHOLD
        if len(series) < 3:
            return []
        arr = np.array(series, dtype=float)
        # robust z-score (median/MAD) agar burst besar tidak "menutupi" burst lain
        med = np.median(arr)
        mad = np.median(np.abs(arr - med)) * 1.4826 or arr.std() or 1.0
        z = (arr - med) / mad
        return [{"window_start": starts[i].isoformat(), "activity_count": int(arr[i]),
                 "z_score": round(float(z[i]), 2)} for i in range(len(arr)) if z[i] >= z_thr]

    # ------------------------------------------------------------------ accounts
    @staticmethod
    def account_anomaly(meta, posts_of_acc, ref_time):
        """Skor 0..1 anomali profil akun + alasan. Bekerja walau metadata parsial."""
        score, reasons = 0.0, []
        created = parse_ts(meta.get("created_at")) if meta.get("created_at") else None
        if created:
            age = (ref_time - created).days
            if age < 90:
                score += 0.4
                reasons.append(f"akun baru ({age} hari)")
            elif age < 365:
                score += 0.15
        fol = meta.get("followers")
        fing = meta.get("following")
        if fol is not None:
            if fol < 50:
                score += 0.25
                reasons.append(f"follower sangat sedikit ({fol})")
            if fing is not None and fing / max(fol, 1) > 10:
                score += 0.1
                reasons.append("rasio following/follower ekstrem")
        uname = meta.get("username") or ""
        if re.search(r"\d{3,}$", uname):
            score += 0.15
            reasons.append("pola username generik + angka")
        # perilaku: proporsi post akun yang nyaris identik satu sama lain
        texts = [normalize_text(p["content"]) for p in posts_of_acc]
        if len(texts) >= 3:
            dup = 1 - len(set(t[:40] for t in texts)) / len(texts)
            if dup > 0.3:
                score += 0.1
                reasons.append("mengulang narasi yang sama")
        return min(score, 1.0), reasons

    @staticmethod
    def top_keywords(texts, k=6):
        c = Counter()
        for t in texts:
            for w in normalize_text(t).split():
                if len(w) > 2 and w not in STOPWORDS and not w.isdigit():
                    c[w.lstrip("#")] += 1
        return [w for w, _ in c.most_common(k)]


def sigmoid(x):
    return 1 / (1 + math.exp(-x))

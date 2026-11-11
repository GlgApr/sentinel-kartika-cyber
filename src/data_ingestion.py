# Data Ingestion Module
# SENTINEL · Kartika Cyber Hackathon 2026
#
# 1) generate_synthetic_dataset(): dataset sintetis berlabel (ground truth) yang
#    meniru pola nyata operasi pengaruh di medsos Indonesia. Dipakai untuk demo
#    DAN untuk mengukur akurasi (precision/recall) secara objektif.
#    Seluruh akun, nomor, dan URL FIKTIF — tidak ada data pribadi pihak ketiga
#    (sesuai ketentuan rulebook & UU PDP).
# 2) load_file(): memuat dataset nyata (CSV/JSON/JSONL) dengan pemetaan kolom
#    otomatis (text/content, author/username, created_at/date, dst).

import argparse
import json
import random
import re
from datetime import datetime, timedelta
from pathlib import Path

from database import Database

HASHTAG_RE = re.compile(r"#\w+")
URL_RE = re.compile(r"(https?://\S+|\b[\w-]+\.(?:com|id|xyz|net|org|ly|co)/\S*)", re.I)
MENTION_RE = re.compile(r"@\w+")

BASE_TIME = datetime(2026, 11, 1, 0, 0, 0)
DAYS = 3

# ----------------------------------------------------------------------------- organic
FIRST = ["rina", "budi", "sari", "agus", "dewi", "andi", "putri", "eko", "wulan", "dimas",
         "nadia", "rizky", "fitri", "yoga", "intan", "fajar", "ayu", "hendra", "maya", "bayu",
         "lestari", "arif", "tika", "galih", "indah", "reza", "nisa", "teguh", "citra", "adit"]
LAST = ["santoso", "wulandari", "pratama", "saputra", "lestari", "hidayat", "kurniawan",
        "nugroho", "permata", "siregar", "situmorang", "wijaya", "rahma", "setiawan", "utami"]

ORGANIC_TOPICS = {
    "macet": {
        "tags": ["#InfoJakarta", "#Macet"],
        "lines": ["macet parah di {loc} pagi ini", "udah sejam kejebak di {loc}, ada apa ya",
                  "{loc} padat merayap, mending lewat jalan lain", "tol arah {loc} lumayan lancar sih hari ini",
                  "jam segini {loc} udah kayak parkiran"],
    },
    "beras": {
        "tags": ["#HargaBeras"],
        "lines": ["harga beras di pasar {loc} naik lagi", "beli beras 5kg sekarang hampir {n}rb",
                  "di warung deket rumah beras premium mulai langka", "ibu-ibu di {loc} pada ngeluh harga beras",
                  "semoga harga beras cepet stabil lagi"],
    },
    "bola": {
        "tags": ["#Timnas", "#GarudaMendunia"],
        "lines": ["nonton timnas semalem tegang banget", "lini tengah timnas makin solid ya",
                  "gol kedua tadi keren parah", "pelatih harus rotasi pemain biar gak capek",
                  "nobar di {loc} rame bener"],
    },
    "cuaca": {
        "tags": ["#InfoCuaca"],
        "lines": ["hujan deras dari siang di {loc}", "panas banget hari ini di {loc}",
                  "jangan lupa bawa payung, {loc} mendung", "angin kenceng di {loc}, hati-hati di jalan"],
    },
    "kuliner": {
        "tags": ["#KulinerNusantara"],
        "lines": ["nemu warung soto enak di {loc}", "rekomendasi bakso di {loc} dong",
                  "martabak manis deket kampus {loc} juara", "lagi pengen seblak level 5"],
    },
    "kerja": {
        "tags": [],
        "lines": ["senin lagi, semangat kerja semua", "lembur lagi malam ini",
                  "meeting dari pagi sampe sore capek juga", "akhirnya gajian juga",
                  "wfh hari ini, produktif banget"],
    },
    "teknologi": {
        "tags": ["#Teknologi", "#KeamananSiber"],
        "lines": ["jangan asal klik link di grup WA ya, banyak phishing", "update hp kemarin baterainya jadi boros",
                  "aktifin verifikasi dua langkah di semua akun kalian", "lagi belajar python buat analisis data",
                  "ada yang pernah coba laptop {n} series?"],
    },
}
LOCS = ["Cawang", "Bekasi", "Depok", "Bogor", "Tangerang", "Bandung", "Surabaya", "Medan",
        "Semarang", "Yogyakarta", "Makassar", "Palembang", "Kuningan", "Sudirman", "Pasar Minggu"]
OPENERS = ["", "", "", "duh ", "wkwk ", "gaes, ", "btw ", "jujur ", "aduh ", "eh "]
CLOSERS = ["", "", "", " 😅", " 🙏", " sih", " banget", " ya", " euy", " 😂", " hmm"]

# Hard negative: event organik viral — banyak akun asli memposting topik sama
# pada waktu berdekatan. Sistem yang naif akan salah mem-flag ini.
QUAKE_LINES = ["barusan kerasa gempa di {loc}, kalian aman?", "gempa lumayan kenceng tadi, lampu goyang",
               "semoga semua warga {loc} aman ya", "kaget banget lagi kerja tiba-tiba goyang",
               "info resmi cek BMKG aja jangan percaya hoaks", "anak-anak langsung lari keluar rumah tadi",
               "ada yang tau pusat gempanya dimana?", "doa untuk saudara-saudara di Sukabumi 🙏",
               "gedung kantor di {loc} sempet dievakuasi", "baru sadar ada gempa pas liat grup WA"]
QUAKE_URL = "bmkg.go.id/gempabumi-terkini"

# ----------------------------------------------------------------------------- operations
OPERATIONS = {
    "OP-REKRUT": {
        "desc": "Hoaks & penipuan rekrutmen 'jalur khusus' mencatut nama TNI AD",
        "n_accounts": 12, "name_tpl": ["info_rekrut{d}", "lowongan_resmi{d}", "admin_seleksi{d}"],
        "templates": [
            "PENDAFTARAN {inst} JALUR KHUSUS DIBUKA! kuota terbatas, biaya admin {fee} langsung lulus. info: {url}",
            "dibuka jalur khusus {inst} tanpa tes, cukup bayar admin {fee}. daftar cepat {url}",
            "info valid!! seleksi {inst} jalur khusus, bayar {fee} dijamin lolos. link {url}",
            "kesempatan emas jadi {inst} lewat jalur khusus, admin {fee} aja. buruan {url}",
        ],
        "fill": {"inst": ["Bintara TNI AD", "Tamtama TNI AD", "Bintara AD"], "fee": ["Rp2,5jt", "2.5 juta", "Rp 2.500.000"],
                 "url": ["bit.ly/jalurkhusus-ad", "jalurkhusus-rekrut.xyz/daftar"]},
        "tags": ["#RekrutmenTNI", "#LowonganKerja"],
        "waves": [(0, 9, 5), (1, 8, 40), (1, 20, 0), (2, 10, 15)],  # (hari, jam, menit)
        "wave_spread_min": 8, "posts_per_wave": 1,
    },
    "OP-BBM": {
        "desc": "Astroturfing tagar disinformasi 'BBM naik besok' memicu panic buying",
        "n_accounts": 18, "name_tpl": ["suararakyat{d}", "wargapeduli{d}", "netizen_{d}", "rakyatkecil{d}"],
        "templates": [
            "BBM naik besok pagi, buruan isi full sekarang sebelum telat {tag}",
            "katanya besok bbm naik lagi, antrian spbu udah panjang {tag}",
            "infonya bbm resmi naik mulai besok, siap-siap aja {tag}",
            "besok harga bbm naik drastis, isi tangki kalian sekarang {tag}",
            "bbm naik besok!! sebarkan biar semua tau {tag}",
        ],
        "fill": {"tag": ["#BBMNaikBesok", "#BBMNaikBesok #PanicBuying"]},
        "tags": ["#BBMNaikBesok"],
        "waves": [(1, h, 0) for h in range(10, 22)],  # tiap jam, terjadwal (bot scheduler)
        "wave_spread_min": 6, "posts_per_wave": 1, "participation": 0.75,
    },
    "OP-BANSOS": {
        "desc": "Phishing berkedok pencairan bansos via tautan palsu",
        "n_accounts": 8, "name_tpl": ["bansos_info{d}", "cek_bantuan{d}"],
        "templates": [
            "bansos tahap 4 sudah cair, cek nama penerima disini {url}",
            "cek apakah kamu dapat bansos 2026, isi data di {url}",
            "pencairan bansos {amt} sudah dibuka, verifikasi NIK di {url}",
            "yang belum dapet bansos {amt} cek ulang di {url} sebelum ditutup",
        ],
        "fill": {"url": ["bansos-cair2026.xyz/cek", "cekbansos-resmi.com/nik"], "amt": ["600rb", "Rp600.000"]},
        "tags": ["#Bansos2026"],
        "waves": [(0, 19, 30), (1, 13, 10), (2, 7, 45)],
        "wave_spread_min": 12, "posts_per_wave": 1,
    },
}

SLANG = {"yang": "yg", "tidak": "gak", "sudah": "udah", "sekarang": "skrg", "banget": "bgt", "buruan": "buruan!!"}


def _mutate(text, rng):
    """Variasi ringan ala operator (ganti slang, kapitalisasi, tanda baca) untuk
    menghindari deteksi duplikat persis."""
    words = text.split()
    words = [SLANG.get(w, w) if rng.random() < 0.4 else w for w in words]
    t = " ".join(words)
    r = rng.random()
    if r < 0.2:
        t = t.upper()
    elif r < 0.4:
        t = t.capitalize()
    if rng.random() < 0.3:
        t += rng.choice(["!!", " 🔥", " ‼️", " 👇", "."])
    return t


def _diurnal_time(rng):
    """Waktu posting organik mengikuti ritme harian manusia (puncak pagi/siang/malam)."""
    day = rng.randrange(DAYS)
    hour = rng.choices(range(24), weights=[1, 0.5, 0.3, 0.3, 0.5, 1.5, 3, 5, 6, 5, 4, 4,
                                            6, 5, 4, 4, 5, 6, 6, 7, 8, 8, 6, 3])[0]
    return BASE_TIME + timedelta(days=day, hours=hour, minutes=rng.randrange(60), seconds=rng.randrange(60))


def generate_synthetic_dataset(seed=42, n_organic=160, organic_posts=1300, difficulty=0.0):
    """difficulty 0..1: makin tinggi, operasi makin "rapi" menyamar —
    jeda antar akun lebih lebar, partisipasi per gelombang lebih rendah.
    Dipakai untuk stress-test di evaluation.py."""
    rng = random.Random(seed)
    accounts, posts = [], []

    # ---- organic accounts
    used = set()
    organic_ids = []
    while len(organic_ids) < n_organic:
        name = f"{rng.choice(FIRST)}{rng.choice(['_', '.', ''])}{rng.choice(LAST)}"
        if rng.random() < 0.3:
            name += str(rng.randrange(70, 99))
        if name in used:
            continue
        used.add(name)
        organic_ids.append(name)
        created = datetime(2012, 1, 1) + timedelta(days=rng.randrange(0, 4500))
        accounts.append({"account_id": name, "metadata": {
            "username": name, "created_at": created.date().isoformat(),
            "followers": int(rng.lognormvariate(5.6, 1.1)), "following": int(rng.lognormvariate(5.3, 0.8)),
            "label": "organic"}})

    def add_post(acc, content, ts, label, extra_tags=(), urls=()):
        tags = list(dict.fromkeys(HASHTAG_RE.findall(content) + list(extra_tags)))
        found_urls = list(dict.fromkeys(URL_RE.findall(content) + list(urls)))
        posts.append({"post_id": f"p{len(posts):05d}", "account_id": acc, "content": content,
                      "timestamp": ts.isoformat(timespec="seconds"), "hashtags": tags,
                      "urls": found_urls, "mentions": MENTION_RE.findall(content),
                      "metadata": {"label": label}})

    # ---- organic posts (beragam topik, waktu diurnal)
    for _ in range(organic_posts):
        acc = rng.choice(organic_ids)
        topic = rng.choice(list(ORGANIC_TOPICS))
        spec = ORGANIC_TOPICS[topic]
        line = rng.choice(spec["lines"]).format(loc=rng.choice(LOCS), n=rng.choice([65, 70, 75, 80, 14, 15]))
        content = rng.choice(OPENERS) + line + rng.choice(CLOSERS)
        if spec["tags"] and rng.random() < 0.35:
            content += " " + rng.choice(spec["tags"])
        add_post(acc, content, _diurnal_time(rng), "organic")

    # ---- hard negative: gempa viral organik (hari ke-2, 14:05)
    quake_t = BASE_TIME + timedelta(days=1, hours=14, minutes=5)
    for acc in rng.sample(organic_ids, 70):
        delay = timedelta(minutes=rng.expovariate(1 / 25))  # peluruhan alami, bukan serentak
        content = rng.choice(OPENERS) + rng.choice(QUAKE_LINES).format(loc=rng.choice(LOCS)) + rng.choice(CLOSERS)
        if rng.random() < 0.3:
            content += " #Gempa"
        add_post(acc, content, quake_t + delay, "organic", urls=[QUAKE_URL] if rng.random() < 0.35 else [])

    # ---- coordinated operations
    for op, spec in OPERATIONS.items():
        op_created = datetime(2026, 10, rng.randrange(1, 15))
        op_ids = []
        for i in range(spec["n_accounts"]):
            name = rng.choice(spec["name_tpl"]).format(d=rng.randrange(1000, 9999))
            while name in used:
                name = rng.choice(spec["name_tpl"]).format(d=rng.randrange(1000, 9999))
            used.add(name)
            op_ids.append(name)
            # Sebagian kecil akun = akun lama yang dibajak/dibeli (lebih sulit dideteksi)
            aged = rng.random() < 0.2
            created = (datetime(2019, 1, 1) + timedelta(days=rng.randrange(0, 1500))) if aged \
                else op_created + timedelta(days=rng.randrange(0, 10))
            accounts.append({"account_id": name, "metadata": {
                "username": name, "created_at": created.date().isoformat(),
                "followers": rng.randrange(0, 60) if not aged else rng.randrange(100, 900),
                "following": rng.randrange(300, 2000), "label": op}})
            # beberapa post "kamuflase" agar akun tampak normal
            for _ in range(rng.randrange(1, 4)):
                topic = rng.choice(list(ORGANIC_TOPICS))
                line = rng.choice(ORGANIC_TOPICS[topic]["lines"]).format(loc=rng.choice(LOCS), n=70)
                add_post(name, line, _diurnal_time(rng), "organic_by_" + op)

        for (d, h, m) in spec["waves"]:
            wave_t = BASE_TIME + timedelta(days=d, hours=h, minutes=m)
            for acc in op_ids:
                if rng.random() > spec.get("participation", 1.0) * (1 - 0.4 * difficulty):
                    continue
                tpl = rng.choice(spec["templates"])
                content = tpl.format(**{k: rng.choice(v) for k, v in spec["fill"].items()})
                content = _mutate(content, rng)
                if rng.random() < 0.5:
                    content += " " + rng.choice(spec["tags"])
                ts = wave_t + timedelta(minutes=rng.uniform(0, spec["wave_spread_min"] * (1 + 3 * difficulty)))
                add_post(acc, content, ts, op)

    posts.sort(key=lambda p: p["timestamp"])
    return posts, accounts


# ----------------------------------------------------------------------------- real data loader
COLUMN_ALIASES = {
    "post_id": ["post_id", "id", "tweet_id", "id_str", "status_id", "comment_id"],
    "account_id": ["account_id", "author", "username", "user", "screen_name", "user_screen_name", "author_id", "user_id"],
    "content": ["content", "text", "full_text", "body", "tweet", "message", "caption"],
    "timestamp": ["timestamp", "created_at", "date", "datetime", "time", "created_utc", "posted_at"],
    "account_created_at": ["account_created_at", "user_created_at", "author_created_at"],
    "followers": ["followers", "followers_count", "user_followers_count"],
}


def _pick(cols, key):
    low = {c.lower(): c for c in cols}
    for alias in COLUMN_ALIASES[key]:
        if alias in low:
            return low[alias]
    return None


def _to_iso(v):
    import pandas as pd
    if isinstance(v, (int, float)) and v > 1e9:  # epoch (Reddit created_utc)
        return datetime.utcfromtimestamp(v).isoformat(timespec="seconds")
    ts = pd.to_datetime(v, errors="coerce", utc=True)
    if pd.isna(ts):
        return None
    return ts.tz_convert("Asia/Jakarta").tz_localize(None).isoformat(timespec="seconds")


def load_dataframe(df, platform="upload"):
    """Konversi DataFrame bebas-format menjadi posts + accounts."""
    cols = list(df.columns)
    m = {k: _pick(cols, k) for k in COLUMN_ALIASES}
    missing = [k for k in ("account_id", "content", "timestamp") if not m[k]]
    if missing:
        raise ValueError(f"Kolom wajib tidak ditemukan: {missing}. Kolom tersedia: {cols}")
    posts, accounts = [], {}
    for i, row in df.iterrows():
        text = str(row[m["content"]])
        ts = _to_iso(row[m["timestamp"]])
        if not ts or not text.strip():
            continue
        acc = str(row[m["account_id"]])
        posts.append({
            "post_id": str(row[m["post_id"]]) if m["post_id"] else f"u{i:06d}",
            "account_id": acc, "content": text, "timestamp": ts, "platform": platform,
            "hashtags": HASHTAG_RE.findall(text), "urls": URL_RE.findall(text),
            "mentions": MENTION_RE.findall(text), "metadata": {},
        })
        if acc not in accounts:
            meta = {"username": acc}
            if m["account_created_at"]:
                c = _to_iso(row[m["account_created_at"]])
                meta["created_at"] = c[:10] if c else None
            if m["followers"]:
                try:
                    meta["followers"] = int(row[m["followers"]])
                except (TypeError, ValueError):
                    pass
            accounts[acc] = {"account_id": acc, "platform": platform, "metadata": meta}
    return posts, list(accounts.values())


def load_file(path):
    import pandas as pd
    p = Path(path)
    if p.suffix.lower() == ".csv":
        df = pd.read_csv(p)
    elif p.suffix.lower() in (".jsonl", ".ndjson"):
        df = pd.read_json(p, lines=True)
    elif p.suffix.lower() == ".json":
        df = pd.read_json(p)
    else:
        raise ValueError("Format didukung: .csv, .json, .jsonl")
    return load_dataframe(df, platform=p.stem)


def ingest(posts, accounts, db=None, reset=True):
    db = db or Database()
    if reset:
        db.reset_data()
    db.insert_accounts(accounts)
    db.insert_posts(posts)
    return len(posts), len(accounts)


def ingest_sample_data(db=None, seed=42):
    posts, accounts = generate_synthetic_dataset(seed=seed)
    n, a = ingest(posts, accounts, db)
    print(f"[ingest] {n} post sintetis dari {a} akun dimuat (seed={seed})")
    return posts


def export_sample_csv(path=None, seed=42):
    """Simpan dataset sintetis ke CSV agar juri bisa mencoba fitur upload."""
    import pandas as pd
    posts, accounts = generate_synthetic_dataset(seed=seed)
    meta = {a["account_id"]: a["metadata"] for a in accounts}
    rows = [{"post_id": p["post_id"], "username": p["account_id"], "text": p["content"],
             "created_at": p["timestamp"], "user_created_at": meta[p["account_id"]]["created_at"],
             "followers_count": meta[p["account_id"]]["followers"]} for p in posts]
    path = Path(path or Path(__file__).resolve().parent.parent / "data" / "raw" / "sample_social_posts.csv")
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Muat data ke database SENTINEL")
    ap.add_argument("--file", help="CSV/JSON/JSONL dataset nyata")
    ap.add_argument("--seed", type=int, default=42, help="seed dataset sintetis")
    ap.add_argument("--export-csv", action="store_true", help="ekspor dataset sintetis ke data/raw")
    args = ap.parse_args()
    if args.export_csv:
        print("CSV ditulis ke", export_sample_csv(seed=args.seed))
    elif args.file:
        posts, accounts = load_file(args.file)
        n, a = ingest(posts, accounts)
        print(f"[ingest] {n} post dari {a} akun dimuat dari {args.file}")
    else:
        ingest_sample_data(seed=args.seed)

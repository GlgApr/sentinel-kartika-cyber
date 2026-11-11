# Buzzer Detector — profil risiko per akun
# SENTINEL · Kartika Cyber Hackathon 2026
#
# Melengkapi deteksi jaringan (detection_engine) dengan lensa PER AKUN.
# Tanpa training data: setiap sinyal adalah aturan perilaku yang bisa
# dijelaskan dan diverifikasi analis (bukan black-box). Bobot dinormalisasi
# ulang bila suatu kelompok sinyal tidak punya data (mis. tidak ada views).
#
# Kelompok sinyal:
#   identitas  — umur akun, pola username, bio, ganti nama baru-baru ini, rasio follow
#   ritme      — aktif hampir 24 jam, interval terlalu teratur (terjadwal), frekuensi
#   konten     — narasi berulang, kepadatan tagar/tautan, fokus satu tagar
#   engagement — interaksi tidak wajar dibanding follower/tayangan
#   jejaring   — keanggotaan di campaign terkoordinasi yang terdeteksi

import re
import statistics
from collections import Counter
from datetime import datetime, timedelta, timezone

from feature_extraction import normalize_text, parse_ts

WIB = timezone(timedelta(hours=7))
WEIGHTS = {"identitas": 0.20, "ritme": 0.25, "konten": 0.25, "engagement": 0.15, "jejaring": 0.15}
LABELS = {"identitas": "Identitas akun", "ritme": "Ritme posting", "konten": "Pola konten",
          "engagement": "Kewajaran interaksi", "jejaring": "Keterlibatan jaringan"}
DAYS = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"]


def _cap(x):
    return max(0.0, min(1.0, x))


def _signal_identity(p, ref):
    s, r = 0.0, []
    created = parse_ts(p.get("created_at")) if p.get("created_at") else None
    if created:
        age = (ref - created).days
        if age < 90:
            s += 0.45
            r.append(f"akun baru, dibuat {age} hari lalu")
        elif age < 365:
            s += 0.2
            r.append(f"akun berumur {age} hari")
    uname = (p.get("username") or "").split(":")[-1]
    if re.search(r"\d{3,}$", uname) or re.match(r"^user\d{5,}", uname):
        s += 0.2
        r.append("username generik dengan deret angka")
    if p.get("bio") is not None and not str(p.get("bio")).strip():
        s += 0.1
        r.append("bio kosong")
    for key, what in (("username_changed_at", "username"), ("nickname_changed_at", "nama tampilan")):
        t = parse_ts(p.get(key)) if p.get(key) else None
        if t and 0 <= (ref - t).days < 90:
            s += 0.25
            r.append(f"{what} diganti {(ref - t).days} hari lalu (indikasi akun daur ulang)")
            break
    fol, fing = p.get("followers"), p.get("following")
    if fol is not None and fol < 50:
        s += 0.15
        r.append(f"follower sangat sedikit ({fol})")
    if fol is not None and fing is not None and fing / max(fol, 1) > 10:
        s += 0.1
        r.append("mengikuti jauh lebih banyak akun daripada pengikutnya")
    if p.get("verified") or p.get("is_organization"):
        s -= 0.3
        r.append("akun terverifikasi/organisasi (menurunkan risiko)")
    known = created or fol is not None or uname
    return (_cap(s), r) if known else (None, ["data profil tidak tersedia"])


def _signal_rhythm(posts):
    ts = sorted(t for t in (parse_ts(p["timestamp"]) for p in posts) if t)
    if len(ts) < 5:
        return None, [f"hanya {len(ts)} post, ritme belum bisa dinilai"]
    s, r = 0.0, []
    hours = Counter(t.hour for t in ts)
    if len(hours) >= 20:
        s += 0.35
        r.append(f"aktif di {len(hours)} dari 24 jam sehari (tanpa jeda tidur)")
    night = sum(v for h, v in hours.items() if h < 5) / len(ts)
    if night > 0.3:
        s += 0.2
        r.append(f"{night:.0%} post dikirim pukul 00.00–05.00")
    gaps = [(b - a).total_seconds() for a, b in zip(ts, ts[1:]) if (b - a).total_seconds() > 0]
    if len(gaps) >= 5:
        cv = statistics.pstdev(gaps) / max(statistics.mean(gaps), 1)
        if cv < 0.35:
            s += 0.35
            r.append(f"jeda antar post sangat teratur (variasi {cv:.0%}), pola terjadwal/otomatis")
    days = max((ts[-1] - ts[0]).total_seconds() / 86400, 1)
    rate = len(ts) / days
    if rate > 10:
        s += 0.3
        r.append(f"{rate:.0f} post per hari")
    elif rate > 4:
        s += 0.15
        r.append(f"{rate:.1f} post per hari")
    bursts = sum(1 for a, b in zip(ts, ts[2:]) if (b - a).total_seconds() <= 600)
    if bursts:
        s += 0.1
        r.append(f"{bursts} kali memposting ≥3 konten dalam 10 menit")
    return _cap(s), r


def _signal_content(posts):
    if len(posts) < 3:
        return None, ["terlalu sedikit post untuk menilai pola konten"]
    s, r = 0.0, []
    keys = [normalize_text(p["content"])[:80] for p in posts]
    dup = 1 - len(set(keys)) / len(keys)
    if dup >= 0.2:
        s += 0.6 * min(1, dup / 0.6)
        r.append(f"{dup:.0%} post adalah salinan narasi yang sama")
    tags = [p.get("hashtags") or re.findall(r"#\w+", p["content"]) for p in posts]
    avg_tags = sum(len(t) for t in tags) / len(posts)
    if avg_tags >= 4:
        s += 0.2
        r.append(f"rata-rata {avg_tags:.1f} tagar per post (penumpukan tagar)")
    tc = Counter(t.lower() for ts in tags for t in set(ts))
    if tc:
        top, n = tc.most_common(1)[0]
        if n / len(posts) >= 0.6 and len(posts) >= 5:
            s += 0.15
            r.append(f"{n / len(posts):.0%} post mendorong tagar {top}")
    links = sum(1 for p in posts if (p.get("urls") or re.search(r"https?://|\.\w{2,3}/", p["content"]))) / len(posts)
    if links >= 0.5:
        s += 0.15
        r.append(f"{links:.0%} post berisi tautan")
    return _cap(s), r


def _signal_engagement(p, posts):
    fol = p.get("followers")
    views = [x.get("views") for x in posts if x.get("views")]
    if not views and fol is None:
        return None, ["data interaksi tidak tersedia"]
    if not views:
        return None, ["platform tidak memberi jumlah tayangan"]
    s, r = 0.0, []
    med_v = statistics.median(views)
    rates = [((x.get("likes") or 0) + (x.get("comments") or 0)) / x["views"] for x in posts if x.get("views")]
    med_er = statistics.median(rates) if rates else 0
    if med_v > 500 and med_er < 0.005:
        s += 0.3
        r.append(f"interaksi hanya {med_er:.2%} dari tayangan")
    if fol and fol > 10_000 and med_v < 0.01 * fol:
        s += 0.35
        r.append(f"{fol:,} follower tapi median tayangan hanya {med_v:,.0f} (follower kemungkinan tidak organik)")
    if sum(x.get("likes") or 0 for x in posts) > 200 and sum(x.get("comments") or 0 for x in posts) == 0:
        s += 0.15
        r.append("banyak suka tetapi tidak ada komentar sama sekali")
    if not r:
        r.append(f"interaksi wajar ({med_er:.1%} dari median {med_v:,.0f} tayangan)")
    return _cap(s), r


def _signal_network(memberships):
    if memberships is None:
        return None, ["belum dicocokkan dengan hasil deteksi jaringan"]
    if not memberships:
        return 0.0, ["tidak tergabung dalam campaign terkoordinasi yang terdeteksi"]
    best = max(memberships, key=lambda m: (m["role"] == "hub", m["flag_score"]))
    s = 1.0 if best["role"] == "hub" else 0.8
    role = "penggerak" if best["role"] == "hub" else "penguat"
    return s, [f"{role} dalam campaign {best['campaign_id']} ({best['description']})"]


def verdict(score, sig):
    get = lambda k: sig[k]["score"] or 0  # noqa: E731
    if score < 25:
        return "Kemungkinan organik"
    if get("jejaring") >= 0.8:
        return "Buzzer terkoordinasi"
    if get("ritme") >= 0.6 and get("konten") >= 0.4:
        return "Bot atau akun otomatis"
    if get("konten") >= 0.5:
        return "Akun spam atau promosi"
    if get("identitas") >= 0.6:
        return "Akun palsu atau sockpuppet"
    return "Perlu dipantau"


def risk_band(score):
    return "TINGGI" if score >= 50 else "SEDANG" if score >= 25 else "RENDAH"


def analyze_account(profile, posts, memberships=None, ref_time=None):
    """profile: username, created_at, followers, following, bio, verified, is_organization,
    username_changed_at, nickname_changed_at. posts: timestamp, content, views, likes, comments, hashtags, urls."""
    ref = ref_time or max([parse_ts(p["timestamp"]) for p in posts] or [datetime.now(WIB).replace(tzinfo=None)])
    parts = {
        "identitas": _signal_identity(profile, ref),
        "ritme": _signal_rhythm(posts),
        "konten": _signal_content(posts),
        "engagement": _signal_engagement(profile, posts),
        "jejaring": _signal_network(memberships),
    }
    sig = {k: {"score": v[0], "reasons": v[1] or ["tidak ada indikasi mencurigakan"], "weight": WEIGHTS[k],
               "label": LABELS[k]} for k, v in parts.items()}
    avail = {k: v for k, v in sig.items() if v["score"] is not None}
    wsum = sum(v["weight"] for v in avail.values()) or 1
    score = round(100 * sum(v["weight"] * v["score"] for v in avail.values()) / wsum)
    heat = [[0] * 24 for _ in range(7)]
    for p in posts:
        t = parse_ts(p["timestamp"])
        if t:
            heat[t.weekday()][t.hour] += 1
    return {"score": score, "verdict": verdict(score, sig), "risk": risk_band(score), "signals": sig, "heatmap": heat,
            "coverage": f"{len(avail)} dari {len(sig)} kelompok sinyal punya data",
            "post_count": len(posts)}


# ----------------------------------------------------------------------------- adapters
def from_database(db, account_id):
    accs = db.get_accounts()
    meta = (accs.get(account_id) or {}).get("metadata") or {}
    posts = [p for p in db.get_all_posts() if p["account_id"] == account_id]
    for p in posts:
        m = p.get("metadata") or {}
        p.update(views=m.get("views"), likes=m.get("likes"), comments=m.get("comments"))
    memberships = [dict(r) for r in db.conn.execute("""
        SELECT c.campaign_id, c.description, c.flag_score, ca.role FROM campaign_accounts ca
        JOIN campaigns c USING(campaign_id) WHERE ca.account_id=? AND c.status != 'dismissed'""", (account_id,))]
    profile = {"username": meta.get("username") or account_id, **meta}
    return profile, posts, memberships


def from_tiktok(sc, handle):
    """Tarik profil + video terbaru TikTok via ScrapeCreators (2 kredit)."""
    from connectors import _ts
    handle = handle.strip().lstrip("@")
    p = sc._call("/v1/tiktok/profile", handle=handle)
    u, st = p.get("user") or {}, p.get("stats") or {}
    if not u:
        raise RuntimeError(f"akun @{handle} tidak ditemukan atau privat")
    v = sc._call("/v3/tiktok/profile/videos", handle=handle)
    posts = []
    for a in v.get("aweme_list") or []:
        s = a.get("statistics") or {}
        posts.append({"timestamp": _ts(a.get("create_time")), "content": a.get("desc") or "",
                      "views": s.get("play_count"), "likes": s.get("digg_count"), "comments": s.get("comment_count"),
                      "shares": s.get("share_count"),
                      "hashtags": ["#" + t["hashtag_name"] for t in a.get("text_extra") or [] if t.get("hashtag_name")],
                      "url": a.get("share_url")})
    posts = [x for x in posts if x["timestamp"]]
    profile = {"username": u.get("uniqueId") or handle, "nickname": u.get("nickname"),
               "created_at": _ts(u.get("createTime")), "followers": st.get("followerCount"),
               "following": st.get("followingCount"), "bio": u.get("signature") or "",
               "verified": u.get("verified"), "is_organization": bool(u.get("isOrganization")),
               "username_changed_at": _ts(u.get("uniqueIdModifyTime")),
               "nickname_changed_at": _ts(u.get("nickNameModifyTime")),
               "total_likes": st.get("heartCount"), "video_count": st.get("videoCount"),
               "avatar": u.get("avatarMedium")}
    return profile, posts


def rank_accounts(db, limit=None):
    """Skor buzzer untuk semua akun di database (untuk tabel 'paling mencurigakan')."""
    accs = db.get_accounts()
    posts_by = {}
    for p in db.get_all_posts():
        m = p.get("metadata") or {}
        p.update(views=m.get("views"), likes=m.get("likes"), comments=m.get("comments"))
        posts_by.setdefault(p["account_id"], []).append(p)
    mem = {}
    for r in db.conn.execute("""SELECT ca.account_id, c.campaign_id, c.description, c.flag_score, ca.role
                                FROM campaign_accounts ca JOIN campaigns c USING(campaign_id)
                                WHERE c.status != 'dismissed'"""):
        mem.setdefault(r["account_id"], []).append(dict(r))
    ref = max((parse_ts(p["timestamp"]) for ps in posts_by.values() for p in ps), default=None)
    out = []
    for aid, ps in posts_by.items():
        meta = (accs.get(aid) or {}).get("metadata") or {}
        res = analyze_account({"username": meta.get("username") or aid, **meta}, ps, mem.get(aid, []), ref)
        out.append({"account_id": aid, "score": res["score"], "verdict": res["verdict"], "posts": len(ps),
                    "label": meta.get("label")})
    out.sort(key=lambda r: -r["score"])
    return out[:limit] if limit else out

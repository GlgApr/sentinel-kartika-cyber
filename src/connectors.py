# Connectors — menarik data publik NYATA dari media sosial
# SENTINEL · Kartika Cyber Hackathon 2026
#
# Sumber:
#   - ScrapeCreators (berbayar per kredit, butuh API key): TikTok, X/Twitter,
#     Threads, YouTube, Instagram Reels. Key dibaca dari env SCRAPECREATORS_API_KEY
#     atau Streamlit secrets — TIDAK PERNAH ditulis di kode/repo.
#   - Mastodon (gratis, tanpa key): timeline tagar publik instance mastodon.
#
# Semua sumber dinormalisasi ke format post SENTINEL:
#   {post_id, account_id, content, timestamp(ISO WIB), platform, hashtags, urls,
#    metadata{url, views, likes, shares, comments, followers, avatar}}

import hashlib
import html
import os
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests

from data_ingestion import HASHTAG_RE, MENTION_RE, URL_RE

WIB = timezone(timedelta(hours=7))
SC_BASE = "https://api.scrapecreators.com"
UA = {"User-Agent": "SentinelCIB/1.0 (research prototype)"}
TAG_RE = re.compile(r"<[^>]+>")


# ----------------------------------------------------------------------------- helpers
def _get(d, path, default=None):
    """Ambil nilai bersarang dengan path 'a.b.0.c' — toleran terhadap field hilang."""
    cur = d
    for part in path.split("."):
        if cur is None:
            return default
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return default
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return default
    return default if cur is None else cur


def _first(d, *paths, default=None):
    for p in paths:
        v = _get(d, p)
        if v not in (None, "", []):
            return v
    return default


def _to_int(v):
    try:
        return int(float(str(v).replace(",", "")))
    except (TypeError, ValueError):
        return None


def _ts(v):
    """Unix detik / ISO 8601 / format legacy Twitter -> ISO waktu WIB (naive)."""
    if v in (None, "", 0):
        return None
    try:
        if isinstance(v, (int, float)) or str(v).isdigit():
            dt = datetime.fromtimestamp(int(v), tz=timezone.utc)
        elif re.match(r"^[A-Z][a-z]{2} [A-Z][a-z]{2} ", str(v)):  # "Thu Oct 01 18:50:27 +0000 2026"
            dt = datetime.strptime(str(v), "%a %b %d %H:%M:%S %z %Y")
        else:
            try:
                dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
            except ValueError:
                dt = parsedate_to_datetime(str(v))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(WIB).replace(tzinfo=None).isoformat(timespec="seconds")
    except (ValueError, TypeError, OverflowError):
        return None


def _post(platform, pid, author, text, ts, url=None, views=None, likes=None, shares=None,
          comments=None, followers=None, avatar=None, account_created=None):
    text = (text or "").strip()
    return {
        "post_id": f"{platform}:{pid}", "account_id": f"{platform}:{author}", "platform": platform,
        "content": text, "timestamp": ts,
        "hashtags": HASHTAG_RE.findall(text), "urls": URL_RE.findall(text), "mentions": MENTION_RE.findall(text),
        "metadata": {"url": url, "views": _to_int(views), "likes": _to_int(likes), "shares": _to_int(shares),
                     "comments": _to_int(comments)},
        "_account": {"username": author, "followers": _to_int(followers), "avatar": avatar,
                     "created_at": account_created},
    }


def get_scrapecreators_key():
    key = os.environ.get("SCRAPECREATORS_API_KEY")
    if key:
        return key
    try:
        import streamlit as st
        key = st.secrets.get("SCRAPECREATORS_API_KEY")
        if key:
            return key
    except Exception:  # secrets.toml tidak ada di lokasi default Streamlit
        pass
    # fallback: .streamlit/secrets.toml di root proyek (bila app dijalankan dari folder lain)
    import tomllib
    from pathlib import Path
    f = Path(__file__).resolve().parent.parent / ".streamlit" / "secrets.toml"
    if f.exists():
        return tomllib.loads(f.read_text()).get("SCRAPECREATORS_API_KEY")
    return None


# ----------------------------------------------------------------------------- ScrapeCreators
class ScrapeCreators:
    PLATFORMS = {
        "tiktok": "TikTok (kata kunci)",
        "tiktok_hashtag": "TikTok (tagar)",
        "twitter": "X / Twitter",
        "threads": "Threads",
        "youtube": "YouTube",
        "instagram": "Instagram Reels",
    }

    def __init__(self, api_key):
        self.key = api_key
        self.credits_remaining = None

    def _call(self, path, **params):
        r = requests.get(SC_BASE + path, params={k: v for k, v in params.items() if v is not None},
                         headers={"x-api-key": self.key, **UA}, timeout=60)
        if r.status_code == 402:
            raise RuntimeError("Kredit ScrapeCreators habis (HTTP 402).")
        if r.status_code in (401, 403):
            raise RuntimeError("API key ScrapeCreators ditolak (HTTP %s)." % r.status_code)
        r.raise_for_status()
        data = r.json()
        self.credits_remaining = data.get("credits_remaining", self.credits_remaining)
        return data

    def search(self, platform, query, pages=1):
        fn = getattr(self, f"_{platform}")
        out, cursor = [], None
        for _ in range(max(1, pages)):
            posts, cursor = fn(query, cursor)
            out += [p for p in posts if p["timestamp"] and p["content"]]
            if not cursor:
                break
        return out

    def _tiktok(self, q, cursor):
        d = self._call("/v1/tiktok/search/keyword", query=q, cursor=cursor, sort_by="date-posted",
                       date_posted="this-month")
        posts = []
        for it in d.get("search_item_list") or []:
            a = it.get("aweme_info") or it
            posts.append(_post("tiktok", a.get("aweme_id"), _get(a, "author.unique_id"), a.get("desc"),
                               _ts(_first(a, "create_time", "create_time_utc")), a.get("share_url"),
                               _get(a, "statistics.play_count"), _get(a, "statistics.digg_count"),
                               _get(a, "statistics.share_count"), _get(a, "statistics.comment_count"),
                               _get(a, "author.follower_count"), _get(a, "author.avatar_medium.url_list.0")))
            posts[-1]["_account"]["following"] = _to_int(_get(a, "author.following_count"))
        return posts, d.get("cursor") if d.get("has_more", True) else None

    def _tiktok_hashtag(self, q, cursor):
        d = self._call("/v1/tiktok/search/hashtag", hashtag=q.lstrip("#"), cursor=cursor)
        posts = []
        for a in d.get("aweme_list") or []:
            posts.append(_post("tiktok", a.get("aweme_id"), _get(a, "author.unique_id"), a.get("desc"),
                               _ts(_first(a, "create_time", "create_time_utc")), a.get("share_url"),
                               _get(a, "statistics.play_count"), _get(a, "statistics.digg_count"),
                               _get(a, "statistics.share_count"), _get(a, "statistics.comment_count"),
                               _get(a, "author.follower_count") or None,
                               _get(a, "author.avatar_thumb.url_list.0"),
                               _ts(_get(a, "author.create_time")) if _get(a, "author.create_time") else None))
        return posts, d.get("cursor") if d.get("has_more") else None

    def _twitter(self, q, cursor):
        d = self._call("/v1/twitter/search/posts", query=q, cursor=cursor)
        posts = []
        for t in d.get("posts") or []:
            url = t.get("url") or ""
            m = re.search(r"(?:x|twitter)\.com/([^/]+)/status", url)
            author = _first(t, "core.user_results.result.legacy.screen_name",
                            "core.user_results.result.core.screen_name") or (m.group(1) if m else "unknown")
            posts.append(_post("x", t.get("rest_id"), author, _get(t, "legacy.full_text"),
                               _ts(_get(t, "legacy.created_at")), url, _get(t, "views.count"),
                               _get(t, "legacy.favorite_count"), _get(t, "legacy.retweet_count"),
                               _get(t, "legacy.reply_count"),
                               _get(t, "core.user_results.result.legacy.followers_count"),
                               account_created=_ts(_get(t, "core.user_results.result.legacy.created_at"))))
        return posts, d.get("cursor")

    def _threads(self, q, cursor):
        d = self._call("/v1/threads/search", query=q, trim="true")
        posts = []
        for t in d.get("posts") or []:
            user = _get(t, "user.username")
            code = t.get("code")
            posts.append(_post("threads", t.get("id") or t.get("pk"), user,
                               _first(t, "caption.text", "text_post_app_info.text_fragments.fragments.0.plaintext"),
                               _ts(t.get("taken_at")),
                               f"https://www.threads.net/@{user}/post/{code}" if code else None,
                               None, t.get("like_count"), _get(t, "text_post_app_info.repost_count"),
                               _get(t, "text_post_app_info.direct_reply_count"), None,
                               _get(t, "user.profile_pic_url")))
        return posts, None

    def _youtube(self, q, cursor):
        d = self._call("/v1/youtube/search", query=q, continuationToken=cursor, uploadDate="this_month")
        posts = []
        for v in (d.get("videos") or []) + (d.get("shorts") or []):
            posts.append(_post("youtube", v.get("id"), _first(v, "channel.handle", "channel.title", "channel.id"),
                               v.get("title"), _ts(v.get("publishedTime")), v.get("url"),
                               _first(v, "viewCountInt"), None, None, None, None, _get(v, "channel.thumbnail")))
        return posts, d.get("continuationToken")

    def _instagram(self, q, cursor):
        page = (cursor or 1)
        d = self._call("/v2/instagram/reels/search", query=q, page=page, date_posted="last-month")
        posts = []
        for r in d.get("reels") or []:
            posts.append(_post("instagram", r.get("id") or r.get("shortcode"), _get(r, "owner.username"),
                               r.get("caption") if isinstance(r.get("caption"), str) else _get(r, "caption.text"),
                               _ts(r.get("taken_at")), r.get("url"), _first(r, "play_count", "video_play_count"),
                               r.get("like_count"), None, r.get("comment_count"), _get(r, "owner.follower_count"),
                               _get(r, "owner.profile_pic_url")))
        return posts, (page + 1) if posts and page < 11 else None


# ----------------------------------------------------------------------------- Mastodon (gratis)
def mastodon_hashtag(tag, instance="mastodon.social", pages=3):
    """Timeline tagar publik Mastodon (tanpa API key). Memberi umur akun & follower asli."""
    out, max_id = [], None
    for _ in range(max(1, pages)):
        r = requests.get(f"https://{instance}/api/v1/timelines/tag/{tag.lstrip('#')}",
                         params={"limit": 40, **({"max_id": max_id} if max_id else {})}, headers=UA, timeout=30)
        r.raise_for_status()
        items = r.json()
        if not items:
            break
        for s in items:
            s = s.get("reblog") or s
            text = html.unescape(TAG_RE.sub(" ", s.get("content") or "")).strip()
            acc = s.get("account") or {}
            p = _post("mastodon", s.get("id"), acc.get("acct"), text, _ts(s.get("created_at")), s.get("url"),
                      None, s.get("favourites_count"), s.get("reblogs_count"), s.get("replies_count"),
                      acc.get("followers_count"), acc.get("avatar_static"), (acc.get("created_at") or "")[:10] or None)
            p["_account"]["following"] = acc.get("following_count")
            if p["timestamp"] and p["content"]:
                out.append(p)
        max_id = items[-1]["id"]
    return out


# ----------------------------------------------------------------------------- pipeline helpers
def mask_identity(username):
    """Mode Presentasi: samarkan username menjadi kode stabil (tidak bisa dibalik)."""
    return "akun_" + hashlib.sha256(username.encode()).hexdigest()[:6]


def to_sentinel(posts, mask=False):
    """Pisahkan post & akun ke format database SENTINEL (opsional disamarkan)."""
    accounts, clean, seen = {}, [], set()
    for p in posts:
        if p["post_id"] in seen:
            continue
        seen.add(p["post_id"])
        p = dict(p)
        acc_meta = dict(p.pop("_account"))
        aid = p["account_id"]
        if mask:
            aid = p["platform"] + ":" + mask_identity(aid)
            acc_meta.update(username=aid, avatar=None)
            p["metadata"] = {**p["metadata"], "url": None}
        p["account_id"] = aid
        acc_meta["username"] = acc_meta.get("username") or aid
        accounts.setdefault(aid, {"account_id": aid, "platform": p["platform"], "metadata": acc_meta})
        clean.append(p)
    return clean, list(accounts.values())


def viral_index(posts, now=None):
    """Indeks Potensi Viral 0-100 untuk sekumpulan post satu topik.

    Komponen: kecepatan interaksi per jam (40%), jangkauan total (25%),
    sebaran lintas platform (15%), keterlibatan akun besar >=100rb follower (20%)."""
    import math
    if not posts:
        return {"score": 0, "label": "Tidak ada data"}
    now = now or datetime.now(WIB).replace(tzinfo=None)
    vel, reach, big = [], 0, 0
    for p in posts:
        m = p.get("metadata") or {}
        acc = p.get("_account") or {}
        inter = (m.get("likes") or 0) + 2 * (m.get("shares") or 0) + (m.get("comments") or 0)
        views = m.get("views") or inter * 20  # estimasi bila platform tidak memberi views
        reach += views
        age_h = max((now - datetime.fromisoformat(p["timestamp"])).total_seconds() / 3600, 1)
        vel.append(views / age_h)
        if (acc.get("followers") or 0) >= 100_000:
            big += 1
    vel.sort()
    v_med = vel[len(vel) // 2]
    platforms = len({p["platform"] for p in posts})
    s_vel = min(1, math.log10(1 + v_med) / 5)        # 100rb views/jam -> 1.0
    s_reach = min(1, math.log10(1 + reach) / 7)      # 10 juta -> 1.0
    s_plat = min(1, (platforms - 1) / 3)
    s_big = min(1, big / 3)
    score = round(100 * (0.4 * s_vel + 0.25 * s_reach + 0.15 * s_plat + 0.2 * s_big))
    label = "VIRAL — segera respons" if score >= 65 else "Mulai menyebar" if score >= 35 else "Belum menyebar"
    return {"score": score, "label": label, "reach": reach, "median_velocity": v_med,
            "platforms": platforms, "big_accounts": big, "posts": len(posts)}


def suspicious_accounts(posts, min_posts=3):
    """Lensa per akun (buzzer/spam tunggal) — melengkapi deteksi jaringan.

    Menandai akun yang dalam hasil tarikan: mengulang narasi nyaris identik,
    atau memposting sangat sering untuk satu topik. Return list dict terurut skor."""
    from collections import defaultdict
    from feature_extraction import normalize_text
    by = defaultdict(list)
    for p in posts:
        by[p["account_id"]].append(p)
    out = []
    for acc, ps in by.items():
        if len(ps) < min_posts:
            continue
        keys = [normalize_text(p["content"])[:80] for p in ps]
        dup = 1 - len(set(keys)) / len(keys)
        ts = sorted(datetime.fromisoformat(p["timestamp"]) for p in ps)
        span_d = max((ts[-1] - ts[0]).total_seconds() / 86400, 1)
        rate = len(ps) / span_d
        meta = ps[0].get("_account") or {}
        reasons, score = [], 0.0
        if dup >= 0.5:
            score += 0.5
            reasons.append(f"{dup:.0%} post adalah salinan narasi yang sama")
        if len(ps) >= 5:
            score += 0.2
            reasons.append(f"{len(ps)} post untuk satu topik pencarian")
        if rate >= 2:
            score += 0.15
            reasons.append(f"{rate:.1f} post/hari")
        fol, fing = meta.get("followers"), meta.get("following")
        if fol is not None and fing is not None and fing <= 2 and fol > 1000:
            score += 0.15
            reasons.append("hampir tidak mengikuti akun lain (pola akun promosi/terkelola)")
        if score >= 0.5:
            out.append({"account_id": acc, "skor": round(min(score, 1), 2), "post": len(ps),
                        "duplikasi": round(dup, 2), "follower": fol, "alasan": "; ".join(reasons),
                        "contoh": ps[0]["content"][:120]})
    return sorted(out, key=lambda r: -r["skor"])

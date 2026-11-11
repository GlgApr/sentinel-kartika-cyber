# Tes parser konektor dengan payload tiruan (tanpa memanggil API berbayar)
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from connectors import ScrapeCreators, _ts, to_sentinel, viral_index  # noqa: E402


class FakeSC(ScrapeCreators):
    def __init__(self, payload):
        super().__init__("dummy")
        self.payload = payload

    def _call(self, path, **params):
        return self.payload


def test_tiktok_keyword_parse():
    sc = FakeSC({"search_item_list": [{"aweme_info": {
        "aweme_id": "1", "desc": "daftar jalur khusus #bintara bit.ly/x", "create_time": 1794300000,
        "share_url": "https://tiktok.com/@a/video/1",
        "author": {"unique_id": "a", "follower_count": 12, "avatar_medium": {"url_list": ["http://img"]}},
        "statistics": {"play_count": 5000, "digg_count": 10, "share_count": 3, "comment_count": 1}}}],
        "cursor": None, "has_more": False})
    p = sc.search("tiktok", "jalur khusus")[0]
    assert p["account_id"] == "tiktok:a" and p["metadata"]["views"] == 5000
    assert p["hashtags"] == ["#bintara"] and p["_account"]["followers"] == 12


def test_twitter_parse_author_from_url_and_legacy_date():
    sc = FakeSC({"posts": [{"rest_id": "9", "url": "https://x.com/budi/status/9",
                            "legacy": {"full_text": "BBM naik besok", "created_at": "Thu Oct 01 18:50:27 +0000 2026",
                                       "favorite_count": 4, "retweet_count": 2, "reply_count": 1},
                            "views": {"count": "780"}}], "cursor": None})
    p = sc.search("twitter", "bbm")[0]
    assert p["account_id"] == "x:budi" and p["timestamp"] == "2026-10-02T01:50:27"
    assert p["metadata"]["views"] == 780


def test_masking_and_viral_index():
    raw = FakeSC({"posts": [{"rest_id": str(i), "url": f"https://x.com/u{i}/status/{i}",
                             "legacy": {"full_text": "x", "created_at": "Thu Oct 01 18:50:27 +0000 2026"},
                             "views": {"count": "1000"}} for i in range(3)], "cursor": None}).search("twitter", "x")
    posts, accs = to_sentinel(raw, mask=True)
    assert all("akun_" in p["account_id"] for p in posts) and all(a["metadata"]["avatar"] is None for a in accs)
    vi = viral_index(raw)
    assert 0 <= vi["score"] <= 100 and vi["reach"] == 3000


def test_timestamp_formats():
    assert _ts("2025-05-28T17:08:46.499Z") == "2025-05-29T00:08:46"
    assert _ts(0) is None

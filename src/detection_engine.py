# Detection Engine
# SENTINEL · Kartika Cyber Hackathon 2026
#
# Pipeline (behavior-based, explainable):
#   1. TF-IDF char n-gram atas teks ter-normalisasi
#   2. Co-action detection: pasangan akun yang memposting narasi mirip / URL
#      sama / tagar langka sama dalam jendela <= 20 menit
#   3. Graf koordinasi akun: edge hanya bila co-action BERULANG (>= 2 episode)
#      -> menyaring kebetulan (mis. event viral organik seperti gempa)
#   4. Community detection (Louvain) -> kandidat campaign
#   5. Scoring multi-sinyal (konten, timing, akun, jaringan, amplifikasi)
#      + penjelasan bahasa Indonesia untuk setiap skor
#   6. Simpan campaign + akun + post bukti + edge ke SQLite

import hashlib
import time
import uuid
from collections import Counter, defaultdict
from datetime import datetime

import networkx as nx
import numpy as np

from config import Config
from database import Database, now_iso
from feature_extraction import FeatureExtractor, parse_ts, normalize_url

SIGNAL_LABELS = {
    "content": "Keseragaman narasi",
    "timing": "Sinkronisasi waktu",
    "account": "Anomali profil akun",
    "network": "Kepadatan jaringan",
    "amplification": "Amplifikasi tagar/URL",
}


def risk_level(score):
    if score >= Config.HIGH_RISK_THRESHOLD:
        return "TINGGI"
    if score >= Config.FLAG_THRESHOLD:
        return "SEDANG"
    return "RENDAH"


class DetectionEngine:
    def __init__(self, db=None, config=Config):
        self.db = db or Database()
        self.cfg = config
        self.fe = FeatureExtractor(config)
        self.last_graph = None

    # ------------------------------------------------------------------ public
    def run_detection_pipeline(self, persist=True, verbose=True):
        t_start = time.time()
        posts = self.db.get_all_posts()
        accounts = self.db.get_accounts()
        if not posts:
            if verbose:
                print("Tidak ada post di database. Jalankan data_ingestion.py dulu.")
            return []
        campaigns = self.detect(posts, accounts)
        run = {"run_id": uuid.uuid4().hex[:10], "started_at": now_iso(),
               "duration_s": round(time.time() - t_start, 2), "post_count": len(posts),
               "account_count": len({p["account_id"] for p in posts}),
               "params": {k: getattr(self.cfg, k) for k in (
                   "SIMILARITY_THRESHOLD", "COORDINATION_WINDOW_MIN", "MIN_EDGE_WEIGHT",
                   "MIN_CLUSTER_SIZE", "FLAG_THRESHOLD")}}
        if persist:
            self.db.save_detection_run(run, campaigns)
        if verbose:
            print(f"[detect] {len(posts)} post, {run['account_count']} akun -> "
                  f"{len(campaigns)} campaign ({sum(c['status'] == 'flagged' for c in campaigns)} flagged) "
                  f"dalam {run['duration_s']} detik")
        return campaigns

    def detect(self, posts, accounts):
        posts = sorted(posts, key=lambda p: str(p["timestamp"]))
        posts = [p for p in posts if parse_ts(p["timestamp"])]
        self.fe.fit_text(posts)
        idx = {p["post_id"]: i for i, p in enumerate(posts)}
        by_acc = defaultdict(list)
        for p in posts:
            by_acc[p["account_id"]].append(p)
        ref_time = parse_ts(posts[-1]["timestamp"])

        events = self.fe.find_coactions(posts)

        # ---- graf koordinasi
        G = nx.Graph()
        for (a, b), evts in events.items():
            w, n_ep = self.fe.pair_weight(evts)
            if w >= self.cfg.MIN_EDGE_WEIGHT:
                types = Counter(t for e in evts for t in e["types"])
                G.add_edge(a, b, weight=w, episodes=n_ep, types=dict(types), events=evts)
        self.last_graph = G
        if G.number_of_edges() == 0:
            return []

        communities = nx.community.louvain_communities(G, weight="weight", seed=7, resolution=1.0)
        campaigns = []
        for comm in communities:
            # k-core (k=2): buang akun yang hanya "nyangkut" lewat satu edge
            # kebetulan — anggota inti operasi saling terhubung ke >= 2 anggota lain.
            comm = set(nx.k_core(G.subgraph(comm), k=2).nodes) if len(comm) >= 3 else set()
            if len(comm) < self.cfg.MIN_CLUSTER_SIZE:
                continue
            c = self._score_cluster(sorted(comm), G, posts, idx, by_acc, accounts, ref_time)
            if c:
                campaigns.append(c)
        campaigns.sort(key=lambda c: -c["flag_score"])
        return campaigns

    # ------------------------------------------------------------------ scoring
    def _score_cluster(self, members, G, posts, idx, by_acc, accounts, ref_time):
        cfg = self.cfg
        sub = G.subgraph(members)
        mset = set(members)

        # post bukti = post yang terlibat co-action di dalam cluster
        ev_posts, ev_types = set(), Counter()
        for a, b, d in sub.edges(data=True):
            for e in d["events"]:
                ev_posts.update(e["posts"])
                ev_types.update(e["types"])
        if len(ev_posts) < 3:
            return None
        ev_list = sorted(ev_posts, key=lambda pid: idx[pid])
        ev_rows = [posts[idx[pid]] for pid in ev_list]

        # 1) CONTENT — rata-rata cosine antar post bukti dari akun berbeda
        Xi = self.fe.X[[idx[p] for p in ev_list]]
        S = (Xi @ Xi.T).toarray()
        acc_arr = np.array([r["account_id"] for r in ev_rows])
        mask = acc_arr[:, None] != acc_arr[None, :]
        content = float(S[mask].mean()) if mask.any() else 0.0
        content = float(np.clip((content - 0.15) / 0.6, 0, 1))  # kalibrasi: 0.15 ~ teks acak, 0.75 ~ copypasta

        # 2) TIMING — proporsi post bukti yang punya "pasangan" dari akun lain <= 10 menit,
        #    dikali faktor pengulangan (operasi = gelombang berulang)
        ts = np.array([parse_ts(r["timestamp"]).timestamp() for r in ev_rows])
        # gelombang = kelompok aktivitas yang dipisahkan jeda > 2x jendela koordinasi
        waves = 1 + int(np.sum(np.diff(np.sort(ts)) > 2 * cfg.COORDINATION_WINDOW_MIN * 60))
        sync = []
        for i in range(len(ts)):
            other = mask[i]
            sync.append(np.min(np.abs(ts[other] - ts[i])) <= 600 if other.any() else False)
        sync_ratio = float(np.mean(sync))
        repeat = min(1.0, waves / 4)
        timing = 0.65 * sync_ratio + 0.35 * repeat

        # 3) ACCOUNT — rata-rata anomali profil
        acc_scores, acc_reasons = {}, Counter()
        for a in members:
            meta = (accounts.get(a) or {}).get("metadata") or {"username": a}
            s, rs = self.fe.account_anomaly(meta, by_acc[a], ref_time)
            acc_scores[a] = s
            for r in rs:
                acc_reasons[r.split(" (")[0]] += 1
        account = float(np.mean(list(acc_scores.values())))

        # 4) NETWORK — densitas graf + rata-rata pengulangan co-action
        density = nx.density(sub)
        mean_w = float(np.mean([d["weight"] for _, _, d in sub.edges(data=True)]))
        network = 0.6 * density + 0.4 * min(1.0, mean_w / 4)

        # 5) AMPLIFICATION — konsentrasi tagar / URL dominan di post bukti
        tag_c = Counter(h for r in ev_rows for h in {x.lower() for x in (r.get("hashtags") or [])})
        url_c = Counter(u for r in ev_rows for u in {normalize_url(x) for x in (r.get("urls") or [])})
        top_tag = tag_c.most_common(1)[0] if tag_c else (None, 0)
        top_url = url_c.most_common(1)[0] if url_c else (None, 0)
        amplification = min(1.0, max(top_tag[1], top_url[1]) / len(ev_rows))

        signals = {"content": content, "timing": timing, "account": account,
                   "network": network, "amplification": amplification}
        signals = {k: round(float(v), 3) for k, v in signals.items()}
        score = round(sum(cfg.SCORING_WEIGHTS[k] * v for k, v in signals.items()), 3)

        # ---- penjelasan (explainability untuk analis)
        first, last = ev_rows[0]["timestamp"], ev_rows[-1]["timestamp"]
        expl = [
            f"{len(members)} akun memposting {len(ev_rows)} konten terkoordinasi dalam "
            f"{waves} gelombang terpisah ({first[:16].replace('T', ' ')} s/d {last[:16].replace('T', ' ')}).",
            f"Keseragaman narasi {signals['content']:.0%}: post dari akun berbeda memakai template teks yang nyaris sama "
            f"(co-action konten: {ev_types.get('content', 0)}, URL: {ev_types.get('url', 0)}, tagar: {ev_types.get('hashtag', 0)}).",
            f"{sync_ratio:.0%} post bukti diunggah ≤ 10 menit dari post akun lain dalam cluster.",
        ]
        if acc_reasons:
            top = ", ".join(f"{r} ({n} akun)" for r, n in acc_reasons.most_common(3))
            expl.append(f"Anomali profil: {top}.")
        if top_url[0]:
            expl.append(f"URL yang didorong: {top_url[0]} ({top_url[1]}x).")
        if top_tag[0]:
            expl.append(f"Tagar yang didorong: {top_tag[0]} ({top_tag[1]}x).")
        expl.append(f"Densitas jaringan {density:.0%} (rata-rata {mean_w:.1f} episode co-action per pasangan akun).")

        keywords = [w for w in self.fe.top_keywords([r["content"] for r in ev_rows], k=7)
                    if not top_tag[0] or w != top_tag[0].lstrip("#")][:5]
        topic = ", ".join(([top_tag[0]] if top_tag[0] else []) + keywords)

        deg = dict(sub.degree(weight="weight"))
        cut = np.percentile(list(deg.values()), 80) if deg else 0
        roles = {a: ("hub" if deg.get(a, 0) >= cut else "amplifier") for a in members}

        edges = [{"source": a, "target": b, "weight": d["weight"], "evidence": d["types"]}
                 for a, b, d in sub.edges(data=True)]
        cid = "CMP-" + hashlib.sha1("|".join(members).encode()).hexdigest()[:6].upper()
        status = "flagged" if score >= cfg.FLAG_THRESHOLD else "dismissed"
        return {
            "campaign_id": cid, "flag_score": score, "risk_level": risk_level(score), "status": status,
            "description": self._describe(signals, top_tag[0], top_url[0], len(members)),
            "topic_keywords": topic, "signals": signals, "explanations": expl,
            "accounts": members, "posts": ev_list, "edges": edges, "roles": roles,
            "degrees": {a: round(v, 2) for a, v in deg.items()}, "account_scores": acc_scores,
            "first_seen": first, "last_seen": last, "waves": waves,
        }

    @staticmethod
    def _describe(sig, tag, url, n):
        dominant = max(sig, key=sig.get)
        kind = {
            "content": "Copypasta terkoordinasi",
            "timing": "Posting serentak terjadwal",
            "account": "Jaringan akun palsu/sockpuppet",
            "network": "Jaringan amplifikasi rapat",
            "amplification": "Dorongan tagar/URL",
        }[dominant]
        target = f" mendorong {url}" if url else (f" mendorong {tag}" if tag else "")
        return f"{kind}: {n} akun{target}"


if __name__ == "__main__":
    db = Database()
    if db.count("posts") == 0:
        from data_ingestion import ingest_sample_data
        ingest_sample_data(db)
    engine = DetectionEngine(db)
    for c in engine.run_detection_pipeline():
        print(f"- {c['campaign_id']} [{c['risk_level']:6}] score={c['flag_score']:.2f} "
              f"akun={len(c['accounts']):3} post={len(c['posts']):3} | {c['description']}")

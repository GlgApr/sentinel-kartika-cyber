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
from feature_extraction import (CODE, FeatureExtractor, normalize_text, normalize_url, parse_ts,
                                display_entity, promoted_entities, skeleton)

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

        self.motifs = []
        motif_w = self._motif_repetition(events, posts, idx)

        # ---- graf koordinasi
        # Edge diterima bila koordinasi BERULANG, di salah satu dari dua level:
        #   (a) pasangan akun yang sama beraksi bersama di >= 2 episode terpisah, atau
        #   (b) pasangan itu bagian dari MOTIF (templat + target promosi yang sama)
        #       yang muncul lagi di >= 2 episode terpisah oleh kelompok yang sama —
        #       pola spam komentar: tiap akun muncul sekali, tapi motifnya berulang.
        G = nx.Graph()
        for (a, b), evts in events.items():
            w, n_ep = self.fe.pair_weight(evts)
            w = max(w, motif_w.get((a, b), 0.0))
            if w >= self.cfg.MIN_EDGE_WEIGHT:
                types = Counter(t for e in evts for t in e["types"])
                G.add_edge(a, b, weight=w, episodes=n_ep, types=dict(types), events=evts)
        # akun yang menjalankan motif yang sama di gelombang BERBEDA adalah satu operasi
        for m in self.motifs:
            accs = sorted(m["accounts"])
            for i, a in enumerate(accs):
                for b in accs[i + 1:]:
                    if not G.has_edge(a, b):
                        G.add_edge(a, b, weight=float(min(m["episodes"], 4)), episodes=m["episodes"],
                                   types={"motif": 1}, events=[])
        self.last_graph = G
        campaigns = []
        claimed = set()
        if G.number_of_edges() == 0:
            communities = []
        else:
            communities = nx.community.louvain_communities(G, weight="weight", seed=7, resolution=1.0)
        for comm in communities:
            # k-core (k=2): buang akun yang hanya "nyangkut" lewat satu edge
            # kebetulan — anggota inti operasi saling terhubung ke >= 2 anggota lain.
            comm = set(nx.k_core(G.subgraph(comm), k=2).nodes) if len(comm) >= 3 else set()
            if len(comm) < self.cfg.MIN_CLUSTER_SIZE:
                continue
            c = self._score_cluster(sorted(comm), G, posts, idx, by_acc, accounts, ref_time)
            if c:
                campaigns.append(c)
                claimed |= set(c["accounts"])

        # operasi templat "tetes lambat" — tanpa keserempakan waktu
        for members, H in self._template_operations(posts, idx):
            # akun yang sudah masuk campaign serentak tidak dihitung dua kali
            members = members - claimed
            if len(members) < self.cfg.MIN_CLUSTER_SIZE:
                continue
            H = H.subgraph(members).copy()
            if H.number_of_edges() == 0:
                continue
            c = self._score_cluster(sorted(members), H, posts, idx, by_acc, accounts, ref_time,
                                    pattern="template")
            if c:
                campaigns.append(c)
        campaigns.sort(key=lambda c: -c["flag_score"])
        return campaigns

    # ------------------------------------------------------------------ template operations
    def _template_operations(self, posts, idx):
        """Operasi templat 'tetes lambat': akun-akun memposting templat yang sama
        sambil MEMUTAR target promosi, tersebar berhari-hari (tidak serentak).

        Graf bipartit templat <-> target. Satu komponen dianggap operasi bila:
          - >= MIN_CLUSTER_SIZE akun, dan
          - >= 2 target yang masing-masing didorong >= 2 akun berbeda, dan
          - ada ROTASI: satu templat dipakai untuk >= 2 target, atau satu target
            didorong lewat >= 2 templat.
        Kutipan/meme organik (1 target, 1 templat) dan tag-teman (target berbeda
        tiap akun) tidak memenuhi syarat ini.
        """
        from sklearn.feature_extraction.text import TfidfVectorizer
        cfg = self.cfg
        rows = []
        for p in posts:
            tg = {e for e in promoted_entities(p) if not e.startswith("#")}
            if not tg:
                continue
            words = [w for w in normalize_text(p["content"]).split()
                     if skeleton(w) not in tg and not CODE.match(w)]
            tmpl = " ".join(words)
            if len(tmpl.replace(" ", "")) < 6:
                continue
            rows.append((p, tg, tmpl))
        if len(rows) < cfg.MIN_CLUSTER_SIZE:
            return []
        V = TfidfVectorizer(analyzer="char_wb", ngram_range=cfg.NGRAM_RANGE).fit_transform([r[2] for r in rows])
        S = (V @ V.T).toarray()
        parent = list(range(len(rows)))

        def f(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for i in range(len(rows)):
            for j in np.nonzero(S[i, i + 1:] >= cfg.SIMILARITY_THRESHOLD)[0] + i + 1:
                parent[f(i)] = f(int(j))
        B = nx.Graph()  # node: ("T", templat-id) / ("E", target)
        for i, (p, tg, _) in enumerate(rows):
            for e in tg:
                B.add_edge(("T", f(i)), ("E", e), posts={p["post_id"]})
                B[("T", f(i))][("E", e)].setdefault("acc", set()).add(p["account_id"])
                B[("T", f(i))][("E", e)]["posts"].add(p["post_id"])
        out = []
        for comp in nx.connected_components(B):
            sub = B.subgraph(comp)
            pids = set().union(*(d["posts"] for _, _, d in sub.edges(data=True)))
            accs = set().union(*(d["acc"] for _, _, d in sub.edges(data=True)))
            ent_acc = defaultdict(set)
            for u, v, d in sub.edges(data=True):
                ent_acc[u if u[0] == "E" else v] |= d["acc"]
            strong = [e for e, a in ent_acc.items() if len(a) >= 2]
            rotation = any(sub.degree(n) >= 2 for n in comp)
            if len(accs) < cfg.MIN_CLUSTER_SIZE or len(strong) < 2 or not rotation:
                continue
            # graf akun: dua akun terhubung bila memakai templat ATAU target yang sama
            H = nx.Graph()
            by_node = defaultdict(list)
            for i, (p, tg, _) in enumerate(rows):
                if p["post_id"] in pids:
                    by_node[("T", f(i))].append(p)
                    for e in tg:
                        by_node[("E", e)].append(p)
            for node, ps in by_node.items():
                for a_i in range(len(ps)):
                    for b_i in range(a_i + 1, len(ps)):
                        a, b = ps[a_i], ps[b_i]
                        if a["account_id"] == b["account_id"]:
                            continue
                        if not H.has_edge(a["account_id"], b["account_id"]):
                            H.add_edge(a["account_id"], b["account_id"], weight=0.0, episodes=0,
                                       types={"template": 0}, events=[])
                        d = H[a["account_id"]][b["account_id"]]
                        d["weight"] = min(4.0, d["weight"] + 1)
                        d["types"]["template"] += 1
                        d["events"].append({"types": ["template"], "posts": (a["post_id"], b["post_id"]),
                                            "sim": 0.0, "t": 0.0})
            tmpl_acc = {u: set().union(*(d["acc"] for _, _, d in sub.edges(u, data=True)))
                        for u in comp if u[0] == "T"}
            # templat milik tiap post + apakah templat itu dipakai >= 2 akun dalam operasi
            reused_post = {p["post_id"]: len(tmpl_acc.get(("T", f(i)), ())) >= 2
                           for i, (p, _, _) in enumerate(rows) if p["post_id"] in pids}
            H.graph.update(reused_post=reused_post, targets=[display_entity(e[1]) for e in sorted(strong, key=lambda e: -len(ent_acc[e]))],
                           n_templates=sum(1 for u in comp if u[0] == "T"))
            out.append((accs, H))
        return out

    # ------------------------------------------------------------------ motif
    def _motif_repetition(self, events, posts, idx):
        """Pengulangan level kelompok.

        1. Episode = komponen terhubung post yang saling ber-co-action (>= 2 akun).
        2. Dua episode termasuk MOTIF yang sama bila terpisah waktu dan berbagi target
           promosi langka, atau teksnya mirip (cosine >= ambang) DAN keduanya
           mendorong suatu target. Slogan organik tanpa target tidak ikut aturan ini.
        3. Motif dengan >= 2 episode, >= 3 akun -> setiap pasangan co-action di dalamnya
           mendapat bobot = jumlah episode motif (maks 4).
        Return: dict[(a, b)] -> bobot.
        """
        rare = getattr(self.fe, "rare_entities", set())
        parent = {}

        def find(x):
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        pair_posts = []
        for pair, evts in events.items():
            for e in evts:
                a, b = e["posts"]
                parent[find(a)] = find(b)
                pair_posts.append((pair, a))
        comps = defaultdict(set)
        for pid in list(parent):
            comps[find(pid)].add(pid)
        eps = []
        for root, pids in comps.items():
            rows = [posts[idx[p]] for p in pids]
            accs = {r["account_id"] for r in rows}
            if len(accs) < 2:
                continue
            ents = set()
            for r in rows:
                # target KUAT saja (mention, kode merek, URL). Tagar sering penanda topik
                # organik (#timnas) — kampanye tagar tetap ditangani aturan pasangan.
                ents |= {e for e in promoted_entities(r)
                         if (e in rare and not e.startswith("#")) or e.startswith("url:")}
            # templat = teks tanpa target promosi ("@MMM5 คืออะไรหรอ" -> "คืออะไรหรอ"),
            # agar satu operasi yang mendorong banyak kode merek tetap dikenali
            tmpl = " ".join(" ".join(w for w in normalize_text(r["content"]).split()
                                     if w not in rare and not CODE.match(w)) for r in rows)
            t = min(parse_ts(r["timestamp"]).timestamp() for r in rows)
            eps.append({"root": root, "accs": accs, "ents": ents, "tmpl": tmpl, "t": t,
                        "pids": pids})
        if len(eps) < 2:
            return {}
        from sklearn.feature_extraction.text import TfidfVectorizer
        docs = [e["tmpl"] or "-" for e in eps]
        V = TfidfVectorizer(analyzer="char_wb", ngram_range=self.cfg.NGRAM_RANGE).fit_transform(docs)
        for e, v in zip(eps, V):
            e["vec"] = v.toarray().ravel()
        gap = 2 * self.cfg.COORDINATION_WINDOW_MIN * 60
        mparent = list(range(len(eps)))

        def mfind(x):
            while mparent[x] != x:
                mparent[x] = mparent[mparent[x]]
                x = mparent[x]
            return x

        for i in range(len(eps)):
            for j in range(i + 1, len(eps)):
                ei, ej = eps[i], eps[j]
                if not (ei["ents"] and ej["ents"]) or abs(ei["t"] - ej["t"]) <= gap:
                    continue
                if ei["ents"] & ej["ents"] or float(ei["vec"] @ ej["vec"]) >= self.cfg.MOTIF_TEMPLATE_SIM:
                    mparent[mfind(i)] = mfind(j)
        motifs = defaultdict(list)
        for i in range(len(eps)):
            motifs[mfind(i)].append(eps[i])
        root_w = {}
        self.motifs = []
        for m in motifs.values():
            accs = set().union(*(e["accs"] for e in m))
            if len(m) >= 2 and len(accs) >= self.cfg.MIN_CLUSTER_SIZE:
                for e in m:
                    root_w[e["root"]] = float(min(len(m), 4))
                self.motifs.append({"episodes": len(m), "accounts": accs,
                                    "targets": set().union(*(e["ents"] for e in m)),
                                    "posts": set().union(*(e["pids"] for e in m))})
        out = {}
        for pair, pid in pair_posts:
            w = root_w.get(find(pid))
            if w:
                out[pair] = max(out.get(pair, 0.0), w)
        return out

    # ------------------------------------------------------------------ scoring
    def _score_cluster(self, members, G, posts, idx, by_acc, accounts, ref_time, pattern="sync"):
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
        # target = tagar / mention / kode merek (mis. "xv99") yang didorong
        tag_c = Counter(e for r in ev_rows for e in promoted_entities(r) if not e.startswith("url:"))
        url_c = Counter(u for r in ev_rows for u in {normalize_url(x) for x in (r.get("urls") or [])})
        top_tag = (display_entity(tag_c.most_common(1)[0][0]), tag_c.most_common(1)[0][1]) if tag_c else (None, 0)
        top_url = url_c.most_common(1)[0] if url_c else (None, 0)
        # porsi post bukti yang MENDORONG target promosi langka (tagar langka, mention,
        # kode merek, URL). Operasi yang memutar banyak merek (xv99 -> mmm5 -> 8ddd)
        # tetap terhitung penuh; tak cukup hanya mengukur satu target teratas.
        rare = getattr(self.fe, "rare_entities", set())
        pushing = sum(1 for r in ev_rows if any(e in rare or e.startswith("url:") for e in promoted_entities(r)))
        amplification = min(1.0, max(top_tag[1], top_url[1], pushing) / len(ev_rows))

        if pattern == "template":
            # operasi tetes lambat: bukti koordinasinya adalah PENGGUNAAN ULANG templat
            # lintas akun sambil memutar target, bukan keserempakan waktu.
            # dihitung atas post anggota yang DINILAI (bukan seluruh komponen)
            rp = G.graph["reused_post"]
            content = sum(1 for r in ev_rows if rp.get(r["post_id"])) / len(ev_rows)
            days = len({r["timestamp"][:10] for r in ev_rows})
            # tanpa bukti keserempakan -> sinyal waktu dibatasi setengah (persistensi saja)
            timing = 0.5 * min(1.0, days / 4)
            amplification = sum(1 for r in ev_rows if any(not e.startswith("#") for e in promoted_entities(r))) / len(ev_rows)
        signals = {"content": content, "timing": timing, "account": account,
                   "network": network, "amplification": amplification}
        signals = {k: round(float(v), 3) for k, v in signals.items()}
        # "Tidak tahu" != "normal": bila mayoritas anggota tak punya data profil
        # (mis. data komentar yang hanya membawa username), sinyal akun tidak dipakai
        # dan bobot sisanya dinormalisasi ulang — sama seperti lensa buzzer per akun.
        has_profile = sum(1 for a in members if any(
            ((accounts.get(a) or {}).get("metadata") or {}).get(k) is not None
            for k in ("created_at", "followers", "following")))
        weights = dict(cfg.SCORING_WEIGHTS)
        if has_profile < len(members) / 2:
            weights.pop("account")
        tot = sum(weights.values())
        score = round(sum(w * signals[k] for k, w in weights.items()) / tot, 3)

        # ---- penjelasan (explainability untuk analis)
        first, last = ev_rows[0]["timestamp"], ev_rows[-1]["timestamp"]
        expl = [
            f"{len(members)} akun memposting {len(ev_rows)} konten terkoordinasi dalam "
            f"{waves} gelombang terpisah ({first[:16].replace('T', ' ')} s/d {last[:16].replace('T', ' ')}).",
            f"Keseragaman narasi {signals['content']:.0%}: post dari akun berbeda memakai template teks yang nyaris sama "
            f"(co-action konten: {ev_types.get('content', 0)}, URL: {ev_types.get('url', 0)}, tagar: {ev_types.get('hashtag', 0)}, "
            f"mention/kode merek: {ev_types.get('entity', 0)}).",
            f"{sync_ratio:.0%} post bukti diunggah ≤ 10 menit dari post akun lain dalam cluster.",
        ]
        if pattern == "template":
            tg = G.graph["targets"]
            expl = [
                f"Pola tetes lambat: {len(members)} akun memakai {G.graph['n_templates']} templat teks untuk memutar "
                f"{len(tg)} target promosi ({', '.join(tg[:6])}) selama {days} hari "
                f"({first[:10]} s/d {last[:10]}), tanpa posting serentak.",
                f"{signals['content']:.0%} post memakai templat yang juga dipakai akun lain.",
                "Rotasi target: templat yang sama dipakai untuk merek berbeda dan merek yang sama didorong lewat templat "
                "berbeda — ciri operasi promosi terkelola, bukan kutipan/meme organik.",
            ]
        if "account" not in weights:
            expl.append("Data profil akun tidak tersedia untuk mayoritas anggota; skor dihitung dari 4 sinyal lain.")
        elif acc_reasons:
            top = ", ".join(f"{r} ({n} akun)" for r, n in acc_reasons.most_common(3))
            expl.append(f"Anomali profil: {top}.")
        if top_url[0]:
            expl.append(f"URL yang didorong: {top_url[0]} ({top_url[1]}x).")
        if top_tag[0]:
            expl.append(f"Target yang didorong: {top_tag[0]} ({top_tag[1]}x).")
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
            "description": (f"Operasi templat tetes lambat: {len(members)} akun memutar {len(G.graph['targets'])} target"
                            if pattern == "template" else self._describe(signals, top_tag[0], top_url[0], len(members))),
            "topic_keywords": topic, "signals": signals, "explanations": expl,
            "accounts": members, "posts": ev_list, "edges": edges, "roles": roles,
            "degrees": {a: round(v, 2) for a, v in deg.items()}, "account_scores": acc_scores,
            "first_seen": first, "last_seen": last, "waves": waves, "pattern": pattern,
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

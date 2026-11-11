# SENTINEL — Streamlit Dashboard
# Coordinated Campaign & Astroturfing Detection Platform
# Kartika Cyber Hackathon 2026 · Kategori: Siber Sosial
#
# Jalankan:  streamlit run app/dashboard.py

import sys
from pathlib import Path

import networkx as nx
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from config import Config  # noqa: E402
from data_ingestion import generate_synthetic_dataset, ingest, load_dataframe  # noqa: E402
from database import Database  # noqa: E402
from detection_engine import SIGNAL_LABELS, DetectionEngine  # noqa: E402
from feature_extraction import FeatureExtractor  # noqa: E402
from report import campaign_brief  # noqa: E402

st.set_page_config(page_title="SENTINEL · Deteksi Operasi Pengaruh", page_icon="🛡️",
                   layout="wide", initial_sidebar_state="expanded")

RISK_COLOR = {"TINGGI": "#d62728", "SEDANG": "#ff9f1c", "RENDAH": "#7f8c8d"}
STATUS_ICON = {"flagged": "🔴", "escalated": "🚨", "reviewed": "🟡", "dismissed": "⚪"}
PALETTE = px.colors.qualitative.Bold

st.markdown("""
<style>
.block-container {padding-top: 1.6rem;}
.risk-badge {display:inline-block;padding:2px 10px;border-radius:12px;color:#fff;font-weight:600;font-size:0.85rem}
.expl li {margin-bottom: 0.25rem;}
div[data-testid="stMetricValue"] {font-size: 1.7rem;}
</style>""", unsafe_allow_html=True)


@st.cache_resource
def get_db():
    db = Database()
    if db.count("posts") == 0:  # first run: siapkan data demo otomatis
        posts, accounts = generate_synthetic_dataset(seed=42)
        ingest(posts, accounts, db)
        DetectionEngine(db).run_detection_pipeline(verbose=False)
    return db


db = get_db()


def load_state():
    posts = pd.DataFrame(db.get_all_posts())
    camps = db.get_campaigns()
    members = pd.DataFrame(db.get_all_campaign_accounts())
    return posts, camps, members


posts_df, campaigns, members_df = load_state()
if not posts_df.empty:
    posts_df["ts"] = pd.to_datetime(posts_df["timestamp"])
flagged = [c for c in campaigns if c["status"] in ("flagged", "escalated", "reviewed")]
camp_color = {c["campaign_id"]: PALETTE[i % len(PALETTE)] for i, c in enumerate(campaigns)}


def risk_badge(level):
    return f"<span class='risk-badge' style='background:{RISK_COLOR[level]}'>{level}</span>"


def campaign_label(c):
    return f"{STATUS_ICON.get(c['status'], '')} {c['campaign_id']} · {c['risk_level']} · {c['description']}"


# ============================================================== sidebar
st.sidebar.markdown(f"## 🛡️ {Config.APP_NAME}")
st.sidebar.caption(Config.APP_TAGLINE)
page = st.sidebar.radio("Navigasi", ["🏠 Ringkasan Situasi", "🔍 Investigasi Campaign", "🕸️ Peta Jaringan",
                                     "🌐 Data Lapangan (Live)", "📥 Data & Deteksi", "📈 Evaluasi Akurasi",
                                     "ℹ️ Metodologi"])
if not posts_df.empty:
    src = posts_df["platform"].value_counts()
    st.sidebar.caption("Sumber data aktif: " + ", ".join(f"{k} ({v})" for k, v in src.items()))
    if "sample" not in src.index and st.sidebar.button("↩️ Kembali ke data skenario demo", width="stretch"):
        ingest(*generate_synthetic_dataset(seed=42), db)
        DetectionEngine(db).run_detection_pipeline(verbose=False)
        st.rerun()
st.sidebar.divider()
run = db.get_last_run()
if run:
    st.sidebar.caption(f"Run terakhir: {run['started_at'].replace('T', ' ')}  \n"
                       f"{run['post_count']} post · {run['account_count']} akun · {run['duration_s']} dtk")
if st.sidebar.button("🔄 Jalankan Ulang Deteksi", width="stretch"):
    with st.spinner("Menjalankan pipeline deteksi..."):
        DetectionEngine(db).run_detection_pipeline(verbose=False)
    st.rerun()
st.sidebar.caption("Kartika Cyber Hackathon 2026 · Kategori Siber Sosial")


# ============================================================== helpers (charts)
def timeline_chart(df, height=360):
    """Aktivitas per jam: organik vs post terkoordinasi per campaign."""
    shown = {c["campaign_id"] for c in flagged}
    cp = pd.read_sql("SELECT campaign_id, post_id FROM campaign_posts", db.conn)
    cp = cp[cp["campaign_id"].isin(shown)].drop_duplicates("post_id")
    d = df.merge(cp, on="post_id", how="left")
    d["kategori"] = d["campaign_id"].fillna("Organik / tidak terkoordinasi")
    d["jam"] = d["ts"].dt.floor("h")
    g = d.groupby(["jam", "kategori"]).size().reset_index(name="jumlah")
    cmap = {**camp_color, "Organik / tidak terkoordinasi": "#c7ccd1"}
    fig = px.bar(g, x="jam", y="jumlah", color="kategori", color_discrete_map=cmap, height=height)
    starts, series = FeatureExtractor.hourly_activity(df.to_dict("records"))
    for b in FeatureExtractor.detect_bursts(starts, series):
        fig.add_vrect(x0=b["window_start"], x1=pd.Timestamp(b["window_start"]) + pd.Timedelta(hours=1),
                      fillcolor="red", opacity=0.07, line_width=0)
    fig.update_traces(width=3600 * 1000 * 0.9)  # lebar bar = 1 jam (sumbu datetime dalam ms)
    fig.update_layout(bargap=0.05, legend=dict(orientation="h", y=-0.25), margin=dict(t=10, b=10),
                      xaxis_title=None, yaxis_title="post / jam")
    return fig


def network_figure(edges, node_meta, height=520):
    G = nx.Graph()
    for e in edges:
        G.add_edge(e["source"], e["target"], weight=e["weight"])
    if G.number_of_nodes() == 0:
        return None
    pos = nx.spring_layout(G, seed=3, weight="weight", k=0.6)
    ex, ey = [], []
    for a, b in G.edges():
        ex += [pos[a][0], pos[b][0], None]
        ey += [pos[a][1], pos[b][1], None]
    fig = go.Figure(go.Scatter(x=ex, y=ey, mode="lines", line=dict(width=0.6, color="#9aa5b1"), hoverinfo="skip",
                               showlegend=False))
    groups = {}
    for n in G.nodes():
        m = node_meta.get(n, {})
        groups.setdefault(m.get("group", "-"), []).append(n)
    for gname, nodes in groups.items():
        fig.add_trace(go.Scatter(
            x=[pos[n][0] for n in nodes], y=[pos[n][1] for n in nodes], mode="markers", name=gname,
            marker=dict(size=[10 + 2.2 * G.degree(n) for n in nodes], color=node_meta.get(nodes[0], {}).get("color"),
                        line=dict(width=1, color="white")),
            text=[f"{n}<br>{node_meta.get(n, {}).get('hover', '')}" for n in nodes], hoverinfo="text"))
    fig.update_layout(height=height, showlegend=True, margin=dict(t=10, b=10, l=10, r=10),
                      xaxis=dict(visible=False), yaxis=dict(visible=False),
                      legend=dict(orientation="h", y=-0.05), plot_bgcolor="rgba(0,0,0,0)")
    return fig


# ============================================================== pages
if page == "🏠 Ringkasan Situasi":
    st.title("🏠 Ringkasan Situasi Ruang Siber Sosial")
    st.caption("Gambaran operasi pengaruh terkoordinasi (Coordinated Inauthentic Behavior) yang terdeteksi pada data terkini.")

    involved = set(members_df[members_df["campaign_id"].isin([c["campaign_id"] for c in flagged])]["account_id"]) \
        if not members_df.empty else set()
    n_posts = len(posts_df)
    coord_posts = sum(c["post_count"] for c in flagged)
    k = st.columns(5)
    k[0].metric("Post dianalisis", f"{n_posts:,}")
    k[1].metric("Akun dianalisis", f"{posts_df['account_id'].nunique() if n_posts else 0:,}")
    k[2].metric("Campaign terdeteksi", len(flagged))
    k[3].metric("Risiko TINGGI", sum(c["risk_level"] == "TINGGI" for c in flagged))
    k[4].metric("Akun terlibat", len(involved),
                f"{len(involved) / max(posts_df['account_id'].nunique(), 1):.0%} dari total", delta_color="off")

    if n_posts:
        st.subheader("Timeline aktivitas")
        st.caption(f"{coord_posts} dari {n_posts} post ({coord_posts / n_posts:.1%}) berasal dari jaringan terkoordinasi. "
                   "Area merah = lonjakan aktivitas (robust z-score). Perhatikan: tidak semua lonjakan adalah operasi — "
                   "lonjakan organik (mis. berita gempa) tidak di-flag karena tidak ada koordinasi berulang.")
        st.plotly_chart(timeline_chart(posts_df), width="stretch")

    st.subheader("Campaign prioritas")
    if not flagged:
        st.info("Belum ada campaign terdeteksi. Buka **📥 Data & Deteksi** untuk memuat data dan menjalankan deteksi.")
    for c in flagged:
        with st.container(border=True):
            a, b, cc = st.columns([5, 1.2, 1.2])
            a.markdown(f"**{c['campaign_id']}** {risk_badge(c['risk_level'])} &nbsp; {STATUS_ICON.get(c['status'], '')} "
                       f"`{c['status']}`<br>{c['description']}<br><small>🏷️ {c['topic_keywords']}</small>",
                       unsafe_allow_html=True)
            b.metric("Skor", f"{c['flag_score']:.2f}")
            cc.metric("Akun / Post", f"{c['account_count']} / {c['post_count']}")
            st.progress(c["flag_score"])

elif page == "🔍 Investigasi Campaign":
    st.title("🔍 Investigasi Campaign")
    if not campaigns:
        st.info("Belum ada campaign.")
        st.stop()
    show_all = st.toggle("Tampilkan juga cluster yang skornya di bawah ambang (dismissed)", value=False)
    pool = campaigns if show_all else [c for c in campaigns if c["status"] != "dismissed"] or campaigns
    sel = st.selectbox("Pilih campaign", pool, format_func=campaign_label)
    c = db.get_campaign_by_id(sel["campaign_id"])
    accs = db.get_campaign_accounts(c["campaign_id"])
    cposts = db.get_posts_by_campaign(c["campaign_id"])
    edges = db.get_campaign_edges(c["campaign_id"])

    st.markdown(f"### {c['description']} &nbsp; {risk_badge(c['risk_level'])}", unsafe_allow_html=True)
    m = st.columns(5)
    m[0].metric("Skor koordinasi", f"{c['flag_score']:.2f}")
    m[1].metric("Akun", c["account_count"])
    m[2].metric("Post bukti", c["post_count"])
    m[3].metric("Mulai", c["first_seen"][5:16].replace("T", " "))
    m[4].metric("Status", f"{STATUS_ICON.get(c['status'], '')} {c['status']}")

    left, right = st.columns([1, 1.25])
    with left:
        st.markdown("#### Mengapa di-flag?")
        sig = c["signals"]
        cats = [SIGNAL_LABELS[k] for k in sig]
        fig = go.Figure(go.Scatterpolar(r=list(sig.values()) + [list(sig.values())[0]], theta=cats + [cats[0]],
                                        fill="toself", line_color=RISK_COLOR[c["risk_level"]]))
        fig.update_layout(polar=dict(radialaxis=dict(range=[0, 1], tickformat=".0%", tickfont_size=9)), height=320,
                          margin=dict(t=30, b=30, l=110, r=110), showlegend=False)
        st.plotly_chart(fig, width="stretch")
        contrib = pd.DataFrame({"Sinyal": cats, "Skor": list(sig.values()),
                                "Bobot": [Config.SCORING_WEIGHTS[k] for k in sig]})
        contrib["Kontribusi"] = contrib["Skor"] * contrib["Bobot"]
        st.dataframe(contrib.style.format({"Skor": "{:.0%}", "Bobot": "{:.0%}", "Kontribusi": "{:.3f}"}),
                     hide_index=True, width="stretch")
    with right:
        st.markdown("#### Temuan (explainable)")
        st.markdown("<ul class='expl'>" + "".join(f"<li>{e}</li>" for e in c["signal_summary"]) + "</ul>",
                    unsafe_allow_html=True)
        st.markdown("#### Pola sinkronisasi (barcode akun × waktu)")
        pdf = pd.DataFrame(cposts)
        pdf["ts"] = pd.to_datetime(pdf["timestamp"])
        fig = px.scatter(pdf, x="ts", y="account_id", hover_data={"content": True, "ts": True, "account_id": False},
                         height=320)
        fig.update_traces(marker=dict(symbol="line-ns-open", size=14, line=dict(width=2),
                                      color=RISK_COLOR[c["risk_level"]]))
        fig.update_layout(margin=dict(t=10, b=10), yaxis_title=None, xaxis_title=None,
                          yaxis=dict(showticklabels=len(accs) <= 20))
        st.plotly_chart(fig, width="stretch")
        st.caption("Garis vertikal yang sejajar = banyak akun memposting pada menit yang hampir sama, berulang kali.")

    t1, t2, t3, t4 = st.tabs(["🕸️ Jaringan akun", "📝 Konten bukti", "👤 Profil akun", "🗂️ Tindak lanjut & laporan"])
    with t1:
        meta = {a["account_id"]: {"group": "Hub (penggerak)" if a["role"] == "hub" else "Amplifier",
                                  "color": "#d62728" if a["role"] == "hub" else "#1f77b4",
                                  "hover": f"peran: {a['role']}<br>dibuat: {a['metadata'].get('created_at', '-')}"
                                           f"<br>follower: {a['metadata'].get('followers', '-')}"} for a in accs}
        fig = network_figure(edges, meta, height=460)
        if fig:
            st.plotly_chart(fig, width="stretch")
        st.caption("Edge = dua akun melakukan co-action (narasi mirip / URL sama / tagar langka) dalam ≤ "
                   f"{Config.COORDINATION_WINDOW_MIN} menit pada ≥ {Config.MIN_EDGE_WEIGHT} kesempatan berbeda.")
    with t2:
        q = st.text_input("Cari dalam konten bukti", "")
        view = pdf[pdf["content"].str.contains(q, case=False)] if q else pdf
        st.dataframe(view[["timestamp", "account_id", "content", "hashtags", "urls"]], hide_index=True,
                     width="stretch", height=380)
        st.download_button("📥 Unduh bukti (CSV)", view.to_csv(index=False), f"{c['campaign_id']}_bukti.csv", "text/csv")
    with t3:
        adf = pd.DataFrame([{"akun": a["account_id"], "peran": a["role"], "derajat": a["degree"],
                             "dibuat": a["metadata"].get("created_at"), "follower": a["metadata"].get("followers"),
                             "following": a["metadata"].get("following")} for a in accs])
        st.dataframe(adf, hide_index=True, width="stretch")
        if adf["dibuat"].notna().any():
            fig = px.histogram(adf, x="dibuat", nbins=20, height=240, title="Tanggal pembuatan akun")
            fig.update_layout(margin=dict(t=40, b=10))
            st.plotly_chart(fig, width="stretch")
            st.caption("Akun yang dibuat dalam rentang sempit adalah indikator kuat sockpuppet/akun pesanan.")
    with t4:
        with st.form("triage"):
            new_status = st.radio("Keputusan analis", ["flagged", "reviewed", "escalated", "dismissed"],
                                  index=["flagged", "reviewed", "escalated", "dismissed"].index(c["status"])
                                  if c["status"] in ("flagged", "reviewed", "escalated", "dismissed") else 0,
                                  horizontal=True,
                                  format_func=lambda s: {"flagged": "🔴 Perlu review", "reviewed": "🟡 Sudah direview",
                                                         "escalated": "🚨 Eskalasi", "dismissed": "⚪ Bukan ancaman"}[s])
            note = st.text_area("Catatan analis", c.get("analyst_note") or "")
            if st.form_submit_button("💾 Simpan keputusan"):
                db.update_campaign_status(c["campaign_id"], new_status, note)
                st.success("Keputusan tersimpan.")
                st.rerun()
        brief = campaign_brief(c, accs, cposts)
        st.download_button("📄 Unduh Laporan Intelijen (Markdown)", brief, f"laporan_{c['campaign_id']}.md",
                           "text/markdown", type="primary")
        with st.expander("Pratinjau laporan"):
            st.markdown(brief)

elif page == "🕸️ Peta Jaringan":
    st.title("🕸️ Peta Jaringan Koordinasi")
    st.caption("Seluruh akun yang terlibat co-action berulang. Warna = campaign hasil community detection (Louvain).")
    meta, edges = {}, []
    for c in campaigns:
        if c["status"] == "dismissed" and not st.session_state.get("net_all"):
            continue
        for a in db.get_campaign_accounts(c["campaign_id"]):
            meta[a["account_id"]] = {"group": f"{c['campaign_id']} ({c['risk_level']})",
                                     "color": camp_color[c["campaign_id"]],
                                     "hover": f"{c['description']}<br>peran: {a['role']}"}
        edges += db.get_campaign_edges(c["campaign_id"])
    st.toggle("Tampilkan cluster dismissed", key="net_all")
    fig = network_figure(edges, meta, height=640)
    if fig:
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("Belum ada jaringan terdeteksi.")

elif page == "📥 Data & Deteksi":
    st.title("📥 Data & Deteksi")
    st.markdown(f"Database saat ini: **{db.count('posts'):,} post** dari **{db.count('accounts'):,} akun**.")
    tab1, tab2, tab3 = st.tabs(["🧪 Dataset skenario (sintetis berlabel)", "📤 Unggah dataset sendiri",
                                "⚙️ Parameter deteksi"])
    with tab1:
        st.markdown("Dataset sintetis meniru 3 operasi pengaruh nyata yang relevan bagi TNI AD "
                    "(**hoaks rekrutmen jalur khusus**, **astroturfing tagar BBM**, **phishing bansos**) "
                    "di tengah ~1.300 post organik + **event viral organik (gempa)** sebagai jebakan false-positive. "
                    "Semua akun/URL fiktif — tidak memakai data pribadi pihak ketiga.")
        c1, c2 = st.columns(2)
        seed = c1.number_input("Seed", 0, 99999, 42)
        diff = c2.slider("Tingkat kesulitan (penyamaran operasi)", 0.0, 1.0, 0.0, 0.1)
        if st.button("Muat dataset & jalankan deteksi", type="primary"):
            posts, accounts = generate_synthetic_dataset(seed=int(seed), difficulty=diff)
            ingest(posts, accounts, db)
            DetectionEngine(db).run_detection_pipeline(verbose=False)
            st.success(f"{len(posts)} post dimuat dan dianalisis.")
            st.rerun()
    with tab2:
        st.markdown("Format: CSV / JSON / JSONL. Kolom dikenali otomatis: "
                    "`text|content|full_text`, `username|author|user_screen_name`, `created_at|timestamp|date`, "
                    "opsional `user_created_at`, `followers_count`. Contoh: `data/raw/sample_social_posts.csv`.")
        up = st.file_uploader("Pilih file", type=["csv", "json", "jsonl"])
        if up is not None and st.button("Proses file", type="primary"):
            try:
                if up.name.endswith(".csv"):
                    df = pd.read_csv(up)
                else:
                    df = pd.read_json(up, lines=up.name.endswith(".jsonl"))
                posts, accounts = load_dataframe(df, platform=Path(up.name).stem)
                ingest(posts, accounts, db)
                DetectionEngine(db).run_detection_pipeline(verbose=False)
                st.success(f"{len(posts)} post dari {len(accounts)} akun berhasil dianalisis.")
                st.rerun()
            except Exception as e:  # tampilkan error yang ramah untuk analis
                st.error(f"Gagal memproses file: {e}")
    with tab3:
        st.markdown("Atur sensitivitas deteksi lalu jalankan ulang (berlaku untuk sesi ini).")
        sim = st.slider("Ambang kemiripan narasi (cosine)", 0.3, 0.95, Config.SIMILARITY_THRESHOLD, 0.05)
        win = st.slider("Jendela koordinasi (menit)", 5, 120, Config.COORDINATION_WINDOW_MIN, 5)
        rep = st.slider("Minimal pengulangan co-action", 1.0, 5.0, float(Config.MIN_EDGE_WEIGHT), 0.5)
        thr = st.slider("Ambang flag", 0.3, 0.9, Config.FLAG_THRESHOLD, 0.05)
        if st.button("Jalankan dengan parameter ini"):
            Cfg = type("RuntimeConfig", (Config,), {"SIMILARITY_THRESHOLD": sim, "COORDINATION_WINDOW_MIN": win,
                                                    "MIN_EDGE_WEIGHT": rep, "FLAG_THRESHOLD": thr})
            camps = DetectionEngine(db, config=Cfg).run_detection_pipeline(verbose=False)
            st.success(f"Selesai: {sum(c['status'] == 'flagged' for c in camps)} campaign di-flag.")
            st.rerun()

elif page == "📈 Evaluasi Akurasi":
    st.title("📈 Evaluasi Akurasi (Ground Truth)")
    st.markdown("Akurasi diukur di level akun terhadap label ground-truth dataset sintetis, dibandingkan dengan dua "
                "pendekatan yang umum dipakai dashboard monitoring biasa:\n"
                "- **Baseline A – Burst monitor**: flag semua akun yang posting saat terjadi lonjakan volume.\n"
                "- **Baseline B – Duplicate filter**: flag akun yang memposting teks identik dengan akun lain.\n\n"
                "**Tingkat kesulitan** mensimulasikan operator yang lebih rapi (jeda antar akun lebih lebar, "
                "partisipasi tiap gelombang lebih rendah).")
    bench = Path(__file__).resolve().parent.parent / "docs" / "benchmark.md"
    if st.button("▶️ Jalankan benchmark (5 seed × 3 tingkat kesulitan, ±10 detik)", type="primary"):
        from evaluation import run_benchmark
        with st.spinner("Menjalankan benchmark..."):
            st.session_state["bench"] = pd.DataFrame(run_benchmark())
    if "bench" in st.session_state:
        b = st.session_state["bench"]
        fig = px.bar(b, x="difficulty", y="f1", color="method", barmode="group", height=380,
                     labels={"difficulty": "Tingkat kesulitan", "f1": "F1-score", "method": "Metode"},
                     color_discrete_sequence=["#d62728", "#95a5a6", "#bdc3c7"])
        fig.update_layout(yaxis_tickformat=".0%", legend=dict(orientation="h", y=-0.25))
        st.plotly_chart(fig, width="stretch")
        st.dataframe(b.style.format({"difficulty": "{:.1f}", "precision": "{:.1%}", "recall": "{:.1%}", "f1": "{:.1%}"}),
                     hide_index=True, width="stretch")
    elif bench.exists():
        st.markdown(bench.read_text())

elif page == "🌐 Data Lapangan (Live)":
    from connectors import ScrapeCreators, get_scrapecreators_key, mastodon_hashtag, to_sentinel, viral_index

    st.title("🌐 Data Lapangan — Tarik Data Publik Nyata")
    st.caption("Tarik post publik terbaru dari media sosial berdasarkan kata kunci/tagar, ukur **Indeks Potensi "
               "Viral**, lalu jalankan deteksi koordinasi pada data nyata tersebut.")
    key = get_scrapecreators_key()
    sources = ["ScrapeCreators (TikTok, X, Threads, YouTube, Instagram)"] if key else []
    sources.append("Mastodon (gratis, tanpa API key)")
    c1, c2 = st.columns([2, 1])
    source = c1.radio("Sumber data", sources, horizontal=True)
    if not key:
        c1.caption("🔑 ScrapeCreators belum aktif — tambahkan `SCRAPECREATORS_API_KEY` di Streamlit Secrets "
                   "untuk TikTok/X/Threads/YouTube/Instagram.")
    mask = c2.toggle("🕶️ Mode Presentasi (samarkan identitas)", value=True,
                     help="Username diganti kode anonim & avatar/URL tidak disimpan. Wajib aktif saat rekam video/screenshot.")

    if source.startswith("ScrapeCreators"):
        sc = ScrapeCreators(key)
        query = st.text_input("Kata kunci / tagar", "jalur khusus bintara")
        plats = st.multiselect("Platform", list(ScrapeCreators.PLATFORMS), default=["tiktok", "twitter", "youtube"],
                               format_func=ScrapeCreators.PLATFORMS.get)
        pages = st.slider("Halaman per platform (1 halaman = 1 kredit)", 1, 5, 1)
        st.caption(f"Perkiraan biaya: {len(plats) * pages} kredit.")
    else:
        query = st.text_input("Tagar Mastodon (tanpa #)", "indonesia")
        instance = st.text_input("Instance", "mastodon.social")
        pages = st.slider("Halaman (40 post/halaman)", 1, 10, 3)

    if st.button("📡 Tarik data", type="primary"):
        raw, errors = [], []
        with st.spinner("Menarik data publik..."):
            if source.startswith("ScrapeCreators"):
                for pf in plats:
                    try:
                        raw += sc.search(pf, query, pages=pages)
                    except Exception as e:
                        errors.append(f"{ScrapeCreators.PLATFORMS[pf]}: {e}")
            else:
                try:
                    raw = mastodon_hashtag(query, instance=instance, pages=pages)
                except Exception as e:
                    errors.append(str(e))
        st.session_state["live_raw"], st.session_state["live_query"] = raw, query
        for e in errors:
            st.warning(e)
        if source.startswith("ScrapeCreators") and sc.credits_remaining is not None:
            st.info(f"Sisa kredit ScrapeCreators: {sc.credits_remaining}")

    raw = st.session_state.get("live_raw")
    if raw is not None:
        if not raw:
            st.warning("Tidak ada post ditemukan untuk kata kunci ini.")
            st.stop()
        vi = viral_index(raw)
        st.subheader(f"Hasil: “{st.session_state['live_query']}”")
        m = st.columns(5)
        m[0].metric("Indeks Potensi Viral", f"{vi['score']}/100")
        m[1].metric("Status", vi["label"])
        m[2].metric("Perkiraan jangkauan", f"{vi['reach']:,}")
        m[3].metric("Platform", vi["platforms"])
        m[4].metric("Akun besar (≥100rb)", vi["big_accounts"])
        st.caption("Indeks = kecepatan tayangan/jam (40%) + jangkauan total (25%) + sebaran lintas platform (15%) "
                   "+ keterlibatan akun besar (20%). Bila platform tidak memberi jumlah tayangan, diestimasi dari interaksi.")
        posts, accounts = to_sentinel(raw, mask=mask)
        ldf = pd.DataFrame([{**{k: p[k] for k in ("timestamp", "platform", "account_id", "content")},
                             **{k: p["metadata"].get(k) for k in ("views", "likes", "shares", "comments")}}
                            for p in posts]).sort_values("timestamp")
        ldf["ts"] = pd.to_datetime(ldf["timestamp"])
        fig = px.histogram(ldf, x="ts", color="platform", nbins=40, height=260)
        fig.update_layout(margin=dict(t=10, b=10), xaxis_title=None, yaxis_title="post",
                          legend=dict(orientation="h", y=-0.3))
        st.plotly_chart(fig, width="stretch")
        st.dataframe(ldf.drop(columns="ts"), hide_index=True, width="stretch", height=300)
        st.caption(f"{len(posts)} post dari {len(accounts)} akun. Data hanya berasal dari konten publik.")
        if st.button("🔎 Analisis koordinasi pada data ini (menggantikan data di database)"):
            ingest(posts, accounts, db)
            camps = DetectionEngine(db).run_detection_pipeline(verbose=False)
            st.session_state.pop("live_raw")
            st.success(f"Selesai: {sum(c['status'] == 'flagged' for c in camps)} campaign di-flag dari "
                       f"{len(camps)} cluster. Buka 🏠 Ringkasan / 🔍 Investigasi untuk melihat hasil.")

else:
    st.title("ℹ️ Metodologi")
    st.markdown(f"""
**{Config.APP_NAME}** mendeteksi *perilaku terkoordinasi*, bukan opini. Sistem tidak menilai benar/salahnya isi
post maupun sikap politik — yang dinilai adalah **apakah sekelompok akun bertindak secara tidak autentik dan
terorkestrasi**. Pendekatan ini sejalan dengan definisi *Coordinated Inauthentic Behavior* yang dipakai platform
global, dan menjaga netralitas institusi.

| Tahap | Teknik | Tujuan |
|---|---|---|
| 1. Normalisasi | Kamus slang medsos Indonesia (yg→yang, gak→tidak, …), hapus URL/emoji | Menyamakan variasi ejaan operator |
| 2. Representasi | TF-IDF **char n-gram (3–5)** | Tahan typo & parafrase ringan; ringan tanpa GPU |
| 3. Co-action | Sliding window ≤ {Config.COORDINATION_WINDOW_MIN} menit: narasi mirip (cos ≥ {Config.SIMILARITY_THRESHOLD}), URL sama, tagar langka sama | Menangkap aksi serentak |
| 4. Graf koordinasi | Edge hanya bila co-action **berulang ≥ {Config.MIN_EDGE_WEIGHT} episode** | Menyaring kebetulan & event viral organik |
| 5. Clustering | Louvain community detection + k-core (k=2) | Memisahkan operasi berbeda, buang akun "nyangkut" |
| 6. Scoring | 5 sinyal berbobot: konten {Config.SCORING_WEIGHTS['content']:.0%}, timing {Config.SCORING_WEIGHTS['timing']:.0%}, akun {Config.SCORING_WEIGHTS['account']:.0%}, jaringan {Config.SCORING_WEIGHTS['network']:.0%}, amplifikasi {Config.SCORING_WEIGHTS['amplification']:.0%} | Skor yang bisa dijelaskan ke pimpinan |
| 7. Triage | Status flagged → reviewed / escalated / dismissed + catatan + laporan | Human-in-the-loop |

**Prinsip desain**
- *Explainable*: setiap skor disertai alasan berbahasa Indonesia & bukti konten.
- *Human-in-the-loop*: sistem merekomendasikan, analis memutuskan.
- *Ringan & on-premise*: berjalan di laptop tanpa GPU/internet, cocok untuk jaringan tertutup satuan.
- *Privasi*: demo memakai data sintetis; data nyata cukup berupa post publik.
""")

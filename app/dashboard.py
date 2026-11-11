# SENTINEL — Streamlit Dashboard
# Coordinated Campaign & Astroturfing Detection Platform
# Kartika Cyber Hackathon 2026 · Kategori: Siber Sosial
#
# Jalankan:  streamlit run app/dashboard.py
#
# Alur analis: Sumber data -> Ancaman (antrean terurut) -> Kasus (bukti, jaringan,
# akun) -> Tindakan & laporan. Desain mengikuti metode unslop
# (github.com/heydamir/unslop, CC BY 4.0 — Damir Sokolovsky).

import hashlib
import sys
import urllib.parse
from pathlib import Path

import networkx as nx
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from config import Config  # noqa: E402
from data_ingestion import generate_synthetic_dataset, ingest, load_dataframe  # noqa: E402
from database import Database  # noqa: E402
from detection_engine import SIGNAL_LABELS, DetectionEngine  # noqa: E402
from feature_extraction import FeatureExtractor, parse_ts  # noqa: E402
from report import campaign_brief  # noqa: E402

st.set_page_config(page_title="SENTINEL", page_icon=":material/radar:", layout="wide",
                   initial_sidebar_state="expanded")

# ============================================================== design tokens
BG, CARD, RAISED = "#141415", "#19191b", "#232325"
TEXT, TEXT_2, MUTED = "#ededed", "#a1a1a6", "#85858b"
HAIR = "rgba(237,237,237,0.08)"
ACCENT = "#e0a040"          # amber sinyal — hanya untuk hal terpenting
HIGH = "#e5484d"            # risiko tinggi
NEUTRAL_1, NEUTRAL_2 = "#5c5c63", "#38383d"
RISK_COLOR = {"TINGGI": HIGH, "SEDANG": ACCENT, "RENDAH": MUTED}
RISK_LABEL = {"TINGGI": "Risiko tinggi", "SEDANG": "Risiko sedang", "RENDAH": "Risiko rendah"}
STATUS_LABEL = {"flagged": "Perlu review", "reviewed": "Sudah direview", "escalated": "Dieskalasi",
                "dismissed": "Bukan ancaman"}

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap');
html, body, .stApp, p, li, label, input, textarea, button, h1, h2, h3, h4, td, th,
[data-testid="stMarkdownContainer"], [data-testid="stMetricLabel"] {{
  font-family: 'IBM Plex Sans', system-ui, sans-serif;
}}
[data-testid="stIconMaterial"] {{ font-family: 'Material Symbols Rounded' !important; }}
.block-container {{ padding-top: 2rem; padding-bottom: 4rem; max-width: 1480px; }}
h1 {{ font-size: 28px !important; font-weight: 500 !important; letter-spacing: -0.01em; }}
h2, h3 {{ font-weight: 500 !important; }}
h3 {{ font-size: 16px !important; color: {TEXT}; }}
.mono, code {{ font-family: 'IBM Plex Mono', ui-monospace, monospace; font-variant-numeric: tabular-nums; }}
.sub {{ color: {TEXT_2}; font-size: 14px; margin-top: -8px; margin-bottom: 24px; }}
.meta {{ color: {MUTED}; font-size: 12px; font-family: 'IBM Plex Mono', monospace; }}
[data-testid="stMetricValue"] {{ font-family: 'IBM Plex Mono', monospace; font-size: 28px;
  font-weight: 500; font-variant-numeric: tabular-nums; }}
[data-testid="stMetricLabel"] p {{ color: {TEXT_2}; font-size: 13px; }}
[data-testid="stMetric"] {{ background: {CARD}; border: 1px solid {HAIR}; border-radius: 12px; padding: 16px 20px; }}
[data-testid="stSidebar"] {{ background: #0f0f10; border-right: 1px solid {HAIR}; }}
button[kind="primary"] {{ background: {TEXT} !important; color: {BG} !important; border: none !important;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.12); }}
button[kind="primary"]:hover {{ background: #ffffff !important; }}
.dot {{ display:inline-block; width:8px; height:8px; border-radius:4px; margin-right:8px; vertical-align:middle; }}
.case-id {{ font-family:'IBM Plex Mono', monospace; font-size:13px; color:{TEXT_2};
  border:1px solid {HAIR}; border-radius:6px; padding:2px 8px; }}
.status-line {{ display:flex; gap:24px; align-items:center; background:{CARD}; border:1px solid {HAIR};
  border-radius:12px; padding:12px 20px; margin-bottom:16px; font-size:14px; color:{TEXT_2}; }}
.status-line b {{ color:{TEXT}; font-weight:500; }}
.sig {{ margin-bottom:12px; }}
.sig-row {{ display:flex; justify-content:space-between; font-size:13px; color:{TEXT_2}; margin-bottom:4px; }}
.sig-row .mono {{ color:{TEXT}; }}
.bar {{ height:4px; background:{RAISED}; border-radius:2px; overflow:hidden; }}
.bar i {{ display:block; height:4px; border-radius:2px; }}
.score {{ font-family:'IBM Plex Mono', monospace; font-size:44px; font-weight:500; line-height:1; }}
.findings li {{ color:{TEXT_2}; font-size:14px; margin-bottom:8px; line-height:20px; }}
.panel {{ background:{CARD}; border:1px solid {HAIR}; border-radius:14px; padding:20px 24px; }}
</style>""", unsafe_allow_html=True)


# ============================================================== data
@st.cache_resource
def get_db():
    db = Database()
    if db.count("posts") == 0:  # first run: siapkan data skenario otomatis
        ingest(*generate_synthetic_dataset(seed=42), db)
        DetectionEngine(db).run_detection_pipeline(verbose=False)
    return db


db = get_db()
posts_df = pd.DataFrame(db.get_all_posts())
if not posts_df.empty:
    posts_df["ts"] = pd.to_datetime(posts_df["timestamp"])
campaigns = db.get_campaigns()
active = [c for c in campaigns if c["status"] != "dismissed"]
members_df = pd.DataFrame(db.get_all_campaign_accounts())


# ============================================================== helpers
def plot_layout(fig, height):
    fig.update_layout(
        height=height, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="IBM Plex Sans, sans-serif", color=TEXT_2, size=12),
        margin=dict(t=8, b=8, l=8, r=8), hoverlabel=dict(bgcolor=RAISED, font_family="IBM Plex Mono"),
        legend=dict(orientation="h", y=-0.18, x=0, font=dict(size=12)),
        xaxis=dict(gridcolor=HAIR, zeroline=False, tickfont=dict(family="IBM Plex Mono", size=11, color=MUTED)),
        yaxis=dict(gridcolor=HAIR, zeroline=False, tickfont=dict(family="IBM Plex Mono", size=11, color=MUTED)))
    return fig


def avatar(account_id):
    """Avatar inisial buatan (bukan foto asli) — aman untuk presentasi."""
    name = account_id.split(":")[-1]
    letters = "".join(ch for ch in name if ch.isalpha())[:2].upper() or "?"
    tone = ["#2a2a2e", "#323238", "#3a3a40", "#26262a"][int(hashlib.sha1(name.encode()).hexdigest(), 16) % 4]
    svg = (f"<svg xmlns='http://www.w3.org/2000/svg' width='32' height='32'><circle cx='16' cy='16' r='16' "
           f"fill='{tone}'/><text x='16' y='20.5' font-family='IBM Plex Sans,Arial' font-size='12' "
           f"text-anchor='middle' fill='#ededed'>{letters}</text></svg>")
    return "data:image/svg+xml;utf8," + urllib.parse.quote(svg)


def dot(color):
    return f"<span class='dot' style='background:{color}'></span>"


def fmt_ts(s):
    return s[:16].replace("T", " ") if s else "-"


def threat_level():
    high = sum(c["risk_level"] == "TINGGI" for c in active)
    if high:
        return "Siaga", HIGH
    if active:
        return "Waspada", ACCENT
    return "Normal", "#4cc38a"


def data_source_line():
    if posts_df.empty:
        return "Belum ada data"
    src = posts_df["platform"].replace({"sample": "skenario demo"}).value_counts()
    return ", ".join(f"{k} {v:,}" for k, v in src.items())


def run_detection(config=Config):
    return DetectionEngine(db, config=config).run_detection_pipeline(verbose=False)


# ============================================================== page: Ancaman
def page_threats():
    st.title("Ancaman aktif")
    if posts_df.empty:
        st.info("Belum ada data. Buka Sumber data untuk memuat skenario demo atau menarik data live")
        return
    t0, t1 = posts_df["ts"].min(), posts_df["ts"].max()
    st.markdown(f"<div class='sub'>Operasi pengaruh terkoordinasi yang terdeteksi pada "
                f"{t0:%d %b %Y} – {t1:%d %b %Y}, diurutkan dari yang paling berisiko</div>",
                unsafe_allow_html=True)

    level, color = threat_level()
    high = sum(c["risk_level"] == "TINGGI" for c in active)
    mid = sum(c["risk_level"] == "SEDANG" for c in active)
    st.markdown(f"<div class='status-line'><span>{dot(color)}<b>Status {level}</b></span>"
                f"<span>{high} risiko tinggi · {mid} risiko sedang</span>"
                f"<span class='meta'>sumber: {data_source_line()}</span></div>", unsafe_allow_html=True)

    involved = set(members_df[members_df["campaign_id"].isin([c["campaign_id"] for c in active])]["account_id"]) \
        if not members_df.empty else set()
    n_acc = posts_df["account_id"].nunique()
    coord_posts = sum(c["post_count"] for c in active)
    k = st.columns(4)
    k[0].metric("Post dianalisis", f"{len(posts_df):,}")
    k[1].metric("Akun dianalisis", f"{n_acc:,}")
    k[2].metric("Campaign aktif", len(active))
    k[3].metric("Akun terlibat", f"{len(involved):,}  ·  {len(involved) / max(n_acc, 1):.0%}")

    st.markdown("### Aktivitas per jam")
    st.plotly_chart(timeline_chart(), width="stretch", config={"displayModeBar": False})
    note = (" Lonjakan besar tanpa warna adalah percakapan organik, misalnya berita gempa, dan sengaja tidak "
            "ditandai karena tidak ada koordinasi berulang.") if "sample" in set(posts_df["platform"]) else ""
    st.caption(f"{coord_posts:,} dari {len(posts_df):,} post ({coord_posts / len(posts_df):.1%}) berasal dari "
               f"jaringan terkoordinasi. Pita terang menandai lonjakan volume.{note}")

    st.markdown("### Antrean kasus")
    show_all = st.toggle("Tampilkan juga cluster di bawah ambang", value=False)
    rows = campaigns if show_all else active
    if not rows:
        st.success("Tidak ada jaringan terkoordinasi pada data ini")
        return
    q = pd.DataFrame([{
        "ID": c["campaign_id"], "Risiko": RISK_LABEL[c["risk_level"]], "Skor": c["flag_score"],
        "Pola": c["description"], "Akun": c["account_count"], "Post": c["post_count"],
        "Mulai": fmt_ts(c["first_seen"]), "Status": STATUS_LABEL.get(c["status"], c["status"])} for c in rows])
    ev = st.dataframe(q, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
                      key="queue", column_config={
                          "Skor": st.column_config.ProgressColumn("Skor", min_value=0, max_value=1, format="%.2f"),
                          "Pola": st.column_config.TextColumn("Pola", width="medium")})
    st.caption("Pilih satu baris untuk membuka berkas kasus")
    if ev.selection.rows:
        st.session_state["case_id"] = q.iloc[ev.selection.rows[0]]["ID"]
        st.switch_page(PAGES["kasus"])


def timeline_chart():
    shown = {c["campaign_id"]: c["risk_level"] for c in active}
    cp = pd.read_sql("SELECT campaign_id, post_id FROM campaign_posts", db.conn)
    cp = cp[cp["campaign_id"].isin(shown)].drop_duplicates("post_id")
    d = posts_df.merge(cp, on="post_id", how="left")
    d["kelas"] = d["campaign_id"].map(shown).map({"TINGGI": "Terkoordinasi · risiko tinggi",
                                                  "SEDANG": "Terkoordinasi · risiko sedang"}).fillna("Organik")
    d["jam"] = d["ts"].dt.floor("h")
    g = d.groupby(["jam", "kelas"]).size().unstack(fill_value=0)
    fig = go.Figure()
    for name, color in [("Organik", NEUTRAL_2), ("Terkoordinasi · risiko sedang", ACCENT),
                        ("Terkoordinasi · risiko tinggi", HIGH)]:
        if name in g:
            fig.add_bar(x=g.index, y=g[name], name=name, marker_color=color, marker_line_width=0,
                        width=3600 * 1000 * 0.85, hovertemplate="%{x|%d %b %H:00}<br>%{y} post<extra>" + name + "</extra>")
    starts, series = FeatureExtractor.hourly_activity(posts_df.to_dict("records"))
    for b in FeatureExtractor.detect_bursts(starts, series):
        fig.add_vrect(x0=b["window_start"], x1=pd.Timestamp(b["window_start"]) + pd.Timedelta(hours=1),
                      fillcolor=TEXT, opacity=0.05, line_width=0)
    fig.update_layout(barmode="stack", bargap=0)
    return plot_layout(fig, 320)


# ============================================================== page: Kasus
def page_case():
    st.title("Berkas kasus")
    if not campaigns:
        st.info("Belum ada kasus. Jalankan deteksi dari Sumber data")
        return
    ids = [c["campaign_id"] for c in campaigns]
    default = st.session_state.get("case_id")
    idx = ids.index(default) if default in ids else 0
    by_id = {c["campaign_id"]: c for c in campaigns}
    cid = st.selectbox("Kasus", ids, index=idx, label_visibility="collapsed",
                       format_func=lambda i: f"{i}  ·  {RISK_LABEL[by_id[i]['risk_level']]}  ·  {by_id[i]['description']}")
    st.session_state["case_id"] = cid
    c = db.get_campaign_by_id(cid)
    accs = db.get_campaign_accounts(cid)
    cposts = pd.DataFrame(db.get_posts_by_campaign(cid))
    cposts["ts"] = pd.to_datetime(cposts["timestamp"])
    edges = db.get_campaign_edges(cid)
    color = RISK_COLOR[c["risk_level"]]

    st.markdown(f"<div style='margin:16px 0 4px'><span class='case-id'>{cid}</span></div>"
                f"<h2 style='font-size:22px;margin:8px 0 4px'>{c['description']}</h2>"
                f"<div class='meta'>{dot(color)}{RISK_LABEL[c['risk_level']]} · {c['account_count']} akun · "
                f"{c['post_count']} post · {fmt_ts(c['first_seen'])} → {fmt_ts(c['last_seen'])} · "
                f"status: {STATUS_LABEL.get(c['status'], c['status'])}</div>", unsafe_allow_html=True)
    st.write("")

    left, right = st.columns([2, 1], gap="large")
    with left:
        st.markdown("### Pola sinkronisasi")
        fig = go.Figure(go.Scatter(
            x=cposts["ts"], y=cposts["account_id"].str.split(":").str[-1], mode="markers",
            marker=dict(symbol="line-ns-open", size=16, color=color, line=dict(width=2, color=color)),
            customdata=cposts["content"].str.slice(0, 90),
            hovertemplate="%{y}<br>%{x|%d %b %H:%M}<br>%{customdata}<extra></extra>"))
        plot_layout(fig, 380)
        fig.update_yaxes(showticklabels=len(accs) <= 24, gridcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        st.caption("Setiap garis adalah satu post. Garis yang berbaris vertikal berarti banyak akun memposting "
                   "pada menit yang hampir sama, dan pola itu berulang di beberapa gelombang")
    with right:
        st.markdown("### Kenapa ditandai")
        st.markdown(f"<div class='score' style='color:{color}'>{c['flag_score']:.2f}</div>"
                    f"<div class='meta' style='margin:4px 0 20px'>skor koordinasi · ambang {Config.FLAG_THRESHOLD}</div>",
                    unsafe_allow_html=True)
        sig = c["signals"]
        contrib = {k: v * Config.SCORING_WEIGHTS[k] for k, v in sig.items()}
        lead = max(contrib, key=contrib.get)
        html = ""
        for k, v in sorted(sig.items(), key=lambda kv: -contrib[kv[0]]):
            html += (f"<div class='sig'><div class='sig-row'><span>{SIGNAL_LABELS[k]}</span>"
                     f"<span class='mono'>{v:.0%} <span style='color:{MUTED}'>× {Config.SCORING_WEIGHTS[k]:.0%}</span></span></div>"
                     f"<div class='bar'><i style='width:{v * 100:.0f}%;background:{ACCENT if k == lead else NEUTRAL_1}'></i></div></div>")
        st.markdown(html, unsafe_allow_html=True)

    st.markdown("### Temuan")
    st.markdown("<ul class='findings'>" + "".join(f"<li>{e}</li>" for e in c["signal_summary"]) + "</ul>",
                unsafe_allow_html=True)

    t1, t2, t3, t4 = st.tabs(["Bukti", "Jaringan", "Akun", "Tindakan dan laporan"])
    with t1:
        q = st.text_input("Cari", "", placeholder="Cari kata dalam konten bukti")
        view = cposts[cposts["content"].str.contains(q, case=False, regex=False)] if q else cposts
        view = view.assign(akun=view["account_id"].str.split(":").str[-1])
        st.dataframe(view[["timestamp", "akun", "content", "hashtags", "urls"]], hide_index=True, width="stretch",
                     height=360, column_config={"timestamp": "Waktu", "akun": "Akun", "content": st.column_config.TextColumn("Konten", width="large"),
                                                "hashtags": "Tagar", "urls": "URL"})
        csv = view.drop(columns=["ts"]).to_csv(index=False).encode()
        digest = hashlib.sha256(csv).hexdigest()
        a, b = st.columns([1, 3])
        a.download_button("Unduh bukti (CSV)", csv, f"{cid}_bukti.csv", "text/csv")
        b.markdown(f"<div class='meta' style='padding-top:10px'>SHA-256 {digest}</div>", unsafe_allow_html=True)
        st.caption("Sidik jari SHA-256 membuktikan berkas bukti tidak berubah sejak diunduh (chain of custody)")
    with t2:
        fig = network_figure(edges, {a["account_id"]: a["role"] for a in accs})
        if fig:
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        st.caption(f"Garis menghubungkan dua akun yang memposting narasi mirip, URL sama, atau tagar langka sama dalam "
                   f"≤ {Config.COORDINATION_WINDOW_MIN} menit pada sedikitnya {Config.MIN_EDGE_WEIGHT:g} kesempatan berbeda. "
                   f"Titik amber adalah penggerak (hub)")
    with t3:
        ref = posts_df["ts"].max().to_pydatetime()
        rows = []
        for a in accs:
            meta = a["metadata"] or {}
            aposts = posts_df[posts_df["account_id"] == a["account_id"]].to_dict("records")
            s, reasons = FeatureExtractor.account_anomaly(meta, aposts, ref)
            created = parse_ts(meta.get("created_at")) if meta.get("created_at") else None
            rows.append({"": avatar(a["account_id"]), "Akun": a["account_id"].split(":")[-1],
                         "Peran": "Penggerak" if a["role"] == "hub" else "Penguat",
                         "Umur akun": f"{(ref - created).days} hari" if created else "-",
                         "Follower": meta.get("followers"), "Anomali": s,
                         "Indikator": ", ".join(reasons) or "-"})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=420, column_config={
            "": st.column_config.ImageColumn("", width="small"),
            "Anomali": st.column_config.ProgressColumn("Anomali profil", min_value=0, max_value=1, format="%.2f"),
            "Indikator": st.column_config.TextColumn("Indikator", width="large")})
        st.caption("Avatar adalah inisial buatan, bukan foto profil asli")
    with t4:
        left, right = st.columns([1, 1], gap="large")
        with left:
            with st.form("triage"):
                opts = list(STATUS_LABEL)
                new_status = st.radio("Keputusan analis", opts, format_func=STATUS_LABEL.get,
                                      index=opts.index(c["status"]) if c["status"] in opts else 0)
                note = st.text_area("Catatan analis", c.get("analyst_note") or "", height=120)
                if st.form_submit_button("Simpan keputusan", type="primary"):
                    db.update_campaign_status(cid, new_status, note)
                    st.toast("Keputusan tersimpan")
                    st.rerun()
        with right:
            brief = campaign_brief(c, accs, cposts.drop(columns=["ts"]).to_dict("records"))
            st.markdown("Laporan intelijen singkat berisi ringkasan, indikator, akun penggerak, contoh bukti "
                        "dan rekomendasi tindak lanjut sesuai tingkat risiko")
            st.download_button("Unduh laporan (Markdown)", brief, f"laporan_{cid}.md", "text/markdown", type="primary")
            with st.expander("Pratinjau laporan"):
                st.markdown(brief)


def network_figure(edges, roles):
    G = nx.Graph()
    for e in edges:
        G.add_edge(e["source"], e["target"], weight=e["weight"])
    if G.number_of_nodes() == 0:
        return None
    pos = nx.spring_layout(G, seed=3, weight="weight", k=0.7)
    ex, ey = [], []
    for a, b in G.edges():
        ex += [pos[a][0], pos[b][0], None]
        ey += [pos[a][1], pos[b][1], None]
    fig = go.Figure(go.Scatter(x=ex, y=ey, mode="lines", line=dict(width=0.7, color="rgba(237,237,237,0.14)"),
                               hoverinfo="skip", showlegend=False))
    for role, name, col in [("amplifier", "Penguat", NEUTRAL_1), ("hub", "Penggerak", ACCENT)]:
        nodes = [n for n in G.nodes() if roles.get(n, "amplifier") == role]
        fig.add_trace(go.Scatter(
            x=[pos[n][0] for n in nodes], y=[pos[n][1] for n in nodes], mode="markers", name=name,
            marker=dict(size=[10 + 1.6 * G.degree(n) for n in nodes], color=col, line=dict(width=1, color=BG)),
            text=[n.split(":")[-1] for n in nodes], hovertemplate="%{text}<extra>" + name + "</extra>"))
    plot_layout(fig, 460)
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig



# ============================================================== page: Profil akun (buzzer detector)
def page_account():
    from buzzer import analyze_account, from_database, from_tiktok, rank_accounts
    from connectors import ScrapeCreators, get_scrapecreators_key, mask_identity

    st.title("Profil akun")
    st.markdown("<div class='sub'>Buzzer detector per akun. Menilai identitas, ritme posting, pola konten, "
                "kewajaran interaksi dan keterlibatan jaringan, lalu menjelaskan setiap alasannya</div>",
                unsafe_allow_html=True)
    key = get_scrapecreators_key()
    modes = ["Akun di data aktif"] + (["Cek akun TikTok"] if key else [])
    mode = st.segmented_control("Mode", modes, default=modes[0], label_visibility="collapsed")
    st.write("")
    result = None

    if mode == "Akun di data aktif":
        ranked = rank_accounts(db)
        if not ranked:
            st.info("Belum ada data. Muat data dari Sumber data")
            return
        top = pd.DataFrame(ranked[:15])
        top.insert(0, "", top["account_id"].map(avatar))
        top["Akun"] = top["account_id"].str.split(":").str[-1]
        st.markdown("### Akun paling mencurigakan")
        ev = st.dataframe(top[["", "Akun", "score", "verdict", "posts"]], hide_index=True, width="stretch",
                          on_select="rerun", selection_mode="single-row", key="acc_rank", height=300,
                          column_config={"": st.column_config.ImageColumn("", width="small"),
                                         "score": st.column_config.ProgressColumn("Skor buzzer", min_value=0,
                                                                                  max_value=100, format="%d"),
                                         "verdict": "Penilaian", "posts": "Post"})
        ids = [r["account_id"] for r in ranked]
        pick = top.iloc[ev.selection.rows[0]]["account_id"] if ev.selection.rows else st.session_state.get("acc_id", ids[0])
        aid = st.selectbox("Atau cari akun", ids, index=ids.index(pick) if pick in ids else 0,
                           format_func=lambda i: i.split(":")[-1])
        st.session_state["acc_id"] = aid
        profile, aposts, mem = from_database(db, aid)
        result = (profile, aposts, analyze_account(profile, aposts, mem), aid)
    else:
        with st.container(border=True):
            c1, c2 = st.columns([3, 1])
            handle = c1.text_input("Username TikTok", placeholder="tanpa @")
            mask = c2.toggle("Mode presentasi", value=True, help="Samarkan username pada tampilan")
            c2.markdown("<div class='meta'>2 kredit per akun</div>", unsafe_allow_html=True)
            go_ = st.button("Analisis akun", type="primary", disabled=not handle)
        if go_ and handle:
            try:
                with st.spinner("Menarik profil dan video terbaru"):
                    profile, aposts = from_tiktok(ScrapeCreators(key), handle)
                st.session_state["acc_live"] = (profile, aposts, mask)
            except Exception as e:
                st.error(f"Gagal menganalisis akun: {e}")
        if "acc_live" in st.session_state:
            profile, aposts, mask = st.session_state["acc_live"]
            name = "tiktok:" + profile["username"]
            mem = [dict(r) for r in db.conn.execute(
                """SELECT c.campaign_id, c.description, c.flag_score, ca.role FROM campaign_accounts ca
                   JOIN campaigns c USING(campaign_id) WHERE ca.account_id=? AND c.status!='dismissed'""", (name,))]
            shown = "tiktok:" + mask_identity(name) if mask else name
            result = (profile, aposts, analyze_account(profile, aposts, mem), shown)
    if result:
        account_dossier(*result)


def account_dossier(profile, aposts, r, shown_id):
    band = r["risk"]
    color = RISK_COLOR[band]
    name = shown_id.split(":")[-1]
    created = parse_ts(profile.get("created_at")) if profile.get("created_at") else None
    facts = [f"{profile.get('followers'):,} follower" if profile.get("followers") is not None else None,
             f"mengikuti {profile.get('following'):,}" if profile.get("following") is not None else None,
             f"dibuat {created:%d %b %Y}" if created else None, f"{r['post_count']} post dianalisis"]
    st.divider()
    left, right = st.columns([1, 2], gap="large")
    with left:
        st.markdown(f"<div class='panel'><img src=\"{avatar(shown_id)}\" width='48' style='border-radius:24px'>"
                    f"<div style='font-size:18px;margin-top:12px'>{name}</div>"
                    f"<div class='meta' style='margin:4px 0 20px'>{' · '.join(f for f in facts if f)}</div>"
                    f"<div class='meta'>Skor buzzer</div>"
                    f"<div class='score' style='color:{color};margin:8px 0'>{r['score']}</div>"
                    f"<div style='font-size:15px;color:{TEXT}'>{r['verdict']}</div>"
                    f"<div class='meta' style='margin-top:12px'>{r['coverage']}</div></div>",
                    unsafe_allow_html=True)
    with right:
        st.markdown("### Sinyal")
        sig = r["signals"]
        avail = {k: v for k, v in sig.items() if v["score"] is not None}
        lead = max(avail, key=lambda k: avail[k]["score"] * avail[k]["weight"]) if avail else None
        html = ""
        for k, v in sig.items():
            val = v["score"]
            pct = "–" if val is None else f"{val:.0%}"
            width = 0 if val is None else val * 100
            html += (f"<div class='sig'><div class='sig-row'><span>{v['label']}</span>"
                     f"<span class='mono'>{pct} <span style='color:{MUTED}'>× {v['weight']:.0%}</span></span></div>"
                     f"<div class='bar'><i style='width:{width:.0f}%;background:{ACCENT if k == lead else NEUTRAL_1}'></i></div>"
                     f"<div class='meta' style='margin-top:4px'>{'; '.join(v['reasons'])}</div></div>")
        st.markdown(html, unsafe_allow_html=True)

    st.markdown("### Jam aktivitas")
    fig = go.Figure(go.Heatmap(z=r["heatmap"], x=[f"{h:02d}" for h in range(24)], y=["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"],
                               colorscale=[[0, CARD], [0.01, RAISED], [1, ACCENT]], showscale=False, xgap=2, ygap=2,
                               hovertemplate="%{y} %{x}:00 · %{z} post<extra></extra>"))
    plot_layout(fig, 220)
    fig.update_yaxes(autorange="reversed", gridcolor="rgba(0,0,0,0)")
    fig.update_xaxes(gridcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    st.caption("Akun manusia punya jam tidur. Kotak terisi merata di semua jam, termasuk dini hari, adalah ciri otomasi")

    st.markdown("### Post terbaru")
    pdf = pd.DataFrame([{"Waktu": fmt_ts(p["timestamp"]), "Konten": p["content"], "Tayangan": p.get("views"),
                         "Suka": p.get("likes")} for p in sorted(aposts, key=lambda p: p["timestamp"], reverse=True)])
    if not pdf.empty:
        pdf = pdf.dropna(axis=1, how="all")
        st.dataframe(pdf, hide_index=True, width="stretch", height=280,
                     column_config={"Konten": st.column_config.TextColumn("Konten", width="large")})
    st.caption("Skor berbasis aturan perilaku yang transparan, bukan model yang dilatih. Keputusan tetap pada analis")

# ============================================================== page: Sumber data
def page_sources():
    st.title("Sumber data")
    st.markdown(f"<div class='sub'>Data aktif: {data_source_line()}. Memuat sumber baru akan menggantikan data "
                f"ini untuk semua pengguna demo</div>", unsafe_allow_html=True)
    mode = st.segmented_control("Sumber", ["Data live", "Skenario demo", "Unggah file"], default="Data live",
                                label_visibility="collapsed")
    st.write("")
    if mode == "Data live":
        source_live()
    elif mode == "Skenario demo":
        source_demo()
    elif mode == "Unggah file":
        source_upload()

    st.divider()
    with st.expander("Parameter deteksi"):
        c1, c2 = st.columns(2)
        sim = c1.slider("Ambang kemiripan narasi (cosine)", 0.3, 0.95, Config.SIMILARITY_THRESHOLD, 0.05)
        win = c2.slider("Jendela koordinasi (menit)", 5, 120, Config.COORDINATION_WINDOW_MIN, 5)
        rep = c1.slider("Minimal pengulangan co-action", 1.0, 5.0, float(Config.MIN_EDGE_WEIGHT), 0.5)
        thr = c2.slider("Ambang flag", 0.3, 0.9, Config.FLAG_THRESHOLD, 0.05)
        if st.button("Jalankan ulang deteksi"):
            cfg = type("RuntimeConfig", (Config,), {"SIMILARITY_THRESHOLD": sim, "COORDINATION_WINDOW_MIN": win,
                                                    "MIN_EDGE_WEIGHT": rep, "FLAG_THRESHOLD": thr})
            run_detection(cfg)
            st.switch_page(PAGES["ancaman"])


def source_demo():
    st.markdown("Skenario berlabel yang meniru tiga operasi nyata: hoaks rekrutmen jalur khusus, astroturfing "
                "tagar BBM, dan phishing bansos, di tengah ±1.300 post organik dan satu event viral organik (gempa) "
                "sebagai jebakan alarm palsu. Semua akun dan URL fiktif")
    c1, c2 = st.columns(2)
    seed = c1.number_input("Seed", 0, 99999, 42)
    diff = c2.slider("Tingkat penyamaran operasi", 0.0, 1.0, 0.0, 0.1)
    if st.button("Muat skenario dan analisis", type="primary"):
        ingest(*generate_synthetic_dataset(seed=int(seed), difficulty=diff), db)
        run_detection()
        st.switch_page(PAGES["ancaman"])


def source_upload():
    st.markdown("CSV, JSON atau JSONL. Kolom dikenali otomatis: `text`, `username`, `created_at`, opsional "
                "`user_created_at` dan `followers_count`")
    up = st.file_uploader("File", type=["csv", "json", "jsonl"], label_visibility="collapsed")
    if up is not None and st.button("Proses file", type="primary"):
        try:
            df = pd.read_csv(up) if up.name.endswith(".csv") else pd.read_json(up, lines=up.name.endswith(".jsonl"))
            ingest(*load_dataframe(df, platform=Path(up.name).stem), db)
            run_detection()
            st.switch_page(PAGES["ancaman"])
        except Exception as e:  # pesan ramah untuk analis
            st.error(f"Gagal memproses file: {e}")


def source_live():
    from connectors import (ScrapeCreators, get_scrapecreators_key, mastodon_hashtag, suspicious_accounts,
                            to_sentinel, viral_index)
    key = get_scrapecreators_key()
    with st.container(border=True):
        c1, c2 = st.columns([3, 1])
        if key:
            query = c1.text_input("Kata kunci atau tagar", "jalur khusus bintara")
            plats = c1.multiselect("Platform", list(ScrapeCreators.PLATFORMS), default=["tiktok", "youtube"],
                                   format_func=ScrapeCreators.PLATFORMS.get)
            pages = c2.number_input("Halaman per platform", 1, 5, 1)
            c2.markdown(f"<div class='meta'>±{len(plats) * pages} kredit</div>", unsafe_allow_html=True)
        else:
            c1.caption("Kunci ScrapeCreators belum diatur, jadi hanya Mastodon yang tersedia")
            query = c1.text_input("Tagar Mastodon", "indonesia")
            pages = c2.number_input("Halaman", 1, 10, 3)
        mask = c2.toggle("Mode presentasi", value=True,
                         help="Username diganti kode anonim, avatar dan URL tidak disimpan")
        go_ = st.button("Tarik data", type="primary")

    if go_:
        raw, errors = [], []
        with st.spinner("Menarik post publik"):
            if key:
                sc = ScrapeCreators(key)
                for pf in plats:
                    try:
                        raw += sc.search(pf, query, pages=int(pages))
                    except Exception as e:
                        errors.append(f"{ScrapeCreators.PLATFORMS[pf]}: {e}")
            else:
                try:
                    raw = mastodon_hashtag(query, pages=int(pages))
                except Exception as e:
                    errors.append(str(e))
        st.session_state.update(live_raw=raw, live_query=query, live_mask=mask)
        for e in errors:
            st.warning(e)

    raw = st.session_state.get("live_raw")
    if raw is None:
        return
    if not raw:
        st.warning("Tidak ada post ditemukan untuk kata kunci ini")
        return
    vi = viral_index(raw)
    posts, accounts = to_sentinel(raw, mask=st.session_state.get("live_mask", True))
    st.markdown(f"### Hasil untuk “{st.session_state['live_query']}”")
    color = HIGH if vi["score"] >= 65 else ACCENT if vi["score"] >= 35 else MUTED
    left, right = st.columns([1, 2], gap="large")
    with left:
        st.markdown(f"<div class='panel'><div class='meta'>Indeks potensi viral</div>"
                    f"<div class='score' style='color:{color};margin:8px 0'>{vi['score']}</div>"
                    f"<div style='color:{TEXT};font-size:14px'>{vi['label']}</div>"
                    f"<div class='meta' style='margin-top:16px'>jangkauan ±{vi['reach']:,} tayangan<br>"
                    f"{vi['platforms']} platform · {vi['big_accounts']} akun ≥100rb follower<br>"
                    f"{len(posts)} post · {len(accounts)} akun</div></div>", unsafe_allow_html=True)
        st.caption("Kecepatan tayangan per jam 40%, jangkauan 25%, sebaran lintas platform 15%, "
                   "keterlibatan akun besar 20%")
    with right:
        ldf = pd.DataFrame([{"Waktu": fmt_ts(p["timestamp"]), "Platform": p["platform"],
                             "Akun": p["account_id"].split(":")[-1], "Konten": p["content"],
                             "Tayangan": p["metadata"].get("views"), "Suka": p["metadata"].get("likes")}
                            for p in posts]).sort_values("Tayangan", ascending=False, na_position="last")
        st.dataframe(ldf, hide_index=True, width="stretch", height=300,
                     column_config={"Konten": st.column_config.TextColumn("Konten", width="large")})

    acc_meta = {a["account_id"]: a["metadata"] for a in accounts}
    sus = suspicious_accounts([{**p, "_account": acc_meta[p["account_id"]]} for p in posts])
    st.markdown("### Akun tunggal mencurigakan")
    if sus:
        sdf = pd.DataFrame(sus)
        sdf.insert(0, "", sdf["account_id"].map(avatar))
        sdf["account_id"] = sdf["account_id"].str.split(":").str[-1]
        st.dataframe(sdf, hide_index=True, width="stretch", column_config={
            "": st.column_config.ImageColumn("", width="small"), "account_id": "Akun",
            "skor": st.column_config.ProgressColumn("Skor", min_value=0, max_value=1, format="%.2f"),
            "alasan": st.column_config.TextColumn("Alasan", width="large"), "contoh": "Contoh post"})
        st.caption("Akun yang membanjiri topik dengan narasi berulang. Ini melengkapi deteksi jaringan, "
                   "yang hanya menandai koordinasi antara tiga akun atau lebih")
    else:
        st.caption("Tidak ada akun tunggal dengan pola spam pada hasil ini")

    if st.button("Analisis koordinasi pada data ini", type="primary"):
        ingest(posts, accounts, db)
        run_detection()
        st.session_state.pop("live_raw", None)
        st.switch_page(PAGES["ancaman"])


# ============================================================== page: Metodologi
def page_method():
    st.title("Metodologi dan akurasi")
    st.markdown(f"<div class='sub'>{Config.APP_NAME} menilai perilaku terkoordinasi, bukan isi opini. Yang diukur "
                "adalah apakah sekelompok akun bertindak serentak, berulang dan seragam</div>", unsafe_allow_html=True)
    st.markdown(f"""
| Tahap | Teknik | Tujuan |
|---|---|---|
| Normalisasi | Kamus slang medsos Indonesia, hapus URL dan emoji | Menyamakan variasi ejaan operator |
| Representasi | TF-IDF char n-gram 3–5 | Tahan typo dan parafrase ringan, tanpa GPU |
| Co-action | Jendela ≤ {Config.COORDINATION_WINDOW_MIN} menit: narasi mirip, URL sama, tagar langka sama | Menangkap aksi serentak |
| Graf koordinasi | Garis hanya bila co-action berulang di ≥ {Config.MIN_EDGE_WEIGHT:g} episode | Menyaring kebetulan dan viral organik |
| Clustering | Louvain + 2-core | Memisahkan operasi, membuang akun yang ikut secara kebetulan |
| Skor | Konten {Config.SCORING_WEIGHTS['content']:.0%}, waktu {Config.SCORING_WEIGHTS['timing']:.0%}, akun {Config.SCORING_WEIGHTS['account']:.0%}, jaringan {Config.SCORING_WEIGHTS['network']:.0%}, amplifikasi {Config.SCORING_WEIGHTS['amplification']:.0%} | Skor yang bisa dijelaskan |
| Triage | Keputusan analis, catatan, laporan, hash bukti | Manusia tetap memutuskan |
""")
    st.markdown("### Akurasi terhadap ground truth")
    st.markdown("F1-score level akun pada skenario berlabel, rata-rata 5 seed per tingkat penyamaran, dibandingkan "
                "dua pendekatan umum: burst monitor (flag semua akun saat lonjakan volume) dan *duplicate filter* "
                "(flag akun yang memposting teks identik)")
    if st.button("Jalankan benchmark (±10 detik)"):
        from evaluation import run_benchmark
        with st.spinner("Menjalankan benchmark"):
            st.session_state["bench"] = pd.DataFrame(run_benchmark())
    b = st.session_state.get("bench")
    if b is None:
        b = pd.DataFrame([
            {"difficulty": d, "method": m, "f1": f} for d, vals in
            {0.0: (1.0, .2248, .3604), 0.5: (.9526, .1761, .3467), 1.0: (.68, .1631, .341)}.items()
            for m, f in zip(["SENTINEL", "Baseline A (burst monitor)", "Baseline B (duplicate filter)"], vals)])
        st.caption("Hasil tersimpan dari docs/benchmark.md. Tekan tombol untuk menghitung ulang")
    fig = go.Figure()
    for m, col in [("SENTINEL", ACCENT), ("Baseline B (duplicate filter)", NEUTRAL_1),
                   ("Baseline A (burst monitor)", NEUTRAL_2)]:
        s = b[b["method"] == m]
        fig.add_bar(x=s["difficulty"].map(lambda d: f"penyamaran {d:.1f}"), y=s["f1"], name=m.replace("Baseline ", ""),
                    marker_color=col, marker_line_width=0, text=s["f1"].map(lambda v: f"{v:.0%}"),
                    textposition="outside", textfont=dict(family="IBM Plex Mono", size=11))
    fig.update_layout(barmode="group", bargap=0.35, yaxis_tickformat=".0%", yaxis_range=[0, 1.12])
    st.plotly_chart(plot_layout(fig, 320), width="stretch", config={"displayModeBar": False})
    st.caption("Precision SENTINEL 100% di semua tingkat: tidak ada akun organik yang dituduh. Pada penyamaran "
               "tertinggi recall turun ke 52%, keterbatasan yang kami ungkap apa adanya")
    st.markdown("<div class='meta'>Desain antarmuka mengikuti metode unslop oleh Damir Sokolovsky, CC BY 4.0</div>",
                unsafe_allow_html=True)


# ============================================================== navigation
PAGES = {
    "ancaman": st.Page(page_threats, title="Ancaman", icon=":material/radar:", default=True, url_path="ancaman"),
    "kasus": st.Page(page_case, title="Kasus", icon=":material/folder_open:", url_path="kasus"),
    "akun": st.Page(page_account, title="Profil akun", icon=":material/person_search:", url_path="akun"),
    "sumber": st.Page(page_sources, title="Sumber data", icon=":material/database:", url_path="sumber"),
    "metode": st.Page(page_method, title="Metodologi", icon=":material/science:", url_path="metodologi"),
}
st.logo(str(Path(__file__).resolve().parent / "logo.svg"), size="large")
nav = st.navigation(list(PAGES.values()))
with st.sidebar:
    run = db.get_last_run()
    level, color = threat_level()
    st.markdown(f"<div class='meta' style='margin-top:8px'>Deteksi operasi pengaruh · siber sosial</div>"
                f"<div style='margin-top:24px;font-size:13px;color:{TEXT_2}'>{dot(color)}Status {level}</div>"
                f"<div class='meta' style='margin-top:8px'>{data_source_line()}"
                + (f"<br>deteksi {fmt_ts(run['started_at'])} · {run['duration_s']} dtk" if run else "")
                + "</div>", unsafe_allow_html=True)
nav.run()

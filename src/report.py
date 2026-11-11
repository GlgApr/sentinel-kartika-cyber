# Report Generator — Laporan Intelijen Singkat per campaign (Markdown)
# SENTINEL · Kartika Cyber Hackathon 2026

from datetime import datetime

from detection_engine import SIGNAL_LABELS
from config import Config

RECOMMENDATION = {
    "TINGGI": [
        "Eskalasi ke pimpinan & tim kontra-narasi dalam 1x24 jam.",
        "Ajukan takedown / pelaporan akun & URL ke platform dan Kominfo (aduankonten).",
        "Siapkan klarifikasi resmi melalui kanal humas satuan bila mencatut institusi.",
    ],
    "SEDANG": [
        "Pantau lanjutan 48 jam; tandai akun inti (hub) untuk watchlist.",
        "Verifikasi narasi dengan sumber resmi; siapkan materi literasi bila menyebar.",
    ],
    "RENDAH": ["Arsipkan sebagai referensi; tidak perlu tindakan segera."],
}


def campaign_brief(c, accounts, posts, max_posts=8):
    sig = c["signals"]
    lines = [
        f"# LAPORAN DETEKSI OPERASI PENGARUH — {c['campaign_id']}",
        "",
        f"*Dihasilkan otomatis oleh {Config.APP_NAME} pada {datetime.now():%d %B %Y %H:%M} WIB. "
        "Klasifikasi: TERBATAS — untuk keperluan analisis internal.*",
        "",
        "## 1. Ringkasan",
        f"- **Deskripsi**: {c['description']}",
        f"- **Tingkat risiko**: {c['risk_level']} (skor {c['flag_score']:.2f} / 1.00)",
        f"- **Status**: {c['status']}",
        f"- **Topik / kata kunci**: {c['topic_keywords']}",
        f"- **Periode aktivitas**: {c['first_seen'][:16].replace('T', ' ')} s/d {c['last_seen'][:16].replace('T', ' ')}",
        f"- **Skala**: {c['account_count']} akun, {c['post_count']} post terkoordinasi",
        "",
        "## 2. Indikator Koordinasi",
        "| Sinyal | Skor | Bobot |",
        "|---|---|---|",
    ]
    for k, v in sig.items():
        lines.append(f"| {SIGNAL_LABELS[k]} | {v:.0%} | {Config.SCORING_WEIGHTS[k]:.0%} |")
    lines += ["", "**Temuan:**"] + [f"- {e}" for e in c["signal_summary"]]
    lines += ["", "## 3. Akun Inti (hub)", "| Akun | Peran | Dibuat | Follower |", "|---|---|---|---|"]
    for a in accounts[:10]:
        m = a.get("metadata") or {}
        lines.append(f"| {a['account_id']} | {a['role']} | {m.get('created_at', '-')} | {m.get('followers', '-')} |")
    lines += ["", "## 4. Contoh Konten Bukti", "| Waktu | Akun | Konten |", "|---|---|---|"]
    for p in posts[:max_posts]:
        txt = p["content"].replace("|", "/")
        lines.append(f"| {p['timestamp'][:16].replace('T', ' ')} | {p['account_id']} | {txt} |")
    lines += ["", "## 5. Rekomendasi Tindak Lanjut"] + [f"- {r}" for r in RECOMMENDATION[c["risk_level"]]]
    if c.get("analyst_note"):
        lines += ["", "## 6. Catatan Analis", c["analyst_note"]]
    lines += ["", "---", "*Skor bersifat pendukung keputusan; keputusan akhir tetap pada analis.*"]
    return "\n".join(lines)

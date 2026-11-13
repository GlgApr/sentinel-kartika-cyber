# Report Generator — Laporan Intelijen Singkat per campaign (Markdown & STIX 2.1)
# SENTINEL · Kartika Cyber Hackathon 2026

import json
import uuid
from datetime import datetime, timezone

from detection_engine import SIGNAL_LABELS
from feature_extraction import promoted_entities
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


def classify_disarm_ttps(c, posts):
    """Petakan indikator perilaku campaign ke taksonomi global DISARM Framework
    (MITRE ATT&CK untuk operasi informasi) beserta countermeasure (DISARM Blue)."""
    sig = c.get("signals") or {}
    ttps = []
    if sig.get("timing", 0) >= 0.6:
        ttps.append({
            "id": "T0049", "tactic": "TA09 · Maximise Exposure",
            "name": "Flood Information Space (Synchronized Posting)",
            "countermeasure_id": "M001", "countermeasure": "Rate-limit & pantau gelombang jam sibuk; siapkan kontra-narasi pre-bunking.",
        })
    if sig.get("content", 0) >= 0.6 or c.get("pattern") == "template":
        ttps.append({
            "id": "T0057", "tactic": "TA07 · Deliver Content",
            "name": "Organise Copypasta / Template Rotation",
            "countermeasure_id": "M002", "countermeasure": "Blokir templat & variasi homoglyph di filter moderasi platform.",
        })
    if sig.get("account", 0) >= 0.5:
        ttps.append({
            "id": "T0046", "tactic": "TA06 · Develop People",
            "name": "Use Bots & Inauthentic Sockpuppet Accounts",
            "countermeasure_id": "M003", "countermeasure": "Laporkan klaster akun baru/anonim ke platform untuk verifikasi identitas.",
        })
    if sig.get("amplification", 0) >= 0.6:
        ttps.append({
            "id": "T0049.002", "tactic": "TA09 · Maximise Exposure",
            "name": "Coordinated Hashtag / URL Amplification",
            "countermeasure_id": "M004", "countermeasure": "Ajukan takedown URL/tagar promosi ke Kominfo (aduankonten) & platform.",
        })
    funnels = {e for p in posts for e in promoted_entities(p) if e.startswith(("wa:", "tg:", "typosquat:"))}
    if funnels:
        ttps.append({
            "id": "T0019", "tactic": "TA03 · Establish Legitimacy / Infrastructure",
            "name": "Fraudulent Contact Funnel / Domain Typosquatting",
            "countermeasure_id": "M005", "countermeasure": f"Blokir/suspend kanal kontak & domain palsu ({', '.join(sorted(funnels)[:3])}).",
        })
    platforms = {p.get("platform") for p in posts if p.get("platform")}
    if len(platforms) > 1:
        ttps.append({
            "id": "T0002", "tactic": "TA01 · Plan Strategy",
            "name": "Cross-Platform Narrative Seeding",
            "countermeasure_id": "M006", "countermeasure": f"Sinkronkan pemantauan lintas platform ({', '.join(sorted(platforms))}).",
        })
    return ttps


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
    ttps = classify_disarm_ttps(c, posts)
    if ttps:
        lines += ["", "## 6. Pemetaan DISARM Framework (Standar Global FIMI)",
                  "| ID | Taktik | Teknik | Countermeasure (DISARM Blue) |", "|---|---|---|---|"]
        for t in ttps:
            lines.append(f"| {t['id']} | {t['tactic']} | {t['name']} | {t['countermeasure']} |")
    if c.get("analyst_note"):
        lines += ["", "## 7. Catatan Analis", c["analyst_note"]]
    lines += ["", "---", "*Skor bersifat pendukung keputusan; keputusan akhir tetap pada analis.*"]
    return "\n".join(lines)


def _stix_id(kind, seed):
    return f"{kind}--{uuid.uuid5(uuid.NAMESPACE_URL, f'sentinel:{kind}:{seed}')}"


def _stix_ts(s):
    if not s:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return s[:19] + "Z" if "T" in s else s


def campaign_stix_bundle(c, accounts, posts):
    """Ekspor temuan campaign ke format standar STIX 2.1 JSON (kompatibel MISP/OpenCTI/SOC)."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    identity_id = _stix_id("identity", "pussiberad-sentinel")
    camp_id = _stix_id("campaign", c["campaign_id"])
    objects = [
        {
            "type": "identity",
            "spec_version": "2.1",
            "id": identity_id,
            "created": now,
            "modified": now,
            "name": f"{Config.APP_NAME} (PUSSIBERAD Siber Sosial)",
            "identity_class": "organization",
        },
        {
            "type": "campaign",
            "spec_version": "2.1",
            "id": camp_id,
            "created": now,
            "modified": now,
            "created_by_ref": identity_id,
            "name": f"{c['campaign_id']} — {c['description']}",
            "description": "; ".join(c.get("signal_summary") or []),
            "first_seen": _stix_ts(c.get("first_seen")),
            "last_seen": _stix_ts(c.get("last_seen")),
            "objective": c.get("topic_keywords") or "Coordinated Inauthentic Behavior",
            "labels": ["coordinated-inauthentic-behavior", f"risk-{c['risk_level'].lower()}"],
            "x_sentinel_score": round(float(c["flag_score"]), 4),
            "x_sentinel_signals": c.get("signals") or {},
        },
    ]
    urls = sorted({u for p in posts for u in (p.get("urls") or [])})
    for u in urls[:20]:
        ind_id = _stix_id("indicator", u)
        objects.append({
            "type": "indicator",
            "spec_version": "2.1",
            "id": ind_id,
            "created": now,
            "modified": now,
            "created_by_ref": identity_id,
            "name": f"Promoted URL: {u}",
            "pattern": f"[url:value = '{u}']",
            "pattern_type": "stix",
            "valid_from": _stix_ts(c.get("first_seen")),
        })
        objects.append({
            "type": "relationship",
            "spec_version": "2.1",
            "id": _stix_id("relationship", f"{camp_id}:{ind_id}"),
            "created": now,
            "modified": now,
            "relationship_type": "indicates",
            "source_ref": ind_id,
            "target_ref": camp_id,
        })
    for a in [x for x in accounts if x.get("role") == "hub"][:10]:
        ta_id = _stix_id("threat-actor", a["account_id"])
        objects.append({
            "type": "threat-actor",
            "spec_version": "2.1",
            "id": ta_id,
            "created": now,
            "modified": now,
            "created_by_ref": identity_id,
            "name": a["account_id"],
            "threat_actor_types": ["disinformation-agent"],
            "roles": ["hub"],
        })
        objects.append({
            "type": "relationship",
            "spec_version": "2.1",
            "id": _stix_id("relationship", f"{ta_id}:{camp_id}"),
            "created": now,
            "modified": now,
            "relationship_type": "attributed-to",
            "source_ref": camp_id,
            "target_ref": ta_id,
        })
    for t in classify_disarm_ttps(c, posts):
        ap_id = _stix_id("attack-pattern", t["id"])
        coa_id = _stix_id("course-of-action", t["countermeasure_id"])
        objects.append({
            "type": "attack-pattern",
            "spec_version": "2.1",
            "id": ap_id,
            "created": now,
            "modified": now,
            "created_by_ref": identity_id,
            "name": f"{t['id']} — {t['name']}",
            "description": t["tactic"],
            "external_references": [{"source_name": "DISARM", "external_id": t["id"]}],
        })
        objects.append({
            "type": "course-of-action",
            "spec_version": "2.1",
            "id": coa_id,
            "created": now,
            "modified": now,
            "created_by_ref": identity_id,
            "name": f"{t['countermeasure_id']} — Mitigasi {t['id']}",
            "description": t["countermeasure"],
        })
        objects.append({
            "type": "relationship",
            "spec_version": "2.1",
            "id": _stix_id("relationship", f"{camp_id}:uses:{ap_id}"),
            "created": now,
            "modified": now,
            "relationship_type": "uses",
            "source_ref": camp_id,
            "target_ref": ap_id,
        })
        objects.append({
            "type": "relationship",
            "spec_version": "2.1",
            "id": _stix_id("relationship", f"{coa_id}:mitigates:{ap_id}"),
            "created": now,
            "modified": now,
            "relationship_type": "mitigates",
            "source_ref": coa_id,
            "target_ref": ap_id,
        })
    return json.dumps({
        "type": "bundle",
        "id": f"bundle--{uuid.uuid5(uuid.NAMESPACE_URL, c['campaign_id'])}",
        "objects": objects,
    }, indent=2, ensure_ascii=False)

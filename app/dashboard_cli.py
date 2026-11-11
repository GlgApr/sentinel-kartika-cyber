# SENTINEL — CLI (mode demo tanpa browser / untuk server tanpa GUI)
# Jalankan:  python app/dashboard_cli.py [--rerun] [--report CMP-XXXXXX]

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from config import Config  # noqa: E402
from data_ingestion import ingest_sample_data  # noqa: E402
from database import Database  # noqa: E402
from detection_engine import SIGNAL_LABELS, DetectionEngine  # noqa: E402
from report import campaign_brief  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=f"{Config.APP_NAME} CLI")
    ap.add_argument("--rerun", action="store_true", help="jalankan ulang deteksi")
    ap.add_argument("--report", metavar="CAMPAIGN_ID", help="cetak laporan intelijen markdown")
    args = ap.parse_args()

    db = Database()
    if db.count("posts") == 0:
        ingest_sample_data(db)
        args.rerun = True
    if args.rerun or db.count("campaigns") == 0:
        DetectionEngine(db).run_detection_pipeline()

    if args.report:
        c = db.get_campaign_by_id(args.report)
        if not c:
            sys.exit(f"Campaign {args.report} tidak ditemukan")
        print(campaign_brief(c, db.get_campaign_accounts(c["campaign_id"]), db.get_posts_by_campaign(c["campaign_id"])))
        return

    print("=" * 78)
    print(f"  🛡️  {Config.APP_NAME} — {Config.APP_TAGLINE}")
    print("=" * 78)
    camps = db.get_campaigns()
    flagged = [c for c in camps if c["status"] != "dismissed"]
    print(f"  Post: {db.count('posts'):,} | Akun: {db.count('accounts'):,} | "
          f"Campaign di-flag: {len(flagged)} (dari {len(camps)} cluster)\n")
    for c in camps:
        print(f"[{c['risk_level']:6}] {c['campaign_id']}  skor={c['flag_score']:.2f}  status={c['status']}")
        print(f"         {c['description']}")
        print("         " + " | ".join(f"{SIGNAL_LABELS[k]}: {v:.0%}" for k, v in c["signals"].items()))
        for e in c["signal_summary"][:3]:
            print(f"         • {e}")
        print()
    print("Laporan detail:  python app/dashboard_cli.py --report <CAMPAIGN_ID>")


if __name__ == "__main__":
    main()

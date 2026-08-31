"""MWGym CLI — experiment management, review, and R2 sync.

Usage:
  python3 -m mwgym review          # Run review on local logs
  python3 -m mwgym sync            # Pull logs from R2
  python3 -m mwgym push            # Push local logs to R2
  python3 -m mwgym status          # Show R2 health + local log count
  python3 -m mwgym crossover       # Run the crossover experiment
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mwgym.storage.r2 import R2Store


LOG_DIR = Path("/root/mwgym/logs")
REVIEW_SCRIPT = Path("/root/mwgym/review.py")


def cmd_review(args):
    """Run experiment review."""
    subprocess.run([sys.executable, str(REVIEW_SCRIPT)] + args.extra, check=False)


def cmd_sync(args):
    """Pull latest logs from R2."""
    store = R2Store()
    health = store.health()
    if not health["ok"]:
        print(f"R2 unreachable: {health.get('error')}")
        sys.exit(1)

    downloaded = store.sync_logs_to_local(LOG_DIR, limit=args.limit)
    print(f"Synced {len(downloaded)} log(s) from R2")
    for p in downloaded:
        print(f"  {p.name}")


def cmd_push(args):
    """Push local logs to R2."""
    store = R2Store()
    health = store.health()
    if not health["ok"]:
        print(f"R2 unreachable: {health.get('error')}")
        sys.exit(1)

    count = 0
    for log_file in sorted(LOG_DIR.glob("*.json")):
        if log_file.name.startswith("."):
            continue
        key = store.upload_log(log_file)
        print(f"  {log_file.name} → {key}")
        count += 1

    # Push review if exists
    review_file = LOG_DIR / "REVIEW.md"
    if review_file.exists():
        key = store.upload_review(review_file)
        print(f"  REVIEW.md → {key}")
        count += 1

    print(f"Pushed {count} file(s) to R2")


def cmd_status(args):
    """Show R2 health and local log count."""
    store = R2Store()
    health = store.health()

    local_logs = list(LOG_DIR.glob("*.json"))
    print(f"R2: {'OK' if health['ok'] else 'UNREACHABLE'} (bucket={health.get('bucket', '?')})")
    print(f"Local logs: {len(local_logs)}")
    print(f"Log dir: {LOG_DIR}")

    if health["ok"]:
        remote_logs = store.list_logs(limit=5)
        print(f"Remote logs (latest {len(remote_logs)}):")
        for log in remote_logs:
            print(f"  {log['key']} ({log['size']} bytes)")


def cmd_crossover(args):
    """Run the crossover experiment."""
    subprocess.run([sys.executable, str(Path("/root/mwgym/run_crossover.py"))], check=False)


def main():
    parser = argparse.ArgumentParser(prog="mwgym", description="MWGym experiment management")
    sub = parser.add_subparsers(dest="command")

    p_review = sub.add_parser("review", help="Run experiment review")
    p_review.add_argument("extra", nargs="*", help="Extra args for review.py")

    p_sync = sub.add_parser("sync", help="Pull logs from R2")
    p_sync.add_argument("--limit", type=int, default=20)

    p_push = sub.add_parser("push", help="Push local logs to R2")

    p_status = sub.add_parser("status", help="Show R2 health + local state")

    p_crossover = sub.add_parser("crossover", help="Run crossover experiment")

    args = parser.parse_args()
    if args.command == "review":
        cmd_review(args)
    elif args.command == "sync":
        cmd_sync(args)
    elif args.command == "push":
        cmd_push(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "crossover":
        cmd_crossover(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

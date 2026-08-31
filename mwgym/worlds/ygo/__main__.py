"""YGO World Runner CLI.

Usage:
  cd /root/mwgym && python3 -m mwgym.worlds.ygo --games 10
  python3 -m mwgym.worlds.ygo --games 5 --opponents passive,aggressive,defensive,economic
  python3 -m mwgym.worlds.ygo --games 5 --all
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from mwgym.worlds.ygo.runner import YGORunner, YGO_GENOMES
from mwgym.worlds.ygo.env import OPPONENT_STRATEGIES


def main():
    parser = argparse.ArgumentParser(description="YGO genome × opponent experiment")
    parser.add_argument("--games", type=int, default=10, help="Games per genome×opponent pair")
    parser.add_argument("--genomes", type=str, default="static,memory,memory_bats")
    parser.add_argument("--opponents", type=str, default="passive",
                        help="Comma-separated: passive,aggressive,defensive,economic")
    parser.add_argument("--all", action="store_true", help="Run all opponents")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    genome_ids = [g.strip() for g in args.genomes.split(",")]
    valid_genomes = [g for g in genome_ids if g in YGO_GENOMES]
    if not valid_genomes:
        print(f"No valid genomes. Available: {list(YGO_GENOMES.keys())}", file=sys.stderr)
        sys.exit(1)

    if args.all:
        opponents = list(OPPONENT_STRATEGIES.keys())
    else:
        opponents = [o.strip() for o in args.opponents.split(",")]
        invalid = [o for o in opponents if o not in OPPONENT_STRATEGIES]
        if invalid:
            print(f"Unknown opponents: {invalid}. Available: {list(OPPONENT_STRATEGIES.keys())}",
                  file=sys.stderr)
            sys.exit(1)

    total_games = args.games * len(valid_genomes) * len(opponents)
    print(f"Running: {args.games} games × {len(valid_genomes)} genomes × {len(opponents)} opponents = {total_games} games")

    runner = YGORunner(seed=args.seed)
    result = runner.run_experiment(n_games=args.games, genome_ids=valid_genomes, opponents=opponents)

    print(f"\n{'='*60}")
    print("RESULTS")
    print(f"{'='*60}")
    for key, stats in sorted(result["summary"].items()):
        print(f"\n{stats['genome']} vs {stats['opponent']}:")
        print(f"  Win rate: {stats['win_rate']*100:.0f}% ({stats['wins']}/{stats['n']})")
        print(f"  Avg reward: {stats['avg_reward']}")
        print(f"  Avg efficiency: {stats['avg_efficiency']}")
        print(f"  Decision quality: {stats['avg_decision_quality']}")

    print(f"\nLog: {result['log']}")

    from mwgym.storage.r2 import R2Store
    try:
        store = R2Store()
        if store.health()["ok"]:
            store.upload_log(Path(result["log"]))
            print("Pushed to R2")
    except Exception as e:
        print(f"R2 push failed: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()

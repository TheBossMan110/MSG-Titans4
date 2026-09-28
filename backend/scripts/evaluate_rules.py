"""
Score the Python rule engine against the labelled dataset, offline.

    python scripts/evaluate_rules.py                 # full 500-complaint benchmark
    python scripts/evaluate_rules.py --limit 100     # a quicker sample
    python scripts/evaluate_rules.py --json out.json # also write the metrics

Builds a throwaway SQLite database under var/, seeds it from the same
configuration files the live system loads, imports the benchmark CSV and runs
it rules-only. Nothing touches the production database or any model provider,
so the figures measure Pipeline 2 alone and can be re-run after every change.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL_DB = ROOT / "var" / "eval_rules.db"

# Settings are read once, at first import: configure before importing src.*
EVAL_DB.parent.mkdir(parents=True, exist_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{EVAL_DB.as_posix()}"
os.environ["APP_ENV"] = "test"
os.environ["EMBEDDING_ENABLED"] = "false"
os.environ["LLM_CACHE_ENABLED"] = "false"
os.environ["STORAGE_BACKEND"] = "local"
for key in ("GEMINI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY", "DEEPSEEK_API_KEY",
            "EMAIL_APP_PASSWORD", "EMAIL_RELAY_URL", "RESEND_API_KEY"):
    os.environ[key] = ""
sys.path.insert(0, str(ROOT))

from genai_pipeline.prompts import seed_prompts  # noqa: E402
from src.db.base import Base, SessionLocal, engine  # noqa: E402
from src.db.seed.core_data import seed_policy_config, seed_signals, seed_taxonomy  # noqa: E402
from src.db.seed.rules import seed_rules  # noqa: E402
from src.db.seed.users import seed_users  # noqa: E402
from src.services import benchmark, dataset  # noqa: E402

CSV = ROOT.parent / "dataset" / "raftarxpress" / "complaints" / "raftarxpress_benchmark.csv"
TAG = "EVAL"


def build() -> None:
    engine.dispose()
    if EVAL_DB.exists():
        EVAL_DB.unlink()
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        for seeder in (seed_taxonomy, seed_policy_config, seed_signals, seed_users, seed_rules, seed_prompts):
            seeder(db)
            db.commit()
        result = dataset.import_file(db, CSV.read_bytes(), CSV.name, dataset_tag=TAG, replace=True)
        db.commit()
        print(f"imported {result.imported} complaints ({result.labelled} labelled, {len(result.errors)} errors) from {CSV.name}")
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    started = time.perf_counter()
    build()
    db = SessionLocal()
    try:
        outcome = benchmark.run(db, dataset_tag=TAG, limit=args.limit, run_genai=False, workers=1, resume=True, apply=True)
    finally:
        db.close()
    metrics = outcome.metrics()

    print(f"\nprocessed {outcome.processed}, failed {outcome.failed}, {time.perf_counter() - started:.0f} s")
    for row in metrics["by_field"]:
        print(f"  {row.get('field', '?'):<14} python {row.get('python_accuracy_pct')!s:>6} %")
    print(f"  overall python accuracy {metrics['overall']['python_accuracy_pct']} %")
    esc = metrics["mandatory_escalation"]
    print(f"  mandatory escalation recall {esc['recall_pct']} %  ({esc['recalled']}/{esc['expected']}), over-escalated {esc['over_escalated']}")
    if args.json:
        args.json.write_text(json.dumps(metrics, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

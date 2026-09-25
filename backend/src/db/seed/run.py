"""
Seed runner.

    python -m src.db.seed.run              # seed everything (idempotent)
    python -m src.db.seed.run --only users
    python -m src.db.seed.run --reset      # DANGER: drops and recreates

Safe to run repeatedly: every seeder upserts.
"""

from __future__ import annotations

import argparse
import sys

from genai_pipeline.prompts import seed_prompts
from src.core.config import settings
from src.core.logging import configure_logging, get_logger
from src.db.base import Base, SessionLocal, engine
from src.db.seed.core_data import seed_policy_config, seed_signals, seed_taxonomy
from src.db.seed.rules import seed_rules
from src.db.seed.users import seed_users

log = get_logger("seed")


SEEDERS = {
    "taxonomy": seed_taxonomy,
    "config": seed_policy_config,
    "signals": seed_signals,
    "users": seed_users,   # must run after taxonomy (agents reference departments)
    # Last: rules reference categories, departments, priorities, escalation
    # levels AND signal keys, so everything they point at must exist first.
    "rules": seed_rules,
    # Independent of everything above: reads prompt_templates/ from disk.
    "prompts": seed_prompts,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed the SupportNova database")
    parser.add_argument(
        "--only", choices=list(SEEDERS), action="append",
        help="Run only the named seeder (repeatable).",
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Drop and recreate every table first. Destroys all data.",
    )
    args = parser.parse_args(argv)

    configure_logging(settings.log_level, json_output=settings.is_production)

    if args.reset:
        if settings.is_production:
            print("Refusing to --reset a production database.", file=sys.stderr)
            return 2
        log.warning("dropping_all_tables", url=_safe_url())
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)

    selected = args.only or list(SEEDERS)
    totals: dict[str, int] = {}

    db = SessionLocal()
    try:
        for name in selected:
            result = SEEDERS[name](db)
            totals.update({f"{name}.{k}": v for k, v in result.items()})
        db.commit()
    except Exception:
        db.rollback()
        log.error("seed_failed", exc_info=True)
        raise
    finally:
        db.close()

    print("\nSeed complete —", _safe_url())
    for key, value in totals.items():
        print(f"  {key:<32} {value}")
    print("\nEvaluator login: evaluator@raftarxpress.com")
    print("Administrator  : admin@raftarxpress.com")
    from src.db.seed.users import DEFAULT_PASSWORD

    print(f"Password       : {DEFAULT_PASSWORD}\n")
    return 0


def _safe_url() -> str:
    """Never print credentials."""
    url = settings.database_url
    if "@" in url:
        scheme, rest = url.split("://", 1)
        return f"{scheme}://***@{rest.split('@', 1)[1]}"
    return url


if __name__ == "__main__":
    raise SystemExit(main())

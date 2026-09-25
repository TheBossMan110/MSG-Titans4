"""
Seed the accounts an evaluator needs on day one.

SRS Deliverable 15 requires the submission to include a public URL plus
**evaluator credentials** and **administrator credentials**.  Seeding them
means the judges never wait for a signup flow.

Passwords are intentionally simple and published in the README — this is a
demonstration system holding synthetic data only (SRS Step 1 forbids real
customer information).  Set SEED_PASSWORD in the environment to override.
"""

from __future__ import annotations

import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.logging import get_logger
from src.core.security import hash_password
from src.db.enums import UserRole
from src.db.models import Customer, Department, User
from src.db.seed.loader import upsert

log = get_logger("seed")

DEFAULT_PASSWORD = os.getenv("SEED_PASSWORD", "SupportNova#2026")

# (email, full_name, role, department_code)
SEED_USERS: list[tuple[str, str, str, str | None]] = [
    ("evaluator@raftarxpress.com", "Competition Evaluator", UserRole.EVALUATOR, None),
    ("admin@raftarxpress.com", "Aarav Menon", UserRole.ADMIN, None),
    ("manager@raftarxpress.com", "Priya Raghavan", UserRole.MANAGER, "CUSTOMER_RELATIONS"),
    ("reviewer@raftarxpress.com", "Daniel Osei", UserRole.REVIEWER, "COMPLIANCE"),
    ("agent.billing@raftarxpress.com", "Sara Qureshi", UserRole.AGENT, "BILLING"),
    ("agent.logistics@raftarxpress.com", "Rohan Pillai", UserRole.AGENT, "LOGISTICS_OPS"),
    ("agent.claims@raftarxpress.com", "Mei Lin Tan", UserRole.AGENT, "WARRANTY_CLAIMS"),
    ("agent.safety@raftarxpress.com", "Imran Farooq", UserRole.AGENT, "SAFETY"),
    ("customer@raftarxpress.com", "Demo Customer", UserRole.CUSTOMER, None),
]


def seed_users(db: Session) -> dict[str, int]:
    departments = {d.code: d for d in db.execute(select(Department)).scalars()}
    password_hash = hash_password(DEFAULT_PASSWORD)
    created_count = 0

    for email, full_name, role, dept_code in SEED_USERS:
        department = departments.get(dept_code) if dept_code else None
        _, created = upsert(
            db, User,
            match={"email": email},
            values={
                "full_name": full_name,
                "role": role,
                "department_id": department.id if department else None,
                "is_active": True,
                # Reseeding deliberately resets seeded passwords back to the
                # documented default, so the evaluator credentials in the
                # README are always correct after a demo reset.
                "password_hash": password_hash,
            },
        )
        created_count += int(created)

    # The demo customer needs a Customer record too — users and customers are
    # separate concepts (see src/db/models/complaints.py).
    portal_user = db.execute(
        select(User).where(User.email == "customer@raftarxpress.com")
    ).scalars().first()
    upsert(
        db, Customer,
        match={"external_ref": "CUST-00001"},
        values={
            "display_name": "Demo Customer",
            "email": "customer@raftarxpress.com",
            "tier": "STANDARD",
            "region": "IN",
            "user_id": portal_user.id if portal_user else None,
        },
    )

    log.info("seeded_users", total=len(SEED_USERS), created=created_count)
    return {"users": len(SEED_USERS), "created": created_count}

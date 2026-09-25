"""
The reference-data cache must never serve a rule, threshold or category that an
administrator has already changed. These tests hold it to that.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, update

from python_validation.pipeline import load_active_rules
from src.core import refcache
from src.core.config import settings
from src.db.models import AppConfig, Rule

calls = {"n": 0}


@refcache.reference_data("test_counter")
def _counted(db):
    calls["n"] += 1
    return {"value": calls["n"]}


@pytest.fixture(autouse=True)
def _fresh():
    refcache.invalidate()
    calls["n"] = 0
    before = settings.reference_cache_seconds
    settings.reference_cache_seconds = 60
    yield
    settings.reference_cache_seconds = before
    refcache.invalidate()


def test_a_second_read_is_served_from_memory(db):
    assert _counted(db) == {"value": 1}
    assert _counted(db) == {"value": 1}
    assert calls["n"] == 1


def test_callers_get_copies_they_may_mutate(db):
    first = _counted(db)
    first["value"] = "tampered"
    assert _counted(db) == {"value": 1}


def test_zero_seconds_turns_caching_off(db):
    settings.reference_cache_seconds = 0
    _counted(db)
    _counted(db)
    assert calls["n"] == 2


def test_committing_a_reference_change_invalidates(db):
    _counted(db)
    row = db.get(AppConfig, "thresholds") or AppConfig(key="thresholds", value={})
    row.value = {**(row.value or {}), "_touched": True}
    db.add(row)
    db.commit()
    _counted(db)
    assert calls["n"] == 2


def test_committing_unrelated_rows_keeps_the_cache(db):
    from src.db.models import Customer

    _counted(db)
    customer = Customer(
        external_ref=f"CUST-T{uuid.uuid4().hex[:8]}", email="cache-test@example.com",
        display_name="Cache Test",
    )
    db.add(customer)
    db.commit()
    _counted(db)
    assert calls["n"] == 1
    db.delete(customer)
    db.commit()


def test_a_session_sees_its_own_uncommitted_rule_change(db):
    rules = load_active_rules(db)
    target = db.execute(select(Rule).where(Rule.is_active.is_(True))).scalars().first()
    target.is_active = False
    db.flush()  # sessions here do not autoflush; the cache must not hide the flush

    after = load_active_rules(db)
    assert target.rule_ref not in {r.rule_ref for r in after}
    assert len(after) == len(rules) - 1
    db.rollback()


def test_nothing_read_inside_a_dirty_transaction_is_kept(db):
    target = db.execute(select(Rule).where(Rule.is_active.is_(True))).scalars().first()
    target.is_active = False
    db.flush()
    load_active_rules(db)  # reads the uncommitted state
    db.rollback()

    refs = {r.rule_ref for r in load_active_rules(db)}
    assert target.rule_ref in refs, "a rolled-back change leaked into the cache"


def test_a_bulk_update_marks_the_session(db):
    load_active_rules(db)
    db.execute(update(Rule).where(Rule.rule_ref == "__none__").values(precedence=1))
    assert db.info.get("reference_dirty") is True
    db.rollback()


def test_warming_fills_the_cache_so_the_first_read_is_free(db):
    import python_validation.pipeline as pipeline

    report = refcache.warm()
    assert isinstance(report.get("active_rules"), float), report
    before = dict(refcache._store)
    pipeline.load_active_rules(db)
    assert refcache._store.keys() == before.keys()  # served, not reloaded


def test_invalidation_wakes_the_refresher():
    refcache._wake.clear()
    refcache.invalidate()
    assert refcache._wake.is_set()


def test_dataset_customer_labels_map_to_tiers():
    from python_validation.signals import tier_of

    assert tier_of("VIP/Premium Account") == "VIP"
    assert tier_of("Business/Merchant Account") == "BUSINESS"
    assert tier_of("Corporate Freight Client") == "BUSINESS"
    assert tier_of("Individual Consumer") == "STANDARD"
    assert tier_of("VIP") == "VIP"
    assert tier_of(None) is None

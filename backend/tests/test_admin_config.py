"""
Live configuration and rule editing (SRS 1.8 #14).

The test that matters most is
:meth:`TestFloorGuard.test_a_mandatory_escalation_rule_cannot_be_switched_off`.
The escalation floor is enforced against the model, against the comparison
engine and against a human reviewer. An admin API able to deactivate the rule
that *sets* the floor would be a fourth way through, and the quietest of the
four — it leaves no override on the complaint for anyone to notice.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from src.db.models import EscalationLevel, LexiconTerm, Rule, SLAPolicy
from src.services import admin_config

SAFETY = (
    "The parcel you delivered made a loud pop and there is a burning smell "
    "from the plug. I unplugged it immediately. Order CN-9923190."
)
LATE_PARCEL = (
    "My parcel for order CN-4455660 has not arrived and the tracking page has "
    "not updated for four days."
)


def _escalation_ranks(db) -> dict[str, int]:
    return {row.code: row.rank for row in db.execute(select(EscalationLevel)).scalars()}


def _mandatory_rules(db) -> list[Rule]:
    return list(
        db.execute(
            select(Rule)
            .where(Rule.is_mandatory_escalation.is_(True))
            .order_by(Rule.rule_ref)
        ).scalars()
    )


@pytest.fixture
def mandatory_rule(db):
    """Any rule that sets a mandatory escalation floor."""
    rules = _mandatory_rules(db)
    assert rules, "the matrix must carry mandatory escalation rules"
    return rules[0]


@pytest.fixture
def lowerable_mandatory_rule(db):
    """
    The mandatory rule with the *highest* escalation level.

    Chosen rather than taken arbitrarily so there is always a level below it
    to attempt. Picking the first rule by reference happened to land on one
    already at the top of the ladder, and the test skipped -- which reads as a
    pass while testing nothing.
    """
    ranks = _escalation_ranks(db)
    rules = [r for r in _mandatory_rules(db) if r.outcome_escalation_code in ranks]
    assert rules, "no mandatory rule names a known escalation level"
    return max(rules, key=lambda r: ranks[r.outcome_escalation_code])


@pytest.fixture
def raisable_mandatory_rule(db):
    """The mandatory rule with the *lowest* escalation level, so there is room above."""
    ranks = _escalation_ranks(db)
    rules = [r for r in _mandatory_rules(db) if r.outcome_escalation_code in ranks]
    assert rules, "no mandatory rule names a known escalation level"
    return min(rules, key=lambda r: ranks[r.outcome_escalation_code])


@pytest.fixture
def ordinary_rule(db):
    """A rule that does not set a floor, so it is freely editable."""
    return db.execute(
        select(Rule)
        .where(Rule.is_mandatory_escalation.is_(False), Rule.is_active.is_(True))
        .order_by(Rule.rule_ref)
    ).scalars().first()


@pytest.fixture
def restore_rules(db):
    """Put the matrix back however the test left it."""
    yield
    from src.db.seed.rules import seed_rules

    seed_rules(db)
    db.commit()


# ══════════════════════════════════════════════════════════════
# the floor guard
# ══════════════════════════════════════════════════════════════
class TestFloorGuard:
    def test_a_mandatory_escalation_rule_cannot_be_switched_off(
        self, client, auth_headers, mandatory_rule, db
    ):
        """
        The whole point of the guard. Deactivating the rule that sets the floor
        would lower every future complaint's escalation without leaving an
        override on any of them.
        """
        assert mandatory_rule is not None, "the matrix must carry mandatory rules"

        response = client.patch(
            f"/api/admin/rules/{mandatory_rule.rule_ref}",
            json={"is_active": False, "reason": "Tidying the matrix."},
            headers=auth_headers("admin"),
        )

        assert response.status_code == 422, response.text
        assert "mandatory escalation" in response.text.lower()

        db.expire(mandatory_rule)
        assert mandatory_rule.is_active, "the rule must still be live"

    def test_its_level_cannot_be_lowered(
        self, client, auth_headers, lowerable_mandatory_rule, db
    ):
        rule = lowerable_mandatory_rule
        ranks = _escalation_ranks(db)
        current = ranks[rule.outcome_escalation_code]
        lower = sorted(
            (code for code, rank in ranks.items() if rank < current),
            key=lambda code: ranks[code],
        )
        assert lower, "the fixture picked the highest rule; something has room below"

        response = client.patch(
            f"/api/admin/rules/{rule.rule_ref}",
            json={"outcome_escalation_code": lower[0]},
            headers=auth_headers("admin"),
        )

        assert response.status_code == 422, response.text
        assert "raised but not lowered" in response.text

        db.expire(rule)
        assert rule.outcome_escalation_code != lower[0], "the level must be unchanged"

    def test_its_level_may_be_raised(
        self, client, auth_headers, raisable_mandatory_rule, db, restore_rules
    ):
        """
        Raising is always allowed. A guard that refused both directions would
        block a genuine safety tightening, which is the opposite of the point.
        """
        rule = raisable_mandatory_rule
        ranks = _escalation_ranks(db)
        current = ranks[rule.outcome_escalation_code]
        higher = sorted(
            (code for code, rank in ranks.items() if rank > current),
            key=lambda code: ranks[code],
        )
        assert higher, "the fixture picked the lowest rule; something has room above"

        response = client.patch(
            f"/api/admin/rules/{rule.rule_ref}",
            json={"outcome_escalation_code": higher[0], "reason": "Tightening."},
            headers=auth_headers("admin"),
        )

        assert response.status_code == 200, response.text
        assert response.json()["rule"]["outcome_escalation_code"] == higher[0]

    def test_the_listing_says_which_rules_are_protected(self, client, auth_headers):
        """
        An interface that offers a deactivate button the API refuses teaches
        people to distrust it.
        """
        rows = client.get(
            "/api/admin/rules?mandatory=true", headers=auth_headers("admin")
        ).json()
        assert rows
        assert all(row["is_mandatory_escalation"] for row in rows)
        assert all(row["can_deactivate"] is False for row in rows)


# ══════════════════════════════════════════════════════════════
# refusing a bad rule at save time
# ══════════════════════════════════════════════════════════════
class TestRuleValidation:
    def test_a_malformed_condition_is_refused(
        self, client, auth_headers, ordinary_rule
    ):
        """
        Refused at save time, not at evaluation time. A rule that saves and
        then silently never fires looks exactly like the system ignoring the
        evaluator.
        """
        response = client.patch(
            f"/api/admin/rules/{ordinary_rule.rule_ref}",
            json={"conditions": {"all_of": []}},
            headers=auth_headers("admin"),
        )
        assert response.status_code == 422
        assert "non-empty list" in response.text

    def test_a_condition_on_a_signal_nothing_raises_is_refused(
        self, client, auth_headers, ordinary_rule
    ):
        """
        A rule testing a signal no lexicon term raises never fires, and reads
        in the matrix as though the case is covered. That exact mistake made a
        promise check vacuous once already.
        """
        response = client.patch(
            f"/api/admin/rules/{ordinary_rule.rule_ref}",
            json={"conditions": {"signal": "customer_is_definitely_annoyed"}},
            headers=auth_headers("admin"),
        )
        assert response.status_code == 422
        assert "no active lexicon term raises" in response.text

    def test_an_unknown_outcome_code_is_refused(
        self, client, auth_headers, ordinary_rule
    ):
        response = client.patch(
            f"/api/admin/rules/{ordinary_rule.rule_ref}",
            json={"outcome_department": "DEPARTMENT_OF_MAGIC"},
            headers=auth_headers("admin"),
        )
        assert response.status_code == 422
        assert "not a known department code" in response.text

    def test_every_problem_is_reported_at_once(
        self, client, auth_headers, ordinary_rule
    ):
        """
        Fixing a rule one error per round-trip is the demonstration going badly
        in public.
        """
        response = client.patch(
            f"/api/admin/rules/{ordinary_rule.rule_ref}",
            json={
                "conditions": {"signal": "nothing_raises_this"},
                "outcome_department": "NOT_A_DEPARTMENT",
                "outcome_priority_code": "P99",
            },
            headers=auth_headers("admin"),
        )
        assert response.status_code == 422
        body = response.text
        assert "no active lexicon term raises" in body
        assert "not a known department code" in body
        assert "P99" in body

    def test_an_unknown_rule_is_404_not_422(self, client, auth_headers):
        response = client.patch(
            "/api/admin/rules/ESC-9999",
            json={"precedence": 5},
            headers=auth_headers("admin"),
        )
        assert response.status_code == 404


# ══════════════════════════════════════════════════════════════
# a change that actually takes effect
# ══════════════════════════════════════════════════════════════
class TestLiveModification:
    def test_the_rule_test_endpoint_writes_nothing(self, client, auth_headers, db):
        """
        Deterministic and free: an evaluator can run it as often as they like
        without spending the free-tier quota or filling the register.
        """
        from src.db.models import Complaint, GenAIRun, ValidationRun

        def counts():
            return tuple(
                db.execute(select(model)).scalars().all().__len__()
                for model in (Complaint, ValidationRun, GenAIRun)
            )

        before = counts()
        response = client.post(
            "/api/admin/rules/test",
            json={"description": SAFETY},
            headers=auth_headers("evaluator"),
        )
        assert response.status_code == 200, response.text
        db.expire_all()
        assert counts() == before, "the rule test must not persist anything"

    def test_the_rule_test_reports_the_safety_decision(self, client, auth_headers):
        """The Sentiment-Urgency trap, in one request and with no provider."""
        body = client.post(
            "/api/admin/rules/test",
            json={"description": SAFETY},
            headers=auth_headers("evaluator"),
        ).json()

        assert body["escalation_required"]
        assert body["mandatory_escalation_refs"], "a safety case must name its rule"
        assert body["matched_rules"]
        assert body["ruleset_version"]

    def test_a_new_lexicon_term_changes_the_next_decision(
        self, client, auth_headers, db, restore_rules
    ):
        """
        The Live Modification Challenge, end to end: teach the engine a word
        and the very next evaluation of the same text differs. No restart, no
        redeploy.
        """
        headers = auth_headers("admin")
        text = "The courier left my parcel in the rain and the box is sopping wet."

        before = client.post(
            "/api/admin/rules/test", json={"description": text}, headers=headers
        ).json()

        signal = db.execute(select(LexiconTerm)).scalars().first().signal_key
        added = client.post(
            "/api/admin/lexicon",
            json={"signal_key": signal, "term": "sopping wet", "match_type": "PHRASE"},
            headers=headers,
        )
        assert added.status_code == 201, added.text

        after = client.post(
            "/api/admin/rules/test", json={"description": text}, headers=headers
        ).json()

        assert signal in after["signals_fired"]
        assert signal not in before["signals_fired"] or before != after

    def test_a_precedence_change_bumps_the_ruleset_version(
        self, client, auth_headers, ordinary_rule, restore_rules
    ):
        """
        Every validation_run stamps the version. Without the bump, re-reading
        an old run would attribute it to the new matrix.
        """
        headers = auth_headers("admin")
        before = client.post(
            "/api/admin/rules/test", json={"description": LATE_PARCEL}, headers=headers
        ).json()["ruleset_version"]

        response = client.patch(
            f"/api/admin/rules/{ordinary_rule.rule_ref}",
            json={"precedence": (ordinary_rule.precedence or 0) + 7},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["changed_fields"] == ["precedence"]
        assert response.json()["ruleset_version"] != before

    def test_an_edit_that_changes_nothing_bumps_nothing(
        self, client, auth_headers, ordinary_rule
    ):
        """A no-op edit must not invent a new ruleset version."""
        response = client.patch(
            f"/api/admin/rules/{ordinary_rule.rule_ref}",
            json={"precedence": ordinary_rule.precedence},
            headers=auth_headers("admin"),
        )
        assert response.status_code == 200
        assert response.json()["changed_fields"] == []

    def test_reload_restores_the_committed_matrix(
        self, client, auth_headers, ordinary_rule, db
    ):
        """The undo, so the next demonstration starts from a known state."""
        headers = auth_headers("admin")

        # Start from the committed state rather than from whatever an earlier
        # test left behind, so `original` is the YAML value and not a mutation.
        client.post("/api/admin/rules/reload", headers=headers)
        db.expire_all()
        original = db.execute(
            select(Rule).where(Rule.rule_ref == ordinary_rule.rule_ref)
        ).scalars().one().precedence

        client.patch(
            f"/api/admin/rules/{ordinary_rule.rule_ref}",
            json={"precedence": (original or 0) + 31},
            headers=headers,
        )

        response = client.post("/api/admin/rules/reload", headers=headers)
        assert response.status_code == 200, response.text

        db.expire_all()
        restored = db.execute(
            select(Rule).where(Rule.rule_ref == ordinary_rule.rule_ref)
        ).scalars().one()
        assert restored.precedence == original


# ══════════════════════════════════════════════════════════════
# configuration values
# ══════════════════════════════════════════════════════════════
class TestConfig:
    def test_the_configuration_is_readable(self, client, auth_headers):
        rows = client.get("/api/admin/config", headers=auth_headers("evaluator")).json()
        keys = {row["key"] for row in rows}
        assert {"thresholds", "response_guard", "ruleset_version"} <= keys

    def test_derived_rows_are_marked_uneditable(self, client, auth_headers):
        rows = client.get("/api/admin/config", headers=auth_headers("admin")).json()
        version_row = next(row for row in rows if row["key"] == "ruleset_version")
        assert version_row["editable"] is False

    def test_a_derived_row_is_refused(self, client, auth_headers):
        """
        Hand-editing it would detach stored results from the configuration
        that produced them.
        """
        response = client.put(
            "/api/admin/config/ruleset_version",
            json={"value": {"version": "9.9.9"}},
            headers=auth_headers("admin"),
        )
        assert response.status_code == 422
        assert "derived, not configured" in response.text

    def test_a_threshold_can_be_changed(self, client, auth_headers, db):
        from src.db.models import AppConfig

        headers = auth_headers("admin")
        current = db.get(AppConfig, "thresholds")
        original = dict(current.value)

        changed = {**original, "duplicate_similarity": 0.99}
        response = client.put(
            "/api/admin/config/thresholds",
            json={"value": changed, "reason": "Tightening duplicate detection."},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["value"]["duplicate_similarity"] == 0.99
        assert response.json()["version"] > 1

        client.put(
            "/api/admin/config/thresholds",
            json={"value": original, "reason": "Restore."},
            headers=headers,
        )

    def test_the_wrong_shape_is_refused(self, client, auth_headers):
        """
        A list where an object was expected fails deep inside the rule engine
        on the next complaint, which is a far worse place to discover it.
        """
        response = client.put(
            "/api/admin/config/thresholds",
            json={"value": ["not", "an", "object"]},
            headers=auth_headers("admin"),
        )
        assert response.status_code == 422
        assert "expect the existing shape" in response.text

    def test_the_change_is_audited(self, client, auth_headers, db):
        from src.db.models import AppConfig, AuditLog

        headers = auth_headers("admin")
        original = dict(db.get(AppConfig, "thresholds").value)

        client.put(
            "/api/admin/config/thresholds",
            json={"value": {**original, "duplicate_similarity": 0.91},
                  "reason": "Audit check."},
            headers=headers,
        )

        entry = db.execute(
            select(AuditLog)
            .where(AuditLog.action == "CONFIG_CHANGE")
            .order_by(AuditLog.created_at.desc())
        ).scalars().first()

        assert entry is not None
        assert entry.before != entry.after, "an audit row with no delta records nothing"
        assert entry.reason == "Audit check."

        client.put(
            "/api/admin/config/thresholds",
            json={"value": original}, headers=headers,
        )

    def test_the_taxonomy_is_read_only(self, client, auth_headers):
        body = client.get("/api/admin/taxonomy", headers=auth_headers("manager")).json()
        assert body["categories"] and body["departments"]
        assert body["priority_levels"]
        # P0 is rank 0: the ladder counts down.
        assert body["priority_levels"][0]["rank"] == 0


# ══════════════════════════════════════════════════════════════
# lexicon
# ══════════════════════════════════════════════════════════════
class TestLexicon:
    def test_an_uncompilable_regex_is_refused(self, client, auth_headers, db):
        """
        An uncompilable term disables one signal silently, and a signal that
        stops firing looks exactly like a complaint that did not mention the
        thing.
        """
        signal = db.execute(select(LexiconTerm)).scalars().first().signal_key
        response = client.post(
            "/api/admin/lexicon",
            json={"signal_key": signal, "term": "burn(ing", "match_type": "REGEX"},
            headers=auth_headers("admin"),
        )
        assert response.status_code == 422
        assert "not a valid regular expression" in response.text

    def test_a_duplicate_term_is_refused(self, client, auth_headers, db):
        existing = db.execute(select(LexiconTerm)).scalars().first()
        response = client.post(
            "/api/admin/lexicon",
            json={"signal_key": existing.signal_key, "term": existing.term},
            headers=auth_headers("admin"),
        )
        assert response.status_code == 422
        assert "already raises" in response.text

    def test_withdrawing_deactivates_rather_than_deletes(
        self, client, auth_headers, db
    ):
        """
        A term that once raised a signal is part of the explanation for every
        complaint decided while it was active.
        """
        headers = auth_headers("admin")
        signal = db.execute(select(LexiconTerm)).scalars().first().signal_key
        created = client.post(
            "/api/admin/lexicon",
            json={"signal_key": signal, "term": "temporary demo term"},
            headers=headers,
        ).json()

        response = client.delete(f"/api/admin/lexicon/{created['id']}", headers=headers)
        assert response.status_code == 200
        assert response.json()["is_active"] is False

        db.expire_all()
        import uuid as _uuid

        assert db.get(LexiconTerm, _uuid.UUID(created["id"])) is not None

    def test_analytics_only_signals_are_flagged(self, client, auth_headers):
        """
        SRS 1.8 #6: these must not influence urgency or priority, whatever
        weight they carry. An evaluator editing the weight should see that.
        """
        rows = client.get("/api/admin/lexicon", headers=auth_headers("admin")).json()
        assert rows
        assert all("analytics_only" in row for row in rows)


# ══════════════════════════════════════════════════════════════
# SLA
# ══════════════════════════════════════════════════════════════
class TestSLA:
    def test_targets_are_listed(self, client, auth_headers):
        rows = client.get("/api/admin/sla", headers=auth_headers("manager")).json()
        assert rows
        assert all(row["first_response_mins"] > 0 for row in rows)

    def test_a_resolution_shorter_than_first_response_is_refused(
        self, client, auth_headers, db
    ):
        """
        Every complaint would breach resolution before its first reply was
        due, and the dashboard would show a system in total failure.
        """
        policy = db.execute(select(SLAPolicy)).scalars().first()
        response = client.patch(
            f"/api/admin/sla/{policy.id}",
            json={"first_response_mins": 600, "resolution_mins": 10},
            headers=auth_headers("admin"),
        )
        assert response.status_code == 422
        assert "shorter than" in response.text

    def test_a_target_can_be_retuned(self, client, auth_headers, db):
        headers = auth_headers("admin")
        policy = db.execute(select(SLAPolicy)).scalars().first()
        original = policy.first_response_mins

        response = client.patch(
            f"/api/admin/sla/{policy.id}",
            json={"first_response_mins": original + 5, "reason": "Demo."},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["first_response_mins"] == original + 5

        client.patch(
            f"/api/admin/sla/{policy.id}",
            json={"first_response_mins": original}, headers=headers,
        )


# ══════════════════════════════════════════════════════════════
# access
# ══════════════════════════════════════════════════════════════
class TestAccess:
    @pytest.mark.parametrize("role", ["agent", "reviewer", "customer"])
    def test_configuration_is_not_readable_by_everyone(
        self, client, auth_headers, role
    ):
        assert (
            client.get("/api/admin/config", headers=auth_headers(role)).status_code
            == 403
        )

    @pytest.mark.parametrize("role", ["manager", "evaluator"])
    def test_a_reader_cannot_write(self, client, auth_headers, role, ordinary_rule):
        """
        An evaluator verifies the system is configuration-driven by reading it;
        changing it is the administrator's act, on the record.
        """
        response = client.patch(
            f"/api/admin/rules/{ordinary_rule.rule_ref}",
            json={"precedence": 1},
            headers=auth_headers(role),
        )
        assert response.status_code == 403

    def test_an_evaluator_can_read_and_test(self, client, auth_headers):
        headers = auth_headers("evaluator")
        assert client.get("/api/admin/rules", headers=headers).status_code == 200
        assert (
            client.post(
                "/api/admin/rules/test",
                json={"description": LATE_PARCEL},
                headers=headers,
            ).status_code
            == 200
        )


# ══════════════════════════════════════════════════════════════
# prompts
# ══════════════════════════════════════════════════════════════
class TestPrompts:
    def test_registered_templates_are_listed(self, client, auth_headers):
        rows = client.get("/api/admin/prompts", headers=auth_headers("admin")).json()
        assert rows
        assert any(row["is_active"] for row in rows)

    def test_an_unknown_version_is_refused(self, client, auth_headers):
        response = client.patch(
            "/api/admin/prompts/complaint_intelligence",
            json={"version": "v99.9"},
            headers=auth_headers("admin"),
        )
        assert response.status_code == 422


# ══════════════════════════════════════════════════════════════
# the service, directly
# ══════════════════════════════════════════════════════════════
class TestService:
    def test_the_ruleset_checksum_covers_what_decides(self, db, restore_rules):
        """
        Two matrices that decide differently must not share a version string.
        """
        first = admin_config.bump_ruleset_version(db)
        db.commit()

        rule = db.execute(
            select(Rule).where(Rule.is_active.is_(True)).order_by(Rule.rule_ref)
        ).scalars().first()
        rule.precedence = (rule.precedence or 0) + 13
        db.flush()

        second = admin_config.bump_ruleset_version(db)
        db.commit()
        assert first != second

    def test_structural_keys_are_named_not_guessed(self):
        """
        The guard is a declared set, so adding a key to it is a deliberate act
        rather than a side effect of how a value happens to be shaped.
        """
        assert "ruleset_version" in admin_config.STRUCTURAL_KEYS
        assert "analytics_only_signals" in admin_config.STRUCTURAL_KEYS

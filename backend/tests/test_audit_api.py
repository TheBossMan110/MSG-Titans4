"""
The readable audit trail (FR lxiv; SRS Step 59).

The test that matters most is
:meth:`TestTrail.test_a_live_edit_is_on_the_record`. The Live Modification
Challenge writes an audit row for every change an evaluator makes; until this
endpoint existed nothing could show it to them, and a trail nobody can read is
indistinguishable from no trail.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from src.db.models import AppConfig


class TestTrail:
    def test_a_live_edit_is_on_the_record(self, client, auth_headers, db):
        """Change a threshold through the admin API; find the change in the trail."""
        headers = auth_headers("admin")
        original = dict(db.get(AppConfig, "thresholds").value)

        response = client.put(
            "/api/admin/config/thresholds",
            json={"value": {**original, "duplicate_similarity": 0.93},
                  "reason": "Audit trail check."},
            headers=headers,
        )
        assert response.status_code == 200, response.text

        trail = client.get(
            "/api/audit?entity_type=app_config&action=CONFIG_CHANGE", headers=headers
        ).json()

        assert trail["total"] >= 1
        latest = trail["items"][0]
        assert latest["actor"] == "admin@raftarxpress.com"
        assert latest["reason"] == "Audit trail check."
        # Two snapshots, not a diff. Both sides must be there.
        assert latest["before"]["value"]["duplicate_similarity"] != 0.93
        assert latest["after"]["value"]["duplicate_similarity"] == 0.93

        client.put(
            "/api/admin/config/thresholds", json={"value": original}, headers=headers
        )

    def test_the_trail_is_newest_first(self, client, auth_headers):
        items = client.get("/api/audit?size=50", headers=auth_headers("admin")).json()["items"]
        stamps = [row["at"] for row in items if row["at"]]
        assert stamps == sorted(stamps, reverse=True)

    def test_an_entity_trail_reads_forwards(self, client, auth_headers, db):
        """A trail is read in the order things happened."""
        headers = auth_headers("admin")
        original = dict(db.get(AppConfig, "thresholds").value)
        for value in (0.91, 0.92):
            client.put(
                "/api/admin/config/thresholds",
                json={"value": {**original, "duplicate_similarity": value}},
                headers=headers,
            )
        client.put("/api/admin/config/thresholds", json={"value": original}, headers=headers)

        trail = client.get("/api/audit/app_config/thresholds", headers=headers).json()
        assert len(trail) >= 3
        stamps = [row["at"] for row in trail]
        assert stamps == sorted(stamps)

    def test_filtering_by_actor(self, client, auth_headers):
        rows = client.get(
            "/api/audit?actor=admin@raftarxpress.com", headers=auth_headers("manager")
        ).json()["items"]
        assert all(row["actor"] == "admin@raftarxpress.com" for row in rows)

    def test_actions_are_counted_from_the_rows(self, client, auth_headers):
        """An action that never happened is absent, not listed at zero."""
        rows = client.get("/api/audit/actions", headers=auth_headers("evaluator")).json()
        assert all(row["count"] > 0 for row in rows)
        assert {"action", "count"} <= set(rows[0]) if rows else True


class TestAccess:
    @pytest.mark.parametrize("role", ["agent", "reviewer", "customer"])
    def test_the_organisation_trail_is_oversight_only(self, client, auth_headers, role):
        """
        An agent sees a complaint's history on the complaint. The whole
        organisation's log is a manager's, an administrator's and an
        evaluator's job.
        """
        assert client.get("/api/audit", headers=auth_headers(role)).status_code == 403

    @pytest.mark.parametrize("role", ["manager", "admin", "evaluator"])
    def test_oversight_roles_can_read(self, client, auth_headers, role):
        assert client.get("/api/audit", headers=auth_headers(role)).status_code == 200

    def test_the_trail_cannot_be_written_through_this_router(self, client, auth_headers):
        """Append-only. This router adds no way to change that."""
        headers = auth_headers("admin")
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            response = client.request(method, "/api/audit", headers=headers)
            assert response.status_code in (404, 405), method

    def test_pagination_is_honest_about_the_total(self, client, auth_headers, db):
        body = client.get("/api/audit?size=1", headers=auth_headers("admin")).json()
        from src.db.models import AuditLog

        actual = len(db.execute(select(AuditLog)).scalars().all())
        assert body["total"] == actual
        assert len(body["items"]) <= 1

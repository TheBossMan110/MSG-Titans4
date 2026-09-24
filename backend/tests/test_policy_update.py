"""
The Hidden Policy Update Challenge (SRS 1.8 #4).

Judges swap in an updated policy mid-evaluation and check the system uses it.
The test that matters most is
:meth:`TestHiddenPolicyUpdate.test_the_new_version_governs_the_next_analysis`,
which walks the whole demonstration: a complaint decided under v1, a new
version activated, and the next analysis grounded in v2 instead — with no
restart and no redeployment.

The second is :meth:`TestImpact.test_the_switch_reports_what_it_invalidated`.
Activating already worked; what nobody was told was *what they had just
invalidated*. Every complaint decided while the old version was active was
decided from text that no longer governs, and nothing was pointing that out.
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete, select

from src.db.enums import DocStatus
from src.db.models import (
    Chunk,
    Complaint,
    ComplaintPolicyRef,
    Document,
    DocumentSection,
    DocumentValidationIssue,
    DocumentVersion,
)
from src.services import policy_update

REFUND_QUESTION = (
    "I returned a damaged item for consignment CN-5511220 three "
    "weeks ago and I have still not been refunded. How long is this supposed "
    "to take?"
)


# ══════════════════════════════════════════════════════════════
# a two-version policy family
# ══════════════════════════════════════════════════════════════
@pytest.fixture
def policy_family(db):
    """
    One document with v1 active and v2 waiting, saying different things.

    Built directly rather than by uploading a file: the challenge is about
    what happens *after* a version is activated, and routing that through the
    parser would make this a test of the PDF reader.
    """
    import hashlib
    import uuid as _uuid

    tag = _uuid.uuid4().hex[:8].upper()
    ref = f"{tag}-REF-POL"

    document = Document(
        family_key=ref.lower(), title=f"{ref} refund policy", doc_type="POLICY"
    )
    db.add(document)
    db.flush()

    def make(label: str, status: str, text: str) -> DocumentVersion:
        version = DocumentVersion(
            document_id=document.id,
            doc_ref=ref,
            version=label,
            title=f"{ref} refund policy",
            status=status,
            file_format="PDF",
            file_name=f"{ref}_v{label}.pdf",
            file_path=f"fixture/{ref}_v{label}.pdf",
            file_hash=hashlib.sha256(f"{ref}{label}{text}".encode()).hexdigest(),
        )
        db.add(version)
        db.flush()
        db.add(
            Chunk(
                document_version_id=version.id,
                chunk_key=f"{ref}#v{label}#1",
                doc_ref=ref,
                doc_version=label,
                section_ref="4.1",
                ordinal=0,
                text=text,
            )
        )
        db.flush()
        return version

    v1 = make(
        "1.0", DocStatus.ACTIVE,
        "Refunds for damaged consumer electronics are issued within 30 business "
        "days of the returned item being received at the warehouse.",
    )
    v2 = make(
        "2.0", DocStatus.DRAFT,
        "Refunds for damaged consumer electronics are issued within 7 business "
        "days of the returned item being received at the warehouse.",
    )
    db.commit()

    yield document, v1, v2, ref

    version_ids = [v1.id, v2.id]
    db.execute(delete(ComplaintPolicyRef).where(
        ComplaintPolicyRef.document_version_id.in_(version_ids)
    ))
    db.execute(delete(Chunk).where(Chunk.document_version_id.in_(version_ids)))
    db.execute(delete(DocumentSection).where(
        DocumentSection.document_version_id.in_(version_ids)
    ))
    db.execute(delete(DocumentValidationIssue).where(
        DocumentValidationIssue.document_version_id.in_(version_ids)
    ))
    db.execute(delete(DocumentVersion).where(DocumentVersion.id.in_(version_ids)))
    db.execute(delete(Document).where(Document.id == document.id))
    db.commit()


@pytest.fixture
def complaint_citing_v1(db, policy_family):
    """A complaint already decided, resting on the version about to be replaced."""
    from complaint_processing.intake import next_public_ref
    from src.db.enums import ComplaintStatus, PolicyApplicability, PolicyRefSource

    _, v1, _, ref = policy_family

    complaint = Complaint(
        public_ref=next_public_ref(db),
        title="Refund still not received",
        description_raw=REFUND_QUESTION,
        description_clean=REFUND_QUESTION,
        status=ComplaintStatus.IN_PROGRESS,
        channel="WEB",
    )
    db.add(complaint)
    db.flush()
    db.add(
        ComplaintPolicyRef(
            complaint_id=complaint.id,
            source=PolicyRefSource.GENAI,
            doc_ref=ref,
            section_ref="4.1",
            doc_version="1.0",
            chunk_key=f"{ref}#v1.0#1",
            document_version_id=v1.id,
            resolved=True,
            was_active=True,
            applicability=PolicyApplicability.APPLICABLE,
        )
    )
    db.commit()

    yield complaint

    db.execute(delete(ComplaintPolicyRef).where(
        ComplaintPolicyRef.complaint_id == complaint.id
    ))
    db.execute(delete(Complaint).where(Complaint.id == complaint.id))
    db.commit()


# ══════════════════════════════════════════════════════════════
# the demonstration
# ══════════════════════════════════════════════════════════════
class TestHiddenPolicyUpdate:
    def test_the_new_version_governs_the_next_analysis(
        self, client, auth_headers, db, policy_family
    ):
        """
        The whole challenge in one test: the corpus answers with v1's figure,
        a new version is activated through the API, and the corpus then
        answers with v2's. No restart, no redeployment.
        """
        from knowledge_base import retrieval

        _, v1, v2, ref = policy_family

        query = "refund damaged consumer electronics business days"
        before = retrieval.retrieve(db, query, top_k=10, semantic=False)
        before_text = " ".join(hit.text or "" for hit in before.chunks)
        assert "30 business days" in before_text, "v1 must govern to begin with"
        assert "7 business days" not in before_text, "a DRAFT must not be retrievable"

        response = client.post(
            f"/api/documents/versions/{v2.id}/activate", headers=auth_headers("admin")
        )
        assert response.status_code == 200, response.text

        db.expire_all()
        after = retrieval.retrieve(db, query, top_k=10, semantic=False)
        after_text = " ".join(hit.text or "" for hit in after.chunks)
        assert "7 business days" in after_text, "v2 must now govern"
        assert "30 business days" not in after_text, "v1 must no longer be retrievable"

    def test_the_old_version_is_demoted_not_deleted(
        self, client, auth_headers, db, policy_family
    ):
        """
        Contradiction detection and the Policy Update Challenge both need the
        old text to compare against. Deleting it would make every decision
        taken under it unexplainable.
        """
        _, v1, v2, _ = policy_family
        client.post(
            f"/api/documents/versions/{v2.id}/activate", headers=auth_headers("admin")
        )

        db.expire_all()
        old = db.get(DocumentVersion, v1.id)
        assert old is not None
        assert old.status == DocStatus.SUPERSEDED
        assert old.superseded_by_id == v2.id
        assert old.superseded_at is not None

    def test_a_citation_to_the_old_version_is_now_outdated(
        self, client, auth_headers, db, policy_family
    ):
        """
        A reply grounded in last year's policy looks perfectly well-cited. The
        applicability verdict is the only thing that tells them apart.
        """
        from knowledge_base import versioning

        _, v1, v2, _ = policy_family
        assert versioning.applicability_for(db.get(DocumentVersion, v1.id)) == "APPLICABLE"

        client.post(
            f"/api/documents/versions/{v2.id}/activate", headers=auth_headers("admin")
        )
        db.expire_all()

        assert versioning.applicability_for(db.get(DocumentVersion, v1.id)) == "OUTDATED"
        assert versioning.applicability_for(db.get(DocumentVersion, v2.id)) == "APPLICABLE"

    def test_the_knowledge_base_version_moves(
        self, client, auth_headers, db, policy_family
    ):
        """
        Every validation run stamps it, so a decision stays attributable to
        the corpus that produced it.
        """
        from knowledge_base.versioning import knowledge_base_version

        _, _, v2, _ = policy_family
        before = knowledge_base_version(db)

        client.post(
            f"/api/documents/versions/{v2.id}/activate", headers=auth_headers("admin")
        )
        db.expire_all()

        assert knowledge_base_version(db) != before

    def test_only_an_admin_may_switch_a_policy(
        self, client, auth_headers, policy_family
    ):
        _, _, v2, _ = policy_family
        for role in ("agent", "reviewer", "manager", "evaluator"):
            response = client.post(
                f"/api/documents/versions/{v2.id}/activate", headers=auth_headers(role)
            )
            assert response.status_code == 403, f"{role} must not switch policy"


# ══════════════════════════════════════════════════════════════
# what the switch invalidated
# ══════════════════════════════════════════════════════════════
class TestImpact:
    def test_the_switch_reports_what_it_invalidated(
        self, client, auth_headers, policy_family, complaint_citing_v1
    ):
        """
        The question an administrator asks the moment they press the button.
        Activating already worked; nobody was told what it had just made stale.
        """
        _, _, v2, ref = policy_family

        body = client.post(
            f"/api/documents/versions/{v2.id}/activate", headers=auth_headers("admin")
        ).json()

        impact = body["impact"]
        assert impact is not None
        assert impact["superseded_version"] == "1.0"
        assert impact["active_version"] == "2.0"
        assert impact["affected_total"] >= 1
        assert complaint_citing_v1.public_ref in [
            row["public_ref"] for row in impact["complaints"]
        ]

    def test_an_open_complaint_is_counted_separately(
        self, client, auth_headers, policy_family, complaint_citing_v1
    ):
        """
        A closed complaint decided under the old policy is history. An open one
        is a decision somebody is still about to act on, and only the second is
        worth a person's time.
        """
        _, _, v2, _ = policy_family
        body = client.post(
            f"/api/documents/versions/{v2.id}/activate", headers=auth_headers("admin")
        ).json()

        assert body["impact"]["affected_open"] >= 1
        assert "open complaint" in body["message"]

    def test_a_settled_complaint_is_listed_but_not_counted_as_open(
        self, client, auth_headers, db, policy_family, complaint_citing_v1
    ):
        from src.db.enums import ComplaintStatus

        complaint_citing_v1.status = ComplaintStatus.CLOSED
        db.commit()

        _, _, v2, _ = policy_family
        impact = client.post(
            f"/api/documents/versions/{v2.id}/activate", headers=auth_headers("admin")
        ).json()["impact"]

        assert impact["affected_total"] >= 1
        assert impact["affected_open"] == 0

    def test_nothing_is_re_analysed_automatically(
        self, client, auth_headers, db, policy_family, complaint_citing_v1
    ):
        """
        Re-running hundreds of complaints on a policy change would spend the
        free-tier quota in one click, and silently rewriting a decision an
        agent has already acted on is worse than leaving it visibly stale.
        """
        before = complaint_citing_v1.analyzed_at
        before_status = complaint_citing_v1.status

        _, _, v2, _ = policy_family
        client.post(
            f"/api/documents/versions/{v2.id}/activate", headers=auth_headers("admin")
        )

        db.expire_all()
        after = db.execute(
            select(Complaint).where(Complaint.id == complaint_citing_v1.id)
        ).scalars().one()
        assert after.analyzed_at == before
        assert after.status == before_status

    def test_the_impact_is_readable_on_its_own(
        self, client, auth_headers, policy_family, complaint_citing_v1
    ):
        _, v1, _, _ = policy_family
        body = client.get(
            f"/api/documents/versions/{v1.id}/impact", headers=auth_headers("manager")
        ).json()

        assert body["affected_total"] >= 1
        assert body["superseded_version"] == "1.0"

    def test_an_unknown_version_is_404(self, client, auth_headers):
        import uuid as _uuid

        response = client.get(
            f"/api/documents/versions/{_uuid.uuid4()}/impact",
            headers=auth_headers("admin"),
        )
        assert response.status_code == 404

    def test_a_first_activation_invalidates_nothing(
        self, client, auth_headers, db, policy_family
    ):
        """
        Activating a version that replaces nothing must not report a phantom
        blast radius.
        """
        document, v1, v2, _ = policy_family
        v1.status = DocStatus.SUPERSEDED
        db.commit()

        body = client.post(
            f"/api/documents/versions/{v2.id}/activate", headers=auth_headers("admin")
        ).json()
        assert body["superseded_version"] is None
        assert body["impact"] is None


# ══════════════════════════════════════════════════════════════
# the standing figure
# ══════════════════════════════════════════════════════════════
class TestStaleCitations:
    def test_no_citations_reports_null_not_zero(self, db):
        """
        SRS 1.8 #17. No citations is not the same as no stale ones, and a
        dashboard reading "0 stale" on an empty corpus is exactly the
        unsourced reassurance the rule forbids.
        """
        db.execute(delete(ComplaintPolicyRef))
        db.commit()
        assert policy_update.stale_citation_count(db) is None

    def test_a_superseded_citation_is_counted(
        self, client, auth_headers, db, policy_family, complaint_citing_v1
    ):
        assert policy_update.stale_citation_count(db) == 0

        _, _, v2, _ = policy_family
        client.post(
            f"/api/documents/versions/{v2.id}/activate", headers=auth_headers("admin")
        )
        db.expire_all()

        assert policy_update.stale_citation_count(db) == 1

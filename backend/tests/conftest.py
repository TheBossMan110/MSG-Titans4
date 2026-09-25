"""
Shared pytest fixtures.

By default the test database is a throwaway SQLite file.  That keeps the suite
fast and offline, and it continuously proves the demo-day fallback
(``DATABASE_URL=sqlite:///...``) really works.

It is **not** the deployment target, though, and two real bugs once passed every
SQLite test and failed on Supabase.  So the whole suite can also be pointed at
PostgreSQL::

    SUPPORTNOVA_TEST_DATABASE_URL=postgresql+psycopg://user:pw@host/db pytest -q

CI runs it both ways.  The override is a *separate* variable from
``DATABASE_URL`` on purpose: a stray development ``DATABASE_URL`` in the
environment must never cause the suite to drop and recreate every table in a
real database.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEST_DB = ROOT / "var" / "test_supportnova.db"

# Must be set BEFORE any src.* import: settings is a cached singleton.
TEST_DB.parent.mkdir(parents=True, exist_ok=True)
_OVERRIDE = os.environ.get("SUPPORTNOVA_TEST_DATABASE_URL", "").strip()
USING_POSTGRES = _OVERRIDE.startswith(("postgresql", "postgres"))
os.environ["DATABASE_URL"] = _OVERRIDE or f"sqlite:///{TEST_DB.as_posix()}"
os.environ["APP_ENV"] = "test"
os.environ["JWT_SECRET"] = "test-secret-not-used-anywhere-real"
os.environ["LLM_CACHE_ENABLED"] = "false"
# Tests run offline. Disabling embeddings keeps the suite fast and
# deterministic, and continuously exercises the lexical-only degradation
# path that must work during a provider outage (NFR 5).
os.environ["EMBEDDING_ENABLED"] = "false"
os.environ["STORAGE_BACKEND"] = "local"
os.environ["RATE_LIMIT_LOGIN"] = "1000/minute"
os.environ["RATE_LIMIT_DEFAULT"] = "10000/minute"
# Every provider key is blanked -- not defaulted. A developer's real key in
# the environment would otherwise make the suite reach the network, and an
# unreachable provider costs ~70s of timeout and retry per escalated
# complaint. Pipeline 1 is exercised deliberately, by injecting a chain.
os.environ["GEMINI_API_KEY"] = ""
os.environ["GROQ_API_KEY"] = ""
os.environ["OPENROUTER_API_KEY"] = ""

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from genai_pipeline.prompts import seed_prompts  # noqa: E402
from src.db.base import Base, SessionLocal, engine  # noqa: E402
from src.db.seed.core_data import (  # noqa: E402
    seed_policy_config,
    seed_signals,
    seed_taxonomy,
)
from src.db.seed.rules import seed_rules  # noqa: E402
from src.db.seed.users import DEFAULT_PASSWORD, seed_users  # noqa: E402
from src.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _database() -> Generator[None, None, None]:
    """One freshly-seeded database for the whole session."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    db = SessionLocal()
    try:
        seed_taxonomy(db)
        seed_policy_config(db)
        seed_signals(db)
        seed_users(db)
        # Rules last: they reference categories, departments, priorities,
        # escalation levels and signal keys, all of which must exist first.
        seed_rules(db)
        # Part of `python -m src.db.seed.run`, so the suite mirrors a
        # seeded deployment. Without it the prompt registry is empty
        # here while the pipeline quietly uses the on-disk fallback,
        # and every registry code path goes untested.
        seed_prompts(db)
        db.commit()
    finally:
        db.close()

    yield

    # Leave a real database's tables dropped but the file-based one removed.
    if USING_POSTGRES:
        Base.metadata.drop_all(engine)
    engine.dispose()
    if not USING_POSTGRES:
        TEST_DB.unlink(missing_ok=True)


@pytest.fixture
def db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def seed_password() -> str:
    return DEFAULT_PASSWORD


def _login(client: TestClient, email: str, password: str) -> str:
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture
def auth_headers(client: TestClient, seed_password: str):
    """``auth_headers("admin")`` -> Authorization header for that seeded role."""
    emails = {
        "evaluator": "evaluator@raftarxpress.com",
        "admin": "admin@raftarxpress.com",
        "manager": "manager@raftarxpress.com",
        "reviewer": "reviewer@raftarxpress.com",
        "agent": "agent.billing@raftarxpress.com",
        "customer": "customer@raftarxpress.com",
    }

    def _make(role: str) -> dict[str, str]:
        token = _login(client, emails[role], seed_password)
        return {"Authorization": f"Bearer {token}"}

    return _make


@pytest.fixture(scope="session")
def sample_documents_dir():
    """
    Locate a corpus file by name, wherever its domain happens to be.

    Returns a callable rather than a folder. The corpus is split across
    ``dataset/<domain>/documents/``, and which domain a policy belongs to is a
    business fact that can change -- DEL-POL-04 is a logistics document today
    and might be filed elsewhere tomorrow. A test that hardcoded the domain
    would break on a decision that has nothing to do with what it is testing.

    Usage::

        data = sample_documents_dir("DEL-POL-04_v2.1.pdf").read_bytes()
        yaml = sample_documents_dir("source/DEL-POL-04_v2.1.yaml").read_text()
    """
    from src.core.config import settings

    def _find(name: str) -> Path:
        for folder in settings.document_dirs:
            candidate = folder / name
            if candidate.exists():
                return candidate
        searched = ", ".join(str(f) for f in settings.document_dirs)
        raise FileNotFoundError(f"'{name}' is not in the corpus. Searched: {searched}")

    return _find


def _corpus_files(*, limit_per_format: int = 2) -> list[Path]:
    """
    A stable sample of the configured corpus, both formats.

    Sorted so a run is reproducible: a fixture that ingested a different
    document each time would make a failure impossible to repeat.
    """
    from src.core.config import settings

    def is_active(path: Path) -> bool:
        """
        Whether the document's source declares it in force.

        A corpus carries superseded and draft versions on purpose -- the policy
        challenges need them -- but a fixture that happened to ingest two
        legacy versions made every test asserting ACTIVE fail for a reason
        that had nothing to do with what it was testing.
        """
        source = path.parent / "source" / f"{path.stem}.yaml"
        if not source.exists():
            return True
        text = source.read_text(encoding="utf-8")
        return "status: ACTIVE" in text or "status:" not in text

    chosen: list[Path] = []
    for suffix in (".pdf", ".docx"):
        found: list[Path] = []
        for folder in settings.document_dirs:
            found.extend(sorted(folder.glob(f"*{suffix}")))
        active = [p for p in found if is_active(p)] or found
        chosen.extend(active[:limit_per_format])
    return chosen


@dataclass(frozen=True)
class SampleDocument:
    """One corpus document, with the source it was rendered from."""

    pdf: Path
    source: Path

    @property
    def name(self) -> str:
        return self.pdf.name

    @property
    def doc_ref(self) -> str:
        return self.pdf.stem.split("_v")[0]

    def spec(self) -> dict:
        import yaml as _yaml

        return _yaml.safe_load(self.source.read_text(encoding="utf-8"))


@pytest.fixture
def a_cited_document(ingested_kb, db):
    """
    A document in the index that has more than one chunk, and one of its chunks.

    Returns ``(doc_ref, chunk)``. Citation tests need a reference that resolves
    and a section that exists; which document supplies them is not something
    any of them should assert.
    """
    from sqlalchemy import select as _select

    from src.db.enums import DocStatus as _DocStatus
    from src.db.models import Chunk as _Chunk
    from src.db.models import DocumentVersion as _Version

    active = {
        v.id
        for v in db.execute(
            _select(_Version).where(_Version.status == _DocStatus.ACTIVE)
        ).scalars()
    }
    chunks = [
        c
        for c in db.execute(_select(_Chunk)).scalars().all()
        if c.document_version_id in active
    ]
    assert chunks, "no ACTIVE document was indexed"

    # ACTIVE only. A citation to a superseded version resolves but does not
    # support, so a fixture that handed one back would make a guard test fail
    # for being right.
    by_ref: dict[str, list] = {}
    for chunk in chunks:
        by_ref.setdefault(chunk.doc_ref, []).append(chunk)

    # A multi-section document, so "the whole document" and "one section" are
    # genuinely different scopes.
    doc_ref, group = max(by_ref.items(), key=lambda item: len(item[1]))
    assert len(group) > 1, "no indexed document has more than one section"
    return doc_ref, sorted(group, key=lambda c: c.ordinal or 0)[1]


@pytest.fixture
def an_indexed_phrase(ingested_kb, db):
    """
    A phrase that is genuinely in the index, and where it came from.

    Returns ``(doc_ref, section_ref, phrase)``. Retrieval tests need a query
    the corpus can answer: querying words it happens not to contain proves
    nothing, and the zero result reads as a retrieval bug.
    """
    from sqlalchemy import select as _select

    from src.db.models import Chunk as _Chunk

    chunks = db.execute(_select(_Chunk)).scalars().all()
    assert chunks, "nothing was indexed"

    # The longest chunk gives the best chance of a distinctive run of words.
    chunk = max(chunks, key=lambda c: len(c.text or ""))
    words = (chunk.text or "").split()
    assert len(words) >= 6, "indexed text is too short to query with"

    # From the middle, away from the heading a dozen documents may share.
    start = len(words) // 3
    return chunk.doc_ref, chunk.section_ref, " ".join(words[start:start + 6])


@pytest.fixture
def a_document(ingested_kb) -> SampleDocument:
    """
    A document that `ingested_kb` actually ingested, with its YAML source.

    Tests that re-upload a file, or render a new version of one, need a real
    pair. Which document it is should not matter to any of them.
    """
    from src.core.config import settings

    for name in ingested_kb:
        if not name.endswith(".pdf"):
            continue
        for folder in settings.document_dirs:
            pdf = folder / name
            source = folder / "source" / f"{Path(name).stem}.yaml"
            if pdf.exists() and source.exists():
                return SampleDocument(pdf=pdf, source=source)

    pytest.fail("no ingested PDF has a YAML source beside it")


@pytest.fixture
def ingested_kb(db, sample_documents_dir):
    """
    A knowledge base with the RaftarXpress corpus loaded.

    Function-scoped and self-cleaning so retrieval tests never see rows left
    behind by a version-control test that deliberately superseded something.
    """
    from sqlalchemy import delete

    from knowledge_base.ingest import ingest_document
    from src.db.models import (
        Chunk,
        Document,
        DocumentSection,
        DocumentValidationIssue,
        DocumentVersion,
    )

    def _purge():
        for model in (
            Chunk, DocumentSection, DocumentValidationIssue, DocumentVersion, Document,
        ):
            db.execute(delete(model))
        db.commit()


    _purge()
    results = {}
    # Discovered, never named. Naming three files meant that changing the
    # corpus failed eleven tests on a missing filename rather than on anything
    # they were written to check.
    #
    # A couple of each format, so the PDF and DOCX parsers are both exercised
    # without ingesting a 25-document corpus for every test that needs one.
    for path in _corpus_files(limit_per_format=2):
        results[path.name] = ingest_document(db, path.read_bytes(), path.name)
    db.commit()

    assert results, (
        "no documents in the configured corpus -- run "
        "scripts/make_sample_documents.py"
    )
    yield results

    _purge()

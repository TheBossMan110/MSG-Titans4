"""
Versioned prompt templates (FR lii, FR liii; SRS Steps 48-49).

    "Prompts must be centrally stored and versioned. Teams must not scatter
     uncontrolled prompts across source-code files."      — SRS Step 48

So every prompt lives in ``prompt_templates/<name>/v<major>.<minor>.j2`` and
this module is the only way to reach one.  Nothing else in the codebase builds
a prompt string.

Three properties matter:

**Versioned.**  Templates are never edited in place once used.  A change means
a new file, and ``genai_runs.prompt_version`` records which one produced each
result — so a comparison report stays meaningful after the prompts move on.

**Checksummed.**  The registry stores a SHA-256 of the rendered template file.
A template edited without a version bump is therefore detectable, which is the
difference between "versioned" and "versioned in principle".

**Enum-injected.**  Category, department, priority and escalation codes are
read from the database at render time.  Adding a complaint category never
requires touching a prompt file, which is what SRS 1.8 #5 asks for.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from security.injection_defense import DATA_NOT_INSTRUCTIONS_NOTICE, fence
from src.core.config import settings
from src.core.errors import AppError
from src.core.logging import get_logger
from src.core.refcache import reference_data
from src.db.models import (
    AppConfig,
    Category,
    Department,
    EscalationLevel,
    PriorityLevel,
    PromptVersion,
)

log = get_logger("genai_pipeline.prompts")

_VERSION_FILE = re.compile(r"^v(\d+)\.(\d+)\.j2$")

SENTIMENT_VALUES = ["POSITIVE", "NEUTRAL", "NEGATIVE", "STRONGLY_NEGATIVE"]
URGENCY_VALUES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]


class PromptError(AppError):
    code = "PROMPT_ERROR"


@dataclass(slots=True)
class RenderedPrompt:
    """A prompt ready to send, with the provenance needed to reproduce it."""

    name: str
    version: str
    text: str
    checksum: str
    variables: dict[str, Any]

    @property
    def token_estimate(self) -> int:
        return max(1, len(self.text) // 4)

    def provenance(self) -> dict[str, Any]:
        """Stored on ``genai_runs`` so a result can be traced to its prompt."""
        return {
            "prompt_name": self.name,
            "prompt_version": self.version,
            "prompt_checksum": self.checksum,
        }


# ══════════════════════════════════════════════════════════════
# template discovery
# ══════════════════════════════════════════════════════════════
def _environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(settings.prompt_dir)),
        undefined=StrictUndefined,  # a missing variable is a bug, not a blank
        trim_blocks=True,
        lstrip_blocks=True,
        autoescape=False,           # prompts are plain text, not HTML
    )


def available_versions(name: str) -> list[str]:
    """Every version of a template, newest first."""
    directory = settings.prompt_dir / name
    if not directory.exists():
        return []

    versions: list[tuple[tuple[int, int], str]] = []
    for path in directory.glob("v*.j2"):
        match = _VERSION_FILE.match(path.name)
        if match:
            versions.append(((int(match[1]), int(match[2])), f"v{match[1]}.{match[2]}"))
    return [version for _, version in sorted(versions, reverse=True)]


def latest_version(name: str) -> str:
    versions = available_versions(name)
    if not versions:
        raise PromptError(f"No prompt template found for '{name}' in {settings.prompt_dir}")
    return versions[0]


def template_path(name: str, version: str) -> Path:
    return settings.prompt_dir / name / f"{version}.j2"


def checksum_of(name: str, version: str) -> str:
    path = template_path(name, version)
    if not path.exists():
        raise PromptError(f"Prompt template not found: {name} {version}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


@reference_data("active_prompt_version")
def active_version(db: Session, name: str) -> str:
    """
    The version the database says is active, falling back to the newest file.

    The database is authoritative so an administrator can pin a version without
    a deploy; the file fallback means a fresh checkout still works.
    """
    row = db.execute(
        select(PromptVersion).where(
            PromptVersion.name == name, PromptVersion.is_active.is_(True)
        )
    ).scalars().first()
    if row is not None:
        if template_path(name, row.version).exists():
            return row.version
        log.warning(
            "active_prompt_missing_on_disk",
            name=name, version=row.version, falling_back_to="latest file",
        )
    return latest_version(name)


# ══════════════════════════════════════════════════════════════
# enum injection
# ══════════════════════════════════════════════════════════════
@reference_data("enum_context")
def build_enum_context(db: Session) -> dict[str, Any]:
    """
    Read the live taxonomy for injection into a prompt.

    This is why a new category needs no prompt edit: the values the model is
    permitted to use come from the same rows the validator checks against, so
    the two cannot drift.
    """
    categories: list[dict[str, Any]] = []
    for category in db.execute(
        select(Category)
        .where(Category.is_active.is_(True))
        .order_by(Category.code)
        .options(selectinload(Category.subcategories))
    ).scalars():
        categories.append(
            {
                "code": category.code,
                "name": category.name,
                "subcategories": [
                    sub.code for sub in sorted(category.subcategories, key=lambda s: s.code)
                    if sub.is_active
                ],
            }
        )

    departments = [
        {"code": d.code, "name": d.name, "description": d.description}
        for d in db.execute(
            select(Department).where(Department.is_active.is_(True)).order_by(Department.code)
        ).scalars()
    ]

    priorities = [
        p.code for p in db.execute(select(PriorityLevel).order_by(PriorityLevel.rank)).scalars()
    ]
    escalations = [
        e.code for e in db.execute(select(EscalationLevel).order_by(EscalationLevel.rank)).scalars()
    ]

    organisation = db.get(AppConfig, "organisation")
    profile = organisation.value if organisation and isinstance(organisation.value, dict) else {}

    return {
        "categories": categories,
        "departments": departments,
        "priority_values": priorities,
        "escalation_values": escalations,
        "urgency_values": URGENCY_VALUES,
        "sentiment_values": SENTIMENT_VALUES,
        "organisation": {
            "name": profile.get("name", "the company"),
            "industry": profile.get("industry", "a consumer business"),
            "regions": profile.get("regions", []),
        },
    }


# ══════════════════════════════════════════════════════════════
# rendering
# ══════════════════════════════════════════════════════════════
# Variables whose value is recorded as a size rather than verbatim.
#
# Both are reproducible from elsewhere and expensive to duplicate: the
# complaint text already lives in ``complaints``, and the retrieved policy text
# is identified chunk-by-chunk in ``genai_runs.policy_snapshot``. Copying
# either into ``request_payload`` on every attempt would multiply the stored
# text by the number of retries and widen the data-protection surface for
# customer content with nothing gained.
_SUMMARISED_VARIABLES = ("fenced_complaint", "policy_context")


def _recordable(variables: dict[str, Any]) -> dict[str, Any]:
    """The provenance-safe view of the render variables."""
    recorded: dict[str, Any] = {}
    for key, value in variables.items():
        if key in _SUMMARISED_VARIABLES:
            recorded[f"{key}_chars"] = len(value) if isinstance(value, str) else 0
        else:
            recorded[key] = value
    return recorded


def render(
    db: Session,
    name: str,
    *,
    version: str | None = None,
    **variables: Any,
) -> RenderedPrompt:
    """
    Render a prompt template.

    ``StrictUndefined`` means a variable the template expects but the caller
    forgot raises here rather than silently rendering an empty section — a
    prompt quietly missing its policy extracts would produce plausible,
    ungrounded output.
    """
    version = version or active_version(db, name)
    relative = f"{name}/{version}.j2"

    try:
        template = _environment().get_template(relative)
    except TemplateNotFound as exc:
        raise PromptError(f"Prompt template not found: {relative}") from exc

    context: dict[str, Any] = {
        **build_enum_context(db),
        "data_not_instructions_notice": DATA_NOT_INSTRUCTIONS_NOTICE,
        **variables,
    }

    try:
        text = template.render(**context)
    except Exception as exc:
        raise PromptError(
            f"Failed to render {relative}: {type(exc).__name__}: {exc}"
        ) from exc

    rendered = RenderedPrompt(
        name=name,
        version=version,
        text=text.strip(),
        checksum=checksum_of(name, version),
        variables=_recordable(variables),
    )
    log.debug(
        "prompt_rendered",
        name=name, version=version, chars=len(rendered.text),
        tokens=rendered.token_estimate,
    )
    return rendered


def _tier(complaint: Any) -> str | None:
    from python_validation.signals import tier_of

    return tier_of(
        getattr(getattr(complaint, "customer", None), "tier", None)
        or getattr(complaint, "customer_type", None)
    )


def render_complaint_intelligence(
    db: Session,
    *,
    complaint_text: str,
    complaint: Any | None = None,
    policy_context: str = "",
    version: str | None = None,
) -> RenderedPrompt:
    """
    Render the classification prompt for one complaint.

    ``complaint_text`` must already have passed through
    :func:`security.injection_defense.scan`; this function fences it but does
    not sanitise it, and fencing unsanitised input would embed a forged
    delimiter verbatim.
    """
    metadata = {
        "public_ref": getattr(complaint, "public_ref", None),
        "title": getattr(complaint, "title", None),
        "product": getattr(complaint, "product", None),
        "order_ref": getattr(complaint, "order_ref", None),
        "channel": getattr(complaint, "channel", None),
        "customer_tier": _tier(complaint),
        "previous_contacts": getattr(complaint, "repeat_count", None) or None,
    }

    return render(
        db,
        "complaint_intelligence",
        version=version,
        complaint=metadata,
        fenced_complaint=fence(complaint_text),
        policy_context=policy_context,
    )


# ══════════════════════════════════════════════════════════════
# registry
# ══════════════════════════════════════════════════════════════
def sync_registry(db: Session) -> dict[str, Any]:
    """
    Record every template file in ``prompt_versions`` with its checksum.

    A template edited in place without a version bump shows up here as a
    changed checksum against an already-used version — which is the only way
    "prompts are versioned" is a checkable claim rather than a convention.
    """
    discovered = 0
    changed: list[str] = []

    if not settings.prompt_dir.exists():
        return {"discovered": 0, "changed": []}

    for directory in sorted(p for p in settings.prompt_dir.iterdir() if p.is_dir()):
        name = directory.name
        versions = available_versions(name)
        if not versions:
            continue

        for version in versions:
            digest = checksum_of(name, version)
            path = template_path(name, version)
            relative = path.relative_to(settings.prompt_dir.parent).as_posix()

            existing = db.execute(
                select(PromptVersion).where(
                    PromptVersion.name == name, PromptVersion.version == version
                )
            ).scalars().first()

            if existing is None:
                db.add(
                    PromptVersion(
                        name=name, version=version, file_path=relative,
                        checksum=digest, is_active=False,
                    )
                )
                discovered += 1
            elif existing.checksum != digest:
                log.warning(
                    "prompt_edited_without_version_bump",
                    name=name, version=version,
                    was=existing.checksum[:12], now=digest[:12],
                )
                existing.checksum = digest
                existing.file_path = relative
                changed.append(f"{name} {version}")

        db.flush()

        # Newest version becomes active when nothing has been pinned.
        has_active = db.execute(
            select(PromptVersion).where(
                PromptVersion.name == name, PromptVersion.is_active.is_(True)
            )
        ).scalars().first()
        if has_active is None:
            newest = db.execute(
                select(PromptVersion).where(
                    PromptVersion.name == name, PromptVersion.version == versions[0]
                )
            ).scalars().first()
            if newest is not None:
                newest.is_active = True
        db.flush()

    log.info("prompt_registry_synced", discovered=discovered, changed=changed)
    return {"discovered": discovered, "changed": changed}


def activate(db: Session, name: str, version: str) -> PromptVersion:
    """
    Make ``version`` the active template for ``name``.

    Deliberately not done by :func:`sync_registry`: dropping a new file into
    the repository must not silently redirect production traffic away from a
    version an administrator pinned. Promotion is an explicit act, exposed at
    ``PATCH /api/admin/prompts/{name}`` so it needs no deploy.

    The deactivate-flush-activate order is not cosmetic. ``ux_prompt_one_active``
    is a partial unique index, so two rows briefly active in the same
    transaction violates it on PostgreSQL.
    """
    if not template_path(name, version).exists():
        raise PromptError(f"Prompt template not found on disk: {name} {version}")

    target = db.execute(
        select(PromptVersion).where(
            PromptVersion.name == name, PromptVersion.version == version
        )
    ).scalars().first()
    if target is None:
        raise PromptError(
            f"{name} {version} is not registered; run the prompt seeder first"
        )

    for row in db.execute(
        select(PromptVersion).where(
            PromptVersion.name == name, PromptVersion.is_active.is_(True)
        )
    ).scalars():
        row.is_active = False
    db.flush()

    target.is_active = True
    target.checksum = checksum_of(name, version)
    db.flush()

    log.info("prompt_version_activated", name=name, version=version)
    return target


def read_template_text(name: str, version: str) -> str | None:
    """Read prompt template source from disk."""
    path = template_path(name, version)
    if path.exists():
        try:
            return path.read_text(encoding="utf-8")
        except Exception:
            return None
    return None


def registry_status(db: Session) -> list[dict[str, Any]]:
    """Every registered template with a live on-disk integrity check."""
    rows = db.execute(
        select(PromptVersion).order_by(PromptVersion.name, PromptVersion.version)
    ).scalars().all()

    status: list[dict[str, Any]] = []
    for row in rows:
        path = template_path(row.name, row.version)
        on_disk = path.exists()
        current = checksum_of(row.name, row.version) if on_disk else None
        template_text = None
        if on_disk:
            try:
                template_text = path.read_text(encoding="utf-8")
            except Exception:
                pass
        status.append(
            {
                "name": row.name,
                "version": row.version,
                "file_path": row.file_path,
                "is_active": row.is_active,
                "checksum": row.checksum,
                "on_disk": on_disk,
                # False means the file changed without a version bump -- the
                # one thing a version registry exists to detect.
                "checksum_matches": on_disk and current == row.checksum,
                "template_text": template_text,
            }
        )
    return status


def seed_prompts(db: Session) -> dict[str, int]:
    """Seeder entry point."""
    result = sync_registry(db)
    return {"discovered": result["discovered"], "checksum_changed": len(result["changed"])}

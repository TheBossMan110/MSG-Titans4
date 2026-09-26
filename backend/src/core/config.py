"""
Central application configuration.

Every tunable value lives here or in ``config/*.yaml`` — never hard-coded in
business logic.  This is what lets evaluators change thresholds, SLAs,
categories and rules at runtime without a code change
(SRS 1.8 #14 "Live Modification Challenge").
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]

# The repository root, one level above ``backend/``. The dataset is a sibling
# of the backend rather than a child of it, because it is authored by people
# who never open this code -- and because the same corpus feeds the frontend's
# fixtures and any future service.
PROJECT_DIR = ROOT_DIR.parent

# A '%XX' sequence means the value was already percent-encoded; encoding it
# again would turn '%40' into '%2540'.
_PERCENT_ESCAPE = re.compile(r"%[0-9A-Fa-f]{2}")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── application ───────────────────────────────────────────
    app_env: str = "development"
    app_name: str = "SupportNova"
    app_version: str = "0.1.0"
    api_prefix: str = "/api"
    log_level: str = "INFO"

    # ── database ──────────────────────────────────────────────
    database_url: str = "sqlite:///./supportnova.db"
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_echo: bool = False

    # ── storage ───────────────────────────────────────────────
    storage_backend: str = "local"
    storage_local_dir: Path = ROOT_DIR / "var" / "uploads"
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_storage_bucket: str = "documents"

    # ── auth (FR i, ii) ───────────────────────────────────────
    jwt_secret: str = "insecure-dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 120
    refresh_token_days: int = 7

    # ── generative ai (FR xii) ────────────────────────────────
    llm_primary_provider: str = "gemini"
    llm_fallback_provider: str = "groq"
    llm_timeout_seconds: int = 30
    # How long a model may "think" before answering. Classification against a
    # fixed schema gains little from long reasoning and loses seconds to it, so
    # the default is low. minimal | low | medium | high | default (provider's own).
    llm_reasoning_effort: str = "low"
    llm_max_retries: int = 2          # SRS Step 47: bounded, never infinite
    llm_cache_enabled: bool = True
    llm_temperature_intelligence: float = 0.1
    # How much room a provider gets to answer. The intelligence schema is
    # large, and a model that fills it verbosely hits the cap and returns
    # JSON cut off mid-structure -- which reads as a malformed response
    # rather than as a budget that was too small.
    llm_max_output_tokens: int = 4096
    llm_temperature_response: float = 0.4

    gemini_api_key: str = ""
    # A comma-separated chain, tried left to right. Google retires model names
    # and 503s the busiest ones on the free tier, so pinning a single name is
    # how the whole GenAI pipeline goes dark without a line of code changing.
    gemini_model: str = "gemini-3.5-flash-lite,gemini-2.5-flash-lite,gemini-3.1-flash-lite"
    gemini_embed_model: str = "gemini-embedding-001"

    groq_api_key: str = ""
    # Verified against GET /models on 2026-09-25: Groq no longer serves Llama.
    groq_model: str = "openai/gpt-oss-120b,qwen/qwen3.8-27b"
    groq_base_url: str = "https://api.groq.com/openai/v1"

    # ── email channel ─────────────────────────────────────────
    # The support mailbox customers write to. Gmail is read over IMAP and
    # replied from over SMTP, both with a Google "App Password" (needs 2-Step
    # Verification on the account). Resend is used for sending instead when
    # RESEND_FROM is an address on a domain verified with Resend -- it cannot
    # send as, or receive for, a gmail.com address.
    email_address: str = ""
    email_app_password: str = ""
    email_imap_host: str = "imap.gmail.com"
    email_imap_port: int = 993
    email_smtp_host: str = "smtp.gmail.com"
    email_smtp_port: int = 587
    email_poll_seconds: int = 60
    email_sender_name: str = "RaftarXpress Support"
    resend_api_key: str = ""
    resend_from: str = ""
    # Where links in emails point: the website customers sign in to.
    public_app_url: str = "http://localhost:3000"

    # DeepSeek: OpenAI-compatible API, pay-per-use (not a free tier).
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com"

    openrouter_api_key: str = ""
    openrouter_model: str = "z-ai/glm-5.2:free,nvidia/nemotron-3-super-120b-a12b:free,dots-studio/dots-3-note-preview:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # ── retrieval (SRS Steps 6, 25) ───────────────────────────
    embedding_enabled: bool = True
    embedding_dim: int = 768
    retrieval_top_k: int = 8
    # Seconds reference data (rules, lexicon, taxonomy, config) may be served
    # from memory. Edits made through this server invalidate at once; this
    # only bounds edits made by another process (a seeding script). The server
    # refreshes ahead of expiry, so the length costs nothing. 0 turns it off.
    reference_cache_seconds: int = 900
    chunk_tokens: int = 800
    chunk_overlap: int = 120

    # ── pipeline thresholds (SRS Steps 10, 35, 52) ────────────
    duplicate_similarity_threshold: float = 0.85
    near_duplicate_threshold: float = 0.70
    hallucination_overlap_threshold: float = 0.35
    min_complaint_length: int = 20
    max_complaint_length: int = 8000
    max_upload_mb: int = 10

    # ── cors ──────────────────────────────────────────────────
    cors_origins: str = "http://localhost:3000"

    # ── rate limiting ─────────────────────────────────────────
    rate_limit_login: str = "5/minute"
    rate_limit_default: str = "120/minute"

    # ── derived paths ─────────────────────────────────────────
    config_dir: Path = Field(default=ROOT_DIR / "config")
    prompt_dir: Path = Field(default=ROOT_DIR / "prompt_templates")
    rules_dir: Path = Field(default=ROOT_DIR / "complaint_rules")
    routing_rules_dir: Path = Field(default=ROOT_DIR / "routing_rules")
    escalation_rules_dir: Path = Field(default=ROOT_DIR / "escalation_rules")
    reports_dir: Path = Field(default=ROOT_DIR / "reports" / "generated")

    # ── dataset (a sibling of backend/, not a child) ──────────
    dataset_dir: Path = Field(default=PROJECT_DIR / "dataset")
    # Domains the corpus is split across. Adding one is a folder and an entry
    # here -- no loader changes -- which is the same configuration-as-data
    # stance the taxonomy takes.
    dataset_domains: str = "ecommerce,logistics"

    @property
    def dataset_domain_list(self) -> list[str]:
        return [d.strip() for d in self.dataset_domains.split(",") if d.strip()]

    @property
    def document_dirs(self) -> list[Path]:
        """Every folder holding rendered knowledge-base documents."""
        return [
            self.dataset_dir / domain / "documents"
            for domain in self.dataset_domain_list
        ]

    @property
    def document_source_dirs(self) -> list[Path]:
        """Every folder holding document source YAML."""
        return [path / "source" for path in self.document_dirs]

    @property
    def complaint_dirs(self) -> list[Path]:
        return [
            self.dataset_dir / domain / "complaints"
            for domain in self.dataset_domain_list
        ]

    @field_validator("database_url")
    @classmethod
    def _normalise_db_url(cls, v: str) -> str:
        """
        Make a pasted connection string safe to use as-is.

        Two things go wrong with a real Supabase string and both are silent:

        1. The scheme is ``postgresql://``, which selects the psycopg2 driver we
           do not install.  Upgraded to ``postgresql+psycopg://``.

        2. The password contains a character that is structural in a URL -
           ``@`` is the common one, ``#``, ``/``, ``?`` and ``:`` also occur.
           SQLAlchemy splits user-info at the *first* ``@``, so a password like
           ``secret@123`` silently yields the host ``123@aws-0-...`` and a
           DNS failure that looks nothing like the real cause.

           A host name can never contain ``@``, so the *last* ``@`` is always
           the true separator.  We re-split there and percent-encode the
           user-info, unless it already looks encoded (so running twice is
           harmless).
        """
        v = v.strip().strip('"').strip("'")

        for old in ("postgresql://", "postgres://"):
            if v.startswith(old):
                v = v.replace(old, "postgresql+psycopg://", 1)
                break

        if "://" not in v or "@" not in v:
            return v

        scheme, _, rest = v.partition("://")
        netloc, slash, path = rest.partition("/")
        userinfo, _, host = netloc.rpartition("@")  # rpartition -> last '@'
        if not userinfo:
            return v

        user, colon, password = userinfo.partition(":")
        already_encoded = bool(_PERCENT_ESCAPE.search(password))
        if not already_encoded:
            user = quote(user, safe="")
            password = quote(password, safe="")

        userinfo = f"{user}{colon}{password}"
        return f"{scheme}://{userinfo}@{host}{slash}{path}"

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgresql")

    @property
    def gemini_model_chain(self) -> list[str]:
        """The Gemini models to try, in order. Never empty."""
        chain = [m.strip() for m in self.gemini_model.split(",") if m.strip()]
        return chain or ["gemini-2.5-flash-lite"]

    @property
    def groq_model_chain(self) -> list[str]:
        chain = [m.strip() for m in self.groq_model.split(",") if m.strip()]
        return chain or ["openai/gpt-oss-120b"]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

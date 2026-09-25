"""Central configuration for the debt-collection call audit pipeline.

All values can be overridden via environment variables (see .env.example).
Nothing here contains secrets; API keys are read from the environment at
call time inside the individual stages.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # dotenv is optional
    pass


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass
class TranscriptionConfig:
    # scribe_v1 is broadly available; scribe_v2 adds detect_speaker_roles.
    model_id: str = field(default_factory=lambda: _env("STT_MODEL_ID", "scribe_v1"))
    diarize: bool = True
    # When True (scribe_v2 only) ElevenLabs returns speaker_id as 'agent'/'customer'.
    detect_speaker_roles: bool = field(
        default_factory=lambda: _env("STT_DETECT_ROLES", "false").lower() == "true"
    )
    # Optional BCP-47 language hint, e.g. "ita" for Italian. Empty => auto-detect.
    language_code: str = field(default_factory=lambda: _env("STT_LANGUAGE", ""))
    tag_audio_events: bool = True
    # Heuristic used when roles are NOT auto-detected: which speaker index is the agent.
    # The agent almost always speaks first on an outbound collection call.
    agent_is_first_speaker: bool = True


@dataclass
class MaskingConfig:
    # Phone masking: keep this many leading and trailing characters, collapse the
    # middle to a single mask char. Example: 00417612345 -> 004176*45 (prefix=6, suffix=2).
    phone_keep_prefix: int = field(default_factory=lambda: _env_int("PHONE_KEEP_PREFIX", 6))
    phone_keep_suffix: int = field(default_factory=lambda: _env_int("PHONE_KEEP_SUFFIX", 2))
    phone_mask_char: str = field(default_factory=lambda: _env("PHONE_MASK_CHAR", "*"))
    # Salt for the deterministic synthetic customer id. MUST be stable across runs
    # (so the same customer always maps to the same CUST-ANON id) and secret
    # (so the mapping is not reversible without it). Set ANON_SALT in the environment.
    anon_salt: str = field(default_factory=lambda: _env("ANON_SALT", "change-me-in-production"))
    anon_id_length: int = field(default_factory=lambda: _env_int("ANON_ID_LENGTH", 4))
    anon_prefix: str = "CUST-ANON-"


@dataclass
class ExtractionConfig:
    model: str = field(default_factory=lambda: _env("ANTHROPIC_MODEL", "claude-sonnet-4-5"))
    max_tokens: int = 2000
    temperature: float = 0.0
    # KPI: which flags are mandatory for a compliant call and the pass threshold.
    mandatory_flags: tuple = (
        "presentation_of_agency",
        "presentation_of_company",
        "name_ask",
        "date_birth_ask",
    )
    kpi_pass_threshold: float = field(default_factory=lambda: _env_float("KPI_PASS_THRESHOLD", 1.0))


@dataclass
class PipelineConfig:
    transcription: TranscriptionConfig = field(default_factory=TranscriptionConfig)
    masking: MaskingConfig = field(default_factory=MaskingConfig)
    extraction: ExtractionConfig = field(default_factory=ExtractionConfig)
    # Column that ties an audio file to a row in the customer database.
    manifest_audio_col: str = "audio_file"
    manifest_customer_col: str = "customer_id"
    db_customer_col: str = "customer_id"
    db_phone_col: str = "phone"
    db_name_col: str = "full_name"      # used only to redact the name from transcripts
    db_dob_col: str = "date_of_birth"   # used only to redact the DOB from transcripts

    @property
    def elevenlabs_api_key(self) -> Optional[str]:
        return os.environ.get("ELEVENLABS_API_KEY")

    @property
    def anthropic_api_key(self) -> Optional[str]:
        return os.environ.get("ANTHROPIC_API_KEY")

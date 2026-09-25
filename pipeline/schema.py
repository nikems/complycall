"""Typed records that flow through the pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

# YES/NO is represented as a plain string so it lands cleanly in Excel/CSV.
YesNo = str  # "YES" | "NO" | "N/A"


@dataclass
class TranscriptTurn:
    speaker: str          # "Agent" | "Customer"
    text: str
    start: float          # seconds
    end: float            # seconds


@dataclass
class Transcript:
    audio_file: str
    language: str
    duration_sec: float
    turns: List[TranscriptTurn] = field(default_factory=list)

    def as_dialogue(self) -> str:
        """Render as a labelled dialogue for the extraction LLM."""
        return "\n".join(f"{t.speaker}: {t.text}".strip() for t in self.turns)


@dataclass
class ComplianceFlags:
    """The audit variables extracted from the dialogue.

    Each YES/NO flag is paired with a short evidence quote for auditability.
    """
    presentation_of_agency: YesNo = "NO"
    presentation_of_company: YesNo = "NO"
    name_ask: YesNo = "NO"
    date_birth_ask: YesNo = "NO"
    client_answer: YesNo = "NO"
    is_family_member: YesNo = "NO"
    refuses_identity: YesNo = "NO"
    satisfaction: str = "Neutral"          # Positive | Neutral | Negative
    satisfaction_score: Optional[int] = None  # 1..5, optional
    evidence: Dict[str, str] = field(default_factory=dict)


@dataclass
class AuditRecord:
    """One row of the final audit report (one call)."""
    audio_file: str
    customer_id_original: str
    customer_id_anon: str
    masked_number: str
    # 8 extracted compliance variables + satisfaction
    presentation_of_agency: YesNo
    presentation_of_company: YesNo
    name_ask: YesNo
    date_birth_ask: YesNo
    client_answer: YesNo
    is_family_member: YesNo
    refuses_identity: YesNo
    satisfaction: str
    satisfaction_score: Optional[int]
    # derived KPI
    kpi_score: float          # 0..1 fraction of mandatory steps completed
    kpi_result: str           # PASS | FAIL
    # provenance
    language: str = ""
    duration_sec: float = 0.0
    transcript_path: str = ""
    processed_at: str = ""
    evidence: Dict[str, str] = field(default_factory=dict)

    def to_row(self) -> dict:
        d = asdict(self)
        d.pop("evidence", None)
        return d

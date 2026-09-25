"""Shared helpers used by both the CLI (run.py) and the web app."""
from __future__ import annotations

import datetime as dt
from typing import Callable, Optional

from .config import PipelineConfig
from . import masking, extraction
from .schema import AuditRecord


def make_extractor(cfg: PipelineConfig) -> Callable[[str], dict]:
    """Return the best extractor available: Anthropic if a key is set, else heuristic."""
    if cfg.anthropic_api_key:
        return extraction.AnthropicExtractor(cfg.extraction, cfg.anthropic_api_key)
    return extraction.HeuristicExtractor()


def extractor_kind(cfg: PipelineConfig) -> str:
    return "Claude (Anthropic)" if cfg.anthropic_api_key else "heuristic (no-API)"


def record_from_dialogue(audio_name: str, customer_id: str, full_name: str,
                         phone: str, dialogue_raw: str, cfg: PipelineConfig,
                         extractor: Callable[[str], dict],
                         language: str = "", duration: float = 0.0) -> AuditRecord:
    """Mask -> extract -> KPI -> AuditRecord for one already-transcribed call."""
    masked_number = masking.mask_phone(phone, cfg.masking)
    anon_id = masking.synthetic_customer_id(customer_id, cfg.masking)
    dialogue_safe = masking.redact_transcript(dialogue_raw, full_name)

    flags = extraction.extract(dialogue_safe, extractor)
    kpi_score, kpi_result = extraction.compute_kpi(flags, cfg.extraction)

    return AuditRecord(
        audio_file=audio_name,
        customer_id_original=customer_id,
        customer_id_anon=anon_id,
        masked_number=masked_number,
        presentation_of_agency=flags.presentation_of_agency,
        presentation_of_company=flags.presentation_of_company,
        name_ask=flags.name_ask,
        date_birth_ask=flags.date_birth_ask,
        client_answer=flags.client_answer,
        is_family_member=flags.is_family_member,
        refuses_identity=flags.refuses_identity,
        satisfaction=flags.satisfaction,
        satisfaction_score=flags.satisfaction_score,
        kpi_score=kpi_score,
        kpi_result=kpi_result,
        language=language,
        duration_sec=duration,
        transcript_path="",
        processed_at=dt.datetime.now().isoformat(timespec="seconds"),
        evidence=flags.evidence,
    )

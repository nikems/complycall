"""Stage 2 — privacy masking.

Two distinct jobs:
  1. mask_phone()          : format a phone number from the customer DB as 004176*98
  2. synthetic_customer_id : deterministic, non-reversible CUST-ANON-XXXX
  3. redact_transcript()   : strip raw phone numbers, full DOB, fiscal codes,
                             IBANs, emails and the known customer name from the
                             transcript text BEFORE it is sent to the extractor.

Redacting *values* never removes the *questions*: the phrase "what is your date
of birth?" is preserved, so date_birth_ask can still be detected downstream.
"""
from __future__ import annotations

import hmac
import hashlib
import re
from typing import Optional

from .config import MaskingConfig

# ---------------------------------------------------------------------------
# Phone masking
# ---------------------------------------------------------------------------

def mask_phone(raw: str, cfg: MaskingConfig) -> str:
    """Keep leading/trailing digits, collapse the middle to a single mask char.

    >>> from .config import MaskingConfig
    >>> mask_phone("0041761234598", MaskingConfig(phone_keep_prefix=6, phone_keep_suffix=2))
    '004176*98'
    """
    if raw is None:
        return ""
    digits = re.sub(r"\D", "", str(raw))
    p, s = cfg.phone_keep_prefix, cfg.phone_keep_suffix
    if len(digits) <= p + s:
        # too short to mask meaningfully — mask everything but the last suffix
        if len(digits) <= s:
            return cfg.phone_mask_char * len(digits)
        return cfg.phone_mask_char + digits[-s:]
    return f"{digits[:p]}{cfg.phone_mask_char}{digits[-s:]}"


# ---------------------------------------------------------------------------
# Deterministic synthetic customer id
# ---------------------------------------------------------------------------

def synthetic_customer_id(original_id: str, cfg: MaskingConfig) -> str:
    """Deterministic, salted, non-reversible id: CUST-ANON-XXXX.

    Same original id + same salt => same anon id (stable joins across runs).
    Without the salt the mapping cannot be reproduced.
    """
    mac = hmac.new(cfg.anon_salt.encode(), str(original_id).encode(), hashlib.sha256)
    token = mac.hexdigest().upper()[: cfg.anon_id_length]
    return f"{cfg.anon_prefix}{token}"


# ---------------------------------------------------------------------------
# Transcript PII redaction
# ---------------------------------------------------------------------------

# Italian codice fiscale: 6 letters, 2 digits, 1 letter, 2 digits, 1 letter, 3 digits, 1 letter
_CF_RE = re.compile(r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b", re.IGNORECASE)
# IBAN: 2 country letters, 2 check digits, up to 30 alphanumerics
_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
# Phone-like: optional +, then 7+ digits possibly separated by spaces/dashes/dots/parens
_PHONE_RE = re.compile(r"(?<!\w)(\+?\d[\d\s().\-]{6,}\d)(?!\w)")

_MONTHS = (
    r"gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|"
    r"ottobre|novembre|dicembre|"
    r"january|february|march|april|may|june|july|august|september|october|"
    r"november|december"
)
# Numeric dates: 12/03/1980, 12-03-1980, 12.03.1980
_DATE_NUM_RE = re.compile(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})\b")
# Spoken dates: "12 marzo 1980" / "March 12, 1980"
_DATE_WORD_RE = re.compile(
    rf"\b(\d{{1,2}}\s+(?:{_MONTHS})\s+\d{{4}}|(?:{_MONTHS})\s+\d{{1,2}},?\s+\d{{4}})\b",
    re.IGNORECASE,
)


def _redact_name(text: str, full_name: Optional[str]) -> str:
    if not full_name:
        return text
    for token in str(full_name).split():
        if len(token) < 2:
            continue
        text = re.sub(rf"\b{re.escape(token)}\b", "[NAME]", text, flags=re.IGNORECASE)
    return text


def redact_transcript(text: str, full_name: Optional[str] = None) -> str:
    """Return the transcript with PII values replaced by typed placeholders."""
    text = _CF_RE.sub("[FISCAL_CODE]", text)
    text = _IBAN_RE.sub("[IBAN]", text)
    text = _EMAIL_RE.sub("[EMAIL]", text)
    text = _DATE_WORD_RE.sub("[DOB]", text)
    text = _DATE_NUM_RE.sub("[DOB]", text)
    text = _PHONE_RE.sub("[PHONE]", text)
    text = _redact_name(text, full_name)
    return text

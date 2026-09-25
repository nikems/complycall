"""Stage 3 — the extraction engine (compliance verifier).

Reads the labelled Agent/Customer dialogue and emits the audit variables as
strict YES/NO flags plus a satisfaction reading, each with a short evidence
quote. The LLM is called with Anthropic tool-use so the output is a validated
JSON object rather than free text.

The extractor is pluggable: `AnthropicExtractor` calls the API; any callable
`(dialogue:str) -> dict` can be substituted for testing/offline use.
"""
from __future__ import annotations

import json
from typing import Callable, Dict

from .config import ExtractionConfig
from .schema import ComplianceFlags

# ---------------------------------------------------------------------------
# Prompt + tool schema
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a compliance auditor for debt-collection phone calls.
You are given a transcript of a call, labelled by speaker (Agent = the collection
operator, Customer = the contacted person). Personal data has already been
redacted and replaced with tokens like [NAME], [DOB], [PHONE], [FISCAL_CODE].
Redaction hides the VALUES, not the QUESTIONS: if the agent asks "what is your
date of birth?" you must still record that the question was asked.

Judge ONLY what the transcript supports. Do not infer beyond the text. For every
flag, YES means the transcript clearly shows it happened; otherwise NO. Provide a
short verbatim evidence quote (or "" if none) for each flag."""

INSTRUCTIONS = """Analyse the dialogue and call the `record_audit` tool with:

- presentation_of_agency: did the agent state they are calling on behalf of a
  debt-collection agency? (identifies the agency)
- presentation_of_company: did the agent name the creditor company / the company
  the debt is owed to?
- name_ask: did the agent ask the customer to state or confirm their name?
- date_birth_ask: did the agent ask for the customer's date of birth (identity check)?
- client_answer: did the contacted person confirm they are the customer/debtor?
- is_family_member: is the person reached a family member / third party rather
  than the debtor themselves?
- refuses_identity: did the person refuse to provide or confirm their identity?
- satisfaction: overall tone of the customer at the end of the call
  (Positive / Neutral / Negative).
- satisfaction_score: integer 1 (very negative) to 5 (very positive).
- evidence: an object mapping each flag name above to a short verbatim quote."""

_FLAG_NAMES = [
    "presentation_of_agency", "presentation_of_company", "name_ask",
    "date_birth_ask", "client_answer", "is_family_member", "refuses_identity",
]

RECORD_TOOL = {
    "name": "record_audit",
    "description": "Record the compliance audit variables for this call.",
    "input_schema": {
        "type": "object",
        "properties": {
            **{name: {"type": "string", "enum": ["YES", "NO"]} for name in _FLAG_NAMES},
            "satisfaction": {"type": "string", "enum": ["Positive", "Neutral", "Negative"]},
            "satisfaction_score": {"type": "integer", "minimum": 1, "maximum": 5},
            "evidence": {
                "type": "object",
                "additionalProperties": {"type": "string"},
                "description": "flag_name -> verbatim evidence quote",
            },
        },
        "required": _FLAG_NAMES + ["satisfaction", "satisfaction_score"],
    },
}


def build_messages(dialogue: str):
    return [{
        "role": "user",
        "content": f"{INSTRUCTIONS}\n\n=== TRANSCRIPT ===\n{dialogue}\n=== END ===",
    }]


# ---------------------------------------------------------------------------
# Extractors
# ---------------------------------------------------------------------------

class AnthropicExtractor:
    def __init__(self, cfg: ExtractionConfig, api_key: str):
        import anthropic

        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set.")
        self.cfg = cfg
        self.client = anthropic.Anthropic(api_key=api_key)

    def __call__(self, dialogue: str) -> Dict:
        resp = self.client.messages.create(
            model=self.cfg.model,
            max_tokens=self.cfg.max_tokens,
            temperature=self.cfg.temperature,
            system=SYSTEM_PROMPT,
            tools=[RECORD_TOOL],
            tool_choice={"type": "tool", "name": "record_audit"},
            messages=build_messages(dialogue),
        )
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use":
                return block.input
        raise RuntimeError("Model did not return a tool_use block.")


class HeuristicExtractor:
    """No-API fallback: keyword rules over the labelled dialogue.

    Used when no ANTHROPIC_API_KEY is available (offline demo / quick trials).
    Clearly weaker than the LLM extractor — it looks for Italian/English cue
    phrases. Good enough to demonstrate the flow; not for production auditing.
    """

    AGENCY = ["recupero crediti", "agenzia di recupero", "societa di recupero",
              "collection agency", "debt collection", "recupero del credito"]
    COMPANY = ["per conto di", "on behalf of", "creditore", "azienda cliente"]
    NAME_ASK = ["il suo nome", "parlo con", "conferma il", "e lei il", "e lei la",
                "signor", "signora", "your name", "am i speaking", "confirm your name", "c'e "]
    DOB_ASK = ["data di nascita", "quando e nato", "quando e nata", "date of birth",
               "born", "nato il"]
    CLIENT_YES = ["si sono io", "sono io", "si, sono io", "esatto sono io",
                  "yes it's me", "speaking", "yes that's me"]
    FAMILY = ["sorella", "fratello", "moglie", "marito", "figlio", "figlia",
              "madre", "padre", "familiare", "sono la ", "sono il ", "parente",
              "my sister", "my brother", "my wife", "my husband", "relative"]
    REFUSE = ["non le do", "non fornisco", "non vi do", "non so chi siete",
              "non so chi", "rifiuto", "non do nessun dato", "no dato",
              "i won't give", "i refuse", "not giving you", "who are you"]
    POS = ["grazie", "la ringrazio", "gentile", "va bene", "perfetto", "thank you", "great"]
    NEG = ["no", "non", "arrabbiat", "basta", "non voglio", "smettetela", "angry", "stop calling"]

    def _lines(self, dialogue: str):
        agent, cust = [], []
        for ln in dialogue.splitlines():
            low = ln.lower()
            if low.startswith("agent:"):
                agent.append(low[len("agent:"):])
            elif low.startswith("customer:"):
                cust.append(low[len("customer:"):])
        return " ".join(agent), " ".join(cust)

    @staticmethod
    def _has(text, cues):
        return "YES" if any(c in text for c in cues) else "NO"

    def __call__(self, dialogue: str) -> Dict:
        agent, cust = self._lines(dialogue)
        satis = "Neutral"; score = 3
        if any(c in cust for c in self.POS):
            satis, score = "Positive", 4
        refuses = self._has(cust, self.REFUSE)
        family = self._has(cust, self.FAMILY)
        if refuses == "YES" or family == "YES":
            satis, score = "Negative", 2
        return {
            "presentation_of_agency": self._has(agent, self.AGENCY),
            "presentation_of_company": self._has(agent, self.COMPANY),
            "name_ask": self._has(agent, self.NAME_ASK),
            "date_birth_ask": self._has(agent, self.DOB_ASK),
            "client_answer": self._has(cust, self.CLIENT_YES),
            "is_family_member": family,
            "refuses_identity": refuses,
            "satisfaction": satis,
            "satisfaction_score": score,
            "evidence": {"note": "heuristic (no-API) extraction — cue-phrase matching"},
        }


def flags_from_dict(raw: Dict) -> ComplianceFlags:
    """Validate/normalise a raw extractor dict into ComplianceFlags."""
    def yn(v):
        return "YES" if str(v).strip().upper() == "YES" else "NO"

    return ComplianceFlags(
        presentation_of_agency=yn(raw.get("presentation_of_agency")),
        presentation_of_company=yn(raw.get("presentation_of_company")),
        name_ask=yn(raw.get("name_ask")),
        date_birth_ask=yn(raw.get("date_birth_ask")),
        client_answer=yn(raw.get("client_answer")),
        is_family_member=yn(raw.get("is_family_member")),
        refuses_identity=yn(raw.get("refuses_identity")),
        satisfaction=raw.get("satisfaction", "Neutral"),
        satisfaction_score=raw.get("satisfaction_score"),
        evidence=raw.get("evidence", {}) or {},
    )


def extract(dialogue: str, extractor: Callable[[str], Dict]) -> ComplianceFlags:
    return flags_from_dict(extractor(dialogue))


# ---------------------------------------------------------------------------
# KPI (computed deterministically, not by the LLM)
# ---------------------------------------------------------------------------

def compute_kpi(flags: ComplianceFlags, cfg: ExtractionConfig):
    """Return (score in 0..1, 'PASS'/'FAIL') from the mandatory compliance steps."""
    done = sum(1 for f in cfg.mandatory_flags if getattr(flags, f) == "YES")
    total = len(cfg.mandatory_flags)
    score = done / total if total else 0.0
    result = "PASS" if score >= cfg.kpi_pass_threshold else "FAIL"
    return round(score, 3), result

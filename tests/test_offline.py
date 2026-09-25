"""Offline tests — no ElevenLabs / Anthropic calls.

Run:  python -m tests.test_offline    (from the project root)
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.config import PipelineConfig, MaskingConfig, TranscriptionConfig, ExtractionConfig
from pipeline import masking, transcribe, extraction, report
from pipeline.schema import AuditRecord


def test_phone_masking():
    cfg = MaskingConfig(phone_keep_prefix=6, phone_keep_suffix=2)
    assert masking.mask_phone("0041761234598", cfg) == "004176*98"
    assert masking.mask_phone("0041 76 123 45 98", cfg) == "004176*98"  # separators stripped
    assert masking.mask_phone("+41 76 123 45 98", cfg) == "417612*98"   # no 0041 prefix here
    assert masking.mask_phone("123", cfg).endswith("23")
    print("  phone masking OK")


def test_synthetic_id_deterministic():
    cfg = MaskingConfig(anon_salt="fixed-salt", anon_id_length=4)
    a = masking.synthetic_customer_id("10001", cfg)
    b = masking.synthetic_customer_id("10001", cfg)
    c = masking.synthetic_customer_id("10002", cfg)
    assert a == b, "same id + salt must be stable"
    assert a != c, "different ids must differ"
    assert a.startswith("CUST-ANON-") and len(a) == len("CUST-ANON-") + 4
    # salt actually changes the mapping
    other = masking.synthetic_customer_id("10001", MaskingConfig(anon_salt="other"))
    assert other != a
    print(f"  synthetic id OK ({a})")


def test_redaction():
    text = ("Agent: Buongiorno, la sua data di nascita? "
            "Customer: 12 marzo 1980, codice fiscale RSSMRA80C12F205X, "
            "IBAN IT60X0542811101000000123456, telefono 0041761234598, "
            "email mario.rossi@example.com.")
    out = masking.redact_transcript(text, full_name="Mario Rossi")
    assert "1980" not in out and "[DOB]" in out
    assert "RSSMRA80C12F205X" not in out and "[FISCAL_CODE]" in out
    assert "IT60X0542811101000000123456" not in out and "[IBAN]" in out
    assert "0041761234598" not in out and "[PHONE]" in out
    assert "@example.com" not in out and "[EMAIL]" in out
    assert "Mario" not in out and "Rossi" not in out
    # the QUESTION survives redaction of the value
    assert "data di nascita" in out
    print("  redaction OK")


def test_turn_grouping():
    # simulate diarized words: speaker_0 then speaker_1
    def w(text, spk, s, e, typ="word"):
        return SimpleNamespace(text=text, speaker_id=spk, start=s, end=e, type=typ)
    words = [
        w("Buongiorno", "speaker_0", 0.0, 0.5), w(" ", "speaker_0", 0.5, 0.5, "spacing"),
        w("sono", "speaker_0", 0.5, 0.8), w(" ", "speaker_0", 0.8, 0.8, "spacing"),
        w("Anna", "speaker_0", 0.8, 1.2),
        w("Salve", "speaker_1", 1.5, 2.0), w(" ", "speaker_1", 2.0, 2.0, "spacing"),
        w("chi", "speaker_1", 2.0, 2.3),
    ]
    tr = transcribe.transcript_from_words("x.mp3", words, TranscriptionConfig())
    assert len(tr.turns) == 2
    assert tr.turns[0].speaker == "Agent" and "Buongiorno" in tr.turns[0].text
    assert tr.turns[1].speaker == "Customer" and "Salve" in tr.turns[1].text
    print(f"  turn grouping OK ({len(tr.turns)} turns)")


def test_extraction_parse_and_kpi():
    raw = {
        "presentation_of_agency": "YES", "presentation_of_company": "yes",
        "name_ask": "YES", "date_birth_ask": "NO", "client_answer": "YES",
        "is_family_member": "NO", "refuses_identity": "no",
        "satisfaction": "Positive", "satisfaction_score": 4,
        "evidence": {"name_ask": "Mi conferma il suo nome?"},
    }
    flags = extraction.flags_from_dict(raw)
    assert flags.presentation_of_company == "YES"   # normalised
    assert flags.refuses_identity == "NO"
    score, result = extraction.compute_kpi(flags, ExtractionConfig())
    assert abs(score - 0.75) < 1e-9   # 3 of 4 mandatory steps
    assert result == "FAIL"           # threshold defaults to 1.0
    print(f"  extraction+KPI OK (score={score}, {result})")


def test_report(tmp="./_test_out"):
    os.makedirs(tmp, exist_ok=True)
    recs = [
        AuditRecord(
            audio_file="10001_call.mp3", customer_id_original="10001",
            customer_id_anon="CUST-ANON-AB12", masked_number="004176*98",
            presentation_of_agency="YES", presentation_of_company="YES",
            name_ask="YES", date_birth_ask="YES", client_answer="YES",
            is_family_member="NO", refuses_identity="NO",
            satisfaction="Positive", satisfaction_score=4,
            kpi_score=1.0, kpi_result="PASS", language="ita", duration_sec=63.2,
            processed_at="2026-01-01T00:00:00",
            evidence={"name_ask": "Mi conferma il suo nome?"},
        ),
    ]
    xlsx, csv = f"{tmp}/Audit_Report.xlsx", f"{tmp}/Audit_Report.csv"
    report.write_reports(recs, xlsx, csv)
    assert os.path.getsize(xlsx) > 0 and os.path.getsize(csv) > 0
    print(f"  report OK ({os.path.getsize(xlsx)} bytes xlsx)")


if __name__ == "__main__":
    for fn in [test_phone_masking, test_synthetic_id_deterministic, test_redaction,
               test_turn_grouping, test_extraction_parse_and_kpi, test_report]:
        print(f"- {fn.__name__}")
        fn()
    print("\nALL OFFLINE TESTS PASSED")

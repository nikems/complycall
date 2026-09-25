# Collection Call Audit Pipeline

Turns collection-call recordings into a compliance audit report.

The workflow below is one example of what the pipeline can do — it is a starting point that
can be extended further.
`
<img width="1600" height="173" alt="wf" src="https://github.com/user-attachments/assets/1f938ffc-d75b-4299-a9ad-59c3cd092a24" />



## The idea

The core idea of the project is a **Data Minimizer**: an AI assistant built around a
privacy-first workflow. The tool that inspired it is **ElevenLabs**, which can be configured
to comply with GDPR rules.

In our workflow:
1. **ElevenLabs** converts the call audio into text (and separates who is speaking).
2. We then apply a **data minimization** step in **Python**, using regular expressions (regex),
   to remove the sensitive data.
3. Finally an **agent** — Claude, in this case — reads the minimized text and extracts the
   variables of interest, i.e. selects the information we need.

<img width="1600" height="173" alt="wf" src="https://github.com/user-attachments/assets/1f938ffc-d75b-4299-a9ad-59c3cd092a24" />

## Workflow

1. **Transcribe** (`pipeline/transcribe.py`) — ElevenLabs Scribe with diarization,
   producing `Agent/Operator:` / `Customer:` turns. Uses `detect_speaker_roles` when
   available (scribe_v2); otherwise maps the first speaker to Agent/Operator.
2. **Mask** (`pipeline/masking.py`) — masks the phone from the customer DB to
   `004176*98`, mints a deterministic, non-reversible `CUST-ANON-XXXX` id, and
   redacts phone / full DOB / fiscal code / IBAN / email / customer name from the
   transcript **before** it reaches the model. This step is pure Python — no AI.
3. **Extract** (`pipeline/extraction.py`) — an Anthropic tool-use call that returns
   strict `YES`/`NO` compliance flags + satisfaction, each with an evidence quote.
   The **KPI is computed deterministically** from the mandatory steps (not by the LLM).
   A no-API heuristic mode is also available for the demo (no key needed).
4. **Report** (`pipeline/report.py`) — one row per call: `Audit_Report.xlsx`
   (colour-coded YES/NO and PASS/FAIL, plus an Evidence sheet) and `Audit_Report.csv`.

## Examples of the audit variables

More variables can be added. These are some binary variables that help check compliance
and determine the KPIs.

| # | Column | Source | Meaning |
|---|--------|--------|---------|
| — | ID Number Customer (original) | DB | real customer id (kept for internal join) |
| — | Number (masked) | DB + Stage 2 | phone masked as `004176*98` |
| — | Customer ID (anon) | Stage 2 | deterministic `CUST-ANON-XXXX` |
| 1 | Presentation of Agency | transcript | agent identified the collection agency |
| 2 | Presentation of Company | transcript | agent named the creditor company |
| 3 | Name Ask | transcript | agent asked to confirm the customer's name |
| 4 | Date of Birth Ask | transcript | agent asked DOB for identity verification |
| 5 | Client Answer | transcript | person confirmed they are the debtor |
| 6 | Is Family Member | transcript | person reached is a third party / relative |
| 7 | Refuses to Provide Identity | transcript | person refused to identify themselves |
| 8 | Satisfaction | transcript | Positive / Neutral / Negative (+ 1–5 score) |
| 9 | KPI | computed | fraction of mandatory steps done → PASS/FAIL |

> **Note on "10 audit variables":** the original list had 11 items, but two of them
> (original id, masked number) come from the customer database, not the transcript.
> The pipeline produces all of them; the 9 above are the transcript-derived + computed
> audit variables, plus the 2 DB-joined fields.

## Install

```bash
pip install -r requirements.txt        # elevenlabs, anthropic, pandas, xlsxwriter, flask, ...
cp .env.example .env                   # then fill in the keys (optional — demo runs without them)
```

## Run the web app

```bash
cd webapp && python app.py             # then open the address it prints (e.g. http://127.0.0.1:8000)
```

The page has three ways to run:

- **Try the live demo** — one click, **no API keys**. Runs two built-in sample calls and
  shows a PASS/FAIL report you can download. Ideal for a pitch.
- **Upload transcripts (.txt)** — dialogues with `Agent:` / `Customer:` lines. No ElevenLabs
  needed; the file name starts with the customer id (`10001_call.txt`).
- **Upload audio (.mp3/.wav)** — transcribed + speaker-split automatically (needs an
  ElevenLabs key, entered in the form or via the environment).

## Layout

```
call_audit_pipeline/
├── run.py                     # CLI orchestrator
├── pipeline/
│   ├── config.py              # all tunables (env-overridable)
│   ├── schema.py              # Transcript / ComplianceFlags / AuditRecord
│   ├── transcribe.py          # Stage 1 — ElevenLabs Scribe + diarization
│   ├── masking.py             # Stage 2 — phone mask, anon id, PII redaction (Python, no AI)
│   ├── extraction.py          # Stage 3 — Anthropic tool-use + KPI
│   └── report.py              # Stage 4 — xlsx/csv writer
├── webapp/                    # Flask web app (pages, demo, upload, download)
├── sample_data/               # example customer DB + manifest
├── sample_output/             # example Audit_Report.xlsx / .csv (2 calls)
├── tests/test_offline.py
├── requirements.txt
└── render.yaml                # deployment config (see Render)
```

---

*Screening tool with human review — it flags calls for a person to confirm. Not legal advice;
confirm GDPR and sector-specific rules with your compliance advisor.*


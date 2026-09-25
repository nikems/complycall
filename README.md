# Collection Call Audit Pipeline

Turns collection call recordings into a compliance audit report. The scheme workflow that was used is the following -i's na example on what is posible to do

`
<img width="1600" height="173" alt="wf" src="https://github.com/user-attachments/assets/1f938ffc-d75b-4299-a9ad-59c3cd092a24" />


1. **Transcribe** (`pipeline/transcribe.py`) — ElevenLabs Scribe with diarization,
   producing `Agent/Operator:` / `Customer:` turns. Uses `detect_speaker_roles` when
   available (scribe_v2); otherwise maps the first speaker to Agent/Operator.
2. **Mask** (`pipeline/masking.py`) — masks the phone from the customer DB to
   `004176*98`, mints a deterministic, non-reversible `CUST-ANON-XXXX` id, and
   redacts phone / full DOB / fiscal code / IBAN / email / customer name from the
   transcript **before** it reaches the model.
3. **Extract** (`pipeline/extraction.py`) — an Anthropic tool-use call that returns
   strict `YES`/`NO` compliance flags + satisfaction, each with an evidence quote.
   The **KPI is computed deterministically** from the mandatory steps (not by the LLM).
4. **Report** (`pipeline/report.py`) — one row per call, `Audit_Report.xlsx`
   (colour-coded YES/NO and PASS/FAIL, plus an Evidence sheet) and `Audit_Report.csv`.

## Examples of the audit variables
It's possible to create more varibles, we create some Binary Variables that could pemrit to check the compliance and help to dtermine the KPIs.

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

> **Note on "10 audit variables":** your list had 11 items, but two of them
> (original id, masked number) come from the customer database, not the
> transcript. The pipeline produces all of them; the 9 above are the
> transcript-derived + computed audit variables, plus the 2 DB-joined fields.



## Install

```bash
pip install -r requirements.txt        # elevenlabs, anthropic, pandas, xlsxwriter, ...
cp .env.example .env                   # then fill in the keys
```

## Configure (`.env`)

| Variable | Purpose |
|----------|---------|
| `ELEVENLABS_API_KEY` | Stage 1 transcription |
| `ANTHROPIC_API_KEY` | Stage 3 extraction |
| `ANTHROPIC_MODEL` | a model your key can access (default `claude-sonnet-4-5`) |
| `ANON_SALT` | **stable, secret** salt for `CUST-ANON` ids — keep constant across runs |
| `STT_MODEL_ID` / `STT_DETECT_ROLES` | `scribe_v2` + `true` to get agent/customer roles directly |
| `STT_LANGUAGE` | e.g. `ita`; empty = auto-detect |
| `KPI_PASS_THRESHOLD` | fraction of mandatory steps to PASS (default `1.0`) |

## Run

```bash
python run.py \
  --audio-dir ./calls \
  --customers ./sample_data/customers.csv \
  --manifest  ./sample_data/manifest.csv \   # optional; else id inferred from filename
  --out-dir   ./out
```

- **Customer DB** (`sample_data/customers.csv`): needs `customer_id`, `phone`;
  optional `full_name`, `date_of_birth` are used only to redact those values from
  transcripts.
- **Manifest** (optional): maps `audio_file → customer_id`. Without it, the id is
  read from the filename stem (`10001_call.mp3 → 10001`).
- **Output**: `out/Audit_Report.xlsx`, `out/Audit_Report.csv`, and one redacted
  transcript per call under `out/transcripts/<anon-id>.txt`.

## Web app (open a page, run ComplyCall from the browser)

```bash
pip install -r requirements.txt          # includes flask
cd webapp && python app.py               # then open http://localhost:8000
```

The page has three ways to run:

- **Try the live demo** — one click, **no API keys**. Runs two built-in sample
  calls and shows a PASS/FAIL report you can download. Ideal for a pitch.
- **Upload transcripts (.txt)** — dialogues with `Agent:` / `Customer:` lines.
  No ElevenLabs needed; the file name starts with the customer id
  (`10001_call.txt`).
- **Upload audio (.mp3/.wav)** — transcribed + speaker-split automatically
  (needs an ElevenLabs key, entered in the form or via the environment).

Extraction uses **Claude** when an Anthropic key is present, otherwise a built-in
**no-API heuristic** (clearly labelled on the results page). Keys typed in the
form are used only for that run and are not stored. Reports for each run are
written under `webapp/runs/<id>/`.

## Test

```bash
python tests/test_offline.py     # masking, redaction, turn-grouping, KPI, report — no API keys
```

## Privacy

- Raw PII (phone, full DOB, fiscal code, IBAN, email, customer name) is stripped
  from the transcript **before** any text is sent to the extraction model.
- Redaction removes *values*, never *questions* — "what is your date of birth?"
  survives so `Date of Birth Ask` is still detectable.
- The only PII that leaves the DB is the masked phone (`004176*98`); the original
  customer id is kept in the report for your internal join but is paired with a
  non-reversible `CUST-ANON` id you can share externally.
- Set a long, secret `ANON_SALT` and keep it constant so anon ids stay stable and
  the original↔anon mapping cannot be reproduced without the salt.

## Layout

```
call_audit_pipeline/
├── run.py                     # CLI orchestrator
├── pipeline/
│   ├── config.py              # all tunables (env-overridable)
│   ├── schema.py              # Transcript / ComplianceFlags / AuditRecord
│   ├── transcribe.py          # Stage 1 — ElevenLabs Scribe + diarization
│   ├── masking.py             # Stage 2 — phone mask, anon id, PII redaction
│   ├── extraction.py          # Stage 3 — Anthropic tool-use + KPI
│   └── report.py              # Stage 4 — xlsx/csv writer
├── sample_data/               # example customer DB + manifest
├── sample_output/             # example Audit_Report.xlsx / .csv (2 calls)
├── tests/test_offline.py
├── requirements.txt
└── .env.example
```

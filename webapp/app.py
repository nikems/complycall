#!/usr/bin/env python3
"""ComplyCall web app — upload calls, run the audit, download the report.

Run:
    pip install -r ../requirements.txt flask
    python app.py            # then open http://localhost:8000

Works in three modes:
  * Demo            — one click, no API keys, uses two built-in sample calls.
  * Transcripts     — upload .txt dialogues (Agent:/Customer: lines); no ElevenLabs needed.
  * Audio           — upload .mp3/.wav; needs an ElevenLabs key (entered in the form or env).
The compliance extraction uses Claude if an Anthropic key is present, otherwise a
built-in no-API heuristic (clearly labelled).
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

from flask import (Flask, render_template, request, redirect, url_for,
                   send_from_directory, abort)
from werkzeug.utils import secure_filename

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pandas as pd
from pipeline.config import PipelineConfig
from pipeline import core, transcribe, report

APP_DIR = Path(__file__).resolve().parent
RUNS_DIR = APP_DIR / "runs"
RUNS_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200 MB uploads

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".flac", ".ogg"}

# ---- built-in demo dialogues (Italian debt-collection calls) ----
DEMO = [
    ("10001_call.mp3", "10001", "Mario Rossi", "0041761234598",
     "Agent: Buongiorno, parlo con il signor Mario Rossi? Sono Anna della societa di "
     "recupero crediti Credit Solutions, che chiama per conto di Vodafone Italia.\n"
     "Customer: Si, sono io.\n"
     "Agent: Per verificare la sua identita, mi puo confermare la sua data di nascita?\n"
     "Customer: Certo, 12 marzo 1980. Il mio codice fiscale e RSSMRA80C12F205X.\n"
     "Agent: Grazie. La contatto per una fattura non saldata di 240 euro.\n"
     "Customer: Va bene, la ringrazio per la chiarezza, provvedo subito al pagamento."),
    ("10002_call.mp3", "10002", "Giulia Bianchi", "00393391112233",
     "Agent: Buongiorno, sono Marco. C'e Giulia Bianchi? Devo parlarle.\n"
     "Customer: Sono la sorella, lei adesso non c'e. Chi parla? Di che azienda siete?\n"
     "Agent: E una questione personale. Mi puo lasciare un recapito, tipo 00393391112233?\n"
     "Customer: No, non le do nessun dato. Non so nemmeno chi siete.\n"
     "Agent: Va bene, richiamero piu tardi."),
]


def _cfg_from_form() -> PipelineConfig:
    cfg = PipelineConfig()
    el = request.form.get("elevenlabs_key", "").strip()
    an = request.form.get("anthropic_key", "").strip()
    lang = request.form.get("language", "").strip()
    if el:
        os.environ["ELEVENLABS_API_KEY"] = el
    if an:
        os.environ["ANTHROPIC_API_KEY"] = an
    if lang:
        cfg.transcription.language_code = lang
    return cfg


def _finish(records, cfg, mode_note):
    run_id = uuid.uuid4().hex[:12]
    rdir = RUNS_DIR / run_id
    rdir.mkdir(parents=True, exist_ok=True)
    report.write_reports(records, str(rdir / "Audit_Report.xlsx"), str(rdir / "Audit_Report.csv"))
    df = report.records_to_dataframe(records)
    n_pass = int((df["KPI Result"] == "PASS").sum())
    n_fail = int((df["KPI Result"] == "FAIL").sum())
    return render_template(
        "results.html", run_id=run_id, columns=list(df.columns),
        rows=df.to_dict("records"), n=len(df), n_pass=n_pass, n_fail=n_fail,
        engine=core.extractor_kind(cfg), mode_note=mode_note,
        yesno={"Presentation of Agency", "Presentation of Company", "Name Ask",
               "Date of Birth Ask", "Client Answer (identity confirmed)",
               "Is Family Member", "Refuses to Provide Identity"})


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/demo")
def demo():
    cfg = PipelineConfig()
    ext = core.make_extractor(cfg)
    records = [core.record_from_dialogue(a, cid, nm, ph, dlg, cfg, ext, language="ita")
               for (a, cid, nm, ph, dlg) in DEMO]
    return _finish(records, cfg, "Demo mode — two built-in sample calls.")


@app.route("/run", methods=["POST"])
def run():
    cfg = _cfg_from_form()
    ext = core.make_extractor(cfg)

    # customer database (optional)
    db = {}
    cust_file = request.files.get("customers")
    if cust_file and cust_file.filename:
        df = pd.read_csv(cust_file, dtype=str).fillna("")
        db = {str(r[cfg.db_customer_col]): r.to_dict() for _, r in df.iterrows()}

    def cust_info(cid):
        row = db.get(cid, {})
        return row.get(cfg.db_name_col, ""), row.get(cfg.db_phone_col, "")

    records, errors = [], []

    # transcripts (.txt) — dialogue used directly
    for f in request.files.getlist("transcripts"):
        if not f or not f.filename:
            continue
        cid = Path(secure_filename(f.filename)).stem.split("_")[0]
        name, phone = cust_info(cid)
        dialogue = f.read().decode("utf-8", errors="replace")
        records.append(core.record_from_dialogue(f.filename, cid, name, phone, dialogue, cfg, ext))

    # audio (.mp3/.wav) — transcribe first (needs ElevenLabs key)
    audio_files = [f for f in request.files.getlist("audio") if f and f.filename]
    if audio_files and not cfg.elevenlabs_api_key:
        errors.append("Audio uploaded but no ElevenLabs API key provided — skipped. "
                      "Add a key or upload .txt transcripts instead.")
    elif audio_files:
        tmp = RUNS_DIR / ("_tmp_" + uuid.uuid4().hex[:8])
        tmp.mkdir(parents=True, exist_ok=True)
        for f in audio_files:
            if Path(f.filename).suffix.lower() not in AUDIO_EXTS:
                continue
            p = tmp / secure_filename(f.filename)
            f.save(str(p))
            cid = Path(f.filename).stem.split("_")[0]
            name, phone = cust_info(cid)
            try:
                tr = transcribe.transcribe(str(p), cfg.transcription, cfg.elevenlabs_api_key)
                records.append(core.record_from_dialogue(
                    f.filename, cid, name, phone, tr.as_dialogue(),
                    cfg, ext, language=tr.language, duration=tr.duration_sec))
            except Exception as e:
                errors.append(f"{f.filename}: {e}")

    if not records:
        return render_template("index.html",
                               error="No results. " + (" ".join(errors) or
                               "Upload .txt transcripts or .mp3/.wav audio, then run."))
    note = "Processed uploads."
    if errors:
        note += "  Warnings: " + " | ".join(errors)
    return _finish(records, cfg, note)


@app.route("/download/<run_id>/<fmt>")
def download(run_id, fmt):
    if not run_id.isalnum() or fmt not in ("xlsx", "csv"):
        abort(404)
    rdir = RUNS_DIR / run_id
    fname = f"Audit_Report.{fmt}"
    if not (rdir / fname).exists():
        abort(404)
    return send_from_directory(str(rdir), fname, as_attachment=True)


if __name__ == "__main__":
    import socket, webbrowser, threading

    def _free_port(start):
        """Return the first free port at or after `start` (handles busy 5000/8000)."""
        p = start
        for _ in range(100):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(("127.0.0.1", p))
                    return p
                except OSError:
                    p += 1
        return start

    desired = int(os.environ.get("PORT", "8000"))
    port = _free_port(desired)
    url = f"http://127.0.0.1:{port}"
    print("\n" + "=" * 52)
    if port != desired:
        print(f"(port {desired} was busy — using {port} instead)")
    print(f"  ComplyCall is running.  Open this in your browser:")
    print(f"     {url}")
    print("  Your browser should open it automatically.")
    print("  To stop ComplyCall: press  Ctrl + C  here.")
    print("=" * 52 + "\n")
    # open the browser automatically once the server is up
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=port, debug=False)

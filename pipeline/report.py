"""Stage 4 — Excel / CSV report generator.

One row per call. The .xlsx has two sheets:
  * "Audit"    — the audit variables, with YES/NO and PASS/FAIL colour-coded.
  * "Evidence" — the verbatim quote supporting each flag, for manual review.
"""
from __future__ import annotations

from typing import List

import pandas as pd

from .schema import AuditRecord

# Order of columns in the report (maps the spec's variable list).
COLUMNS = [
    ("audio_file", "Audio File"),
    ("customer_id_original", "ID Number Customer (original)"),
    ("customer_id_anon", "Customer ID (anon)"),
    ("masked_number", "Number (masked)"),
    ("presentation_of_agency", "Presentation of Agency"),
    ("presentation_of_company", "Presentation of Company"),
    ("name_ask", "Name Ask"),
    ("date_birth_ask", "Date of Birth Ask"),
    ("client_answer", "Client Answer (identity confirmed)"),
    ("is_family_member", "Is Family Member"),
    ("refuses_identity", "Refuses to Provide Identity"),
    ("satisfaction", "Satisfaction"),
    ("satisfaction_score", "Satisfaction Score"),
    ("kpi_score", "KPI Score"),
    ("kpi_result", "KPI Result"),
    ("language", "Language"),
    ("duration_sec", "Duration (s)"),
    ("processed_at", "Processed At"),
]

_YESNO_COLS = {
    "Presentation of Agency", "Presentation of Company", "Name Ask",
    "Date of Birth Ask", "Client Answer (identity confirmed)",
    "Is Family Member", "Refuses to Provide Identity",
}


def records_to_dataframe(records: List[AuditRecord]) -> pd.DataFrame:
    rows = [r.to_row() for r in records]
    df = pd.DataFrame(rows)
    ordered = [src for src, _ in COLUMNS if src in df.columns]
    df = df[ordered].rename(columns={src: label for src, label in COLUMNS})
    return df


def _evidence_dataframe(records: List[AuditRecord]) -> pd.DataFrame:
    rows = []
    for r in records:
        row = {"Customer ID (anon)": r.customer_id_anon, "Audio File": r.audio_file}
        row.update(r.evidence or {})
        rows.append(row)
    return pd.DataFrame(rows)


def write_reports(records: List[AuditRecord], xlsx_path: str, csv_path: str) -> None:
    df = records_to_dataframe(records)
    df.to_csv(csv_path, index=False)

    with pd.ExcelWriter(xlsx_path, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name="Audit", index=False, startrow=1, header=False)
        wb, ws = writer.book, writer.sheets["Audit"]

        header_fmt = wb.add_format({"bold": True, "bg_color": "#1F3864", "font_color": "white",
                                    "border": 1, "align": "center", "valign": "vcenter"})
        yes_fmt = wb.add_format({"bg_color": "#C6EFCE", "font_color": "#006100", "align": "center"})
        no_fmt = wb.add_format({"bg_color": "#FFC7CE", "font_color": "#9C0006", "align": "center"})
        pass_fmt = wb.add_format({"bg_color": "#C6EFCE", "font_color": "#006100", "bold": True, "align": "center"})
        fail_fmt = wb.add_format({"bg_color": "#FFC7CE", "font_color": "#9C0006", "bold": True, "align": "center"})
        pct_fmt = wb.add_format({"num_format": "0%", "align": "center"})

        for col_idx, label in enumerate(df.columns):
            ws.write(0, col_idx, label, header_fmt)
            width = max(len(label) + 2, 14)
            ws.set_column(col_idx, col_idx, min(width, 40))

        nrows = len(df)
        for col_idx, label in enumerate(df.columns):
            first, last = 1, nrows
            col_letter = _xl_col(col_idx)
            rng = f"{col_letter}{first + 1}:{col_letter}{last + 1}"
            if label in _YESNO_COLS:
                ws.conditional_format(rng, {"type": "cell", "criteria": "==", "value": '"YES"', "format": yes_fmt})
                ws.conditional_format(rng, {"type": "cell", "criteria": "==", "value": '"NO"', "format": no_fmt})
            elif label == "KPI Result":
                ws.conditional_format(rng, {"type": "cell", "criteria": "==", "value": '"PASS"', "format": pass_fmt})
                ws.conditional_format(rng, {"type": "cell", "criteria": "==", "value": '"FAIL"', "format": fail_fmt})
            elif label == "KPI Score":
                ws.set_column(col_idx, col_idx, 12, pct_fmt)
        ws.freeze_panes(1, 4)
        ws.autofilter(0, 0, nrows, len(df.columns) - 1)

        ev = _evidence_dataframe(records)
        ev.to_excel(writer, sheet_name="Evidence", index=False)
        ews = writer.sheets["Evidence"]
        for col_idx, label in enumerate(ev.columns):
            ews.set_column(col_idx, col_idx, 28)


def _xl_col(idx: int) -> str:
    letters = ""
    idx += 1
    while idx:
        idx, rem = divmod(idx - 1, 26)
        letters = chr(65 + rem) + letters
    return letters

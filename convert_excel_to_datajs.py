"""
Convert CA Prostate Excel registry export to aggregated data.js for the static dashboard.

Usage:
  pip install pandas xlrd
  python convert_excel_to_datajs.py "รายงานสรุปข้อมูลผู้ป่วยมะเร็งต่อมลูกหมาก (CA Prostate) ปี 2564-2568.xls"

Output:
  data.js  (safe aggregate data only; no HN / CTB row-level export)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

PRIMARY_SHEET = "รายการ Cancer Primary "
PROCEDURE_SHEET = "หัตถการ"
RECURRENT_SHEET = "Cancer Recurrent"
RECURRENT_TREATMENT_SHEET = "treatment recurrent"


def clean_text(value):
    if pd.isna(value):
        return "ไม่ระบุ"
    text = str(value).strip()
    return text if text else "ไม่ระบุ"


def map_t_to_stage(value):
    """Map T value to broad CA stage group. T1->Stage 1, T2->Stage 2, etc."""
    if pd.isna(value):
        return "ไม่ระบุ"
    text = str(value).strip().upper().replace(" ", "")
    text = re.sub(r"^T", "", text)
    if text.startswith("1"):
        return "ระยะที่ 1"
    if text.startswith("2"):
        return "ระยะที่ 2"
    if text.startswith("3"):
        return "ระยะที่ 3"
    if text.startswith("4"):
        return "ระยะที่ 4"
    return "ไม่ระบุ"


def count_rows(df, col, top=None):
    out = (
        df[col]
        .map(clean_text)
        .value_counts(dropna=False)
        .reset_index()
        .rename(columns={"index": col, col: "count"})
    )
    out.columns = [col, "count"]
    if top:
        out = out.head(top)
    return out.to_dict("records")


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python convert_excel_to_datajs.py <excel-file.xls/xlsx>")

    excel_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2]) if len(sys.argv) >= 3 else Path("data.js")

    primary = pd.read_excel(excel_path, sheet_name=PRIMARY_SHEET)
    procedure = pd.read_excel(excel_path, sheet_name=PROCEDURE_SHEET)
    recurrent = pd.read_excel(excel_path, sheet_name=RECURRENT_SHEET)
    recurrent_treatment = pd.read_excel(excel_path, sheet_name=RECURRENT_TREATMENT_SHEET)

    primary["stage_group"] = primary["T"].map(map_t_to_stage)
    primary["age"] = pd.to_numeric(primary.get("อายุ ณ.วันที่วินิจฉัย"), errors="coerce")

    # one row per CTB + treatment to avoid duplicate procedure rows inflating patient treatment count
    treatment_patient = procedure[["CTB No.", "วิธีการรักษา"]].dropna(subset=["CTB No."]).drop_duplicates()
    stage_treatment = primary[["CTB No.", "stage_group"]].merge(treatment_patient, on="CTB No.", how="left")
    stage_treatment["วิธีการรักษา"] = stage_treatment["วิธีการรักษา"].map(clean_text)

    stage_treatment_summary = (
        stage_treatment.groupby(["stage_group", "วิธีการรักษา"], dropna=False)
        .size()
        .reset_index(name="count")
        .rename(columns={"stage_group": "stage", "วิธีการรักษา": "treatment"})
        .sort_values(["stage", "count"], ascending=[True, False])
    )

    # Stage -> treatment -> ICD9 sankey links
    proc_join = primary[["CTB No.", "stage_group"]].merge(procedure, on="CTB No.", how="inner")
    proc_join["วิธีการรักษา"] = proc_join["วิธีการรักษา"].map(clean_text)
    proc_join["ชื่อ ICD-9"] = proc_join["ชื่อ ICD-9"].map(clean_text)

    stage_to_treatment = (
        proc_join.groupby(["stage_group", "วิธีการรักษา"]).size().reset_index(name="value")
    )
    treatment_to_icd = (
        proc_join.groupby(["วิธีการรักษา", "ชื่อ ICD-9"]).size().reset_index(name="value")
        .sort_values("value", ascending=False)
        .head(40)
    )
    sankey_links = []
    for _, r in stage_to_treatment.iterrows():
        sankey_links.append({"source": r["stage_group"], "target": r["วิธีการรักษา"], "value": int(r["value"])})
    for _, r in treatment_to_icd.iterrows():
        sankey_links.append({"source": r["วิธีการรักษา"], "target": r["ชื่อ ICD-9"], "value": int(r["value"])})

    metastatic_cols = [c for c in ["Bone", "Brain", "Liver", "Lung", "Lymph", "Peritoneum"] if c in primary.columns]
    metastatic_summary = []
    for c in metastatic_cols:
        yes_count = primary[c].notna().sum()
        metastatic_summary.append({"site": c, "count": int(yes_count)})

    year_summary = (
        primary["ปี"].map(clean_text).value_counts().reset_index()
    )
    year_summary.columns = ["year", "count"]
    year_summary = year_summary.sort_values("year")

    data = {
        "kpis": {
            "patients": int(primary["CTB No."].nunique()),
            "procedurePatients": int(procedure["CTB No."].nunique()),
            "procedureRows": int(len(procedure)),
            "recurrentPatients": int(recurrent["CTB No."].nunique()),
            "recurrentTreatmentRows": int(len(recurrent_treatment)),
            "recurrentRate": round((recurrent["CTB No."].nunique() / primary["CTB No."].nunique()) * 100, 1),
            "avgAge": round(float(primary["age"].mean()), 1) if primary["age"].notna().any() else None,
        },
        "stageCounts": (
            primary["stage_group"].value_counts().reindex(["ระยะที่ 1", "ระยะที่ 2", "ระยะที่ 3", "ระยะที่ 4", "ไม่ระบุ"], fill_value=0)
            .reset_index().rename(columns={"index": "stage", "stage_group": "count"}).to_dict("records")
        ),
        "treatmentCounts": count_rows(treatment_patient, "วิธีการรักษา"),
        "procedureCounts": count_rows(procedure, "ชื่อ ICD-9", top=20),
        "stageTreatment": stage_treatment_summary.to_dict("records"),
        "sankeyLinks": sankey_links,
        "metastaticSummary": metastatic_summary,
        "yearSummary": year_summary.to_dict("records"),
    }

    output_path.write_text(
        "window.CA_PROSTATE_DATA = " + json.dumps(data, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )
    print(f"Created {output_path.resolve()}")


if __name__ == "__main__":
    main()

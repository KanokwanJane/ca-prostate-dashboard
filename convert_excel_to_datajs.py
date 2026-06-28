"""
Build aggregate data.js for the prostate regimen-by-stage infographic.

Usage:
  python convert_excel_to_datajs.py prostate_cancer_dashboard.xlsx data.js
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd


STAGE_ORDER = ["I", "II", "III", "IV"]
STAGE_META = {
    "I": {"label": "ระยะ I", "name": "ระยะเริ่มต้น", "color": "#2E8B7F"},
    "II": {"label": "ระยะ II", "name": "ระยะลุกลามเฉพาะที่", "color": "#2F6DB0"},
    "III": {"label": "ระยะ III", "name": "ระยะลุกลามต่อมน้ำเหลือง", "color": "#D98A2B"},
    "IV": {"label": "ระยะ IV", "name": "ระยะแพร่กระจาย", "color": "#C0453B"},
}

TREATMENT_LABELS = {
    "Hormone": "ADT",
    "Radiation": "RT",
    "Surgery": "RP",
    "Chemotherapy": "Chemo",
    "Targeted Therapy": "ARPI",
    "Interventional": "IR",
    "Immonotherapy": "IO",
    "Other": "อื่นๆ",
}

HEATMAP_TREATMENTS = [
    ("Hormone", "ฮอร์โมน (ADT)"),
    ("Radiation", "รังสีรักษา (RT)"),
    ("Surgery", "ผ่าตัด (RP)"),
    ("Chemotherapy", "เคมีบำบัด"),
    ("Targeted Therapy", "มุ่งเป้า (ARPI)"),
    ("Interventional", "หัตถการ (IR)"),
    ("Immonotherapy", "ภูมิคุ้มกัน (IO)"),
]

ACTIVE_TREATMENTS = set(TREATMENT_LABELS)
NON_ACTIVE = {"Loss Follow-up", "Refer", "Supportive", "ปฏิเสธการรักษา", "ไม่ระบุ"}


def clean(value, default="ไม่ระบุ"):
    if pd.isna(value):
        return default
    text = str(value).strip()
    return text if text else default


def pct(numerator, denominator, digits=1):
    if not denominator:
        return 0
    return round((numerator / denominator) * 100, digits)


def fmt_regimen(treatments):
    labels = [TREATMENT_LABELS.get(t, t) for t in treatments]
    order = ["RP", "RT", "ADT", "Chemo", "ARPI", "IR", "IO", "อื่นๆ"]
    labels = sorted(labels, key=lambda x: order.index(x) if x in order else len(order))
    return " + ".join(labels)


def main():
    excel_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("prostate_cancer_dashboard.xlsx")
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("data.js")

    dashboard = pd.read_excel(excel_path, sheet_name="Dashboard")
    patients = pd.read_excel(excel_path, sheet_name="Patient Data")
    treatments = pd.read_excel(excel_path, sheet_name="Treatment Data")
    unknown = pd.read_excel(excel_path, sheet_name="Unknown", header=1)

    patients["HN"] = patients["HN"].map(clean)
    patients["stage"] = patients["Stage_หลัก"].map(clean)
    patients = patients[patients["stage"].isin(STAGE_ORDER)].copy()

    treatments["HN"] = treatments["HN"].map(clean)
    treatments["stage"] = treatments["Stage_หลัก"].map(clean)
    treatments["treatment"] = treatments["วิธีการรักษา"].map(clean)
    treatments = treatments[treatments["stage"].isin(STAGE_ORDER)].copy()

    stage_patient_counts = {
        stage: int(patients.loc[patients["stage"] == stage, "HN"].nunique())
        for stage in STAGE_ORDER
    }

    # Coverage by treatment is per patient, so duplicated event rows do not inflate percentages.
    patient_treatment = (
        treatments[["HN", "stage", "treatment"]]
        .drop_duplicates()
        .query("treatment not in @NON_ACTIVE")
    )

    coverage = {}
    for treatment, label in HEATMAP_TREATMENTS:
        row = {"treatment": treatment, "label": label, "stages": {}}
        for stage in STAGE_ORDER:
            count = int(
                patient_treatment[
                    (patient_treatment["stage"] == stage)
                    & (patient_treatment["treatment"] == treatment)
                ]["HN"].nunique()
            )
            total = stage_patient_counts[stage]
            row["stages"][stage] = {"count": count, "percent": pct(count, total, 0)}
        coverage[treatment] = row

    patient_stage = dict(zip(patients["HN"], patients["stage"]))
    active = patient_treatment[patient_treatment["treatment"].isin(ACTIVE_TREATMENTS)]
    grouped = defaultdict(set)
    for _, row in active.iterrows():
        grouped[row["HN"]].add(row["treatment"])

    regimen_counts = {stage: Counter() for stage in STAGE_ORDER}
    multimodal_counts = {stage: 0 for stage in STAGE_ORDER}
    active_patient_counts = {stage: 0 for stage in STAGE_ORDER}

    for hn, treatment_set in grouped.items():
        stage = patient_stage.get(hn)
        if stage not in STAGE_ORDER or not treatment_set:
            continue
        active_patient_counts[stage] += 1
        if len(treatment_set) >= 2:
            multimodal_counts[stage] += 1
        regimen_counts[stage][fmt_regimen(treatment_set)] += 1

    panels = []
    for stage in STAGE_ORDER:
        total = stage_patient_counts[stage]
        counter = regimen_counts[stage]
        top = counter.most_common(6)
        if len(counter) > 6:
            shown = sum(v for _, v in top)
            top.append(("อื่นๆ (รวม)", sum(counter.values()) - shown))

        max_count = max([v for _, v in top] or [1])
        panels.append(
            {
                "stage": stage,
                "label": STAGE_META[stage]["label"],
                "name": STAGE_META[stage]["name"],
                "color": STAGE_META[stage]["color"],
                "patients": total,
                "activePatients": active_patient_counts[stage],
                "multimodalPatients": multimodal_counts[stage],
                "multimodalPercent": pct(multimodal_counts[stage], active_patient_counts[stage], 0),
                "regimens": [
                    {
                        "name": name,
                        "count": int(count),
                        "percent": pct(count, total, 1),
                        "width": pct(count, max_count, 1),
                        "combined": " + " in name,
                    }
                    for name, count in top
                    if count > 0
                ],
            }
        )

    total_known = int(patients["HN"].nunique())
    total_active = sum(active_patient_counts.values())
    total_multimodal = sum(multimodal_counts.values())

    data = {
        "sourceFile": excel_path.name,
        "summary": {
            "knownStagePatients": total_known,
            "treatmentEvents": int(len(treatments)),
            "stageCount": len(STAGE_ORDER),
            "unknownStagePatients": int(dashboard.iloc[4, 7]) if pd.notna(dashboard.iloc[4, 7]) else int(unknown["HN"].nunique()) if "HN" in unknown else 0,
            "activePatients": int(total_active),
            "multimodalPatients": int(total_multimodal),
            "multimodalPercent": pct(total_multimodal, total_active, 0),
        },
        "stages": [
            {
                "stage": stage,
                "label": STAGE_META[stage]["label"],
                "name": STAGE_META[stage]["name"],
                "color": STAGE_META[stage]["color"],
                "patients": stage_patient_counts[stage],
            }
            for stage in STAGE_ORDER
        ],
        "heatmap": [coverage[treatment] for treatment, _ in HEATMAP_TREATMENTS],
        "panels": panels,
        "notes": [
            "รวมระยะย่อย IIA/IIB/IIC เป็น II, IIIA/IIIB/IIIC เป็น III, IVA/IVB เป็น IV",
            "Heatmap นับต่อผู้ป่วยต่อวิธีการรักษา ส่วนเหตุการณ์การรักษาทั้งหมดมาจาก Treatment Data",
            "Regimen นับชุดวิธีการรักษาต่อผู้ป่วย โดยตัดกลุ่มประคับประคอง ส่งต่อ ปฏิเสธ ขาดติดตาม และไม่ระบุออกจากการจัดชุด",
        ],
    }

    output_path.write_text(
        "window.CA_PROSTATE_DATA = "
        + json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )
    print(f"Created {output_path.resolve()}")


if __name__ == "__main__":
    main()

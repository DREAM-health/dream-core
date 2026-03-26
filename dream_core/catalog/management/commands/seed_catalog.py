"""
dream_core/catalog/fixtures/seed_catalog.py

Management command to seed the test catalog with a starter set of
real-world test panels, definitions, units, and reference ranges.

Usage:
    python manage.py seed_catalog

This is NOT a migration — it is idempotent and safe to run repeatedly.
"""
from django.core.management.base import BaseCommand
from decimal import Decimal
from dream_core.catalog.models import MeasurementUnit, LabTestPanel, LabTestDefinition, ReferenceRange


UNITS = [
    {"symbol": "g/dL",    "name": "Grams per decilitre",         "ucum_code": "g/dL"},
    {"symbol": "fL",      "name": "Femtolitres",                  "ucum_code": "fL"},
    {"symbol": "pg",      "name": "Picograms",                    "ucum_code": "pg"},
    {"symbol": "%",       "name": "Percent",                      "ucum_code": "%"},
    {"symbol": "10^3/µL", "name": "Thousands per microlitre",    "ucum_code": "10*3/uL"},
    {"symbol": "10^6/µL", "name": "Millions per microlitre",     "ucum_code": "10*6/uL"},
    {"symbol": "mg/dL",   "name": "Milligrams per decilitre",    "ucum_code": "mg/dL"},
    {"symbol": "mmol/L",  "name": "Millimoles per litre",        "ucum_code": "mmol/L"},
    {"symbol": "U/L",     "name": "Units per litre",             "ucum_code": "U/L"},
    {"symbol": "IU/L",    "name": "International units per litre", "ucum_code": "[IU]/L"},
    {"symbol": "g/L",     "name": "Grams per litre",             "ucum_code": "g/L"},
    {"symbol": "µmol/L",  "name": "Micromoles per litre",        "ucum_code": "umol/L"},
    {"symbol": "mEq/L",   "name": "Milliequivalents per litre",  "ucum_code": "meq/L"},
    {"symbol": "mIU/L",   "name": "Milli-international units per litre", "ucum_code": "m[IU]/L"},
    {"symbol": "ng/mL",   "name": "Nanograms per millilitre",    "ucum_code": "ng/mL"},
    {"symbol": "s",       "name": "Seconds",                     "ucum_code": "s"},
    {"symbol": "ratio",   "name": "Ratio",                       "ucum_code": "{ratio}"},
]

FBC_TESTS = [
    {
        "code": "HGB",  "name": "Haemoglobin", "abbreviation": "Hb",
        "loinc_code": "718-7", "unit_symbol": "g/dL", "decimal_places": 1,
        "turnaround_hours": 2,
        "method": "Spectrophotometry (SLS method)",
        "ranges": [
            {"gender": "male",   "label": "Adult Male",   "low_normal": "13.0", "high_normal": "17.0", "low_critical": "7.0",  "high_critical": "20.0", "low_reportable": "0.0",  "high_reportable": "25.0"},
            {"gender": "female", "label": "Adult Female", "low_normal": "12.0", "high_normal": "15.5", "low_critical": "7.0",  "high_critical": "20.0", "low_reportable": "0.0",  "high_reportable": "25.0"},
        ],
    },
    {
        "code": "WBC",  "name": "White Blood Cell Count", "abbreviation": "WBC",
        "loinc_code": "6690-2", "unit_symbol": "10^3/µL", "decimal_places": 2,
        "turnaround_hours": 2,
        "ranges": [
            {"gender": "any", "label": "Adult", "low_normal": "4.0", "high_normal": "11.0", "low_critical": "2.0", "high_critical": "30.0", "low_reportable": "0.0", "high_reportable": "100.0"},
        ],
    },
    {
        "code": "PLT",  "name": "Platelet Count", "abbreviation": "PLT",
        "loinc_code": "777-3", "unit_symbol": "10^3/µL", "decimal_places": 0,
        "turnaround_hours": 2,
        "ranges": [
            {"gender": "any", "label": "Adult", "low_normal": "150.0", "high_normal": "400.0", "low_critical": "50.0", "high_critical": "1000.0", "low_reportable": "0.0", "high_reportable": "2000.0"},
        ],
    },
    {
        "code": "RBC",  "name": "Red Blood Cell Count", "abbreviation": "RBC",
        "loinc_code": "789-8", "unit_symbol": "10^6/µL", "decimal_places": 2,
        "turnaround_hours": 2,
        "ranges": [
            {"gender": "male",   "label": "Adult Male",   "low_normal": "4.50", "high_normal": "5.90", "low_critical": "2.0", "high_critical": "8.0", "low_reportable": "0.0", "high_reportable": "12.0"},
            {"gender": "female", "label": "Adult Female", "low_normal": "4.00", "high_normal": "5.20", "low_critical": "2.0", "high_critical": "8.0", "low_reportable": "0.0", "high_reportable": "12.0"},
        ],
    },
    {
        "code": "HCT",  "name": "Haematocrit", "abbreviation": "Hct",
        "loinc_code": "4544-3", "unit_symbol": "%", "decimal_places": 1,
        "turnaround_hours": 2,
        "ranges": [
            {"gender": "male",   "label": "Adult Male",   "low_normal": "40.0", "high_normal": "52.0", "low_critical": "20.0", "high_critical": "60.0", "low_reportable": "0.0", "high_reportable": "75.0"},
            {"gender": "female", "label": "Adult Female", "low_normal": "36.0", "high_normal": "46.0", "low_critical": "20.0", "high_critical": "60.0", "low_reportable": "0.0", "high_reportable": "75.0"},
        ],
    },
    {
        "code": "MCV",  "name": "Mean Corpuscular Volume", "abbreviation": "MCV",
        "loinc_code": "787-2", "unit_symbol": "fL", "decimal_places": 1,
        "turnaround_hours": 2,
        "ranges": [
            {"gender": "any", "label": "Adult", "low_normal": "80.0", "high_normal": "100.0", "low_reportable": "50.0", "high_reportable": "130.0"},
        ],
    },
    {
        "code": "MCH",  "name": "Mean Corpuscular Haemoglobin", "abbreviation": "MCH",
        "loinc_code": "785-6", "unit_symbol": "pg", "decimal_places": 1,
        "turnaround_hours": 2,
        "ranges": [
            {"gender": "any", "label": "Adult", "low_normal": "27.0", "high_normal": "33.0", "low_reportable": "10.0", "high_reportable": "50.0"},
        ],
    },
    {
        "code": "MCHC", "name": "Mean Corpuscular Haemoglobin Concentration", "abbreviation": "MCHC",
        "loinc_code": "786-4", "unit_symbol": "g/dL", "decimal_places": 1,
        "turnaround_hours": 2,
        "ranges": [
            {"gender": "any", "label": "Adult", "low_normal": "32.0", "high_normal": "36.0", "low_reportable": "20.0", "high_reportable": "45.0"},
        ],
    },
]

CMP_TESTS = [
    {
        "code": "GLU-F", "name": "Glucose (Fasting)", "abbreviation": "Glu",
        "loinc_code": "1558-6", "unit_symbol": "mg/dL", "decimal_places": 0,
        "turnaround_hours": 4,
        "method": "Hexokinase enzymatic",
        "ranges": [
            {"gender": "any", "label": "Adult Fasting", "low_normal": "70.0", "high_normal": "99.0", "low_critical": "40.0", "high_critical": "500.0", "low_reportable": "10.0", "high_reportable": "700.0"},
        ],
    },
    {
        "code": "UREA",  "name": "Blood Urea Nitrogen", "abbreviation": "BUN",
        "loinc_code": "3094-0", "unit_symbol": "mg/dL", "decimal_places": 0,
        "turnaround_hours": 4,
        "ranges": [
            {"gender": "any", "label": "Adult", "low_normal": "7.0", "high_normal": "25.0", "high_critical": "100.0", "low_reportable": "0.0", "high_reportable": "200.0"},
        ],
    },
    {
        "code": "CREAT", "name": "Creatinine", "abbreviation": "Cr",
        "loinc_code": "2160-0", "unit_symbol": "mg/dL", "decimal_places": 2,
        "turnaround_hours": 4,
        "method": "Jaffe modified kinetic",
        "ranges": [
            {"gender": "male",   "label": "Adult Male",   "low_normal": "0.74", "high_normal": "1.35", "high_critical": "10.0", "low_reportable": "0.0", "high_reportable": "20.0"},
            {"gender": "female", "label": "Adult Female", "low_normal": "0.59", "high_normal": "1.04", "high_critical": "10.0", "low_reportable": "0.0", "high_reportable": "20.0"},
        ],
    },
    {
        "code": "NA",    "name": "Sodium", "abbreviation": "Na",
        "loinc_code": "2951-2", "unit_symbol": "mEq/L", "decimal_places": 0,
        "turnaround_hours": 4,
        "ranges": [
            {"gender": "any", "label": "Adult", "low_normal": "136.0", "high_normal": "145.0", "low_critical": "120.0", "high_critical": "160.0", "low_reportable": "100.0", "high_reportable": "200.0"},
        ],
    },
    {
        "code": "K",     "name": "Potassium", "abbreviation": "K",
        "loinc_code": "2823-3", "unit_symbol": "mEq/L", "decimal_places": 1,
        "turnaround_hours": 4,
        "ranges": [
            {"gender": "any", "label": "Adult", "low_normal": "3.5", "high_normal": "5.1", "low_critical": "2.5", "high_critical": "6.5", "low_reportable": "1.0", "high_reportable": "10.0"},
        ],
    },
    {
        "code": "ALT",   "name": "Alanine Aminotransferase", "abbreviation": "ALT",
        "loinc_code": "1742-6", "unit_symbol": "U/L", "decimal_places": 0,
        "turnaround_hours": 4,
        "method": "IFCC kinetic",
        "ranges": [
            {"gender": "male",   "label": "Adult Male",   "low_normal": "7.0",  "high_normal": "56.0", "high_critical": "1000.0", "low_reportable": "0.0", "high_reportable": "5000.0"},
            {"gender": "female", "label": "Adult Female", "low_normal": "7.0",  "high_normal": "45.0", "high_critical": "1000.0", "low_reportable": "0.0", "high_reportable": "5000.0"},
        ],
    },
    {
        "code": "AST",   "name": "Aspartate Aminotransferase", "abbreviation": "AST",
        "loinc_code": "1920-8", "unit_symbol": "U/L", "decimal_places": 0,
        "turnaround_hours": 4,
        "ranges": [
            {"gender": "any", "label": "Adult", "low_normal": "10.0", "high_normal": "40.0", "high_critical": "1000.0", "low_reportable": "0.0", "high_reportable": "5000.0"},
        ],
    },
    {
        "code": "TBIL",  "name": "Total Bilirubin", "abbreviation": "T.Bil",
        "loinc_code": "1975-2", "unit_symbol": "mg/dL", "decimal_places": 1,
        "turnaround_hours": 4,
        "ranges": [
            {"gender": "any", "label": "Adult", "low_normal": "0.2", "high_normal": "1.2", "high_critical": "15.0", "low_reportable": "0.0", "high_reportable": "30.0"},
        ],
    },
    {
        "code": "TPROT", "name": "Total Protein", "abbreviation": "TP",
        "loinc_code": "2885-2", "unit_symbol": "g/dL", "decimal_places": 1,
        "turnaround_hours": 4,
        "ranges": [
            {"gender": "any", "label": "Adult", "low_normal": "6.3", "high_normal": "8.2", "low_reportable": "1.0", "high_reportable": "15.0"},
        ],
    },
    {
        "code": "ALB",   "name": "Albumin", "abbreviation": "Alb",
        "loinc_code": "1751-7", "unit_symbol": "g/dL", "decimal_places": 1,
        "turnaround_hours": 4,
        "ranges": [
            {"gender": "any", "label": "Adult", "low_normal": "3.5", "high_normal": "5.0", "low_critical": "2.0", "low_reportable": "0.5", "high_reportable": "8.0"},
        ],
    },
]

LIPID_TESTS = [
    {
        "code": "TCHOL", "name": "Total Cholesterol", "abbreviation": "T.Chol",
        "loinc_code": "2093-3", "unit_symbol": "mg/dL", "decimal_places": 0,
        "turnaround_hours": 4,
        "ranges": [
            {"gender": "any", "label": "Desirable", "high_normal": "200.0", "high_critical": "400.0", "low_reportable": "50.0", "high_reportable": "600.0"},
        ],
    },
    {
        "code": "HDL",   "name": "HDL Cholesterol", "abbreviation": "HDL",
        "loinc_code": "2085-9", "unit_symbol": "mg/dL", "decimal_places": 0,
        "turnaround_hours": 4,
        "ranges": [
            {"gender": "male",   "label": "Adult Male",   "low_normal": "40.0", "high_normal": "60.0", "low_reportable": "5.0", "high_reportable": "200.0"},
            {"gender": "female", "label": "Adult Female", "low_normal": "50.0", "high_normal": "60.0", "low_reportable": "5.0", "high_reportable": "200.0"},
        ],
    },
    {
        "code": "LDL",   "name": "LDL Cholesterol (calculated)", "abbreviation": "LDL",
        "loinc_code": "13457-7", "unit_symbol": "mg/dL", "decimal_places": 0,
        "turnaround_hours": 4,
        "ranges": [
            {"gender": "any", "label": "Optimal", "high_normal": "100.0", "high_critical": "300.0", "low_reportable": "10.0", "high_reportable": "500.0"},
        ],
    },
    {
        "code": "TRIG",  "name": "Triglycerides", "abbreviation": "TG",
        "loinc_code": "2571-8", "unit_symbol": "mg/dL", "decimal_places": 0,
        "turnaround_hours": 4,
        "ranges": [
            {"gender": "any", "label": "Normal", "high_normal": "150.0", "high_critical": "1000.0", "low_reportable": "10.0", "high_reportable": "5000.0"},
        ],
    },
]

THYROID_TESTS = [
    {
        "code": "TSH",   "name": "Thyroid Stimulating Hormone", "abbreviation": "TSH",
        "loinc_code": "3016-3", "unit_symbol": "mIU/L", "decimal_places": 3,
        "turnaround_hours": 6,
        "method": "Chemiluminescent immunoassay",
        "ranges": [
            {"gender": "any", "label": "Adult", "low_normal": "0.400", "high_normal": "4.000", "low_critical": "0.010", "high_critical": "10.000", "low_reportable": "0.001", "high_reportable": "100.000"},
        ],
    },
    {
        "code": "FT4",   "name": "Free Thyroxine", "abbreviation": "fT4",
        "loinc_code": "3024-7", "unit_symbol": "ng/mL", "decimal_places": 2,
        "turnaround_hours": 6,
        "ranges": [
            {"gender": "any", "label": "Adult", "low_normal": "0.93", "high_normal": "1.70", "low_reportable": "0.10", "high_reportable": "10.00"},
        ],
    },
    {
        "code": "FT3",   "name": "Free Triiodothyronine", "abbreviation": "fT3",
        "loinc_code": "3051-0", "unit_symbol": "ng/mL", "decimal_places": 2,
        "turnaround_hours": 6,
        "ranges": [
            {"gender": "any", "label": "Adult", "low_normal": "2.0", "high_normal": "4.4", "low_reportable": "0.5", "high_reportable": "15.0"},
        ],
    },
]

PANELS_DATA = [
    {
        "code": "FBC", "name": "Full Blood Count", "category": "Haematology",
        "loinc_code": "58410-2",
        "container_type": "EDTA tube (purple cap)",
        "turnaround_hours": 2, "fasting_required": False, "sort_order": 10,
        "tests": FBC_TESTS,
    },
    {
        "code": "CMP", "name": "Comprehensive Metabolic Panel", "category": "Biochemistry",
        "loinc_code": "24323-8", 
        "container_type": "SST (gold cap)",
        "turnaround_hours": 4, "fasting_required": True, "sort_order": 20,
        "tests": CMP_TESTS,
    },
    {
        "code": "LIPID", "name": "Lipid Panel", "category": "Biochemistry",
        "loinc_code": "57698-3", 
        "container_type": "SST (gold cap)",
        "turnaround_hours": 4, "fasting_required": True, "sort_order": 30,
        "tests": LIPID_TESTS,
    },
    {
        "code": "TFT", "name": "Thyroid Function Tests", "category": "Endocrinology",
        "loinc_code": "11580-8", 
        "container_type": "SST (gold cap)",
        "turnaround_hours": 6, "fasting_required": False, "sort_order": 40,
        "tests": THYROID_TESTS,
    },
]


class Command(BaseCommand):
    help = "Seed the test catalog with standard panels and reference ranges."

    def handle(self, *args: object, **options: object) -> None:
        self.stdout.write("Seeding units...")
        unit_map: dict[str, MeasurementUnit] = {}
        for u in UNITS:
            unit, created = MeasurementUnit.objects.get_or_create(
                symbol=u["symbol"],
                defaults={"name": u["name"], "ucum_code": u.get("ucum_code", "")},
            )
            unit_map[unit.symbol] = unit
            if created:
                self.stdout.write(f"  Created unit: {unit.symbol}")

        for panel_data in PANELS_DATA:
            tests_data = panel_data.pop("tests")
            panel, panel_created = LabTestPanel.objects.get_or_create(
                code=panel_data["code"],
                defaults={k: v for k, v in panel_data.items()},
            )
            if panel_created:
                self.stdout.write(f"Panel created: [{panel.code}] {panel.name}")
            else:
                self.stdout.write(f"Panel exists:  [{panel.code}] {panel.name}")

            for i, t in enumerate(tests_data):
                ranges_data = t.pop("ranges", [])
                unit_symbol = t.pop("unit_symbol", None)
                unit = unit_map.get(unit_symbol) if unit_symbol else None

                test, test_created = LabTestDefinition.objects.get_or_create(
                    code=t["code"],
                    defaults={
                        **t,
                        "panel": panel,
                        "unit": unit,
                        "sort_order": i,
                        "result_type": LabTestDefinition.ResultTypeChoices.NUMERIC,
                    },
                )
                if test_created:
                    self.stdout.write(f"  Test created: [{test.code}] {test.name}")
                    for rr in ranges_data:
                        ReferenceRange.objects.create(
                            test=test,
                            **{k: Decimal(v) if k not in ("gender", "label") else v
                               for k, v in rr.items()},
                        )

        self.stdout.write(self.style.SUCCESS("Catalog seeded successfully."))

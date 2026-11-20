
"""
EnerFlow - Independent Validation

Recalculate regional energy indicators from raw RTE CSV
using Python, independently from DuckDB transformations.

DuckDB is used only to read the final Parquet file.
"""

import csv
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import duckdb

RAW = Path("data/raw/rte_energy.csv")
GOLD = Path("data/processed/gold/regional_summary.parquet")

HALF_HOUR = Decimal("0.5")
TOLERANCE_MWH = Decimal("0.001")
TOLERANCE_PCT = Decimal("0.000001")

if not RAW.exists() or not GOLD.exists():
    raise FileNotFoundError("Missing Bronze or Gold dataset")

# Independent calculations using raw CSV
regional = defaultdict(
    lambda: {
        "consumption": Decimal("0"),
        "renewable": Decimal("0"),
        "intervals": 0,
    }
)

seen = set()
rejected = 0

with RAW.open(encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f, delimiter=";")

    for row in reader:

        # DST correction independently reproduced
        if (
            row["date"] == "2025-03-30"
            and row["heure"] in ("02:00", "02:30")
        ):
            rejected += 1
            continue

        timestamp = datetime.fromisoformat(
            row["date_heure"]
        ).astimezone(timezone.utc)

        key = (row["code_insee_region"], timestamp)

        if key in seen:
            raise AssertionError(
                f"Duplicate region/timestamp: {key}"
            )
        seen.add(key)

        consumption = Decimal(row["consommation"])

        renewable = sum(
            (
                Decimal(row[column])
                for column in (
                    "eolien",
                    "solaire",
                    "hydraulique",
                    "bioenergies",
                )
            ),
            Decimal("0"),
        )

        if consumption <= 0:
            raise AssertionError("Invalid consumption")

        region = row["libelle_region"]

        regional[region]["consumption"] += (
            consumption * HALF_HOUR
        )

        regional[region]["renewable"] += (
            renewable * HALF_HOUR
        )

        regional[region]["intervals"] += 1

# Read Gold output without repeating its SQL calculations
con = duckdb.connect()

gold_rows = con.execute("""
    SELECT
        libelle_region,
        nb_intervalles,
        consommation_estimee_mwh,
        production_enr_estimee_mwh,
        couverture_enr_pct
    FROM read_parquet(
        'data/processed/gold/regional_summary.parquet'
    )
    ORDER BY libelle_region
""").fetchall()

con.close()

assert rejected == 6
assert len(gold_rows) == len(regional) == 3

print("=== ENERFLOW INDEPENDENT VALIDATION ===")
print("Method: Python Decimal calculations from Bronze CSV")
print("Rejected DST observations:", rejected)
print("Regions:", len(regional))

for (
    region,
    gold_intervals,
    gold_consumption,
    gold_renewable,
    gold_coverage,
) in gold_rows:

    values = regional[region]

    expected_consumption = values["consumption"]
    expected_renewable = values["renewable"]

    expected_coverage = (
        Decimal("100")
        * expected_renewable
        / expected_consumption
    )

    def close(actual, expected, tolerance):
        return abs(
            Decimal(str(actual)) - expected
        ) <= tolerance

    assert gold_intervals == values["intervals"]

    assert close(
        gold_consumption,
        expected_consumption,
        TOLERANCE_MWH,
    )

    assert close(
        gold_renewable,
        expected_renewable,
        TOLERANCE_MWH,
    )

    assert close(
        gold_coverage,
        expected_coverage,
        TOLERANCE_PCT,
    )

    print(f"\nRegion: {region}")
    print(f"Intervals: {values['intervals']}")
    print(f"Consumption MWh: {expected_consumption}")
    print(f"Renewable MWh: {expected_renewable}")
    print(f"Coverage: {expected_coverage:.2f}%")
    print("Validation: PASS")

print("\n=== FINAL RESULT ===")
print("PASS: All regional Gold results independently verified")

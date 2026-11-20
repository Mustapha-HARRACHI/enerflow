"""
EnerFlow - CSV vs Parquet Benchmark

Compare identical Silver data and SQL aggregations.
Measurements: file size and median execution time.
"""

from pathlib import Path
from datetime import datetime, timezone
from statistics import median
from time import perf_counter
import json
import random
import duckdb

SILVER = Path("data/processed/rte_silver.parquet")
BENCHMARK = Path("data/processed/benchmark")
CSV = BENCHMARK / "silver_comparison.csv"
REPORT = BENCHMARK / "format_benchmark.json"

RUNS = 20
WARMUPS = 3

BENCHMARK.mkdir(parents=True, exist_ok=True)

if not SILVER.exists():
    raise FileNotFoundError(SILVER)

con = duckdb.connect()

# Export exactly the same Silver data to CSV.
con.execute("""
    COPY (
        SELECT *
        FROM read_parquet(
            'data/processed/rte_silver.parquet'
        )
        ORDER BY code_insee_region, date_heure_utc
    )
    TO 'data/processed/benchmark/silver_comparison.csv'
    (HEADER, DELIMITER ';')
""")

sources = {
    "CSV": (
        "read_csv_auto("
        "'data/processed/benchmark/silver_comparison.csv',"
        " delim=';', header=true)"
    ),
    "Parquet": (
        "read_parquet("
        "'data/processed/rte_silver.parquet')"
    ),
}

# Same SQL operations for both formats.
def query(source):
    return f"""
        SELECT
            libelle_region,
            COUNT(*) AS nb_lignes,
            SUM(consommation_mw) AS consommation,
            SUM(production_enr_mw) AS production_enr
        FROM {source}
        GROUP BY libelle_region
        ORDER BY libelle_region
    """

queries = {
    name: query(source)
    for name, source in sources.items()
}

# Ensure both formats produce equivalent results.
csv_result = con.execute(queries["CSV"]).fetchall()
parquet_result = con.execute(queries["Parquet"]).fetchall()

assert len(csv_result) == len(parquet_result) == 3

for csv_row, parquet_row in zip(csv_result, parquet_result):
    assert csv_row[:2] == parquet_row[:2]
    for a, b in zip(csv_row[2:], parquet_row[2:]):
        assert abs(float(a) - float(b)) < 0.001

assert sum(row[1] for row in csv_result) == 26064

# Warm up both file formats.
for _ in range(WARMUPS):
    for name in ("CSV", "Parquet"):
        con.execute(queries[name]).fetchall()

# Alternate query order to reduce order bias.
rng = random.Random(42)
timings = {"CSV": [], "Parquet": []}

for _ in range(RUNS):
    order = ["CSV", "Parquet"]
    rng.shuffle(order)

    for name in order:
        start = perf_counter()
        con.execute(queries[name]).fetchall()
        elapsed_ms = (perf_counter() - start) * 1000
        timings[name].append(elapsed_ms)

csv_bytes = CSV.stat().st_size
parquet_bytes = SILVER.stat().st_size

csv_median = median(timings["CSV"])
parquet_median = median(timings["Parquet"])

report = {
    "timestamp_utc": datetime.now(
        timezone.utc
    ).isoformat(),
    "engine": f"DuckDB {duckdb.__version__}",
    "runs_per_format": RUNS,
    "warmups_per_format": WARMUPS,
    "rows": 26064,
    "result_equivalence": "PASS",
    "csv_bytes": csv_bytes,
    "parquet_bytes": parquet_bytes,
    "csv_median_ms": csv_median,
    "parquet_median_ms": parquet_median,
    "csv_times_ms": timings["CSV"],
    "parquet_times_ms": timings["Parquet"],
}

REPORT.write_text(
    json.dumps(report, indent=2),
    encoding="utf-8",
)

print("=== ENERFLOW FORMAT BENCHMARK ===")
print("Engine:", report["engine"])
print("Rows: 26064")
print("Result equivalence: PASS")
print("Runs per format:", RUNS)

print("\n=== STORAGE SIZE ===")
print(f"CSV:     {csv_bytes:,} bytes")
print(f"Parquet: {parquet_bytes:,} bytes")
print(f"CSV / Parquet: {csv_bytes / parquet_bytes:.2f}x")

print("\n=== MEDIAN EXECUTION TIME ===")
print(f"CSV:     {csv_median:.3f} ms")
print(f"Parquet: {parquet_median:.3f} ms")
print(f"CSV / Parquet: {csv_median / parquet_median:.2f}x")

print("\n=== OUTPUT ===")
print(REPORT)
print("Benchmark: SUCCESS")

con.close()

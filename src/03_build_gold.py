
from pathlib import Path
import duckdb

SILVER = Path("data/processed/rte_silver.parquet")
GOLD = Path("data/processed/gold")
GOLD.mkdir(parents=True, exist_ok=True)

if not SILVER.exists():
    raise FileNotFoundError(f"Missing Silver file: {SILVER}")

con = duckdb.connect()

# 1. Daily energy indicators, using UTC calendar days
con.execute("""
    CREATE TEMP TABLE gold_daily AS
    SELECT
        code_insee_region,
        libelle_region,
        CAST(
            date_heure_utc AT TIME ZONE 'UTC'
            AS DATE
        ) AS date_utc,
        COUNT(*) AS nb_intervalles,
        SUM(consommation_mw) * 0.5
            AS consommation_estimee_mwh,
        SUM(production_enr_mw) * 0.5
            AS production_enr_estimee_mwh,
        100.0 * SUM(production_enr_mw)
            / NULLIF(SUM(consommation_mw), 0)
            AS couverture_enr_pct
    FROM read_parquet(
        'data/processed/rte_silver.parquet'
    )
    GROUP BY 1, 2, 3
""")

# 2. Regional summary and ranking
con.execute("""
    CREATE TEMP TABLE gold_regional AS
    WITH totals AS (
        SELECT
            code_insee_region,
            libelle_region,
            COUNT(*) AS nb_jours,
            SUM(nb_intervalles) AS nb_intervalles,
            SUM(consommation_estimee_mwh)
                AS consommation_estimee_mwh,
            SUM(production_enr_estimee_mwh)
                AS production_enr_estimee_mwh,
            100.0 * SUM(production_enr_estimee_mwh)
                / NULLIF(SUM(consommation_estimee_mwh), 0)
                AS couverture_enr_pct
        FROM gold_daily
        GROUP BY 1, 2
    )
    SELECT *,
        RANK() OVER (
            ORDER BY couverture_enr_pct DESC
        ) AS classement
    FROM totals
""")

# 3. Quality checks before export
silver_rows = con.execute("""
    SELECT COUNT(*)
    FROM read_parquet(
        'data/processed/rte_silver.parquet'
    )
""").fetchone()[0]

daily_rows = con.execute(
    "SELECT COUNT(*) FROM gold_daily"
).fetchone()[0]

regional_rows = con.execute(
    "SELECT COUNT(*) FROM gold_regional"
).fetchone()[0]

incomplete_days = con.execute("""
    SELECT COUNT(*)
    FROM gold_daily
    WHERE nb_intervalles <> 48
""").fetchone()[0]

assert silver_rows == 26064
assert daily_rows == 543
assert regional_rows == 3
assert incomplete_days == 0, (
    f"{incomplete_days} incomplete region-days"
)

# 4. Export Gold datasets to Parquet
con.execute("""
    COPY (
        SELECT *
        FROM gold_daily
        ORDER BY code_insee_region, date_utc
    )
    TO 'data/processed/gold/regional_daily.parquet'
    (FORMAT PARQUET, COMPRESSION ZSTD)
""")

con.execute("""
    COPY (
        SELECT *
        FROM gold_regional
        ORDER BY classement
    )
    TO 'data/processed/gold/regional_summary.parquet'
    (FORMAT PARQUET, COMPRESSION ZSTD)
""")

# 5. Display real analytical results
print("=== ENERFLOW GOLD ===")
print("Silver observations:", silver_rows)
print("Daily rows:", daily_rows)
print("Regional rows:", regional_rows)
print("Incomplete region-days:", incomplete_days)

print("\n=== REGIONAL RANKING ===")
results = con.execute("""
    SELECT
        classement,
        libelle_region,
        nb_jours,
        ROUND(couverture_enr_pct, 2)
            AS couverture_pct,
        ROUND(consommation_estimee_mwh, 2)
            AS consommation_mwh,
        ROUND(production_enr_estimee_mwh, 2)
            AS production_enr_mwh
    FROM gold_regional
    ORDER BY classement
""").fetchall()

for row in results:
    print(row)

print("\n=== GOLD FILES ===")
for path in sorted(GOLD.glob("*.parquet")):
    print(path, path.stat().st_size, "bytes")

con.close()

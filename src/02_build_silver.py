
from pathlib import Path
import json
import hashlib
import duckdb

RAW = Path("data/raw/rte_energy.csv")
OUT = Path("data/processed")
OUT.mkdir(parents=True, exist_ok=True)

if not RAW.exists():
    raise FileNotFoundError(f"Missing Bronze file: {RAW}")

con = duckdb.connect()

# 1. Read Bronze without modifying the source
con.execute("""
    CREATE TEMP TABLE bronze AS
    SELECT *
    FROM read_csv(
        ?,
        delim=';',
        header=true,
        all_varchar=true
    )
""", [str(RAW)])

# 2. Convert measurements to explicit types
con.execute("""
    CREATE TEMP TABLE typed AS
    SELECT
        code_insee_region,
        libelle_region,
        "date" AS date_locale,
        heure AS heure_locale,
        TRY_CAST(date_heure AS TIMESTAMPTZ) AS timestamp_utc,
        TRY_CAST(consommation AS DOUBLE) AS consommation_mw,
        TRY_CAST(eolien AS DOUBLE) AS eolien_mw,
        TRY_CAST(solaire AS DOUBLE) AS solaire_mw,
        TRY_CAST(hydraulique AS DOUBLE) AS hydraulique_mw,
        TRY_CAST(bioenergies AS DOUBLE) AS bioenergies_mw,
        TRY_CAST(ech_physiques AS DOUBLE) AS echanges_mw
    FROM bronze
""")

# 3. Identify invalid observations
con.execute("""
    CREATE TEMP TABLE checked AS
    SELECT *,
        CASE
            WHEN date_locale = '2025-03-30'
                 AND heure_locale IN ('02:00', '02:30')
                THEN 'nonexistent_local_hour'
            WHEN code_insee_region IS NULL
                 OR TRIM(code_insee_region) = ''
                 OR libelle_region IS NULL
                 OR TRIM(libelle_region) = ''
                 OR TRY_CAST(date_locale AS DATE) IS NULL
                 OR timestamp_utc IS NULL
                 OR consommation_mw IS NULL
                 OR consommation_mw <= 0
                 OR eolien_mw IS NULL
                 OR solaire_mw IS NULL
                 OR hydraulique_mw IS NULL
                 OR bioenergies_mw IS NULL
                 OR echanges_mw IS NULL
                THEN 'invalid_measure_or_identifier'
            ELSE NULL
        END AS rejection_reason
    FROM typed
""")

# 4. Create clean Silver table
con.execute("""
    CREATE TEMP TABLE silver AS
    SELECT
        code_insee_region,
        libelle_region,
        CAST(date_locale AS DATE) AS date_locale,
        heure_locale,
        timestamp_utc AS date_heure_utc,
        consommation_mw,
        eolien_mw,
        solaire_mw,
        hydraulique_mw,
        bioenergies_mw,
        echanges_mw,
        (
            eolien_mw + solaire_mw
            + hydraulique_mw + bioenergies_mw
        ) AS production_enr_mw
    FROM checked
    WHERE rejection_reason IS NULL
""")

# 5. Count rows and verify uniqueness
raw_count = con.execute(
    "SELECT COUNT(*) FROM bronze"
).fetchone()[0]

silver_count = con.execute(
    "SELECT COUNT(*) FROM silver"
).fetchone()[0]

rejections = con.execute("""
    SELECT rejection_reason, COUNT(*)
    FROM checked
    WHERE rejection_reason IS NOT NULL
    GROUP BY rejection_reason
    ORDER BY rejection_reason
""").fetchall()

rejected_count = sum(count for _, count in rejections)

duplicate_keys = con.execute("""
    SELECT COUNT(*)
    FROM (
        SELECT code_insee_region, date_heure_utc
        FROM silver
        GROUP BY 1, 2
        HAVING COUNT(*) > 1
    )
""").fetchone()[0]

assert raw_count == silver_count + rejected_count
assert duplicate_keys == 0, "Duplicate keys remain in Silver"

# 6. Export Parquet and rejected rows
con.execute("""
    COPY (
        SELECT *
        FROM silver
        ORDER BY code_insee_region, date_heure_utc
    )
    TO 'data/processed/rte_silver.parquet'
    (FORMAT PARQUET, COMPRESSION ZSTD)
""")

con.execute("""
    COPY (
        SELECT *
        FROM checked
        WHERE rejection_reason IS NOT NULL
    )
    TO 'data/processed/silver_rejected.csv'
    (HEADER, DELIMITER ',')
""")

# 7. Save reproducible quality metrics
report = {
    "source": str(RAW),
    "source_sha256": hashlib.sha256(RAW.read_bytes()).hexdigest(),
    "raw_rows": raw_count,
    "silver_rows": silver_count,
    "rejected_rows": rejected_count,
    "duplicate_keys_silver": duplicate_keys,
    "rejection_reasons": dict(rejections),
}

(OUT / "silver_quality.json").write_text(
    json.dumps(report, indent=2),
    encoding="utf-8"
)

print("=== ENERFLOW SILVER ===")
print(json.dumps(report, indent=2))
print("\nSilver: data/processed/rte_silver.parquet")
print("Rejected: data/processed/silver_rejected.csv")
con.close()


# EnerFlow — Regional Renewable Electricity Analysis

End-to-end data engineering project built with **Python, DuckDB, Parquet and S3** on **Onyxia**.

**Author:** Mustapha HARRACHI — ECE Paris, ING4 Data & AI  
**Repository:** https://github.com/Mustapha-HARRACHI/enerflow

## 1. Research question

How does regional renewable electricity production relate to electricity consumption between January and June 2025 in **Bretagne, Occitanie and Hauts-de-France**?

We compare estimated renewable production with electricity demand, calculate regional coverage ratios, and rank the regions.

## 2. Data source

- **Provider:** RTE / Open Data Réseaux Énergies (ODRÉ)
- **Dataset:** [éCO2mix regional consolidated and definitive data](https://odre.opendatasoft.com/explore/dataset/eco2mix-regional-cons-def/)
- **API:** [Opendatasoft Explore API v2.1](https://odre.opendatasoft.com/api/explore/v2.1/catalog/datasets/eco2mix-regional-cons-def/exports/csv)
- **License:** Licence Ouverte v2.0 (Etalab)
- **Downloaded:** 2026-11-20
- **Period:** 2025-01-01 to 2025-06-30
- **Raw size:** 2,138,478 bytes (within the 1–5 MB requirement)
- **Raw observations:** 26,070; **columns:** 11
- **SHA-256:** `631b87cc0c89a6724ba4b523306bbfdcbe32725b06905167415589ef16237109`

The extraction script selects the three regions, date range and required electricity variables. Since the provider updates its dataset, subsequent API downloads may differ from the original snapshot.

## 3. Architecture

| Layer | Processing | S3 location |
|---|---|---|
| Bronze | Original RTE CSV | `enerflow/bronze/rte_energy.csv` |
| Silver | DuckDB cleaning, quality checks, ZSTD Parquet | `enerflow/silver/` |
| Gold | Daily metrics and regional ranking | `enerflow/gold/` |

**S3 bucket:** `s3://user-m-harrachi-ece`

Silver rejects six records associated with nonexistent local times (`02:00` and `02:30`) on 2025-03-30. This resolves six duplicate region/UTC-timestamp keys.

**Quality results:** 26,070 Bronze rows; 26,064 Silver rows; 6 rejected rows; 0 duplicate keys.

Gold uses 48 half-hour intervals per UTC day. For each measure, estimated energy (MWh) = sum of power (MW) × 0.5 h. Renewable production includes wind, solar, hydro and bioenergy.

**Renewable coverage (%) = 100 × total renewable production / total consumption.**

## 4. Reproduce the pipeline

**Prerequisites:** Python 3.13, DuckDB 1.5.5, Git; AWS CLI and Onyxia S3 credentials only for accessing the stored snapshot.

```bash
git clone https://github.com/Mustapha-HARRACHI/enerflow.git
cd enerflow
python -m venv .venv
source .venv/bin/activate
python -m pip install duckdb==1.5.5

# Download current source data from RTE
python src/01_extract_rte.py

# Build and verify all datasets
python src/02_build_silver.py
python src/03_build_gold.py
python src/04_validate_independent.py
python src/05_benchmark_formats.py
```

For **exact reproduction of the original snapshot**, replace the RTE download step with:

```bash
mkdir -p data/raw
aws s3 cp \
  s3://user-m-harrachi-ece/enerflow/bronze/rte_energy.csv \
  data/raw/rte_energy.csv --profile default
```

Check its SHA-256 against Section 2 before executing the remaining scripts.

**Local outputs:** `data/processed/rte_silver.parquet`, `data/processed/gold/regional_daily.parquet`, `data/processed/gold/regional_summary.parquet`, plus quality and benchmark reports.

## 5. Results

| Rank | Region | Estimated renewable coverage |
|---|---|---:|
| 1 | Occitanie | **64.10%** |
| 2 | Hauts-de-France | **27.42%** |
| 3 | Bretagne | **25.49%** |

Gold contains **543 region-days** (181 per region) and **3 regional summaries**. An independent Python/Decimal calculation from Bronze verifies all three regional totals and coverage ratios.

Coverage compares regional production against demand; it does **not** establish the exact share of renewable electricity physically consumed locally, because electricity can be exchanged between regions.

## 6. Benchmark and technical choices

Measured on Onyxia with **DuckDB 1.5.5**, using equivalent aggregations and 20 timed runs per format:

| Metric | CSV | Parquet |
|---|---:|---:|
| File size | 2,517,802 B | 338,881 B |
| Median query time | 284.956 ms | 4.032 ms |

Parquet was **7.43× smaller** and **70.68× faster** in this local benchmark. CSV uses automatic schema inference, so these figures must not be generalized to every workload.

DuckDB + Parquet was chosen over a Spark cluster because the input is only approximately 2.14 MB; the extra distributed-processing overhead is not justified at this scale. At 100× volume, partitioning and a new benchmark would be required before reconsidering Spark.

## 7. Restart on Onyxia

After restarting the VS Code service:

1. Open or clone the `enerflow` repository.
2. Reinstall/activate Python dependencies if necessary.
3. Restore the AWS `default` profile using the **official Onyxia S3 profile setup script**; never commit credentials.
4. Recover the Bronze snapshot from S3 with the command in Section 4.
5. Rerun Silver, Gold, independent validation and benchmark in order.

To inspect all published objects:

```bash
aws s3 ls \
  s3://user-m-harrachi-ece/enerflow/ \
  --recursive --profile default
```

## 8. Evidence and limitations

Execution evidence is stored in [`evidence/`](evidence/): Bronze upload, Silver processing, Gold aggregation, independent validation, format benchmark and final S3 storage.

Limitations include the three-region/six-month scope, the treatment of DST anomalies, estimated energy from half-hourly power values, possible API revisions and environment-dependent benchmark timings.

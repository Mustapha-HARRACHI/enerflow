# EnerFlow — Regional Electricity Data Pipeline

**Author:** HARRACHI Mustapha (ECE Paris, ING4 Data & AI)

## 1. Prerequisites

Onyxia VS Code (or Linux), **Python 3.13**, **Git**, **DuckDB 1.5.5** (`pip install duckdb==1.5.5`). For the original S3 snapshot: AWS CLI and an authorized Onyxia S3 profile named `default`. Never commit credentials.

## 2. Dataset

**RTE / ODRÉ — éCO2mix regional consolidated and definitive data**

URL: https://odre.opendatasoft.com/explore/dataset/eco2mix-regional-cons-def/

License: **Licence Ouverte 2.0 (Etalab)** · Downloaded: **2026-11-20**

Raw CSV: **2,138,478 bytes** (26,070 rows; 11 columns); period: **2025-01-01–2025-06-30**, three regions.

SHA-256: `631b87cc0c89a6724ba4b523306bbfdcbe32725b06905167415589ef16237109`

## 3. Problem statement

How does renewable electricity production compare with consumption in **Bretagne, Occitanie and Hauts-de-France** during the first half of 2025? We calculate daily indicators and regional renewable-production-to-consumption ratios.

## 4. S3 paths

Bucket: `s3://user-m-harrachi-ece/` · Project prefix: `enerflow/`

- **Bronze (raw):** `enerflow/bronze/rte_energy.csv`
- **Silver (cleaned):** `enerflow/silver/` — `rte_silver.parquet`, `silver_quality.json`, `silver_rejected.csv`
- **Gold (analytics):** `enerflow/gold/` — `regional_daily.parquet`, `regional_summary.parquet`

## 5. Reproduction and restart

**1. Clone and install:**

```bash
git clone https://github.com/Mustapha-HARRACHI/enerflow.git
cd enerflow
python -m venv .venv
source .venv/bin/activate
python -m pip install duckdb==1.5.5
```

**2. Obtain Bronze** (original snapshot, authorized Onyxia S3 access):

```bash
mkdir -p data/raw
aws s3 cp s3://user-m-harrachi-ece/enerflow/bronze/rte_energy.csv data/raw/rte_energy.csv --profile default
sha256sum data/raw/rte_energy.csv
```

Alternatively, without S3 access, run `python src/01_extract_rte.py` to download the **public** dataset from RTE; the content/hash may change after source updates.

**3. Execute in order:**

```bash
python src/02_build_silver.py
python src/03_build_gold.py
python src/04_validate_independent.py
python src/05_benchmark_formats.py
```

Outputs are written to `data/processed/` (excluded from Git); six execution screenshots are in `evidence/`.

After an **Onyxia restart**, reopen the repository (or clone again), reactivate/recreate `.venv`, restore the AWS `default` profile via **Onyxia → Data Storage → S3 → Profile Detail**, then repeat steps 2–3. The original SHA-256 above identifies the verified input snapshot.
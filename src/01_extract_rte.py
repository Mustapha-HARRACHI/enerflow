#!/usr/bin/env python3
"""
EnerFlow - RTE Dataset Extraction

Download regional electricity data from the official
RTE Open Data API.

Period: January 1 - June 30, 2025
Regions: Bretagne, Occitanie, Hauts-de-France
Raw dataset size requirement: 1-5 MB
"""

from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError
import hashlib
import sys


API_URL = (
    "https://odre.opendatasoft.com/api/explore/v2.1/"
    "catalog/datasets/eco2mix-regional-cons-def/exports/csv"
)

COLUMNS = [
    "code_insee_region",
    "libelle_region",
    "date",
    "heure",
    "date_heure",
    "consommation",
    "eolien",
    "solaire",
    "hydraulique",
    "bioenergies",
    "ech_physiques",
]

DATE_FILTER = (
    "date_heure >= date'2025-01-01' "
    "AND date_heure < date'2025-07-01' "
    "AND libelle_region IN "
    "('Bretagne','Occitanie','Hauts-de-France')"
)

MIN_SIZE = 1_000_000
MAX_SIZE = 5_000_000


def download_dataset(output: Path) -> None:
    """Download and validate the raw RTE dataset."""

    params = {
        "select": ",".join(COLUMNS),
        "where": DATE_FILTER,
    }

    url = f"{API_URL}?{urlencode(params)}"

    print("=== ENERFLOW DATA EXTRACTION ===")
    print("Source: RTE Open Data")
    print("Period: January - June 2025")
    print("Regions: Bretagne, Occitanie, Hauts-de-France")

    request = Request(
        url,
        headers={"User-Agent": "EnerFlow/1.0"},
    )

    try:
        with urlopen(request, timeout=120) as response:
            data = response.read()
    except HTTPError as error:
        raise SystemExit(
            f"HTTP error {error.code}: "
            f"{error.read().decode('utf-8', errors='replace')}"
        ) from error
    except URLError as error:
        raise SystemExit(
            f"Connection error: {error.reason}"
        ) from error

    # Validate raw dataset size before saving
    size = len(data)

    if not MIN_SIZE <= size <= MAX_SIZE:
        raise ValueError(
            f"Dataset size {size} bytes "
            "is outside the 1-5 MB limit."
        )

    # Validate the exported CSV schema
    header = data.splitlines()[0].decode("utf-8-sig")
    expected_header = ";".join(COLUMNS)

    if header != expected_header:
        raise ValueError(
            f"Unexpected CSV header: {header}"
        )

    # Save the verified raw dataset
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)

    # Reproducibility information
    row_count = len(data.splitlines()) - 1
    checksum = hashlib.sha256(data).hexdigest()

    print("\n=== DATASET VALIDATION ===")
    print(f"File: {output}")
    print(f"Size: {size} bytes")
    print(f"Observations: {row_count}")
    print(f"Columns: {len(COLUMNS)}")
    print(f"SHA-256: {checksum}")
    print("Status: SUCCESS")


if __name__ == "__main__":
    destination = Path(
        sys.argv[1]
        if len(sys.argv) > 1
        else "data/raw/rte_energy.csv"
    )

    download_dataset(destination)

#!/usr/bin/env bash
set -euo pipefail

OUTPUT="${1:-data/raw/rte_energy.csv}"
mkdir -p "$(dirname "$OUTPUT")"

API="https://odre.opendatasoft.com/api/explore/v2.1/catalog/datasets/eco2mix-regional-cons-def/exports/csv"

curl --fail --show-error --location --get \
  "$API" \
  --data-urlencode "select=code_insee_region,libelle_region,date,heure,date_heure,consommation,eolien,solaire,hydraulique,bioenergies,ech_physiques" \
  --data-urlencode "where=date_heure >= date'2025-01-01' AND date_heure < date'2025-07-01' AND libelle_region IN ('Bretagne','Occitanie','Hauts-de-France')" \
  -o "$OUTPUT"

SIZE=$(wc -c < "$OUTPUT")

if (( SIZE < 1000000 || SIZE > 5000000 )); then
  echo "ERROR: Dataset outside the 1-5 MB limit."
  exit 1
fi

echo "=== DATASET ==="
echo "File: $OUTPUT"
echo "Size: $SIZE bytes"
echo "Rows including header: $(wc -l < "$OUTPUT")"
echo "SHA-256:"
sha256sum "$OUTPUT"

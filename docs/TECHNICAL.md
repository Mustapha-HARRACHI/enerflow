# Technical notes and model card

## Scope and availability

The analytical unit is a region and a UTC day. The data pipeline starts from RTE's public CSV export, retains its local date/time fields for audit, and uses the UTC timestamp to form daily aggregates. The daylight-saving transition produces six source records at local times that did not exist in 2025; these are excluded in Silver, logged in `silver_quality.json`, and independently excluded in the Decimal cross-check. The pipeline fails on duplicate cleaned region/timestamp keys, incomplete days, unexpected regions, missing Gold data, and missing measurements. The raw CSV and processed Parquet remain local because `data/` is Git-ignored.

The three regional renewable coverage ratios from the independently checked Gold output are Occitanie **64.10%**, Hauts-de-France **27.42%**, and Bretagne **25.49%** for the six-month period. These are ratios of summed generation to summed demand, not physical tracing of electricity use. Renewable production is omitted from demand forecasting because its future realized value would not be available at forecast time.

## Forecast protocol

For target day `t`, features use demand at `t-1`, `t-2`, `t-7`, `t-14`, averages of the preceding 7 and 14 observed days, weekday/month sine and cosine terms, and region indicators. The reference predicts `demand(t-7)`. No target-day consumption, generation, or physical exchange enters the features. `StandardScaler` is fitted within the training partition via a scikit-learn pipeline. Negative Ridge outputs would be clipped to zero.

Training targets run from **15 January through 30 April 2025** (318 region-days after the 14-day warm-up). Validation is **1–31 May** (93 region-days). Ridge `alpha` is selected from `0.1, 10, 100, 1000` by validation MAE; the selected value is `100`. The model is then refitted on training plus validation targets. The untouched test interval is **1–30 June** (90 region-days). The source records are chronological; every test day's lag uses actual prior-day observations. This is a sequence of one-day-ahead forecasts, not a 30-day recursive forecast.

MAE and RMSE are in MWh per region-day. WAPE is `sum(abs(actual - prediction)) / sum(actual) × 100`. These metrics are descriptive for this fixed period; no confidence interval or significance claim is made with only three related time series.

## Measured errors

| Region | Weekly MAE (MWh) | Ridge MAE (MWh) | Ridge WAPE |
|---|---:|---:|---:|
| Bretagne | 1,402.20 | 2,476.26 | 5.13% |
| Hauts-de-France | 3,146.57 | 4,330.70 | 3.91% |
| Occitanie | 5,978.62 | 6,088.50 | 6.69% |

The June chart shows that the Ridge prediction is smoother than observed consumption. The model misses several abrupt changes and trends low in Occitanie late in the month. Those are observations from the plotted test values, not proven causal explanations. The ten largest absolute Ridge errors are listed in the HTML report; all 90 rows are in CSV. The validation advantage did not persist on test, so this experiment supports retaining the weekly reference until a longer evaluation shows a robust gain.

## Reproducibility and review

The original local raw SHA-256 is in the README. The 2026-11-22 fresh RTE export had a different byte hash but the same 26,070 row multiset, confirming order variance in the export. Fixed split dates and candidate `alpha` values live in `config/experiment.json`. Running `src/06_forecast.py evaluate` overwrites only generated `reports/` outputs. The script's `predict` command reads an evaluated test row for demonstration; it does not claim to serve future, unobserved dates. `pytest` checks actual Gold coverage and partition sizes, unknown-region rejection, and that changing a target value cannot change that day's features or weekly reference.

Potential future improvements should be assessed with additional out-of-time windows, and access to weather **forecasts** at the correct issue time. Testing new approaches against this same June holdout repeatedly would invalidate its status as an untouched final test.

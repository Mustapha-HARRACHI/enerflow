"""Evaluate a predeclared time split and render a browsable demand report."""

import argparse
import csv
import html
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from forecasting import (CONFIG, REGIONS, TRAIN_END, VALID_END, TEST_END, load_daily,
                         make_rows, partition, fit_model, predict, metrics)

GOLD = Path("data/processed/gold/regional_daily.parquet")
OUT = Path("reports")
ALPHAS = tuple(CONFIG["ridge_alphas"])


def run() -> dict:
    rows = make_rows(load_daily(GOLD))
    train, valid, test = (partition(rows, name) for name in ("train", "validation", "test"))
    x_valid = np.array([r["actual_mwh"] for r in valid])
    candidates = []
    for alpha in ALPHAS:
        model = fit_model(train, alpha)
        candidates.append((metrics(x_valid, predict(model, valid))["mae_mwh"], alpha))
    _, selected_alpha = min(candidates)
    model = fit_model(train + valid, selected_alpha)
    actual = np.array([r["actual_mwh"] for r in test])
    baseline = np.array([r["baseline_mwh"] for r in test])
    improved = predict(model, test)
    report = {
        "question": "Can a causal lag model improve next-day regional demand forecasts over a weekly seasonal naive reference?",
        "unit": "MWh per UTC day", "train_end": str(TRAIN_END),
        "validation_end": str(VALID_END), "test_end": str(TEST_END),
        "counts": {"train": len(train), "validation": len(valid), "test": len(test)},
        "selection": {"metric": "validation MAE (MWh)", "candidates":
                      [{"alpha": alpha, "mae_mwh": score} for score, alpha in candidates],
                      "selected_alpha": selected_alpha,
                      "weekly_naive_mae_mwh": metrics(x_valid, np.array([r["baseline_mwh"] for r in valid]))["mae_mwh"]},
        "test": {"weekly_naive": metrics(actual, baseline), "ridge_lags": metrics(actual, improved)},
        "by_region": {},
    }
    for region in REGIONS:
        ids = np.array([r["region"] == region for r in test])
        report["by_region"][region] = {
            "weekly_naive": metrics(actual[ids], baseline[ids]),
            "ridge_lags": metrics(actual[ids], improved[ids]),
        }
    OUT.mkdir(exist_ok=True)
    (OUT / "metrics.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    records = []
    for row, naive, ridge in zip(test, baseline, improved):
        records.append({"date_utc": str(row["date"]), "region": row["region"],
                        "actual_mwh": row["actual_mwh"], "weekly_naive_mwh": float(naive),
                        "ridge_lags_mwh": float(ridge),
                        "ridge_abs_error_mwh": abs(row["actual_mwh"] - float(ridge))})
    with (OUT / "test_predictions.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=records[0].keys(), lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)
    make_chart(records)
    make_html(report, records)
    return report


def make_chart(records: list[dict]) -> None:
    fig, axes = plt.subplots(3, 1, figsize=(11, 8), sharex=True, constrained_layout=True)
    colors = {"actual_mwh": "#111827", "weekly_naive_mwh": "#b45309", "ridge_lags_mwh": "#0e7490"}
    for ax, region in zip(axes, REGIONS):
        subset = [r for r in records if r["region"] == region]
        for key, label in (("actual_mwh", "Observed"), ("weekly_naive_mwh", "Weekly naive"),
                           ("ridge_lags_mwh", "Ridge lags")):
            ax.plot([r["date_utc"][-2:] for r in subset], [r[key] for r in subset],
                    color=colors[key], label=label, linewidth=1.7 if key == "actual_mwh" else 1.2)
        ax.set_title(region, loc="left", fontsize=11, fontweight="bold")
        ax.set_ylabel("MWh / UTC day")
        ax.grid(alpha=0.2)
    axes[0].legend(ncol=3, frameon=False, loc="upper right")
    axes[-1].set_xlabel("June 2025")
    fig.suptitle("Next-day regional demand: held-out test", fontsize=15, fontweight="bold")
    fig.savefig(OUT / "test_forecasts.png", dpi=150)
    plt.close(fig)


def make_html(report: dict, records: list[dict]) -> None:
    hardest = sorted(records, key=lambda r: r["ridge_abs_error_mwh"], reverse=True)[:10]
    cards = "".join(
        f"<tr><td>{html.escape(region)}</td><td>{values['weekly_naive']['mae_mwh']:,.0f}</td>"
        f"<td>{values['ridge_lags']['mae_mwh']:,.0f}</td>"
        f"<td>{values['ridge_lags']['wape_pct']:.2f}%</td></tr>"
        for region, values in report["by_region"].items())
    errors = "".join(
        f"<tr><td>{r['date_utc']}</td><td>{html.escape(r['region'])}</td>"
        f"<td>{r['actual_mwh']:,.0f}</td><td>{r['ridge_lags_mwh']:,.0f}</td>"
        f"<td>{r['ridge_abs_error_mwh']:,.0f}</td></tr>" for r in hardest)
    content = f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>EnerFlow | June 2025 demand forecast</title><style>body{{font:16px/1.55 system-ui,sans-serif;max-width:1100px;margin:auto;padding:2rem;color:#172033;background:#f7fafc}}h1{{font-size:2.2rem}}.hero{{background:#10324a;color:white;padding:2rem;border-radius:14px}}.hero p{{max-width:65ch}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:1rem;margin:1.4rem 0}}.metric{{background:white;padding:1rem;border-radius:10px;border:1px solid #d9e4ea}}.metric strong{{display:block;font-size:1.7rem;color:#0e7490}}section{{background:white;padding:1.5rem;margin:1.5rem 0;border-radius:12px;border:1px solid #d9e4ea}}img{{width:100%;height:auto}}table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}}th,td{{text-align:left;padding:.65rem;border-bottom:1px solid #ddd}}th{{background:#eef5f8}}.scroll{{overflow-x:auto}}small{{color:#486172}}</style>
<div class="hero"><h1>EnerFlow</h1><p>One-day-ahead electricity demand for Bretagne, Hauts-de-France and Occitanie. Evaluated on 90 unseen region-days in June 2025.</p></div>
<div class="grid"><div class="metric">Weekly naive MAE<strong>{report['test']['weekly_naive']['mae_mwh']:,.0f} MWh</strong></div><div class="metric">Ridge lag MAE<strong>{report['test']['ridge_lags']['mae_mwh']:,.0f} MWh</strong></div><div class="metric">Ridge WAPE<strong>{report['test']['ridge_lags']['wape_pct']:.2f}%</strong></div></div>
<section><h2>Observed vs forecast</h2><img src="test_forecasts.png" alt="Observed and forecast daily consumption for each region in June 2025"><p><small>Features use prior consumption and calendar only. Each test forecast assumes the previous day's actual consumption is available.</small></p></section>
<section><h2>Errors by region</h2><div class="scroll"><table><thead><tr><th>Region</th><th>Naive MAE (MWh)</th><th>Ridge MAE (MWh)</th><th>Ridge WAPE</th></tr></thead><tbody>{cards}</tbody></table></div></section>
<section><h2>Largest Ridge misses</h2><div class="scroll"><table><thead><tr><th>UTC date</th><th>Region</th><th>Actual (MWh)</th><th>Forecast (MWh)</th><th>Absolute error (MWh)</th></tr></thead><tbody>{errors}</tbody></table></div><p><small>These are diagnostic cases, not a filtered evaluation sample.</small></p></section>
<section><h2>Provenance & method</h2><p>RTE / ODRÉ éCO2mix regional consolidated and definitive observations, January–June 2025. Licence Ouverte 2.0. Source: <a href="https://odre.opendatasoft.com/explore/dataset/eco2mix-regional-cons-def/">official dataset</a>.</p><p>Training: through April 30; Ridge regularization selected by May MAE; refit through May 31; June held out. Daily UTC totals approximate MWh from 30-minute MW values. The result is a retrospective one-day-ahead backtest, not an operational live forecast.</p><p><a href="test_predictions.csv">Download all test predictions</a> · <a href="metrics.json">Download metrics</a></p></section></html>"""
    (OUT / "index.html").write_text(content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=("evaluate", "predict"), default="evaluate")
    parser.add_argument("--region", choices=REGIONS)
    parser.add_argument("--date", help="UTC date in June 2025 (YYYY-MM-DD)")
    args = parser.parse_args()
    if args.command == "evaluate":
        print(json.dumps(run(), indent=2))
        return
    if not args.region or not args.date:
        parser.error("predict requires --region and --date")
    path = OUT / "test_predictions.csv"
    if not path.is_file():
        parser.error(f"Missing {path}; run evaluate first")
    with path.open(newline="", encoding="utf-8") as fh:
        matches = [r for r in csv.DictReader(fh) if r["region"] == args.region and r["date_utc"] == args.date]
    if not matches:
        parser.error("No held-out prediction for that region/date")
    print(json.dumps(matches[0], indent=2))


if __name__ == "__main__":
    main()

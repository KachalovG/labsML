from pathlib import Path
import json

import joblib
import pandas as pd
import matplotlib.pyplot as plt

from data.data_processing import prepare_data


ASSETS_DIR = Path("report_assets")
SAVE_DIR = Path("models/save_models")


def main():
    ASSETS_DIR.mkdir(exist_ok=True)

    df = prepare_data("data/inflation_long_format.csv")
    type_cols = [col for col in df.columns if col.startswith("type_")]
    df["inflation_type"] = (
        df[type_cols]
        .idxmax(axis=1)
        .str.replace("type_", "", regex=False)
    )

    metrics = pd.read_csv(SAVE_DIR / "model_metrics.csv")
    seasonality = pd.read_csv(SAVE_DIR / "seasonality.csv")
    predictions = pd.read_csv(SAVE_DIR / "predictions.csv")
    future = pd.read_csv(SAVE_DIR / "future_forecast.csv")

    plt.style.use("seaborn-v0_8-whitegrid")
    plt.rcParams["font.family"] = "DejaVu Sans"

    fig, axes = plt.subplots(2, 1, figsize=(13, 8), sharex=False)
    for inflation_type, part in df.groupby("inflation_type"):
        axes[0].plot(part["date"], part["target"], label=inflation_type, linewidth=1.1)
    axes[0].set_title("Monthly inflation by category, full period")
    axes[0].set_ylabel("target = idx - 100")
    axes[0].legend(ncol=4)

    recent = df[df["date"] >= "2016-01-01"]
    for inflation_type, part in recent.groupby("inflation_type"):
        axes[1].plot(part["date"], part["target"], label=inflation_type, linewidth=1.3)
    axes[1].set_title("Monthly inflation by category, recent period")
    axes[1].set_ylabel("target = idx - 100")
    axes[1].legend(ncol=4)

    plt.tight_layout()
    fig.savefig(ASSETS_DIR / "time_series.png", dpi=160, bbox_inches="tight")
    plt.close(fig)

    seasonality_total = seasonality[seasonality["inflation_type"] == "total"]
    fig, ax = plt.subplots(figsize=(11, 4.8))
    ax.plot(
        seasonality_total["month_num"],
        seasonality_total["seasonality_by_year_method"],
        marker="o",
        label="Year-average method"
    )
    ax.plot(
        seasonality_total["month_num"],
        seasonality_total["seasonality_pivot_method"],
        marker="s",
        label="Pivot-table method"
    )
    ax.axhline(1, color="black", linewidth=1, linestyle="--")
    ax.set_title("Seasonality profile for total inflation")
    ax.set_xlabel("Month")
    ax.set_ylabel("Seasonality coefficient")
    ax.set_xticks(range(1, 13))
    ax.legend()
    fig.savefig(ASSETS_DIR / "seasonality.png", dpi=160, bbox_inches="tight")
    plt.close(fig)

    test_metrics = metrics[metrics["dataset"] == "test_2023_2024"].sort_values("mae")
    fig, ax = plt.subplots(figsize=(11, 4.8))
    ax.bar(test_metrics["model"], test_metrics["mae"])
    ax.set_title("Model comparison on test 2023-2024 by MAE")
    ax.set_ylabel("MAE")
    ax.tick_params(axis="x", rotation=30)
    fig.savefig(ASSETS_DIR / "test_mae.png", dpi=160, bbox_inches="tight")
    plt.close(fig)

    features = json.load(open(SAVE_DIR / "features.json", encoding="utf-8"))
    best_model = features["best_model"]
    best_predictions = predictions[
        (predictions["model"] == best_model) &
        (predictions["inflation_type"] == "total") &
        (predictions["dataset"].isin(["test_2023_2024", "holdout_2025", "recent_actual"]))
    ].copy()
    best_predictions["date"] = pd.to_datetime(best_predictions["date"])

    fig, ax = plt.subplots(figsize=(12, 4.8))
    ax.plot(best_predictions["date"], best_predictions["true_target"], marker="o", label="Actual")
    ax.plot(best_predictions["date"], best_predictions["pred_target"], marker="s", label=f"Forecast: {best_model}")
    ax.set_title("Actual vs forecast for total inflation")
    ax.set_ylabel("target = idx - 100")
    ax.legend()
    fig.savefig(ASSETS_DIR / "actual_vs_pred.png", dpi=160, bbox_inches="tight")
    plt.close(fig)

    future["date"] = pd.to_datetime(future["date"])
    future_total = future[future["inflation_type"] == "total"]

    fig, ax = plt.subplots(figsize=(11, 4.8))
    ax.plot(future_total["date"], future_total["pred_target"], marker="o")
    ax.set_title("Final 12-month forecast for total inflation")
    ax.set_ylabel("Forecast target = idx - 100")
    fig.savefig(ASSETS_DIR / "future_forecast.png", dpi=160, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 4.8))
    ax.hist(df["target"], bins=50, color="#4C78A8", edgecolor="white")
    ax.set_title("Target distribution: monthly inflation")
    ax.set_xlabel("target = idx - 100")
    ax.set_ylabel("Frequency")
    fig.savefig(ASSETS_DIR / "target_distribution.png", dpi=160, bbox_inches="tight")
    plt.close(fig)

    model = joblib.load(SAVE_DIR / "best_model.pkl")
    if hasattr(model, "feature_importances_"):
        feature_importance = (
            pd.DataFrame({
                "feature": features["feature_cols"],
                "importance": model.feature_importances_
            })
            .sort_values("importance", ascending=False)
            .head(12)
            .sort_values("importance")
        )

        fig, ax = plt.subplots(figsize=(10, 5.2))
        ax.barh(feature_importance["feature"], feature_importance["importance"], color="#59A14F")
        ax.set_title("Top feature importances for Gradient Boosting")
        ax.set_xlabel("Importance")
        fig.savefig(ASSETS_DIR / "feature_importance.png", dpi=160, bbox_inches="tight")
        plt.close(fig)

    print("Report images rebuilt")


if __name__ == "__main__":
    main()

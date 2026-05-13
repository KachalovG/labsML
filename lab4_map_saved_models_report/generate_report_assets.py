from __future__ import annotations

import json
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

import saved_model_pipeline


PROJECT_DIR = Path(__file__).resolve().parent
BASE_DIR = PROJECT_DIR.parent
PLOTS_DIR = PROJECT_DIR / "plots"
OUTPUTS_DIR = PROJECT_DIR / "outputs"

RAW_PATH = BASE_DIR / "data" / "train.csv"
PROCESSED_PATH = BASE_DIR / "data" / "train_processed.csv"
SCALER_PATH = BASE_DIR / "models" / "scaler.pkl"
SAVE_MODELS_DIR = BASE_DIR / "save_models"


class MLP(nn.Module):
    def __init__(self, input_size: int):
        super().__init__()
        self.network = nn.Sequential(
            nn.Linear(input_size, 128),
            nn.ReLU(),
            nn.BatchNorm1d(128),
            nn.Dropout(0.2),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.BatchNorm1d(64),
            nn.Dropout(0.1),
            nn.Linear(64, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.network(x)


def load_checkpoint(path: Path) -> dict:
    try:
        return torch.load(path, map_location="cpu", weights_only=False)
    except TypeError:
        return torch.load(path, map_location="cpu")


def mape(y_true: pd.Series, y_pred: np.ndarray) -> float:
    actual = np.asarray(y_true)
    pred = np.asarray(y_pred)
    mask = actual != 0
    return float(np.mean(np.abs((actual[mask] - pred[mask]) / actual[mask])) * 100)


def smape(y_true: pd.Series, y_pred: np.ndarray) -> float:
    actual = np.asarray(y_true)
    pred = np.asarray(y_pred)
    denominator = (np.abs(actual) + np.abs(pred)) / 2
    mask = denominator != 0
    return float(np.mean(np.abs(actual[mask] - pred[mask]) / denominator[mask]) * 100)


def metric_row(name: str, y_true: pd.Series, y_pred: np.ndarray) -> dict:
    mse = mean_squared_error(y_true, y_pred)
    return {
        "model": name,
        "MAE": float(mean_absolute_error(y_true, y_pred)),
        "MSE": float(mse),
        "RMSE": float(np.sqrt(mse)),
        "R2": float(r2_score(y_true, y_pred)),
        "MAPE": mape(y_true, y_pred),
        "SMAPE": smape(y_true, y_pred),
    }


def evaluate_saved_models(processed: pd.DataFrame) -> pd.DataFrame:
    target_col = processed.columns[10]
    X = processed.drop(columns=[target_col])
    y = processed[target_col]
    _, X_test, _, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    scaler_pack = joblib.load(SCALER_PATH)
    X_test_scaled = X_test.copy()
    numeric_cols = scaler_pack["numeric_cols"]
    X_test_scaled[numeric_cols] = scaler_pack["scaler"].transform(X_test[numeric_cols])

    rows: list[dict] = []

    linear_model = joblib.load(SAVE_MODELS_DIR / "linear_regression.pkl")
    rows.append(metric_row("LinearRegression", y_test, linear_model.predict(X_test_scaled)))

    rf_model = joblib.load(SAVE_MODELS_DIR / "random_forest.pkl")
    rf_cols = list(getattr(rf_model, "feature_names_in_", X_test.columns))
    rows.append(metric_row("RandomForestRegressor", y_test, rf_model.predict(X_test[rf_cols])))

    checkpoint = load_checkpoint(SAVE_MODELS_DIR / "torch_mlp.pth")
    feature_names = list(checkpoint["feature_names"])
    mlp_model = MLP(input_size=int(checkpoint["input_size"]))
    mlp_model.load_state_dict(checkpoint["model_state_dict"])
    mlp_model.eval()

    with torch.no_grad():
        pred_log = mlp_model(
            torch.tensor(X_test_scaled[feature_names].to_numpy(), dtype=torch.float32)
        ).numpy().ravel()
    mlp_pred = np.expm1(pred_log) if checkpoint.get("target_transform") == "log1p" else pred_log
    rows.append(metric_row("TorchMLP", y_test, mlp_pred))

    metrics = pd.DataFrame(rows).sort_values("MAPE").reset_index(drop=True)
    metrics.to_csv(OUTPUTS_DIR / "metrics_saved_models.csv", index=False, encoding="utf-8-sig")
    return metrics


def setup_plot_style() -> None:
    plt.style.use("seaborn-v0_8-whitegrid")
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "#fbfbfd",
            "axes.edgecolor": "#d7dbe7",
            "axes.labelcolor": "#1f2937",
            "xtick.color": "#374151",
            "ytick.color": "#374151",
            "font.size": 10,
        }
    )


def save_target_distribution(raw: pd.DataFrame) -> str:
    target = raw.columns[-1]
    values = raw[target] / 1_000_000
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.hist(values, bins=70, color="#2563eb", alpha=0.86, edgecolor="white")
    ax.axvline(values.median(), color="#111827", linewidth=2, label=f"Median: {values.median():.1f}M")
    ax.set_title("RTO distribution in historical data", fontsize=15, weight="bold", pad=14)
    ax.set_xlabel("RTO, million")
    ax.set_ylabel("Observations")
    ax.legend(frameon=True)
    fig.tight_layout()
    path = PLOTS_DIR / "eda_target_distribution.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return str(path)


def save_monthly_history(raw: pd.DataFrame) -> str:
    month_col = raw.columns[1]
    target_col = raw.columns[-1]
    month_total = raw.groupby(month_col)[target_col].sum().sort_index() / 1_000_000_000
    month_mean = raw.groupby(month_col)[target_col].mean().sort_index() / 1_000_000

    fig, ax1 = plt.subplots(figsize=(10, 6))
    ax1.plot(month_total.index, month_total.values, marker="o", linewidth=2.5, color="#0f766e")
    ax1.set_xlabel("Month")
    ax1.set_ylabel("Total RTO, billion", color="#0f766e")
    ax1.tick_params(axis="y", labelcolor="#0f766e")
    ax1.set_xticks(month_total.index)

    ax2 = ax1.twinx()
    ax2.plot(month_mean.index, month_mean.values, marker="s", linewidth=2, color="#b45309")
    ax2.set_ylabel("Average store RTO, million", color="#b45309")
    ax2.tick_params(axis="y", labelcolor="#b45309")

    ax1.set_title("Historical RTO dynamics by month", fontsize=15, weight="bold", pad=14)
    fig.tight_layout()
    path = PLOTS_DIR / "eda_monthly_history.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return str(path)


def save_correlation_heatmap(processed: pd.DataFrame) -> str:
    idx = [10, 11, 12, 13, 14, 15, 2, 4, 9, 0, 1, 84, 85]
    labels = [
        "RTO",
        "Lag 1",
        "Lag 2",
        "Avg 3m",
        "Growth",
        "Store avg",
        "Population",
        "Foot traffic",
        "Cash registers",
        "Opening age",
        "Area size",
        "Month sin",
        "Month cos",
    ]
    corr = processed.iloc[:, idx].corr()

    fig, ax = plt.subplots(figsize=(9, 8))
    im = ax.imshow(corr.values, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(labels)))
    ax.set_yticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_yticklabels(labels)
    for i in range(len(labels)):
        for j in range(len(labels)):
            value = corr.values[i, j]
            ax.text(j, i, f"{value:.2f}", ha="center", va="center", fontsize=7, color="#111827")
    ax.set_title("Correlation heatmap for selected features", fontsize=15, weight="bold", pad=14)
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    path = PLOTS_DIR / "eda_correlation_heatmap.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return str(path)


def save_category_profile(raw: pd.DataFrame) -> str:
    open_col = raw.columns[2]
    area_col = raw.columns[3]
    target_col = raw.columns[-1]
    open_avg = raw.groupby(open_col)[target_col].mean().sort_values() / 1_000_000
    area_avg = raw.groupby(area_col)[target_col].mean().sort_values() / 1_000_000

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    axes[0].barh(open_avg.index.astype(str), open_avg.values, color="#7c3aed", alpha=0.9)
    axes[0].set_title("Opening-age category")
    axes[0].set_xlabel("Average RTO, million")
    axes[1].barh(area_avg.index.astype(str), area_avg.values, color="#0f9f6e", alpha=0.9)
    axes[1].set_title("Trading-area category")
    axes[1].set_xlabel("Average RTO, million")
    fig.suptitle("Average RTO by categorical store profile", fontsize=15, weight="bold")
    fig.tight_layout()
    path = PLOTS_DIR / "eda_category_profile.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return str(path)


def save_metrics_plot(metrics: pd.DataFrame) -> str:
    ordered = metrics.sort_values("MAPE")
    x = np.arange(len(ordered))
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    axes[0].bar(x, ordered["MAPE"], color="#2563eb", alpha=0.9)
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(ordered["model"], rotation=20, ha="right")
    axes[0].set_ylabel("MAPE, %")
    axes[0].set_title("Relative error")
    for pos, value in zip(x, ordered["MAPE"]):
        axes[0].text(pos, value + 0.05, f"{value:.2f}%", ha="center", fontsize=9)

    rmse_m = ordered["RMSE"] / 1_000_000
    axes[1].bar(x, rmse_m, color="#dc2626", alpha=0.84)
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(ordered["model"], rotation=20, ha="right")
    axes[1].set_ylabel("RMSE, million")
    axes[1].set_title("Absolute error scale")
    for pos, value in zip(x, rmse_m):
        axes[1].text(pos, value + 0.03, f"{value:.2f}", ha="center", fontsize=9)

    fig.suptitle("Saved model quality on holdout sample", fontsize=15, weight="bold")
    fig.tight_layout()
    path = PLOTS_DIR / "model_metrics_comparison.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return str(path)


def save_rf_feature_importance(processed: pd.DataFrame) -> tuple[str, list[dict]]:
    target_col = processed.columns[10]
    X = processed.drop(columns=[target_col])
    model = joblib.load(SAVE_MODELS_DIR / "random_forest.pkl")
    names = list(getattr(model, "feature_names_in_", X.columns))
    importances = pd.DataFrame({"feature": names, "importance": model.feature_importances_})
    top = importances.sort_values("importance", ascending=False).head(15).sort_values("importance")

    fig, ax = plt.subplots(figsize=(10, 7))
    ax.barh(top["feature"], top["importance"], color="#0f766e", alpha=0.9)
    ax.set_title("Top Random Forest feature importances", fontsize=15, weight="bold", pad=14)
    ax.set_xlabel("Importance")
    fig.tight_layout()
    path = PLOTS_DIR / "feature_importance_random_forest.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return str(path), importances.sort_values("importance", ascending=False).head(10).to_dict("records")


def build_stats(raw: pd.DataFrame, processed: pd.DataFrame, metrics: pd.DataFrame, top_features: list[dict]) -> dict:
    target_col = raw.columns[-1]
    region_col = raw.columns[5]
    month_col = raw.columns[1]
    categorical_cols = list(raw.select_dtypes(include=["object"]).columns)
    numeric_cols = [col for col in raw.columns if col not in categorical_cols]

    q1 = raw[target_col].quantile(0.25)
    q3 = raw[target_col].quantile(0.75)
    iqr = q3 - q1
    outlier_mask = (raw[target_col] < q1 - 1.5 * iqr) | (raw[target_col] > q3 + 1.5 * iqr)

    corr_cols = processed.iloc[:, [10, 11, 12, 13, 14, 15, 2, 4, 9]].corr().iloc[0].dropna()
    top_corr = (
        corr_cols.drop(processed.columns[10], errors="ignore")
        .abs()
        .sort_values(ascending=False)
        .head(5)
        .to_dict()
    )

    summary_path = OUTPUTS_DIR / "summary.json"
    submission_summary = json.loads(summary_path.read_text(encoding="utf-8"))

    best = metrics.sort_values("MAPE").iloc[0].to_dict()

    return {
        "raw_rows": int(raw.shape[0]),
        "raw_cols": int(raw.shape[1]),
        "processed_rows": int(processed.shape[0]),
        "processed_cols": int(processed.shape[1]),
        "store_count": int(raw[raw.columns[0]].nunique()),
        "month_count": int(raw[month_col].nunique()),
        "month_min": int(raw[month_col].min()),
        "month_max": int(raw[month_col].max()),
        "region_count": int(raw[region_col].nunique()),
        "categorical_feature_count_raw": int(len(categorical_cols)),
        "numeric_feature_count_raw": int(len(numeric_cols) - 1),
        "missing_raw": int(raw.isna().sum().sum()),
        "missing_processed": int(processed.isna().sum().sum()),
        "target_min": float(raw[target_col].min()),
        "target_q1": float(q1),
        "target_median": float(raw[target_col].median()),
        "target_mean": float(raw[target_col].mean()),
        "target_q3": float(q3),
        "target_max": float(raw[target_col].max()),
        "target_outliers_iqr": int(outlier_mask.sum()),
        "target_outliers_iqr_share": float(outlier_mask.mean() * 100),
        "top_correlations_abs": top_corr,
        "best_model": best,
        "submission_summary": submission_summary,
        "top_features": top_features,
        "code_url": "https://github.com/KachalovG/labsML/tree/main/lab4_map_saved_models_report",
        "script_url": "https://github.com/KachalovG/labsML/blob/main/lab4_map_saved_models_report/saved_model_pipeline.py",
    }


def main() -> None:
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)

    saved_model_pipeline.main()

    setup_plot_style()
    raw = pd.read_csv(RAW_PATH)
    processed = pd.read_csv(PROCESSED_PATH)
    metrics = evaluate_saved_models(processed)

    extra_plots = [
        save_target_distribution(raw),
        save_monthly_history(raw),
        save_correlation_heatmap(processed),
        save_category_profile(raw),
        save_metrics_plot(metrics),
    ]
    feature_plot, top_features = save_rf_feature_importance(processed)
    extra_plots.append(feature_plot)

    stats = build_stats(raw, processed, metrics, top_features)
    stats["extra_plots"] = extra_plots
    (OUTPUTS_DIR / "report_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"metrics": metrics.to_dict("records"), "stats": stats}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

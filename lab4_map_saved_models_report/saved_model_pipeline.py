from __future__ import annotations

import json
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
import torch.nn as nn


BASE_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = Path(__file__).resolve().parent
OUT_DIR = PROJECT_DIR / "outputs"
PLOTS_DIR = PROJECT_DIR / "plots"

TRAIN_PATH = BASE_DIR / "data" / "train.csv"
SAVE_MODELS_DIR = BASE_DIR / "save_models"
SCALER_PATH = BASE_DIR / "models" / "scaler.pkl"

FORECAST_MONTH = 11
EXPECTED_ROWS = 20615


OPEN_MAP = {
    "\u041d\u043e\u0432\u044b\u0439": 1,
    "\u0421\u0440\u0435\u0434\u043d\u0438\u0439 \u043f\u043e \u0432\u043e\u0437\u0440\u0430\u0441\u0442\u0443": 2,
    "\u041e\u0442\u043a\u0440\u044b\u0442 \u0434\u0430\u0432\u043d\u043e": 3,
}

AREA_MAP = {
    "\u041c\u0430\u043b\u0435\u043d\u044c\u043a\u0438\u0439": 1,
    "\u0421\u0440\u0435\u0434\u043d\u0438\u0439": 2,
    "\u0411\u043e\u043b\u044c\u0448\u043e\u0439": 3,
    "\u041e\u0447\u0435\u043d\u044c \u0431\u043e\u043b\u044c\u0448\u043e\u0439": 4,
}


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


def load_torch_checkpoint(path: Path) -> dict:
    try:
        return torch.load(path, map_location="cpu", weights_only=False)
    except TypeError:
        return torch.load(path, map_location="cpu")


def build_feature_frame(raw: pd.DataFrame, feature_names: list[str]) -> tuple[pd.Series, pd.DataFrame, pd.DataFrame]:
    id_col = raw.columns[0]
    month_col = raw.columns[1]
    open_col = raw.columns[2]
    area_col = raw.columns[3]
    region_col = raw.columns[5]
    target_col = raw.columns[-1]

    sorted_raw = raw.sort_values([id_col, month_col]).reset_index(drop=True)
    last_month = int(sorted_raw[month_col].max())
    if FORECAST_MONTH != last_month + 1:
        raise ValueError(f"Expected to forecast month {last_month + 1}, got {FORECAST_MONTH}.")

    last_rows = (
        sorted_raw.groupby(id_col, sort=True)
        .tail(1)
        .sort_values(id_col)
        .reset_index(drop=True)
    )
    ids = last_rows[id_col].astype(int)

    pivot = sorted_raw.pivot(index=id_col, columns=month_col, values=target_col).sort_index()
    required_months = [last_month - 2, last_month - 1, last_month]
    missing_months = [month for month in required_months if month not in pivot.columns]
    if missing_months:
        raise ValueError(f"Missing history months needed for lags: {missing_months}.")

    lag1 = pivot[last_month]
    lag2 = pivot[last_month - 1]
    avg3 = pivot[required_months].mean(axis=1)
    growth = (lag1 - lag2) / lag2.replace(0, np.nan)
    avg_all = pivot.loc[:, pivot.columns <= last_month].mean(axis=1)

    features = pd.DataFrame(index=last_rows.index)
    for col in feature_names[:10]:
        features[col] = last_rows[col].to_numpy()

    features[open_col] = features[open_col].map(OPEN_MAP)
    features[area_col] = features[area_col].map(AREA_MAP)

    lag_columns = feature_names[10:15]
    aligned_lags = pd.DataFrame(
        {
            lag_columns[0]: lag1.reindex(ids).to_numpy(),
            lag_columns[1]: lag2.reindex(ids).to_numpy(),
            lag_columns[2]: avg3.reindex(ids).to_numpy(),
            lag_columns[3]: growth.reindex(ids).to_numpy(),
            lag_columns[4]: avg_all.reindex(ids).to_numpy(),
        },
        index=features.index,
    )
    features = pd.concat([features, aligned_lags], axis=1)

    region_prefix = region_col + "_"
    region_columns = [col for col in feature_names if col.startswith(region_prefix)]
    for col in region_columns:
        region_value = col.removeprefix(region_prefix)
        features[col] = (last_rows[region_col] == region_value).astype(int).to_numpy()

    features[feature_names[-2]] = np.sin(2 * np.pi * FORECAST_MONTH / 12)
    features[feature_names[-1]] = np.cos(2 * np.pi * FORECAST_MONTH / 12)

    features = features.replace([np.inf, -np.inf], np.nan)
    missing = features.columns[features.isna().any()].tolist()
    if missing:
        raise ValueError(f"Feature frame has missing values in columns: {missing[:10]}")

    return ids, features[feature_names], last_rows


def predict_mlp(features: pd.DataFrame) -> tuple[np.ndarray, list[str]]:
    checkpoint = load_torch_checkpoint(SAVE_MODELS_DIR / "torch_mlp.pth")
    feature_names = list(checkpoint["feature_names"])
    scaler_pack = joblib.load(SCALER_PATH)

    scaled = features[feature_names].copy()
    numeric_cols = scaler_pack["numeric_cols"]
    scaled[numeric_cols] = scaler_pack["scaler"].transform(features[numeric_cols])

    model = MLP(input_size=int(checkpoint["input_size"]))
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()

    with torch.no_grad():
        pred_log = model(torch.tensor(scaled.to_numpy(), dtype=torch.float32)).numpy().ravel()

    if checkpoint.get("target_transform") == "log1p":
        predictions = np.expm1(pred_log)
    else:
        predictions = pred_log

    return np.clip(predictions, 0, None), feature_names


def predict_random_forest(features: pd.DataFrame) -> np.ndarray:
    model = joblib.load(SAVE_MODELS_DIR / "random_forest.pkl")
    model_features = list(model.feature_names_in_)
    predictions = model.predict(features[model_features])
    return np.clip(predictions, 0, None)


def save_plots(raw: pd.DataFrame, diagnostic: pd.DataFrame) -> list[str]:
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
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

    id_col = raw.columns[0]
    month_col = raw.columns[1]
    region_col = raw.columns[5]
    target_col = raw.columns[-1]

    files: list[str] = []

    fig, ax = plt.subplots(figsize=(10, 6))
    values = diagnostic["rto_mlp"] / 1_000_000
    ax.hist(values, bins=55, color="#3662e3", alpha=0.86, edgecolor="white")
    ax.axvline(values.median(), color="#111827", linewidth=2, label=f"Median: {values.median():.1f}M")
    ax.set_title("November RTO forecast distribution", fontsize=15, weight="bold", pad=14)
    ax.set_xlabel("RTO, million")
    ax.set_ylabel("Stores")
    ax.legend(frameon=True)
    fig.tight_layout()
    path = PLOTS_DIR / "forecast_distribution.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    files.append(str(path))

    top_regions = (
        diagnostic.groupby(region_col)["rto_mlp"]
        .mean()
        .sort_values(ascending=False)
        .head(15)
        .sort_values()
        / 1_000_000
    )
    fig, ax = plt.subplots(figsize=(11, 7))
    ax.barh(top_regions.index, top_regions.values, color="#0f9f6e", alpha=0.9)
    ax.set_title("Top regions by average November forecast", fontsize=15, weight="bold", pad=14)
    ax.set_xlabel("Average RTO, million")
    ax.set_ylabel("")
    fig.tight_layout()
    path = PLOTS_DIR / "top_regions_average_forecast.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    files.append(str(path))

    history_total = raw.groupby(month_col)[target_col].sum().sort_index() / 1_000_000_000
    months = list(history_total.index) + [FORECAST_MONTH]
    totals = list(history_total.values) + [diagnostic["rto_mlp"].sum() / 1_000_000_000]
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(months, totals, marker="o", color="#7c3aed", linewidth=2.5)
    ax.scatter([FORECAST_MONTH], [totals[-1]], color="#ef4444", s=90, zorder=3, label="Forecast")
    ax.set_xticks(months)
    ax.set_title("Network total RTO: history and November forecast", fontsize=15, weight="bold", pad=14)
    ax.set_xlabel("Month")
    ax.set_ylabel("Total RTO, billion")
    ax.legend(frameon=True)
    fig.tight_layout()
    path = PLOTS_DIR / "network_total_history_forecast.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    files.append(str(path))

    oct_col = "october_rto"
    fig, ax = plt.subplots(figsize=(8, 8))
    sample = diagnostic.sample(min(7000, len(diagnostic)), random_state=42)
    x = sample[oct_col] / 1_000_000
    y = sample["rto_mlp"] / 1_000_000
    ax.scatter(x, y, s=13, alpha=0.28, color="#2563eb", edgecolors="none")
    max_value = max(float(x.max()), float(y.max()))
    ax.plot([0, max_value], [0, max_value], color="#111827", linewidth=1.4, linestyle="--")
    ax.set_title("October actual vs November forecast", fontsize=15, weight="bold", pad=14)
    ax.set_xlabel("October RTO, million")
    ax.set_ylabel("November forecast, million")
    fig.tight_layout()
    path = PLOTS_DIR / "october_vs_forecast.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    files.append(str(path))

    return files


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw = pd.read_csv(TRAIN_PATH)

    checkpoint = load_torch_checkpoint(SAVE_MODELS_DIR / "torch_mlp.pth")
    mlp_feature_names = list(checkpoint["feature_names"])
    ids, features, last_rows = build_feature_frame(raw, mlp_feature_names)

    mlp_predictions, _ = predict_mlp(features)
    rf_predictions = predict_random_forest(features)

    submission = pd.DataFrame(
        {
            "new_id": ids.to_numpy(dtype=int),
            "rto": np.round(mlp_predictions, 2),
        }
    )
    submission_path = OUT_DIR / "test.csv"
    submission.to_csv(submission_path, index=False)

    rf_submission = pd.DataFrame(
        {
            "new_id": ids.to_numpy(dtype=int),
            "rto": np.round(rf_predictions, 2),
        }
    )
    rf_submission.to_csv(OUT_DIR / "test_random_forest_backup.csv", index=False)

    id_col = raw.columns[0]
    month_col = raw.columns[1]
    region_col = raw.columns[5]
    target_col = raw.columns[-1]
    diagnostic = pd.DataFrame(
        {
            "new_id": ids.to_numpy(dtype=int),
            region_col: last_rows[region_col].to_numpy(),
            "october_rto": last_rows[target_col].to_numpy(),
            "rto_mlp": mlp_predictions,
            "rto_random_forest": rf_predictions,
        }
    )
    diagnostic["absolute_model_gap"] = np.abs(diagnostic["rto_mlp"] - diagnostic["rto_random_forest"])
    diagnostic.to_csv(OUT_DIR / "prediction_diagnostics.csv", index=False)

    plot_files = save_plots(raw, diagnostic)

    if len(submission) != EXPECTED_ROWS:
        raise ValueError(f"Submission has {len(submission)} rows, expected {EXPECTED_ROWS}.")
    if list(submission.columns) != ["new_id", "rto"]:
        raise ValueError("Submission must have exactly two columns: new_id, rto.")
    if submission_path.stat().st_size > 1_000_000:
        raise ValueError(f"Submission is too large: {submission_path.stat().st_size} bytes.")

    summary = {
        "submission": str(submission_path),
        "rows": int(len(submission)),
        "columns": list(submission.columns),
        "forecast_month": FORECAST_MONTH,
        "primary_model": "save_models/torch_mlp.pth",
        "backup_model": "save_models/random_forest.pkl",
        "preprocessing_scaler": str(SCALER_PATH),
        "rto_min": float(submission["rto"].min()),
        "rto_median": float(submission["rto"].median()),
        "rto_max": float(submission["rto"].max()),
        "rto_sum": float(submission["rto"].sum()),
        "plots": plot_files,
        "note": "No model fitting is performed by this script.",
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

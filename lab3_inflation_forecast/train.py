import json
import os
import warnings

import joblib
import numpy as np
import pandas as pd

from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import StandardScaler

from data.data_processing import prepare_data
import models.GradientBoostingRegressor as gradient_boosting_model
import models.HuberRegressor as huber_model
import models.Linear_regression as linear_model
import models.Ridge as ridge_model


# =========================
# CONFIG
# =========================

DATA_PATH = "data/inflation_long_format.csv"
SAVE_DIR = "models/save_models"

BEST_MODEL_PATH = os.path.join(SAVE_DIR, "best_model.pkl")
SCALER_PATH = os.path.join(SAVE_DIR, "scaler.pkl")
FEATURES_PATH = os.path.join(SAVE_DIR, "features.json")
METRICS_PATH = os.path.join(SAVE_DIR, "model_metrics.csv")
PREDICTIONS_PATH = os.path.join(SAVE_DIR, "predictions.csv")
SEASONALITY_PATH = os.path.join(SAVE_DIR, "seasonality.csv")
FUTURE_FORECAST_PATH = os.path.join(SAVE_DIR, "future_forecast.csv")

HOLDOUT_YEAR = 2025


# =========================
# SPLIT
# =========================

def split_data(df):
    train_df = df[df["date"] < "2019-01-01"].copy()

    val_df = df[
        (df["date"] >= "2019-01-01") &
        (df["date"] < "2023-01-01")
    ].copy()

    test_df = df[
        (df["date"] >= "2023-01-01") &
        (df["date"] < f"{HOLDOUT_YEAR}-01-01")
    ].copy()

    holdout_df = df[
        (df["date"] >= f"{HOLDOUT_YEAR}-01-01") &
        (df["date"] < f"{HOLDOUT_YEAR + 1}-01-01")
    ].copy()

    recent_df = df[
        df["date"] >= f"{HOLDOUT_YEAR + 1}-01-01"
    ].copy()

    return train_df, val_df, test_df, holdout_df, recent_df


def make_xy(source_df):
    drop_cols = ["date", "idx", "target"]

    X = source_df.drop(columns=drop_cols)
    y = source_df["target"]

    return X, y


# =========================
# SCALE
# =========================

def get_num_cols(X):
    return [
        col for col in [
            "yr",
            "lag_1",
            "lag_2",
            "lag_3",
            "lag_6",
            "lag_12",
            "roll_3",
            "roll_6",
            "roll_12"
        ]
        if col in X.columns
    ]


def scale_features(X_train, datasets):
    num_cols = get_num_cols(X_train)
    scaler = StandardScaler()

    X_train = X_train.copy()
    X_train[num_cols] = scaler.fit_transform(X_train[num_cols])

    scaled_datasets = {}
    for dataset_name, X in datasets.items():
        X_scaled = X.copy()
        if len(X_scaled) > 0:
            X_scaled[num_cols] = scaler.transform(X_scaled[num_cols])
        scaled_datasets[dataset_name] = X_scaled

    return X_train, scaled_datasets, scaler, num_cols


# =========================
# MODELS
# =========================

def get_models():
    return {
        "linear_regression": linear_model.get_model,
        "ridge": ridge_model.get_model,
        "huber": huber_model.get_model,
        "gradient_boosting": gradient_boosting_model.get_model
    }


def get_baseline_predictions(X):
    return {
        "naive_lag_1": X["lag_1"].to_numpy() - 100,
        "naive_lag_12": X["lag_12"].to_numpy() - 100,
        "rolling_3": X["roll_3"].to_numpy() - 100,
        "rolling_12": X["roll_12"].to_numpy() - 100
    }


# =========================
# METRICS
# =========================

def mean_absolute_percentage_error_idx(y_true, y_pred):
    y_true_idx = np.asarray(y_true) + 100
    y_pred_idx = np.asarray(y_pred) + 100

    return np.mean(np.abs((y_true_idx - y_pred_idx) / y_true_idx)) * 100


def regression_metrics(y_true, y_pred):
    return {
        "mae": mean_absolute_error(y_true, y_pred),
        "mse": mean_squared_error(y_true, y_pred),
        "rmse": mean_squared_error(y_true, y_pred) ** 0.5,
        "r2": r2_score(y_true, y_pred),
        "mape_idx": mean_absolute_percentage_error_idx(y_true, y_pred)
    }


def add_metrics_row(rows, model_name, dataset_name, y_true, y_pred):
    metrics = regression_metrics(y_true, y_pred)

    rows.append({
        "model": model_name,
        "dataset": dataset_name,
        "mae": float(metrics["mae"]),
        "mse": float(metrics["mse"]),
        "rmse": float(metrics["rmse"]),
        "r2": float(metrics["r2"]),
        "mape_idx": float(metrics["mape_idx"])
    })


def get_inflation_type(source_df):
    type_cols = [col for col in source_df.columns if col.startswith("type_")]

    return (
        source_df[type_cols]
        .idxmax(axis=1)
        .str.replace("type_", "", regex=False)
        .values
    )


def make_predictions_df(source_df, y_true, y_pred, model_name, dataset_name):
    return pd.DataFrame({
        "model": model_name,
        "dataset": dataset_name,
        "date": source_df["date"].values,
        "inflation_type": get_inflation_type(source_df),
        "true_target": np.asarray(y_true).reshape(-1),
        "pred_target": np.asarray(y_pred).reshape(-1),
        "true_idx": np.asarray(y_true).reshape(-1) + 100,
        "pred_idx": np.asarray(y_pred).reshape(-1) + 100
    })


# =========================
# SEASONALITY
# =========================

def calculate_seasonality(raw_df):
    seasonality_df = raw_df.copy()
    if "inflation_type" not in seasonality_df.columns:
        seasonality_df["inflation_type"] = get_inflation_type(seasonality_df)

    seasonality_df["month_num"] = seasonality_df["date"].dt.month
    seasonality_df["year"] = seasonality_df["date"].dt.year

    yearly_mean = (
        seasonality_df
        .groupby(["inflation_type", "year"])["idx"]
        .transform("mean")
    )
    seasonality_df["seasonality_by_year"] = seasonality_df["idx"] / yearly_mean

    by_year = (
        seasonality_df
        .groupby(["inflation_type", "month_num"])["seasonality_by_year"]
        .mean()
        .reset_index(name="seasonality_by_year_method")
    )

    month_mean = (
        seasonality_df
        .groupby(["inflation_type", "month_num"])["idx"]
        .mean()
        .reset_index(name="month_mean_idx")
    )
    total_mean = (
        seasonality_df
        .groupby("inflation_type")["idx"]
        .mean()
        .reset_index(name="total_mean_idx")
    )

    seasonality = month_mean.merge(total_mean, on="inflation_type")
    seasonality["seasonality_pivot_method"] = (
        seasonality["month_mean_idx"] / seasonality["total_mean_idx"]
    )
    seasonality = seasonality.merge(
        by_year,
        on=["inflation_type", "month_num"],
        how="left"
    )

    return seasonality.sort_values(["inflation_type", "month_num"])


def make_future_forecast(df, feature_cols, num_cols, scaler, model, periods=12):
    history_df = df.copy()
    history_df["inflation_type"] = get_inflation_type(history_df)

    type_values = sorted(history_df["inflation_type"].unique())
    last_date = history_df["date"].max()
    future_dates = pd.date_range(
        last_date + pd.DateOffset(months=1),
        periods=periods,
        freq="MS"
    )

    history = {
        inflation_type: (
            history_df[history_df["inflation_type"] == inflation_type]
            .sort_values("date")["idx"]
            .tolist()
        )
        for inflation_type in type_values
    }

    rows = []
    for date in future_dates:
        for inflation_type in type_values:
            values = history[inflation_type]
            row = {col: 0 for col in feature_cols}

            row["yr"] = date.year
            row[f"m_{date.month:02d}"] = 1
            row[f"type_{inflation_type}"] = 1

            for lag in [1, 2, 3, 6, 12]:
                row[f"lag_{lag}"] = values[-lag]

            for window in [3, 6, 12]:
                row[f"roll_{window}"] = float(np.mean(values[-window:]))

            X_future = pd.DataFrame([row], columns=feature_cols)
            X_future[num_cols] = scaler.transform(X_future[num_cols])

            pred_target = float(model.predict(X_future)[0])
            pred_idx = pred_target + 100
            history[inflation_type].append(pred_idx)

            rows.append({
                "date": date,
                "inflation_type": inflation_type,
                "pred_target": pred_target,
                "pred_idx": pred_idx
            })

    return pd.DataFrame(rows)


# =========================
# TRAIN
# =========================

def train_models(X_train, y_train, eval_sets, raw_eval_sets):
    fitted_models = {}
    metrics_rows = []
    predictions = []

    for model_name, get_model in get_models().items():
        print(f"Training model: {model_name}")

        model = get_model(X_train, y_train)
        fitted_models[model_name] = model

        for dataset_name, (X_eval, y_eval, source_df) in eval_sets.items():
            if len(X_eval) == 0:
                continue

            y_pred = model.predict(X_eval)
            add_metrics_row(metrics_rows, model_name, dataset_name, y_eval, y_pred)
            predictions.append(
                make_predictions_df(source_df, y_eval, y_pred, model_name, dataset_name)
            )

    for dataset_name, (X_raw, y_eval, source_df) in raw_eval_sets.items():
        if len(X_raw) == 0:
            continue

        for baseline_name, y_pred in get_baseline_predictions(X_raw).items():
            add_metrics_row(metrics_rows, baseline_name, dataset_name, y_eval, y_pred)
            predictions.append(
                make_predictions_df(source_df, y_eval, y_pred, baseline_name, dataset_name)
            )

    metrics_df = (
        pd.DataFrame(metrics_rows)
        .sort_values(["dataset", "mae"])
        .reset_index(drop=True)
    )
    predictions_df = pd.concat(predictions, ignore_index=True)

    trainable_metrics = metrics_df[
        ~metrics_df["model"].str.startswith(("naive_", "rolling_"))
    ]
    best_model_name = (
        trainable_metrics[trainable_metrics["dataset"] == "val_2019_2022"]
        .sort_values("mae")
        .iloc[0]["model"]
    )

    return fitted_models, metrics_df, predictions_df, best_model_name


def fit_final_model(best_model_name, X_fit, y_fit):
    return get_models()[best_model_name](X_fit, y_fit)


# =========================
# MAIN
# =========================

def main():
    warnings.filterwarnings("ignore")
    os.makedirs(SAVE_DIR, exist_ok=True)

    df = prepare_data(DATA_PATH)

    print("\nPrepared data:")
    print(df.head())
    print("Shape:", df.shape)
    print("Date range:", df["date"].min(), "-", df["date"].max())

    train_df, val_df, test_df, holdout_df, recent_df = split_data(df)

    print("\nSplit:")
    print("Train:", train_df.shape)
    print("Val 2019-2022:", val_df.shape)
    print("Test 2023-2024:", test_df.shape)
    print(f"Holdout {HOLDOUT_YEAR}:", holdout_df.shape)
    print("Recent actual:", recent_df.shape)

    X_train_raw, y_train = make_xy(train_df)
    X_val_raw, y_val = make_xy(val_df)
    X_test_raw, y_test = make_xy(test_df)
    X_holdout_raw, y_holdout = make_xy(holdout_df)
    X_recent_raw, y_recent = make_xy(recent_df)

    X_train, scaled_eval, scaler, num_cols = scale_features(
        X_train_raw,
        {
            "val_2019_2022": X_val_raw,
            "test_2023_2024": X_test_raw,
            f"holdout_{HOLDOUT_YEAR}": X_holdout_raw,
            "recent_actual": X_recent_raw
        }
    )

    eval_sets = {
        "val_2019_2022": (scaled_eval["val_2019_2022"], y_val, val_df),
        "test_2023_2024": (scaled_eval["test_2023_2024"], y_test, test_df),
        f"holdout_{HOLDOUT_YEAR}": (scaled_eval[f"holdout_{HOLDOUT_YEAR}"], y_holdout, holdout_df),
        "recent_actual": (scaled_eval["recent_actual"], y_recent, recent_df)
    }
    raw_eval_sets = {
        "val_2019_2022": (X_val_raw, y_val, val_df),
        "test_2023_2024": (X_test_raw, y_test, test_df),
        f"holdout_{HOLDOUT_YEAR}": (X_holdout_raw, y_holdout, holdout_df),
        "recent_actual": (X_recent_raw, y_recent, recent_df)
    }

    _, metrics_df, predictions_df, best_model_name = train_models(
        X_train,
        y_train,
        eval_sets,
        raw_eval_sets
    )

    X_fit_raw = pd.concat([X_train_raw, X_val_raw], axis=0)
    y_fit = pd.concat([y_train, y_val], axis=0)
    X_fit, final_scaled, final_scaler, final_num_cols = scale_features(
        X_fit_raw,
        {
            "test_2023_2024": X_test_raw,
            f"holdout_{HOLDOUT_YEAR}": X_holdout_raw,
            "recent_actual": X_recent_raw
        }
    )
    final_model = fit_final_model(best_model_name, X_fit, y_fit)

    X_all_raw, y_all = make_xy(df)
    X_all, _, production_scaler, production_num_cols = scale_features(
        X_all_raw,
        {}
    )
    production_model = fit_final_model(best_model_name, X_all, y_all)

    seasonality_df = calculate_seasonality(df)
    future_forecast_df = make_future_forecast(
        df,
        X_all_raw.columns.tolist(),
        production_num_cols,
        production_scaler,
        production_model,
        periods=12
    )

    print("\n===== VALIDATION METRICS =====")
    print(
        metrics_df[metrics_df["dataset"] == "val_2019_2022"]
        .sort_values("mae")
        .to_string(index=False)
    )

    print("\n===== TEST 2023-2024 METRICS =====")
    print(
        metrics_df[metrics_df["dataset"] == "test_2023_2024"]
        .sort_values("mae")
        .to_string(index=False)
    )

    if len(holdout_df) > 0:
        print(f"\n===== HOLDOUT {HOLDOUT_YEAR} METRICS =====")
        print(
            metrics_df[metrics_df["dataset"] == f"holdout_{HOLDOUT_YEAR}"]
            .sort_values("mae")
            .to_string(index=False)
        )

    print("\nBest trainable model:", best_model_name)

    joblib.dump(production_model, BEST_MODEL_PATH)
    joblib.dump(production_scaler, SCALER_PATH)

    with open(FEATURES_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {
                "feature_cols": X_all_raw.columns.tolist(),
                "num_cols": production_num_cols,
                "target": "idx - 100",
                "best_model": best_model_name,
                "train_rows": int(len(train_df)),
                "val_rows": int(len(val_df)),
                "test_rows": int(len(test_df)),
                "holdout_rows": int(len(holdout_df)),
                "recent_rows": int(len(recent_df))
            },
            f,
            ensure_ascii=False,
            indent=4
        )

    metrics_df.to_csv(METRICS_PATH, index=False, encoding="utf-8-sig")
    predictions_df.to_csv(PREDICTIONS_PATH, index=False, encoding="utf-8-sig")
    seasonality_df.to_csv(SEASONALITY_PATH, index=False, encoding="utf-8-sig")
    future_forecast_df.to_csv(FUTURE_FORECAST_PATH, index=False, encoding="utf-8-sig")

    print("\n===== SAVED =====")
    print(f"Best model saved to: {BEST_MODEL_PATH}")
    print(f"Scaler saved to: {SCALER_PATH}")
    print(f"Features saved to: {FEATURES_PATH}")
    print(f"Metrics saved to: {METRICS_PATH}")
    print(f"Predictions saved to: {PREDICTIONS_PATH}")
    print(f"Seasonality saved to: {SEASONALITY_PATH}")
    print(f"Future forecast saved to: {FUTURE_FORECAST_PATH}")


if __name__ == "__main__":
    main()

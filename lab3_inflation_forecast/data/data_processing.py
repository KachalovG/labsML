import pandas as pd


def prepare_data(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)

    df = df.rename(columns={
        "year": "yr",
        "month_num": "month_num",
        "month": "mon_name",
        "inflation_type": "inflation_type",
        "source_type": "src",
        "value": "idx"
    })

    df = df.drop(columns=["src"])

    # кодировка месяца one-hot
    df["mon_code"] = "m_" + df["month_num"].astype(str).str.zfill(2)
    month_dummies = pd.get_dummies(df["mon_code"], dtype=int)
    df = pd.concat([df, month_dummies], axis=1)
    df.drop(columns=["month_num", "mon_name", "mon_code"], inplace=True)

    # дата и idx
    df["date"] = pd.to_datetime(df["date"])
    df["idx"] = pd.to_numeric(df["idx"], errors="coerce")

    # сортировка перед лагами
    df = df.sort_values(["inflation_type", "date"]).reset_index(drop=True)

    # лаги
    for lag in [1, 2, 3, 6, 12]:
        df[f"lag_{lag}"] = df.groupby("inflation_type")["idx"].shift(lag)

    # rolling
    for window in [3, 6, 12]:
        df[f"roll_{window}"] = (
            df.groupby("inflation_type")["idx"]
              .transform(lambda s: s.shift(1).rolling(window=window).mean())
        )

    df = df.dropna().reset_index(drop=True)

    # one-hot типа инфляции
    type_dummies = pd.get_dummies(df["inflation_type"], prefix="type", dtype=int)
    df = pd.concat([df, type_dummies], axis=1)
    df = df.drop(columns=["inflation_type"])

    # target
    df["target"] = df["idx"] - 100

    # финальная сортировка
    df = df.sort_values("date").reset_index(drop=True)

    return df


if __name__ == "__main__":
    df = prepare_data("inflation_long_format.csv")
    print(df.head())
    print(df.shape)
    print(df.columns.tolist())

import pandas as pd
import csv

df = pd.read_csv("../../data/raw/spam.csv", encoding="latin1")

df = df[['v1','v2']]
df.columns = ['label','text']

df['text'] = df['text'].str.replace('\n',' ', regex=False)
df['text'] = df['text'].str.replace('\r',' ', regex=False)

# ключевая строка
df['text'] = df['text'].str.replace('"', "'", regex=False)

df['text'] = df['text'].str.strip()

df['label'] = df['label'].map({'spam':1,'ham':0})

df.to_csv(
    "../../data/processed/spam_clean_fix.csv",
    index=False,
    encoding="utf-8")
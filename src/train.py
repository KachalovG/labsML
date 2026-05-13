import pandas as pd
import numpy as np
from models.adaline_sgd import AdalineSGD
from preprocessing.text_vectorizer import build_vocab, vectorize_text

df = pd.read_csv("../data/processed/data-for-fit.csv")

texts = df["text"].values
y = df["label"].values

vocab = build_vocab(texts)

X = vectorize_text(texts, vocab)

print("X shape:", X.shape)
print("y shape:", y.shape)

model = AdalineSGD(eta=0.01, n_iter=30)

model.fit(X, y)

predictions = model.predict(X)

print(predictions[:10])

accuracy = (predictions == y).mean()

print("accuracy:", accuracy)
print("training finished")

import pickle

with open("model.pkl", "wb") as f:
    pickle.dump(model, f)

with open("vocab.pkl", "wb") as f:
    pickle.dump(vocab, f)
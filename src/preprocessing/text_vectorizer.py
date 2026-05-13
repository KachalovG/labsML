import numpy as np

def build_vocab(texts):
    vocab = {}
    for text in texts:
        words = text.lower().split()
        for word in words:
            if word not in vocab:
                vocab[word] = len(vocab)
    return vocab

def vectorize_text(texts, vocab):
    X = np.zeros((len(texts), len(vocab)))
    for i,text in enumerate(texts):
        words = text.lower().split()
        for word in words:
            if word in vocab:
                j = vocab[word]
                X[i, j] += 1
    return X

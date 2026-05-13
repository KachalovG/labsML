import pickle
from preprocessing.text_vectorizer import vectorize_text


class SpamClassifier:

    def __init__(self):

        with open("model.pkl", "rb") as f:
            self.model = pickle.load(f)

        with open("vocab.pkl", "rb") as f:
            self.vocab = pickle.load(f)

    def predict(self, text):

        X = vectorize_text([text], self.vocab)

        prediction = self.model.predict(X)[0]

        if prediction == 1:
            return "SPAM"
        else:
            return "HAM"


def main():

    clf = SpamClassifier()

    text = input("Введите сообщение: ")

    result = clf.predict(text)

    print("Prediction:", result)


if __name__ == "__main__":
    main()


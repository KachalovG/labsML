from sklearn.linear_model import LinearRegression


def get_model(Xtrain, ytrain):
    model = LinearRegression()
    model.fit(Xtrain, ytrain)
    return model

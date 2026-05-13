from sklearn.linear_model import HuberRegressor
from sklearn.model_selection import GridSearchCV
from sklearn.model_selection import TimeSeriesSplit


def get_model(Xtrain, ytrain):
    model = HuberRegressor(max_iter=2000)

    param_grid = {
        "epsilon": [1.1, 1.35, 1.75],
        "alpha": [0.0001, 0.001, 0.01],
        "tol": [1e-4]
    }

    grid_search = GridSearchCV(
        estimator=model,
        param_grid=param_grid,
        scoring="neg_mean_absolute_error",
        cv=TimeSeriesSplit(n_splits=3),
        n_jobs=1
    )

    grid_search.fit(Xtrain, ytrain)

    return grid_search.best_estimator_

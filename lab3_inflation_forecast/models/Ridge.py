from sklearn.linear_model import Ridge
from sklearn.model_selection import GridSearchCV
from sklearn.model_selection import TimeSeriesSplit

def get_model(Xtrain, ytrain):
    model = Ridge()

    param_grid = {
        'alpha':[0.001, 0.01, 0.1, 1, 10, 100],
        'fit_intercept':[True, False],
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

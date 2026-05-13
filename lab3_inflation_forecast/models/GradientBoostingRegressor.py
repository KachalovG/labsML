from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import GridSearchCV
from sklearn.model_selection import TimeSeriesSplit

def get_model(Xtrain, ytrain):
    model = GradientBoostingRegressor(random_state=42)

    param_grid = {
        "loss": ["huber"],
        "n_estimators": [100, 200],
        "learning_rate": [0.03, 0.05],
        "max_depth": [1, 2],
        "min_samples_leaf": [4]
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

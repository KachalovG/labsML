# Lab 4 MAP: saved-model report

Папка содержит финальные артефакты лабораторной работы №4 по прогнозированию РТО.

Главный принцип: модели не обучаются заново. Скрипты загружают уже сохраненные артефакты из проекта:

- `../save_models/torch_mlp.pth`
- `../save_models/random_forest.pkl`
- `../save_models/linear_regression.pkl`
- `../models/scaler.pkl`

## Файлы

- `saved_model_pipeline.py` - строит прогноз на 11-й месяц через сохраненные модели и сохраняет `outputs/test.csv`.
- `generate_report_assets.py` - пересчитывает метрики через `predict`, строит EDA-графики, важность признаков и JSON для отчета.
- `build_report.py` - собирает строгий отчет Word с пустым первым листом.
- `plots/` - графики для отчета.
- `outputs/` - прогноз, диагностика, метрики и служебные JSON.
- `report_lab4_map_saved_models.docx` - итоговый отчет.

## Запуск

```powershell
python generate_report_assets.py
python build_report.py
```

В финальных скриптах нет вызовов обучения моделей; используются только загрузка сохраненных моделей, подготовка признаков, `transform` и `predict`.

# Evaluation

Система проверяется отдельным evaluation-контуром в `scripts/evaluate.py`.
Он запускает вопросы из `tests/qa_set.jsonl`, получает найденные чанки и,
при флаге `--call-llm`, генерирует ответы модели.

## Метрики

В отчете считаются:

- `expected_hit_rate` - доля ответов, где найден ожидаемый фрагмент ответа из QA-набора.
- `expected_source_hit_rate` - доля запросов, где среди источников найден ожидаемый файл.
- `retrieval_hit_rate` - доля запросов, для которых найден хотя бы один чанк.
- `avg_retrieved_chunks` - среднее количество найденных чанков на вопрос.
- `answer_nonempty_rate` - доля непустых ответов.
- `answer_too_short_rate` - доля слишком коротких ответов.
- `answer_context_overlap_avg` - средняя доля значимых токенов ответа, найденных в извлеченном контексте.
- `answer_source_ref_rate` - доля ответов со ссылками вида `[source1]`.
- `answer_valid_source_ref_rate` - доля ответов, где ссылки указывают на реально извлеченные источники.
- `answer_grounded_rate` - доля ответов, которые либо являются корректным отказом из-за недостатка информации, либо имеют достаточное пересечение с контекстом.

`answer_context_overlap_avg` и `answer_grounded_rate` являются базовой защитой от
ситуации, когда модель генерирует связный, но не подтвержденный документами текст.
Метрика не доказывает полноту ответа, но хорошо ловит ответы, слабо связанные с
извлеченным контекстом.

## Пример запуска

## Синтетический корпус

Для проверки метрик без внешних данных можно создать небольшой контрольный
корпус:

```bash
python scripts/generate_eval_corpus.py
```

Команда создает:

- `eval_corpus/documents/*.docx` - синтетические документы для индексации;
- `eval_corpus/manifest.json` - метаданные для загрузки;
- `eval_corpus/qa_set.jsonl` - вопросы, ожидаемые источники и ожидаемые фразы.

Загрузить корпус через API можно так:

```bash
python scripts/upload_eval_corpus.py \
  --api-url http://app:8000 \
  --username admin \
  --password admin
```

После загрузки запускайте evaluation по этому QA-набору:

```bash
python scripts/evaluate.py \
  --qa eval_corpus/qa_set.jsonl \
  --strategy hybrid \
  --call-llm \
  --validate \
  --min-expected-source-hit-rate 0.8 \
  --min-answer-nonempty-rate 1.0 \
  --min-retrieval-hit-rate 0.9 \
  --min-avg-retrieved-chunks 1.0 \
  --max-answer-too-short-rate 0.05 \
  --min-answer-context-overlap-avg 0.2 \
  --min-answer-source-ref-rate 0.8 \
  --min-answer-valid-source-ref-rate 0.8 \
  --min-answer-grounded-rate 0.9
```

Результат сохраняется в `analysis/results_*.json`. При нарушении порогов команда
завершается с кодом `1`, поэтому ее можно использовать как quality gate в CI.

Если `retrieval_hit_rate` равен `0`, проблема не в генерации ответа, а в том,
что evaluation-запуск не видит документы: база пустая, документы не
проиндексированы или фильтры QA-набора (`doc_year_from`, `doc_year_to`,
`doc_category`) не совпадают с метаданными документов.

Для быстрой проверки текущей базы можно добавить `--ignore-qa-filters`: тогда
скрипт не будет применять фильтры годов и категорий из QA-набора.

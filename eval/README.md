# RIS Pipeline Evaluation Framework

Stress-tests the full Evidara pipeline using real Austrian Federal Court
decisions and legislation from the RIS (Rechtsinformationssystem des Bundes).

## Structure

```
eval/
  documents.csv          # curated catalog of ~50 RIS documents
  queries.csv            # 30 test queries across 6 task types
  gold_answers.csv       # expected answers with required citations
  score_eval.py          # automated scorer
  conftest.py            # pytest fixtures for eval
  test_eval_pipeline.py  # pytest-based eval runner
  runs/                  # output from eval runs
```

## Quick start

```bash
# Download documents from RIS OGD API
make eval-download

# Run documents through the DI pipeline
make eval-process

# Score predictions against gold answers
make eval-score

# Or run everything at once
make eval
```

## Query task types

| Task | Description | Count |
|------|-------------|-------|
| `section_extraction` | Extract specific section content from a law | 5 |
| `holding_extraction` | Extract the holding/ruling from a decision | 5 |
| `temporal_version` | Identify which law version was in force at a date | 5 |
| `source_classification` | Classify doc type (law vs decision vs Rechtssatz) | 5 |
| `citation_chain` | Find cited laws/cases within a document | 5 |
| `cross_reference` | Identify entities or references across documents | 5 |

## Scoring dimensions

- **correctness**: keyword overlap with gold answer
- **citation_precision**: cited docs are in gold set
- **citation_recall**: all required docs were cited
- **temporal_accuracy**: correct law version used
- **source_type_correct**: law/decision/Rechtssatz classified correctly
- **hallucination**: unsupported legal claims (hard fail gate)
- **completeness**: combined correctness + recall metric

## Pass/fail gates

- Citation precision >= 95%
- Source-type correctness >= 98%
- Temporal accuracy >= 95%
- Hallucination rate <= 2%

## Predictions CSV format

The scorer expects predictions in this format:

```csv
query_id,answer_text,used_doc_ids,source_class_claimed,model_flags
Q001,"Errichtung einer Notarstelle...",DOC_LAW_001,law,"grounded=true;temporal_ok=true"
```

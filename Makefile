.PHONY: eval eval-download eval-process eval-score eval-data-check

EVAL_DIR := eval
EVAL_DATA_DIR := $(EVAL_DIR)/data
EVAL_RUNS_DIR := $(EVAL_DIR)/runs

# Download RIS documents listed in the eval catalog
eval-download:
	python $(EVAL_DIR)/download_ris_documents.py $(EVAL_DATA_DIR)

# Run DI pipeline integration tests on golden RIS fixtures
eval-process:
	python -m pytest $(EVAL_DIR)/test_eval_pipeline.py -v --tb=short -k "test_ris_fixture"

# Score predictions against gold answers
# Usage: make eval-score PREDICTIONS=path/to/predictions.csv
eval-score:
	@if [ -z "$(PREDICTIONS)" ]; then \
		echo "Usage: make eval-score PREDICTIONS=path/to/predictions.csv"; \
		exit 1; \
	fi
	python $(EVAL_DIR)/score_eval.py $(PREDICTIONS)

# Validate eval data integrity (CSV cross-references)
eval-data-check:
	python -m pytest $(EVAL_DIR)/test_eval_pipeline.py -v --tb=short -k "test_eval_data_integrity or test_query_task_type"

# Full eval pipeline: download + process + data check
eval: eval-download eval-process eval-data-check
	@echo "Evaluation complete. Check $(EVAL_RUNS_DIR)/ for results."

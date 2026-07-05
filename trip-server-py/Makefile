.PHONY: test eval eval-real eval-debug eval-compare eval-baseline eval-retrieval eval-retrieval-save benchmark-http benchmark-sse benchmark-charts verify-guards mcp-smoke lint type-check

test:
	.venv/bin/python -m pytest tests/ -v --tb=short

test-quick:
	.venv/bin/python -m pytest tests/ -v --tb=short -x -q

test-schemas:
	.venv/bin/python -m pytest tests/test_schemas.py -v --tb=short

eval:
	.venv/bin/python -m eval.run

eval-real:
	.venv/bin/python -m eval.run --real

eval-debug:
	EVAL_DEBUG=1 .venv/bin/python -m eval.run --real

eval-compare:
	.venv/bin/python scripts/eval_compare.py

eval-baseline:
	.venv/bin/python -m eval.run --tag smoke --save && cp $$(ls -t eval-reports/*.json | grep -v baseline | grep -v comparison | head -1) eval-reports/baseline.json

eval-retrieval:
	.venv/bin/python -m eval.retrieval.run

eval-retrieval-save:
	.venv/bin/python -m eval.retrieval.run --save

eval-ragas:
	.venv/bin/python -m eval.run --tag smoke --real 2>&1 | head -80

eval-ragas-mock:
	.venv/bin/python -m eval.run --tag smoke 2>&1 | head -80

mcp-smoke:
	.venv/bin/python -m eval.mcp_smoke

benchmark-http:
	.venv/bin/python scripts/benchmark_http.py

benchmark-sse:
	.venv/bin/python scripts/benchmark_sse.py

benchmark-charts:
	.venv/bin/python scripts/benchmark_lib/chart.py

verify-guards:
	.venv/bin/python scripts/verify_guards.py

lint:
	.venv/bin/ruff check src/ tests/ eval/

type-check:
	.venv/bin/mypy src/ --ignore-missing-imports

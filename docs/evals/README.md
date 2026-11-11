# Documentation Evals

This folder contains the simulator documentation eval set.

## Files

- `simulator_qa.jsonl`: question bank for junior, intermediate, and senior readers.
- `../../DOCUMENTATION_GOALS.md`: definition of the target documentation state.
- `../../tools/evals/run_docs_eval.py`: local runner for static checks and optional DeepSeek-backed chat checks.

## Run Static Checks

```bash
uv run python tools/evals/run_docs_eval.py --mode static
```

Static mode checks the documentation structure, required lesson coverage, lesson index coverage, and question-bank source coverage. It does not call DeepSeek.

## Run Chat Checks

```bash
uv run python tools/evals/run_docs_eval.py --mode chat --limit 10
```

Chat mode uses `src/app/services/chat_service.py`, so it requires `config/deepseek_key`.

The first version of the eval set is expected to fail on topics whose lessons have not been written yet. Those failures are the work queue for the remaining documentation pass.

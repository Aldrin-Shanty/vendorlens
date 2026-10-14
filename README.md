VendorLens compares supplier evidence, quote totals, and fictional policy gaps with citations and human review.

## Local development

### Prerequisites

- Python 3.13
- uv
- Docker

### Setup

Install dependencies:

    uv sync --dev

Create the local environment file:

    Copy-Item .env.example .env

Update the values in `.env` for your local environment.

Start PostgreSQL:

    docker compose up -d

Apply database migrations:

    uv run alembic upgrade head

Start the API:

    uv run uvicorn vendorlens.api.main:app --reload

The API is available at:

    http://localhost:8000

Swagger documentation is available at:

    http://localhost:8000/docs

### Tests

Create the test database if it does not already exist:

    docker exec -it vendorlens-db-1 psql -U postgres -d postgres

Then in PostgreSQL:

    CREATE DATABASE vendorlens_test;

Run the test suite:

    uv run pytest -v

### Supplier comparison and evidence judgment

`POST /procurement-events/{event_id}/compare` accepts `supplier_ids` containing
two to eight distinct supplier UUIDs. Every supplier must have a proposal in that
event. The response includes extracted facts and only their cited source chunks.
Citation IDs are local to each supplier entry.

Evidence judgment uses local [DeBERTa NLI](https://huggingface.co/MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli),
pinned to revision `6f5cf0a`, on CPU. Qwen handles extraction and keeps the GPU.
No TypeSafe account or API key is required. Existing TYPESAFE settings are unused.

Download the model and run four synthetic checks:

```powershell
uv run python scripts/verify_nli.py --download
```

Subsequent checks use only cached files:

```powershell
uv run python scripts/verify_nli.py
```

The report is saved to `output/phase4/nli-live-results.json`. After setup, enable
`NLI_EVIDENCE_JUDGMENT_ENABLED=true` in `.env` and restart the API. Inference never
downloads model files during an API request. Model weights live in `data/models`.

Each supplier has a `judgment` object: `not_checked` means no semantic check;
`checked` reports per-fact relation, probabilities, model/revision and input token
count. Entailment maps to supports, neutral to insufficient, contradiction to
contradicts. Confidence is the largest softmax probability, not calibrated truth.
The 0.8 review threshold is provisional. Contradicted, insufficient and low-confidence
facts require review; original facts remain visible.

Bounds: three facts per supplier, eight suppliers per comparison, a 48,000-byte
serialized state guard and 512 tokens per premise/hypothesis pair. Oversized input
is rejected, not truncated. Local inference is serialized. Cited texts are combined
per fact; conflicting or long sources still need human review. CPU inference has no
hard execution timeout. Missing models return 503; oversized/invalid output returns
502. Regression tests use fake models and disable judgment regardless of `.env`.
Four smoke cases do not establish corpus accuracy or calibrate the threshold.

To exercise real Qwen extraction, start your llama.cpp server on port 8080, then run:

```powershell
$env:RUN_LOCAL_LLM_TESTS = "true"
uv run pytest -v tests/test_local_llm_smoke.py
Remove-Item Env:RUN_LOCAL_LLM_TESTS
```

This opt-in smoke test uses synthetic evidence and checks extraction and provenance;
it does not establish model quality across the procurement corpus.

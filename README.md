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

`src/vendorlens/services/comparison.py::compare_suppliers` is the direct comparison
service used by `/compare`. Persistent LangGraph workflows use
`src/vendorlens/workflows/services.py`. Read the comparison service top to bottom:
validate selection, retrieve supplier evidence, extract facts,
validate identity/citations, build evidence references, judge facts, assemble the
comparison. Selection is validated for every supplier before retrieval or model
calls begin. Stage implementations live in `services/fact_extraction.py`; its
`extract_facts_for_supplier` convenience function uses the same stages for
standalone extraction and the Qwen smoke test.

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
The workflow review policy owns the provisional 0.8 threshold and produces
`review_issues` for missing, unchecked, contradicted, insufficient or low-confidence
facts. Model judgments contain relation, confidence and probabilities; original
facts remain visible.

Bounds: three facts per supplier, eight suppliers per comparison, a 48,000-byte
serialized state guard and 512 tokens per premise/hypothesis pair. Oversized input
is rejected, not truncated. Local inference is serialized. Cited texts are combined
per fact; conflicting or long sources still need human review. CPU inference has no
hard execution timeout. For the direct `/compare` endpoint, missing models return
503; oversized/invalid output returns 502. Persistent workflows record handled
errors with status `failed` in their saved state. Regression tests use fake models
and disable judgment regardless of `.env`.
Four smoke cases do not establish corpus accuracy or calibrate the threshold.

The Qwen smoke test automatically checks the local server's `/health` endpoint.
When ready, it runs with the rest of the suite; when unavailable or loading, it
skips after a health check with a two-second timeout. Once ready, extraction
errors fail the test rather than being skipped.

Start your llama.cpp server on port 8080, then run:

```powershell
uv run pytest -v
```

This smoke test uses synthetic evidence and checks extraction and provenance;
it does not establish model quality across the procurement corpus.

### Persistent comparison workflows

Comparison workflows use LangGraph with PostgreSQL checkpoints. They run
synchronously until completion, a handled failure, budget exhaustion, or
a pause for human review.

Run the following commands from the project root. Initialize checkpoint tables
after configuring the application database:

```powershell
uv run python -c "from vendorlens.db.engine import engine; from vendorlens.workflows.checkpoint import initialize_checkpoints; initialize_checkpoints(engine.url.render_as_string(hide_password=False))"
```

This setup is separate from Alembic migrations. It is not run on every request.
Run it for each new application database and when checkpoint storage migrations
are needed after a dependency upgrade.

Start the API:

```powershell
uv run uvicorn vendorlens.api.main:app --reload
```

In another PowerShell terminal, prepare the request. Use an existing
procurement event and two suppliers with ingested proposal evidence
in that event. Start the local Qwen server before creating a workflow; enable
DeBERTa evidence judgment as described above to include semantic checks.

```powershell
$baseUrl = "http://127.0.0.1:8000"
$headers = @{
    "X-API-Key" = Read-Host "API_KEY from .env"
}
$eventId = Read-Host "Procurement event UUID"
$supplierIds = @(
    (Read-Host "First supplier UUID")
    (Read-Host "Second supplier UUID")
)
```

Start a workflow:

```powershell
$body = @{
    supplier_ids = $supplierIds
} | ConvertTo-Json

$workflow = Invoke-RestMethod `
    -Method Post `
    -Uri "$baseUrl/procurement-events/$eventId/comparison-workflows" `
    -Headers $headers `
    -ContentType "application/json" `
    -Body $body

$workflowId = $workflow.workflow_id
$workflow | ConvertTo-Json -Depth 20
```

Read its saved state:

```powershell
$workflowUrl = "$baseUrl/procurement-events/$eventId/comparison-workflows/$workflowId"

$saved = Invoke-RestMethod `
    -Method Get `
    -Uri $workflowUrl `
    -Headers $headers

$saved | ConvertTo-Json -Depth 20
```

Reading does not repeat retrieval or model calls. Saved review pauses
can be retrieved after restarting the API, using the same workflow ID
and database. Keep the request terminal open to retain these variables,
or save the event and workflow IDs to use in a later session.

When the status is `awaiting_review`, inspect the comparison, cited
evidence, and review issues before submitting a decision:

```powershell
$decision = @{
    action = "acknowledge"
    comment = "Inspected the cited evidence and noted the reported gaps."
} | ConvertTo-Json

$reviewed = Invoke-RestMethod `
    -Method Post `
    -Uri "$workflowUrl/review" `
    -Headers $headers `
    -ContentType "application/json" `
    -Body $decision

$reviewed | ConvertTo-Json -Depth 20
```

Use `reject` instead of `acknowledge` to reject the comparison.
Acknowledgment records that the issues were reviewed; it does not
correct facts or approve a purchase. Review decisions preserve the comparison,
review issues, and execution counters without rerunning extraction or judgment.

| Status | Meaning |
|---|---|
| `completed` | Comparison finished without review issues |
| `awaiting_review` | Saved comparison is paused for human review |
| `reviewed` | Reviewer acknowledged the issues |
| `rejected` | Reviewer rejected the comparison |
| `stopped` | Execution allowance was exhausted |
| `failed` | A handled selection, evidence, or AI error occurred |

The API allows two to eight distinct suppliers. Each supplier receives
allowance for one retrieval, one extraction, and up to three NLI calls.
Reviewing and reading do not consume additional model or tool allowance.

Creation returns HTTP 201 with the saved workflow status, including when that
status is `failed` or `stopped`. Reading and successful review return HTTP 200.
All workflow endpoints require `X-API-Key`. Workflows are scoped to their
procurement event. Unknown or incorrectly scoped workflows return 404.
Reviewing a workflow that is not awaiting review returns 409. Invalid
review bodies return 422.

The shared API key does not identify an individual reviewer.

Run the full test suite with:

```powershell
uv run pytest -q
```

Workflow API tests use an in-memory checkpointer and synthetic model results.
Separate PostgreSQL tests verify resuming with a new graph and connection,
preserving results and counters, and isolation between workflow IDs. These
checks do not simulate a process crash during a model call.

### Deleting records and their evidence

The frontend shows a confirmation dialog with current related-record counts.
Deleting a proposal also deletes its documents, versions, evidence chunks, stored
PDFs, and saved comparison workflows that used that supplier's evidence in the
same event. Deleting an event removes all its proposals and their owned data;
deleting a supplier removes that supplier's proposals across events. Other
suppliers and events are preserved. Empty events and suppliers do not show the
related-proposal warning. Canceling does not issue a delete request.

For direct API clients, preview the impact with
`GET /proposals/{id}/deletion-impact`,
`GET /procurement-events/{id}/deletion-impact`, or
`GET /suppliers/{id}/deletion-impact`. The DELETE routes require
`?confirm_related=true` when related records or saved comparisons exist;
otherwise they return 409 without deleting anything. An empty record can be
deleted without that flag. All these endpoints require `X-API-Key`.

Database rows and affected checkpoints are removed in the same transaction.
PDFs are first moved into a reversible staging directory under `data/uploads`;
database failure restores them. Once the database commit succeeds, the staged
files are removed. If that final filesystem cleanup fails, the API reports that
the record was deleted and logs the remaining staging location for cleanup.
Active comparisons hold transaction-scoped locks so deletion waits until their
model execution finishes before removing saved evidence.

### Named workflow history and deletion

Run `uv run alembic upgrade head` before starting the updated API. The workflow
catalog migration adds names and persistent per-event/supplier-set run counters.
Names follow `Event title — Supplier A + Supplier B (1)`; supplier order does not
change the group, and deleting runs renumbers the remaining runs consecutively. Existing saved
comparisons receive names automatically when listed or opened.

- `GET /procurement-events/{event_id}/comparison-workflows`: named history for an event.
- `GET /comparison-workflows`: history across events.
- `DELETE /procurement-events/{event_id}/comparison-workflows/{workflow_id}?confirm=true`: delete one saved comparison.
- `DELETE /comparison-workflows?confirm=true`: delete all saved comparisons across events.

Deletion requires the API key and explicit confirmation, and removes checkpoints,
results and review decisions. Source proposals and PDFs remain available. Without
confirmation, deleting existing workflows returns 409. UUIDs remain the technical
API identifiers. The UI provides named history and confirmation dialogs.

# VendorLens frontend

React + TypeScript + Vite, with Tailwind v4 and shadcn/ui-style components built on Radix primitives. All frontend files live here; the Python backend is unchanged.

## Run

```powershell
cd apps/web
npm install
npm run dev
```

Open the URL printed by Vite. The frontend first loads your live suppliers, events,
and proposals automatically. A brief connecting screen appears while those requests
finish. A healthy API opens the live workspace, including when its collections are
empty. If any request fails, returns invalid data, or takes longer than eight
seconds, the interface falls back to a clearly labeled demo workspace and explains
why. Demo mutations are session-only and reset on reload. Demo questions show a
fixed sample answer, not an AI-generated response.

## Connect the existing API

The frontend proxy reads the existing `.env` in the repository root (`vendorlens/.env`, beside `apps/`). It uses the same `API_KEY` as your backend. There is no need to copy the key into another file.

Optionally add `API_TARGET=http://127.0.0.1:8000` to the root `.env` if your backend address differs from the default. Frontend-specific overrides in `apps/web/.env` are also supported and take precedence. Restart Vite after changing environment values; the interface attempts a live connection automatically. If it falls back to demo, fix the connection and choose **Connect API** to retry, or reload the page. You can also choose **Use demo** in connection settings for the current session. Follow the repository's existing backend startup instructions separately.

The browser calls `/api`. Vite proxies to the backend and injects `X-API-Key` on the server, avoiding CORS changes and keeping the key out of browser bundles. Never prefix the key with `VITE_`.

For production, serve the compiled assets behind a reverse proxy that handles `/api`, strips the prefix, and injects the API key on the server. Authenticate users at that gateway before exposing write operations. Vite's development proxy is not included in a static production build or preview server.

## Features

- Responsive overview, events, suppliers, and proposal tables
- Create/edit/delete events and suppliers; create/delete proposals
- Confirmed cascading deletion of proposals, events, and suppliers, including
  owned PDFs, evidence, and affected saved comparisons; cancel preserves records
- PDF upload with the API's 10 MB limit and ingestion feedback
- Event-scoped question answering and semantic search with document/page citations
- Supplier comparison workflows: select two to eight suppliers with proposals,
  inspect prices, warranties, delivery timelines, judgments, and cited passages
- Named saved workflows from the server, status refresh, and confirmed deletion
- Human review with acknowledge/reject decisions, required comments, and saved results
- Accessible Radix dialogs, loading/empty/error states, keyboard focus, mobile navigation

The current API does not expose document listing/download, timestamps, evaluation status, or quote totals. The frontend does not invent those fields for live records.

Deletion dialogs fetch the current related-record counts before enabling Delete.
Events and suppliers without proposals do not show a related-proposal warning.
Confirming deletion removes owned proposals and their documents, versions, evidence
chunks, and stored PDFs, plus saved comparisons containing the removed evidence.
Other events and suppliers remain intact. Canceling or closing the dialog sends no
DELETE request. If related data appears after an empty preview, the backend refuses
the unconfirmed deletion and the dialog reloads the impact for another confirmation.

## Compare and review

Initialize the PostgreSQL checkpoint tables using the command in the root README
before starting live workflows. Start Qwen and, if wanted, enable the locally
cached DeBERTa model for semantic evidence checks.

Open **Comparisons**, select an event, and choose two to eight suppliers. Only
suppliers with proposals in that event appear. Upload their proposal PDFs before
starting a live comparison. Creation is synchronous and may take time while
extraction and evidence checks run.

The result shows the saved status, operation usage, extracted facts, model
judgments, and review issues. Click a fact's citation or expand a document passage
to inspect its text, page, document version, and chunk ID. Confidence values are
model scores, not calibrated probabilities of truth.

When the result is **Awaiting review**, choose **Acknowledge issues** or **Reject
comparison** and enter a comment of up to 1,000 characters. Acknowledgment records
your review; it does not fix facts or approve a purchase. Reading, refreshing, and
reviewing preserve the original results and do not repeat model calls. If another
request has already reviewed the workflow, the interface refreshes the saved
result and reports the conflict.

Saved workflows are listed for the selected event, including runs created in other
browsers. Names use `Event title — Supplier A + Supplier B (1)`. Supplier order
does not affect the counter; each event and supplier set has its own sequence.
Creation and deletion keep each event/supplier group numbered consecutively.
Creating a comparison assigns the next number (or 1 for an empty group). Names are snapshots of the titles at
creation. Existing saved runs receive names automatically, oldest first.

Use a row to reopen a comparison or its trash button to delete it after confirmation.
**Delete all workflows** confirms deletion across every event. Workflow deletion
removes results and review decisions while keeping source proposals and PDFs.
UUIDs remain available under **Workflow details** and **Open by workflow ID**.

Demo comparisons use explicitly labeled synthetic facts, sources, and judgments.
Sample decisions last for the current preview and never call the backend.

## Validate

```powershell
npm run build
npm test
npx playwright test
```

Playwright checks use the demo workspace and mocked API responses; they do not mutate your backend. Install its Chromium browser first with `npx playwright install chromium` if needed.

Comparison checks cover demo review on mobile, live creation and both review
decisions, reopening after a browser reload, conflict recovery, event changes,
lookup errors, and completed/failed/stopped states.

Startup checks cover automatic live connection, empty workspaces, a connecting
screen without sample-data flashes, network and authentication failures, partial
or malformed responses, an eight-second timeout, and manual recovery from demo.

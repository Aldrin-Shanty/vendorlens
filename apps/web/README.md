# VendorLens frontend

React + TypeScript + Vite, with Tailwind v4 and shadcn/ui-style components built on Radix primitives. All frontend files live here; the Python backend is unchanged.

## Run

```powershell
cd apps/web
npm install
npm run dev
```

Open the URL printed by Vite. The frontend starts with clearly labeled sample data so you can explore the interface without running the database or API. Demo mutations are session-only and reset on reload. Demo questions show a fixed sample answer, not an AI-generated response.

## Connect the existing API

The frontend proxy reads the existing `.env` in the repository root (`vendorlens/.env`, beside `apps/`). It uses the same `API_KEY` as your backend. There is no need to copy the key into another file.

Optionally add `API_TARGET=http://127.0.0.1:8000` to the root `.env` if your backend address differs from the default. Frontend-specific overrides in `apps/web/.env` are also supported and take precedence. Restart Vite after changing environment values, then choose **Connect API** in the interface. The interface starts in demo mode until you connect successfully. Follow the repository's existing backend startup instructions separately.

The browser calls `/api`. Vite proxies to the backend and injects `X-API-Key` on the server, avoiding CORS changes and keeping the key out of browser bundles. Never prefix the key with `VITE_`.

For production, serve the compiled assets behind a reverse proxy that handles `/api`, strips the prefix, and injects the API key on the server. Authenticate users at that gateway before exposing write operations. Vite's development proxy is not included in a static production build or preview server.

## Features

- Responsive overview, events, suppliers, and proposal tables
- Create/edit/delete events and suppliers; create/delete proposals
- PDF upload with the API's 10 MB limit and ingestion feedback
- Event-scoped question answering and semantic search with document/page citations
- Accessible Radix dialogs, loading/empty/error states, keyboard focus, mobile navigation

The current API does not expose document listing/download, timestamps, evaluation status, or quote totals. The frontend does not invent those fields for live records.

## Validate

```powershell
npm run build
npm test
npx playwright test
```

Playwright checks use the demo workspace and mocked API responses; they do not mutate your backend. Install its Chromium browser first with `npx playwright install chromium` if needed.

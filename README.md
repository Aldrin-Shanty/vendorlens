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

"""Real llama.cpp smoke test; runs when the configured local server is ready."""

import uuid
from unittest.mock import Mock
from urllib.parse import urlsplit, urlunsplit

import httpx
import pytest
from sqlalchemy.orm import Session

from vendorlens.services import fact_extraction
from vendorlens.services.llm import LLM_URL
from vendorlens.services.retrieval import SearchResult


def test_real_local_supplier_extraction(monkeypatch):
    endpoint = urlsplit(LLM_URL)
    health_url = urlunsplit((endpoint.scheme, endpoint.netloc, "/health", "", ""))
    try:
        response = httpx.get(health_url, timeout=2.0)
    except httpx.RequestError:
        pytest.skip("Local Qwen server is unavailable")
    if response.status_code != 200:
        pytest.skip(f"Local Qwen server is not ready (HTTP {response.status_code})")

    supplier_id = uuid.uuid4()
    source = SearchResult(
        chunk_id=uuid.uuid4(), supplier_id=supplier_id, supplier_name="Synthetic Supplier",
        document_version_id=uuid.uuid4(), filename="synthetic-proposal.pdf", page_number=1,
        text="Each laptop costs 1200 USD per unit. The warranty is 3 years. Delivery takes 14 days.",
        distance=0.0,
    )
    monkeypatch.setattr(fact_extraction, "semantic_search", lambda **kwargs: [source])
    result = fact_extraction.extract_facts_for_supplier(
        Mock(spec=Session), uuid.uuid4(), supplier_id, "Synthetic Supplier",
    )
    assert result.facts.unit_price == 1200
    assert result.facts.currency == "USD"
    assert result.facts.warranty_years == 3
    assert result.facts.delivery_days == 14
    assert set(result.evidence) == {1}
    assert result.evidence[1].chunk_id == source.chunk_id

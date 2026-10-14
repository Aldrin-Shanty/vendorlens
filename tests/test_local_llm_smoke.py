"""Opt-in real llama.cpp smoke test using synthetic evidence only."""

import os
import uuid
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from vendorlens.services import fact_extraction
from vendorlens.services.retrieval import SearchResult


@pytest.mark.skipif(
    os.getenv("RUN_LOCAL_LLM_TESTS") != "true",
    reason="Set RUN_LOCAL_LLM_TESTS=true with llama.cpp running on port 8080",
)
def test_real_local_supplier_extraction(monkeypatch):
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

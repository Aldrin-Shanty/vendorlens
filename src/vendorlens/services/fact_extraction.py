import uuid

from dataclasses import dataclass
from sqlalchemy.orm import Session

from vendorlens.services.llm import extract_supplier_facts
from vendorlens.services.retrieval import SearchResult, semantic_search
from vendorlens.services.schemas.supplier_comparison import SupplierFacts, EvidenceReference
from vendorlens.services.evidence_validation import validate_supplier_evidence
from vendorlens.services.errors import AIOutputError, SupplierSelectionError

@dataclass
class SupplierExtractionResult:
    facts: SupplierFacts
    evidence: dict[int, EvidenceReference]

def retrieve_supplier_evidence(
    db: Session,
    procurement_event_id: uuid.UUID,
    supplier_id: uuid.UUID,
) -> list[SearchResult]:
    """Retrieve evidence within the requested event and supplier."""
    supplier_results = semantic_search(
        db=db,
        procurement_event_id=procurement_event_id,
        query="unit price currency warranty period delivery timeline",
        limit=20,
        supplier_id=supplier_id,
    )

    if not supplier_results:
        raise SupplierSelectionError(
            "No proposal evidence found for this supplier"
        )

    return supplier_results


def extract_facts_from_evidence(
    supplier_name: str,
    supplier_results: list[SearchResult],
) -> SupplierFacts:
    """Build the extraction prompt and parse Qwen's structured response."""
    evidence_parts = []

    for index, result in enumerate(supplier_results, start=1):
        evidence_parts.append(
            f"[Evidence {index}]\n"
            f"Supplier: {result.supplier_name}\n"
            f"Document: {result.filename}\n"
            f"Page: {result.page_number}\n"
            f"Text: {result.text}"
        )

    evidence_text = "\n\n".join(evidence_parts)

    prompt = f"""
You are extracting supplier facts for a procurement comparison.

Supplier: {supplier_name}

Use ONLY the evidence provided below.
Do not use external knowledge.
Do not invent prices, warranties, or delivery timelines.

Return a JSON object with these fields:
- supplier_name: string
- unit_price: number or null
- currency: string or null
- unit_price_evidence: object with evidence_ids, or null
- warranty_years: number or null
- warranty_evidence: object with evidence_ids, or null
- delivery_days: integer or null
- delivery_evidence: object with evidence_ids, or null
- missing_information: list of strings

Rules:
1. Extract a value only if the evidence explicitly supports it.
2. Every extracted value must reference its evidence IDs.
3. If a value is unavailable, use null and no evidence.
4. Do not reference evidence IDs that are not provided.
5. Do not mix information from different suppliers.
6. Do not assume a currency, price unit, or delivery period.
7. Return only valid JSON, without Markdown.

Evidence:
{evidence_text}
"""

    facts = extract_supplier_facts(prompt)
    return facts


def validate_supplier_facts(
    facts: SupplierFacts,
    supplier_id: uuid.UUID,
    supplier_name: str,
    supplier_results: list[SearchResult],
) -> None:
    """Check supplier identity and cited source ownership before judgment."""
    if facts.supplier_name != supplier_name:
        raise AIOutputError(
            "Extracted supplier name does not match the requested supplier"
        )

    validate_supplier_evidence(
        facts=facts,
        supplier_id=supplier_id,
        results=supplier_results,
    )


def build_evidence_references(
    facts: SupplierFacts,
    supplier_results: list[SearchResult],
) -> dict[int, EvidenceReference]:
    """Keep only cited sources without changing their original evidence IDs."""
    cited_ids: set[int] = set()

    for evidence_field in (
        facts.unit_price_evidence,
        facts.warranty_evidence,
        facts.delivery_evidence,
    ):
        if evidence_field is not None:
            cited_ids.update(evidence_field.evidence_ids)

    evidence_map = {
        index: EvidenceReference(
            chunk_id=result.chunk_id,
            document_version_id=result.document_version_id,
            filename=result.filename,
            page_number=result.page_number,
            text=result.text,
        )
        for index, result in enumerate(
            supplier_results,
            start=1,
        )
        if index in cited_ids
    }

    return evidence_map


def extract_facts_for_supplier(
    db: Session,
    procurement_event_id: uuid.UUID,
    supplier_id: uuid.UUID,
    supplier_name: str,
) -> SupplierExtractionResult:
    """Convenience entry point for standalone extraction, including the smoke test."""
    sources = retrieve_supplier_evidence(db, procurement_event_id, supplier_id)
    facts = extract_facts_from_evidence(supplier_name, sources)
    validate_supplier_facts(facts, supplier_id, supplier_name, sources)
    evidence = build_evidence_references(facts, sources)
    return SupplierExtractionResult(facts=facts, evidence=evidence)

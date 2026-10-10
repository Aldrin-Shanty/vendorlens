from dataclasses import dataclass
import uuid

from sqlalchemy.orm import Session

from vendorlens.services.llm import generate_structured_answer
from vendorlens.services.retrieval import SearchResult, semantic_search

@dataclass
class RAGResult:
    answer: str
    retrieved_evidence: list[SearchResult]


def answer_question(
    db: Session,
    procurement_event_id: uuid.UUID,
    question: str,
) -> RAGResult:
    results = semantic_search(
        db=db,
        procurement_event_id=procurement_event_id,
        query=question,
        limit=3,
    )

    if not results:
        return RAGResult(
            answer="I could not find relevant evidence for this question.",
            retrieved_evidence=[],
        )
    evidence_parts = []

    for index, result in enumerate(results, start=1):
        evidence_parts.append(
            f"""[Evidence {index}]
                Supplier: {result.supplier_name}
                Document: {result.filename}
                Page: {result.page_number}
                Text: {result.text}"""
        )

    evidence = "\n\n".join(evidence_parts)

    prompt = f"""
You are VendorLens, a procurement analysis assistant.

Answer the question using ONLY the evidence below.

Return ONLY a JSON object with exactly these fields:
- "answer": a concise string
- "supported": a boolean
- "evidence_ids": an array of integer evidence IDs

Rules:
- Do not use outside knowledge.
- Do not invent missing information.
- Set supported to true only if the evidence answers the question.
- If supported is true, include the IDs of the supporting evidence.
- If supported is false, return an empty evidence_ids array.
- If evidence is insufficient, explain that in the answer.
- Evidence IDs must refer to the numbered evidence provided below.

Question:
{question}

Evidence:
{evidence}
"""

    structured_answer = generate_structured_answer(prompt)

    valid_evidence_ids = set(range(1, len(results)+1))

    if not set(structured_answer.evidence_ids).issubset(valid_evidence_ids):
        return RAGResult(
            answer="I could not verify the evidence references in the generated answer.",
            retrieved_evidence=results,
        )

    if not structured_answer.supported:
        return RAGResult(
            answer="The available evidence is insufficient to answer this question.",
            retrieved_evidence=results,
        )

    return RAGResult(
        answer=structured_answer.answer,
        retrieved_evidence=results,
    )

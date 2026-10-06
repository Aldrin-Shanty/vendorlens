from dataclasses import dataclass
import uuid

from sqlalchemy.orm import Session

from vendorlens.services.llm import generate_answer
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

Answer the user's question using ONLY the evidence provided below.

Rules:
- Do not use outside knowledge.
- Do not invent missing information.
- If the evidence does not contain the answer, say that the available evidence is insufficient.
- Cite supporting evidence using [Evidence 1], [Evidence 2], etc.
- Keep the answer concise.

Question:
{question}

Evidence:
{evidence}

Answer:
"""

    answer = generate_answer(prompt)

    return RAGResult(
        answer=answer,
        retrieved_evidence=results,
    )   

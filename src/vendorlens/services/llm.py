import httpx

from pydantic import ValidationError

from vendorlens.services.structured_output import GroundedAnswer
from vendorlens.services.supplier_comparison import SupplierFacts

LLM_URL = "http://127.0.0.1:8080/v1/chat/completions"


def generate_answer(prompt: str) -> str:
    response = httpx.post(
        LLM_URL,
        json={
            "messages": [
                {
                    "role": "user",
                    "content": f"/no_think\n{prompt}",
                }
            ],
            "max_tokens": 300,
            "temperature": 0.1,
        },
        timeout=60.0,
    )

    response.raise_for_status()

    data = response.json()

    return data["choices"][0]["message"]["content"]

def generate_structured_answer(prompt: str) -> GroundedAnswer:
    response = httpx.post(
        LLM_URL,
        json={
            "messages": [
                {
                    "role": "user",
                    "content": f"/no_think\n{prompt}",
                }
            ],
            "max_tokens": 400,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        },
        timeout=60.0,
    )

    response.raise_for_status()

    data = response.json()
    content = data["choices"][0]["message"]["content"]

    return GroundedAnswer.model_validate_json(content)

def extract_supplier_facts(prompt: str) -> SupplierFacts:
    response = httpx.post(
        LLM_URL,
        json={
            "messages": [
                {
                    "role": "user",
                    "content": f"/no_think\n{prompt}",
                }
            ],
            "max_tokens": 600,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        },
        timeout=60.0,
    )

    response.raise_for_status()

    data = response.json()
    content = data["choices"][0]["message"]["content"]

    return SupplierFacts.model_validate_json(content)

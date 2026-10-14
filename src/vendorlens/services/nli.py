"""Local, CPU-only premise/hypothesis classification with bounded inputs."""

import json
import threading
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from vendorlens.services.errors import AIOutputError, AIServiceUnavailableError
from vendorlens.services.schemas.supplier_comparison import Probability, Relation

MODEL = "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli"
REVISION = "6f5cf0a2b59cabb106aca4c287eed12e357e90eb"
CACHE_DIR = Path(__file__).resolve().parents[3] / "data" / "models"
MAX_STATE_BYTES = 48_000
MAX_PAIR_TOKENS = 512
LABELS: dict[str, Relation] = {
    "entailment": "supports", "neutral": "insufficient", "contradiction": "contradicts",
}
_runtime: tuple[Any, Any] | None = None
_lock = threading.Lock()


class NLIAnswer(BaseModel):
    choice: Relation
    probabilities: dict[Relation, Probability]
    confidence: Probability


class NLIResult(BaseModel):
    model: str = MODEL
    revision: str = REVISION
    answers: dict[str, NLIAnswer]
    input_tokens: int


def load_runtime(*, download: bool = False):
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        MODEL, revision=REVISION, cache_dir=str(CACHE_DIR),
        local_files_only=not download, trust_remote_code=False,
    )
    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL, revision=REVISION, cache_dir=str(CACHE_DIR), use_safetensors=True,
        local_files_only=not download, trust_remote_code=False,
    )
    model.to("cpu")
    model.eval()
    if set(str(label).lower() for label in model.config.id2label.values()) != set(LABELS):
        raise AIOutputError("Unexpected NLI model labels")
    return tokenizer, model


def judge_claims(claims: dict[str, dict]) -> NLIResult:
    global _runtime
    if not 1 <= len(claims) <= 3:
        raise AIOutputError("Evidence judgment requires one to three claims")
    if len(json.dumps(claims, ensure_ascii=False).encode("utf-8")) > MAX_STATE_BYTES:
        raise AIOutputError("Evidence judgment exceeds the state budget")

    import torch

    # Serialize loading and inference; Qwen retains the GPU for generation.
    with _lock:
        if _runtime is None:
            try:
                _runtime = load_runtime()
            except AIOutputError:
                raise
            except Exception as exc:
                raise AIServiceUnavailableError("Local NLI model is unavailable; run scripts/verify_nli.py --download") from exc
        tokenizer, model = _runtime
        answers = {}
        total_tokens = 0
        for name, claim in claims.items():
            # Evidence is the premise, extracted fact is the hypothesis.
            premise = "\n\n".join(item["text"] for item in claim["evidence"])
            inputs = tokenizer(premise, claim["claim"], truncation=False, return_tensors="pt")
            token_count = inputs["input_ids"].shape[-1]
            if token_count > MAX_PAIR_TOKENS:
                raise AIOutputError("Cited evidence exceeds the 512-token NLI pair budget")
            total_tokens += token_count
            with torch.inference_mode():
                logits = model(**inputs).logits[0]
                scores = torch.softmax(logits, dim=-1).tolist()
            probabilities = {
                LABELS[str(model.config.id2label[index]).lower()]: float(score)
                for index, score in enumerate(scores)
            }
            choice = max(probabilities, key=lambda label: probabilities[label])
            answers[name] = NLIAnswer(
                choice=choice, probabilities=probabilities, confidence=probabilities[choice],
            )
        return NLIResult(answers=answers, input_tokens=total_tokens)

"""Download explicitly, then verify four synthetic local NLI cases."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vendorlens.services import nli
from vendorlens.services.errors import AIOutputError, AIServiceUnavailableError

CASES = [
    ("supported", "The warranty is 3 years.", "supports"),
    ("contradicted", "The warranty is exactly 1 year, not 3 years.", "contradicts"),
    ("ambiguous", "Warranty duration will be negotiated after purchase.", "insufficient"),
    ("missing", "The laptops include a carrying case.", "insufficient"),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    if args.download:
        nli._runtime = nli.load_runtime(download=True)
    report: dict[str, Any] = {
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Four synthetic NLI smoke cases; not a calibrated evaluation",
        "cases": [],
    }
    for name, text, expected in CASES:
        try:
            result = nli.judge_claims({"warranty_years": {
                "claim": "The warranty is 3 years.", "evidence": [{"text": text}],
            }})
        except (AIOutputError, AIServiceUnavailableError) as exc:
            report["cases"].append({"case": name, "error": str(exc)})
            print(str(exc))
            break
        answer = result.answers["warranty_years"]
        report["cases"].append({"case": name, "expected": expected,
                                "matched": answer.choice == expected,
                                "result": result.model_dump()})
        print(f"{name}: {answer.choice} ({answer.confidence:.3f})")
    passed = len(report["cases"]) == 4 and all(case.get("matched", False) for case in report["cases"])
    report["passed"] = passed
    output = Path(__file__).resolve().parents[1] / "output" / "phase4" / "nli-live-results.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Report: {output}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

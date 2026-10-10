from unittest.mock import Mock

from vendorlens.services import llm


def test_extract_supplier_facts(monkeypatch):
    fake_response = Mock()

    fake_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": """
                    {
                        "supplier_name": "Dell",
                        "unit_price": 1200,
                        "currency": "USD",
                        "unit_price_evidence": {
                            "evidence_ids": [1]
                        },
                        "warranty_years": 3,
                        "warranty_evidence": {
                            "evidence_ids": [2]
                        },
                        "delivery_days": null,
                        "delivery_evidence": null,
                        "missing_information": ["Delivery timeline"]
                    }
                    """
                }
            }
        ]
    }

    def fake_post(*args, **kwargs):
        return fake_response

    monkeypatch.setattr(llm.httpx, "post", fake_post)

    facts = llm.extract_supplier_facts(
        "Extract supplier facts from this proposal."
    )

    assert facts.supplier_name == "Dell"
    assert facts.unit_price == 1200
    assert facts.currency == "USD"
    assert facts.warranty_years == 3
    assert facts.delivery_days is None
    assert facts.unit_price_evidence.evidence_ids == [1]
    assert facts.warranty_evidence.evidence_ids == [2]

import type { ComparisonWorkflow, Relation, Supplier } from "./api";

export function createDemoComparison(
  eventId: string,
  suppliers: Supplier[],
  eventName = "Sample procurement event",
  sequence = 1,
): ComparisonWorkflow {
  const judgment = (relation: Relation) => ({
    relation,
    confidence: 0.94,
    probabilities: {
      supports: relation === "supports" ? 0.94 : 0.03,
      contradicts: relation === "contradicts" ? 0.94 : 0.03,
      insufficient: relation === "insufficient" ? 0.94 : 0.03,
    },
  });
  return {
    workflow_id: crypto.randomUUID(),
    supplier_ids: suppliers.map((supplier) => supplier.id),
    name: `${eventName} — ${suppliers
      .map((supplier) => supplier.name)
      .sort((a, b) => a.localeCompare(b))
      .join(" + ")} (${sequence})`,
    sequence_number: sequence,
    created_at: new Date().toISOString(),
    procurement_event_id: eventId,
    status: "awaiting_review",
    budget: {
      max_model_calls: suppliers.length * 4,
      max_tool_calls: suppliers.length,
      model_calls_used: suppliers.length * 4 - 1,
      tool_calls_used: suppliers.length,
    },
    comparison: {
      procurement_event_id: eventId,
      suppliers: suppliers.map((supplier, index) => ({
        supplier_id: supplier.id,
        facts: {
          supplier_name: supplier.name,
          unit_price: 1200 + index * 150,
          currency: "USD",
          warranty_years: index === 0 ? 3 : 2,
          delivery_days: index === 1 ? null : 14 + index * 7,
          unit_price_evidence: { evidence_ids: [1] },
          warranty_evidence: { evidence_ids: [1] },
          delivery_evidence: index === 1 ? null : { evidence_ids: [1] },
          missing_information: index === 1 ? ["Delivery timeline"] : [],
        },
        judgment: {
          status: "checked",
          model: "Illustrative demo judgment",
          revision: null,
          input_tokens: 0,
          output_tokens: 0,
          facts: {
            unit_price: judgment("supports"),
            warranty_years: judgment(index === 0 ? "contradicts" : "supports"),
            ...(index === 1 ? {} : { delivery_days: judgment("supports") }),
          },
        },
        evidence: {
          "1": {
            chunk_id: `demo-chunk-${supplier.id}`,
            document_version_id: `demo-version-${supplier.id}`,
            filename: `${supplier.name.toLowerCase().replaceAll(" ", "-")}-sample.pdf`,
            page_number: index + 1,
            text: `Synthetic example: Unit price is ${1200 + index * 150} USD. Warranty is ${index === 0 ? 1 : 2} years.${index === 1 ? " Delivery is not specified." : ` Delivery takes ${14 + index * 7} days.`}`,
          },
        },
      })),
    },
    review_issues: [
      {
        supplier_id: suppliers[0].id,
        field: "warranty_years",
        reason: "contradicted",
      },
      {
        supplier_id: suppliers[1].id,
        field: "delivery_days",
        reason: "missing_value",
      },
    ],
    review_decision: null,
    error: null,
  };
}

export type Supplier = { id: string; name: string };
export type ProcurementEvent = { id: string; title: string };
export type Proposal = {
  id: string;
  supplier_id: string;
  procurement_event_id: string;
};
export type DeletionImpact = {
  proposals: number;
  documents: number;
  document_versions: number;
  evidence_chunks: number;
  comparison_workflows: number;
  comparison_workflow_ids: string[];
};
export type Evidence = {
  chunk_id: string;
  supplier_id: string;
  supplier_name: string;
  document_version_id: string;
  filename: string;
  page_number: number;
  text: string;
  distance?: number;
};
export type Answer = { answer: string; retrieved_evidence: Evidence[] };
export type Workspace = {
  suppliers: Supplier[];
  events: ProcurementEvent[];
  proposals: Proposal[];
};

export type Relation = "supports" | "contradicts" | "insufficient";
export type FactField = "unit_price" | "warranty_years" | "delivery_days";
export type ReviewDecision = {
  action: "acknowledge" | "reject";
  comment: string;
};
export type ComparisonWorkflow = {
  workflow_id: string;
  procurement_event_id: string;
  status:
    | "completed"
    | "awaiting_review"
    | "reviewed"
    | "rejected"
    | "stopped"
    | "failed";
  budget: {
    max_model_calls: number;
    max_tool_calls: number;
    model_calls_used: number;
    tool_calls_used: number;
  };
  comparison: {
    procurement_event_id: string;
    suppliers: {
      supplier_id: string;
      facts: {
        supplier_name: string;
        unit_price: number | null;
        currency: string | null;
        warranty_years: number | null;
        delivery_days: number | null;
        unit_price_evidence: { evidence_ids: number[] } | null;
        warranty_evidence: { evidence_ids: number[] } | null;
        delivery_evidence: { evidence_ids: number[] } | null;
        missing_information: string[];
      };
      judgment: {
        status: "not_checked" | "checked";
        model: string | null;
        revision: string | null;
        input_tokens: number;
        output_tokens: number;
        facts: Partial<
          Record<
            FactField,
            {
              relation: Relation;
              confidence: number;
              probabilities: Record<Relation, number>;
            }
          >
        >;
      };
      evidence: Record<
        string,
        {
          chunk_id: string;
          document_version_id: string;
          filename: string;
          page_number: number;
          text: string;
        }
      >;
    }[];
  } | null;
  review_issues: {
    supplier_id: string;
    field: FactField;
    reason:
      | "missing_value"
      | "not_checked"
      | "contradicted"
      | "insufficient"
      | "low_confidence";
  }[];
  review_decision: ReviewDecision | null;
  error: string | null;
};

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: {
      ...(options.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
      ...options.headers,
    },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail = payload?.detail;
    const validationMessage = Array.isArray(detail)
      ? detail
          .map(
            (item: { loc?: (string | number)[]; msg?: string }) =>
              `${item.loc?.filter((part) => part !== "body").join(" · ") || "Request"}: ${item.msg || "Invalid value"}`,
          )
          .join("; ")
      : null;
    throw new ApiError(
      typeof detail === "string"
        ? detail
        : validationMessage
          ? validationMessage
          : response.status === 401
            ? "Check the API key in the frontend .env file."
            : response.status >= 500
              ? `The server could not complete this operation (${response.status}). Check the backend logs and try again.`
              : `Request failed (${response.status}). Check your API connection.`,
      response.status,
    );
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

const workflowPath = (eventId: string, workflowId?: string) =>
  `/procurement-events/${encodeURIComponent(eventId)}/comparison-workflows${workflowId ? `/${encodeURIComponent(workflowId)}` : ""}`;

export const startComparison = (eventId: string, supplierIds: string[]) =>
  request<ComparisonWorkflow>(workflowPath(eventId), {
    method: "POST",
    body: JSON.stringify({ supplier_ids: supplierIds }),
  });

export const getComparison = (eventId: string, workflowId: string) =>
  request<ComparisonWorkflow>(workflowPath(eventId, workflowId));

export const reviewComparison = (
  eventId: string,
  workflowId: string,
  decision: ReviewDecision,
) =>
  request<ComparisonWorkflow>(`${workflowPath(eventId, workflowId)}/review`, {
    method: "POST",
    body: JSON.stringify(decision),
  });
export async function loadWorkspace(
  options: Pick<RequestInit, "signal"> = {},
): Promise<Workspace> {
  const [suppliers, events, proposals] = await Promise.all([
    request<Supplier[]>("/suppliers", options),
    request<ProcurementEvent[]>("/procurement-events", options),
    request<Proposal[]>("/proposals", options),
  ]);
  if (
    !Array.isArray(suppliers) ||
    !suppliers.every(
      (row) =>
        row && typeof row.id === "string" && typeof row.name === "string",
    ) ||
    !Array.isArray(events) ||
    !events.every(
      (row) =>
        row && typeof row.id === "string" && typeof row.title === "string",
    ) ||
    !Array.isArray(proposals) ||
    !proposals.every(
      (row) =>
        row &&
        typeof row.id === "string" &&
        typeof row.supplier_id === "string" &&
        typeof row.procurement_event_id === "string",
    )
  )
    throw new Error("The API returned invalid workspace data.");
  return { suppliers, events, proposals };
}

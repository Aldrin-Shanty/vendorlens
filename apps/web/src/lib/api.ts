export type Supplier = { id: string; name: string };
export type ProcurementEvent = { id: string; title: string };
export type Proposal = {
  id: string;
  supplier_id: string;
  procurement_event_id: string;
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
    throw new Error(
      typeof detail === "string"
        ? detail
        : response.status === 401
          ? "Check the API key in the frontend .env file."
          : `Request failed (${response.status}). Check your API connection.`,
    );
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
export async function loadWorkspace(): Promise<Workspace> {
  const [suppliers, events, proposals] = await Promise.all([
    request<Supplier[]>("/suppliers"),
    request<ProcurementEvent[]>("/procurement-events"),
    request<Proposal[]>("/proposals"),
  ]);
  return { suppliers, events, proposals };
}

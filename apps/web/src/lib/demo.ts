import type { Workspace, Evidence } from "./api";
export const demoWorkspace: Workspace = {
  suppliers: [
    { id: "s1", name: "Northstar Technologies" },
    { id: "s2", name: "Acme Infrastructure" },
    { id: "s3", name: "Vertex Solutions" },
    { id: "s4", name: "Evergreen Systems" },
    { id: "s5", name: "Meridian Partners" },
  ],
  events: [
    { id: "e1", title: "Cloud infrastructure modernization" },
    { id: "e2", title: "Enterprise security platform" },
    { id: "e3", title: "Workplace technology refresh" },
    { id: "e4", title: "Customer support operations" },
  ],
  proposals: [
    { id: "p1", supplier_id: "s1", procurement_event_id: "e1" },
    { id: "p2", supplier_id: "s2", procurement_event_id: "e1" },
    { id: "p3", supplier_id: "s3", procurement_event_id: "e1" },
    { id: "p4", supplier_id: "s4", procurement_event_id: "e2" },
    { id: "p5", supplier_id: "s1", procurement_event_id: "e2" },
    { id: "p6", supplier_id: "s5", procurement_event_id: "e3" },
  ],
};
export const demoEvidence: Evidence[] = [
  {
    chunk_id: "c1",
    supplier_id: "s1",
    supplier_name: "Northstar Technologies",
    document_version_id: "v1",
    filename: "northstar-cloud-proposal.pdf",
    page_number: 12,
    text: "The proposed service includes 24/7 monitoring and a 99.95% availability commitment. Critical incidents receive an initial response within 15 minutes. Migration support is included for the first 90 days.",
    distance: 0.12,
  },
  {
    chunk_id: "c2",
    supplier_id: "s2",
    supplier_name: "Acme Infrastructure",
    document_version_id: "v2",
    filename: "acme-service-agreement.pdf",
    page_number: 8,
    text: "The managed infrastructure service provides 99.9% availability. Support is available during business hours, with an optional premium tier for round-the-clock incident response.",
    distance: 0.18,
  },
  {
    chunk_id: "c3",
    supplier_id: "s3",
    supplier_name: "Vertex Solutions",
    document_version_id: "v3",
    filename: "vertex-technical-response.pdf",
    page_number: 16,
    text: "Enterprise support includes a dedicated technical account manager and 24/7 incident response. The availability target is 99.95%, subject to the exclusions in section 4.2.",
    distance: 0.21,
  },
];

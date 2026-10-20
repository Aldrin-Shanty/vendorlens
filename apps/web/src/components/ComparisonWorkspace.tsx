import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  ArrowRight,
  Check,
  FileText,
  GitCompareArrows,
  Loader2,
  RefreshCw,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import {
  ApiError,
  getComparison,
  reviewComparison,
  startComparison,
  listComparisons,
  deleteComparison,
  deleteAllComparisons,
  type WorkflowSummary,
  type ComparisonWorkflow,
  type FactField,
  type ReviewDecision,
  type Workspace,
} from "@/lib/api";
import { createDemoComparison } from "@/lib/comparison-demo";

const fields: {
  key: FactField;
  label: string;
  evidence: "unit_price_evidence" | "warranty_evidence" | "delivery_evidence";
}[] = [
  { key: "unit_price", label: "Unit price", evidence: "unit_price_evidence" },
  { key: "warranty_years", label: "Warranty", evidence: "warranty_evidence" },
  { key: "delivery_days", label: "Delivery", evidence: "delivery_evidence" },
];
const statusLabels: Record<ComparisonWorkflow["status"], string> = {
  running: "Running",
  completed: "Completed",
  awaiting_review: "Awaiting review",
  reviewed: "Reviewed",
  rejected: "Rejected",
  stopped: "Stopped",
  failed: "Failed",
};
const reasons = {
  missing_value: "Value missing",
  not_checked: "Not checked",
  contradicted: "Source contradicts this fact",
  insufficient: "Insufficient evidence",
  low_confidence: "Low confidence",
};
const storageKey = "vendorlens.workflow-references.v1";
type SavedRun = { eventId: string; id: string };
const uuidPattern =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function savedRuns(): SavedRun[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(storageKey) || "[]");
    return Array.isArray(value)
      ? value
          .filter(
            (item): item is SavedRun =>
              item &&
              typeof item.eventId === "string" &&
              typeof item.id === "string" &&
              uuidPattern.test(item.id),
          )
          .slice(0, 30)
      : [];
  } catch {
    return [];
  }
}

export function ComparisonWorkspace({
  data,
  demo,
  eventId,
  onEventChange,
}: {
  data: Workspace;
  demo: boolean;
  eventId: string;
  onEventChange: (id: string) => void;
}) {
  const [selected, setSelected] = useState<string[]>([]);
  const [workflow, setWorkflow] = useState<ComparisonWorkflow | null>(null);
  const [runs, setRuns] = useState<WorkflowSummary[]>([]);
  const [listLoading, setListLoading] = useState(false);
  const [listError, setListError] = useState("");
  const [listRevision, setListRevision] = useState(0);
  const [deleteTarget, setDeleteTarget] = useState<
    | { kind: "one"; run: WorkflowSummary }
    | { kind: "all"; count: number }
    | null
  >(null);
  const [lookupId, setLookupId] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [comment, setComment] = useState("");
  const [action, setAction] = useState<ReviewDecision["action"] | "">("");
  const mounted = useRef(true);
  const demoRuns = useRef(new Map<string, ComparisonWorkflow>());
  const demoSequences = useRef<Record<string, number>>({});
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  useEffect(() => {
    if (demo || !eventId) return;
    const controller = new AbortController();
    setListLoading(true);
    setListError("");
    void listComparisons(eventId, controller.signal)
      .then((items) => {
        if (!controller.signal.aborted) {
          setRuns(items);
          setWorkflow((current) => {
            const updated = items.find(
              (item) => item.workflow_id === current?.workflow_id,
            );
            return current && updated
              ? {
                  ...current,
                  name: updated.name,
                  sequence_number: updated.sequence_number,
                }
              : current;
          });
        }
      })
      .catch((err) => {
        if (!controller.signal.aborted)
          setListError(
            err instanceof Error
              ? err.message
              : "Unable to load saved workflows.",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setListLoading(false);
      });
    return () => controller.abort();
  }, [demo, eventId, listRevision]);

  const eligibleIds = new Set(
    data.proposals
      .filter((p) => p.procurement_event_id === eventId)
      .map((p) => p.supplier_id),
  );
  const suppliers = data.suppliers.filter((s) => eligibleIds.has(s.id));
  const selection = selected.filter(
    (id) => eligibleIds.has(id) && data.suppliers.some((s) => s.id === id),
  );

  const accept = (result: ComparisonWorkflow) => {
    let storageNotice = "";
    if (demo) demoRuns.current.set(result.workflow_id, result);
    // Preserve the reference even if the user left this page during extraction.
    if (!demo) {
      const updated = [
        { eventId, id: result.workflow_id },
        ...savedRuns().filter((run) => run.id !== result.workflow_id),
      ].slice(0, 30);
      try {
        localStorage.setItem(storageKey, JSON.stringify(updated));
      } catch {
        storageNotice =
          "Workflow saved on the server. Keep its ID to reopen it; this browser could not save the reference.";
      }
    }
    if (!mounted.current) return;
    setRuns((previous) => [
      result,
      ...previous.filter((run) => run.workflow_id !== result.workflow_id),
    ]);
    setWorkflow(result);
    setLookupId(result.workflow_id);
    setComment("");
    setAction("");
    if (storageNotice) setNotice(storageNotice);
  };

  const start = async () => {
    if (!eventId || selection.length < 2 || selection.length > 8 || busy)
      return;
    setBusy("Starting comparison");
    setError("");
    setNotice("");
    try {
      const group = [...selection].sort().join(",");
      if (demo)
        demoSequences.current[group] = (demoSequences.current[group] || 0) + 1;
      const result = demo
        ? createDemoComparison(
            eventId,
            suppliers.filter((s) => selection.includes(s.id)),
            data.events.find((event) => event.id === eventId)?.title,
            demoSequences.current[group],
          )
        : await startComparison(eventId, selection);
      accept(result);
    } catch (err) {
      if (mounted.current)
        setError(
          err instanceof Error ? err.message : "Unable to start comparison.",
        );
    } finally {
      if (mounted.current) setBusy("");
    }
  };

  const load = async (id: string) => {
    if (!eventId || busy) return;
    if (!uuidPattern.test(id.trim())) {
      setError("Enter a valid workflow UUID.");
      return;
    }
    setBusy("Loading workflow");
    setError("");
    setNotice("");
    try {
      accept(await getComparison(eventId, id.trim()));
    } catch (err) {
      if (mounted.current)
        setError(
          err instanceof Error ? err.message : "Unable to load workflow.",
        );
      if (mounted.current && err instanceof ApiError && err.status === 404) {
        setRuns((previous) =>
          previous.filter((run) => run.workflow_id !== id.trim()),
        );
        if (workflow?.workflow_id === id.trim()) setWorkflow(null);
      }
    } finally {
      if (mounted.current) setBusy("");
    }
  };

  const requestDeleteAll = async () => {
    setBusy("Checking saved workflows");
    setError("");
    try {
      const all = demo ? runs : await listComparisons();
      if (mounted.current) {
        if (all.length) setDeleteTarget({ kind: "all", count: all.length });
        else setNotice("There are no saved workflows to delete.");
      }
    } catch (err) {
      if (mounted.current)
        setError(
          err instanceof Error
            ? err.message
            : "Unable to check saved workflows.",
        );
    } finally {
      if (mounted.current) setBusy("");
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget || busy) return;
    const target = deleteTarget;
    setBusy("Deleting workflows");
    setError("");
    try {
      if (!demo) {
        if (target.kind === "all") await deleteAllComparisons();
        else
          await deleteComparison(
            target.run.procurement_event_id,
            target.run.workflow_id,
          );
      }
      if (!mounted.current) return;
      if (demo) {
        if (target.kind === "all") demoRuns.current.clear();
        else demoRuns.current.delete(target.run.workflow_id);
        demoSequences.current = {};
        const remaining = [...demoRuns.current.values()].sort(
          (a, b) => a.sequence_number - b.sequence_number,
        );
        for (const run of remaining) {
          const key = [...run.supplier_ids].sort().join(",");
          const number = (demoSequences.current[key] || 0) + 1;
          demoSequences.current[key] = number;
          run.sequence_number = number;
          run.name = run.name.replace(/ \(\d+\)$/, ` (${number})`);
        }
        setRuns(remaining.reverse());
        setWorkflow((current) =>
          current
            ? { ...(demoRuns.current.get(current.workflow_id) || current) }
            : current,
        );
      } else {
        setRuns((previous) =>
          target.kind === "all"
            ? []
            : previous.filter(
                (run) => run.workflow_id !== target.run.workflow_id,
              ),
        );
        setListRevision((value) => value + 1);
      }
      if (
        target.kind === "all" ||
        workflow?.workflow_id === target.run.workflow_id
      ) {
        setWorkflow(null);
        setLookupId("");
        setComment("");
        setAction("");
      }
      try {
        if (!demo)
          localStorage.setItem(
            storageKey,
            JSON.stringify(
              target.kind === "all"
                ? []
                : savedRuns().filter(
                    (run) => run.id !== target.run.workflow_id,
                  ),
            ),
          );
      } catch {
        /* The server list is authoritative when browser storage is unavailable. */
      }
      setDeleteTarget(null);
      setNotice(
        target.kind === "all"
          ? "All saved workflows deleted. Source proposals and PDFs are kept."
          : "Workflow deleted. Source proposals and PDFs are kept.",
      );
    } catch (err) {
      if (mounted.current)
        setError(
          err instanceof Error
            ? err.message
            : "Unable to delete saved workflows.",
        );
    } finally {
      if (mounted.current) setBusy("");
    }
  };

  const submitReview = async (event: FormEvent) => {
    event.preventDefault();
    if (
      !workflow ||
      workflow.status !== "awaiting_review" ||
      !action ||
      !comment.trim() ||
      busy
    )
      return;
    setBusy("Saving review");
    setError("");
    setNotice("");
    const decision: ReviewDecision = { action, comment: comment.trim() };
    try {
      const result: ComparisonWorkflow = demo
        ? {
            ...workflow,
            status: action === "acknowledge" ? "reviewed" : "rejected",
            review_decision: decision,
          }
        : await reviewComparison(eventId, workflow.workflow_id, decision);
      accept(result);
      if (mounted.current)
        setNotice(
          demo
            ? "Sample review recorded for this preview."
            : "Review decision saved.",
        );
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        try {
          accept(await getComparison(eventId, workflow.workflow_id));
        } catch {
          /* Keep the displayed result until a refresh succeeds. */
        }
      }
      if (mounted.current)
        setError(
          err instanceof Error
            ? err.message
            : "Unable to save review. Refresh the saved state before retrying.",
        );
    } finally {
      if (mounted.current) setBusy("");
    }
  };

  return (
    <div className="comparison-workspace">
      <section className="panel comparison-setup">
        <div className="panel-heading">
          <div>
            <h2>Compare the details</h2>
            <p>
              Select suppliers, inspect their evidence, and record your review.
            </p>
          </div>
          <span className="stat-icon mint">
            <GitCompareArrows size={20} />
          </span>
        </div>
        <div className="comparison-controls">
          <label>
            Procurement event
            <select
              aria-label="Procurement event"
              value={eventId}
              disabled={!!busy || !data.events.length}
              onChange={(e) => onEventChange(e.target.value)}
            >
              {!data.events.length && (
                <option value="">No events available</option>
              )}
              {data.events.map((event) => (
                <option key={event.id} value={event.id}>
                  {event.title}
                </option>
              ))}
            </select>
          </label>
          <fieldset disabled={!!busy}>
            <legend>
              Suppliers with proposals{" "}
              <span>{selection.length}/8 selected</span>
            </legend>
            <div className="comparison-supplier-options">
              {suppliers.map((supplier) => (
                <label key={supplier.id}>
                  <input
                    type="checkbox"
                    checked={selection.includes(supplier.id)}
                    disabled={
                      !selection.includes(supplier.id) && selection.length >= 8
                    }
                    onChange={(e) =>
                      setSelected(
                        e.target.checked
                          ? [...selection, supplier.id]
                          : selection.filter((id) => id !== supplier.id),
                      )
                    }
                  />
                  {supplier.name}
                </label>
              ))}
            </div>
            {suppliers.length < 2 && (
              <p className="comparison-hint">
                Add proposals for at least two suppliers in this event to
                compare them.
              </p>
            )}
          </fieldset>
          <div className="comparison-start">
            <p>
              Choose 2–8 suppliers.
              {demo
                ? " Explore illustrative facts and a sample review."
                : " Upload proposal PDFs first. Extraction may take a moment."}
            </p>
            <Button
              disabled={!!busy || selection.length < 2 || !eventId}
              onClick={start}
            >
              {busy === "Starting comparison" ? (
                <Loader2 size={16} className="spin" />
              ) : (
                <GitCompareArrows size={16} />
              )}
              {demo ? "Preview comparison" : "Start comparison"}
            </Button>
          </div>
        </div>
      </section>

      <section className="panel saved-workflows">
        <div className="panel-heading">
          <div>
            <h2>Saved workflows</h2>
            <p>
              Comparisons for this procurement event, saved with their review
              decisions.
            </p>
          </div>
          <div className="saved-workflow-actions">
            {!demo && (
              <Button
                variant="outline"
                disabled={!!busy || listLoading}
                onClick={() => setListRevision((value) => value + 1)}
              >
                <RefreshCw size={15} />
                Refresh list
              </Button>
            )}
            <Button
              variant="outline"
              disabled={!!busy}
              onClick={requestDeleteAll}
            >
              <Trash2 size={15} />
              Delete all workflows
            </Button>
          </div>
        </div>
        {listLoading && <p role="status">Loading saved workflows…</p>}
        {listError && (
          <p className="error" role="alert">
            {listError}
          </p>
        )}
        {!listLoading && !listError && !runs.length && (
          <p className="comparison-hint">No saved workflows for this event.</p>
        )}
        {runs.map((run) => (
          <div className="saved-workflow-row" key={run.workflow_id}>
            <button
              className="saved-workflow-open"
              disabled={!!busy}
              aria-label={`Open ${run.name}`}
              onClick={() => {
                const sample = demoRuns.current.get(run.workflow_id);
                if (demo && sample) accept(sample);
                else if (!demo) void load(run.workflow_id);
              }}
            >
              <strong>{run.name}</strong>
              <span>
                {statusLabels[run.status]} ·{" "}
                {new Date(run.created_at).toLocaleString()}
              </span>
            </button>
            <Button
              variant="outline"
              disabled={!!busy}
              aria-label={`Delete ${run.name}`}
              onClick={() => {
                setError("");
                setDeleteTarget({ kind: "one", run });
              }}
            >
              <Trash2 size={16} />
            </Button>
          </div>
        ))}
        {!demo && (
          <details className="workflow-technical">
            <summary>Open by workflow ID</summary>
            <form
              className="workflow-lookup"
              onSubmit={(e) => {
                e.preventDefault();
                void load(lookupId);
              }}
            >
              <label className="sr-only" htmlFor="workflow-id">
                Workflow ID
              </label>
              <input
                id="workflow-id"
                placeholder="Workflow UUID"
                value={lookupId}
                onChange={(e) => setLookupId(e.target.value)}
                disabled={!!busy}
                required
              />
              <Button
                variant="outline"
                disabled={!!busy || !eventId || !lookupId.trim()}
              >
                Open workflow <ArrowRight size={15} />
              </Button>
            </form>
          </details>
        )}
      </section>
      <Dialog
        open={!!deleteTarget}
        onOpenChange={(open) => {
          if (!open && !busy) {
            setDeleteTarget(null);
            setError("");
          }
        }}
        title={
          deleteTarget?.kind === "all"
            ? "Delete all workflows?"
            : "Delete this workflow?"
        }
        description={
          deleteTarget?.kind === "all"
            ? `Delete ${deleteTarget.count} saved workflow(s) across all procurement events? Source proposals and PDFs are kept.`
            : `Delete ${deleteTarget?.kind === "one" ? deleteTarget.run.name : "this comparison"} and its review decisions? Source proposals and PDFs are kept.`
        }
      >
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <div className="saved-workflow-actions">
          <Button
            variant="outline"
            disabled={!!busy}
            onClick={() => {
              setDeleteTarget(null);
              setError("");
            }}
          >
            Cancel
          </Button>
          <Button
            variant="destructive"
            disabled={!!busy}
            onClick={confirmDelete}
          >
            {busy === "Deleting workflows" ? "Deleting…" : "Confirm deletion"}
          </Button>
        </div>
      </Dialog>

      {error && !deleteTarget && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      {notice && (
        <div className="comparison-notice" role="status">
          <Check size={16} />
          {notice}
        </div>
      )}
      {busy && (
        <div className="comparison-progress" role="status">
          <Loader2 className="spin" size={18} />
          <span>
            {busy}…{" "}
            {busy === "Starting comparison" &&
              "Retrieving evidence and checking supplier facts."}
          </span>
        </div>
      )}

      {!workflow ? (
        <section className="panel comparison-empty">
          <span className="assistant-orb">
            <GitCompareArrows size={30} />
          </span>
          <h2>From proposals to a clearer comparison.</h2>
          <p>
            Unit prices, warranties, delivery timelines, and the sources behind
            every fact. Start with two suppliers above.
          </p>
          <div>
            <span>01 · Extract facts</span>
            <span>02 · Check evidence</span>
            <span>03 · Human review</span>
          </div>
        </section>
      ) : (
        <>
          <section className="panel comparison-summary">
            <div>
              <span className={`workflow-status workflow-${workflow.status}`}>
                {statusLabels[workflow.status]}
              </span>
              {demo && (
                <span className="badge badge-gray">Illustrative demo</span>
              )}
              <h2>{workflow.name}</h2>
              <details className="workflow-technical">
                <summary>Workflow details</summary>
                <p className="workflow-id">
                  Workflow ID <code>{workflow.workflow_id}</code>
                </p>
              </details>
            </div>
            {!demo && (
              <Button
                variant="outline"
                disabled={!!busy}
                onClick={() => load(workflow.workflow_id)}
              >
                <RefreshCw size={15} />
                Refresh status
              </Button>
            )}
            <div className="comparison-usage">
              <span>
                Model calls{" "}
                <strong>
                  {workflow.budget.model_calls_used} /{" "}
                  {workflow.budget.max_model_calls}
                </strong>
              </span>
              <span>
                Retrievals{" "}
                <strong>
                  {workflow.budget.tool_calls_used} /{" "}
                  {workflow.budget.max_tool_calls}
                </strong>
              </span>
              <span>
                Review issues <strong>{workflow.review_issues.length}</strong>
              </span>
            </div>
            {workflow.error && (
              <p className="comparison-failure" role="alert">
                {workflow.error}
              </p>
            )}
            {workflow.status === "completed" && (
              <p className="comparison-hint">
                No review issues were found by the configured checks. Inspect
                the cited sources before making a procurement decision.
              </p>
            )}
          </section>

          {workflow.comparison && (
            <div className="comparison-cards">
              {workflow.comparison.suppliers.map((entry) => (
                <article
                  className="panel comparison-supplier-card"
                  key={entry.supplier_id}
                >
                  <div className="panel-heading">
                    <div>
                      <span className="eyebrow">SUPPLIER FACTS</span>
                      <h2>{entry.facts.supplier_name}</h2>
                    </div>
                    <span className="stat-icon lavender">
                      <FileText size={19} />
                    </span>
                  </div>
                  <div className="comparison-facts">
                    {fields.map((field) => {
                      const value = entry.facts[field.key];
                      const judgment =
                        entry.judgment.status === "checked"
                          ? entry.judgment.facts[field.key]
                          : undefined;
                      const issues = workflow.review_issues.filter(
                        (issue) =>
                          issue.supplier_id === entry.supplier_id &&
                          issue.field === field.key,
                      );
                      const formatted =
                        value === null
                          ? "Not provided"
                          : field.key === "unit_price"
                            ? `${value.toLocaleString()} ${entry.facts.currency || ""}`
                            : `${value} ${field.key === "warranty_years" ? "years" : "days"}`;
                      return (
                        <div className="comparison-fact" key={field.key}>
                          <div>
                            <span>{field.label}</span>
                            <strong>{formatted}</strong>
                          </div>
                          <div className="fact-context">
                            {judgment ? (
                              <span
                                className={`fact-judgment fact-${judgment.relation}`}
                                title="Model confidence is not a calibrated probability of truth."
                              >
                                {judgment.relation === "supports"
                                  ? "Supported"
                                  : judgment.relation === "contradicts"
                                    ? "Contradicted"
                                    : "Insufficient evidence"}{" "}
                                · {Math.round(judgment.confidence * 100)}%
                              </span>
                            ) : (
                              <span className="fact-judgment">
                                {value === null
                                  ? "Missing information"
                                  : "Not checked"}
                              </span>
                            )}
                            <span className="fact-citations">
                              {entry.facts[field.evidence]?.evidence_ids.map(
                                (id) => (
                                  <a
                                    key={id}
                                    href={`#source-${workflow.workflow_id}-${entry.supplier_id}-${id}`}
                                    aria-label={`${entry.facts.supplier_name} ${field.label} source ${id}`}
                                    onClick={() => {
                                      const source = document.getElementById(
                                        `source-${workflow.workflow_id}-${entry.supplier_id}-${id}`,
                                      );
                                      if (source instanceof HTMLDetailsElement)
                                        source.open = true;
                                    }}
                                  >
                                    [{id}]
                                  </a>
                                ),
                              )}
                            </span>
                          </div>
                          {issues.map((issue) => (
                            <p className="fact-issue" key={issue.reason}>
                              {reasons[issue.reason]}
                            </p>
                          ))}
                        </div>
                      );
                    })}
                  </div>
                  <div className="comparison-sources">
                    <h3>Cited evidence</h3>
                    {!Object.keys(entry.evidence).length && (
                      <p className="comparison-hint">
                        No cited passages are available for these facts.
                      </p>
                    )}
                    {Object.entries(entry.evidence).map(([id, source]) => (
                      <details
                        key={id}
                        id={`source-${workflow.workflow_id}-${entry.supplier_id}-${id}`}
                      >
                        <summary>
                          <FileText size={14} />
                          <span>
                            [{id}] {source.filename}
                          </span>
                          <span>p. {source.page_number}</span>
                        </summary>
                        <blockquote>{source.text}</blockquote>
                        <dl>
                          <dt>Document version</dt>
                          <dd>{source.document_version_id}</dd>
                          <dt>Source chunk</dt>
                          <dd>{source.chunk_id}</dd>
                        </dl>
                      </details>
                    ))}
                    <p className="comparison-model">
                      {entry.judgment.status === "checked" ? (
                        <>
                          Judgment model: {entry.judgment.model}
                          {entry.judgment.revision && (
                            <> · Revision {entry.judgment.revision}</>
                          )}
                        </>
                      ) : (
                        "Semantic evidence checks were not performed."
                      )}
                    </p>
                    {!!entry.facts.missing_information.length && (
                      <p className="comparison-hint">
                        Missing information:{" "}
                        {entry.facts.missing_information.join("; ")}
                      </p>
                    )}
                  </div>
                </article>
              ))}
            </div>
          )}

          <section className="panel comparison-review">
            <div className="panel-heading">
              <div>
                <h2>
                  <ShieldCheck size={19} />
                  Human review
                </h2>
                <p>
                  Review the facts against the cited passages. Model confidence
                  is not calibrated truth.
                </p>
              </div>
            </div>
            {workflow.status === "awaiting_review" ? (
              <form onSubmit={submitReview}>
                <p>
                  {workflow.review_issues.length} issue
                  {workflow.review_issues.length === 1 ? "" : "s"} need
                  attention. Acknowledgment records your review; it does not
                  correct facts or approve a purchase.
                </p>
                <label>
                  Review decision
                  <select
                    aria-label="Review decision"
                    required
                    value={action}
                    disabled={!!busy}
                    onChange={(e) =>
                      setAction(e.target.value as ReviewDecision["action"] | "")
                    }
                  >
                    <option value="">Choose a decision</option>
                    <option value="acknowledge">Acknowledge issues</option>
                    <option value="reject">Reject comparison</option>
                  </select>
                </label>
                <label htmlFor="review-comment">Review comment</label>
                <textarea
                  id="review-comment"
                  required
                  maxLength={1000}
                  rows={3}
                  value={comment}
                  disabled={!!busy}
                  onChange={(e) => setComment(e.target.value)}
                  placeholder="Record what you checked and any remaining gaps."
                />
                <div className="comparison-review-actions">
                  <span>{comment.length}/1000 characters</span>
                  <Button
                    type="submit"
                    disabled={!!busy || !action || !comment.trim()}
                  >
                    {busy === "Saving review" ? (
                      <Loader2 className="spin" size={16} />
                    ) : (
                      <Check size={16} />
                    )}
                    {demo ? "Record sample review" : "Submit review"}
                  </Button>
                </div>
              </form>
            ) : workflow.review_decision ? (
              <div className="comparison-decision">
                <strong>
                  {workflow.review_decision.action === "acknowledge"
                    ? "Issues acknowledged"
                    : "Comparison rejected"}
                </strong>
                <p>{workflow.review_decision.comment}</p>
                <span>
                  The original comparison and review issues remain available
                  above.
                </span>
              </div>
            ) : (
              <p className="comparison-review-unavailable">
                {workflow.status === "completed"
                  ? "This workflow finished without a review pause."
                  : "Review is unavailable because this workflow did not reach a review pause."}
              </p>
            )}
          </section>
        </>
      )}
    </div>
  );
}

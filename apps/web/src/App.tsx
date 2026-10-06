import { useEffect, useState, type FormEvent } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  Building2,
  Check,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  FileText,
  FolderKanban,
  LayoutDashboard,
  Loader2,
  Menu,
  Plus,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  Upload,
  X,
  RefreshCw,
  ExternalLink,
  Pencil,
  Trash2,
  Network,
  Layers3,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import {
  loadWorkspace,
  request,
  type Workspace,
  type Evidence,
  type Answer,
} from "@/lib/api";
import { demoWorkspace, demoEvidence } from "@/lib/demo";

type Page =
  | "Overview"
  | "Procurement events"
  | "Suppliers"
  | "Proposals"
  | "Evidence assistant";
type Editor = {
  kind: "event" | "supplier" | "proposal";
  id?: string;
  value?: string;
} | null;
const nav = [
  { name: "Overview", icon: LayoutDashboard },
  { name: "Procurement events", icon: FolderKanban },
  { name: "Suppliers", icon: Building2 },
  { name: "Proposals", icon: FileText },
  { name: "Evidence assistant", icon: Sparkles },
] as const;
const colors = ["mint", "lavender", "peach", "blue", "yellow"];
const initials = (name: string) =>
  name
    .split(" ")
    .slice(0, 2)
    .map((word) => word[0])
    .join("")
    .toUpperCase();

export default function App() {
  const [page, setPage] = useState<Page>("Overview");
  const [data, setData] = useState<Workspace>(structuredClone(demoWorkspace));
  const [demo, setDemo] = useState(true);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [query, setQuery] = useState("");
  const [eventId, setEventId] = useState("e1");
  const [editor, setEditor] = useState<Editor>(null);
  const [settings, setSettings] = useState(false);
  const [help, setHelp] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const [deleteItem, setDeleteItem] = useState<{
    kind: "supplier" | "event" | "proposal";
    id: string;
    name: string;
  } | null>(null);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [searchMode, setSearchMode] = useState(false);
  const [uploadId, setUploadId] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [uploadError, setUploadError] = useState("");
  useEffect(() => {
    if (notice) {
      const timer = setTimeout(() => setNotice(""), 5000);
      return () => clearTimeout(timer);
    }
  }, [notice]);
  useEffect(() => {
    if (!data.events.some((event) => event.id === eventId)) {
      setEventId(data.events[0]?.id || "");
      setAnswer(null);
      setEvidence([]);
    }
  }, [data.events, eventId]);
  const navigate = (next: Page) => {
    setPage(next);
    setQuery("");
    setMobileNav(false);
    setError("");
  };
  const supplierName = (id: string) =>
    data.suppliers.find((s) => s.id === id)?.name || "Unknown supplier";
  const eventTitle = (id: string) =>
    data.events.find((e) => e.id === id)?.title || "Unknown event";
  const activeEvent = data.events.find((e) => e.id === eventId);
  const refresh = async () => {
    setLoading(true);
    setError("");
    try {
      const workspace = await loadWorkspace();
      setData(workspace);
      setDemo(false);
      setEventId(workspace.events[0]?.id || "");
      setAnswer(null);
      setEvidence([]);
      setSettings(false);
      setNotice("Connected to your VendorLens API.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to connect.");
    } finally {
      setLoading(false);
    }
  };
  const useDemo = () => {
    setData(structuredClone(demoWorkspace));
    setDemo(true);
    setEventId("e1");
    setAnswer(null);
    setEvidence([]);
    setSettings(false);
    setError("");
    setNotice("Demo workspace loaded. Changes stay in this session.");
  };
  const save = async (ev: FormEvent<HTMLFormElement>) => {
    ev.preventDefault();
    if (!editor) return;
    const form = new FormData(ev.currentTarget);
    const value = String(form.get("name") || "").trim();
    if (editor.kind !== "proposal" && !value) {
      setError("Enter a name before saving.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const collection =
        editor.kind === "supplier"
          ? "suppliers"
          : editor.kind === "event"
            ? "events"
            : "proposals";
      const endpoint =
        editor.kind === "event" ? "procurement-events" : collection;
      const payload =
        editor.kind === "supplier"
          ? { name: value }
          : editor.kind === "event"
            ? { title: value }
            : {
                supplier_id: String(form.get("supplier")),
                procurement_event_id: String(form.get("event")),
              };
      if (
        editor.kind === "proposal" &&
        data.proposals.some(
          (p) =>
            p.supplier_id ===
              (payload as { supplier_id: string }).supplier_id &&
            p.procurement_event_id ===
              (payload as { procurement_event_id: string })
                .procurement_event_id,
        )
      )
        throw new Error("This supplier already has a proposal for this event.");
      const item = demo
        ? { ...payload, id: editor.id || crypto.randomUUID() }
        : await request(`/${endpoint}${editor.id ? `/${editor.id}` : ""}`, {
            method: editor.id ? "PUT" : "POST",
            body: JSON.stringify(payload),
          });
      if (demo)
        setData(
          (prev) =>
            ({
              ...prev,
              [collection]: editor.id
                ? prev[collection].map((row) =>
                    row.id === editor.id ? item : row,
                  )
                : [...prev[collection], item],
            }) as Workspace,
        );
      else setData(await loadWorkspace());
      setEditor(null);
      setNotice(
        `${editor.kind === "event" ? "Procurement event" : editor.kind === "supplier" ? "Supplier" : "Proposal"} ${editor.id ? "updated" : "created"}${demo ? " in demo mode" : ""}.`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save.");
    } finally {
      setBusy(false);
    }
  };
  const remove = async () => {
    if (!deleteItem) return;
    setBusy(true);
    setError("");
    try {
      const { kind, id } = deleteItem;
      if (
        kind !== "proposal" &&
        data.proposals.some((p) =>
          kind === "event"
            ? p.procurement_event_id === id
            : p.supplier_id === id,
        )
      )
        throw new Error(
          "Remove associated proposals before deleting this record.",
        );
      const collection =
        kind === "event"
          ? "events"
          : kind === "supplier"
            ? "suppliers"
            : "proposals";
      if (!demo)
        await request(
          `/${kind === "event" ? "procurement-events" : collection}/${id}`,
          { method: "DELETE" },
        );
      setData((prev) => ({
        ...prev,
        [collection]: prev[collection].filter((row) => row.id !== id),
      }));
      setDeleteItem(null);
      setNotice("Record deleted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to delete.");
    } finally {
      setBusy(false);
    }
  };
  const ask = async (ev?: FormEvent, prompt?: string) => {
    ev?.preventDefault();
    const text = (prompt || question).trim();
    if (!text || !eventId) return;
    setQuestion(text);
    setBusy(true);
    setError("");
    setAnswer(null);
    setEvidence([]);
    try {
      if (demo) {
        const rows = eventId === "e1" ? demoEvidence : [];
        if (searchMode) setEvidence(rows);
        else
          setAnswer({
            answer: rows.length
              ? "Sample answer: Northstar and Vertex both state a 99.95% availability commitment. Northstar includes 24/7 monitoring and a 15-minute initial response for critical incidents [1]. Acme states 99.9% availability, with 24/7 support offered as an optional premium tier [2]. Vertex includes a dedicated account manager, but its availability target is subject to exclusions [3]. Review the source pages before making a decision."
              : "There is no sample evidence for this event. Select Cloud infrastructure modernization to explore the demo.",
            retrieved_evidence: rows,
          });
      } else if (searchMode)
        setEvidence(
          await request<Evidence[]>(`/procurement-events/${eventId}/search`, {
            method: "POST",
            body: JSON.stringify({ query: text, limit: 5 }),
          }),
        );
      else
        setAnswer(
          await request<Answer>(`/procurement-events/${eventId}/ask`, {
            method: "POST",
            body: JSON.stringify({ question: text }),
          }),
        );
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to retrieve evidence.",
      );
    } finally {
      setBusy(false);
    }
  };
  const upload = async (ev: FormEvent) => {
    ev.preventDefault();
    if (!file || !uploadId) return;
    if (
      !file.name.toLowerCase().endsWith(".pdf") ||
      file.type !== "application/pdf"
    ) {
      setUploadError("Choose a PDF document.");
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setUploadError("PDF files must be 10 MB or smaller.");
      return;
    }
    setBusy(true);
    setUploadError("");
    try {
      if (!demo) {
        const body = new FormData();
        body.append("file", file);
        await request(`/proposals/${uploadId}/documents`, {
          method: "POST",
          body,
        });
      }
      setNotice(
        demo
          ? `Demo preview: ${file.name} selected. Connect the API to upload and ingest it.`
          : `${file.name} uploaded and ingested.`,
      );
      setUploadId(null);
      setFile(null);
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setBusy(false);
    }
  };
  const openEditor = (
    kind: "event" | "supplier" | "proposal",
    id?: string,
    value?: string,
  ) => {
    setError("");
    setEditor({ kind, id, value });
  };
  const filteredEvents = data.events.filter((e) =>
    e.title.toLowerCase().includes(query.toLowerCase()),
  );
  const filteredSuppliers = data.suppliers.filter((s) =>
    s.name.toLowerCase().includes(query.toLowerCase()),
  );
  const filteredProposals = data.proposals.filter((p) =>
    `${supplierName(p.supplier_id)} ${eventTitle(p.procurement_event_id)}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  const sources = answer?.retrieved_evidence || evidence;
  const empty = (label: string) => (
    <div className="empty">
      <Layers3 size={30} />
      <h3>No {label} yet</h3>
      <p>Try another search or add your first record.</p>
    </div>
  );

  return (
    <div className="app-shell">
      {mobileNav && (
        <button
          className="sidebar-backdrop"
          aria-label="Close navigation"
          onClick={() => setMobileNav(false)}
        />
      )}
      <aside className={`sidebar ${mobileNav ? "sidebar-open" : ""}`}>
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            navigate("Overview");
          }}
        >
          <span className="brand-mark">
            <Network size={23} />
          </span>
          vendorlens<span className="brand-dot">.</span>
        </a>
        <button className="workspace-switch" onClick={() => setSettings(true)}>
          <span className="workspace-icon">V</span>
          <span>
            <strong>Procurement workspace</strong>
            <small>VendorLens platform</small>
          </span>
          <ChevronDown size={15} />
        </button>
        <span className="nav-label">WORKSPACE</span>
        <nav>
          {nav.map(({ name, icon: Icon }) => (
            <button
              key={name}
              onClick={() => navigate(name)}
              className={`nav-item ${page === name ? "nav-active" : ""}`}
            >
              <Icon size={18} />
              {name}
              {name === "Evidence assistant" && (
                <span className="nav-ai">AI</span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-insight">
          <span className="tiny-icon">
            <ShieldCheck size={18} />
          </span>
          <h3>Clarity in every decision.</h3>
          <p>Bring your supplier evidence together. Let the facts lead.</p>
          <button onClick={() => navigate("Evidence assistant")}>
            Explore your evidence <ArrowUpRight size={15} />
          </button>
        </div>
        <div className="sidebar-bottom">
          <button onClick={() => setSettings(true)}>
            <Settings2 size={17} />
            Connection settings
          </button>
          <button onClick={() => setHelp(true)}>
            <CircleHelp size={17} />
            Help & getting started
            <ArrowUpRight size={14} />
          </button>
        </div>
        <div className="profile">
          <span className="avatar">VL</span>
          <span>
            <strong>Procurement team</strong>
            <small>{demo ? "Demo workspace" : "Connected workspace"}</small>
          </span>
          <span className="profile-status" />
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="mobile-menu"
              onClick={() => setMobileNav(true)}
              aria-label="Open navigation"
            >
              <Menu size={20} />
            </button>
            <span>Workspace</span>
            <ChevronRight size={14} />
            <strong>{page}</strong>
          </div>
          <div className="topbar-right">
            <button className="mode-pill" onClick={() => setSettings(true)}>
              <span className={demo ? "dot amber" : "dot"} />
              {demo ? "Demo mode" : "Live API"}
              <ChevronDown size={13} />
            </button>
            <span className="topbar-divider" />
            <span className="avatar small">VL</span>
          </div>
        </header>
        <main>
          <div className="page-heading">
            <div>
              <div className="eyebrow">YOUR PROCUREMENT, IN FOCUS</div>
              <h1>
                {page === "Overview"
                  ? "A clearer view. Better decisions."
                  : page}
              </h1>
              <p>
                {page === "Overview"
                  ? "Your suppliers, proposals, and evidence. All in one place."
                  : page === "Procurement events"
                    ? "Organize sourcing projects and the proposals behind them."
                    : page === "Suppliers"
                      ? "Build a connected view of your supplier network."
                      : page === "Proposals"
                        ? "Keep supplier submissions and supporting documents together."
                        : "Ask better questions. Get answers grounded in your documents."}
              </p>
            </div>
            <div className="heading-actions">
              {page === "Overview" ? (
                <>
                  <Button
                    variant="outline"
                    onClick={() => navigate("Evidence assistant")}
                  >
                    <Sparkles size={16} />
                    Ask your evidence
                  </Button>
                  <Button onClick={() => openEditor("event")}>
                    <Plus size={17} />
                    New event
                  </Button>
                </>
              ) : page !== "Evidence assistant" ? (
                <Button
                  onClick={() =>
                    openEditor(
                      page === "Suppliers"
                        ? "supplier"
                        : page === "Proposals"
                          ? "proposal"
                          : "event",
                    )
                  }
                >
                  <Plus size={17} />
                  {page === "Suppliers"
                    ? "Add supplier"
                    : page === "Proposals"
                      ? "New proposal"
                      : "New event"}
                </Button>
              ) : (
                <span className="evidence-label">
                  <ShieldCheck size={16} />
                  Evidence-backed answers
                </span>
              )}
            </div>
          </div>
          {demo && (
            <div className="demo-banner">
              <span>
                <span className="dot amber" />
                You're exploring a sample workspace.{" "}
                <span className="banner-detail">
                  Connect your API to work with your own data.
                </span>
              </span>
              <button onClick={() => setSettings(true)}>
                Connect API <ArrowRight size={14} />
              </button>
            </div>
          )}
          {error && !editor && !deleteItem && (
            <div className="error" role="alert">
              {error}
              <button onClick={() => setError("")} aria-label="Dismiss error">
                <X size={15} />
              </button>
            </div>
          )}
          {page === "Overview" && (
            <>
              <div className="stats-grid">
                {[
                  {
                    label: "Procurement events",
                    value: data.events.length,
                    icon: FolderKanban,
                    description: "Your sourcing projects",
                    color: "mint",
                    next: "Procurement events",
                  },
                  {
                    label: "Supplier network",
                    value: data.suppliers.length,
                    icon: Building2,
                    description: "Connected to your workspace",
                    color: "lavender",
                    next: "Suppliers",
                  },
                  {
                    label: "Supplier proposals",
                    value: data.proposals.length,
                    icon: FileText,
                    description: "Ready for evidence review",
                    color: "peach",
                    next: "Proposals",
                  },
                  {
                    label: "Events with proposals",
                    value: new Set(
                      data.proposals.map((p) => p.procurement_event_id),
                    ).size,
                    icon: ShieldCheck,
                    description: "A foundation for comparison",
                    color: "blue",
                    next: "Evidence assistant",
                  },
                ].map((stat) => (
                  <button
                    className="stat-card"
                    key={stat.label}
                    onClick={() => navigate(stat.next as Page)}
                  >
                    <div className="stat-top">
                      <span>{stat.label}</span>
                      <span className={`stat-icon ${stat.color}`}>
                        <stat.icon size={18} />
                      </span>
                    </div>
                    <strong className="stat-number">
                      {String(stat.value).padStart(2, "0")}
                    </strong>
                    <div className="stat-bottom">
                      <span>{stat.description}</span>
                      <ArrowUpRight size={15} />
                    </div>
                  </button>
                ))}
              </div>
              <div className="overview-columns">
                <section className="panel events-panel">
                  <div className="panel-heading">
                    <div>
                      <h2>
                        Procurement events{" "}
                        <span className="count">{data.events.length}</span>
                      </h2>
                      <p>From supplier submissions to informed decisions.</p>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => navigate("Procurement events")}
                    >
                      View all
                      <ArrowRight size={15} />
                    </Button>
                  </div>
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>EVENT NAME</th>
                          <th>SUPPLIERS</th>
                          <th>WORKSPACE</th>
                          <th aria-label="Open event" />
                        </tr>
                      </thead>
                      <tbody>
                        {data.events.slice(0, 4).map((event, index) => {
                          const proposals = data.proposals.filter(
                            (p) => p.procurement_event_id === event.id,
                          );
                          return (
                            <tr key={event.id}>
                              <td>
                                <button
                                  className="event-name"
                                  onClick={() => {
                                    setEventId(event.id);
                                    navigate("Evidence assistant");
                                    setAnswer(null);
                                    setEvidence([]);
                                  }}
                                >
                                  <span
                                    className={`event-icon ${colors[index % 5]}`}
                                  >
                                    <FolderKanban size={18} />
                                  </span>
                                  <span>
                                    <strong>{event.title}</strong>
                                    <small>
                                      {demo
                                        ? `PRC-${String(index + 1).padStart(3, "0")} · Sample event`
                                        : `${event.id.slice(0, 8)} · Procurement event`}
                                    </small>
                                  </span>
                                </button>
                              </td>
                              <td>
                                <div className="avatar-stack">
                                  {proposals.slice(0, 3).map((p, i) => (
                                    <span
                                      title={supplierName(p.supplier_id)}
                                      key={p.id}
                                      className={`supplier-avatar ${colors[i]}`}
                                    >
                                      {initials(supplierName(p.supplier_id))}
                                    </span>
                                  ))}
                                  {!proposals.length && (
                                    <span className="muted">—</span>
                                  )}
                                </div>
                              </td>
                              <td>
                                <span
                                  className={`badge ${proposals.length ? "badge-green" : "badge-gray"}`}
                                >
                                  <span className="dot" />
                                  {proposals.length
                                    ? `${proposals.length} proposals`
                                    : "No proposals"}
                                </span>
                              </td>
                              <td>
                                <button
                                  className="icon-button"
                                  aria-label={`Open ${event.title}`}
                                  onClick={() => {
                                    setEventId(event.id);
                                    navigate("Evidence assistant");
                                    setAnswer(null);
                                    setEvidence([]);
                                  }}
                                >
                                  <ArrowUpRight size={17} />
                                </button>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                    {!data.events.length && empty("events")}
                  </div>
                  <div className="panel-footer">
                    <span>{data.events.length} events in your workspace</span>
                    <button onClick={() => openEditor("event")}>
                      <Plus size={14} />
                      Create an event
                    </button>
                  </div>
                </section>
                <section className="assistant-card">
                  <div className="assistant-top">
                    <span className="sparkle-box">
                      <Sparkles size={23} />
                    </span>
                    <span className="ai-pill">EVIDENCE ASSISTANT</span>
                  </div>
                  <h2>
                    Less searching.
                    <br />
                    More understanding.
                  </h2>
                  <p>
                    Turn your supplier documents into answers you can trace back
                    to the source.
                  </p>
                  <div className="sample-question">
                    <span>TRY ASKING</span>
                    <p>
                      “How do the suppliers compare on support and
                      availability?”
                    </p>
                  </div>
                  <Button onClick={() => navigate("Evidence assistant")}>
                    Explore the evidence
                    <ArrowRight size={16} />
                  </Button>
                  <small>
                    <ShieldCheck size={13} />
                    Citations included. Human review encouraged.
                  </small>
                </section>
              </div>
              <div className="lower-columns">
                <section className="panel">
                  <div className="panel-heading">
                    <div>
                      <h2>Your supplier network</h2>
                      <p>The people behind the proposals.</p>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => navigate("Suppliers")}
                    >
                      View all
                      <ArrowRight size={15} />
                    </Button>
                  </div>
                  <div className="supplier-preview">
                    {data.suppliers.slice(0, 4).map((supplier, i) => (
                      <button
                        key={supplier.id}
                        onClick={() => {
                          navigate("Suppliers");
                          setQuery(supplier.name);
                        }}
                      >
                        <span className={`supplier-logo ${colors[i]}`}>
                          {initials(supplier.name)}
                        </span>
                        <span>
                          <strong>{supplier.name}</strong>
                          <small>
                            {
                              data.proposals.filter(
                                (p) => p.supplier_id === supplier.id,
                              ).length
                            }{" "}
                            proposals
                          </small>
                        </span>
                        <ChevronRight size={15} />
                      </button>
                    ))}
                    {!data.suppliers.length && empty("suppliers")}
                  </div>
                </section>
                <section className="workflow-card">
                  <div className="workflow-title">
                    <span className="eyebrow">A MORE CONNECTED WORKFLOW</span>
                    <Layers3 size={20} />
                  </div>
                  <h2>From documents to decisions.</h2>
                  <div className="workflow-steps">
                    {[
                      {
                        title: "Create an event",
                        text: "Give your sourcing project a home.",
                        next: () => openEditor("event"),
                      },
                      {
                        title: "Bring in your suppliers",
                        text: "Connect proposals and upload PDFs.",
                        next: () => navigate("Proposals"),
                      },
                      {
                        title: "Follow the evidence",
                        text: "Ask, compare, and review the sources.",
                        next: () => navigate("Evidence assistant"),
                      },
                    ].map((step, i) => (
                      <button key={step.title} onClick={step.next}>
                        <span className="step-number">0{i + 1}</span>
                        <span>
                          <strong>{step.title}</strong>
                          <small>{step.text}</small>
                        </span>
                        <ArrowUpRight size={15} />
                      </button>
                    ))}
                  </div>
                </section>
              </div>
            </>
          )}
          {page === "Procurement events" && (
            <section className="panel">
              <div className="list-toolbar">
                <h2>
                  All events <span className="count">{data.events.length}</span>
                </h2>
                <SearchInput
                  value={query}
                  onChange={setQuery}
                  placeholder="Search events…"
                />
              </div>
              <div className="event-grid">
                {filteredEvents.map((event, i) => (
                  <article className="event-card" key={event.id}>
                    <div className="event-card-top">
                      <span className={`event-icon ${colors[i % 5]}`}>
                        <FolderKanban size={22} />
                      </span>
                      <span className="badge badge-gray">Procurement</span>
                    </div>
                    <h3>{event.title}</h3>
                    <p>
                      {
                        data.proposals.filter(
                          (p) => p.procurement_event_id === event.id,
                        ).length
                      }{" "}
                      supplier proposals
                    </p>
                    <div className="event-card-bottom">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          setEventId(event.id);
                          setAnswer(null);
                          setEvidence([]);
                          navigate("Evidence assistant");
                        }}
                      >
                        Review evidence
                        <ArrowRight size={14} />
                      </Button>
                      <div className="row-actions">
                        <button
                          className="icon-button"
                          aria-label={`Edit ${event.title}`}
                          onClick={() =>
                            openEditor("event", event.id, event.title)
                          }
                        >
                          <Pencil size={15} />
                        </button>
                        <button
                          className="icon-button"
                          aria-label={`Delete ${event.title}`}
                          onClick={() => {
                            setError("");
                            setDeleteItem({
                              kind: "event",
                              id: event.id,
                              name: event.title,
                            });
                          }}
                        >
                          <Trash2 size={15} />
                        </button>
                      </div>
                    </div>
                  </article>
                ))}
                {!filteredEvents.length && empty("events")}
              </div>
            </section>
          )}
          {page === "Suppliers" && (
            <section className="panel">
              <div className="list-toolbar">
                <h2>
                  Supplier directory{" "}
                  <span className="count">{data.suppliers.length}</span>
                </h2>
                <SearchInput
                  value={query}
                  onChange={setQuery}
                  placeholder="Search suppliers…"
                />
              </div>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>SUPPLIER</th>
                      <th>PROPOSALS</th>
                      <th>PROCUREMENT EVENTS</th>
                      <th>ACTIONS</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredSuppliers.map((supplier, i) => {
                      const proposals = data.proposals.filter(
                        (p) => p.supplier_id === supplier.id,
                      );
                      return (
                        <tr key={supplier.id}>
                          <td>
                            <div className="event-name">
                              <span
                                className={`supplier-logo ${colors[i % 5]}`}
                              >
                                {initials(supplier.name)}
                              </span>
                              <span>
                                <strong>{supplier.name}</strong>
                                <small>ID: {supplier.id.slice(0, 8)}</small>
                              </span>
                            </div>
                          </td>
                          <td>
                            <span className="badge badge-gray">
                              {proposals.length} proposals
                            </span>
                          </td>
                          <td className="event-summary">
                            {proposals
                              .map((p) => eventTitle(p.procurement_event_id))
                              .join(", ") || "No events yet"}
                          </td>
                          <td>
                            <div className="row-actions">
                              <button
                                className="icon-button"
                                aria-label={`Edit ${supplier.name}`}
                                onClick={() =>
                                  openEditor(
                                    "supplier",
                                    supplier.id,
                                    supplier.name,
                                  )
                                }
                              >
                                <Pencil size={15} />
                              </button>
                              <button
                                className="icon-button"
                                aria-label={`Delete ${supplier.name}`}
                                onClick={() => {
                                  setError("");
                                  setDeleteItem({
                                    kind: "supplier",
                                    id: supplier.id,
                                    name: supplier.name,
                                  });
                                }}
                              >
                                <Trash2 size={15} />
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                {!filteredSuppliers.length && empty("suppliers")}
              </div>
            </section>
          )}
          {page === "Proposals" && (
            <section className="panel">
              <div className="list-toolbar">
                <h2>
                  All proposals{" "}
                  <span className="count">{data.proposals.length}</span>
                </h2>
                <SearchInput
                  value={query}
                  onChange={setQuery}
                  placeholder="Search proposals…"
                />
              </div>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>SUPPLIER</th>
                      <th>PROCUREMENT EVENT</th>
                      <th>DOCUMENTS</th>
                      <th aria-label="Actions" />
                    </tr>
                  </thead>
                  <tbody>
                    {filteredProposals.map((proposal, i) => (
                      <tr key={proposal.id}>
                        <td>
                          <div className="event-name">
                            <span className={`supplier-logo ${colors[i % 5]}`}>
                              {initials(supplierName(proposal.supplier_id))}
                            </span>
                            <span>
                              <strong>
                                {supplierName(proposal.supplier_id)}
                              </strong>
                              <small>Proposal {proposal.id.slice(0, 8)}</small>
                            </span>
                          </div>
                        </td>
                        <td>{eventTitle(proposal.procurement_event_id)}</td>
                        <td>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => {
                              setUploadId(proposal.id);
                              setFile(null);
                              setUploadError("");
                            }}
                          >
                            <Upload size={14} />
                            Upload PDF
                          </Button>
                        </td>
                        <td>
                          <button
                            className="icon-button"
                            aria-label={`Delete proposal from ${supplierName(proposal.supplier_id)}`}
                            onClick={() => {
                              setError("");
                              setDeleteItem({
                                kind: "proposal",
                                id: proposal.id,
                                name: `proposal from ${supplierName(proposal.supplier_id)}`,
                              });
                            }}
                          >
                            <Trash2 size={15} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!filteredProposals.length && empty("proposals")}
              </div>
              <div className="panel-footer">
                Upload PDF evidence up to 10 MB per file. Existing documents are
                not listed by the current API.
              </div>
            </section>
          )}
          {page === "Evidence assistant" && (
            <div className="evidence-layout">
              <section className="panel evidence-main">
                <div className="evidence-toolbar">
                  <label htmlFor="evidence-event">
                    Procurement event
                    <select
                      id="evidence-event"
                      value={eventId}
                      onChange={(e) => {
                        setEventId(e.target.value);
                        setAnswer(null);
                        setEvidence([]);
                      }}
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
                  <div className="segmented">
                    <button
                      className={!searchMode ? "selected" : ""}
                      onClick={() => {
                        setSearchMode(false);
                        setAnswer(null);
                        setEvidence([]);
                      }}
                    >
                      <Sparkles size={14} />
                      Ask
                    </button>
                    <button
                      className={searchMode ? "selected" : ""}
                      onClick={() => {
                        setSearchMode(true);
                        setAnswer(null);
                        setEvidence([]);
                      }}
                    >
                      <Search size={14} />
                      Search
                    </button>
                  </div>
                </div>
                <div className="answer-space">
                  {!answer && !evidence.length && !busy ? (
                    <div className="assistant-empty">
                      <span className="assistant-orb">
                        <Sparkles size={32} />
                      </span>
                      <span className="eyebrow">
                        A CLEARER PICTURE STARTS HERE
                      </span>
                      <h2>What would you like to understand?</h2>
                      <p>
                        {searchMode
                          ? "Find relevant passages in your supplier documents."
                          : "Explore the details, surface differences, and follow the citations."}
                      </p>
                      <div className="prompt-list">
                        {[
                          "How do suppliers compare on support and availability?",
                          "What exclusions should we review?",
                          "Summarize the migration support commitments.",
                        ].map((prompt) => (
                          <button
                            disabled={!eventId}
                            key={prompt}
                            onClick={() => ask(undefined, prompt)}
                          >
                            {prompt}
                            <ArrowUpRight size={15} />
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : busy ? (
                    <div className="assistant-empty">
                      <Loader2 className="spin" size={30} />
                      <h2>Following the evidence…</h2>
                      <p>Reviewing supplier documents for this event.</p>
                    </div>
                  ) : answer ? (
                    <div className="answer">
                      <span className="badge badge-green">
                        <Sparkles size={13} />
                        {demo ? "Sample answer" : "Evidence answer"}
                      </span>
                      <h2>{question}</h2>
                      <p className="answer-text">{answer.answer}</p>
                      <div className="review-note">
                        <ShieldCheck size={17} />
                        Review cited passages alongside the answer before making
                        a procurement decision.
                      </div>
                    </div>
                  ) : (
                    <div className="answer">
                      <span className="badge badge-gray">Semantic search</span>
                      <h2>{question}</h2>
                      <p>
                        {evidence.length} relevant passages found. Read the
                        sources in the evidence panel.
                      </p>
                    </div>
                  )}
                </div>
                <form className="ask-form" onSubmit={ask}>
                  <label className="sr-only" htmlFor="question">
                    {searchMode ? "Search evidence" : "Ask a question"}
                  </label>
                  <textarea
                    id="question"
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    maxLength={2000}
                    placeholder={
                      searchMode
                        ? "Search your supplier evidence…"
                        : "Ask a question about your supplier proposals…"
                    }
                    rows={2}
                  />
                  <div>
                    <span>
                      <ShieldCheck size={13} />
                      {demo
                        ? "Sample evidence · Demo only"
                        : "Grounded in your uploaded documents"}
                    </span>
                    <Button
                      disabled={busy || !question.trim() || !eventId}
                      type="submit"
                    >
                      {busy ? (
                        <Loader2 className="spin" size={16} />
                      ) : searchMode ? (
                        <Search size={16} />
                      ) : (
                        <ArrowUpRight size={16} />
                      )}
                      {searchMode ? "Search" : "Ask question"}
                    </Button>
                  </div>
                </form>
              </section>
              <aside className="panel sources-panel">
                <div className="panel-heading">
                  <div>
                    <h2>
                      <FileText size={17} />
                      Source evidence{" "}
                      <span className="count">{sources.length}</span>
                    </h2>
                    <p>Every answer starts with a source.</p>
                  </div>
                </div>
                {sources.length ? (
                  <div className="source-list">
                    {sources.map((source, i) => (
                      <article className="source-card" key={source.chunk_id}>
                        <div>
                          <span className="source-number">{i + 1}</span>
                          <strong>{source.supplier_name}</strong>
                        </div>
                        <p>{source.text}</p>
                        <div className="source-file">
                          <FileText size={13} />
                          <span>{source.filename}</span>
                          <span>p. {source.page_number}</span>
                        </div>
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className="sources-empty">
                    <FileText size={30} />
                    <h3>Your citations appear here</h3>
                    <p>
                      Ask a question to see the document passages behind the
                      answer.
                    </p>
                    {activeEvent && (
                      <span className="badge badge-gray">
                        {
                          data.proposals.filter(
                            (p) => p.procurement_event_id === eventId,
                          ).length
                        }{" "}
                        proposals in this event
                      </span>
                    )}
                  </div>
                )}
              </aside>
            </div>
          )}
          <footer className="main-footer">
            <span>
              <Network size={14} />
              VendorLens<span className="footer-divider">/</span>A clearer view
              of procurement.
            </span>
            <span>Evidence first. Human decisions.</span>
          </footer>
        </main>
      </div>
      <Dialog
        open={!!editor}
        onOpenChange={(open) => {
          if (!open && !busy) {
            setEditor(null);
            setError("");
          }
        }}
        title={`${editor?.id ? "Edit" : editor?.kind === "supplier" ? "Add" : "Create"} ${editor?.kind === "event" ? "procurement event" : editor?.kind || "record"}`}
        description={
          demo
            ? "This is a demo workspace. Changes stay in the current session."
            : "Save this record to your connected VendorLens workspace."
        }
      >
        <form onSubmit={save} className="dialog-form">
          {editor?.kind === "proposal" ? (
            <>
              <label>
                Supplier
                <select name="supplier" required>
                  <option value="">Select a supplier</option>
                  {data.suppliers.map((s) => (
                    <option value={s.id} key={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Procurement event
                <select
                  name="event"
                  required
                  defaultValue={
                    data.events.some((e) => e.id === eventId) ? eventId : ""
                  }
                >
                  <option value="">Select an event</option>
                  {data.events.map((e) => (
                    <option value={e.id} key={e.id}>
                      {e.title}
                    </option>
                  ))}
                </select>
              </label>
              {(!data.suppliers.length || !data.events.length) && (
                <p className="muted">
                  Add a supplier and an event before creating a proposal.
                </p>
              )}
            </>
          ) : (
            <label>
              {editor?.kind === "event" ? "Event title" : "Supplier name"}
              <input
                autoFocus
                name="name"
                maxLength={200}
                required
                defaultValue={editor?.value || ""}
                placeholder={
                  editor?.kind === "event"
                    ? "e.g. Enterprise security platform"
                    : "e.g. Northstar Technologies"
                }
              />
            </label>
          )}
          {error && (
            <div className="error" role="alert">
              {error}
            </div>
          )}
          <div className="dialog-actions">
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              onClick={() => {
                setEditor(null);
                setError("");
              }}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={busy}>
              {busy && <Loader2 size={16} className="spin" />}Save{" "}
              {editor?.kind}
            </Button>
          </div>
        </form>
      </Dialog>
      <Dialog
        open={settings}
        onOpenChange={setSettings}
        title="Connect your workspace"
        description="Use your existing VendorLens API to manage real procurement data."
      >
        <div className="settings-content">
          <div className="connection-status">
            <span className={demo ? "dot amber" : "dot"} />
            {demo
              ? "Currently viewing sample data"
              : "Connected to VendorLens API"}
          </div>
          <p>
            Your project root <code>.env</code> supplies <code>API_KEY</code>.
            Optionally set <code>API_TARGET</code> there, then restart the frontend development
            server. The key stays in the server-side proxy.
          </p>
          <div className="config-preview">
            API_TARGET=http://127.0.0.1:8000
            <br />
            API_KEY=your-api-key
          </div>
          {error && (
            <div className="error" role="alert">
              {error}
            </div>
          )}
          <div className="dialog-actions">
            <Button variant="outline" onClick={useDemo} disabled={loading}>
              Use demo
            </Button>
            <Button onClick={refresh} disabled={loading}>
              {loading ? (
                <Loader2 className="spin" size={16} />
              ) : (
                <RefreshCw size={16} />
              )}
              Connect API
            </Button>
          </div>
        </div>
      </Dialog>
      <Dialog
        open={!!deleteItem}
        onOpenChange={(open) => {
          if (!open && !busy) {
            setDeleteItem(null);
            setError("");
          }
        }}
        title="Delete this record?"
        description={`This will delete ${deleteItem?.name || "this record"}${demo ? " from the demo session" : " from your workspace"}.`}
      >
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        <div className="dialog-actions">
          <Button
            variant="outline"
            disabled={busy}
            onClick={() => {
              setDeleteItem(null);
              setError("");
            }}
          >
            Cancel
          </Button>
          <Button variant="destructive" disabled={busy} onClick={remove}>
            {busy && <Loader2 size={16} className="spin" />}Delete record
          </Button>
        </div>
      </Dialog>
      <Dialog
        open={!!uploadId}
        onOpenChange={(open) => {
          if (!open && !busy) setUploadId(null);
        }}
        title="Upload proposal evidence"
        description={
          demo
            ? "Preview the upload flow. Connect the API to ingest your documents."
            : "Your PDF will be parsed and indexed for evidence search."
        }
      >
        <form onSubmit={upload} className="dialog-form">
          <label className="upload-zone">
            <Upload size={28} />
            <strong>{file?.name || "Choose a PDF document"}</strong>
            <span>PDF only · Maximum 10 MB</span>
            <input
              type="file"
              accept="application/pdf,.pdf"
              onChange={(e) => {
                setFile(e.target.files?.[0] || null);
                setUploadError("");
              }}
            />
          </label>
          {uploadError && (
            <div className="error" role="alert">
              {uploadError}
            </div>
          )}
          <div className="dialog-actions">
            <Button
              variant="outline"
              type="button"
              disabled={busy}
              onClick={() => setUploadId(null)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={busy || !file}>
              {busy ? (
                <Loader2 className="spin" size={16} />
              ) : (
                <Upload size={16} />
              )}
              {demo ? "Preview upload" : "Upload & ingest"}
            </Button>
          </div>
        </form>
      </Dialog>
      <Dialog
        open={help}
        onOpenChange={setHelp}
        title="Welcome to VendorLens"
        description="A simple path from supplier documents to informed decisions."
      >
        <ol className="help-steps">
          <li>
            <strong>Create a procurement event.</strong>
            <p>Give your sourcing project a title.</p>
          </li>
          <li>
            <strong>Add suppliers and proposals.</strong>
            <p>Link each supplier to an event with a proposal.</p>
          </li>
          <li>
            <strong>Upload your PDF evidence.</strong>
            <p>Open Proposals and upload documents up to 10 MB.</p>
          </li>
          <li>
            <strong>Ask questions and review citations.</strong>
            <p>
              Select an event in the Evidence assistant to explore its
              documents.
            </p>
          </li>
        </ol>
        <Button variant="outline" asChild>
          <a href="http://127.0.0.1:8000/docs" target="_blank" rel="noreferrer">
            Open local API documentation
            <ExternalLink size={15} />
          </a>
        </Button>
      </Dialog>
      {notice && (
        <div className="toast" role="status">
          <span className="toast-icon">
            <Check size={16} />
          </span>
          {notice}
          <button
            onClick={() => setNotice("")}
            aria-label="Dismiss notification"
          >
            <X size={15} />
          </button>
        </div>
      )}
    </div>
  );
}

function SearchInput({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
}) {
  return (
    <div className="search-input">
      <Search size={16} />
      <input
        aria-label={placeholder.replace("…", "")}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      {value && (
        <button onClick={() => onChange("")} aria-label="Clear search">
          <X size={14} />
        </button>
      )}
    </div>
  );
}

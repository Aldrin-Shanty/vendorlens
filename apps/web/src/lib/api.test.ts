import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  getComparison,
  loadWorkspace,
  request,
  reviewComparison,
  startComparison,
} from "./api";

afterEach(() => vi.unstubAllGlobals());
describe("existing API integration", () => {
  it("loads all three workspace collections from the existing routes", async () => {
    const fetch = vi
      .fn()
      .mockImplementation(async () => new Response("[]", { status: 200 }));
    vi.stubGlobal("fetch", fetch);
    expect(await loadWorkspace()).toEqual({
      suppliers: [],
      events: [],
      proposals: [],
    });
    expect(fetch.mock.calls.map((call) => call[0])).toEqual([
      "/api/suppliers",
      "/api/procurement-events",
      "/api/proposals",
    ]);
  });
  it("forwards the startup cancellation signal to every request", async () => {
    const controller = new AbortController();
    const fetch = vi
      .fn()
      .mockImplementation(async () => new Response("[]", { status: 200 }));
    vi.stubGlobal("fetch", fetch);
    await loadWorkspace({ signal: controller.signal });
    expect(fetch.mock.calls).toHaveLength(3);
    for (const call of fetch.mock.calls)
      expect(call[1].signal).toBe(controller.signal);
  });
  it.each(["/api/suppliers", "/api/procurement-events", "/api/proposals"])(
    "rejects incomplete records returned by %s",
    async (invalidPath) => {
      vi.stubGlobal(
        "fetch",
        vi
          .fn()
          .mockImplementation(
            async (path: string) =>
              new Response(
                JSON.stringify(
                  path === invalidPath
                    ? [{ id: "missing-required-fields" }]
                    : [],
                ),
                { status: 200 },
              ),
          ),
      );
      await expect(loadWorkspace()).rejects.toThrow("invalid workspace data");
    },
  );
  it("preserves backend conflict messages", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail:
              "Supplier already has a proposal for this procurement event",
          }),
          { status: 409 },
        ),
      ),
    );
    await expect(request("/proposals")).rejects.toThrow(
      "Supplier already has a proposal",
    );
  });
  it("does not set a JSON content type on multipart uploads", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(new Response("{}", { status: 201 }));
    vi.stubGlobal("fetch", fetch);
    const body = new FormData();
    body.append(
      "file",
      new Blob(["test"], { type: "application/pdf" }),
      "test.pdf",
    );
    await request("/proposals/id/documents", { method: "POST", body });
    expect(fetch.mock.calls[0][1].headers).toEqual({});
  });
  it("handles empty deletion responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(null, { status: 204 })),
    );
    expect(
      await request("/suppliers/id", { method: "DELETE" }),
    ).toBeUndefined();
  });
});

describe("comparison workflow API", () => {
  it("starts, reads and reviews an event-scoped workflow", async () => {
    const fetch = vi
      .fn()
      .mockImplementation(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetch);
    await startComparison("event-1", ["supplier-a", "supplier-b"]);
    await getComparison("event-1", "workflow-1");
    await reviewComparison("event-1", "workflow-1", {
      action: "reject",
      comment: "Warranty conflicts with its source.",
    });
    expect(fetch.mock.calls.map((call) => call[0])).toEqual([
      "/api/procurement-events/event-1/comparison-workflows",
      "/api/procurement-events/event-1/comparison-workflows/workflow-1",
      "/api/procurement-events/event-1/comparison-workflows/workflow-1/review",
    ]);
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({
      supplier_ids: ["supplier-a", "supplier-b"],
    });
    expect(fetch.mock.calls[0][1].method).toBe("POST");
    expect(JSON.parse(fetch.mock.calls[2][1].body)).toEqual({
      action: "reject",
      comment: "Warranty conflicts with its source.",
    });
    expect(fetch.mock.calls[2][1].method).toBe("POST");
  });

  it("keeps the HTTP status for review conflicts", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: "Comparison workflow is not awaiting review",
          }),
          { status: 409 },
        ),
      ),
    );
    const error = await reviewComparison("event", "run", {
      action: "reject",
      comment: "Reviewed.",
    }).catch((err) => err);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(409);
    expect(error.message).toContain("not awaiting review");
  });

  it("shows field validation errors from the backend", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: [
              {
                loc: ["body", "comment"],
                msg: "String should have at least 1 character",
              },
            ],
          }),
          { status: 422 },
        ),
      ),
    );
    await expect(request("/review")).rejects.toThrow(
      "comment: String should have at least 1 character",
    );
  });
});

import { afterEach, describe, expect, it, vi } from "vitest";
import { loadWorkspace, request } from "./api";

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
  it("preserves backend conflict messages", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
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

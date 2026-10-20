import { expect, test, type Page } from "@playwright/test";

const eventId = "00000000-0000-4000-8000-000000000001";
const workflowId = "00000000-0000-4000-8000-000000000002";
const supplierIds = ["supplier-1", "supplier-2"];

function result(status = "awaiting_review") {
  return {
    workflow_id: workflowId,
    name: "Laptop refresh — Dell + HP (1)",
    supplier_ids: supplierIds,
    sequence_number: 1,
    created_at: "2026-10-21T10:00:00Z",
    procurement_event_id: eventId,
    status,
    budget: {
      max_model_calls: 8,
      max_tool_calls: 2,
      model_calls_used: 7,
      tool_calls_used: 2,
    },
    comparison: {
      procurement_event_id: eventId,
      suppliers: supplierIds.map((id, index) => ({
        supplier_id: id,
        facts: {
          supplier_name: index === 0 ? "Dell" : "HP",
          unit_price: 1200,
          currency: "USD",
          warranty_years: 3,
          delivery_days: null,
          unit_price_evidence: { evidence_ids: [1] },
          warranty_evidence: { evidence_ids: [1] },
          delivery_evidence: null,
          missing_information: ["Delivery timeline"],
        },
        judgment: {
          status: "checked",
          model: "Local test NLI",
          revision: "test-revision",
          input_tokens: 50,
          output_tokens: 0,
          facts: {
            warranty_years: {
              relation: "contradicts",
              confidence: 0.93,
              probabilities: {
                supports: 0.04,
                contradicts: 0.93,
                insufficient: 0.03,
              },
            },
          },
        },
        evidence: {
          "1": {
            chunk_id: `chunk-${id}`,
            document_version_id: `version-${id}`,
            filename: `${id}.pdf`,
            page_number: 4,
            text: "Unit price: 1200 USD. Warranty: 1 year.",
          },
        },
      })),
    },
    review_issues: [
      {
        supplier_id: "supplier-1",
        field: "warranty_years",
        reason: "contradicted",
      },
    ],
    review_decision: null as { action: string; comment: string } | null,
    error:
      status === "failed"
        ? "Comparison failed: AIServiceUnavailableError"
        : status === "stopped"
          ? "Model-call budget exhausted"
          : null,
  };
}

async function mockApi(
  page: Page,
  options: { conflict?: boolean; status?: string } = {},
) {
  let saved = result(options.status);
  const calls = { start: 0, read: 0, review: 0 };
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const method = route.request().method();
    const base = `/api/procurement-events/${eventId}/comparison-workflows`;
    if (path === "/api/suppliers")
      return route.fulfill({
        json: [
          { id: supplierIds[0], name: "Dell" },
          { id: supplierIds[1], name: "HP" },
          { id: "outsider", name: "No proposal supplier" },
        ],
      });
    if (path === "/api/procurement-events")
      return route.fulfill({
        json: [
          { id: eventId, title: "Laptop refresh" },
          { id: "other-event", title: "Other event" },
        ],
      });
    if (path === "/api/proposals")
      return route.fulfill({
        json: supplierIds.map((id) => ({
          id: `proposal-${id}`,
          supplier_id: id,
          procurement_event_id: eventId,
        })),
      });
    if (
      (path === base || path === "/api/comparison-workflows") &&
      method === "GET"
    )
      return route.fulfill({ json: [saved] });
    if (
      method === "DELETE" &&
      (path === `${base}/${workflowId}` || path === "/api/comparison-workflows")
    )
      return route.fulfill({ status: 204 });
    if (path === base && method === "POST") {
      calls.start++;
      expect(route.request().postDataJSON()).toEqual({
        supplier_ids: supplierIds,
      });
      return route.fulfill({ status: 201, json: saved });
    }
    if (path === `${base}/${workflowId}` && method === "GET") {
      calls.read++;
      return route.fulfill({ json: saved });
    }
    if (path === `${base}/${workflowId}/review` && method === "POST") {
      calls.review++;
      const decision = route.request().postDataJSON();
      if (options.conflict) {
        saved = {
          ...saved,
          status: "rejected",
          review_decision: {
            action: "reject",
            comment: "Another review was already saved.",
          },
        };
        return route.fulfill({
          status: 409,
          json: { detail: "Comparison workflow is not awaiting review" },
        });
      }
      saved = {
        ...saved,
        status: decision.action === "acknowledge" ? "reviewed" : "rejected",
        review_decision: decision,
      };
      return route.fulfill({ json: saved });
    }
    return route.fulfill({
      status: 404,
      json: { detail: "Comparison workflow not found" },
    });
  });
  return calls;
}

async function connect(page: Page) {
  await expect(page.getByRole("button", { name: "Live API" })).toBeVisible();
  await page
    .locator("nav")
    .getByRole("button", { name: "Comparisons", exact: true })
    .click();
}

async function start(page: Page) {
  await page.getByRole("checkbox", { name: "Dell", exact: true }).check();
  await page.getByRole("checkbox", { name: "HP", exact: true }).check();
  await page
    .getByRole("button", { name: "Start comparison", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "Laptop refresh — Dell + HP (1)",
      exact: true,
    }),
  ).toBeVisible();
}

test("demo comparison includes citations and a sample human review on mobile", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route("**/api/**", (route) => route.abort("connectionrefused"));
  await page.goto("/");
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page
    .locator("nav")
    .getByRole("button", { name: "Comparisons", exact: true })
    .click();
  await page.getByRole("checkbox", { name: "Northstar Technologies" }).check();
  await page.getByRole("checkbox", { name: "Acme Infrastructure" }).check();
  await page.getByRole("button", { name: "Preview comparison" }).click();
  await expect(
    page.getByText("Illustrative demo", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Northstar Technologies Warranty source 1" })
    .click();
  await expect(
    page.getByText("Synthetic example: Unit price is 1200 USD.", {
      exact: false,
    }),
  ).toBeVisible();
  await page
    .getByLabel("Review decision", { exact: true })
    .selectOption("reject");
  await page
    .getByLabel("Review comment", { exact: true })
    .fill("Warranty conflicts with the cited source.");
  await page.getByRole("button", { name: "Record sample review" }).click();
  await expect(
    page.getByText("Comparison rejected", { exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/comparison-mobile.png",
    fullPage: true,
  });
});

for (const action of ["acknowledge", "reject"]) {
  test(`live comparison ${action}, reload and reopen preserve the saved workflow`, async ({
    page,
  }) => {
    const calls = await mockApi(page);
    await page.goto("/");
    await connect(page);
    await expect(
      page.getByRole("button", { name: "Start comparison", exact: true }),
    ).toBeDisabled();
    await expect(
      page.getByRole("checkbox", { name: "No proposal supplier" }),
    ).toHaveCount(0);
    await start(page);
    await page.getByRole("link", { name: "Dell Warranty source 1" }).click();
    await expect(
      page
        .getByText("Unit price: 1200 USD. Warranty: 1 year.", { exact: true })
        .first(),
    ).toBeVisible();
    await page
      .getByLabel("Review decision", { exact: true })
      .selectOption(action);
    await page.getByLabel("Review comment", { exact: true }).fill("   ");
    await expect(
      page.getByRole("button", { name: "Submit review", exact: true }),
    ).toBeDisabled();
    await page
      .getByLabel("Review comment", { exact: true })
      .fill("Reviewed the warranty source.");
    await page
      .getByRole("button", { name: "Submit review", exact: true })
      .click();
    await expect(
      page.getByText(
        action === "acknowledge"
          ? "Issues acknowledged"
          : "Comparison rejected",
        { exact: true },
      ),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Submit review", exact: true }),
    ).toHaveCount(0);
    await page.reload();
    await connect(page);
    await page
      .getByRole("button", {
        name: "Open Laptop refresh — Dell + HP (1)",
        exact: true,
      })
      .click();
    await expect(
      page.getByText("Reviewed the warranty source.", { exact: true }),
    ).toBeVisible();
    expect(calls).toEqual({ start: 1, read: 1, review: 1 });
    await page.screenshot({
      path: `test-results/comparison-${action}-desktop.png`,
      fullPage: true,
    });
  });
}

test("conflicting review refreshes the saved result and removes the stale form", async ({
  page,
}) => {
  const calls = await mockApi(page, { conflict: true });
  await page.goto("/");
  await connect(page);
  await start(page);
  await page
    .getByLabel("Review decision", { exact: true })
    .selectOption("acknowledge");
  await page.getByLabel("Review comment", { exact: true }).fill("Reviewed.");
  await page
    .getByRole("button", { name: "Submit review", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("not awaiting review");
  await expect(
    page.getByText("Another review was already saved.", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Submit review", exact: true }),
  ).toHaveCount(0);
  expect(calls).toEqual({ start: 1, read: 1, review: 1 });
});

test("lookup validates IDs, reports missing workflows and resets on event change", async ({
  page,
}) => {
  const calls = await mockApi(page);
  await page.goto("/");
  await connect(page);
  await page.getByText("Open by workflow ID", { exact: true }).click();
  await page
    .getByRole("textbox", { name: "Workflow ID", exact: true })
    .fill("invalid");
  await page
    .getByRole("button", { name: "Open workflow", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("valid workflow UUID");
  await page
    .getByRole("textbox", { name: "Workflow ID", exact: true })
    .fill("00000000-0000-4000-8000-000000000099");
  await page
    .getByRole("button", { name: "Open workflow", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "Comparison workflow not found",
  );
  await start(page);
  await page
    .getByLabel("Procurement event", { exact: true })
    .selectOption("other-event");
  await expect(page.locator(".workflow-id code")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Start comparison", exact: true }),
  ).toBeDisabled();
  expect(calls.review).toBe(0);
});

test("leaving during extraction keeps the returned workflow reference", async ({
  page,
}) => {
  await mockApi(page);
  await page.goto("/");
  await connect(page);
  let finish: () => void = () => {};
  const gate = new Promise<void>((resolve) => {
    finish = resolve;
  });
  await page.route(
    `**/api/procurement-events/${eventId}/comparison-workflows`,
    async (route) => {
      if (route.request().method() === "GET")
        return route.fulfill({ json: [result()] });
      await gate;
      await route.fulfill({ status: 201, json: result() });
    },
  );
  await page.getByRole("checkbox", { name: "Dell", exact: true }).check();
  await page.getByRole("checkbox", { name: "HP", exact: true }).check();
  const requested = page.waitForRequest(
    (request) =>
      request.method() === "POST" &&
      request.url().endsWith("/comparison-workflows"),
  );
  await page
    .getByRole("button", { name: "Start comparison", exact: true })
    .click();
  await requested;
  await page
    .locator("nav")
    .getByRole("button", { name: "Overview", exact: true })
    .click();
  finish();
  await expect
    .poll(() =>
      page.evaluate(() =>
        localStorage.getItem("vendorlens.workflow-references.v1"),
      ),
    )
    .toContain(workflowId);
  await page
    .locator("nav")
    .getByRole("button", { name: "Comparisons", exact: true })
    .click();
  await page
    .getByRole("button", {
      name: "Open Laptop refresh — Dell + HP (1)",
      exact: true,
    })
    .click();
  await expect(page.locator(".workflow-id code")).toHaveText(workflowId);
});

for (const status of ["completed", "failed", "stopped"]) {
  test(`${status} workflows show status and do not offer review`, async ({
    page,
  }) => {
    await mockApi(page, { status });
    await page.goto("/");
    await connect(page);
    await start(page);
    await expect(page.locator(`.workflow-${status}`)).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Submit review", exact: true }),
    ).toHaveCount(0);
    if (status === "failed")
      await expect(page.getByRole("alert")).toContainText(
        "AIServiceUnavailableError",
      );
    if (status === "stopped")
      await expect(page.getByRole("alert")).toContainText("budget exhausted");
  });
}

for (const all of [false, true]) {
  test(`confirmed ${all ? "bulk" : "individual"} workflow deletion keeps proposals`, async ({
    page,
  }) => {
    await mockApi(page);
    let deletes = 0;
    await page.route("**/api/**", async (route) => {
      if (deletes && route.request().method() === "GET" && new URL(route.request().url()).pathname.endsWith("/comparison-workflows")) return route.fulfill({json: []});
      if (route.request().method() !== "DELETE") return route.fallback();
      deletes++;
      expect(new URL(route.request().url()).searchParams.get("confirm")).toBe(
        "true",
      );
      expect(new URL(route.request().url()).pathname).toBe(
        all
          ? "/api/comparison-workflows"
          : `/api/procurement-events/${eventId}/comparison-workflows/${workflowId}`,
      );
      return route.fulfill({ status: 204 });
    });
    await page.goto("/");
    await connect(page);
    await page
      .getByRole("button", {
        name: "Open Laptop refresh — Dell + HP (1)",
        exact: true,
      })
      .click();
    const openDelete = () =>
      page
        .getByRole("button", {
          name: all
            ? "Delete all workflows"
            : "Delete Laptop refresh — Dell + HP (1)",
          exact: true,
        })
        .click();
    await openDelete();
    await expect(page.getByRole("dialog")).toContainText(
      "Source proposals and PDFs are kept",
    );
    await page.getByRole("button", { name: "Cancel", exact: true }).click();
    expect(deletes).toBe(0);
    await openDelete();
    await page
      .getByRole("button", { name: "Confirm deletion", exact: true })
      .click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(
      page.getByRole("button", {
        name: "Open Laptop refresh — Dell + HP (1)",
        exact: true,
      }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("heading", {
        name: "Laptop refresh — Dell + HP (1)",
        exact: true,
      }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("checkbox", { name: "Dell", exact: true }),
    ).toBeVisible();
    expect(deletes).toBe(1);
  });
}

test("failed workflow deletion keeps the saved result and displays the error", async ({
  page,
}) => {
  await mockApi(page);
  await page.route("**/api/**", (route) =>
    route.request().method() === "DELETE"
      ? route.fulfill({ status: 503, json: { detail: "Storage unavailable" } })
      : route.fallback(),
  );
  await page.goto("/");
  await connect(page);
  await page
    .getByRole("button", {
      name: "Delete Laptop refresh — Dell + HP (1)",
      exact: true,
    })
    .click();
  await page
    .getByRole("button", { name: "Confirm deletion", exact: true })
    .click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText(
    "Storage unavailable",
  );
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(
    page.getByRole("button", {
      name: "Open Laptop refresh — Dell + HP (1)",
      exact: true,
    }),
  ).toBeVisible();
});

import { expect, test, type Page } from "@playwright/test";

const collections: Record<string, unknown> = {
  "/api/suppliers": [{ id: "supplier-live", name: "Live supplier" }],
  "/api/procurement-events": [
    { id: "event-live", title: "Live procurement event" },
  ],
  "/api/proposals": [
    {
      id: "proposal-live",
      supplier_id: "supplier-live",
      procurement_event_id: "event-live",
    },
  ],
};

async function showSuppliers(page: Page) {
  await page
    .locator("nav")
    .getByRole("button", { name: "Suppliers", exact: true })
    .click();
}

test("waits for all collections and opens live mode without sample data", async ({
  page,
}) => {
  let finish: () => void = () => {};
  const gate = new Promise<void>((resolve) => {
    finish = resolve;
  });
  await page.route("**/api/**", async (route) => {
    await gate;
    await route.fulfill({
      json: collections[new URL(route.request().url()).pathname],
    });
  });
  await page.goto("/");
  await expect(
    page.getByText("Connecting to your workspace…", { exact: true }),
  ).toBeVisible();
  await expect(page.locator("nav")).toHaveCount(0);
  await expect(
    page.getByText("Northstar Technologies", { exact: true }),
  ).toHaveCount(0);
  finish();
  await expect(page.getByRole("button", { name: "Live API" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Demo mode" })).toHaveCount(0);
  await expect(
    page.getByText("Live procurement event", { exact: true }),
  ).toBeVisible();
  await showSuppliers(page);
  await expect(page.getByText("Live supplier", { exact: true })).toBeVisible();
  await expect(
    page.getByText("Northstar Technologies", { exact: true }),
  ).toHaveCount(0);
});

test("an empty healthy workspace opens live mode", async ({ page }) => {
  await page.route("**/api/**", (route) => route.fulfill({ json: [] }));
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Live API" })).toBeVisible();
  await expect(page.locator(".demo-banner")).toHaveCount(0);
  await showSuppliers(page);
  await expect(page.locator("tbody tr")).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "No suppliers yet" }),
  ).toBeVisible();
});

test("unreachable API falls back to demo and can reconnect later", async ({
  page,
}) => {
  let ready = false;
  await page.route("**/api/**", (route) =>
    ready
      ? route.fulfill({
          json: collections[new URL(route.request().url()).pathname],
        })
      : route.abort("connectionrefused"),
  );
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Demo mode" })).toBeVisible();
  await expect(page.locator(".connection-fallback")).toContainText(
    "Showing sample data",
  );
  await showSuppliers(page);
  await expect(
    page.getByText("Northstar Technologies", { exact: true }),
  ).toBeVisible();
  ready = true;
  await page.getByRole("button", { name: "Connect API", exact: true }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Connect API", exact: true })
    .click();
  await expect(page.getByRole("button", { name: "Live API" })).toBeVisible();
  await expect(page.getByText("Live supplier", { exact: true })).toBeVisible();
  await expect(page.locator(".connection-fallback")).toHaveCount(0);
});

test("authentication failure shows the reason for demo fallback", async ({
  page,
}) => {
  await page.route("**/api/**", (route) =>
    route.fulfill({
      status: 401,
      json: { detail: "Invalid or missing API key" },
    }),
  );
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Demo mode" })).toBeVisible();
  await expect(page.locator(".connection-fallback")).toContainText(
    "Invalid or missing API key",
  );
});

test("one failed collection does not mix live and demo records", async ({
  page,
}) => {
  await page.route("**/api/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    return path === "/api/proposals"
      ? route.fulfill({
          status: 503,
          json: { detail: "Database temporarily unavailable" },
        })
      : route.fulfill({ json: collections[path] });
  });
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Demo mode" })).toBeVisible();
  await expect(page.locator(".connection-fallback")).toContainText(
    "Database temporarily unavailable",
  );
  await showSuppliers(page);
  await expect(
    page.getByText("Northstar Technologies", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Live supplier", { exact: true })).toHaveCount(0);
});

test("invalid collection data falls back instead of crashing the workspace", async ({
  page,
}) => {
  await page.route("**/api/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    return route.fulfill({
      json:
        path === "/api/procurement-events"
          ? { unexpected: "shape" }
          : collections[path],
    });
  });
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Demo mode" })).toBeVisible();
  await expect(page.locator(".connection-fallback")).toContainText(
    "invalid workspace data",
  );
});

test("a stalled API falls back after eight seconds", async ({ page }) => {
  await page.clock.install();
  let finish: () => void = () => {};
  const gate = new Promise<void>((resolve) => {
    finish = resolve;
  });
  await page.route("**/api/**", async (route) => {
    await gate;
    await route.fulfill({ json: [] }).catch(() => {});
  });
  await page.goto("/");
  await expect(
    page.getByText("Connecting to your workspace…", { exact: true }),
  ).toBeVisible();
  await page.clock.fastForward(8100);
  finish();
  await expect(page.getByRole("button", { name: "Demo mode" })).toBeVisible();
  await expect(page.locator(".connection-fallback")).toContainText(
    "did not respond within 8 seconds",
  );
});

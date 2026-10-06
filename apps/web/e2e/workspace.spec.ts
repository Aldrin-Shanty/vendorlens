import { test, expect } from "@playwright/test";

test("demo supplier CRUD, filtering, and relationship protection", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .locator("nav")
    .getByRole("button", { name: "Suppliers", exact: true })
    .click();
  await page.getByRole("button", { name: "Add supplier", exact: true }).click();
  await page
    .getByRole("textbox", { name: "Supplier name" })
    .fill("Test Supplier");
  await page.getByRole("button", { name: "Save supplier" }).click();
  await page
    .getByRole("textbox", { name: "Search suppliers" })
    .fill("Test Supplier");
  await expect(page.locator("tbody tr")).toHaveCount(1);
  await page.getByRole("button", { name: "Edit Test Supplier" }).click();
  await page
    .getByRole("textbox", { name: "Supplier name" })
    .fill("Updated Supplier");
  await page.getByRole("button", { name: "Save supplier" }).click();
  await page.getByRole("button", { name: "Clear search" }).click();
  await page.getByRole("button", { name: "Delete Updated Supplier" }).click();
  await page
    .getByRole("button", { name: "Delete record", exact: true })
    .click();
  await expect(page.getByText("Updated Supplier", { exact: true })).toHaveCount(
    0,
  );
  await page
    .getByRole("button", { name: "Delete Northstar Technologies" })
    .click();
  await page
    .getByRole("button", { name: "Delete record", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "Remove associated proposals",
  );
});

test("evidence answers include source pages; search also works", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .locator("nav")
    .getByRole("button", { name: "Evidence assistant" })
    .click();
  await page
    .getByRole("button", {
      name: "How do suppliers compare on support and availability?",
    })
    .click();
  await expect(page.getByText("Sample answer", { exact: true })).toBeVisible();
  await expect(page.getByText("p. 12", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "Search", exact: true })
    .first()
    .click();
  await page.getByRole("textbox", { name: "Search evidence" }).fill("support");
  await page
    .locator("form")
    .getByRole("button", { name: "Search", exact: true })
    .click();
  await expect(
    page.getByText("3 relevant passages found.", { exact: false }),
  ).toBeVisible();
});

test("live workspace loads and posts the existing API contract", async ({
  page,
}) => {
  let created = false;
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url()).pathname;
    if (
      url === "/api/procurement-events" &&
      route.request().method() === "POST"
    ) {
      expect(route.request().postDataJSON()).toEqual({
        title: "Live sourcing event",
      });
      created = true;
      await route.fulfill({
        status: 201,
        json: { id: "event-1", title: "Live sourcing event" },
      });
    } else
      await route.fulfill({
        json:
          url === "/api/procurement-events" && created
            ? [{ id: "event-1", title: "Live sourcing event" }]
            : [],
      });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Connect API", exact: true }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Connect API", exact: true })
    .click();
  await expect(page.getByRole("button", { name: "Live API" })).toBeVisible();
  await page.getByRole("button", { name: "New event", exact: true }).click();
  await page
    .getByRole("textbox", { name: "Event title" })
    .fill("Live sourcing event");
  await page.getByRole("button", { name: "Save event" }).click();
  await expect(
    page.getByText("Live sourcing event", { exact: true }),
  ).toBeVisible();
});

test("mobile navigation and upload size validation", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page
    .locator("nav")
    .getByRole("button", { name: "Proposals", exact: true })
    .click();
  await page.getByRole("button", { name: "Upload PDF" }).first().click();
  await page.locator("input[type=file]").setInputFiles({
    name: "large.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.alloc(10 * 1024 * 1024 + 1),
  });
  await page.getByRole("button", { name: "Preview upload" }).click();
  await expect(page.getByRole("alert")).toContainText("10 MB");
});

test("capture desktop and mobile overview", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1050 });
  await page.goto("/");
  await page.screenshot({
    path: "test-results/overview-desktop.png",
    fullPage: true,
    animations: "disabled",
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "test-results/overview-mobile.png",
    fullPage: true,
    animations: "disabled",
  });
});

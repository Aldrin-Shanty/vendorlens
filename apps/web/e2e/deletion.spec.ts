import { expect, test, type Page } from "@playwright/test";

async function deletionApi(
  page: Page,
  options: {
    failedPreview?: boolean;
    changedImpact?: boolean;
    storageFailure?: "prepare" | "cleanup";
  } = {},
) {
  const suppliers = [
    { id: "s1", name: "Alpha" },
    { id: "s2", name: "Beta" },
    { id: "s3", name: "Empty supplier" },
  ];
  const events = [
    { id: "e1", title: "Laptop sourcing" },
    { id: "e2", title: "Other sourcing" },
    { id: "e3", title: "Empty event" },
  ];
  const proposals = [
    { id: "p1", supplier_id: "s1", procurement_event_id: "e1" },
    { id: "p2", supplier_id: "s1", procurement_event_id: "e2" },
    { id: "p3", supplier_id: "s2", procurement_event_id: "e1" },
  ];
  const calls: string[] = [];
  let previews = 0;
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const segments = url.pathname.replace("/api/", "").split("/");
    const [collection, id, operation] = segments;
    if (operation === "deletion-impact") {
      previews++;
      if (options.failedPreview)
        return route.fulfill({
          status: 503,
          json: { detail: "Cannot inspect related records right now" },
        });
      const children = proposals.filter((proposal) =>
        collection === "proposals"
          ? proposal.id === id
          : collection === "suppliers"
            ? proposal.supplier_id === id
            : proposal.procurement_event_id === id,
      ).length;
      const count = options.changedImpact && previews === 1 ? 0 : children;
      return route.fulfill({
        json: {
          proposals: collection === "proposals" ? 0 : count,
          documents: count,
          document_versions: count,
          evidence_chunks: count * 2,
          comparison_workflows: count ? 1 : 0,
          comparison_workflow_ids: count
            ? ["00000000-0000-4000-8000-000000000001"]
            : [],
        },
      });
    }
    if (route.request().method() === "DELETE") {
      calls.push(`${url.pathname}${url.search}`);
      if (options.storageFailure) {
        if (options.storageFailure === "cleanup") {
          suppliers.splice(
            suppliers.findIndex((supplier) => supplier.id === id),
            1,
          );
          for (let index = proposals.length - 1; index >= 0; index--) {
            if (proposals[index].supplier_id === id) proposals.splice(index, 1);
          }
        }
        return route.fulfill({
          status: 503,
          json: {
            detail:
              options.storageFailure === "cleanup"
                ? "The record and database evidence were deleted, but stored PDF cleanup could not finish."
                : "Could not prepare the PDFs for deletion. Nothing was deleted.",
          },
        });
      }
      if (options.changedImpact && calls.length === 1)
        return route.fulfill({
          status: 409,
          json: {
            detail: "Related records changed. Review and confirm again.",
          },
        });
      return route.fulfill({ status: 204 });
    }
    return route.fulfill({
      json:
        collection === "suppliers"
          ? suppliers
          : collection === "procurement-events"
            ? events
            : proposals,
    });
  });
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Live API" })).toBeVisible();
  return calls;
}

test("proposal deletion warns about PDFs, cancels without deleting, and confirms once", async ({
  page,
}) => {
  const calls = await deletionApi(page);
  await page
    .locator("nav")
    .getByRole("button", { name: "Proposals", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Delete proposal from Alpha", exact: true })
    .first()
    .click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText(
    "Attached documents and evidence will also be deleted",
  );
  await expect(dialog).toContainText("stored PDF files");
  await expect(dialog).toContainText("saved comparison workflow");
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  expect(calls).toHaveLength(0);
  await expect(page.locator("tbody tr")).toHaveCount(3);
  await page
    .getByRole("button", { name: "Delete proposal from Alpha", exact: true })
    .first()
    .click();
  await dialog
    .getByRole("button", { name: "Delete record", exact: true })
    .click();
  await expect(dialog).toHaveCount(0);
  expect(calls).toEqual(["/api/proposals/p1?confirm_related=true"]);
  await expect(page.locator("tbody tr")).toHaveCount(2);
});

for (const stage of ["prepare", "cleanup"] as const) {
  test(`storage ${stage} failure reports the actual saved record state`, async ({
    page,
  }) => {
    const calls = await deletionApi(page, { storageFailure: stage });
    await page
      .locator("nav")
      .getByRole("button", { name: "Suppliers", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Delete Alpha", exact: true })
      .click();
    const dialog = page.getByRole("dialog");
    await dialog
      .getByRole("button", { name: "Delete record", exact: true })
      .click();
    if (stage === "prepare") {
      await expect(dialog.getByRole("alert")).toContainText(
        "Nothing was deleted",
      );
      await expect(
        dialog.getByRole("button", { name: "Delete record", exact: true }),
      ).toBeEnabled();
      await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
      await expect(
        page.getByRole("button", { name: "Delete Alpha", exact: true }),
      ).toBeVisible();
    } else {
      await expect(dialog).toHaveCount(0);
      await expect(page.getByRole("alert")).toContainText(
        "cleanup could not finish",
      );
      await expect(
        page.getByRole("button", { name: "Delete Alpha", exact: true }),
      ).toHaveCount(0);
      await page
        .locator("nav")
        .getByRole("button", { name: "Proposals", exact: true })
        .click();
      await expect(page.locator("tbody tr")).toHaveCount(1);
    }
    expect(calls).toEqual(["/api/suppliers/s1?confirm_related=true"]);
  });
}

test("cascade confirmation is usable on a narrow mobile viewport", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const calls = await deletionApi(page);
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page
    .locator("nav")
    .getByRole("button", { name: "Suppliers", exact: true })
    .click();
  await page.getByRole("button", { name: "Delete Alpha", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("2 related proposals");
  await expect(
    dialog.getByRole("button", { name: "Cancel", exact: true }),
  ).toBeInViewport();
  await expect(
    dialog.getByRole("button", { name: "Delete record", exact: true }),
  ).toBeInViewport();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/delete-mobile-confirmation.png",
  });
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  expect(calls).toHaveLength(0);
});

for (const kind of ["event", "supplier"]) {
  test(`${kind} deletion confirms related proposals and updates all affected lists`, async ({
    page,
  }) => {
    const calls = await deletionApi(page);
    await page.evaluate(() =>
      localStorage.setItem(
        "vendorlens.workflow-references.v1",
        JSON.stringify([
          { eventId: "e1", id: "00000000-0000-4000-8000-000000000001" },
          { eventId: "e2", id: "00000000-0000-4000-8000-000000000002" },
        ]),
      ),
    );
    await page
      .locator("nav")
      .getByRole("button", {
        name: kind === "event" ? "Procurement events" : "Suppliers",
        exact: true,
      })
      .click();
    const deleteButton = page.getByRole("button", {
      name: kind === "event" ? "Delete Laptop sourcing" : "Delete Alpha",
      exact: true,
    });
    await deleteButton.click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toContainText(
      "2 related proposals and all their documents and evidence",
    );
    await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
    expect(calls).toHaveLength(0);
    await deleteButton.click();
    await page.screenshot({
      path: `test-results/delete-${kind}-confirmation.png`,
    });
    await dialog
      .getByRole("button", { name: "Delete record", exact: true })
      .click();
    await expect(dialog).toHaveCount(0);
    expect(calls).toEqual([
      `/api/${kind === "event" ? "procurement-events/e1" : "suppliers/s1"}?confirm_related=true`,
    ]);
    await expect(deleteButton).toHaveCount(0);
    await page
      .locator("nav")
      .getByRole("button", { name: "Proposals", exact: true })
      .click();
    await expect(page.locator("tbody tr")).toHaveCount(1);
    await expect(page.locator("tbody tr")).toContainText(
      kind === "event" ? "Other sourcing" : "Beta",
    );
    const references = await page.evaluate(() =>
      JSON.parse(
        localStorage.getItem("vendorlens.workflow-references.v1") || "[]",
      ),
    );
    expect(references).toEqual([
      { eventId: "e2", id: "00000000-0000-4000-8000-000000000002" },
    ]);
  });
}

for (const kind of ["event", "supplier"]) {
  test(`empty ${kind} has no related-proposal warning`, async ({ page }) => {
    const calls = await deletionApi(page);
    await page
      .locator("nav")
      .getByRole("button", {
        name: kind === "event" ? "Procurement events" : "Suppliers",
        exact: true,
      })
      .click();
    await page
      .getByRole("button", {
        name: kind === "event" ? "Delete Empty event" : "Delete Empty supplier",
        exact: true,
      })
      .click();
    const dialog = page.getByRole("dialog");
    await expect(
      dialog.getByRole("button", { name: "Delete record", exact: true }),
    ).toBeEnabled();
    await expect(dialog.locator(".deletion-warning")).toHaveCount(0);
    await dialog
      .getByRole("button", { name: "Delete record", exact: true })
      .click();
    await expect(dialog).toHaveCount(0);
    expect(calls).toEqual([
      `/api/${kind === "event" ? "procurement-events/e3" : "suppliers/s3"}?confirm_related=false`,
    ]);
  });
}

test("failed impact lookup disables confirmation and cancel sends no delete", async ({
  page,
}) => {
  const calls = await deletionApi(page, { failedPreview: true });
  await page
    .locator("nav")
    .getByRole("button", { name: "Suppliers", exact: true })
    .click();
  await page.getByRole("button", { name: "Delete Alpha", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("alert")).toContainText(
    "Cannot inspect related records",
  );
  await expect(
    dialog.getByRole("button", { name: "Delete record", exact: true }),
  ).toBeDisabled();
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  expect(calls).toHaveLength(0);
});

test("new related records require a fresh confirmation", async ({ page }) => {
  const calls = await deletionApi(page, { changedImpact: true });
  await page
    .locator("nav")
    .getByRole("button", { name: "Suppliers", exact: true })
    .click();
  await page.getByRole("button", { name: "Delete Alpha", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog
    .getByRole("button", { name: "Delete record", exact: true })
    .click();
  await expect(dialog.getByRole("alert")).toContainText("confirm again");
  await expect(dialog).toContainText("2 related proposals");
  expect(calls).toEqual(["/api/suppliers/s1?confirm_related=false"]);
  await dialog
    .getByRole("button", { name: "Delete record", exact: true })
    .click();
  await expect(dialog).toHaveCount(0);
  expect(calls).toEqual([
    "/api/suppliers/s1?confirm_related=false",
    "/api/suppliers/s1?confirm_related=true",
  ]);
});

import { test, expect, Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

async function loginAuditor(page: Page) {
  await page.goto("/login");
  await page.getByLabel(/Email Address/i).fill("auditor@partproof.io");
  await page.getByLabel(/^Password/i).fill("PartProofSecureDemo2026!");
  await page.getByRole("button", { name: "Sign In to Console" }).click();
  await page.waitForURL(/\/app/);
}

test.describe("Accessibility & Responsive Design (WCAG 2.1 AA)", () => {
  test("login page meets accessibility standards (0 critical or serious violations)", async ({
    page,
  }) => {
    await page.goto("/login");
    await page.waitForLoadState("domcontentloaded");

    const accessibilityScanResults = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();

    const seriousOrCritical = accessibilityScanResults.violations.filter(
      (v) => v.impact === "serious" || v.impact === "critical"
    );

    expect(seriousOrCritical).toEqual([]);
  });

  test("dashboard overview meets accessibility standards", async ({ page }) => {
    await loginAuditor(page);

    const accessibilityScanResults = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();

    const seriousOrCritical = accessibilityScanResults.violations.filter(
      (v) => v.impact === "serious" || v.impact === "critical"
    );

    expect(seriousOrCritical).toEqual([]);
  });

  test("task composer meets accessibility standards", async ({ page }) => {
    await loginAuditor(page);

    await page.goto("/app/tasks/new");
    await page.waitForLoadState("domcontentloaded");

    const accessibilityScanResults = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();

    const seriousOrCritical = accessibilityScanResults.violations.filter(
      (v) => v.impact === "serious" || v.impact === "critical"
    );

    expect(seriousOrCritical).toEqual([]);
  });

  test("task detail view meets accessibility standards", async ({ page }) => {
    await loginAuditor(page);

    await page.goto("/app/tasks/task-reconcile-88");
    await page.waitForLoadState("domcontentloaded");

    const accessibilityScanResults = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();

    const seriousOrCritical = accessibilityScanResults.violations.filter(
      (v) => v.impact === "serious" || v.impact === "critical"
    );

    expect(seriousOrCritical).toEqual([]);
  });

  test("mobile viewport (375px) renders responsive navigation and prevents layout breaking", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 375, height: 667 });

    await loginAuditor(page);

    // Verify mobile navigation button is present and functional
    const menuBtn = page.getByRole("button", { name: "Open navigation menu" });
    await expect(menuBtn).toBeVisible();

    // Open drawer
    await menuBtn.click();
    await expect(page.getByRole("button", { name: "Close navigation menu" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Overview" })).toBeVisible();

    // Close drawer
    await page.getByRole("button", { name: "Close navigation menu" }).click();
    await expect(menuBtn).toBeVisible();

    // Verify task composer fits within 375px without document body scrolling horizontally
    await page.goto("/app/tasks/new");
    await page.waitForLoadState("domcontentloaded");
    const bodyScrollWidth = await page.evaluate(() => document.body.scrollWidth);
    const windowInnerWidth = await page.evaluate(() => window.innerWidth);
    expect(bodyScrollWidth).toBeLessThanOrEqual(windowInnerWidth + 1);
  });
});

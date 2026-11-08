import { test, expect } from "@playwright/test";

test.describe("UX Reliability, Input Provenance & Execution Tracking", () => {
  test.beforeEach(async ({ page }) => {
    // Authenticate prior to each test
    await page.goto("/login");
    await page.getByLabel(/Email Address/i).fill("auditor@partproof.io");
    await page.getByLabel(/^Password/i).fill("PartProofSecureDemo2026!");
    await page.getByRole("button", { name: "Sign In to Console" }).click();
    await expect(page).toHaveURL(/\/app/);
  });

  test("Desktop and mobile viewport scrolling without scroll locking", async ({ page }) => {
    // 1. Desktop scrolling on Procurement Intelligence Workspace
    await page.goto("/app/procurement");
    await expect(page.getByRole("heading", { name: "Procurement Intelligence & Forensics" })).toBeVisible();

    // Scroll to bottom on desktop
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(500);
    const desktopScrollY = await page.evaluate(() => window.scrollY);
    expect(desktopScrollY).toBeGreaterThan(0);

    // Verify footer/bottom controls are accessible
    await expect(page.getByRole("button", { name: "Load Synthetic Demo Case" })).toBeVisible();

    // 2. Mobile viewport scrolling test (iPhone 13/14 viewport: 390x844)
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/app/procurement");
    await expect(page.getByRole("heading", { name: "Procurement Intelligence & Forensics" })).toBeVisible();

    // Verify document can scroll freely without body overflow:hidden locks
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(500);
    const mobileScrollY = await page.evaluate(() => window.scrollY);
    expect(mobileScrollY).toBeGreaterThan(0);

    // Restore desktop viewport
    await page.setViewportSize({ width: 1280, height: 800 });
  });

  test("3 task input modes (Prompt-Only, Synthetic Sample, User Files)", async ({ page }) => {
    await page.goto("/app/tasks/new");
    await expect(page.getByRole("heading", { name: "Create Engineering Task" })).toBeVisible();

    // Verify Mode Selector
    await expect(page.getByText("Task Input Provenance")).toBeVisible();
    const promptOnlyBtn = page.getByRole("button", { name: /Prompt-Only/i });
    const sampleBtn = page.getByRole("button", { name: /Synthetic Sample/i });
    const userFilesBtn = page.getByRole("button", { name: /User Files/i });

    await expect(promptOnlyBtn).toBeVisible();
    await expect(sampleBtn).toBeVisible();
    await expect(userFilesBtn).toBeVisible();

    // 1. Mode C: Prompt-Only (Default)
    await promptOnlyBtn.click();
    await page.getByText("Binary Integrity Audit").click();
    const promptTextarea = page.getByLabel(/Objective & Requirements/i);
    await expect(promptTextarea).toHaveValue(/Inspect \/bin utilities/);

    // 2. Mode B: Synthetic Sample
    await sampleBtn.click();
    const titleInput = page.getByLabel(/Task Title/i);
    await expect(titleInput).toHaveValue("EV Telemetry Cleaning & Anomaly Audit");
    await expect(promptTextarea).toHaveValue(/sample_telemetry_raw\.csv/);
    await expect(page.getByText("Synthetic Sample Dataset").first()).toBeVisible();
    await expect(page.getByText("sample_telemetry_raw.csv").first()).toBeVisible();
    await expect(page.getByRole("button", { name: /Preview 15 Rows/i })).toBeVisible();

    // 3. Mode A: User Files
    await userFilesBtn.click();
    await expect(page.getByText("Upload CSV, JSON, TXT, or script files")).toBeVisible();
    await expect(page.locator("input[type='file']")).toBeAttached();
  });

  test("Task Detail renders Input Provenance Card, Persisted Steps, and Follow-Execution toggle", async ({
    page,
  }) => {
    // 1. Create a task in Synthetic Sample mode
    await page.goto("/app/tasks/new");
    await page.getByRole("button", { name: /Synthetic Sample/i }).click();
    await page.getByRole("button", { name: "Generate Plan" }).click();

    // 2. Redirected to Task Detail
    await page.waitForURL(/\/app\/tasks\/task-/);

    // 3. Verify Input Provenance Card renders on Task Detail
    await expect(page.getByText("Input Provenance & Staging")).toBeVisible();
    await expect(page.getByText("Synthetic Sample Dataset").first()).toBeVisible();
    await expect(page.getByText("Synthetic automotive EV telemetry sample dataset")).toBeVisible();

    // 4. Approve and execute task
    await page.getByRole("button", { name: "Approve Plan" }).first().click();
    await page.getByRole("button", { name: "Confirm & Queue Execution" }).click();

    // 5. Verify Execution Progress Tracker & 8-Phase Lifecycle
    await expect(page.getByText("Isolated Execution Progress")).toBeVisible();
    await expect(page.getByText("MicroVM Guest Filesystem Mounts")).toBeVisible();
    await expect(page.getByText("/workspace/input/").first()).toBeVisible();
    await expect(page.getByText("/workspace/output/").first()).toBeVisible();

    // 6. Test Follow-Execution Auto-Scroll Toggle
    const followingBtn = page.getByRole("button", { name: /Following Logs/i });
    await expect(followingBtn).toBeVisible();

    // Click to pause auto-scroll
    await followingBtn.click();
    const followExecutionBtn = page.getByRole("button", { name: /Follow Execution/i });
    await expect(followExecutionBtn).toBeVisible();

    // Click to re-enable auto-scroll
    await followExecutionBtn.click();
    await expect(page.getByRole("button", { name: /Following Logs/i })).toBeVisible();

    // 7. Verify Step Logs Viewer tab displays actual persisted steps and outputs
    await page.getByRole("tab", { name: /Execution Logs/i }).click();
    await expect(page.getByText("Guest MicroVM Execution Logs (1 Steps)")).toBeVisible();
    await expect(page.getByText("Step #1")).toBeVisible();
    await expect(page.getByText("Compute cryptographic hashes").first()).toBeVisible();
    await expect(page.getByText("exit: 0")).toBeVisible();
    await expect(page.getByText(/e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855/).first()).toBeVisible();
  });
});

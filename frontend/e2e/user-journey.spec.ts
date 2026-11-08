import { test, expect } from "@playwright/test";

test.describe("Full PartProof User Journey", () => {
  test("completes full lifecycle: unauth redirect -> login -> dashboard -> create task -> plan review -> approval -> execution monitoring -> receipt -> logout", async ({
    page,
  }) => {
    test.setTimeout(60000);

    // 1. Unauthenticated visit to /app must redirect to /login
    await page.goto("/app");
    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByText("Sign In to Console")).toBeVisible();

    // 2. Login with credentials
    await page.getByLabel(/Email Address/i).fill("auditor@partproof.io");
    await page.getByLabel(/^Password/i).fill("PartProofSecureDemo2026!");
    await page.getByRole("button", { name: "Sign In to Console" }).click();

    // Verify redirected to dashboard /app
    await expect(page).toHaveURL(/\/app/);
    await expect(page.getByRole("heading", { name: "Execution Overview" })).toBeVisible();

    // 3. Navigate to Task Composer
    await page.getByRole("link", { name: /Create Task/i }).first().click();
    await expect(page).toHaveURL(/\/app\/tasks\/new/);
    await expect(page.getByRole("heading", { name: "Create Engineering Task" })).toBeVisible();
    await expect(page.getByText("Explicit Approval Required Before Execution")).toBeVisible();

    // 4. Select a preset prompt: "Binary Integrity Audit"
    await page.getByText("Binary Integrity Audit").click();
    const descTextarea = page.getByLabel(/Objective & Requirements/i);
    await expect(descTextarea).not.toBeEmpty();

    // 5. Submit task creation and initiate AI planning
    await page.getByRole("button", { name: "Generate Plan" }).click();

    // 6. Directed to task detail view
    await page.waitForURL(/\/app\/tasks\/task-/);
    await expect(page.getByText("Cryptographic Plan Digest (SHA-256)")).toBeVisible();

    // 7. Verify all 64 characters of canonical SHA-256 plan hash are rendered
    const hashElement = page.getByText("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855").first();
    await expect(hashElement).toBeVisible();

    // 8. Inspect Policy Tab
    await page.getByRole("tab", { name: /Policy Engine/i }).click();
    await expect(page.getByText("Deterministic Policy Engine Inspector")).toBeVisible();
    await expect(page.getByText("ALLOWED")).toBeVisible();

    // 9. Inspect Steps Tab
    await page.getByRole("tab", { name: /Code Steps/i }).click();
    await expect(page.getByText("Compute cryptographic hashes")).toBeVisible();

    // 10. Click "Approve Plan" to open explicit approval confirmation dialog
    await page.getByRole("button", { name: "Approve Plan" }).click();
    await expect(page.getByText("Confirm Plan Approval & Authorize Execution")).toBeVisible();
    await expect(page.getByText("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855").last()).toBeVisible();

    // Confirm approval
    await page.getByRole("button", { name: "Confirm & Queue Execution" }).click();

    // 11. Task execution succeeds; verify Succeeded status badge
    await expect(page.getByText("Succeeded").first()).toBeVisible({ timeout: 10000 });

    // 12. Switch to Execution Logs tab and verify stdout
    await page.getByRole("tab", { name: /Execution Logs/i }).click();
    await expect(page.getByText(/Guest MicroVM Execution Logs/i)).toBeVisible();
    await expect(page.getByText("exit: 0")).toBeVisible();

    // 13. Switch to Receipt & Artifacts tab
    await page.getByRole("tab", { name: /Receipt & Artifacts/i }).click();
    await expect(page.getByText("Cryptographic Execution Receipt")).toBeVisible();
    await expect(page.getByText("SECURITY VERIFIED")).toBeVisible();
    await expect(page.getByText("guest-microsandbox-prod-42").first()).toBeVisible();
    await expect(page.getByText("7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069")).toBeVisible();

    // 14. Check Artifacts Table and verify pending download capability note
    await expect(page.getByText("verification-report.json")).toBeVisible();
    await expect(page.getByText("Artifact Download Note:")).toBeVisible();
    await expect(page.getByText(/pending backend capability/i)).toBeVisible();

    // Ensure no broken 404 download links
    const downloadLinks = await page.locator('a[href*="/download"]').count();
    expect(downloadLinks).toBe(0);

    // 15. Sign out
    await page.getByRole("button", { name: /auditor@partproof\.io/i }).click({ force: true });
    await page.getByRole("menuitem", { name: /Sign Out/i }).click();

    // Verify redirected to login
    await expect(page).toHaveURL(/\/login/);

    // Visiting /app again must redirect to /login
    await page.goto("/app");
    await expect(page).toHaveURL(/\/login/);
  });
});

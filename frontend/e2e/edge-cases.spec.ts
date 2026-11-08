import { test, expect } from "@playwright/test";

test.describe("Edge Cases & Security Controls", () => {
  test("displays error banner on invalid credentials", async ({ page }) => {
    await page.goto("/login");

    await page.getByLabel(/Email Address/i).fill("wrong@partproof.io");
    await page.getByLabel(/^Password/i).fill("WrongPassword123!");
    await page.getByRole("button", { name: "Sign In to Console" }).click();

    await expect(page.getByText("Invalid email or password.")).toBeVisible();
    await expect(page).toHaveURL(/\/login/);
  });

  test("policy denial scenario: renders violations and disables execution approval", async ({
    page,
  }) => {
    // Sign in first
    await page.goto("/login");
    await page.getByLabel(/Email Address/i).fill("auditor@partproof.io");
    await page.getByLabel(/^Password/i).fill("PartProofSecureDemo2026!");
    await page.getByRole("button", { name: "Sign In to Console" }).click();
    await page.waitForURL(/\/app/);

    // Navigate to blocked task
    await page.goto("/app/tasks/task-blocked-99");

    // Verify policy tab shows DISALLOWED and violations
    await page.getByRole("tab", { name: /Policy Engine/i }).click();
    await expect(page.getByText("DISALLOWED")).toBeVisible();
    await expect(page.getByText(/Policy Violations Detected \(2\)/i)).toBeVisible();
    await expect(page.getByText(/Network mode host violates airgap policy/i)).toBeVisible();
    await expect(page.getByText(/Command 'nc' matches forbidden executable rule/i)).toBeVisible();

    // Verify the "Approve Plan" button is strictly disabled
    const approveBtn = page.getByRole("button", { name: "Approve Plan" });
    await expect(approveBtn).toBeDisabled();
  });

  test("reconciliation scenario: renders critical sandbox leak banner and recovery details", async ({
    page,
  }) => {
    // Sign in first
    await page.goto("/login");
    await page.getByLabel(/Email Address/i).fill("auditor@partproof.io");
    await page.getByLabel(/^Password/i).fill("PartProofSecureDemo2026!");
    await page.getByRole("button", { name: "Sign In to Console" }).click();
    await page.waitForURL(/\/app/);

    // Navigate to reconciliation task
    await page.goto("/app/tasks/task-reconcile-88");

    // Verify prominent reconciliation alert banner
    await expect(
      page.getByText(/CRITICAL SECURITY STATE: Sandbox Cleanup Needs Reconciliation/i)
    ).toBeVisible();
    await expect(page.getByText("LEAK DETECTED")).toBeVisible();
    await expect(page.getByRole("alert").getByText("unverified-leak-sandbox-id-8888")).toBeVisible();
    await expect(
      page.getByText(/this task will NEVER be automatically requeued/i)
    ).toBeVisible();
  });

  test("cancellation scenario: aborts active task via confirmation dialog", async ({
    page,
  }) => {
    // Sign in first
    await page.goto("/login");
    await page.getByLabel(/Email Address/i).fill("auditor@partproof.io");
    await page.getByLabel(/^Password/i).fill("PartProofSecureDemo2026!");
    await page.getByRole("button", { name: "Sign In to Console" }).click();
    await page.waitForURL(/\/app/);

    // Navigate to actively running task
    await page.goto("/app/tasks/task-running-77");

    // Click cancel task button
    await page.getByRole("button", { name: "Cancel Task" }).click();
    await expect(page.getByText("Abort Active Task Execution")).toBeVisible();

    // Fill optional reason and confirm
    await page.getByPlaceholder(/e\.g\. Discontinued manual audit/i).fill("Operator security termination");
    await page.getByRole("button", { name: "Confirm Cancellation" }).click();

    // Verify status changes to Cancelled
    await expect(page.getByText("Cancelled").first()).toBeVisible();
  });

  test("plan regeneration scenario: regenerates plan and invalidates previous state", async ({
    page,
  }) => {
    // Sign in first
    await page.goto("/login");
    await page.getByLabel(/Email Address/i).fill("auditor@partproof.io");
    await page.getByLabel(/^Password/i).fill("PartProofSecureDemo2026!");
    await page.getByRole("button", { name: "Sign In to Console" }).click();
    await page.waitForURL(/\/app/);

    // Navigate to blocked task (which is awaiting_approval with violations)
    await page.goto("/app/tasks/task-blocked-99");

    // Verify original plan hash
    await expect(
      page.getByText("f4b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b866")
    ).toBeVisible();

    // Click Regenerate Plan
    await page.getByRole("button", { name: "Regenerate Plan" }).click();

    // Verify new canonical plan hash appears
    await expect(
      page.getByText("a1b2c3d4e5f67890123456789abcdef0123456789abcdef0123456789abcdef0")
    ).toBeVisible();

    // Policy should now be ALLOWED
    await page.getByRole("tab", { name: /Policy Engine/i }).click();
    await expect(page.getByText("ALLOWED")).toBeVisible();
  });
});

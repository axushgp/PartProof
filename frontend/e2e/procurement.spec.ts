import { test, expect } from "@playwright/test";

test.describe("Procurement Intelligence & Forensics E2E Lifecycle", () => {
  test("loads demo dataset -> verifies true landed costs -> executes decision replay -> creates official procurement task", async ({
    page,
  }) => {
    test.setTimeout(60000);

    // 1. Authenticate via login
    await page.goto("/login");
    await page.getByLabel(/Email Address/i).fill("auditor@partproof.io");
    await page.getByLabel(/^Password/i).fill("PartProofSecureDemo2026!");
    await page.getByRole("button", { name: "Sign In to Console" }).click();
    await expect(page).toHaveURL(/\/app/);

    // 2. Navigate to Procurement Intelligence Workspace
    await page.goto("/app/procurement");
    await expect(page.getByRole("heading", { name: "Procurement Intelligence & Forensics" })).toBeVisible();

    // Verify honest labeling of the matching engine
    await expect(page.getByText("Deterministic Part & Policy Engine")).toBeVisible();
    await expect(page.getByText("MicroSandbox Isolated")).toBeVisible();

    // 3. Launch the Synthetic Demonstration Case
    const demoButton = page.getByRole("button", { name: "Load Synthetic Demo Case" });
    await expect(demoButton).toBeVisible();
    await demoButton.click();

    // 4. Verify Award Banner and Side-by-Side Matrix
    await expect(page.getByText("Official Award Recommendation")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Beacon Precision Dynamics" }).first()).toBeVisible();

    // Verify Beacon True Landed Cost ($32,978.64)
    await expect(page.locator("text=$32978.64").first()).toBeVisible();

    // Verify Apex Industrial Components has Compliant and Commercially Expensive badges
    await expect(page.getByText("Commercially Expensive")).toBeVisible();
    await expect(page.locator("text=$35931.00").first()).toBeVisible();

    // 5. Verify Forensic Discrepancy Register
    await expect(page.getByRole("heading", { name: "Procurement Forensics & Discrepancy Register" })).toBeVisible();
    await expect(page.getByText("MOQ-induced excess purchases").first()).toBeVisible();

    // 6. Test Decision Replay (What-If Simulation)
    await expect(page.getByRole("heading", { name: /Procurement Decision Replay/i })).toBeVisible();

    // Click 1-Click Preset 1: Waive $2,920 MOQ Excess & Waive $1,850 Freight
    const preset1Btn = page.getByRole("button", { name: /Apex: Waive \$2,920 MOQ Excess/i });
    await expect(preset1Btn).toBeVisible();
    await preset1Btn.click();

    // Verify simulation recalculation outcome
    await expect(page.getByText("Award Recommendation Changed!")).toBeVisible();
    await expect(page.getByText("+$2676.24")).toBeVisible();

    // 7. Test Voice Briefing attribution & transcript
    await expect(page.getByRole("heading", { name: "Browser-native voice briefing" })).toBeVisible();
    await expect(page.getByText("Underdog Woof: Standby")).toBeVisible();

    // 8. Initiate Official PartProof Isolated Execution Task
    const initTaskBtn = page.getByRole("button", { name: /Initialize Isolated Audit Task/i });
    await expect(initTaskBtn).toBeVisible();
    await initTaskBtn.click();

    // Verify task created with awaiting_approval and plan hash
    await expect(page.getByText("Task ID:")).toBeVisible();
    await expect(page.getByText("awaiting_approval")).toBeVisible();
    await expect(page.getByText("Plan Generated & Policy Verified")).toBeVisible();
    await expect(page.getByRole("button", { name: /Approve & Execute in MicroSandbox/i })).toBeVisible();
  });
});

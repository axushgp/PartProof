import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import CreateTaskPage from "@/app/(dashboard)/app/tasks/new/page";
import { api, ApiError } from "@/lib/api/client";

const mockPush = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mockPush,
  }),
}));

vi.mock("@/lib/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/client")>("@/lib/api/client");
  return {
    ...actual,
    api: {
      tasks: {
        create: vi.fn(),
      },
    },
  };
});

describe("CreateTaskPage Component", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders composer form with inputs, preset prompts, and security notice", () => {
    render(<CreateTaskPage />);

    expect(screen.getByLabelText(/Task Title/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Objective & Requirements/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Generate Plan/i })
    ).toBeInTheDocument();
    expect(screen.getByText(/Explicit Approval Required Before Execution/i)).toBeInTheDocument();
  });

  it("shows validation error if description is shorter than 5 characters", async () => {
    const user = userEvent.setup();
    render(<CreateTaskPage />);

    const descInput = screen.getByLabelText(/Objective & Requirements/i);
    await user.type(descInput, "abc");

    const submitBtn = screen.getByRole("button", {
      name: /Generate Plan/i,
    });
    await user.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText(/Task description must be at least 5 characters long/i)).toBeInTheDocument();
    });

    expect(api.tasks.create).not.toHaveBeenCalled();
  });

  it("populates description and title when a preset prompt is selected", async () => {
    const user = userEvent.setup();
    render(<CreateTaskPage />);

    // Click on the first preset prompt: "Binary Integrity Audit"
    const presetBtn = screen.getByText("Binary Integrity Audit");
    await user.click(presetBtn);

    const descInput = screen.getByLabelText(/Objective & Requirements/i) as HTMLTextAreaElement;
    expect(descInput.value).toContain("SHA-256 digests");
  });

  it("submits valid task and navigates to the newly created task detail view", async () => {
    const user = userEvent.setup();
    vi.mocked(api.tasks.create).mockResolvedValueOnce({
      task: {
        id: "task-test-456",
        user_id: "user-1",
        title: "MicroVM Integrity Test",
        description: "Verify isolated guest execution.",
        status: "planning",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
      artifacts: [],
      events: [],
    });

    render(<CreateTaskPage />);

    const descInput = screen.getByLabelText(/Objective & Requirements/i);
    await user.type(descInput, "Verify isolated guest execution environment.");

    const submitBtn = screen.getByRole("button", {
      name: /Generate Plan/i,
    });
    await user.click(submitBtn);

    await waitFor(() => {
      expect(api.tasks.create).toHaveBeenCalledWith(
        expect.objectContaining({
          title: null,
          description: "Verify isolated guest execution environment.",
        })
      );
      expect(mockPush).toHaveBeenCalledWith("/app/tasks/task-test-456");
    });
  });

  it("displays error banner when planner API rejects the request", async () => {
    const user = userEvent.setup();
    vi.mocked(api.tasks.create).mockRejectedValueOnce(
      new ApiError("Vultr AI inference rate limited. Try again in 30 seconds.", 429)
    );

    render(<CreateTaskPage />);

    const descInput = screen.getByLabelText(/Objective & Requirements/i);
    await user.type(descInput, "Compute SHA-256 hashes of sample test files.");

    const submitBtn = screen.getByRole("button", {
      name: /Generate Plan/i,
    });
    await user.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText(/Vultr AI inference rate limited/i)).toBeInTheDocument();
    });

    expect(mockPush).not.toHaveBeenCalled();
  });
});

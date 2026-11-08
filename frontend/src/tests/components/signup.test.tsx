import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SignupPage from "@/app/(auth)/signup/page";
import { api, ApiError } from "@/lib/api/client";

const mockPush = vi.fn();
const mockRefresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mockPush,
    refresh: mockRefresh,
  }),
}));

vi.mock("@/lib/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/client")>("@/lib/api/client");
  return {
    ...actual,
    api: {
      auth: {
        register: vi.fn(),
      },
    },
  };
});

describe("SignupPage Component", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    sessionStorage.clear();
  });

  it("renders email, password, confirm password inputs, instant provisioning notice, and signup button", () => {
    render(<SignupPage />);

    expect(screen.getByLabelText(/Email Address/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Password/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Confirm Password/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Create Auditor Account/i })
    ).toBeInTheDocument();
    expect(screen.getByText(/Instant Provisioning:/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Sign In/i })).toHaveAttribute("href", "/login");
  });

  it("allows user to type credentials and toggles password visibility controls", async () => {
    const user = userEvent.setup();
    render(<SignupPage />);

    const emailInput = screen.getByLabelText(/Email Address/i) as HTMLInputElement;
    const passwordInput = screen.getByLabelText(/^Password/i) as HTMLInputElement;
    const confirmInput = screen.getByLabelText(/^Confirm Password/i) as HTMLInputElement;

    await user.type(emailInput, "newauditor@partproof.io");
    await user.type(passwordInput, "PartProofSecure2026!");
    await user.type(confirmInput, "PartProofSecure2026!");

    expect(emailInput.value).toBe("newauditor@partproof.io");
    expect(passwordInput.value).toBe("PartProofSecure2026!");
    expect(confirmInput.value).toBe("PartProofSecure2026!");
    expect(passwordInput.type).toBe("password");
    expect(confirmInput.type).toBe("password");

    // Toggle password visibility
    const togglePasswordBtn = screen.getByRole("button", { name: /Show password/i });
    await user.click(togglePasswordBtn);
    expect(passwordInput.type).toBe("text");

    // Toggle confirm password visibility
    const toggleConfirmBtn = screen.getByRole("button", { name: /Show confirm password/i });
    await user.click(toggleConfirmBtn);
    expect(confirmInput.type).toBe("text");
  });

  it("shows validation error on empty fields and weak password", async () => {
    const user = userEvent.setup();
    render(<SignupPage />);

    const submitButton = screen.getByRole("button", { name: /Create Auditor Account/i });
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText(/Email is required/i)).toBeInTheDocument();
      expect(screen.getByText(/Password must be at least 12 characters/i)).toBeInTheDocument();
      expect(screen.getByText(/Please confirm your password/i)).toBeInTheDocument();
    });

    expect(api.auth.register).not.toHaveBeenCalled();
  });

  it("shows validation error when confirmation password does not match", async () => {
    const user = userEvent.setup();
    render(<SignupPage />);

    await user.type(screen.getByLabelText(/Email Address/i), "newauditor@partproof.io");
    await user.type(screen.getByLabelText(/^Password/i), "PartProofSecure2026!");
    await user.type(screen.getByLabelText(/^Confirm Password/i), "MismatchedPassword123!");

    const submitButton = screen.getByRole("button", { name: /Create Auditor Account/i });
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText(/Passwords do not match/i)).toBeInTheDocument();
    });

    expect(api.auth.register).not.toHaveBeenCalled();
  });

  it("registers successfully, sets HttpOnly cookie via BFF, and redirects to /app", async () => {
    const user = userEvent.setup();
    vi.mocked(api.auth.register).mockResolvedValueOnce({
      user_id: "user-new-123",
      email: "newauditor@partproof.io",
      role: "auditor",
    });

    render(<SignupPage />);

    await user.type(screen.getByLabelText(/Email Address/i), "newauditor@partproof.io");
    await user.type(screen.getByLabelText(/^Password/i), "PartProofSecure2026!");
    await user.type(screen.getByLabelText(/^Confirm Password/i), "PartProofSecure2026!");

    const submitButton = screen.getByRole("button", { name: /Create Auditor Account/i });
    await user.click(submitButton);

    await waitFor(() => {
      expect(api.auth.register).toHaveBeenCalledWith({
        email: "newauditor@partproof.io",
        password: "PartProofSecure2026!",
        confirm_password: "PartProofSecure2026!",
      });
      expect(mockPush).toHaveBeenCalledWith("/app");
      expect(mockRefresh).toHaveBeenCalled();
    });

    // Verify token is never exposed to localStorage or sessionStorage
    expect(localStorage.getItem("token")).toBeNull();
    expect(localStorage.getItem("partproof_session")).toBeNull();
    expect(sessionStorage.getItem("token")).toBeNull();
  });

  it("displays duplicate user error banner when registration fails with 409", async () => {
    const user = userEvent.setup();
    vi.mocked(api.auth.register).mockRejectedValueOnce(
      new ApiError("A user with this email address already exists", 409)
    );

    render(<SignupPage />);

    await user.type(screen.getByLabelText(/Email Address/i), "duplicate@partproof.io");
    await user.type(screen.getByLabelText(/^Password/i), "PartProofSecure2026!");
    await user.type(screen.getByLabelText(/^Confirm Password/i), "PartProofSecure2026!");

    const submitButton = screen.getByRole("button", { name: /Create Auditor Account/i });
    await user.click(submitButton);

    await waitFor(() => {
      expect(
        screen.getByText(/A user with this email address already exists\./i)
      ).toBeInTheDocument();
    });

    expect(mockPush).not.toHaveBeenCalled();
  });
});

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import LoginPage from "@/app/(auth)/login/page";
import { api, ApiError } from "@/lib/api/client";

const mockPush = vi.fn();
const mockRefresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mockPush,
    refresh: mockRefresh,
  }),
  useSearchParams: () => ({
    get: vi.fn().mockReturnValue(null),
  }),
}));

vi.mock("@/lib/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/client")>("@/lib/api/client");
  return {
    ...actual,
    api: {
      auth: {
        login: vi.fn(),
      },
    },
  };
});

describe("LoginPage Component", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    sessionStorage.clear();
  });

  it("renders email, password inputs and sign-in button without demo credentials button", () => {
    render(<LoginPage />);

    expect(screen.getByLabelText(/Email Address/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Password/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Sign in to Console/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /autofill/i })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Create Auditor Account/i })).toHaveAttribute("href", "/signup");
  });

  it("allows user to type credentials directly and toggles password visibility", async () => {
    const user = userEvent.setup();
    render(<LoginPage />);

    const emailInput = screen.getByLabelText(/Email Address/i) as HTMLInputElement;
    const passwordInput = screen.getByLabelText(/^Password/i) as HTMLInputElement;

    await user.type(emailInput, "auditor@partproof.io");
    await user.type(passwordInput, "PartProofSecureDemo2026!");

    expect(emailInput.value).toBe("auditor@partproof.io");
    expect(passwordInput.value).toBe("PartProofSecureDemo2026!");
    expect(passwordInput.type).toBe("password");

    const toggleBtn = screen.getByRole("button", { name: /Show password/i });
    await user.click(toggleBtn);
    expect(passwordInput.type).toBe("text");
  });

  it("shows validation error on empty email and password submission", async () => {
    const user = userEvent.setup();
    render(<LoginPage />);

    const submitButton = screen.getByRole("button", { name: /Sign in to Console/i });
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText(/Email is required/i)).toBeInTheDocument();
      expect(screen.getByText(/Password is required/i)).toBeInTheDocument();
    });

    expect(api.auth.login).not.toHaveBeenCalled();
  });

  it("authenticates successfully and redirects to /app", async () => {
    const user = userEvent.setup();
    vi.mocked(api.auth.login).mockResolvedValueOnce({
      user_id: "user-1",
      email: "auditor@partproof.io",
      role: "auditor",
    });

    render(<LoginPage />);

    await user.type(screen.getByLabelText(/Email Address/i), "auditor@partproof.io");
    await user.type(screen.getByLabelText(/^Password/i), "PartProofSecureDemo2026!");

    const submitButton = screen.getByRole("button", { name: /Sign in to Console/i });
    await user.click(submitButton);

    await waitFor(() => {
      expect(api.auth.login).toHaveBeenCalledWith({
        email: "auditor@partproof.io",
        password: "PartProofSecureDemo2026!",
      });
      expect(mockPush).toHaveBeenCalledWith("/app");
      expect(mockRefresh).toHaveBeenCalled();
    });

    // Verify token is never placed in client-accessible storage
    expect(localStorage.getItem("token")).toBeNull();
    expect(localStorage.getItem("partproof_session")).toBeNull();
    expect(sessionStorage.getItem("token")).toBeNull();
  });

  it("displays error banner when authentication fails with 401", async () => {
    const user = userEvent.setup();
    vi.mocked(api.auth.login).mockRejectedValueOnce(
      new ApiError("Invalid credentials", 401)
    );

    render(<LoginPage />);

    await user.type(screen.getByLabelText(/Email Address/i), "auditor@partproof.io");
    await user.type(screen.getByLabelText(/^Password/i), "WrongPassword123!");

    const submitButton = screen.getByRole("button", { name: /Sign in to Console/i });
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText(/Invalid email or password\./i)).toBeInTheDocument();
    });

    expect(mockPush).not.toHaveBeenCalled();
  });
});

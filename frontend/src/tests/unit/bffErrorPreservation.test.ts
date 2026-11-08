import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { NextRequest } from "next/server";
import { POST as tasksPostRoute } from "@/app/api/tasks/route";
import { POST as planPostRoute } from "@/app/api/tasks/[taskId]/plan/route";
import * as sessionModule from "@/lib/auth/session";

vi.mock("@/lib/auth/session", () => ({
  getSessionToken: vi.fn(),
  clearSessionCookie: vi.fn(),
}));

describe("BFF Error Preservation and Upstream Status Passthrough", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    process.env.APP_ORIGIN = "http://localhost:3000";
    process.env.PARTPROOF_API_URL = "http://127.0.0.1:8000";
    vi.mocked(sessionModule.getSessionToken).mockResolvedValue("test_valid_jwt");
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.clearAllMocks();
  });

  it("preserves 504 Gateway Timeout and exact detail from backend", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 504,
      headers: new Headers({ "content-type": "application/json" }),
      json: () =>
        Promise.resolve({
          detail: "Task planning failed: Vultr Serverless Inference request timed out after fallback",
        }),
    });

    const req = new NextRequest("http://localhost:3000/api/tasks", {
      method: "POST",
      headers: {
        origin: "http://localhost:3000",
        "content-type": "application/json",
      },
      body: JSON.stringify({
        description: "Analyze engineering BOM variance across suppliers",
      }),
    });

    const res = await tasksPostRoute(req);
    expect(res.status).toBe(504);
    const data = await res.json();
    expect(data.detail).toBe(
      "Task planning failed: Vultr Serverless Inference request timed out after fallback"
    );
  });

  it("preserves 502 Bad Gateway and upstream auth detail without clearing user cookie", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 502,
      headers: new Headers({ "content-type": "application/json" }),
      json: () =>
        Promise.resolve({
          detail: "Task planning failed: Upstream AI inference authentication or configuration failed.",
        }),
    });

    const req = new NextRequest("http://localhost:3000/api/tasks", {
      method: "POST",
      headers: {
        origin: "http://localhost:3000",
        "content-type": "application/json",
      },
      body: JSON.stringify({
        description: "Analyze engineering BOM variance across suppliers",
      }),
    });

    const res = await tasksPostRoute(req);
    expect(res.status).toBe(502);
    const data = await res.json();
    expect(data.detail).toContain("Upstream AI inference authentication");
    // Ensure clearSessionCookie was NOT called because status is 502, not 401
    expect(sessionModule.clearSessionCookie).not.toHaveBeenCalled();
  });

  it("preserves 503 Service Unavailable on provider connection error", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      headers: new Headers({ "content-type": "application/json" }),
      json: () =>
        Promise.resolve({
          detail: "Task planning failed: Connection error to Vultr endpoint on glm-5.3",
        }),
    });

    const req = new NextRequest("http://localhost:3000/api/tasks/task-456/plan", {
      method: "POST",
      headers: {
        origin: "http://localhost:3000",
      },
    });

    const res = await planPostRoute(req, {
      params: Promise.resolve({ taskId: "task-456" }),
    });

    expect(res.status).toBe(503);
    const data = await res.json();
    expect(data.detail).toContain("Connection error to Vultr endpoint");
  });

  it("preserves 422 Unprocessable Entity on plan validation failure", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      headers: new Headers({ "content-type": "application/json" }),
      json: () =>
        Promise.resolve({
          detail: "Task planning failed: Step code violates safety constraints: empty code",
        }),
    });

    const req = new NextRequest("http://localhost:3000/api/tasks/task-789/plan", {
      method: "POST",
      headers: {
        origin: "http://localhost:3000",
      },
    });

    const res = await planPostRoute(req, {
      params: Promise.resolve({ taskId: "task-789" }),
    });

    expect(res.status).toBe(422);
    const data = await res.json();
    expect(data.detail).toContain("Step code violates safety constraints");
  });

  it("returns 504 when upstream fetch throws a TimeoutError", async () => {
    const timeoutErr = new Error("The operation was aborted due to timeout");
    timeoutErr.name = "TimeoutError";
    global.fetch = vi.fn().mockRejectedValue(timeoutErr);

    const req = new NextRequest("http://localhost:3000/api/tasks", {
      method: "POST",
      headers: {
        origin: "http://localhost:3000",
        "content-type": "application/json",
      },
      body: JSON.stringify({
        description: "Analyze engineering BOM variance across suppliers",
      }),
    });

    const res = await tasksPostRoute(req);
    expect(res.status).toBe(504);
    const data = await res.json();
    expect(data.detail).toContain("gateway timeout");
  });

  it("returns 502 when upstream fetch throws a network connection failure", async () => {
    const netErr = new Error("ECONNREFUSED 127.0.0.1:8000");
    global.fetch = vi.fn().mockRejectedValue(netErr);

    const req = new NextRequest("http://localhost:3000/api/tasks", {
      method: "POST",
      headers: {
        origin: "http://localhost:3000",
        "content-type": "application/json",
      },
      body: JSON.stringify({
        description: "Analyze engineering BOM variance across suppliers",
      }),
    });

    const res = await tasksPostRoute(req);
    expect(res.status).toBe(502);
    const data = await res.json();
    expect(data.detail).toContain("Unable to reach PartProof backend service");
  });
});

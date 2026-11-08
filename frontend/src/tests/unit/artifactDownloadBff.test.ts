import { describe, it, expect, vi, beforeEach } from "vitest";
import { NextRequest } from "next/server";
import {
  GET as downloadRoute,
  isValidArtifactId,
} from "@/app/api/artifacts/[artifactId]/download/route";
import { GET as taskScopedDownloadRoute } from "@/app/api/tasks/[taskId]/artifacts/[artifactId]/download/route";
import * as sessionModule from "@/lib/auth/session";

vi.mock("@/lib/auth/session", () => ({
  getSessionToken: vi.fn(),
  clearSessionCookie: vi.fn(),
}));

describe("Artifact Download BFF Route", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    process.env.PARTPROOF_API_URL = "http://127.0.0.1:8000";
  });

  describe("isValidArtifactId", () => {
    it("accepts valid alphanumeric, hyphenated, and underscore artifact IDs", () => {
      expect(isValidArtifactId("art-100-abc")).toBe(true);
      expect(isValidArtifactId("00000000-0000-0000-0000-000000000000")).toBe(true);
      expect(isValidArtifactId("artifact_42")).toBe(true);
      expect(isValidArtifactId("a1")).toBe(true);
    });

    it("rejects path traversal attempts", () => {
      expect(isValidArtifactId("../etc/passwd")).toBe(false);
      expect(isValidArtifactId("..\\windows\\system32")).toBe(false);
      expect(isValidArtifactId("artifacts/../../secret")).toBe(false);
      expect(isValidArtifactId("..")).toBe(false);
    });

    it("rejects invalid characters, whitespace, and empty strings", () => {
      expect(isValidArtifactId("")).toBe(false);
      expect(isValidArtifactId("art;rm -rf")).toBe(false);
      expect(isValidArtifactId("art with spaces")).toBe(false);
      expect(isValidArtifactId("a".repeat(65))).toBe(false);
    });
  });

  describe("GET /api/artifacts/[artifactId]/download", () => {
    it("returns 400 when artifact ID format is invalid", async () => {
      const req = new NextRequest("http://localhost:3000/api/artifacts/../invalid/download");
      const res = await downloadRoute(req, {
        params: Promise.resolve({ artifactId: "../invalid" }),
      });

      expect(res.status).toBe(400);
      const json = await res.json();
      expect(json.detail).toBe("Invalid artifact ID format");
    });

    it("returns 401 when user is not authenticated", async () => {
      vi.mocked(sessionModule.getSessionToken).mockResolvedValue(null);

      const req = new NextRequest("http://localhost:3000/api/artifacts/art-100/download");
      const res = await downloadRoute(req, {
        params: Promise.resolve({ artifactId: "art-100" }),
      });

      expect(res.status).toBe(401);
      const json = await res.json();
      expect(json.detail).toBe("Not authenticated");
    });

    it("clears session cookie and returns 401 when upstream returns 401", async () => {
      vi.mocked(sessionModule.getSessionToken).mockResolvedValue("expired_or_invalid_jwt");

      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: () => Promise.resolve({ detail: "Token expired" }),
      });

      const req = new NextRequest("http://localhost:3000/api/artifacts/art-100/download");
      const res = await downloadRoute(req, {
        params: Promise.resolve({ artifactId: "art-100" }),
      });

      expect(sessionModule.clearSessionCookie).toHaveBeenCalled();
      expect(res.status).toBe(401);
      const json = await res.json();
      expect(json.detail).toBe("Session expired or invalid");
    });

    it("forwards upstream 403 Forbidden with detail when unauthorized", async () => {
      vi.mocked(sessionModule.getSessionToken).mockResolvedValue("valid_jwt");

      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 403,
        json: () => Promise.resolve({ detail: "Access denied" }),
      });

      const req = new NextRequest("http://localhost:3000/api/artifacts/art-100/download");
      const res = await downloadRoute(req, {
        params: Promise.resolve({ artifactId: "art-100" }),
      });

      expect(res.status).toBe(403);
      const json = await res.json();
      expect(json.detail).toBe("Access denied");
    });

    it("forwards upstream 404 Not Found when artifact is missing", async () => {
      vi.mocked(sessionModule.getSessionToken).mockResolvedValue("valid_jwt");

      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: () => Promise.resolve({ detail: "Artifact not found" }),
      });

      const req = new NextRequest("http://localhost:3000/api/artifacts/art-999/download");
      const res = await downloadRoute(req, {
        params: Promise.resolve({ artifactId: "art-999" }),
      });

      expect(res.status).toBe(404);
      const json = await res.json();
      expect(json.detail).toBe("Artifact not found");
    });

    it("forwards upstream 409 Conflict when integrity check fails", async () => {
      vi.mocked(sessionModule.getSessionToken).mockResolvedValue("valid_jwt");

      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 409,
        json: () => Promise.resolve({ detail: "Artifact integrity verification failed: SHA-256 digest mismatch" }),
      });

      const req = new NextRequest("http://localhost:3000/api/artifacts/art-tampered/download");
      const res = await downloadRoute(req, {
        params: Promise.resolve({ artifactId: "art-tampered" }),
      });

      expect(res.status).toBe(409);
      const json = await res.json();
      expect(json.detail).toContain("integrity verification failed");
    });

    it("streams binary response with safe headers when upstream succeeds", async () => {
      vi.mocked(sessionModule.getSessionToken).mockResolvedValue("valid_jwt");

      const binaryStream = new ReadableStream({
        start(controller) {
          controller.enqueue(new TextEncoder().encode("col1,col2\nval1,val2\n"));
          controller.close();
        },
      });

      const upstreamHeaders = new Headers({
        "content-type": "text/csv; charset=utf-8",
        "content-disposition": 'attachment; filename="report.csv"; filename*=UTF-8\'\'report.csv',
        "content-length": "20",
        "cache-control": "private, no-store",
        "x-content-type-options": "nosniff",
      });

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: upstreamHeaders,
        body: binaryStream,
      });

      const req = new NextRequest("http://localhost:3000/api/artifacts/art-100/download");
      const res = await downloadRoute(req, {
        params: Promise.resolve({ artifactId: "art-100" }),
      });

      expect(res.status).toBe(200);
      expect(res.headers.get("content-type")).toContain("text/csv");
      expect(res.headers.get("content-disposition")).toContain('filename="report.csv"');
      expect(res.headers.get("cache-control")).toBe("private, no-store");
      expect(res.headers.get("x-content-type-options")).toBe("nosniff");

      const text = await res.text();
      expect(text).toBe("col1,col2\nval1,val2\n");
    });

    it("returns 502 when backend fetch throws a network failure", async () => {
      vi.mocked(sessionModule.getSessionToken).mockResolvedValue("valid_jwt");

      global.fetch = vi.fn().mockRejectedValue(new Error("ECONNREFUSED"));

      const req = new NextRequest("http://localhost:3000/api/artifacts/art-100/download");
      const res = await downloadRoute(req, {
        params: Promise.resolve({ artifactId: "art-100" }),
      });

      expect(res.status).toBe(502);
      const json = await res.json();
      expect(json.detail).toContain("Unable to reach PartProof backend service");
    });
  });

  describe("GET /api/tasks/[taskId]/artifacts/[artifactId]/download", () => {
    it("returns 400 when task ID format is invalid", async () => {
      const req = new NextRequest("http://localhost:3000/api/tasks/../invalid/artifacts/art-100/download");
      const res = await taskScopedDownloadRoute(req, {
        params: Promise.resolve({ taskId: "../invalid", artifactId: "art-100" }),
      });

      expect(res.status).toBe(400);
      const json = await res.json();
      expect(json.detail).toBe("Invalid task ID format");
    });

    it("returns 400 when artifact ID format is invalid", async () => {
      const req = new NextRequest("http://localhost:3000/api/tasks/task-100/artifacts/../invalid/download");
      const res = await taskScopedDownloadRoute(req, {
        params: Promise.resolve({ taskId: "task-100", artifactId: "../invalid" }),
      });

      expect(res.status).toBe(400);
      const json = await res.json();
      expect(json.detail).toBe("Invalid artifact ID format");
    });

    it("forwards to upstream task-scoped URL and streams binary body", async () => {
      vi.mocked(sessionModule.getSessionToken).mockResolvedValue("valid_jwt");

      const binaryStream = new ReadableStream({
        start(controller) {
          controller.enqueue(new TextEncoder().encode("task-scoped data"));
          controller.close();
        },
      });

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({
          "content-type": "text/plain",
          "content-disposition": 'attachment; filename="scoped.txt"',
          "content-length": "16",
        }),
        body: binaryStream,
      });

      const req = new NextRequest("http://localhost:3000/api/tasks/task-100/artifacts/art-100/download");
      const res = await taskScopedDownloadRoute(req, {
        params: Promise.resolve({ taskId: "task-100", artifactId: "art-100" }),
      });

      expect(res.status).toBe(200);
      expect(global.fetch).toHaveBeenCalledWith(
        "http://127.0.0.1:8000/api/v1/tasks/task-100/artifacts/art-100/download",
        expect.objectContaining({ method: "GET" })
      );
      const text = await res.text();
      expect(text).toBe("task-scoped data");
    });
  });
});

import { describe, it, expect, beforeEach } from "vitest";
import { NextRequest } from "next/server";
import { isValidTaskId, validateMutationSecurity } from "@/lib/api/bffProxyHelper";
import { getSessionCookieName, getJwtExpiry } from "@/lib/auth/session";

describe("BFF Proxy Security", () => {
  beforeEach(() => {
    process.env.APP_ORIGIN = "http://localhost:3000";
  });

  describe("isValidTaskId", () => {
    it("accepts valid alphanumeric IDs, hyphens, and underscores", () => {
      expect(isValidTaskId("task-123-abc")).toBe(true);
      expect(isValidTaskId("abc_123_456")).toBe(true);
      expect(isValidTaskId("0123456789abcdef")).toBe(true);
      expect(isValidTaskId("t1")).toBe(true);
    });

    it("rejects path traversal attacks", () => {
      expect(isValidTaskId("../etc/passwd")).toBe(false);
      expect(isValidTaskId("..\\windows\\system32")).toBe(false);
      expect(isValidTaskId("tasks/../../secret")).toBe(false);
      expect(isValidTaskId("%2e%2e%2f")).toBe(false);
    });

    it("rejects SQL injection and shell characters", () => {
      expect(isValidTaskId("task; DROP TABLE tasks;")).toBe(false);
      expect(isValidTaskId("task' OR 1=1 --")).toBe(false);
      expect(isValidTaskId("task | rm -rf")).toBe(false);
      expect(isValidTaskId("task`whoami`")).toBe(false);
    });

    it("rejects excessively long or empty IDs", () => {
      expect(isValidTaskId("")).toBe(false);
      expect(isValidTaskId("a".repeat(65))).toBe(false);
    });
  });

  describe("validateMutationSecurity", () => {
    it("allows GET requests unconditionally", () => {
      const req = new NextRequest("http://localhost:3000/api/tasks", {
        method: "GET",
      });
      const check = validateMutationSecurity(req);
      expect(check.valid).toBe(true);
    });

    it("allows POST with matching Origin header", () => {
      const req = new NextRequest("http://localhost:3000/api/tasks", {
        method: "POST",
        headers: {
          origin: "http://localhost:3000",
        },
      });
      const check = validateMutationSecurity(req);
      expect(check.valid).toBe(true);
    });

    it("blocks POST with mismatched Origin header (cross-origin CSRF attempt)", () => {
      const req = new NextRequest("http://localhost:3000/api/tasks", {
        method: "POST",
        headers: {
          origin: "https://evil-attacker.com",
        },
      });
      const check = validateMutationSecurity(req);
      expect(check.valid).toBe(false);
      expect(check.error).toContain("Invalid request origin");
    });

    it("blocks POST when Sec-Fetch-Site is cross-site", () => {
      const req = new NextRequest("http://localhost:3000/api/tasks", {
        method: "POST",
        headers: {
          "sec-fetch-site": "cross-site",
          origin: "http://localhost:3000",
        },
      });
      const check = validateMutationSecurity(req);
      expect(check.valid).toBe(false);
      expect(check.error).toContain("Cross-site requests forbidden");
    });

    it("handles malformed Origin header safely", () => {
      const req = new NextRequest("http://localhost:3000/api/tasks", {
        method: "POST",
        headers: {
          origin: "http://",
        },
      });
      const check = validateMutationSecurity(req);
      expect(check.valid).toBe(false);
      expect(check.error).toContain("Malformed Origin");
    });
  });

  describe("Session Cookie Configuration", () => {
    it("uses partproof_session cookie name in local development", () => {
      (process.env as Record<string, string | undefined>).NODE_ENV = "development";
      process.env.APP_ORIGIN = "http://localhost:3000";
      expect(getSessionCookieName()).toBe("partproof_session");
    });

    it("uses __Host-partproof_session cookie name in production with HTTPS", () => {
      (process.env as Record<string, string | undefined>).NODE_ENV = "production";
      process.env.APP_ORIGIN = "https://app.partproof.io";
      expect(getSessionCookieName()).toBe("__Host-partproof_session");
    });

    it("parses JWT expiry from payload exp claim", () => {
      const expTimestamp = Math.floor(Date.now() / 1000) + 3600;
      const header = Buffer.from(JSON.stringify({ alg: "HS256", typ: "JWT" })).toString("base64url");
      const payload = Buffer.from(JSON.stringify({ sub: "user1", exp: expTimestamp })).toString("base64url");
      const fakeToken = `${header}.${payload}.fakesignature`;

      const expiry = getJwtExpiry(fakeToken);
      expect(expiry).toBeDefined();
      expect(Math.floor(expiry!.getTime() / 1000)).toBe(expTimestamp);
    });

    it("handles invalid or non-JWT strings safely", () => {
      expect(getJwtExpiry("not-a-token")).toBeUndefined();
      expect(getJwtExpiry("a.b")).toBeUndefined();
    });
  });
});

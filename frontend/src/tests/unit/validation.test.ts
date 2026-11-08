import { describe, it, expect } from "vitest";
import {
  loginSchema,
  registerSchema,
  taskCreateSchema,
  approvalSchema,
  cancelSchema,
} from "@/lib/validation";

describe("Validation Schemas", () => {
  describe("loginSchema", () => {
    it("accepts valid email and password", () => {
      const result = loginSchema.safeParse({
        email: "engineer@partproof.io",
        password: "securepassword123",
      });
      expect(result.success).toBe(true);
    });

    it("rejects invalid email address", () => {
      const result = loginSchema.safeParse({
        email: "not-an-email",
        password: "securepassword123",
      });
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.issues[0].message).toContain("email");
      }
    });

    it("rejects empty password", () => {
      const result = loginSchema.safeParse({
        email: "engineer@partproof.io",
        password: "",
      });
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.issues[0].message).toContain("Password is required");
      }
    });
  });

  describe("taskCreateSchema", () => {
    it("accepts valid description with optional title", () => {
      const result = taskCreateSchema.safeParse({
        title: "Test Task",
        description: "Run comprehensive security verification on microVM sandbox.",
      });
      expect(result.success).toBe(true);
    });

    it("accepts valid description with empty title", () => {
      const result = taskCreateSchema.safeParse({
        title: "",
        description: "Run security audit on packages.",
      });
      expect(result.success).toBe(true);
    });

    it("rejects description shorter than 5 characters", () => {
      const result = taskCreateSchema.safeParse({
        description: "test",
      });
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.issues[0].message).toContain("at least 5 characters");
      }
    });

    it("rejects description containing only whitespace", () => {
      const result = taskCreateSchema.safeParse({
        description: "    ",
      });
      expect(result.success).toBe(false);
    });

    it("rejects title exceeding 120 characters", () => {
      const result = taskCreateSchema.safeParse({
        title: "a".repeat(121),
        description: "Valid description for the task",
      });
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.issues[0].message).toContain("cannot exceed 120");
      }
    });
  });

  describe("approvalSchema", () => {
    it("accepts approved decision with valid reason", () => {
      const result = approvalSchema.safeParse({
        decision: "approved",
        reason: "Inspected network and command policies. Approved for execution.",
      });
      expect(result.success).toBe(true);
    });

    it("accepts rejected decision with reason", () => {
      const result = approvalSchema.safeParse({
        decision: "rejected",
        reason: "Detected network egress rule violation.",
      });
      expect(result.success).toBe(true);
    });

    it("accepts approval without reason as reason is optional", () => {
      const result = approvalSchema.safeParse({
        decision: "approved",
      });
      expect(result.success).toBe(true);
    });

    it("rejects invalid decision enum value", () => {
      const result = approvalSchema.safeParse({
        decision: "maybe",
      });
      expect(result.success).toBe(false);
    });
  });

  describe("cancelSchema", () => {
    it("accepts valid cancellation reason", () => {
      const result = cancelSchema.safeParse({
        reason: "User requested abort before microVM startup.",
      });
      expect(result.success).toBe(true);
    });

    it("accepts empty cancellation reason as optional", () => {
      const result = cancelSchema.safeParse({});
      expect(result.success).toBe(true);
    });

    it("rejects reason exceeding 500 characters", () => {
      const result = cancelSchema.safeParse({
        reason: "a".repeat(501),
      });
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.issues[0].message).toContain("cannot exceed 500");
      }
    });
  });

  describe("registerSchema", () => {
    it("accepts valid email, password >= 12 chars, and matching confirmPassword", () => {
      const result = registerSchema.safeParse({
        email: "newauditor@partproof.io",
        password: "PartProofSecure2026!",
        confirmPassword: "PartProofSecure2026!",
      });
      expect(result.success).toBe(true);
    });

    it("rejects password shorter than 12 characters", () => {
      const result = registerSchema.safeParse({
        email: "newauditor@partproof.io",
        password: "Short123!",
        confirmPassword: "Short123!",
      });
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.issues[0].message).toContain("at least 12 characters");
      }
    });

    it("rejects password exceeding 72 bytes", () => {
      const result = registerSchema.safeParse({
        email: "newauditor@partproof.io",
        password: "a".repeat(73),
        confirmPassword: "a".repeat(73),
      });
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.issues[0].message).toContain("cannot exceed 72 bytes");
      }
    });

    it("rejects mismatched confirm password", () => {
      const result = registerSchema.safeParse({
        email: "newauditor@partproof.io",
        password: "PartProofSecure2026!",
        confirmPassword: "DifferentPassword123!",
      });
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.issues[0].message).toContain("Passwords do not match");
      }
    });

    it("rejects invalid email address", () => {
      const result = registerSchema.safeParse({
        email: "invalid-email",
        password: "PartProofSecure2026!",
        confirmPassword: "PartProofSecure2026!",
      });
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.issues[0].message).toContain("Invalid email address");
      }
    });

    it("rejects missing confirm password", () => {
      const result = registerSchema.safeParse({
        email: "newauditor@partproof.io",
        password: "PartProofSecure2026!",
        confirmPassword: "",
      });
      expect(result.success).toBe(false);
    });
  });
});

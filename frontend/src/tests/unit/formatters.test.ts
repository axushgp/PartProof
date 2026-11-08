import { describe, it, expect } from "vitest";
import {
  truncateHash,
  formatBytes,
  formatDuration,
  formatDate,
  formatRelativeTime,
} from "@/lib/formatters";

describe("Formatters", () => {
  describe("truncateHash", () => {
    const fullHash = "a3f5b9c1d2e4f6a8b0c2d4e6f8a0b2c4d6e8f0a2b4c6d8e0f2a4b6c8d0e2f4a6";

    it("returns placeholder dash if hash is falsy", () => {
      expect(truncateHash("")).toBe("—");
      expect(truncateHash(null)).toBe("—");
      expect(truncateHash(undefined)).toBe("—");
    });

    it("truncates with head and tail preserving both ends", () => {
      expect(truncateHash(fullHash, 8, 8)).toBe("a3f5b9c1...d0e2f4a6");
    });

    it("does not truncate if hash is shorter than threshold", () => {
      expect(truncateHash("short", 10, 10)).toBe("short");
    });
  });

  describe("formatBytes", () => {
    it("handles 0, null, and negative bytes", () => {
      expect(formatBytes(0)).toBe("0 B");
      expect(formatBytes(null)).toBe("0 B");
      expect(formatBytes(-10)).toBe("0 B");
    });

    it("formats bytes, kilobytes, megabytes correctly", () => {
      expect(formatBytes(500)).toBe("500 B");
      expect(formatBytes(1024)).toBe("1.0 KB");
      expect(formatBytes(1536)).toBe("1.5 KB");
      expect(formatBytes(1048576)).toBe("1.0 MB");
      expect(formatBytes(5242880)).toBe("5.0 MB");
    });
  });

  describe("formatDuration", () => {
    it("handles 0 and null durations", () => {
      expect(formatDuration(null)).toBe("—");
      expect(formatDuration(0)).toBe("0s");
    });

    it("formats milliseconds accurately", () => {
      expect(formatDuration(0.42)).toBe("420ms");
    });

    it("formats seconds accurately", () => {
      expect(formatDuration(42)).toBe("42s");
      expect(formatDuration(42.6)).toBe("42.6s");
    });

    it("formats minutes and seconds accurately", () => {
      expect(formatDuration(90)).toBe("1m 30s");
      expect(formatDuration(3665)).toBe("61m 5s");
    });
  });

  describe("formatDate and formatRelativeTime", () => {
    it("returns placeholder dash for null dates", () => {
      expect(formatDate(null)).toBe("—");
      expect(formatRelativeTime(null)).toBe("—");
    });

    it("formats valid ISO timestamp into readable text", () => {
      const formatted = formatDate("2026-03-24T12:00:00Z");
      expect(formatted).toContain("2026");
    });

    it("handles invalid date gracefully", () => {
      expect(formatDate("invalid-date-string")).toBe("invalid-date-string");
      expect(formatRelativeTime("invalid-date-string")).toBe("invalid-date-string");
    });
  });
});

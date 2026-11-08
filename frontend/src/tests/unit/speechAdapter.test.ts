import { describe, it, expect } from "vitest";
import {
  BrowserSpeechAdapter,
  UnderdogWoofAdapter,
  sanitizeProcurementTextForSpeech,
} from "@/lib/voice/speechAdapter";

describe("Local Voice Briefing & Speech Adapters", () => {
  it("sanitizes procurement text and currency values for natural speech synthesis", () => {
    const raw = "Total cost is $32,978.64 for 100 pcs with 72V 150A BLDC controller and MOQ excess.";
    const sanitized = sanitizeProcurementTextForSpeech(raw);

    expect(sanitized).toContain("32,978 dollars and 64 cents");
    expect(sanitized).toContain("100 pieces");
    expect(sanitized).toContain("72 volts");
    expect(sanitized).toContain("150 amperes");
    expect(sanitized).toContain("M O Q");
    expect(sanitized).toContain("B L D C");
  });

  it("handles Underdog Woof adapter licensing and status correctly", () => {
    const woof = new UnderdogWoofAdapter();
    expect(woof.id).toBe("underdog-woof");
    expect(woof.name).toContain("Underdog Woof");
    expect(woof.isAvailable()).toBe(false); // Standalone browser WASM weights pending official distribution

    const license = woof.getLicenseStatus();
    expect(license.licenseName).toBe("Underdog Non-Commercial License 1.0");
    expect(license.isCommercialPermitted).toBe(false);
    expect(license.attributionRequired).toBe(true);
    expect(woof.getAttribution()).toContain("Voice by Underdog Woof");
  });

  it("initializes browser-native speech adapter", () => {
    const browserAdapter = new BrowserSpeechAdapter();
    expect(browserAdapter.id).toBe("browser-native");
    expect(browserAdapter.name).toContain("Browser-Native");
    const license = browserAdapter.getLicenseStatus();
    expect(license.isCommercialPermitted).toBe(true);
  });
});

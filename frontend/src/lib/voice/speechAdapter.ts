/**
 * Local Voice Briefing Architecture
 * Modular Text-to-Speech system supporting Browser-Native SpeechSynthesis and Underdog Woof adapter.
 */

export interface VoiceOptions {
  rate?: number;
  pitch?: number;
  volume?: number;
  onStart?: () => void;
  onEnd?: () => void;
  onError?: (err: unknown) => void;
  onPause?: () => void;
  onResume?: () => void;
}

export interface VoiceBriefingAdapter {
  id: string;
  name: string;
  isAvailable(): boolean;
  speak(text: string, options?: VoiceOptions): void;
  pause(): void;
  resume(): void;
  stop(): void;
  isSpeaking(): boolean;
  isPaused(): boolean;
  getAttribution(): string;
  getLicenseStatus(): {
    licenseName: string;
    isCommercialPermitted: boolean;
    attributionRequired: boolean;
    details: string;
  };
}

/**
 * Phonetically tunes procurement jargon, part numbers, and currencies for natural speech.
 */
export function sanitizeProcurementTextForSpeech(text: string): string {
  if (!text) return "";
  let s = text;

  // Currencies: $32,978.64 -> 32,978 dollars and 64 cents
  s = s.replace(/\$([0-9,]+)\.([0-9]{2})/g, "$1 dollars and $2 cents");
  s = s.replace(/\$([0-9,]+)/g, "$1 dollars");
  s = s.replace(/₹([0-9,]+)\.([0-9]{2})/g, "$1 rupees and $2 paise");
  s = s.replace(/₹([0-9,]+)/g, "$1 rupees");

  // Technical units & specifications
  s = s.replace(/\b([0-9]+)\s*V\b/g, "$1 volts");
  s = s.replace(/\b([0-9]+)\s*A\b/g, "$1 amperes");
  s = s.replace(/\b([0-9]+)\s*pcs\b/gi, "$1 pieces");
  s = s.replace(/\bMOQ\b/g, "M O Q");
  s = s.replace(/\bBOM\b/g, "B O M");
  s = s.replace(/\bBLDC\b/g, "B L D C");
  s = s.replace(/\bFOC\b/g, "F O C");
  s = s.replace(/\bCAN\b/g, "CAN bus");
  s = s.replace(/\bIP67\b/g, "I P 67");
  s = s.replace(/\b2RS\b/g, "2 R S");

  return s;
}

/**
 * Browser-Native Web Speech Synthesis Adapter.
 */
export class BrowserSpeechAdapter implements VoiceBriefingAdapter {
  id = "browser-native";
  name = "Browser-Native Speech Synthesis";
  private synth: SpeechSynthesis | null = null;
  private currentUtterance: SpeechSynthesisUtterance | null = null;

  constructor() {
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      this.synth = window.speechSynthesis;
    }
  }

  isAvailable(): boolean {
    return Boolean(this.synth);
  }

  speak(text: string, options: VoiceOptions = {}): void {
    if (!this.synth) {
      if (options.onError) options.onError(new Error("Speech synthesis not supported in this browser."));
      return;
    }

    this.stop();

    const sanitized = sanitizeProcurementTextForSpeech(text);
    const utterance = new SpeechSynthesisUtterance(sanitized);
    utterance.rate = options.rate ?? 1.0;
    utterance.pitch = options.pitch ?? 1.0;
    utterance.volume = options.volume ?? 1.0;

    // Pick natural English voice if present
    const voices = this.synth.getVoices();
    const preferredVoice = voices.find(
      (v) => v.lang.startsWith("en") && (v.name.includes("Natural") || v.name.includes("Google") || v.name.includes("Samantha"))
    ) || voices.find((v) => v.lang.startsWith("en"));
    if (preferredVoice) {
      utterance.voice = preferredVoice;
    }

    if (options.onStart) utterance.onstart = options.onStart;
    if (options.onEnd) utterance.onend = options.onEnd;
    if (options.onError) utterance.onerror = options.onError;
    if (options.onPause) utterance.onpause = options.onPause;
    if (options.onResume) utterance.onresume = options.onResume;

    this.currentUtterance = utterance;
    this.synth.speak(utterance);
  }

  pause(): void {
    if (this.synth && this.synth.speaking) {
      this.synth.pause();
    }
  }

  resume(): void {
    if (this.synth && this.synth.paused) {
      this.synth.resume();
    }
  }

  stop(): void {
    if (this.synth) {
      this.synth.cancel();
      this.currentUtterance = null;
    }
  }

  isSpeaking(): boolean {
    return Boolean(this.synth && this.synth.speaking && !this.synth.paused);
  }

  isPaused(): boolean {
    return Boolean(this.synth && this.synth.paused);
  }

  getAttribution(): string {
    return "Synthesized locally via Browser Web Speech API.";
  }

  getLicenseStatus() {
    return {
      licenseName: "Standard W3C Web Speech API",
      isCommercialPermitted: true,
      attributionRequired: false,
      details: "Client-side browser engine via standard W3C Web Speech API.",
    };
  }
}

/**
 * Underdog Woof Adapter.
 * Documents official ConwayResearch/Underdog-Woof model card and license invariants.
 * Standby until official standalone client-side ONNX/WASM package is distributed.
 */
export class UnderdogWoofAdapter implements VoiceBriefingAdapter {
  id = "underdog-woof";
  name = "Underdog Woof (Conway Research)";

  isAvailable(): boolean {
    // Official distribution currently offers Python MLX/safetensors packages on Hugging Face.
    // Standalone client-side WASM/WebGPU distribution is pending release by Conway Research.
    return false;
  }

  speak(text: string, options: VoiceOptions = {}): void {
    if (options.onError) {
      options.onError(
        new Error(
          "Underdog Woof client model is on standby. Standalone browser WASM weights are not openly packaged. Falling back to Browser Speech."
        )
      );
    }
  }

  pause(): void {}
  resume(): void {}
  stop(): void {}
  isSpeaking(): boolean {
    return false;
  }
  isPaused(): boolean {
    return false;
  }

  getAttribution(): string {
    return "Voice by Underdog Woof (underdog.ai / Conway Research)";
  }

  getLicenseStatus() {
    return {
      licenseName: "Underdog Non-Commercial License 1.0",
      isCommercialPermitted: false,
      attributionRequired: true,
      details:
        "Licensed by Conway Research for non-commercial personal/research/hackathon projects. Requires 'Voice by Underdog Woof' attribution. Commercial deployment requires enterprise license (license@conway.tech). No model training or distillation allowed.",
    };
  }
}

/**
 * Returns the default active voice briefing adapter with automatic fallback.
 */
export function getActiveVoiceAdapter(): VoiceBriefingAdapter {
  return new BrowserSpeechAdapter();
}

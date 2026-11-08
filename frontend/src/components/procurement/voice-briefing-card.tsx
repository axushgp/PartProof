"use client";

import React, { useEffect, useState } from "react";
import { Volume2, Play, Pause, Square, ShieldCheck, ChevronDown, ChevronUp } from "lucide-react";
import { getActiveVoiceAdapter, UnderdogWoofAdapter, VoiceBriefingAdapter } from "@/lib/voice/speechAdapter";

interface VoiceBriefingCardProps {
  narrationText: string;
  recommendedSupplierName: string;
}

export function VoiceBriefingCard({ narrationText, recommendedSupplierName }: VoiceBriefingCardProps) {
  const [adapter] = useState<VoiceBriefingAdapter>(() => getActiveVoiceAdapter());
  const [isPlaying, setIsPlaying] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [playbackRate, setPlaybackRate] = useState<number>(1.0);
  const [showTranscript, setShowTranscript] = useState(false);
  const [showLicenseInfo, setShowLicenseInfo] = useState(false);

  useEffect(() => {
    return () => {
      adapter.stop();
    };
  }, [adapter]);

  const handlePlay = () => {
    if (!adapter) return;
    if (isPaused) {
      adapter.resume();
      setIsPaused(false);
      setIsPlaying(true);
      return;
    }

    adapter.speak(narrationText, {
      rate: playbackRate,
      onStart: () => {
        setIsPlaying(true);
        setIsPaused(false);
      },
      onEnd: () => {
        setIsPlaying(false);
        setIsPaused(false);
      },
      onError: (err) => {
        console.error("Speech playback error:", err);
        setIsPlaying(false);
        setIsPaused(false);
      },
      onPause: () => setIsPaused(true),
      onResume: () => setIsPaused(false),
    });
  };

  const handlePause = () => {
    if (adapter) {
      adapter.pause();
      setIsPaused(true);
      setIsPlaying(false);
    }
  };

  const handleStop = () => {
    if (adapter) {
      adapter.stop();
      setIsPlaying(false);
      setIsPaused(false);
    }
  };

  const handleRateChange = (rate: number) => {
    setPlaybackRate(rate);
    if (isPlaying) {
      handleStop();
      setTimeout(handlePlay, 100);
    }
  };

  const woofAdapter = new UnderdogWoofAdapter();
  const woofLicense = woofAdapter.getLicenseStatus();

  return (
    <div className="rounded-xl border border-teal-500/30 bg-slate-900/90 p-5 shadow-xl backdrop-blur-md">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-teal-500/20 text-teal-400">
              <Volume2 className="h-5 w-5" />
            </div>
            <h3 className="text-base font-semibold text-slate-100">Browser-native voice briefing</h3>
            <span className="rounded-full border border-teal-500/30 bg-teal-950/60 px-2.5 py-0.5 text-xs font-mono text-teal-300">
              Verified Executive Audio
            </span>
          </div>
          <p className="mt-1 text-xs text-slate-400">
            Client-side speech synthesis narrating verified forensic findings and award recommendation for{" "}
            <span className="font-medium text-teal-300">{recommendedSupplierName}</span>.
          </p>
        </div>

        {/* Audio Controls */}
        <div className="flex items-center gap-2">
          {!isPlaying ? (
            <button
              onClick={handlePlay}
              className="inline-flex items-center gap-2 rounded-lg bg-teal-500 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-teal-400 active:scale-95"
            >
              <Play className="h-4 w-4 fill-current" />
              Listen to Briefing
            </button>
          ) : (
            <button
              onClick={handlePause}
              className="inline-flex items-center gap-2 rounded-lg border border-teal-500/40 bg-teal-500/10 px-4 py-2 text-sm font-semibold text-teal-300 transition hover:bg-teal-500/20"
            >
              <Pause className="h-4 w-4" />
              Pause
            </button>
          )}

          {(isPlaying || isPaused) && (
            <button
              onClick={handleStop}
              title="Stop playback"
              className="rounded-lg border border-slate-700 bg-slate-800 p-2 text-slate-300 transition hover:bg-slate-700"
            >
              <Square className="h-4 w-4" />
            </button>
          )}

          {/* Speed selector */}
          <div className="flex rounded-lg border border-slate-700 bg-slate-800/80 p-0.5 text-xs font-mono">
            {[1.0, 1.25, 1.5].map((rate) => (
              <button
                key={rate}
                onClick={() => handleRateChange(rate)}
                className={`rounded px-2 py-1 transition ${
                  playbackRate === rate ? "bg-teal-500 text-slate-950 font-bold" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                {rate}x
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Voice Activity Waveform */}
      {isPlaying && (
        <div className="mt-4 flex items-center gap-1.5 rounded-lg border border-teal-500/20 bg-teal-950/30 px-3 py-2">
          <div className="flex items-center gap-1">
            <span className="h-3 w-1 animate-pulse rounded-full bg-teal-400" />
            <span className="h-5 w-1 animate-pulse rounded-full bg-teal-400 [animation-delay:150ms]" />
            <span className="h-2 w-1 animate-pulse rounded-full bg-teal-400 [animation-delay:300ms]" />
            <span className="h-4 w-1 animate-pulse rounded-full bg-teal-400 [animation-delay:450ms]" />
          </div>
          <span className="text-xs font-mono text-teal-300">
            Speaking executive narration via browser speech synthesis...
          </span>
        </div>
      )}

      {/* Attribution & Technology Pills */}
      <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-slate-800 pt-3 text-xs">
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1 rounded bg-slate-800/80 px-2 py-1 text-slate-300">
            <ShieldCheck className="h-3.5 w-3.5 text-teal-400" />
            Browser-Native Speech Synthesis
          </span>

          <span
            onClick={() => setShowLicenseInfo(!showLicenseInfo)}
            className="cursor-pointer rounded border border-slate-700 bg-slate-800/50 px-2 py-1 text-slate-400 transition hover:border-slate-600 hover:text-slate-300"
          >
            Underdog Woof: Standby
          </span>
        </div>

        <button
          onClick={() => setShowTranscript(!showTranscript)}
          className="inline-flex items-center gap-1 text-slate-400 hover:text-slate-200"
        >
          {showTranscript ? "Hide Transcript" : "View Transcript"}
          {showTranscript ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
        </button>
      </div>

      {/* Underdog Woof License Info Dropdown */}
      {showLicenseInfo && (
        <div className="mt-3 rounded-lg border border-slate-700 bg-slate-950/80 p-3 text-xs text-slate-300">
          <p className="font-semibold text-slate-200">Underdog Woof Integration & Feasibility Audit:</p>
          <ul className="mt-1 list-disc space-y-1 pl-4 text-slate-400">
            <li>
              <strong className="text-slate-300">License:</strong> {woofLicense.licenseName}
            </li>
            <li>
              <strong className="text-slate-300">Attribution Notice:</strong> {woofAdapter.getAttribution()}
            </li>
            <li>
              <strong className="text-slate-300">Commercial Status:</strong> {woofLicense.details}
            </li>
            <li>
              <strong className="text-slate-300">Current Distribution:</strong> Conway Research distributes the model as Python MLX/safetensors for local hardware. Standalone self-hosted client-side browser WASM bundles are not yet openly published. Browser-native speech is active for direct narration.
            </li>
          </ul>
        </div>
      )}

      {/* Full Transcript Viewer */}
      {showTranscript && (
        <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950 p-4 font-mono text-xs text-slate-300">
          <p className="whitespace-pre-wrap leading-relaxed">{narrationText}</p>
        </div>
      )}
    </div>
  );
}

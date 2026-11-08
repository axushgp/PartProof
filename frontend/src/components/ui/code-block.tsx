"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface CodeBlockProps {
  code: string;
  language?: string;
  className?: string;
  maxHeight?: string;
  title?: string;
}

export function CodeBlock({
  code,
  language = "python",
  className,
  maxHeight = "max-h-96",
  title,
}: CodeBlockProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback
    }
  };

  return (
    <div className={cn("rounded-md border border-white/10 bg-[#0B0E12] overflow-hidden", className)}>
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-white/[0.08] bg-[#111820]/70 text-xs">
        <span className="font-mono text-zinc-400 font-medium">
          {title || language.toUpperCase()}
        </span>
        <Button
          variant="ghost"
          size="sm"
          onClick={handleCopy}
          className="h-6 px-2 text-xs text-zinc-400 hover:text-white gap-1"
          title="Copy code"
        >
          {copied ? (
            <>
              <Check className="h-3 w-3 text-emerald-400" />
              <span className="text-emerald-400">Copied</span>
            </>
          ) : (
            <>
              <Copy className="h-3 w-3" />
              <span>Copy</span>
            </>
          )}
        </Button>
      </div>
      <div
        data-lenis-prevent
        className={cn(
          "overflow-auto p-4 text-xs font-mono text-zinc-200 leading-relaxed",
          maxHeight
        )}
      >
        <pre className="m-0 whitespace-pre">
          <code>{code}</code>
        </pre>
      </div>
    </div>
  );
}

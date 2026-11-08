"use client";

import { useState } from "react";
import { Check, Copy, FileText, Info } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ArtifactRead } from "@/types/backend";
import { formatBytes, formatDate } from "@/lib/formatters";

interface ArtifactsTableProps {
  artifacts: ArtifactRead[];
}

export function ArtifactsTable({ artifacts }: ArtifactsTableProps) {
  const [copiedHash, setCopiedHash] = useState<string | null>(null);

  const handleCopy = async (hash: string) => {
    try {
      await navigator.clipboard.writeText(hash);
      setCopiedHash(hash);
      setTimeout(() => setCopiedHash(null), 2000);
    } catch {
      // Fallback
    }
  };

  return (
    <Card className="bg-[#111820] border-white/8 shadow-sm">
      <CardHeader className="pb-3 border-b border-white/[0.06]">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-base font-semibold text-white flex items-center gap-2">
              <FileText className="h-4 w-4 text-[#55D6C2]" />
              Generated Sandbox Artifacts ({artifacts.length})
            </CardTitle>
            <CardDescription className="text-xs text-zinc-400">
              Verified files emitted from guest filesystem with cryptographic SHA-256 digests
            </CardDescription>
          </div>
          <Badge variant="outline" className="font-mono text-xs">
            Host Bound Verified
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="pt-4 space-y-4">
        {/* Backend limitation note */}
        <div className="rounded-md border border-white/8 bg-[#0B0E12] p-3 text-xs text-zinc-400 flex items-start gap-2.5">
          <Info className="h-4 w-4 text-zinc-400 shrink-0 mt-0.5" />
          <p className="leading-relaxed text-[11px]">
            <strong className="text-zinc-300">Artifact Download Note:</strong> Direct binary artifact retrieval endpoint is currently a pending backend capability. Metadata, content size, and cryptographic SHA-256 checksums are verified on host and indexed below for audit trails.
          </p>
        </div>

        {artifacts.length === 0 ? (
          <p className="text-xs text-zinc-400 py-6 text-center">
            No artifacts were emitted during this execution.
          </p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-white/8 bg-[#0B0E12]" data-lenis-prevent>
            <table className="w-full text-left text-xs text-zinc-300">
              <thead className="bg-[#080A0D] text-zinc-400 uppercase text-[10px] tracking-wider font-mono border-b border-white/[0.08]">
                <tr>
                  <th scope="col" className="py-2.5 px-3">Filename</th>
                  <th scope="col" className="py-2.5 px-3">MIME Type</th>
                  <th scope="col" className="py-2.5 px-3">Size</th>
                  <th scope="col" className="py-2.5 px-3">SHA-256 Digest</th>
                  <th scope="col" className="py-2.5 px-3 text-right">Created</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.06]">
                {artifacts.map((art) => {
                  const hash = art.sha256 || (art as unknown as { sha256_hash?: string }).sha256_hash || "";
                  const size = art.size_bytes ?? (art as unknown as { file_size_bytes?: number }).file_size_bytes ?? 0;

                  return (
                    <tr key={art.id} className="hover:bg-white/[0.02] transition-colors">
                      <td className="py-3 px-3 font-mono font-medium text-white">
                        <div className="flex items-center gap-2">
                          <FileText className="h-3.5 w-3.5 text-[#55D6C2] shrink-0" />
                          <span>{art.filename}</span>
                        </div>
                      </td>

                      <td className="py-3 px-3 font-mono text-zinc-400 text-[11px]">
                        {art.mime_type}
                      </td>

                      <td className="py-3 px-3 font-mono text-zinc-300 text-[11px]">
                        {formatBytes(size)}
                      </td>

                      <td className="py-3 px-3 font-mono text-[11px] text-zinc-400 max-w-xs">
                        <div className="flex items-center gap-1.5">
                          <span className="truncate select-all text-[#55D6C2]" title={hash}>
                            {hash ? `${hash.slice(0, 8)}...${hash.slice(-8)}` : "—"}
                          </span>
                          {hash && (
                            <Button
                              variant="ghost"
                              size="icon-sm"
                              onClick={() => handleCopy(hash)}
                              className="h-6 w-6 text-zinc-400 hover:text-white shrink-0"
                              title="Copy full SHA-256 digest"
                            >
                              {copiedHash === hash ? (
                                <Check className="h-3 w-3 text-emerald-400" />
                              ) : (
                                <Copy className="h-3 w-3" />
                              )}
                            </Button>
                          )}
                        </div>
                      </td>

                      <td className="py-3 px-3 text-right font-mono text-[11px] text-zinc-400 whitespace-nowrap">
                        {formatDate(art.created_at)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

import Link from "next/link";
import { ShieldAlert } from "lucide-react";
import { cn } from "@/lib/utils";

interface LogoProps {
  className?: string;
  collapsed?: boolean;
}

export function Logo({ className, collapsed = false }: LogoProps) {
  return (
    <Link
      href="/app"
      className={cn(
        "flex items-center gap-2.5 text-decoration-none group select-none",
        className
      )}
    >
      <div className="flex h-8 w-8 items-center justify-center rounded-md border border-[#55D6C2]/30 bg-[#55D6C2]/10 text-[#55D6C2] transition-colors group-hover:border-[#55D6C2]/60 group-hover:bg-[#55D6C2]/15">
        <ShieldAlert className="h-4 w-4" />
      </div>
      {!collapsed && (
        <div className="flex flex-col">
          <div className="flex items-center gap-1.5">
            <span className="font-sans font-bold tracking-tight text-white text-base">
              Part<span className="text-[#55D6C2]">Proof</span>
            </span>
            <span className="rounded bg-white/[0.08] px-1 py-0.2 text-[9px] font-mono uppercase tracking-wider text-zinc-400">
              Zero-Radius
            </span>
          </div>
          <span className="text-[10px] text-zinc-400 font-medium">
            Isolated Engineering Auditor
          </span>
        </div>
      )}
    </Link>
  );
}

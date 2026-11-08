"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  ListTodo,
  Plus,
  ShieldCheck,
  Server,
  Cpu,
  Scale,
} from "lucide-react";
import { Logo } from "@/components/layout/logo";
import { UserMenu } from "@/components/layout/user-menu";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { UserRead } from "@/types/backend";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";

interface SidebarProps {
  user: UserRead | null;
  className?: string;
  onNavigate?: () => void;
}

export function Sidebar({ user, className, onNavigate }: SidebarProps) {
  const pathname = usePathname();

  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: api.system.health,
    staleTime: 15000,
  });

  const { data: inference } = useQuery({
    queryKey: ["system-inference"],
    queryFn: api.system.inference,
    staleTime: 30000,
  });

  const navItems = [
    {
      title: "Overview",
      href: "/app",
      icon: LayoutDashboard,
      active: pathname === "/app",
    },
    {
      title: "Procurement Forensics",
      href: "/app/procurement",
      icon: Scale,
      active: pathname.startsWith("/app/procurement"),
    },
    {
      title: "Tasks & Audits",
      href: "/app/tasks",
      icon: ListTodo,
      active: pathname.startsWith("/app/tasks") && pathname !== "/app/tasks/new",
    },
  ];

  return (
    <aside
      className={cn(
        "flex h-full w-64 flex-col justify-between border-r border-white/8 bg-[#111820]/95 backdrop-blur-md p-4",
        className
      )}
    >
      <div className="flex flex-col space-y-5">
        {/* Logo */}
        <div className="px-2 pt-1">
          <Logo />
        </div>

        {/* Primary Action: New Task */}
        <div className="px-1">
          <Button
            asChild
            variant="default"
            className="w-full justify-center gap-2 h-9 text-xs font-semibold shadow-sm"
            onClick={onNavigate}
          >
            <Link href="/app/tasks/new">
              <Plus className="h-4 w-4" />
              <span>Create Task</span>
            </Link>
          </Button>
        </div>

        {/* Navigation */}
        <nav className="flex flex-col space-y-1">
          <span className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-wider text-zinc-400 font-mono">
            Navigation
          </span>
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={onNavigate}
                className={cn(
                  "flex items-center gap-2.5 rounded-md px-3 py-2 text-xs font-medium transition-colors select-none",
                  item.active
                    ? "bg-[#151E27] text-[#55D6C2] font-semibold border border-white/10"
                    : "text-zinc-200 hover:bg-white/[0.04] hover:text-white"
                )}
              >
                <Icon className={cn("h-4 w-4 shrink-0", item.active ? "text-[#55D6C2]" : "text-zinc-400")} />
                <span>{item.title}</span>
              </Link>
            );
          })}
        </nav>

        {/* Security & System Status Telemetry */}
        <div className="rounded-lg border border-white/6 bg-[#0B0E12]/80 p-3 text-xs space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-mono text-zinc-400 uppercase tracking-wider flex items-center gap-1.5">
              <ShieldCheck className="h-3 w-3 text-[#55D6C2]" />
              System Status
            </span>
            <span
              className={cn(
                "h-1.5 w-1.5 rounded-full",
                health?.status === "healthy" ? "bg-emerald-400" : "bg-amber-400"
              )}
            />
          </div>

          <div className="space-y-1.5 text-[11px] font-mono">
            <div className="flex items-center justify-between text-zinc-400">
              <span className="flex items-center gap-1 text-zinc-400">
                <Server className="h-2.5 w-2.5 text-zinc-400" />
                Backend
              </span>
              <span className="text-zinc-300 font-medium">
                {health?.database_connected ? "connected" : "degraded"}
              </span>
            </div>

            <div className="flex items-center justify-between text-zinc-400">
              <span className="flex items-center gap-1 text-zinc-400">
                <Cpu className="h-2.5 w-2.5 text-zinc-400" />
                Inference
              </span>
              <span
                className={cn(
                  "font-medium",
                  inference?.status === "reachable"
                    ? "text-emerald-400"
                    : "text-zinc-400"
                )}
              >
                {inference?.status || "checking..."}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Account controls at the bottom */}
      <div className="pt-3 border-t border-white/[0.08]">
        <UserMenu user={user} />
      </div>
    </aside>
  );
}

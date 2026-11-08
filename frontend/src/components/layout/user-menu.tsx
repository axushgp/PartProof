"use client";

import { useRouter } from "next/navigation";
import { LogOut, User as UserIcon } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api/client";
import { UserRead } from "@/types/backend";

interface UserMenuProps {
  user: UserRead | null;
}

export function UserMenu({ user }: UserMenuProps) {
  const router = useRouter();

  const handleLogout = async () => {
    try {
      await api.auth.logout();
    } catch {
      // Ignored: clear client anyway
    }
    router.push("/login");
    router.refresh();
  };

  const email = user?.email || "auditor@partproof.io";
  const role = user?.role || "auditor";

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          className="flex h-11 w-full items-center justify-start gap-2.5 px-2 text-left hover:bg-white/[0.06] rounded-md"
        >
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-zinc-800 border border-white/10 text-zinc-300">
            <UserIcon className="h-3.5 w-3.5" />
          </div>
          <div className="flex flex-col min-w-0 flex-1">
            <span className="truncate text-xs font-medium text-zinc-200">
              {email}
            </span>
            <span className="truncate text-[10px] text-zinc-400 uppercase tracking-wider font-mono">
              {role}
            </span>
          </div>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56 glass-dropdown">
        <DropdownMenuLabel className="font-normal">
          <div className="flex flex-col space-y-1">
            <p className="text-xs font-medium text-zinc-200 leading-none truncate">{email}</p>
            <p className="text-[10px] leading-none text-zinc-400 font-mono">Role: {role}</p>
          </div>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={handleLogout} destructive className="cursor-pointer gap-2">
          <LogOut className="h-3.5 w-3.5" />
          <span>Sign Out</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

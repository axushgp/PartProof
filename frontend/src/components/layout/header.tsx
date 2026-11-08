"use client";

import { ReactNode } from "react";
import { Menu } from "lucide-react";
import { Button } from "@/components/ui/button";
import { UserMenu } from "@/components/layout/user-menu";
import { UserRead } from "@/types/backend";

interface HeaderProps {
  user: UserRead | null;
  onOpenMobileNav: () => void;
  breadcrumbs?: ReactNode;
  actions?: ReactNode;
}

export function Header({
  user,
  onOpenMobileNav,
  breadcrumbs,
  actions,
}: HeaderProps) {
  return (
    <header className="sticky top-0 z-30 flex h-14 w-full items-center justify-between border-b border-white/8 bg-[#0B0E12]/80 backdrop-blur-md px-4 sm:px-6">
      <div className="flex items-center gap-3">
        <Button
          variant="ghost"
          size="icon-sm"
          className="lg:hidden text-zinc-300 hover:text-white"
          onClick={onOpenMobileNav}
          aria-label="Open navigation menu"
        >
          <Menu className="h-4 w-4" />
        </Button>
        <div className="flex items-center gap-2 text-sm text-zinc-300">
          {breadcrumbs}
        </div>
      </div>

      <div className="flex items-center gap-3">
        {actions}
        <div className="lg:hidden">
          <UserMenu user={user} />
        </div>
      </div>
    </header>
  );
}

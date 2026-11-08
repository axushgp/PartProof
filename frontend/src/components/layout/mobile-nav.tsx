"use client";

import { useEffect } from "react";
import { X } from "lucide-react";
import { Sidebar } from "@/components/layout/sidebar";
import { Button } from "@/components/ui/button";
import { UserRead } from "@/types/backend";

interface MobileNavProps {
  isOpen: boolean;
  onClose: () => void;
  user: UserRead | null;
}

export function MobileNav({ isOpen, onClose, user }: MobileNavProps) {
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 lg:hidden">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/80 backdrop-blur-sm transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer */}
      <div className="fixed inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col bg-[#111820] shadow-2xl border-r border-white/10 z-50">
        <div className="flex items-center justify-end p-2 border-b border-white/[0.06]">
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={onClose}
            aria-label="Close navigation menu"
            className="text-zinc-400 hover:text-white"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto">
          <Sidebar user={user} onNavigate={onClose} className="w-full border-r-0" />
        </div>
      </div>
    </div>
  );
}

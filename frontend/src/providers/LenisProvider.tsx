"use client";

import { ReactNode } from "react";

interface LenisProviderProps {
  children: ReactNode;
}

export function LenisProvider({ children }: LenisProviderProps) {
  // Natural browser scrolling without window wheel event capture or scroll-locking.
  return <>{children}</>;
}


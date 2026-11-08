import { ReactNode } from "react";
import { redirect } from "next/navigation";
import { validateServerSession } from "@/lib/auth/session";
import { AppShell } from "@/components/layout/app-shell";

export const metadata = {
  title: "PartProof | Isolated Engineering Auditor",
  description: "Autonomous task planning, policy validation and blast-radius-zero execution console",
};

export default async function DashboardLayout({
  children,
}: {
  children: ReactNode;
}) {
  const user = await validateServerSession();

  if (!user) {
    redirect("/login");
  }

  return <AppShell user={user}>{children}</AppShell>;
}

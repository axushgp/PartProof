import { redirect } from "next/navigation";
import { validateServerSession } from "@/lib/auth/session";

export default async function HomePage() {
  const user = await validateServerSession();

  if (user) {
    redirect("/app");
  } else {
    redirect("/login");
  }
}

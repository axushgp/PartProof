import { NextRequest, NextResponse } from "next/server";
import { clearSessionCookie } from "@/lib/auth/session";
import { validateMutationSecurity } from "@/lib/api/bffProxyHelper";

export async function POST(request: NextRequest): Promise<NextResponse> {
  const secCheck = validateMutationSecurity(request);
  if (!secCheck.valid) {
    return NextResponse.json({ detail: secCheck.error || "Security validation failed" }, { status: 403 });
  }

  await clearSessionCookie();
  return NextResponse.json({ success: true, message: "Logged out successfully" });
}

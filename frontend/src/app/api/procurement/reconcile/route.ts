import { NextRequest, NextResponse } from "next/server";
import { forwardToUpstream } from "@/lib/api/bffProxyHelper";

export async function POST(request: NextRequest): Promise<NextResponse> {
  const body = await request.json().catch(() => null);
  return forwardToUpstream(request, {
    method: "POST",
    upstreamPath: "/api/v1/procurement/reconcile",
    body,
    requiresAuth: true,
  });
}

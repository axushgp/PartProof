import { NextRequest, NextResponse } from "next/server";
import { forwardToUpstream } from "@/lib/api/bffProxyHelper";

export async function GET(request: NextRequest): Promise<NextResponse> {
  return forwardToUpstream(request, {
    method: "GET",
    upstreamPath: "/api/v1/tasks/sample-dataset",
    requiresAuth: true,
  });
}

import { NextRequest, NextResponse } from "next/server";
import { forwardToUpstream } from "@/lib/api/bffProxyHelper";
import { taskCreateSchema } from "@/lib/validation";

export async function GET(request: NextRequest): Promise<NextResponse> {
  return forwardToUpstream(request, {
    method: "GET",
    upstreamPath: "/api/v1/tasks",
    requiresAuth: true,
  });
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid JSON request body" }, { status: 400 });
  }

  const parseResult = taskCreateSchema.safeParse(body);
  if (!parseResult.success) {
    return NextResponse.json(
      { detail: parseResult.error.issues.map((e) => e.message).join(", ") },
      { status: 422 }
    );
  }

  return forwardToUpstream(request, {
    method: "POST",
    upstreamPath: "/api/v1/tasks",
    body: parseResult.data,
    requiresAuth: true,
  });
}

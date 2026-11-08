import { NextRequest, NextResponse } from "next/server";
import { forwardToUpstream, isValidTaskId } from "@/lib/api/bffProxyHelper";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ taskId: string }> }
): Promise<NextResponse> {
  const { taskId } = await params;

  if (!isValidTaskId(taskId)) {
    return NextResponse.json({ detail: "Invalid task ID format" }, { status: 400 });
  }

  return forwardToUpstream(request, {
    method: "GET",
    upstreamPath: `/api/v1/tasks/${taskId}/plan`,
    requiresAuth: true,
  });
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ taskId: string }> }
): Promise<NextResponse> {
  const { taskId } = await params;

  if (!isValidTaskId(taskId)) {
    return NextResponse.json({ detail: "Invalid task ID format" }, { status: 400 });
  }

  return forwardToUpstream(request, {
    method: "POST",
    upstreamPath: `/api/v1/tasks/${taskId}/plan`,
    requiresAuth: true,
  });
}

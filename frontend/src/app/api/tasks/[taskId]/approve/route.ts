import { NextRequest, NextResponse } from "next/server";
import { forwardToUpstream, isValidTaskId } from "@/lib/api/bffProxyHelper";
import { approvalSchema } from "@/lib/validation";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ taskId: string }> }
): Promise<NextResponse> {
  const { taskId } = await params;

  if (!isValidTaskId(taskId)) {
    return NextResponse.json({ detail: "Invalid task ID format" }, { status: 400 });
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid JSON request body" }, { status: 400 });
  }

  const parseResult = approvalSchema.safeParse(body);
  if (!parseResult.success) {
    return NextResponse.json(
      { detail: parseResult.error.issues.map((e) => e.message).join(", ") },
      { status: 422 }
    );
  }

  return forwardToUpstream(request, {
    method: "POST",
    upstreamPath: `/api/v1/tasks/${taskId}/approve`,
    body: parseResult.data,
    requiresAuth: true,
  });
}

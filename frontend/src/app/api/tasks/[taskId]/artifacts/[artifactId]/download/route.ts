import { NextRequest, NextResponse } from "next/server";
import { isValidTaskId } from "@/lib/api/bffProxyHelper";
import { isValidArtifactId } from "@/app/api/artifacts/[artifactId]/download/route";
import { getSessionToken, clearSessionCookie } from "@/lib/auth/session";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ taskId: string; artifactId: string }> }
): Promise<NextResponse> {
  const { taskId, artifactId } = await params;

  // 1. Validate parameter formats
  if (!isValidTaskId(taskId)) {
    return NextResponse.json({ detail: "Invalid task ID format" }, { status: 400 });
  }

  if (!isValidArtifactId(artifactId)) {
    return NextResponse.json({ detail: "Invalid artifact ID format" }, { status: 400 });
  }

  // 2. Retrieve session token server-side from HttpOnly cookie
  const token = await getSessionToken();
  if (!token) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }

  // 3. Resolve upstream task-scoped URL
  const backendBaseUrl = process.env.PARTPROOF_API_URL || "http://127.0.0.1:8000";
  const upstreamUrl = `${backendBaseUrl}/api/v1/tasks/${encodeURIComponent(taskId)}/artifacts/${encodeURIComponent(artifactId)}/download`;

  try {
    const upstreamRes = await fetch(upstreamUrl, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
      },
      cache: "no-store",
    });

    // 4. Handle expired session
    if (upstreamRes.status === 401) {
      await clearSessionCookie();
      return NextResponse.json({ detail: "Session expired or invalid" }, { status: 401 });
    }

    // 5. Handle upstream errors
    if (!upstreamRes.ok) {
      let errorDetail = `Artifact download failed with status ${upstreamRes.status}`;
      try {
        const errJson = await upstreamRes.json();
        if (errJson && typeof errJson.detail === "string") {
          errorDetail = errJson.detail;
        }
      } catch {
        // Upstream response wasn't JSON
      }
      return NextResponse.json({ detail: errorDetail }, { status: upstreamRes.status });
    }

    // 6. Forward safe headers
    const responseHeaders = new Headers();
    const safeHeaders = [
      "content-type",
      "content-disposition",
      "content-length",
      "cache-control",
      "x-content-type-options",
    ];

    for (const h of safeHeaders) {
      const val = upstreamRes.headers.get(h);
      if (val) {
        responseHeaders.set(h, val);
      }
    }

    if (!responseHeaders.has("cache-control")) {
      responseHeaders.set("cache-control", "private, no-store");
    }
    if (!responseHeaders.has("x-content-type-options")) {
      responseHeaders.set("x-content-type-options", "nosniff");
    }

    // 7. Stream binary response directly
    return new NextResponse(upstreamRes.body, {
      status: 200,
      headers: responseHeaders,
    });
  } catch (error) {
    console.error(
      "Task-scoped artifact download upstream connection failure:",
      error instanceof Error ? error.message : "Network error"
    );
    return NextResponse.json(
      {
        detail: "Unable to reach PartProof backend service. Ensure the backend is running and reachable.",
      },
      { status: 502 }
    );
  }
}

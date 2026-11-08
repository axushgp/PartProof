import { NextRequest, NextResponse } from "next/server";
import { getSessionToken, clearSessionCookie } from "@/lib/auth/session";

const ARTIFACT_ID_REGEX = /^[a-zA-Z0-9_-]{1,64}$/;

export function isValidArtifactId(artifactId: string): boolean {
  return ARTIFACT_ID_REGEX.test(artifactId);
}

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ artifactId: string }> }
): Promise<NextResponse> {
  const { artifactId } = await params;

  // 1. Validate artifact ID format
  if (!isValidArtifactId(artifactId)) {
    return NextResponse.json(
      { detail: "Invalid artifact ID format" },
      { status: 400 }
    );
  }

  // 2. Retrieve session token server-side from HttpOnly cookie
  const token = await getSessionToken();
  if (!token) {
    return NextResponse.json(
      { detail: "Not authenticated" },
      { status: 401 }
    );
  }

  // 3. Resolve FastAPI backend URL
  const backendBaseUrl = process.env.PARTPROOF_API_URL || "http://127.0.0.1:8000";
  const upstreamUrl = `${backendBaseUrl}/api/v1/artifacts/${encodeURIComponent(artifactId)}/download`;

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
      return NextResponse.json(
        { detail: "Session expired or invalid" },
        { status: 401 }
      );
    }

    // 5. Handle upstream errors without leaking internals
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
      return NextResponse.json(
        { detail: errorDetail },
        { status: upstreamRes.status }
      );
    }

    // 6. Forward only safe response headers
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

    // Ensure mandatory security headers
    if (!responseHeaders.has("cache-control")) {
      responseHeaders.set("cache-control", "private, no-store");
    }
    if (!responseHeaders.has("x-content-type-options")) {
      responseHeaders.set("x-content-type-options", "nosniff");
    }

    // 7. Stream binary response directly without buffering or converting to JSON
    return new NextResponse(upstreamRes.body, {
      status: 200,
      headers: responseHeaders,
    });
  } catch (error) {
    console.error(
      "Artifact download upstream connection failure:",
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

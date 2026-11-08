import { NextRequest, NextResponse } from "next/server";
import { getSessionToken, clearSessionCookie } from "@/lib/auth/session";

const TASK_ID_REGEX = /^[a-zA-Z0-9_-]{1,64}$/;

export function isValidTaskId(taskId: string): boolean {
  return TASK_ID_REGEX.test(taskId);
}

/**
 * Validates the Origin and Fetch Metadata headers on state-changing requests (CSRF mitigation).
 */
export function validateMutationSecurity(request: NextRequest): { valid: boolean; error?: string } {
  const method = request.method.toUpperCase();
  if (!["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    return { valid: true };
  }

  // 1. Fetch Metadata check (browser-enforced)
  const secFetchSite = request.headers.get("sec-fetch-site");
  if (secFetchSite && secFetchSite === "cross-site") {
    return { valid: false, error: "Cross-site requests forbidden." };
  }

  // 2. Origin validation
  const origin = request.headers.get("origin");
  const configuredOrigin = process.env.APP_ORIGIN || "http://localhost:3000";

  if (origin) {
    try {
      const requestOrigin = new URL(origin).origin;
      const expectedOrigin = new URL(configuredOrigin).origin;
      if (requestOrigin !== expectedOrigin) {
        return { valid: false, error: `Invalid request origin: ${origin}` };
      }
    } catch {
      return { valid: false, error: "Malformed Origin header." };
    }
  }

  return { valid: true };
}

export interface UpstreamRequestOptions {
  method: "GET" | "POST" | "PUT" | "DELETE" | "PATCH";
  upstreamPath: string; // Must begin with /api/v1/
  body?: unknown;
  requiresAuth?: boolean;
}

/**
 * Executes a strictly guarded request from the Next.js BFF to the upstream FastAPI backend.
 */
export async function forwardToUpstream(
  request: NextRequest,
  options: UpstreamRequestOptions
): Promise<NextResponse> {
  // 1. Enforce CSRF / Origin security on mutations
  const secCheck = validateMutationSecurity(request);
  if (!secCheck.valid) {
    return NextResponse.json({ detail: secCheck.error || "Security validation failed" }, { status: 403 });
  }

  // 2. Resolve backend URL
  const backendBaseUrl = process.env.PARTPROOF_API_URL || "http://127.0.0.1:8000";
  const upstreamUrl = `${backendBaseUrl}${options.upstreamPath}`;

  // 3. Construct headers strictly server-side
  const headers: Record<string, string> = {
    Accept: "application/json",
  };

  if (options.requiresAuth !== false) {
    const token = await getSessionToken();
    if (!token) {
      return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
    }
    headers["Authorization"] = `Bearer ${token}`;
  }

  let bodyString: string | undefined = undefined;
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    bodyString = JSON.stringify(options.body);
  }

  try {
    const upstreamRes = await fetch(upstreamUrl, {
      method: options.method,
      headers,
      body: bodyString,
      cache: "no-store",
    });

    // 4. Handle 401: clear session cookie
    if (upstreamRes.status === 401 && options.requiresAuth !== false) {
      await clearSessionCookie();
    }

    // 5. Parse response safely
    const contentType = upstreamRes.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      const data = await upstreamRes.json();
      return NextResponse.json(data, { status: upstreamRes.status });
    }

    const text = await upstreamRes.text();
    return new NextResponse(text, {
      status: upstreamRes.status,
      headers: { "Content-Type": contentType || "text/plain" },
    });
  } catch (error) {
    console.error("Upstream connection failure:", error instanceof Error ? error.message : "Network error");
    const isTimeout =
      error instanceof Error &&
      (error.name === "TimeoutError" ||
        error.name === "AbortError" ||
        ("code" in error &&
          (error as { code: string }).code === "UND_ERR_CONNECT_TIMEOUT"));

    if (isTimeout) {
      return NextResponse.json(
        {
          detail: "PartProof backend gateway timeout. The request exceeded the maximum wait time.",
        },
        { status: 504 }
      );
    }

    return NextResponse.json(
      {
        detail: "Unable to reach PartProof backend service. Ensure the backend is running and reachable.",
      },
      { status: 502 }
    );
  }
}

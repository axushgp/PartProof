import { NextRequest, NextResponse } from "next/server";
import { setSessionCookie } from "@/lib/auth/session";
import { validateMutationSecurity } from "@/lib/api/bffProxyHelper";
import { registerSchema } from "@/lib/validation";
import { Token } from "@/types/backend";

export async function POST(request: NextRequest): Promise<NextResponse> {
  const secCheck = validateMutationSecurity(request);
  if (!secCheck.valid) {
    return NextResponse.json({ detail: secCheck.error || "Security validation failed" }, { status: 403 });
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid JSON request body" }, { status: 400 });
  }

  const rawBody = (body && typeof body === "object" ? body : {}) as Record<string, unknown>;
  const normalizedBody = {
    email: rawBody.email,
    password: rawBody.password,
    confirmPassword: rawBody.confirmPassword ?? rawBody.confirm_password,
  };

  const parseResult = registerSchema.safeParse(normalizedBody);
  if (!parseResult.success) {
    return NextResponse.json(
      { detail: parseResult.error.issues.map((e) => e.message).join(", ") },
      { status: 422 }
    );
  }

  const backendUrl = process.env.PARTPROOF_API_URL || "http://127.0.0.1:8000";

  try {
    const upstreamRes = await fetch(`${backendUrl}/api/v1/auth/register`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({
        email: parseResult.data.email,
        password: parseResult.data.password,
        confirm_password: parseResult.data.confirmPassword,
      }),
      cache: "no-store",
    });

    if (!upstreamRes.ok) {
      const errData = await upstreamRes.json().catch(() => ({ detail: "Registration failed" }));
      return NextResponse.json(errData, { status: upstreamRes.status });
    }

    const tokenData: Token = await upstreamRes.json();

    // Store JWT securely in server-side HttpOnly cookie
    await setSessionCookie(tokenData.access_token);

    // Return safe user info to client (NEVER return access_token)
    return NextResponse.json(
      {
        user_id: tokenData.user_id,
        email: tokenData.email,
        role: tokenData.role,
      },
      { status: 201 }
    );
  } catch (error) {
    console.error("Register upstream error:", error instanceof Error ? error.message : "Network error");
    return NextResponse.json(
      { detail: "Unable to reach PartProof backend service. Ensure backend is running." },
      { status: 502 }
    );
  }
}

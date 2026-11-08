import { NextRequest, NextResponse } from "next/server";
import { getSessionToken } from "@/lib/auth/session";
import { validateMutationSecurity } from "@/lib/api/bffProxyHelper";

export async function POST(request: NextRequest): Promise<NextResponse> {
  const secCheck = validateMutationSecurity(request);
  if (!secCheck.valid) {
    return NextResponse.json({ detail: secCheck.error || "Security validation failed" }, { status: 403 });
  }

  const backendBaseUrl = process.env.PARTPROOF_API_URL || "http://127.0.0.1:8000";
  const upstreamUrl = `${backendBaseUrl}/api/v1/procurement/extract`;

  const headers: Record<string, string> = {
    Accept: "application/json",
  };

  const token = await getSessionToken();
  if (!token) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }
  headers["Authorization"] = `Bearer ${token}`;

  try {
    const formData = await request.formData();
    const upstreamRes = await fetch(upstreamUrl, {
      method: "POST",
      headers,
      body: formData,
      cache: "no-store",
    });

    const data = await upstreamRes.json();
    return NextResponse.json(data, { status: upstreamRes.status });
  } catch (error) {
    console.error("Procurement extraction upstream failure:", error);
    return NextResponse.json(
      { detail: "Unable to reach PartProof backend service for document extraction." },
      { status: 502 }
    );
  }
}

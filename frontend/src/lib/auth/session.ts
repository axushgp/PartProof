import { cookies } from "next/headers";
import { UserRead } from "@/types/backend";

/**
 * Returns the appropriate session cookie name based on environment and protocol.
 * In production with HTTPS, uses the __Host- prefix for strict origin/path binding.
 */
export function getSessionCookieName(): string {
  const appOrigin = process.env.APP_ORIGIN || "";
  const isSecure = process.env.NODE_ENV === "production" && appOrigin.startsWith("https://");
  return isSecure ? "__Host-partproof_session" : "partproof_session";
}

/**
 * Decodes the exp claim from a JWT to align cookie lifetime with token lifetime.
 * Note: this is only used for cookie lifetime, never as client-side proof of authentication.
 */
export function getJwtExpiry(token: string): Date | undefined {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return undefined;
    const decoded = Buffer.from(parts[1], "base64url").toString("utf-8");
    const payload = JSON.parse(decoded);
    if (payload && typeof payload.exp === "number") {
      return new Date(payload.exp * 1000);
    }
  } catch {
    return undefined;
  }
  return undefined;
}

/**
 * Sets the server-side HttpOnly session cookie containing the FastAPI backend JWT.
 */
export async function setSessionCookie(token: string): Promise<void> {
  const cookieStore = await cookies();
  const cookieName = getSessionCookieName();
  const expiry = getJwtExpiry(token);
  const appOrigin = process.env.APP_ORIGIN || "";
  const isProduction = process.env.NODE_ENV === "production";
  const isSecure = isProduction && appOrigin.startsWith("https://");

  cookieStore.set({
    name: cookieName,
    value: token,
    httpOnly: true,
    secure: isSecure,
    sameSite: "lax",
    path: "/",
    expires: expiry || new Date(Date.now() + 24 * 60 * 60 * 1000),
  });
}

/**
 * Retrieves the session token from the HttpOnly cookie.
 */
export async function getSessionToken(): Promise<string | null> {
  const cookieStore = await cookies();
  const cookieName = getSessionCookieName();
  const cookie = cookieStore.get(cookieName);
  return cookie?.value || null;
}

/**
 * Clears the session cookie on logout or invalid session.
 */
export async function clearSessionCookie(): Promise<void> {
  const cookieStore = await cookies();
  const cookieName = getSessionCookieName();
  const appOrigin = process.env.APP_ORIGIN || "";
  const isProduction = process.env.NODE_ENV === "production";
  const isSecure = isProduction && appOrigin.startsWith("https://");

  cookieStore.set({
    name: cookieName,
    value: "",
    httpOnly: true,
    secure: isSecure,
    sameSite: "lax",
    path: "/",
    maxAge: 0,
    expires: new Date(0),
  });
}

/**
 * Validates the current server session against FastAPI `GET /api/v1/auth/me`.
 * Used by Server Components to guard protected routes.
 */
export async function validateServerSession(): Promise<UserRead | null> {
  const token = await getSessionToken();
  if (!token) return null;

  const backendUrl = process.env.PARTPROOF_API_URL || "http://127.0.0.1:8000";
  try {
    const res = await fetch(`${backendUrl}/api/v1/auth/me`, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/json",
      },
      cache: "no-store",
    });

    if (!res.ok) {
      if (res.status === 401) {
        await clearSessionCookie();
      }
      return null;
    }

    const user: UserRead = await res.json();
    return user;
  } catch (error) {
    // Log safe error without tokens
    console.error("Failed to validate server session with upstream API:", error instanceof Error ? error.message : "Network error");
    return null;
  }
}

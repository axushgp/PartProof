"use client";

import { useState, Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Eye, EyeOff, Lock, Mail, ShieldAlert, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { loginSchema, LoginFormData } from "@/lib/validation";
import { api, ApiError } from "@/lib/api/client";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const isExpired = searchParams.get("expired") === "true";

  const [showPassword, setShowPassword] = useState(false);
  const [authError, setAuthError] = useState<string | null>(
    isExpired ? "Your session has expired. Please sign in again." : null
  );

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      email: "",
      password: "",
    },
  });

  const onSubmit = async (data: LoginFormData) => {
    setAuthError(null);
    try {
      await api.auth.login(data);
      router.push("/app");
      router.refresh();
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          setAuthError("Invalid email or password.");
        } else {
          setAuthError(err.message || "Authentication failed. Please try again.");
        }
      } else {
        setAuthError("Network error. Unable to reach authentication service.");
      }
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#0B0E12] px-4 py-12 relative overflow-hidden">
      {/* Background grid accent (restrained) */}
      <div
        className="absolute inset-0 opacity-[0.03] pointer-events-none"
        style={{
          backgroundImage:
            "linear-gradient(to right, #ffffff 1px, transparent 1px), linear-gradient(to bottom, #ffffff 1px, transparent 1px)",
          backgroundSize: "32px 32px",
        }}
        aria-hidden="true"
      />

      <div className="w-full max-w-md relative z-10">
        <Card className="glass-panel border-white/10 shadow-2xl rounded-xl">
          <CardHeader className="text-center pb-6 pt-8 border-b border-white/[0.06]">
            <div className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-lg border border-[#55D6C2]/40 bg-[#55D6C2]/10 text-[#55D6C2]">
              <ShieldAlert className="h-6 w-6" />
            </div>
            <CardTitle className="text-xl font-bold tracking-tight text-white">
              Part<span className="text-[#55D6C2]">Proof</span> Console
            </CardTitle>
            <CardDescription className="text-xs text-zinc-400 mt-1.5 leading-relaxed">
              Blast-Radius-Zero Task Planning, Policy Validation &amp; Isolated Execution
            </CardDescription>
          </CardHeader>

          <CardContent className="pt-6">
            {authError && (
              <div
                role="alert"
                className="mb-5 flex items-start gap-2.5 rounded-md border border-rose-800/60 bg-rose-950/40 p-3 text-xs text-rose-200"
              >
                <AlertCircle className="h-4 w-4 shrink-0 text-rose-400 mt-0.5" />
                <div className="flex-1 leading-relaxed">{authError}</div>
              </div>
            )}

            <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
              <div className="space-y-1.5">
                <label
                  htmlFor="email-input"
                  className="block text-xs font-medium text-zinc-300"
                >
                  Email Address
                </label>
                <div className="relative">
                  <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-zinc-400">
                    <Mail className="h-4 w-4" />
                  </div>
                  <Input
                    id="email-input"
                    type="email"
                    autoComplete="email"
                    placeholder="auditor@partproof.io"
                    className="pl-9"
                    error={Boolean(errors.email)}
                    {...register("email")}
                  />
                </div>
                {errors.email && (
                  <p className="text-[11px] text-rose-400 font-medium">
                    {errors.email.message}
                  </p>
                )}
              </div>

              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label
                    htmlFor="password-input"
                    className="block text-xs font-medium text-zinc-300"
                  >
                    Password
                  </label>
                </div>
                <div className="relative">
                  <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-zinc-400">
                    <Lock className="h-4 w-4" />
                  </div>
                  <Input
                    id="password-input"
                    type={showPassword ? "text" : "password"}
                    autoComplete="current-password"
                    placeholder="••••••••••••"
                    className="pl-9 pr-10"
                    error={Boolean(errors.password)}
                    {...register("password")}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute inset-y-0 right-0 flex items-center pr-3 text-zinc-400 hover:text-white transition-colors"
                    aria-label={showPassword ? "Hide password" : "Show password"}
                  >
                    {showPassword ? (
                      <EyeOff className="h-4 w-4" />
                    ) : (
                      <Eye className="h-4 w-4" />
                    )}
                  </button>
                </div>
                {errors.password && (
                  <p className="text-[11px] text-rose-400 font-medium">
                    {errors.password.message}
                  </p>
                )}
              </div>

              <Button
                type="submit"
                variant="default"
                className="w-full mt-2 h-10 text-sm font-semibold"
                isLoading={isSubmitting}
              >
                Sign In to Console
              </Button>
            </form>

            <div className="mt-5 text-center text-xs text-zinc-400">
              Don&apos;t have an account?{" "}
              <Link
                href="/signup"
                className="font-medium text-[#55D6C2] hover:underline transition-colors"
              >
                Create Auditor Account
              </Link>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-[#0B0E12]" />}>
      <LoginForm />
    </Suspense>
  );
}

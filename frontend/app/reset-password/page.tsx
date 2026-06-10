"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";

const API =
  process.env.NEXT_PUBLIC_API_URL || "https://lossq-production.up.railway.app";

function ResetPasswordContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const token = useMemo(() => searchParams.get("token") || "", [searchParams]);

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  async function submitReset() {
    setMessage("");
    setError("");

    if (!token) {
      setError("Reset token is missing. Please request a new password reset link.");
      return;
    }

    if (!password || password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    try {
      setLoading(true);

      const res = await fetch(`${API}/auth/reset-password`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          token,
          new_password: password,
        }),
      });

      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        throw new Error(data?.detail || data?.message || "Password reset failed.");
      }

      setSuccess(true);
      setMessage(data?.message || "Password reset successful. You can now log in.");
      setPassword("");
      setConfirmPassword("");

      window.setTimeout(() => {
        router.push("/login?reset=success");
      }, 1500);
    } catch (err: any) {
      setError(err?.message || "Password reset failed. Please request a new reset link.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#050816] text-white flex items-center justify-center px-6">
      <section className="w-full max-w-md rounded-3xl border border-white/10 bg-white/[0.04] p-8 shadow-2xl">
        <div className="mb-6">
          <p className="text-sm font-semibold text-cyan-300">LossQ Security</p>
          <h1 className="text-3xl font-bold mt-2">Reset Password</h1>
          <p className="text-sm text-slate-400 mt-2">
            Enter a new password for your LossQ account.
          </p>
        </div>

        {!token && (
          <div className="mb-4 rounded-2xl border border-red-400/30 bg-red-500/10 p-4 text-sm text-red-200">
            This reset link is missing a token. Please request a new reset email.
          </div>
        )}

        {message && (
          <div className="mb-4 rounded-2xl border border-emerald-400/30 bg-emerald-500/10 p-4 text-sm text-emerald-200">
            {message}
          </div>
        )}

        {error && (
          <div className="mb-4 rounded-2xl border border-red-400/30 bg-red-500/10 p-4 text-sm text-red-200">
            {error}
          </div>
        )}

        <div className="space-y-4">
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="New password"
            className="w-full rounded-2xl border border-white/10 bg-black/30 px-4 py-3 text-white outline-none focus:border-cyan-400"
            disabled={loading || success}
          />

          <input
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            placeholder="Confirm new password"
            className="w-full rounded-2xl border border-white/10 bg-black/30 px-4 py-3 text-white outline-none focus:border-cyan-400"
            disabled={loading || success}
          />

          <button
            onClick={submitReset}
            disabled={loading || success || !token}
            className="w-full rounded-2xl bg-cyan-400 px-4 py-3 font-bold text-slate-950 hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {loading ? "Resetting..." : success ? "Password Reset" : "Reset Password"}
          </button>

          <button
            onClick={() => router.push("/login?fresh=1")}
            className="w-full rounded-2xl border border-white/10 px-4 py-3 text-sm text-slate-300 hover:bg-white/10"
          >
            Back to Login
          </button>
        </div>

        <p className="mt-6 text-xs text-slate-500">
          Reset links expire after 30 minutes. If this link is expired, request a new one.
        </p>
      </section>
    </main>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense
      fallback={
        <main className="min-h-screen bg-[#050816] text-white flex items-center justify-center">
          <p className="text-slate-400">Loading reset page...</p>
        </main>
      }
    >
      <ResetPasswordContent />
    </Suspense>
  );
}

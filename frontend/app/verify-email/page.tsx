"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

const API = (
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "https://lossq-production.up.railway.app"
).replace(/\/$/, "");

function VerifyEmailContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [message, setMessage] = useState("Verifying your email address...");

  useEffect(() => {
    const token = searchParams.get("token");

    async function verifyEmail() {
      if (!token) {
        setStatus("error");
        setMessage("Verification token is missing. Please use the link from your email.");
        return;
      }

      try {
        const response = await fetch(`${API}/auth/verify-email?token=${encodeURIComponent(token)}`, {
          method: "GET",
          cache: "no-store",
        });

        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
          setStatus("error");
          setMessage(data?.detail || "This verification link is invalid or expired.");
          return;
        }

        setStatus("success");
        setMessage("Your email has been verified successfully. You can now log in.");

        window.setTimeout(() => {
          router.push("/login?verified=1");
        }, 2500);
      } catch (err) {
        setStatus("error");
        setMessage("Unable to verify your email right now. Please try again.");
      }
    }

    verifyEmail();
  }, [router, searchParams]);

  return (
    <main className="min-h-screen bg-[#050816] text-white flex items-center justify-center px-6">
      <section className="w-full max-w-lg rounded-3xl border border-white/10 bg-white/[0.04] p-8 shadow-2xl">
        <div className="mb-6">
          <p className="text-sm font-semibold uppercase tracking-[0.3em] text-cyan-300">
            LossQ Verification
          </p>
          <h1 className="mt-3 text-3xl font-bold">
            {status === "success"
              ? "Email Verified"
              : status === "error"
              ? "Verification Failed"
              : "Verifying Email"}
          </h1>
        </div>

        <div
          className={`rounded-2xl border p-5 text-sm leading-6 ${
            status === "success"
              ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-100"
              : status === "error"
              ? "border-red-400/30 bg-red-400/10 text-red-100"
              : "border-cyan-400/30 bg-cyan-400/10 text-cyan-100"
          }`}
        >
          {message}
        </div>

        <div className="mt-6 flex flex-wrap gap-3">
          {status === "error" && (
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="rounded-xl bg-cyan-500 px-5 py-3 text-sm font-bold text-slate-950 hover:bg-cyan-400"
            >
              Retry Verification
            </button>
          )}

          <button
            type="button"
            onClick={() => router.push("/login")}
            className="rounded-xl border border-white/10 px-5 py-3 text-sm font-bold text-white hover:bg-white/10"
          >
            Go to Login
          </button>
        </div>

        <p className="mt-6 text-xs text-slate-500">
          If your verification link expired, register again or request a new invite from your account administrator.
        </p>
      </section>
    </main>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense
      fallback={
        <main className="min-h-screen bg-[#050816] text-white flex items-center justify-center px-6">
          <section className="w-full max-w-lg rounded-3xl border border-white/10 bg-white/[0.04] p-8">
            <p className="text-cyan-200">Loading verification page...</p>
          </section>
        </main>
      }
    >
      <VerifyEmailContent />
    </Suspense>
  );
}

// LOSSQ_VERIFY_EMAIL_FRONTEND_PAGE_V1

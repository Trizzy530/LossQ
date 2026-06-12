"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

const API =
  process.env.NEXT_PUBLIC_API_URL || "https://lossq-production.up.railway.app";


// LOSSQ_REGISTER_PAGE_WELCOME_NAME_V1
function setLossQRegisterPageWelcomeName(user: any, fallbackEmail: string) {
  if (typeof window === "undefined") return;

  const fullName = `${user?.first_name || ""} ${user?.last_name || ""}`.trim();
  const cleanName =
    fullName ||
    user?.name ||
    user?.email ||
    fallbackEmail ||
    "there";

  sessionStorage.setItem("lossq_welcome", "1");
  sessionStorage.setItem("lossq_welcome_name", cleanName);
  localStorage.setItem("lossq_new_user_welcome", "1");
  localStorage.setItem("lossq_new_user_welcome_name", cleanName);
  localStorage.removeItem("lossq_new_user_welcome_seen");
}


export default function RegisterPage() {
  const router = useRouter();

  const [organizationName, setOrganizationName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  function errorToText(data: any) {
    if (!data) return "Registration failed.";
    if (typeof data === "string") return data;
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) {
      return data.detail.map((item: any) => item?.msg || JSON.stringify(item)).join(", ");
    }
    if (typeof data.message === "string") return data.message;
    return JSON.stringify(data);
  }

  async function handleRegister(e: React.FormEvent) {
    e.preventDefault();
    setError("");

    if (!acceptedTerms) {
      setError("You must accept the Terms, Privacy Policy, AI Disclaimer, and Insurance Disclaimer before creating an account.");
      return;
    }

    setLoading(true);

    try {
      const res = await fetch(`${API}/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        cache: "no-store",
        body: JSON.stringify({
          email: email.trim(),
          password,
          organization_name: organizationName.trim(),
        }),
      });

      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        setError(errorToText(data));
        return;
      }

      router.replace("/login?fresh=1");
    } catch (err: any) {
      setError(err?.message || "Registration failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-slate-950 text-white flex items-center justify-center px-6">
      <form onSubmit={handleRegister} className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-2xl p-8">
        <h1 className="text-3xl font-bold mb-2">Create LossQ Account</h1>
        <p className="text-slate-400 mb-6">Register to access your dashboard.</p>

        {error && (
          <div className="bg-red-500/10 border border-red-500/30 text-red-300 p-3 rounded-lg mb-4 whitespace-pre-wrap">
            {error}
          </div>
        )}

        <input
          value={organizationName}
          onChange={(e) => setOrganizationName(e.target.value)}
          placeholder="Organization Name"
          className="w-full bg-slate-800 border border-slate-700 rounded-lg px-4 py-3 mb-4"
          required
        />

        <input
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="Email"
          type="email"
          className="w-full bg-slate-800 border border-slate-700 rounded-lg px-4 py-3 mb-4"
          required
        />

        <input
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Password"
          type="password"
          className="w-full bg-slate-800 border border-slate-700 rounded-lg px-4 py-3 mb-6"
          required
        />

        <label className="mb-5 flex items-start gap-3 rounded-xl border border-cyan-400/30 bg-cyan-400/10 p-4 text-sm text-slate-200">
          <input
            type="checkbox"
            checked={acceptedTerms}
            onChange={(e) => setAcceptedTerms(e.target.checked)}
            className="mt-1 h-4 w-4 accent-cyan-400"
          />
          <span>
            I agree to the{" "}
            <a href="/terms" className="text-cyan-300 hover:underline">Terms</a>,{" "}
            <a href="/privacy" className="text-cyan-300 hover:underline">Privacy Policy</a>,{" "}
            <a href="/ai-disclaimer" className="text-cyan-300 hover:underline">AI Disclaimer</a>, and{" "}
            <a href="/insurance-disclaimer" className="text-cyan-300 hover:underline">Insurance Disclaimer</a>.
          </span>
        </label>

        <button type="submit" disabled={loading || !acceptedTerms} className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-60 disabled:cursor-not-allowed rounded-lg px-5 py-3 font-semibold">
          {loading ? "Creating account..." : "Register"}
        </button>

        <p className="text-center text-slate-400 mt-6">
          Already have an account?{" "}
          <Link href="/login" className="text-blue-400 underline">
            Login
          </Link>
        </p>
      </form>
    </main>
  );
}

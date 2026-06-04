"use client";

import { useSearchParams, useRouter } from "next/navigation";
import { useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "https://lossq-production.up.railway.app";

async function safeJson(res: Response) {
  try {
    return await res.json();
  } catch {
    return null;
  }
}

export default function AcceptInvitePage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") || "";

  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function acceptInvite() {
    setError("");
    setMessage("");

    if (!token) {
      setError("Invite token is missing. Ask your admin for a fresh invite link.");
      return;
    }

    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setLoading(true);

    try {
      const res = await fetch(`${API}/auth/accept-invite`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, password, first_name: firstName, last_name: lastName }),
      });

      const data = await safeJson(res);

      if (!res.ok) {
        setError(data?.detail || "Invite could not be accepted.");
        return;
      }

      localStorage.setItem("lossq_token", data.access_token);
      localStorage.setItem("lossq_login_time", Date.now().toString());
      localStorage.setItem("lossq_user", JSON.stringify(data.user || {}));

      setMessage("Invite accepted. Redirecting to your dashboard...");
      setTimeout(() => router.replace("/dashboard"), 900);
    } catch (err: any) {
      setError(err?.message || "Invite acceptance failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#020617] text-white flex items-center justify-center px-5 py-10">
      <div className="fixed inset-0 bg-[radial-gradient(circle_at_top_left,#1d4ed866,transparent_30%),radial-gradient(circle_at_bottom_right,#7c3aed44,transparent_32%)]" />
      <div className="fixed inset-0 bg-[linear-gradient(to_right,rgba(255,255,255,0.04)_1px,transparent_1px),linear-gradient(to_bottom,rgba(255,255,255,0.04)_1px,transparent_1px)] bg-[size:72px_72px] opacity-20" />

      <section className="relative w-full max-w-xl rounded-3xl border border-white/10 bg-slate-950/80 p-8 shadow-2xl backdrop-blur-xl">
        <div className="mb-8">
          <div className="text-4xl font-black tracking-tight">Loss<span className="text-blue-400">Q</span></div>
          <h1 className="mt-6 text-3xl font-black">Accept Your Invite</h1>
          <p className="mt-2 text-slate-400">
            Create your password to join your organization’s LossQ workspace.
          </p>
        </div>

        {message && <div className="mb-5 rounded-2xl border border-emerald-400/30 bg-emerald-500/10 p-4 text-emerald-100">{message}</div>}
        {error && <div className="mb-5 rounded-2xl border border-red-400/30 bg-red-500/10 p-4 text-red-100">{error}</div>}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <input
            value={firstName}
            onChange={(e) => setFirstName(e.target.value)}
            className="rounded-2xl border border-white/10 bg-slate-900/80 px-4 py-3 text-white outline-none focus:border-blue-400"
            placeholder="First name"
          />
          <input
            value={lastName}
            onChange={(e) => setLastName(e.target.value)}
            className="rounded-2xl border border-white/10 bg-slate-900/80 px-4 py-3 text-white outline-none focus:border-blue-400"
            placeholder="Last name"
          />
        </div>

        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="mt-4 w-full rounded-2xl border border-white/10 bg-slate-900/80 px-4 py-3 text-white outline-none focus:border-blue-400"
          placeholder="Create password"
        />

        <input
          type="password"
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          className="mt-4 w-full rounded-2xl border border-white/10 bg-slate-900/80 px-4 py-3 text-white outline-none focus:border-blue-400"
          placeholder="Confirm password"
        />

        <button
          onClick={acceptInvite}
          disabled={loading}
          className="mt-6 w-full rounded-2xl bg-blue-600 px-5 py-4 font-bold text-white hover:bg-blue-500 disabled:opacity-50"
        >
          {loading ? "Accepting Invite..." : "Accept Invite"}
        </button>

        <button
          onClick={() => router.replace("/login?fresh=1")}
          className="mt-4 w-full rounded-2xl border border-white/10 px-5 py-3 font-semibold text-slate-300 hover:bg-white/10"
        >
          Back to Login
        </button>
      </section>
    </main>
  );
}

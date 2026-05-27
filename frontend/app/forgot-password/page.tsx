"use client";

import { useState } from "react";

const API =
  process.env.NEXT_PUBLIC_API_URL || "https://lossq-production.up.railway.app";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [resetLink, setResetLink] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit() {
    setLoading(true);
    setMessage("");
    setResetLink("");

    try {
      const res = await fetch(`${API}/auth/forgot-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim().toLowerCase() }),
      });

      const data = await res.json().catch(() => ({}));

     setMessage(data.message || "If an account exists, a reset email has been sent.");

      {resetLink && (
  <a href={resetLink}>
    Dev reset link: {resetLink}
  </a>
)}
    } catch {
      setMessage("Could not request password reset.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-slate-950 text-white flex items-center justify-center px-6">
      <div className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-2xl p-8">
        <h1 className="text-3xl font-bold mb-3">Forgot Password</h1>
        <p className="text-slate-400 mb-6">
          Enter your email to generate a reset link.
        </p>

        <input
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="Email"
          type="email"
          className="w-full bg-slate-800 border border-slate-700 rounded-lg px-4 py-3 mb-4"
        />

        <button
          onClick={submit}
          disabled={loading}
          className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-60 rounded-lg py-3 font-bold"
        >
          {loading ? "Sending..." : "Send Reset Link"}
        </button>

        {message && <p className="text-slate-300 mt-5">{message}</p>}

        {resetLink && (
          <a href={resetLink} className="block text-blue-400 mt-4 break-all">
            Dev reset link: {resetLink}
          </a>
        )}

        <a href="/login" className="block text-center text-blue-400 mt-6">
          Back to login
        </a>
      </div>
    </main>
  );
}
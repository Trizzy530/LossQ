"use client";

import { useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

async function safeJson(res: Response) {
  try {
    return await res.json();
  } catch {
    return null;
  }
}

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [businessName, setBusinessName] = useState("LossQ Demo Agency");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit() {
    setLoading(true);
    setMessage("");

    try {
      const cleanEmail = email.trim().toLowerCase();

      if (!cleanEmail || !password) {
        setMessage("Email and password are required.");
        return;
      }

      const endpoint = mode === "login" ? "/auth/login" : "/auth/register";

      const payload =
        mode === "register"
          ? {
              email: cleanEmail,
              password: password,
              business_name: businessName || "LossQ Demo Agency",
              organization_name: businessName || "LossQ Demo Agency",
              company_name: businessName || "LossQ Demo Agency",
            }
          : {
              email: cleanEmail,
              password: password,
            };

      const res = await fetch(`${API}${endpoint}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      const data = await safeJson(res);

      if (!res.ok) {
        setMessage(
          typeof data?.detail === "string"
            ? data.detail
            : JSON.stringify(data?.detail || data || "Request failed.")
        );
        return;
      }

      const token = data?.access_token || data?.token;

      if (!token) {
        setMessage("Account request worked, but no login token was returned.");
        return;
      }

      localStorage.setItem("lossq_token", token);
      localStorage.setItem("lossq_user", cleanEmail);

      window.location.href = "/";
    } catch {
      setMessage("Fetch failed. Check Vercel API URL and Railway CORS.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#030508] text-white flex items-center justify-center px-6">
      <div className="fixed inset-0 bg-[linear-gradient(rgba(0,120,255,0.05)_1px,transparent_1px),linear-gradient(90deg,rgba(0,120,255,0.05)_1px,transparent_1px)] bg-[size:60px_60px]" />
      <div className="fixed inset-0 bg-[radial-gradient(circle_at_top,rgba(0,120,255,0.25),transparent_45%)]" />

      <div className="relative w-full max-w-md bg-[#0A1628] border border-blue-500/15 rounded-3xl p-8 shadow-2xl">
        <h1 className="text-4xl font-black">
          Loss<span className="text-blue-500">Q</span>
        </h1>

        <p className="text-slate-400 mt-2 mb-8">
          {mode === "login"
            ? "Sign in to open your underwriting dashboard."
            : "Create your LossQ account."}
        </p>

        {message && (
          <div className="bg-red-500/10 border border-red-500/30 text-red-300 rounded-lg p-3 mb-5 text-sm break-words">
            {message}
          </div>
        )}

        {mode === "register" && (
          <>
            <label className="block text-sm text-slate-400 mb-2">
              Agency / Business Name
            </label>
            <input
              value={businessName}
              onChange={(e) => setBusinessName(e.target.value)}
              className="w-full bg-slate-900 border border-slate-700 rounded-lg px-4 py-3 mb-5 outline-none focus:border-blue-500"
              placeholder="Your agency name"
            />
          </>
        )}

        <label className="block text-sm text-slate-400 mb-2">Email</label>
        <input
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full bg-slate-900 border border-slate-700 rounded-lg px-4 py-3 mb-5 outline-none focus:border-blue-500"
          placeholder="you@email.com"
        />

        <label className="block text-sm text-slate-400 mb-2">Password</label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full bg-slate-900 border border-slate-700 rounded-lg px-4 py-3 mb-6 outline-none focus:border-blue-500"
          placeholder="Password"
        />

        <button
          onClick={submit}
          disabled={loading}
          className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-lg py-3 font-bold shadow-[0_0_35px_rgba(0,120,255,0.25)]"
        >
          {loading
            ? "Please wait..."
            : mode === "login"
            ? "Sign In"
            : "Create Account"}
        </button>

        <button
          onClick={() => {
            setMode(mode === "login" ? "register" : "login");
            setMessage("");
          }}
          className="w-full mt-4 text-slate-400 hover:text-white text-sm"
        >
          {mode === "login"
            ? "Need an account? Register"
            : "Already have an account? Sign in"}
        </button>

        <a href="/landing" className="block text-center mt-6 text-blue-400 text-sm">
          Back to landing page
        </a>
      </div>
    </main>
  );
}
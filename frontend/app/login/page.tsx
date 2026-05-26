"use client";

import { useEffect, useState } from "react";

const API =
  process.env.NEXT_PUBLIC_API_URL || "https://lossq-production.up.railway.app";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);

    if (params.get("fresh") === "1") {
      localStorage.removeItem("lossq_token");
      localStorage.removeItem("lossq_user");
    }
  }, []);

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

      const res = await fetch(`${API}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: cleanEmail, password }),
      });

      const data = await res.json().catch(() => null);

      if (!res.ok) {
        setMessage(data?.detail || "Request failed.");
        return;
      }

      const token = data?.access_token || data?.token;

      if (!token) {
        setMessage("Account created. Please log in.");
        setMode("login");
        return;
      }

      localStorage.setItem("lossq_token", token);
      localStorage.setItem("lossq_user", cleanEmail);

      sessionStorage.setItem(
        "lossq_welcome",
        mode === "register"
          ? `Welcome to LossQ, ${cleanEmail.split("@")[0]}`
          : `Welcome back, ${cleanEmail.split("@")[0]}`
      );

      window.location.href = "/dashboard";
    } catch {
      setMessage("Fetch failed. Check backend connection.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#030508] text-white flex items-center justify-center px-6">
      <div className="fixed inset-0 bg-[linear-gradient(rgba(0,120,255,0.05)_1px,transparent_1px),linear-gradient(90deg,rgba(0,120,255,0.05)_1px,transparent_1px)] bg-[size:60px_60px]" />
      <div className="fixed inset-0 bg-[radial-gradient(circle_at_top,rgba(0,120,255,0.25),transparent_45%)]" />

      <div className="relative w-full max-w-md bg-[#0A1628] border border-blue-500/20 rounded-3xl p-8 shadow-2xl">
        <h1 className="text-5xl font-black mb-3">
          Loss<span className="text-blue-500">Q</span>
        </h1>

        <p className="text-slate-300 text-xl mb-8">
          {mode === "login" ? "Sign in to continue." : "Create your account"}
        </p>

        {message && (
          <div className="bg-red-500/10 border border-red-500/30 text-red-300 rounded-lg p-3 mb-5 text-sm">
            {message}
          </div>
        )}

        <input
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="Email"
          className="w-full bg-slate-900 border border-blue-400/40 rounded-lg px-4 py-3 mb-4 outline-none focus:border-blue-500"
        />

        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Password"
          className="w-full bg-slate-900 border border-blue-400/40 rounded-lg px-4 py-3 mb-6 outline-none focus:border-blue-500"
        />

        <button
          onClick={submit}
          disabled={loading}
          className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-lg py-3 font-bold"
        >
          {loading ? "Please wait..." : mode === "login" ? "Login" : "Register"}
        </button>

        <button
          onClick={() => {
            setMode(mode === "login" ? "register" : "login");
            setMessage("");
          }}
          className="w-full mt-4 text-slate-300 hover:text-white text-sm"
        >
          {mode === "login"
            ? "Need an account? Register"
            : "Already have an account? Login"}
        </button>

        <a href="/landing" className="block text-center mt-6 text-blue-400 text-sm">
          Back to landing
        </a>
      </div>
    </main>
  );
}


"use client";

import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

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
      const endpoint = mode === "login" ? "/auth/login" : "/auth/register";

      const res = await fetch(`${API}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: email.trim().toLowerCase(),
          password,
        }),
      });

      const data = await res.json().catch(() => null);

      if (!res.ok) {
        setMessage(data?.detail || "Request failed.");
        return;
      }

      const token = data?.access_token || data?.token;

      if (!token) {
        setMessage("No login token returned.");
        return;
      }

      localStorage.setItem("lossq_token", token);
      localStorage.setItem("lossq_user", email.trim().toLowerCase());

      window.location.href = "/dashboard";
    } catch {
      setMessage("Fetch failed. Check backend connection.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#030508] text-white flex items-center justify-center px-6">
      <div className="w-full max-w-md bg-[#0A1628] border border-blue-500/20 rounded-3xl p-8">
        <h1 className="text-4xl font-black mb-2">
          Loss<span className="text-blue-500">Q</span>
        </h1>

        <p className="text-slate-400 mb-8">
          {mode === "login" ? "Sign in to continue." : "Create your account."}
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
          className="w-full bg-slate-900 border border-slate-700 rounded-lg px-4 py-3 mb-4"
        />

        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Password"
          className="w-full bg-slate-900 border border-slate-700 rounded-lg px-4 py-3 mb-6"
        />

        <button
          onClick={submit}
          disabled={loading}
          className="w-full bg-blue-600 hover:bg-blue-700 rounded-lg py-3 font-bold"
        >
          {loading ? "Please wait..." : mode === "login" ? "Login" : "Register"}
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
            : "Already have an account? Login"}
        </button>

        <a href="/landing" className="block text-center mt-6 text-blue-400 text-sm">
          Back to landing
        </a>
      </div>
    </main>
  );
}

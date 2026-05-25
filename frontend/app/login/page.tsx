"use client";

import { useState } from "react";

export default function LoginPage() {
  const [email, setEmail] = useState("broker1@agency.com");
  const [password, setPassword] = useState("password123");
  const [message, setMessage] = useState("");

  async function login(e: React.FormEvent) {
    e.preventDefault();
    setMessage("Signing in...");

    try {
      const API_URL = process.env.NEXT_PUBLIC_API_URL;

      const res = await fetch(`${API_URL}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      const data = await res.json();

      if (!res.ok) {
        setMessage(`Login failed: ${JSON.stringify(data)}`);
        return;
      }

      localStorage.setItem("lossq_token", data.access_token || data.token || "");
      setMessage("Login successful");
      window.location.href = "/demo";
    } catch (err) {
      setMessage(`Fetch failed: ${String(err)}`);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center bg-[#030508] text-white px-6">
      <form onSubmit={login} className="w-full max-w-md bg-[#0A1628] border border-blue-500/20 rounded-2xl p-8">
        <h1 className="text-3xl font-black mb-2">LossQ</h1>
        <p className="text-slate-400 mb-8">Sign in to continue.</p>

        <input
          className="w-full mb-4 bg-white/5 border border-blue-500/20 rounded-lg px-4 py-3 outline-none"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="Email"
        />

        <input
          className="w-full mb-6 bg-white/5 border border-blue-500/20 rounded-lg px-4 py-3 outline-none"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Password"
          type="password"
        />

        <button className="w-full bg-blue-600 hover:bg-blue-700 rounded-lg py-3 font-bold">
          Sign In
        </button>

        {message && <p className="mt-5 text-sm text-blue-300">{message}</p>}
      </form>
    </main>
  );
}
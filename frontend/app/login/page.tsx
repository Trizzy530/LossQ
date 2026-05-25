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
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          email,
          password,
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        setMessage(`Login failed: ${JSON.stringify(data)}`);
        return;
      }

      localStorage.setItem("lossq_token", data.access_token);
      localStorage.setItem("lossq_user", data.user.email);

      window.location.href = "/";
    } catch (error: any) {
      setMessage(`Login failed: ${error.message}`);
    }
  }

  return (
    <main className="min-h-screen bg-slate-950 text-white flex items-center justify-center p-8">
      <form
        onSubmit={login}
        className="bg-slate-900 border border-slate-800 rounded-xl p-8 w-full max-w-md"
      >
        <h1 className="text-4xl font-bold mb-2">LossQ</h1>

        <p className="text-slate-400 mb-6">
          Sign in to your dashboard.
        </p>

        <label className="block text-sm text-slate-300 mb-2">
          Email
        </label>

        <input
          className="w-full bg-slate-800 p-3 rounded mb-4"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />

        <label className="block text-sm text-slate-300 mb-2">
          Password
        </label>

        <input
          className="w-full bg-slate-800 p-3 rounded mb-4"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />

        <button
          type="submit"
          className="w-full bg-blue-600 py-3 rounded"
        >
          Sign In
        </button>
<a
  href="/demo"
  className="block text-center mt-4 text-blue-400 hover:text-blue-300"
>
  Try instant demo without login
</a>
        {message && (
          <p className="mt-4 text-sm text-slate-300 break-words">
            {message}
          </p>
        )}
      </form>
    </main>
  );
}
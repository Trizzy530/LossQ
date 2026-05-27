"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

const API =
  process.env.NEXT_PUBLIC_API_URL || "https://lossq-production.up.railway.app";

function errorToText(data: any) {
  if (!data) return "Registration failed.";

  if (typeof data === "string") return data;
  if (typeof data.detail === "string") return data.detail;
  if (typeof data.message === "string") return data.message;

  if (Array.isArray(data.detail)) {
    return data.detail
      .map((item: any) => item?.msg || JSON.stringify(item))
      .join(", ");
  }

  return JSON.stringify(data);
}

export default function RegisterPage() {
  const router = useRouter();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const [error, setError] = useState<string>("");
  const [loading, setLoading] = useState(false);

  async function handleRegister(e: React.FormEvent) {
    e.preventDefault();

    setError("");
    setLoading(true);

    try {
      const res = await fetch(`${API}/auth/register`, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    email,
    password,
    name,
    full_name: name,
    organization_name: name,
    username: email,
  }),
});

      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        setError(errorToText(data));
        return;
      }

      const token = data.access_token || data.token;

      if (token) {
        localStorage.setItem("lossq_token", token);

        if (data.user) {
          localStorage.setItem("lossq_user", JSON.stringify(data.user));
        }

        router.replace("/dashboard?welcome=1");
        return;
      }

      setError("Account created, but no login token was returned. Try logging in.");
      router.replace("/login?fresh=1");
    } catch (err: any) {
      setError(err?.message || "Registration failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-slate-950 text-white flex items-center justify-center px-6">
      <form
        onSubmit={handleRegister}
        className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-2xl p-8"
      >
        <h1 className="text-3xl font-bold mb-2">Create LossQ Account</h1>
        <p className="text-slate-400 mb-6">Register to access your dashboard.</p>

        {error && (
          <div className="bg-red-500/10 border border-red-500/30 text-red-300 p-3 rounded-lg mb-4 whitespace-pre-wrap">
            {error}
          </div>
        )}

        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Name or Company"
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

        <button
          type="submit"
          disabled={loading}
          className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-60 rounded-lg px-5 py-3 font-semibold"
        >
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
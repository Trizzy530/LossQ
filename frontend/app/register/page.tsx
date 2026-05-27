"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

const API =
  process.env.NEXT_PUBLIC_API_URL || "https://lossq-production.up.railway.app";

export default function RegisterPage() {
  const router = useRouter();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  function getErrorMessage(data: any, fallback: string) {
    if (!data) return fallback;

    if (typeof data.detail === "string") return data.detail;
    if (typeof data.message === "string") return data.message;

    if (Array.isArray(data.detail)) {
      return data.detail
        .map((item: any) => item?.msg || JSON.stringify(item))
        .join(", ");
    }

    return fallback;
  }

  async function handleRegister(e: React.FormEvent) {
    e.preventDefault();

    setError("");
    setLoading(true);

    try {
      const registerRes = await fetch(`${API}/auth/register`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          full_name: name,
          name,
          email,
          password,
        }),
      });

      const registerData = await registerRes.json().catch(() => ({}));

      if (!registerRes.ok) {
        throw new Error(getErrorMessage(registerData, "Registration failed"));
      }

      const registerToken = registerData.access_token || registerData.token;

      if (registerToken) {
        localStorage.setItem("lossq_token", registerToken);

        if (registerData.user) {
          localStorage.setItem("lossq_user", JSON.stringify(registerData.user));
        }

        router.replace("/dashboard?welcome=1");
        return;
      }

      const loginRes = await fetch(`${API}/auth/login`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          email,
          password,
        }),
      });

      const loginData = await loginRes.json().catch(() => ({}));

      if (!loginRes.ok) {
        throw new Error(
          getErrorMessage(loginData, "Account created, but auto-login failed.")
        );
      }

      const loginToken = loginData.access_token || loginData.token;

      if (!loginToken) {
        throw new Error("Account created, but no login token was returned.");
      }

      localStorage.setItem("lossq_token", loginToken);

      if (loginData.user) {
        localStorage.setItem("lossq_user", JSON.stringify(loginData.user));
      }

      router.replace("/dashboard?welcome=1");
    } catch (err: any) {
      setError(err.message || "Registration failed");
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
        <p className="text-slate-400 mb-6">
          Register to access your dashboard.
        </p>

        {error && (
          <div className="bg-red-500/10 border border-red-500/30 text-red-300 p-3 rounded-lg mb-4">
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
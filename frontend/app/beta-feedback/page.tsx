"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

const API =
  process.env.NEXT_PUBLIC_API_URL ||
  "https://lossq-production.up.railway.app";

function getToken() {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("lossq_token") || "";
}

async function readApiError(response: Response) {
  const text = await response.text().catch(() => "");
  try {
    const parsed = JSON.parse(text);
    return parsed?.detail || parsed?.message || text;
  } catch {
    return text || `Request failed with status ${response.status}.`;
  }
}

export default function BetaFeedbackPage() {
  const router = useRouter();

  const [feature, setFeature] = useState("General");
  const [severity, setSeverity] = useState("normal");
  const [message, setMessage] = useState("");
  const [result, setResult] = useState("");
  const [loading, setLoading] = useState(false);

  async function submitFeedback() {
    setResult("");

    if (!message.trim()) {
      setResult("Please enter feedback before submitting.");
      return;
    }

    const token = getToken();

    if (!token) {
      router.replace("/login");
      return;
    }

    setLoading(true);

    try {
      const response = await fetch(`${API}/beta/feedback`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          feature,
          severity,
          message,
          page_url: typeof window !== "undefined" ? window.location.href : "",
        }),
      });

      if (response.status === 401) {
        router.replace("/login?expired=1");
        return;
      }

      if (!response.ok) {
        throw new Error(await readApiError(response));
      }

      const data = await response.json();
      setResult(data?.message || "Feedback submitted. Thank you.");
      setMessage("");
      setFeature("General");
      setSeverity("normal");
    } catch (error: any) {
      setResult(error?.message || "Feedback could not be submitted.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#050816] text-white">
      <header className="border-b border-white/10 bg-black/30 px-6 py-5">
        <div className="mx-auto flex max-w-4xl flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.3em] text-cyan-300">
              LossQ Beta
            </p>
            <h1 className="mt-2 text-3xl font-black">Submit Beta Feedback</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">
              Tell us what worked, what failed, what felt confusing, or what does not look ready for insurance professionals.
            </p>
          </div>

          <div className="flex flex-wrap gap-3">
            <Link
              href="/dashboard"
              className="rounded-xl border border-white/10 px-4 py-2 text-sm font-bold text-slate-200 hover:bg-white/10"
            >
              Dashboard
            </Link>
            <Link
              href="/beta-guide"
              className="rounded-xl border border-cyan-400/30 bg-cyan-400/10 px-4 py-2 text-sm font-bold text-cyan-100 hover:bg-cyan-400/20"
            >
              Beta Guide
            </Link>
          </div>
        </div>
      </header>

      <section className="mx-auto max-w-4xl px-6 py-8">
        <div className="rounded-3xl border border-white/10 bg-white/[0.03] p-6 shadow-xl">
          <div className="grid gap-4 md:grid-cols-2">
            <label className="space-y-2">
              <span className="text-xs font-bold uppercase tracking-[0.2em] text-slate-400">
                Feature
              </span>
              <select
                value={feature}
                onChange={(event) => setFeature(event.target.value)}
                className="w-full rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-sm outline-none focus:border-cyan-400"
              >
                <option>General</option>
                <option>Upload</option>
                <option>Claims Analysis</option>
                <option>Account Profile</option>
                <option>Exposure Inputs</option>
                <option>Renewal Score</option>
                <option>Reports</option>
                <option>Submission Builder</option>
                <option>Billing / Access</option>
                <option>Mobile / iPad</option>
              </select>
            </label>

            <label className="space-y-2">
              <span className="text-xs font-bold uppercase tracking-[0.2em] text-slate-400">
                Severity
              </span>
              <select
                value={severity}
                onChange={(event) => setSeverity(event.target.value)}
                className="w-full rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-sm outline-none focus:border-cyan-400"
              >
                <option value="normal">Normal</option>
                <option value="important">Important</option>
                <option value="critical">Critical</option>
                <option value="suggestion">Suggestion</option>
              </select>
            </label>
          </div>

          <label className="mt-5 block space-y-2">
            <span className="text-xs font-bold uppercase tracking-[0.2em] text-slate-400">
              Feedback
            </span>
            <textarea
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              rows={8}
              placeholder="Example: I uploaded a GL loss run and two claims were missing. The original file showed 7 claims, but LossQ showed 5."
              className="w-full rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-sm leading-6 outline-none focus:border-cyan-400"
            />
          </label>

          {result && (
            <div className="mt-5 rounded-2xl border border-cyan-400/20 bg-cyan-400/10 p-4 text-sm text-cyan-100">
              {result}
            </div>
          )}

          <button
            onClick={submitFeedback}
            disabled={loading}
            className="mt-5 rounded-xl bg-cyan-500 px-5 py-3 text-sm font-black text-slate-950 hover:bg-cyan-400 disabled:opacity-50"
          >
            {loading ? "Submitting..." : "Submit Feedback"}
          </button>
        </div>
      </section>
    </main>
  );
}

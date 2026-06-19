"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

const API =
  process.env.NEXT_PUBLIC_API_URL ||
  "https://lossq-production.up.railway.app";

function getToken() {
  if (typeof window === "undefined") return "";
  return sessionStorage.getItem("lossq_tab_token") || "";
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

export default function BetaExitSurveyPage() {
  const router = useRouter();

  const [overallScore, setOverallScore] = useState("8");
  const [wouldPay, setWouldPay] = useState("");
  const [likelyPlan, setLikelyPlan] = useState("");
  const [mostValuableFeature, setMostValuableFeature] = useState("");
  const [mostConfusingPart, setMostConfusingPart] = useState("");
  const [missingFeature, setMissingFeature] = useState("");
  const [wouldRecommend, setWouldRecommend] = useState("");
  const [launchBlocker, setLaunchBlocker] = useState("");
  const [additionalFeedback, setAdditionalFeedback] = useState("");
  const [result, setResult] = useState("");
  const [loading, setLoading] = useState(false);

  async function submitSurvey() {
    setResult("");

    const token = getToken();

    if (!token) {
      router.replace("/login?fresh=1");
      return;
    }

    const score = Number(overallScore || 0);

    if (score < 1 || score > 10) {
      setResult("Please select an overall score from 1 to 10.");
      return;
    }

    setLoading(true);

    try {
      const response = await fetch(`${API}/beta/exit-survey`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          overall_score: score,
          would_pay: wouldPay,
          likely_plan: likelyPlan,
          most_valuable_feature: mostValuableFeature,
          most_confusing_part: mostConfusingPart,
          missing_feature: missingFeature,
          would_recommend: wouldRecommend,
          launch_blocker: launchBlocker,
          additional_feedback: additionalFeedback,
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
      setResult(data?.message || "Exit survey submitted. Thank you.");
    } catch (error: any) {
      setResult(error?.message || "Exit survey could not be submitted.");
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
            <h1 className="mt-2 text-3xl font-black">Beta Exit Survey</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">
              Help us understand whether LossQ is ready for launch and what needs to improve before release.
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
                Overall Score
              </span>
              <select
                value={overallScore}
                onChange={(event) => setOverallScore(event.target.value)}
                className="w-full rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-sm outline-none focus:border-cyan-400"
              >
                {[10, 9, 8, 7, 6, 5, 4, 3, 2, 1].map((score) => (
                  <option key={score} value={score}>
                    {score} / 10
                  </option>
                ))}
              </select>
            </label>

            <label className="space-y-2">
              <span className="text-xs font-bold uppercase tracking-[0.2em] text-slate-400">
                Would you pay for LossQ?
              </span>
              <select
                value={wouldPay}
                onChange={(event) => setWouldPay(event.target.value)}
                className="w-full rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-sm outline-none focus:border-cyan-400"
              >
                <option value="">Select one</option>
                <option>Yes</option>
                <option>Maybe</option>
                <option>No</option>
                <option>Need more features first</option>
              </select>
            </label>

            <label className="space-y-2">
              <span className="text-xs font-bold uppercase tracking-[0.2em] text-slate-400">
                Best-fit plan
              </span>
              <select
                value={likelyPlan}
                onChange={(event) => setLikelyPlan(event.target.value)}
                className="w-full rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-sm outline-none focus:border-cyan-400"
              >
                <option value="">Select one</option>
                <option>Starter</option>
                <option>Professional</option>
                <option>Agency</option>
                <option>Founding Agency</option>
                <option>Enterprise / Carrier</option>
                <option>Not sure</option>
              </select>
            </label>

            <label className="space-y-2">
              <span className="text-xs font-bold uppercase tracking-[0.2em] text-slate-400">
                Would you recommend it?
              </span>
              <select
                value={wouldRecommend}
                onChange={(event) => setWouldRecommend(event.target.value)}
                className="w-full rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-sm outline-none focus:border-cyan-400"
              >
                <option value="">Select one</option>
                <option>Yes</option>
                <option>Maybe</option>
                <option>No</option>
              </select>
            </label>
          </div>

          <label className="mt-5 block space-y-2">
            <span className="text-xs font-bold uppercase tracking-[0.2em] text-slate-400">
              Most valuable feature
            </span>
            <textarea
              value={mostValuableFeature}
              onChange={(event) => setMostValuableFeature(event.target.value)}
              rows={3}
              className="w-full rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-sm leading-6 outline-none focus:border-cyan-400"
            />
          </label>

          <label className="mt-5 block space-y-2">
            <span className="text-xs font-bold uppercase tracking-[0.2em] text-slate-400">
              Most confusing part
            </span>
            <textarea
              value={mostConfusingPart}
              onChange={(event) => setMostConfusingPart(event.target.value)}
              rows={3}
              className="w-full rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-sm leading-6 outline-none focus:border-cyan-400"
            />
          </label>

          <label className="mt-5 block space-y-2">
            <span className="text-xs font-bold uppercase tracking-[0.2em] text-slate-400">
              Missing feature
            </span>
            <textarea
              value={missingFeature}
              onChange={(event) => setMissingFeature(event.target.value)}
              rows={3}
              className="w-full rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-sm leading-6 outline-none focus:border-cyan-400"
            />
          </label>

          <label className="mt-5 block space-y-2">
            <span className="text-xs font-bold uppercase tracking-[0.2em] text-slate-400">
              What would block you from using LossQ at launch?
            </span>
            <textarea
              value={launchBlocker}
              onChange={(event) => setLaunchBlocker(event.target.value)}
              rows={3}
              className="w-full rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-sm leading-6 outline-none focus:border-cyan-400"
            />
          </label>

          <label className="mt-5 block space-y-2">
            <span className="text-xs font-bold uppercase tracking-[0.2em] text-slate-400">
              Additional feedback
            </span>
            <textarea
              value={additionalFeedback}
              onChange={(event) => setAdditionalFeedback(event.target.value)}
              rows={4}
              className="w-full rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-sm leading-6 outline-none focus:border-cyan-400"
            />
          </label>

          {result && (
            <div className="mt-5 rounded-2xl border border-cyan-400/20 bg-cyan-400/10 p-4 text-sm text-cyan-100">
              {result}
            </div>
          )}

          <button
            onClick={submitSurvey}
            disabled={loading}
            className="mt-5 rounded-xl bg-cyan-500 px-5 py-3 text-sm font-black text-slate-950 hover:bg-cyan-400 disabled:opacity-50"
          >
            {loading ? "Submitting..." : "Submit Exit Survey"}
          </button>
        </div>
      </section>
    </main>
  );
}

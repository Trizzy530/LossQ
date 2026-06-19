"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

const API =
  process.env.NEXT_PUBLIC_API_URL ||
  "https://lossq-production.up.railway.app";

type AnyObject = Record<string, any>;

function getToken() {
  if (typeof window === "undefined") return "";
  return sessionStorage.getItem("lossq_tab_token") || "";
}

function authHeaders() {
  const token = getToken();
  return {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };
}

function cleanDate(value: any) {
  if (!value) return "-";
  try {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "-";
    return date.toLocaleString();
  } catch {
    return String(value);
  }
}

function scoreTone(score: any) {
  const cleanScore = Number(score || 0);
  if (cleanScore >= 9) return "border-emerald-400/30 bg-emerald-400/10 text-emerald-200";
  if (cleanScore >= 7) return "border-cyan-400/30 bg-cyan-400/10 text-cyan-200";
  if (cleanScore >= 5) return "border-amber-400/30 bg-amber-400/10 text-amber-200";
  return "border-rose-400/30 bg-rose-400/10 text-rose-200";
}

function statusTone(status: string) {
  const clean = String(status || "").toLowerCase();
  if (clean === "closed") return "border-slate-400/30 bg-slate-400/10 text-slate-200";
  if (clean === "reviewed") return "border-emerald-400/30 bg-emerald-400/10 text-emerald-200";
  if (clean === "follow_up") return "border-orange-400/30 bg-orange-400/10 text-orange-200";
  return "border-cyan-400/30 bg-cyan-400/10 text-cyan-200";
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

export default function PlatformBetaExitSurveysPage() {
  const router = useRouter();

  const [surveys, setSurveys] = useState<AnyObject[]>([]);
  const [averageScore, setAverageScore] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [search, setSearch] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);

  async function loadSurveys() {
    setLoading(true);
    setMessage("");

    try {
      if (!getToken()) {
        router.replace("/login?fresh=1");
        return;
      }

      const response = await fetch(`${API}/platform-admin/beta-exit-surveys`, {
        headers: authHeaders(),
        cache: "no-store",
      });

      if (response.status === 401) {
        router.replace("/login?expired=1");
        return;
      }

      if (response.status === 403) {
        setMessage("This area is restricted to authorized LossQ administrators.");
        setSurveys([]);
        return;
      }

      if (!response.ok) {
        throw new Error(await readApiError(response));
      }

      const data = await response.json();
      setSurveys(Array.isArray(data?.surveys) ? data.surveys : []);
      setAverageScore(data?.average_score ?? null);
    } catch (error: any) {
      setMessage(error?.message || "Beta exit surveys could not be loaded.");
      setSurveys([]);
    } finally {
      setLoading(false);
    }
  }

  async function updateStatus(id: number, status: string) {
    setBusyId(id);
    setMessage("Updating survey status...");

    try {
      const response = await fetch(`${API}/platform-admin/beta-exit-surveys/${id}/status`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ status, notes: "" }),
      });

      if (!response.ok) {
        throw new Error(await readApiError(response));
      }

      const data = await response.json();
      setMessage(data?.message || "Survey updated.");
      await loadSurveys();
    } catch (error: any) {
      setMessage(error?.message || "Survey could not be updated.");
    } finally {
      setBusyId(null);
    }
  }

  useEffect(() => {
    loadSurveys();
  }, []);

  const filteredSurveys = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return surveys;
    return surveys.filter((item) => JSON.stringify(item || {}).toLowerCase().includes(q));
  }, [surveys, search]);

  const wouldPayCount = surveys.filter((item) =>
    String(item.would_pay || "").toLowerCase().includes("yes")
  ).length;

  const recommendCount = surveys.filter((item) =>
    String(item.would_recommend || "").toLowerCase().includes("yes")
  ).length;

  return (
    <main className="min-h-screen bg-[#050816] text-white">
      <header className="border-b border-white/10 bg-black/30 px-6 py-5">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.3em] text-cyan-300">
              LossQ Owner Console
            </p>
            <h1 className="mt-2 text-3xl font-black">Beta Exit Surveys</h1>
            <p className="mt-1 text-sm text-slate-400">
              Review launch readiness, willingness to pay, missing features, and buyer feedback.
            </p>
          </div>

          <div className="flex flex-wrap gap-3">
            <button
              onClick={() => router.push("/platform-admin")}
              className="rounded-xl border border-white/10 px-4 py-2 text-sm hover:bg-white/10"
            >
              Back to Platform Admin
            </button>
            <button
              onClick={loadSurveys}
              className="rounded-xl bg-cyan-500 px-4 py-2 text-sm font-bold text-slate-950 hover:bg-cyan-400"
            >
              Refresh
            </button>
          </div>
        </div>
      </header>

      <section className="mx-auto max-w-7xl space-y-6 px-6 py-8">
        <div className="grid gap-4 md:grid-cols-4">
          <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-slate-500">Surveys</p>
            <p className="mt-2 text-3xl font-black">{surveys.length}</p>
          </div>
          <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-slate-500">Average Score</p>
            <p className="mt-2 text-3xl font-black">{averageScore ?? "-"}</p>
          </div>
          <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-slate-500">Would Pay</p>
            <p className="mt-2 text-3xl font-black">{wouldPayCount}</p>
          </div>
          <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-slate-500">Would Recommend</p>
            <p className="mt-2 text-3xl font-black">{recommendCount}</p>
          </div>
        </div>

        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search email, plan, score, feedback..."
          className="w-full rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-sm outline-none focus:border-cyan-400"
        />

        {message && (
          <div className="rounded-2xl border border-cyan-400/20 bg-cyan-400/10 p-4 text-sm text-cyan-100">
            {message}
          </div>
        )}

        {loading ? (
          <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-6 text-slate-300">
            Loading beta exit surveys...
          </div>
        ) : filteredSurveys.length === 0 ? (
          <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-6 text-slate-300">
            No beta exit surveys found yet.
          </div>
        ) : (
          <div className="grid gap-4">
            {filteredSurveys.map((survey) => {
              const id = Number(survey.id);
              const status = String(survey.status || "new");

              return (
                <article key={id} className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                    <div className="min-w-0 space-y-4">
                      <div className="flex flex-wrap items-center gap-3">
                        <h2 className="break-all text-xl font-black">{survey.email || "Unknown user"}</h2>
                        <span className={`rounded-full border px-3 py-1 text-xs font-bold ${scoreTone(survey.overall_score)}`}>
                          SCORE {survey.overall_score || "-"} / 10
                        </span>
                        <span className={`rounded-full border px-3 py-1 text-xs font-bold ${statusTone(status)}`}>
                          {status.toUpperCase()}
                        </span>
                      </div>

                      <div className="grid gap-2 text-sm text-slate-300 md:grid-cols-2 lg:grid-cols-4">
                        <p><span className="text-slate-500">Would Pay:</span> {survey.would_pay || "-"}</p>
                        <p><span className="text-slate-500">Plan:</span> {survey.likely_plan || "-"}</p>
                        <p><span className="text-slate-500">Recommend:</span> {survey.would_recommend || "-"}</p>
                        <p><span className="text-slate-500">Created:</span> {cleanDate(survey.created_at)}</p>
                      </div>

                      <div className="grid gap-3">
                        <p className="rounded-xl border border-white/10 bg-black/20 p-4 text-sm leading-6 text-slate-200">
                          <strong className="text-cyan-200">Most Valuable:</strong><br />
                          {survey.most_valuable_feature || "-"}
                        </p>
                        <p className="rounded-xl border border-white/10 bg-black/20 p-4 text-sm leading-6 text-slate-200">
                          <strong className="text-amber-200">Most Confusing:</strong><br />
                          {survey.most_confusing_part || "-"}
                        </p>
                        <p className="rounded-xl border border-white/10 bg-black/20 p-4 text-sm leading-6 text-slate-200">
                          <strong className="text-purple-200">Missing Feature:</strong><br />
                          {survey.missing_feature || "-"}
                        </p>
                        <p className="rounded-xl border border-white/10 bg-black/20 p-4 text-sm leading-6 text-slate-200">
                          <strong className="text-rose-200">Launch Blocker:</strong><br />
                          {survey.launch_blocker || "-"}
                        </p>
                      </div>
                    </div>

                    <div className="flex flex-wrap gap-2 lg:min-w-48">
                      {["new", "reviewed", "follow_up", "closed"].map((nextStatus) => (
                        <button
                          key={nextStatus}
                          onClick={() => updateStatus(id, nextStatus)}
                          disabled={busyId === id || status === nextStatus}
                          className="rounded-xl border border-white/10 px-3 py-2 text-xs font-bold text-slate-200 hover:bg-white/10 disabled:opacity-40"
                        >
                          {nextStatus}
                        </button>
                      ))}
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>
    </main>
  );
}

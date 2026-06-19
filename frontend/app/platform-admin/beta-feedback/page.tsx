"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

const API =
  process.env.NEXT_PUBLIC_API_URL ||
  "https://lossq-production.up.railway.app";

type AnyObject = Record<string, any>;

function getToken() {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("lossq_token") || "";
}

function authHeaders() {
  return {
    Authorization: `Bearer ${getToken()}`,
    "Content-Type": "application/json",
  };
}

function cleanDate(value: any) {
  if (!value) return "-";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return String(value);
  }
}

function statusClass(status: string) {
  const clean = String(status || "").toLowerCase();

  if (clean === "fixed") return "border-emerald-400/30 bg-emerald-400/10 text-emerald-200";
  if (clean === "reviewing") return "border-cyan-400/30 bg-cyan-400/10 text-cyan-200";
  if (clean === "closed") return "border-slate-400/30 bg-slate-400/10 text-slate-200";
  return "border-amber-400/30 bg-amber-400/10 text-amber-200";
}

function severityClass(severity: string) {
  const clean = String(severity || "").toLowerCase();

  if (clean === "critical") return "border-rose-400/30 bg-rose-400/10 text-rose-200";
  if (clean === "important") return "border-orange-400/30 bg-orange-400/10 text-orange-200";
  if (clean === "suggestion") return "border-purple-400/30 bg-purple-400/10 text-purple-200";
  return "border-slate-400/30 bg-slate-400/10 text-slate-200";
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

export default function PlatformBetaFeedbackPage() {
  const router = useRouter();

  const [feedback, setFeedback] = useState<AnyObject[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [search, setSearch] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);

  async function loadFeedback() {
    setLoading(true);
    setMessage("");

    try {
      if (!getToken()) {
        router.replace("/login");
        return;
      }

      const response = await fetch(`${API}/platform-admin/beta-feedback`, {
        headers: authHeaders(),
        cache: "no-store",
      });

      if (response.status === 401) {
        router.replace("/login?expired=1");
        return;
      }

      if (response.status === 403) {
        setMessage("Platform Admin access is required to view beta feedback.");
        setFeedback([]);
        return;
      }

      if (!response.ok) {
        throw new Error(await readApiError(response));
      }

      const data = await response.json();
      setFeedback(Array.isArray(data?.feedback) ? data.feedback : []);
    } catch (error: any) {
      setMessage(error?.message || "Beta feedback could not be loaded.");
      setFeedback([]);
    } finally {
      setLoading(false);
    }
  }

  async function updateStatus(id: number, status: string) {
    setBusyId(id);
    setMessage("Updating feedback status...");

    try {
      const response = await fetch(`${API}/platform-admin/beta-feedback/${id}/status`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({
          status,
          notes: "",
        }),
      });

      if (!response.ok) {
        throw new Error(await readApiError(response));
      }

      const data = await response.json();
      setMessage(data?.message || "Feedback updated.");
      await loadFeedback();
    } catch (error: any) {
      setMessage(error?.message || "Feedback could not be updated.");
    } finally {
      setBusyId(null);
    }
  }

  useEffect(() => {
    loadFeedback();
  }, []);

  const filteredFeedback = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return feedback;

    return feedback.filter((item) => JSON.stringify(item || {}).toLowerCase().includes(q));
  }, [feedback, search]);

  return (
    <main className="min-h-screen bg-[#050816] text-white">
      <header className="border-b border-white/10 bg-black/30 px-6 py-5">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.3em] text-cyan-300">
              LossQ Owner Console
            </p>
            <h1 className="mt-2 text-3xl font-black">Beta Feedback</h1>
            <p className="mt-1 text-sm text-slate-400">
              Track beta user issues, requests, bugs, and product feedback.
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
              onClick={loadFeedback}
              className="rounded-xl bg-cyan-500 px-4 py-2 text-sm font-bold text-slate-950 hover:bg-cyan-400"
            >
              Refresh
            </button>
          </div>
        </div>
      </header>

      <section className="mx-auto max-w-7xl space-y-6 px-6 py-8">
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search email, feature, severity, message, status..."
          className="w-full rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-sm outline-none focus:border-cyan-400"
        />

        {message && (
          <div className="rounded-2xl border border-cyan-400/20 bg-cyan-400/10 p-4 text-sm text-cyan-100">
            {message}
          </div>
        )}

        {loading ? (
          <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-6 text-slate-300">
            Loading beta feedback...
          </div>
        ) : filteredFeedback.length === 0 ? (
          <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-6 text-slate-300">
            No beta feedback found yet.
          </div>
        ) : (
          <div className="grid gap-4">
            {filteredFeedback.map((item) => {
              const id = Number(item.id);
              const status = String(item.status || "new");
              const severity = String(item.severity || "normal");

              return (
                <article key={id} className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                    <div className="min-w-0 space-y-3">
                      <div className="flex flex-wrap items-center gap-3">
                        <h2 className="break-all text-lg font-black">{item.email || "Unknown user"}</h2>
                        <span className={`rounded-full border px-3 py-1 text-xs font-bold ${statusClass(status)}`}>
                          {status.toUpperCase()}
                        </span>
                        <span className={`rounded-full border px-3 py-1 text-xs font-bold ${severityClass(severity)}`}>
                          {severity.toUpperCase()}
                        </span>
                      </div>

                      <div className="grid gap-2 text-sm text-slate-300 md:grid-cols-2 lg:grid-cols-4">
                        <p><span className="text-slate-500">Feature:</span> {item.feature || "-"}</p>
                        <p><span className="text-slate-500">Created:</span> {cleanDate(item.created_at)}</p>
                        <p><span className="text-slate-500">User ID:</span> {item.user_id || "-"}</p>
                        <p><span className="text-slate-500">Org ID:</span> {item.organization_id || "-"}</p>
                      </div>

                      <p className="rounded-xl border border-white/10 bg-black/20 p-4 text-sm leading-6 text-slate-200">
                        {item.message}
                      </p>

                      {item.page_url && (
                        <p className="break-all text-xs text-slate-500">
                          Page: {item.page_url}
                        </p>
                      )}
                    </div>

                    <div className="flex flex-wrap gap-2">
                      {["new", "reviewing", "fixed", "closed"].map((nextStatus) => (
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

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

  if (clean === "activated") {
    return "border-emerald-400/30 bg-emerald-400/10 text-emerald-200";
  }

  if (clean === "approved") {
    return "border-cyan-400/30 bg-cyan-400/10 text-cyan-200";
  }

  if (clean === "rejected") {
    return "border-rose-400/30 bg-rose-400/10 text-rose-200";
  }

  return "border-amber-400/30 bg-amber-400/10 text-amber-200";
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

export default function BetaRequestsPage() {
  const router = useRouter();

  const [requests, setRequests] = useState<AnyObject[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [search, setSearch] = useState("");
  const [days, setDays] = useState(30);
  const [uploadLimit, setUploadLimit] = useState(10);
  const [userLimit, setUserLimit] = useState(1);
  const [busyId, setBusyId] = useState<number | null>(null);

  async function loadRequests() {
    setLoading(true);
    setMessage("");

    try {
      if (!getToken()) {
        router.replace("/login");
        return;
      }

      const response = await fetch(`${API}/platform-admin/beta-requests`, {
        headers: authHeaders(),
        cache: "no-store",
      });

      if (response.status === 401) {
        router.replace("/login?expired=1");
        return;
      }

      if (response.status === 403) {
        setMessage("Platform Admin access is required to view beta requests.");
        setRequests([]);
        return;
      }

      if (!response.ok) {
        throw new Error(await readApiError(response));
      }

      const data = await response.json();
      setRequests(Array.isArray(data?.beta_requests) ? data.beta_requests : []);
    } catch (error: any) {
      setMessage(error?.message || "Beta requests could not be loaded.");
      setRequests([]);
    } finally {
      setLoading(false);
    }
  }

  async function approveRequest(requestId: number) {
    setBusyId(requestId);
    setMessage("Approving beta request...");

    try {
      const response = await fetch(`${API}/platform-admin/beta-requests/${requestId}/approve`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({
          days,
          upload_limit: uploadLimit,
          user_limit: userLimit,
        }),
      });

      if (!response.ok) {
        throw new Error(await readApiError(response));
      }

      const data = await response.json();
      setMessage(data?.message || "Beta request approved.");
      await loadRequests();
    } catch (error: any) {
      setMessage(error?.message || "Beta request could not be approved.");
    } finally {
      setBusyId(null);
    }
  }

  async function rejectRequest(requestId: number) {
    if (!confirm("Reject this beta request?")) return;

    setBusyId(requestId);
    setMessage("Rejecting beta request...");

    try {
      const response = await fetch(`${API}/platform-admin/beta-requests/${requestId}/reject`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({
          note: "Rejected from Platform Admin.",
        }),
      });

      if (!response.ok) {
        throw new Error(await readApiError(response));
      }

      const data = await response.json();
      setMessage(data?.message || "Beta request rejected.");
      await loadRequests();
    } catch (error: any) {
      setMessage(error?.message || "Beta request could not be rejected.");
    } finally {
      setBusyId(null);
    }
  }

  useEffect(() => {
    loadRequests();
  }, []);

  const filteredRequests = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return requests;

    return requests.filter((item) => JSON.stringify(item || {}).toLowerCase().includes(q));
  }, [requests, search]);

  return (
    <main className="min-h-screen bg-[#050816] text-white">
      <header className="border-b border-white/10 bg-black/30 px-6 py-5">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.3em] text-cyan-300">
              LossQ Owner Console
            </p>
            <h1 className="mt-2 text-3xl font-black">Beta Requests</h1>
            <p className="mt-1 text-sm text-slate-400">
              Review beta signups, approve access, reject requests, and activate beta users after registration.
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
              onClick={loadRequests}
              className="rounded-xl bg-cyan-500 px-4 py-2 text-sm font-bold text-slate-950 hover:bg-cyan-400"
            >
              Refresh
            </button>
          </div>
        </div>
      </header>

      <section className="mx-auto max-w-7xl space-y-6 px-6 py-8">
        <div className="grid gap-4 rounded-2xl border border-white/10 bg-white/[0.03] p-5 md:grid-cols-4">
          <label className="space-y-2">
            <span className="text-xs font-bold uppercase tracking-[0.2em] text-slate-400">
              Search
            </span>
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Email, status, company..."
              className="w-full rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-sm outline-none focus:border-cyan-400"
            />
          </label>

          <label className="space-y-2">
            <span className="text-xs font-bold uppercase tracking-[0.2em] text-slate-400">
              Beta Days
            </span>
            <input
              type="number"
              min={1}
              max={120}
              value={days}
              onChange={(event) => setDays(Number(event.target.value || 30))}
              className="w-full rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-sm outline-none focus:border-cyan-400"
            />
          </label>

          <label className="space-y-2">
            <span className="text-xs font-bold uppercase tracking-[0.2em] text-slate-400">
              Upload Limit
            </span>
            <input
              type="number"
              min={1}
              value={uploadLimit}
              onChange={(event) => setUploadLimit(Number(event.target.value || 10))}
              className="w-full rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-sm outline-none focus:border-cyan-400"
            />
          </label>

          <label className="space-y-2">
            <span className="text-xs font-bold uppercase tracking-[0.2em] text-slate-400">
              User Limit
            </span>
            <input
              type="number"
              min={1}
              value={userLimit}
              onChange={(event) => setUserLimit(Number(event.target.value || 1))}
              className="w-full rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-sm outline-none focus:border-cyan-400"
            />
          </label>
        </div>

        {message && (
          <div className="rounded-2xl border border-cyan-400/20 bg-cyan-400/10 p-4 text-sm text-cyan-100">
            {message}
          </div>
        )}

        {loading ? (
          <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-6 text-slate-300">
            Loading beta requests...
          </div>
        ) : filteredRequests.length === 0 ? (
          <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-6 text-slate-300">
            No beta requests found yet.
          </div>
        ) : (
          <div className="grid gap-4">
            {filteredRequests.map((item) => {
              const id = Number(item.id);
              const status = String(item.status || "new");
              const registered = Boolean(item.registered);
              const organization = item.organization || {};
              const user = item.user || {};

              return (
                <article key={id} className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                    <div className="min-w-0 space-y-3">
                      <div className="flex flex-wrap items-center gap-3">
                        <h2 className="break-all text-xl font-black">{item.email}</h2>
                        <span className={`rounded-full border px-3 py-1 text-xs font-bold ${statusClass(status)}`}>
                          {status.toUpperCase()}
                        </span>
                        <span className={`rounded-full border px-3 py-1 text-xs font-bold ${
                          registered
                            ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-200"
                            : "border-amber-400/30 bg-amber-400/10 text-amber-200"
                        }`}>
                          {registered ? "REGISTERED" : "PENDING REGISTRATION"}
                        </span>
                      </div>

                      <div className="grid gap-2 text-sm text-slate-300 md:grid-cols-2 lg:grid-cols-3">
                        <p><span className="text-slate-500">Source:</span> {item.source || "-"}</p>
                        <p><span className="text-slate-500">Requested:</span> {cleanDate(item.created_at)}</p>
                        <p><span className="text-slate-500">Updated:</span> {cleanDate(item.updated_at)}</p>
                        <p><span className="text-slate-500">User ID:</span> {user.id || "-"}</p>
                        <p><span className="text-slate-500">Org ID:</span> {organization.id || user.organization_id || "-"}</p>
                        <p><span className="text-slate-500">Plan:</span> {organization.plan || "-"}</p>
                      </div>

                      {item.notes && (
                        <p className="rounded-xl border border-white/10 bg-black/20 p-3 text-sm text-slate-300">
                          {item.notes}
                        </p>
                      )}
                    </div>

                    <div className="flex flex-wrap gap-2">
                      <button
                        onClick={() => approveRequest(id)}
                        disabled={busyId === id}
                        className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-bold text-slate-950 hover:bg-emerald-400 disabled:opacity-50"
                      >
                        {registered ? "Approve + Activate" : "Approve"}
                      </button>

                      <button
                        onClick={() => rejectRequest(id)}
                        disabled={busyId === id}
                        className="rounded-xl border border-rose-400/40 px-4 py-2 text-sm font-bold text-rose-200 hover:bg-rose-400/10 disabled:opacity-50"
                      >
                        Reject
                      </button>
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

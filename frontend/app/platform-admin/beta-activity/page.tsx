"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

const API =
  process.env.NEXT_PUBLIC_API_URL ||
  "https://lossq-production.up.railway.app";

type AnyObject = Record<string, any>;

function getToken() {
  if (typeof window === "undefined") return "";

  const tabToken = sessionStorage.getItem("lossq_tab_token");
  if (tabToken) return tabToken;

  const localToken = localStorage.getItem("lossq_token") || "";
  if (localToken) {
    sessionStorage.setItem("lossq_tab_token", localToken);
  }

  return localToken;
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
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "-";
    return date.toLocaleString();
  } catch {
    return String(value);
  }
}

function compactDate(value: any) {
  if (!value) return "-";

  try {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "-";
    return date.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return String(value);
  }
}

function usageLabel(used: any, limit: any) {
  const cleanUsed = Number(used || 0);
  const cleanLimit = Number(limit || 0);

  if (!cleanLimit) return `${cleanUsed} used`;

  return `${cleanUsed} / ${cleanLimit}`;
}

function usageTone(used: any, limit: any) {
  const cleanUsed = Number(used || 0);
  const cleanLimit = Number(limit || 0);

  if (!cleanLimit) return "border-slate-400/30 bg-slate-400/10 text-slate-200";

  const percent = cleanUsed / cleanLimit;

  if (percent >= 1) return "border-rose-400/30 bg-rose-400/10 text-rose-200";
  if (percent >= 0.75) return "border-orange-400/30 bg-orange-400/10 text-orange-200";
  if (percent >= 0.4) return "border-amber-400/30 bg-amber-400/10 text-amber-200";

  return "border-emerald-400/30 bg-emerald-400/10 text-emerald-200";
}

function activityTone(user: AnyObject) {
  if (Number(user.feedback_count || 0) > 0 || Number(user.uploads_used || 0) > 0) {
    return "border-emerald-400/30 bg-emerald-400/10 text-emerald-200";
  }

  if (user.last_login_at) {
    return "border-cyan-400/30 bg-cyan-400/10 text-cyan-200";
  }

  return "border-amber-400/30 bg-amber-400/10 text-amber-200";
}

function activityLabel(user: AnyObject) {
  if (Number(user.feedback_count || 0) > 0) return "Feedback submitted";
  if (Number(user.uploads_used || 0) > 0) return "Testing uploads";
  if (user.last_login_at) return "Logged in";
  return "No activity yet";
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

export default function PlatformBetaActivityPage() {
  const router = useRouter();

  const [users, setUsers] = useState<AnyObject[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [search, setSearch] = useState("");

  async function loadActivity() {
    setLoading(true);
    setMessage("");

    try {
      if (!getToken()) {
        router.replace("/login");
        return;
      }

      const response = await fetch(`${API}/platform-admin/beta-activity`, {
        headers: authHeaders(),
        cache: "no-store",
      });

      if (response.status === 401) {
        router.replace("/login?expired=1");
        return;
      }

      if (response.status === 403) {
        setMessage("This area is restricted to authorized LossQ administrators.");
        setUsers([]);
        return;
      }

      if (!response.ok) {
        throw new Error(await readApiError(response));
      }

      const data = await response.json();
      setUsers(Array.isArray(data?.beta_users) ? data.beta_users : []);
    } catch (error: any) {
      setMessage(error?.message || "Beta activity could not be loaded.");
      setUsers([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadActivity();
  }, []);

  const filteredUsers = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return users;

    return users.filter((user) => JSON.stringify(user || {}).toLowerCase().includes(q));
  }, [users, search]);

  const totals = useMemo(() => {
    return {
      users: users.length,
      active: users.filter(
        (user) => Number(user.feedback_count || 0) > 0 || Number(user.uploads_used || 0) > 0 || user.last_login_at
      ).length,
      uploads: users.reduce((sum, user) => sum + Number(user.uploads_used || 0), 0),
      feedback: users.reduce((sum, user) => sum + Number(user.feedback_count || 0), 0),
    };
  }, [users]);

  return (
    <main className="min-h-screen bg-[#050816] text-white">
      <header className="border-b border-white/10 bg-black/30 px-6 py-5">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.3em] text-cyan-300">
              LossQ Owner Console
            </p>
            <h1 className="mt-2 text-3xl font-black">Beta User Activity</h1>
            <p className="mt-1 text-sm text-slate-400">
              See which beta users are logging in, uploading files, and submitting feedback.
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
              onClick={loadActivity}
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
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-slate-500">Beta Users</p>
            <p className="mt-2 text-3xl font-black">{totals.users}</p>
          </div>
          <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-slate-500">Active Testers</p>
            <p className="mt-2 text-3xl font-black">{totals.active}</p>
          </div>
          <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-slate-500">Uploads Used</p>
            <p className="mt-2 text-3xl font-black">{totals.uploads}</p>
          </div>
          <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-slate-500">Feedback Items</p>
            <p className="mt-2 text-3xl font-black">{totals.feedback}</p>
          </div>
        </div>

        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search email, organization, plan, status..."
          className="w-full rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-sm outline-none focus:border-cyan-400"
        />

        {message && (
          <div className="rounded-2xl border border-cyan-400/20 bg-cyan-400/10 p-4 text-sm text-cyan-100">
            {message}
          </div>
        )}

        {loading ? (
          <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-6 text-slate-300">
            Loading beta activity...
          </div>
        ) : filteredUsers.length === 0 ? (
          <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-6 text-slate-300">
            No beta users found yet.
          </div>
        ) : (
          <div className="grid gap-4">
            {filteredUsers.map((user) => (
              <article
                key={`${user.user_id}-${user.email}`}
                className="rounded-2xl border border-white/10 bg-white/[0.03] p-5"
              >
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div className="min-w-0 space-y-3">
                    <div className="flex flex-wrap items-center gap-3">
                      <h2 className="break-all text-xl font-black">{user.email}</h2>
                      <span className={`rounded-full border px-3 py-1 text-xs font-bold ${activityTone(user)}`}>
                        {activityLabel(user)}
                      </span>
                      <span className="rounded-full border border-cyan-400/30 bg-cyan-400/10 px-3 py-1 text-xs font-bold text-cyan-200">
                        {(user.plan || "beta").toString().toUpperCase()}
                      </span>
                    </div>

                    <p className="text-sm text-slate-400">
                      {user.full_name || "No name"} • {user.organization_name || "No organization name"}
                    </p>

                    <div className="grid gap-2 text-sm text-slate-300 md:grid-cols-2 lg:grid-cols-4">
                      <p><span className="text-slate-500">Org ID:</span> {user.organization_id || "-"}</p>
                      <p><span className="text-slate-500">User ID:</span> {user.user_id || "-"}</p>
                      <p><span className="text-slate-500">Status:</span> {user.subscription_status || "-"}</p>
                      <p><span className="text-slate-500">Expires:</span> {compactDate(user.beta_expires_at)}</p>
                      <p><span className="text-slate-500">Last Login:</span> {cleanDate(user.last_login_at)}</p>
                      <p><span className="text-slate-500">Registered:</span> {cleanDate(user.registered_at)}</p>
                      <p><span className="text-slate-500">Feedback:</span> {user.feedback_count || 0}</p>
                      <p><span className="text-slate-500">Users Allowed:</span> {user.user_limit || "-"}</p>
                    </div>
                  </div>

                  <div className="flex flex-col gap-2 lg:min-w-48">
                    <div className={`rounded-xl border px-4 py-3 text-center text-sm font-black ${usageTone(user.uploads_used, user.upload_limit)}`}>
                      Uploads: {usageLabel(user.uploads_used, user.upload_limit)}
                    </div>

                    <button
                      onClick={() => router.push("/platform-admin/beta-feedback")}
                      className="rounded-xl border border-orange-400/30 px-4 py-2 text-sm font-bold text-orange-200 hover:bg-orange-400/10"
                    >
                      View Feedback
                    </button>
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}

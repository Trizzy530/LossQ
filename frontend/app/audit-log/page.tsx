"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_URL || "https://lossq-production.up.railway.app";

type AuditEvent = {
  id?: number | string;
  action?: string;
  resource_type?: string;
  resource_id?: string;
  details?: any;
  created_at?: string;
  timestamp?: string;
  uploaded_at?: string;
  user_email?: string;
  email?: string;
  actor_email?: string;
};

async function safeJson(res: Response) {
  try {
    return await res.json();
  } catch {
    return null;
  }
}

function formatDetails(details: any) {
  if (!details) return "-";
  if (typeof details === "string") return details;
  try {
    return JSON.stringify(details, null, 2);
  } catch {
    return String(details);
  }
}

function normalizeEvents(data: any): AuditEvent[] {
  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.events)) return data.events;
  if (Array.isArray(data?.audit_events)) return data.audit_events;
  if (Array.isArray(data?.logs)) return data.logs;
  if (Array.isArray(data?.items)) return data.items;
  return [];
}

export default function AuditLogPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [events, setEvents] = useState<AuditEvent[]>([]);

  function getToken() {
    if (typeof window === "undefined") return null;
    return localStorage.getItem("lossq_token");
  }

  function logout() {
    localStorage.removeItem("lossq_token");
    localStorage.removeItem("lossq_user");
    localStorage.removeItem("lossq_login_time");
    sessionStorage.removeItem("lossq_welcome");
    router.replace("/login?fresh=1");
  }

  async function loadAuditLog() {
    setLoading(true);
    setError("");
    setMessage("");

    const token = getToken();
    if (!token) {
      router.replace("/login?fresh=1");
      return;
    }

    const headers = { Authorization: `Bearer ${token}` };

    // Try the most likely backend audit-log route names without breaking the page if one is not live yet.
    const candidatePaths = [
      "/audit/events",
      "/audit/logs",
      "/audit-log",
      "/auth/audit-log",
    ];

    for (const path of candidatePaths) {
      try {
        const res = await fetch(`${API}${path}`, { headers });

        if (res.status === 401) {
          logout();
          return;
        }

        if (res.status === 403) {
          setError("You do not have permission to view the audit log.");
          setLoading(false);
          return;
        }

        if (res.ok) {
          const data = await safeJson(res);
          const normalized = normalizeEvents(data);
          setEvents(normalized);
          setMessage(`Audit log loaded from ${path}.`);
          setLoading(false);
          return;
        }
      } catch {
        // Try the next possible endpoint.
      }
    }

    setEvents([]);
    setMessage("Audit log page is active. Backend audit log endpoint is not connected yet, so no events were returned.");
    setLoading(false);
  }

  useEffect(() => {
    loadAuditLog();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (loading) {
    return (
      <main className="min-h-screen bg-[#020617] text-white flex items-center justify-center px-6">
        <div className="text-center">
          <div className="text-4xl font-black mb-3">Loss<span className="text-blue-400">Q</span></div>
          <p className="text-slate-400">Loading audit log...</p>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#020617] text-white px-5 py-8">
      <div className="fixed inset-0 bg-[radial-gradient(circle_at_top_left,#1d4ed855,transparent_30%),radial-gradient(circle_at_bottom_right,#7c3aed33,transparent_32%)] pointer-events-none" />
      <div className="fixed inset-0 bg-[linear-gradient(to_right,rgba(255,255,255,0.04)_1px,transparent_1px),linear-gradient(to_bottom,rgba(255,255,255,0.04)_1px,transparent_1px)] bg-[size:72px_72px] opacity-20 pointer-events-none" />

      <section className="relative max-w-7xl mx-auto">
        <header className="flex flex-col gap-5 md:flex-row md:items-center md:justify-between mb-8">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-blue-400/30 bg-blue-500/10 px-4 py-2 text-sm text-blue-200 mb-4">
              <span className="h-2 w-2 rounded-full bg-blue-400 shadow-[0_0_18px_#60a5fa]" />
              Security Activity
            </div>
            <h1 className="text-4xl md:text-5xl font-black tracking-tight">Audit Log</h1>
            <p className="text-slate-300 mt-3 max-w-2xl">
              Review account activity, uploads, user-management changes, security events, and report actions.
            </p>
          </div>

          <div className="flex flex-wrap gap-3">
            <a href="/settings" className="rounded-xl border border-white/10 px-5 py-3 font-semibold text-slate-200 hover:bg-white/10">
              Back to Settings
            </a>
            <a href="/dashboard" className="rounded-xl border border-white/10 px-5 py-3 font-semibold text-slate-200 hover:bg-white/10">
              Dashboard
            </a>
            <button onClick={logout} className="rounded-xl border border-red-400/30 bg-red-500/10 px-5 py-3 font-semibold text-red-200 hover:bg-red-500/20">
              Logout
            </button>
          </div>
        </header>

        {message && (
          <div className="mb-6 rounded-2xl border border-blue-400/30 bg-blue-500/10 p-4 text-blue-100">
            {message}
          </div>
        )}

        {error && (
          <div className="mb-6 rounded-2xl border border-red-400/30 bg-red-500/10 p-4 text-red-100">
            {error}
          </div>
        )}

        <section className="rounded-3xl border border-white/10 bg-slate-950/75 p-6 backdrop-blur-xl">
          <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between mb-6">
            <div>
              <h2 className="text-2xl font-bold">Recent Activity</h2>
              <p className="text-sm text-slate-400 mt-2">
                Events appear here when the backend audit endpoint is connected and returns activity records.
              </p>
            </div>
            <button onClick={loadAuditLog} className="rounded-xl border border-white/10 px-4 py-2 text-sm font-semibold text-slate-200 hover:bg-white/10">
              Refresh
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full min-w-[950px] text-sm">
              <thead>
                <tr className="border-b border-white/10 text-left text-slate-300">
                  <th className="py-3 pr-4">Time</th>
                  <th className="py-3 pr-4">User</th>
                  <th className="py-3 pr-4">Action</th>
                  <th className="py-3 pr-4">Resource</th>
                  <th className="py-3 pr-4">Details</th>
                </tr>
              </thead>
              <tbody>
                {events.length === 0 ? (
                  <tr className="border-b border-white/10 text-slate-400">
                    <td className="py-6 text-center" colSpan={5}>
                      No audit events found yet.
                    </td>
                  </tr>
                ) : (
                  events.map((event, index) => (
                    <tr key={event.id || index} className="border-b border-white/10 text-slate-200 align-top">
                      <td className="py-4 pr-4 whitespace-nowrap">{event.created_at || event.timestamp || event.uploaded_at || "-"}</td>
                      <td className="py-4 pr-4 break-all">{event.user_email || event.actor_email || event.email || "-"}</td>
                      <td className="py-4 pr-4 font-semibold text-blue-200">{event.action || "-"}</td>
                      <td className="py-4 pr-4">{event.resource_type || "-"}{event.resource_id ? ` / ${event.resource_id}` : ""}</td>
                      <td className="py-4 pr-4">
                        <pre className="max-w-xl whitespace-pre-wrap rounded-2xl border border-white/10 bg-slate-900/70 p-3 text-xs text-slate-300">
                          {formatDetails(event.details)}
                        </pre>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>
      </section>
    </main>
  );
}

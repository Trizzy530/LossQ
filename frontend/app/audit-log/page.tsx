"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

const API =
  process.env.NEXT_PUBLIC_API_URL || "https://lossq-production.up.railway.app";

type AuditEvent = {
  id?: string | number;
  created_at?: string;
  timestamp?: string;
  user_email?: string;
  actor_email?: string;
  action?: string;
  resource_type?: string;
  resource_id?: string;
  details?: any;
};

type AuditSummary = {
  total_events?: number;
  uploads?: number;
  claims?: number;
  users?: number;
  exports?: number;
  last_event_at?: string;
  [key: string]: any;
};

function getToken() {
  if (typeof window === "undefined") return "";
  return (
    localStorage.getItem("lossq_token") ||
    localStorage.getItem("token") ||
    localStorage.getItem("access_token") ||
    ""
  );
}

function formatDate(value?: string) {
  if (!value) return "—";

  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function prettyAction(action?: string) {
  if (!action) return "Audit Event";

  return action
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function safeDetails(details: any) {
  if (!details) return "—";

  if (typeof details === "string") return details;

  try {
    return JSON.stringify(details, null, 2);
  } catch {
    return String(details);
  }
}

export default function AuditLogPage() {
  const router = useRouter();

  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [summary, setSummary] = useState<AuditSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [source, setSource] = useState("");

  const totalEvents = useMemo(() => {
    if (summary?.total_events !== undefined) return summary.total_events;
    return events.length;
  }, [summary, events]);

  async function fetchJson(path: string) {
    const token = getToken();

    const response = await fetch(`${API}${path}`, {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      cache: "no-store",
    });

    if (!response.ok) {
      const body = await response.text().catch(() => "");
      throw new Error(`${path} failed: ${response.status} ${body}`);
    }

    return response.json();
  }

  async function loadAuditLog() {
    setLoading(true);
    setError("");

    try {
      /*
        IMPORTANT:
        Your live Swagger shows these backend routes:
        - GET /audit-logs/
        - GET /audit-logs/summary

        The previous frontend was checking:
        - /audit/events
        - /audit/logs
        - /audit-log
        - /auth/audit-log

        This page now uses the live backend routes shown in Swagger.
      */

      const [eventsPayload, summaryPayload] = await Promise.allSettled([
        fetchJson("/audit-logs/"),
        fetchJson("/audit-logs/summary"),
      ]);

      if (eventsPayload.status === "fulfilled") {
        const data = eventsPayload.value;
        const nextEvents = Array.isArray(data)
          ? data
          : Array.isArray(data.events)
          ? data.events
          : Array.isArray(data.audit_logs)
          ? data.audit_logs
          : Array.isArray(data.logs)
          ? data.logs
          : [];

        setEvents(nextEvents);
        setSource(data.source || "audit-logs");
      } else {
        throw eventsPayload.reason;
      }

      if (summaryPayload.status === "fulfilled") {
        setSummary(summaryPayload.value);
      } else {
        setSummary(null);
      }
    } catch (err: any) {
      setError(err?.message || "Audit log could not be loaded.");
      setEvents([]);
      setSummary(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const token = getToken();

    if (!token) {
      router.push("/login");
      return;
    }

    loadAuditLog();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <main className="min-h-screen bg-[#050816] text-white">
      <header className="border-b border-white/10 bg-black/30 px-6 py-5 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <button
            onClick={() => router.push("/settings")}
            className="mb-4 rounded-xl border border-white/10 px-4 py-2 text-sm text-slate-300 hover:bg-white/10"
          >
            ← Back to Settings
          </button>
          <h1 className="text-4xl font-black tracking-tight">Audit Log</h1>
          <p className="text-slate-400 mt-2">
            Organization activity, uploads, user actions, exports, and system records.
          </p>
        </div>

        <button
          onClick={loadAuditLog}
          className="rounded-xl bg-blue-600 px-5 py-3 font-bold hover:bg-blue-500"
        >
          Refresh
        </button>
      </header>

      <section className="p-6 max-w-7xl mx-auto grid gap-6">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-5">
            <p className="text-sm text-slate-400">Total Events</p>
            <p className="text-3xl font-black mt-2">{totalEvents}</p>
          </div>

          <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-5">
            <p className="text-sm text-slate-400">Uploads</p>
            <p className="text-3xl font-black mt-2">{summary?.uploads ?? "—"}</p>
          </div>

          <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-5">
            <p className="text-sm text-slate-400">Claims</p>
            <p className="text-3xl font-black mt-2">{summary?.claims ?? "—"}</p>
          </div>

          <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-5">
            <p className="text-sm text-slate-400">Source</p>
            <p className="text-lg font-black mt-2">{source || "audit-logs"}</p>
          </div>
        </div>

        {loading && (
          <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-8 text-center">
            <p className="text-slate-300">Loading audit log...</p>
          </div>
        )}

        {!loading && error && (
          <div className="rounded-2xl border border-red-500/30 bg-red-500/10 p-6">
            <h2 className="text-xl font-black text-red-200">Audit Log Error</h2>
            <p className="text-red-100 mt-2 whitespace-pre-wrap">{error}</p>
            <p className="text-sm text-red-100/80 mt-4">
              The frontend is now pointed to the live Swagger routes: /audit-logs/ and /audit-logs/summary.
            </p>
          </div>
        )}

        {!loading && !error && events.length === 0 && (
          <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-8 text-center">
            <h2 className="text-2xl font-black">No audit events yet</h2>
            <p className="text-slate-400 mt-2">
              Upload a loss run or perform an account action, then refresh this page.
            </p>
          </div>
        )}

        {!loading && !error && events.length > 0 && (
          <div className="rounded-2xl border border-white/10 bg-white/[0.04] overflow-hidden">
            <div className="p-5 border-b border-white/10">
              <h2 className="text-2xl font-black">Recent Activity</h2>
              <p className="text-slate-400 text-sm mt-1">
                Showing the latest organization audit records.
              </p>
            </div>

            <div className="overflow-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-white/[0.04] text-slate-300">
                  <tr>
                    <th className="px-5 py-4">Time</th>
                    <th className="px-5 py-4">Action</th>
                    <th className="px-5 py-4">User</th>
                    <th className="px-5 py-4">Resource</th>
                    <th className="px-5 py-4">Details</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((event, index) => (
                    <tr
                      key={`${event.id || "event"}-${index}`}
                      className="border-t border-white/10 align-top"
                    >
                      <td className="px-5 py-4 text-slate-300 whitespace-nowrap">
                        {formatDate(event.created_at || event.timestamp)}
                      </td>
                      <td className="px-5 py-4 font-bold">
                        {prettyAction(event.action)}
                      </td>
                      <td className="px-5 py-4 text-slate-300">
                        {event.user_email || event.actor_email || "—"}
                      </td>
                      <td className="px-5 py-4 text-slate-300">
                        <div>{event.resource_type || "—"}</div>
                        <div className="text-xs text-slate-500">
                          {event.resource_id || ""}
                        </div>
                      </td>
                      <td className="px-5 py-4">
                        <pre className="max-w-xl whitespace-pre-wrap rounded-xl bg-black/30 p-3 text-xs text-slate-300">
                          {safeDetails(event.details)}
                        </pre>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>
    </main>
  );
}

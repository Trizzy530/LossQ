"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

type AuditLog = {
  id: number;
  organization_id: number | null;
  user_id: number | null;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  details: string | null;
  ip_address: string | null;
  user_agent: string | null;
  created_at: string;
};

type AuditSummary = {
  recent_event_count: number;
  actions: Record<string, number>;
};

const API =
  process.env.NEXT_PUBLIC_API_URL ||
  "https://lossq-production.up.railway.app";

function formatAction(action: string) {
  return action
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatDate(value: string) {
  if (!value) return "-";

  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function parseDetails(details: string | null) {
  if (!details) return "-";

  try {
    const parsed = JSON.parse(details);

    if (typeof parsed !== "object" || parsed === null) {
      return String(details);
    }

    const importantFields = [
      "report_type",
      "policy_number",
      "business_name",
      "renewal_score",
      "risk_level",
      "claim_count",
      "total_incurred",
      "saved_claims",
      "duplicates_skipped",
    ];

    const lines = importantFields
      .filter((key) => parsed[key] !== undefined && parsed[key] !== null)
      .map((key) => `${key.replaceAll("_", " ")}: ${parsed[key]}`);

    return lines.length > 0 ? lines.join(" | ") : JSON.stringify(parsed);
  } catch {
    return details;
  }
}

export default function AuditLogsPage() {
  const router = useRouter();

  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [summary, setSummary] = useState<AuditSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("Loading audit logs...");
  const [actionFilter, setActionFilter] = useState("");
  const [resourceFilter, setResourceFilter] = useState("");

  function getToken() {
    if (typeof window === "undefined") return "";
    return localStorage.getItem("lossq_token") || "";
  }

  function authHeaders() {
    const token = getToken();

    return {
      Authorization: `Bearer ${token}`,
      Accept: "application/json",
    };
  }

  function clearSession() {
    localStorage.removeItem("lossq_token");
    localStorage.removeItem("lossq_user");
  }

  async function loadAuditLogs() {
    try {
      setLoading(true);
      setMessage("Loading audit logs...");

      const params = new URLSearchParams();

      if (actionFilter) {
        params.set("action", actionFilter);
      }

      if (resourceFilter) {
        params.set("resource_type", resourceFilter);
      }

      params.set("limit", "100");

      const [summaryRes, logsRes] = await Promise.all([
        fetch(`${API}/audit-logs/summary`, {
          headers: authHeaders(),
        }),
        fetch(`${API}/audit-logs/?${params.toString()}`, {
          headers: authHeaders(),
        }),
      ]);

      if (
        summaryRes.status === 401 ||
        summaryRes.status === 403 ||
        logsRes.status === 401 ||
        logsRes.status === 403
      ) {
        clearSession();
        router.replace("/login?expired=1");
        return;
      }

      const summaryData = await summaryRes.json();
      const logsData = await logsRes.json();

      if (!summaryRes.ok || !logsRes.ok) {
        setMessage(
          `Could not load audit logs. Backend returned ${summaryRes.status}/${logsRes.status}.`
        );
        return;
      }

      setSummary(summaryData);
      setLogs(logsData?.audit_logs || []);
      setMessage("Audit logs loaded.");
    } catch (error: any) {
      setMessage(
        `Could not load audit logs. Error: ${error?.message || "Unknown error"}`
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const token = getToken();

    if (!token) {
      router.replace("/login?expired=1");
      return;
    }

    loadAuditLogs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const actionOptions = useMemo(() => {
    const actions = new Set<string>();

    logs.forEach((log) => {
      if (log.action) actions.add(log.action);
    });

    if (summary?.actions) {
      Object.keys(summary.actions).forEach((action) => actions.add(action));
    }

    return Array.from(actions).sort();
  }, [logs, summary]);

  const resourceOptions = useMemo(() => {
    const resources = new Set<string>();

    logs.forEach((log) => {
      if (log.resource_type) resources.add(log.resource_type);
    });

    return Array.from(resources).sort();
  }, [logs]);

  return (
    <main className="min-h-screen bg-[#050816] text-white">
      <header className="border-b border-white/10 bg-black/30 px-6 py-5">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.35em] text-blue-300">
              LossQ Admin
            </p>
            <h1 className="mt-2 text-3xl font-bold">
              Audit Logs
            </h1>
            <p className="mt-1 text-sm text-slate-400">
              Security, compliance, upload, and report activity tracking.
            </p>
          </div>

          <div className="flex gap-3">
            <button
              onClick={() => router.push("/dashboard")}
              className="rounded-xl border border-white/10 px-4 py-2 text-sm text-slate-200 hover:bg-white/10"
            >
              Back to Dashboard
            </button>

            <button
              onClick={loadAuditLogs}
              className="rounded-xl bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-500"
            >
              Refresh
            </button>
          </div>
        </div>
      </header>

      <section className="mx-auto grid max-w-7xl gap-6 p-6">
        <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-5 shadow-2xl">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="text-xl font-semibold">
                Audit Overview
              </h2>
              <p className="mt-1 text-sm text-slate-400">
                {message}
              </p>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div className="rounded-2xl border border-white/10 bg-black/30 p-4">
                <p className="text-xs uppercase tracking-widest text-slate-400">
                  Recent Events
                </p>
                <p className="mt-2 text-3xl font-bold">
                  {summary?.recent_event_count ?? logs.length}
                </p>
              </div>

              <div className="rounded-2xl border border-white/10 bg-black/30 p-4">
                <p className="text-xs uppercase tracking-widest text-slate-400">
                  Report Events
                </p>
                <p className="mt-2 text-3xl font-bold">
                  {(summary?.actions?.executive_report_generated || 0) +
                    (summary?.actions?.carrier_packet_generated || 0)}
                </p>
              </div>

              <div className="rounded-2xl border border-white/10 bg-black/30 p-4">
                <p className="text-xs uppercase tracking-widest text-slate-400">
                  Upload Events
                </p>
                <p className="mt-2 text-3xl font-bold">
                  {summary?.actions?.loss_run_uploaded || 0}
                </p>
              </div>
            </div>
          </div>
        </div>

        <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-5">
          <div className="grid gap-4 md:grid-cols-3">
            <div>
              <label className="text-xs uppercase tracking-widest text-slate-400">
                Action Filter
              </label>
              <select
                value={actionFilter}
                onChange={(event) => setActionFilter(event.target.value)}
                className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-3 py-2 text-sm text-white"
              >
                <option value="">All Actions</option>
                {actionOptions.map((action) => (
                  <option key={action} value={action}>
                    {formatAction(action)}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-xs uppercase tracking-widest text-slate-400">
                Resource Type
              </label>
              <select
                value={resourceFilter}
                onChange={(event) => setResourceFilter(event.target.value)}
                className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-3 py-2 text-sm text-white"
              >
                <option value="">All Resources</option>
                {resourceOptions.map((resource) => (
                  <option key={resource} value={resource}>
                    {formatAction(resource)}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex items-end">
              <button
                onClick={loadAuditLogs}
                className="w-full rounded-xl bg-white px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-slate-200"
              >
                Apply Filters
              </button>
            </div>
          </div>
        </div>

        <div className="overflow-hidden rounded-3xl border border-white/10 bg-white/[0.04] shadow-2xl">
          <div className="border-b border-white/10 px-5 py-4">
            <h2 className="text-xl font-semibold">
              Recent Audit Events
            </h2>
            <p className="mt-1 text-sm text-slate-400">
              Shows the latest activity for your organization.
            </p>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full min-w-[1100px] border-collapse text-left text-sm">
              <thead className="bg-slate-950 text-xs uppercase tracking-widest text-slate-400">
                <tr>
                  <th className="px-4 py-3">Time</th>
                  <th className="px-4 py-3">Action</th>
                  <th className="px-4 py-3">Resource</th>
                  <th className="px-4 py-3">Resource ID</th>
                  <th className="px-4 py-3">User ID</th>
                  <th className="px-4 py-3">Details</th>
                  <th className="px-4 py-3">IP Address</th>
                </tr>
              </thead>

              <tbody>
                {loading ? (
                  <tr>
                    <td
                      colSpan={7}
                      className="px-4 py-8 text-center text-slate-400"
                    >
                      Loading audit logs...
                    </td>
                  </tr>
                ) : logs.length === 0 ? (
                  <tr>
                    <td
                      colSpan={7}
                      className="px-4 py-8 text-center text-slate-400"
                    >
                      No audit logs found yet. Generate a report or upload a
                      loss run to create audit activity.
                    </td>
                  </tr>
                ) : (
                  logs.map((log) => (
                    <tr
                      key={log.id}
                      className="border-t border-white/10 hover:bg-white/[0.03]"
                    >
                      <td className="whitespace-nowrap px-4 py-3 text-slate-300">
                        {formatDate(log.created_at)}
                      </td>

                      <td className="px-4 py-3">
                        <span className="rounded-full bg-blue-500/15 px-3 py-1 text-xs font-semibold text-blue-300">
                          {formatAction(log.action)}
                        </span>
                      </td>

                      <td className="px-4 py-3 text-slate-300">
                        {log.resource_type || "-"}
                      </td>

                      <td className="px-4 py-3 text-slate-300">
                        {log.resource_id || "-"}
                      </td>

                      <td className="px-4 py-3 text-slate-300">
                        {log.user_id || "-"}
                      </td>

                      <td className="max-w-[420px] px-4 py-3 text-slate-300">
                        {parseDetails(log.details)}
                      </td>

                      <td className="px-4 py-3 text-slate-400">
                        {log.ip_address || "-"}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </main>
  );
}
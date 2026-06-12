"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

const API =
  process.env.NEXT_PUBLIC_API_URL || "https://lossq-production.up.railway.app";

type AuditEvent = {
  id?: string | number;
  created_at?: string;
  timestamp?: string;
  user_id?: string | number;
  user_email?: string;
  user_full_name?: string;
  actor_email?: string;
  actor_name?: string;
  user_name?: string;
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
  source?: string;
  [key: string]: any;
};

type ActionTone = "blue" | "emerald" | "purple" | "amber" | "rose" | "slate";

function getToken() {
  if (typeof window === "undefined") return "";
  return (
    localStorage.getItem("lossq_token") ||
    localStorage.getItem("token") ||
    localStorage.getItem("access_token") ||
    ""
  );
}

function decodeJwtPayload(token: string) {
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;

    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const decoded = JSON.parse(window.atob(normalized));

    return decoded;
  } catch {
    return null;
  }
}

function getCurrentUserEmail() {
  if (typeof window === "undefined") return "";

  const token = getToken();
  const payload = decodeJwtPayload(token);

  return (
    payload?.email ||
    payload?.sub ||
    payload?.user_email ||
    localStorage.getItem("lossq_user_email") ||
    localStorage.getItem("user_email") ||
    ""
  );
}

function parseAuditDate(value?: string) {
  if (!value) return null;

  const clean = String(value).trim();

  if (!clean) return null;

  const hasTimezone = /([zZ]|[+-]\d{2}:?\d{2})$/.test(clean);
  const normalized = hasTimezone ? clean : `${clean}Z`;
  const date = new Date(normalized);

  if (Number.isNaN(date.getTime())) return null;

  return date;
}

function formatDate(value?: string) {
  const date = parseAuditDate(value);

  if (!date) return value || "";

  try {
    return new Intl.DateTimeFormat("en-US", {
      timeZone: "America/New_York",
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
      second: "2-digit",
      timeZoneName: "short",
    }).format(date);
  } catch {
    return value || "";
  }
}

function formatCurrency(value: any) {
  const num = Number(value || 0);

  if (!Number.isFinite(num)) return "";

  return num.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });
}

function formatNumber(value: any) {
  if (value === null || value === undefined || value === "") return "";

  const num = Number(value);

  if (!Number.isFinite(num)) return String(value);

  return num.toLocaleString();
}

function prettyAction(action?: string) {
  const clean = String(action || "").trim();

  const labels: Record<string, string> = {
    loss_run_uploaded: "Loss Run Uploaded",
    claim_record_saved: "Claim Saved",
    executive_report_generated: "Executive Report Generated",
    carrier_packet_generated: "Carrier Packet Generated",
    renewal_memo_generated: "Renewal Memo Generated",
    user_login: "User Login",
    user_logout: "User Logout",
    audit_event: "Audit Event",
  };

  if (labels[clean]) return labels[clean];

  if (!clean) return "Audit Event";

  return clean
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function sourceLabel(source?: string) {
  const clean = String(source || "").trim();

  const labels: Record<string, string> = {
    audit_logs_with_claims: "Audit + Claims",
    audit_logs: "Audit Logs",
    existing_uploads: "Upload History",
    safe_error_payload: "Safe Error Payload",
    no_events_found: "No Events Found",
  };

  return labels[clean] || prettyAction(clean || "audit-logs");
}

function toDetails(details: any) {
  if (!details) return {};

  if (typeof details === "string") {
    try {
      return JSON.parse(details);
    } catch {
      return { note: details };
    }
  }

  if (typeof details === "object") return details;

  return { value: String(details) };
}

function cleanDisplayText(value: any) {
  if (value === null || value === undefined || value === "") return "-";

  return String(value)
    .replace(/\u00e2\u20ac\u201d/g, "-")
    .replace(/\u00e2\u20ac\u201c/g, "-")
    .replace(/\u00e2\u20ac\u0153/g, '"')
    .replace(/\u00e2\u20ac\ufffd/g, '"')
    .replace(/\u00e2\u20ac\u009d/g, '"')
    .replace(/\u00e2\u20ac\u2122/g, "'")
    .replace(/\u00e2\u20ac\u02dc/g, "'")
    .replace(/\u00e2\u20ac\u00a2/g, "")
    .replace(/\u00e2\u20ac\u00a6/g, "...")
    .replace(/\u00e2\u2020\u0090/g, "<-")
    .replace(/\u00e2\u2020\u2019/g, "->")
    .replace(/\u00c2/g, "");
}

function safeText(value: any) {
  return cleanDisplayText(value);
}

function eventTime(event: AuditEvent) {
  return event.created_at || event.timestamp || "";
}

function optionalDisplayText(value: any) {
  if (value === null || value === undefined || value === "") return "";
  const clean = cleanDisplayText(value).trim();
  return clean === "-" ? "" : clean;
}

function eventUserName(event: AuditEvent) {
  const details = toDetails(event.details);

  return optionalDisplayText(
    event.user_full_name ||
      event.actor_name ||
      event.user_name ||
      details.user_full_name ||
      details.actor_name ||
      details.user_name
  );
}

function eventUserEmail(event: AuditEvent, fallbackEmail = "") {
  const details = toDetails(event.details);

  return optionalDisplayText(
    event.user_email ||
      event.actor_email ||
      details.user_email ||
      details.actor_email ||
      fallbackEmail
  );
}

function resourceLabel(event: AuditEvent) {
  const type = String(event.resource_type || "system").toLowerCase();

  if (type === "upload") return "Upload";
  if (type === "claim") return "Claim";
  if (type === "report") return "Report";
  if (type === "user") return "User";

  return prettyAction(type);
}

function actionTone(event: AuditEvent): ActionTone {
  const action = String(event.action || "").toLowerCase();
  const resource = String(event.resource_type || "").toLowerCase();

  if (resource === "claim" || action.includes("claim")) return "emerald";
  if (resource === "report" || action.includes("report") || action.includes("packet") || action.includes("memo")) return "purple";
  if (resource === "upload" || action.includes("upload")) return "blue";
  if (action.includes("error") || action.includes("failed")) return "rose";
  if (action.includes("review") || action.includes("warning")) return "amber";

  return "slate";
}

function toneClasses(tone: ActionTone) {
  const map: Record<ActionTone, string> = {
    blue: "border-blue-400/30 bg-blue-500/10 text-blue-200",
    emerald: "border-emerald-400/30 bg-emerald-500/10 text-emerald-200",
    purple: "border-purple-400/30 bg-purple-500/10 text-purple-200",
    amber: "border-amber-400/30 bg-amber-500/10 text-amber-200",
    rose: "border-rose-400/30 bg-rose-500/10 text-rose-200",
    slate: "border-slate-400/30 bg-slate-500/10 text-slate-200",
  };

  return map[tone];
}

function statusTone(value: any) {
  const clean = String(value || "").toLowerCase();

  if (clean.includes("passed") || clean.includes("good") || clean.includes("clean") || clean.includes("low")) {
    return "border-emerald-400/30 bg-emerald-500/10 text-emerald-200";
  }

  if (clean.includes("review") || clean.includes("medium") || clean.includes("moderate")) {
    return "border-amber-400/30 bg-amber-500/10 text-amber-200";
  }

  if (clean.includes("failed") || clean.includes("critical") || clean.includes("high")) {
    return "border-rose-400/30 bg-rose-500/10 text-rose-200";
  }

  return "border-slate-400/30 bg-slate-500/10 text-slate-200";
}

function DetailPill({
  label,
  value,
  tone = "slate",
}: {
  label: string;
  value: any;
  tone?: ActionTone;
}) {
  return (
    <div className={`min-w-0 rounded-xl border px-3 py-2 ${toneClasses(tone)}`}>
      <p className="text-[10px] uppercase tracking-[0.2em] opacity-70">{label}</p>
      <p className="mt-1 min-w-0 break-words text-sm font-bold leading-relaxed">{safeText(value)}</p>
    </div>
  );
}

function StatusPill({ label, value }: { label: string; value: any }) {
  return (
    <div className={`min-w-0 rounded-xl border px-3 py-2 ${statusTone(value)}`}>
      <p className="text-[10px] uppercase tracking-[0.2em] opacity-70">{label}</p>
      <p className="mt-1 min-w-0 break-words text-sm font-bold leading-relaxed">{safeText(value)}</p>
    </div>
  );
}

function RawDetailsButton({ details }: { details: any }) {
  const cleanDetails = toDetails(details);

  return (
    <details className="mt-3 rounded-xl border border-white/10 bg-black/20">
      <summary className="cursor-pointer px-3 py-2 text-xs font-bold text-slate-300 hover:text-white">
        View technical details
      </summary>
      <pre className="max-h-72 overflow-auto whitespace-pre-wrap border-t border-white/10 p-3 text-xs text-slate-400">
        {JSON.stringify(cleanDetails, null, 2)}
      </pre>
    </details>
  );
}

function EventDetails({ event }: { event: AuditEvent }) {
  const details = toDetails(event.details);
  const validation = toDetails(details.validation);
  const reported = toDetails(validation.reported_totals);
  const extracted = toDetails(validation.extracted_totals);
  const uploadedFile = Array.isArray(details.uploaded_files)
    ? details.uploaded_files[0]
    : null;

  const resource = String(event.resource_type || "").toLowerCase();
  const action = String(event.action || "").toLowerCase();

  if (resource === "claim" || action.includes("claim")) {
    return (
      <div className="space-y-3">
        <div className="grid grid-cols-1 gap-2 md:grid-cols-3 [&>*]:min-w-0">
          <DetailPill label="Claim Number" value={details.claim_number || event.resource_id} tone="emerald" />
          <DetailPill label="Policy Number" value={details.policy_number} />
          <StatusPill label="Status" value={details.status} />
          <DetailPill label="Line of Business" value={details.line_of_business} />
          <DetailPill label="Paid" value={formatCurrency(details.paid_amount)} />
          <DetailPill label="Reserve" value={formatCurrency(details.reserve_amount)} />
          <DetailPill label="Total Incurred" value={formatCurrency(details.total_incurred)} tone="emerald" />
        </div>
        <RawDetailsButton details={details} />
      </div>
    );
  }

  if (resource === "report" || action.includes("report") || action.includes("packet") || action.includes("memo")) {
    return (
      <div className="space-y-3">
        <div className="grid grid-cols-1 gap-2 md:grid-cols-3 [&>*]:min-w-0">
          <DetailPill label="Report Type" value={prettyAction(details.report_type)} tone="purple" />
          <DetailPill label="Policy Number" value={details.policy_number || event.resource_id} />
          <DetailPill label="Business" value={details.business_name} />
          <StatusPill label="Risk Level" value={details.risk_level} />
          <DetailPill label="Renewal Score" value={details.renewal_score ?? ""} tone="purple" />
          <DetailPill label="Claim Count" value={formatNumber(details.claim_count)} />
          <DetailPill label="Total Incurred" value={formatCurrency(details.total_incurred)} />
        </div>
        <RawDetailsButton details={details} />
      </div>
    );
  }

  if (resource === "upload" || action.includes("upload")) {
    const warningCount =
      validation.warning_count ??
      (Array.isArray(validation.warnings) ? validation.warnings.length : undefined);

    return (
      <div className="space-y-3">
        <div className="grid grid-cols-1 gap-2 md:grid-cols-3 [&>*]:min-w-0">
          <DetailPill
            label="File"
            value={uploadedFile?.filename || details.filename || "Loss run upload"}
            tone="blue"
          />
          <DetailPill label="Policy Number" value={details.policy_number || event.resource_id} />
          <DetailPill label="Account Number" value={details.account_number} />
          <DetailPill label="Claims Saved" value={formatNumber(details.saved_claims ?? uploadedFile?.claims_saved)} tone="emerald" />
          <DetailPill label="Duplicates" value={formatNumber(details.duplicates_skipped ?? uploadedFile?.duplicates_skipped)} />
          <DetailPill label="Policy Rows" value={formatNumber(details.policy_count)} />
          <StatusPill label="Financial Validation" value={validation.financial_validation || validation.status} />
          <StatusPill label="Renewal Signal" value={validation.renewal_signal} />
          <StatusPill label="Confidence" value={validation.confidence_level || validation.document_confidence} />
          <DetailPill label="Extracted Claims" value={formatNumber(extracted.total_claims ?? validation.parsed_claim_count)} />
          <DetailPill label="Reported Claims" value={formatNumber(reported.reported_total_claims ?? validation.document_total_claims)} />
          <DetailPill label="Warning Count" value={formatNumber(warningCount)} tone={Number(warningCount || 0) > 0 ? "amber" : "emerald"} />
        </div>

        {Array.isArray(validation.warnings) && validation.warnings.length > 0 && (
          <div className="rounded-xl border border-amber-400/20 bg-amber-500/10 p-3">
            <p className="text-xs font-black uppercase tracking-[0.2em] text-amber-200">Review Notes</p>
            <ul className="mt-2 grid gap-1 text-sm text-amber-100">
              {validation.warnings.slice(0, 4).map((warning: string, index: number) => (
                <li key={`${warning}-${index}`}>- {safeText(warning)}</li>
              ))}
            </ul>
          </div>
        )}

        <RawDetailsButton details={details} />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 gap-2 md:grid-cols-3 [&>*]:min-w-0">
        {Object.entries(details)
          .slice(0, 6)
          .map(([key, value]) => (
            <DetailPill key={key} label={prettyAction(key)} value={typeof value === "object" ? "See details" : value} />
          ))}
      </div>
      <RawDetailsButton details={details} />
    </div>
  );
}

function StatCard({
  label,
  value,
  helper,
  tone = "slate",
}: {
  label: string;
  value: any;
  helper: string;
  tone?: ActionTone;
}) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-5 shadow-2xl shadow-black/20">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm text-slate-400">{label}</p>
          <p className="mt-2 text-3xl font-black tracking-tight">{value}</p>
        </div>
        <div className={`rounded-xl border px-3 py-2 text-xs font-black ${toneClasses(tone)}`}>
          {label.split(" ")[0]}
        </div>
      </div>
      <p className="mt-4 text-xs text-slate-500">{helper}</p>
    </div>
  );
}

export default function AuditLogPage() {
  const router = useRouter();

  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [summary, setSummary] = useState<AuditSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [source, setSource] = useState("");
  const [search, setSearch] = useState("");
  const [resourceFilter, setResourceFilter] = useState("all");
  const [currentUserEmail, setCurrentUserEmail] = useState("");

  const totalEvents = useMemo(() => {
    if (summary?.total_events !== undefined) return summary.total_events;
    return events.length;
  }, [summary, events]);

  const filteredEvents = useMemo(() => {
    const cleanSearch = search.trim().toLowerCase();

    return events.filter((event) => {
      const resource = String(event.resource_type || "").toLowerCase();

      if (resourceFilter !== "all" && resource !== resourceFilter) {
        return false;
      }

      if (!cleanSearch) return true;

      const details = JSON.stringify(toDetails(event.details)).toLowerCase();

      return [
        event.action,
        event.resource_type,
        event.resource_id,
        event.user_full_name,
        event.actor_name,
        event.user_name,
        event.user_email,
        event.actor_email,
        currentUserEmail,
        details,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(cleanSearch);
    });
  }, [events, search, resourceFilter, currentUserEmail]);

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

    if (response.status === 401 || response.status === 403) {
      localStorage.removeItem("lossq_token");
      localStorage.removeItem("token");
      localStorage.removeItem("access_token");
      router.push("/login?expired=1");
      throw new Error("Your session expired. Please log in again.");
    }

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

    setCurrentUserEmail(getCurrentUserEmail());
    loadAuditLog();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <main className="min-h-screen bg-[#050816] text-white">
      <header className="border-b border-white/10 bg-black/30 px-6 py-6">
        <div className="mx-auto flex max-w-7xl flex-col gap-5 md:flex-row md:items-center md:justify-between">
          <div>
            <button
              onClick={() => router.push("/settings")}
              className="mb-4 rounded-xl border border-white/10 px-4 py-2 text-sm text-slate-300 transition hover:bg-white/10 hover:text-white"
            >
             Back to Settings
            </button>
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-4xl font-black tracking-tight">Audit Log</h1>
              <span className="rounded-full border border-blue-400/30 bg-blue-500/10 px-3 py-1 text-xs font-black uppercase tracking-[0.2em] text-blue-200">
                Compliance Console
              </span>
            </div>
            <p className="mt-2 max-w-3xl text-slate-400">
              A clean activity timeline for uploads, derived claim records, reports, exports, and system events.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3">
              <p className="text-[10px] uppercase tracking-[0.2em] text-slate-500">Source</p>
              <p className="text-sm font-black text-slate-100">{sourceLabel(source || summary?.source)}</p>
            </div>
            <button
              onClick={loadAuditLog}
              className="rounded-xl bg-blue-600 px-5 py-3 font-bold shadow-lg shadow-blue-950/40 transition hover:bg-blue-500"
            >
              Refresh
            </button>
          </div>
        </div>
      </header>

      <section className="mx-auto grid max-w-7xl gap-6 p-6">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
          <StatCard
            label="Total Events"
            value={formatNumber(totalEvents)}
            helper="Combined organization activity records."
            tone="slate"
          />
          <StatCard
            label="Uploads"
            value={formatNumber(summary?.uploads ?? "")}
            helper="Loss run uploads and file activity."
            tone="blue"
          />
          <StatCard
            label="Claims"
            value={formatNumber(summary?.claims ?? "")}
            helper="Claim records derived from saved claims."
            tone="emerald"
          />
          <StatCard
            label="Reports"
            value={formatNumber(summary?.exports ?? "")}
            helper="Generated reports, packets, and memos."
            tone="purple"
          />
        </div>

        <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-5">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="text-xl font-black">Activity Filters</h2>
              <p className="mt-1 text-sm text-slate-400">
                Search policy numbers, claim numbers, report names, users, or validation results.
              </p>
            </div>

            <div className="flex flex-col gap-3 md:flex-row">
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search audit activity..."
                className="w-full rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-500 focus:border-blue-400/60 md:w-80"
              />

              <select
                value={resourceFilter}
                onChange={(event) => setResourceFilter(event.target.value)}
                className="rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-sm text-white outline-none focus:border-blue-400/60"
              >
                <option value="all">All Resources</option>
                <option value="upload">Uploads</option>
                <option value="claim">Claims</option>
                <option value="report">Reports</option>
                <option value="user">Users</option>
              </select>
            </div>
          </div>
        </div>

        {loading && (
          <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-10 text-center">
            <div className="mx-auto h-10 w-10 animate-spin rounded-full border-2 border-white/10 border-t-blue-400" />
            <p className="mt-4 text-slate-300">Loading audit activity...</p>
          </div>
        )}

        {!loading && error && (
          <div className="rounded-2xl border border-red-500/30 bg-red-500/10 p-6">
            <h2 className="text-xl font-black text-red-200">Audit Log Error</h2>
            <p className="mt-2 whitespace-pre-wrap text-red-100">{error}</p>
            <button
              onClick={loadAuditLog}
              className="mt-5 rounded-xl bg-red-500 px-4 py-2 text-sm font-bold text-white hover:bg-red-400"
            >
              Retry
            </button>
          </div>
        )}

        {!loading && !error && filteredEvents.length === 0 && (
          <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-10 text-center">
            <h2 className="text-2xl font-black">No matching audit events</h2>
            <p className="mt-2 text-slate-400">
              Clear the search or select a different resource filter.
            </p>
          </div>
        )}

        {!loading && !error && filteredEvents.length > 0 && (
          <div className="rounded-2xl border border-white/10 bg-white/[0.04] shadow-2xl shadow-black/30">
            <div className="border-b border-white/10 p-5">
              <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
                <div>
                  <h2 className="text-2xl font-black">Recent Activity</h2>
                  <p className="mt-1 text-sm text-slate-400">
                    Showing {formatNumber(filteredEvents.length)} of {formatNumber(events.length)} records.
                  </p>
                </div>
                <p className="text-xs text-slate-500">
                  Last event: {formatDate(summary?.last_event_at || eventTime(filteredEvents[0]))}
                </p>
              </div>
            </div>

            <div className="grid divide-y divide-white/10">
              {filteredEvents.map((event, index) => {
                const tone = actionTone(event);
                const userName = eventUserName(event);
                const userEmail = eventUserEmail(event, currentUserEmail);

                return (
                  <article
                    key={`${event.id || "event"}-${index}`}
                    className="grid gap-4 p-5 transition hover:bg-white/[0.03] lg:grid-cols-[220px_1fr]"
                  >
                    <aside className="space-y-3">
                      <div>
                        <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Time</p>
                        <p className="mt-1 text-sm font-bold text-slate-200" title={eventTime(event)}>
                          {formatDate(eventTime(event))}
                        </p>
                      </div>

                      <div>
                        <p className="text-xs uppercase tracking-[0.2em] text-slate-500">User</p>
                        {userName ? (
                          <p className="mt-1 break-words text-sm font-bold text-slate-100">
                            {userName}
                          </p>
                        ) : null}
                        <p className="mt-1 break-all text-sm text-slate-300">
                          {userEmail || "System"}
                        </p>
                      </div>

                      <div>
                        <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Resource ID</p>
                        <p className="mt-1 break-all text-xs text-slate-400">
                          {safeText(event.resource_id)}
                        </p>
                      </div>
                    </aside>

                    <div className="space-y-4">
                      <div className="flex flex-wrap items-center gap-3">
                        <span className={`rounded-full border px-3 py-1 text-xs font-black ${toneClasses(tone)}`}>
                          {resourceLabel(event)}
                        </span>
                        <h3 className="text-xl font-black tracking-tight">
                          {prettyAction(event.action)}
                        </h3>
                      </div>

                      <EventDetails event={event} />
                    </div>
                  </article>
                );
              })}
            </div>
          </div>
        )}
      </section>
    </main>
  );
}






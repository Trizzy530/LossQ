"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

const API =
  process.env.NEXT_PUBLIC_API_URL || "https://lossq-production.up.railway.app";

type AuditEvent = {
  id?: string | number;
  created_at?: string;
  timestamp?: string;
  updated_at?: string;
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
  [key: string]: any;
};

type AuditSummary = {
  total_events?: number;
  uploads?: number;
  claims?: number;
  users?: number;
  exports?: number;
  reports?: number;
  last_event_at?: string;
  source?: string;
  [key: string]: any;
};

type SortOrder = "newest" | "oldest";

type CategoryFilter =
  | "all"
  | "reports"
  | "uploads"
  | "claims"
  | "account_profiles"
  | "users"
  | "billing"
  | "system";

type Tone =
  | "blue"
  | "emerald"
  | "purple"
  | "amber"
  | "rose"
  | "slate"
  | "cyan"
  | "orange";

function getToken() {
  if (typeof window === "undefined") return "";

  return (
    sessionStorage.getItem("lossq_tab_token") ||
    localStorage.getItem("lossq_token") ||
    localStorage.getItem("token") ||
    localStorage.getItem("access_token") ||
    ""
  );
}

function authHeaders() {
  const token = getToken();

  return {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };
}

function normalizePlan(plan: any) {
  const clean = String(plan || "free").trim().toLowerCase();

  if (clean === "founder" || clean === "founding" || clean === "founding agency") {
    return "founding_agency";
  }

  if (clean === "enterprise") return "agency";
  if (clean === "pro") return "professional";

  return clean;
}

function canAccessAuditLogsFromBilling(data: any) {
  const plan = normalizePlan(
    data?.plan ||
      data?.subscription_plan ||
      data?.plan_name ||
      data?.organization?.plan ||
      "free"
  );

  const features = Array.isArray(data?.features)
    ? data.features.map((item: any) => String(item).toLowerCase())
    : [];

  return (
    plan === "agency" ||
    plan === "founding_agency" ||
    features.includes("audit_logs")
  );
}

function toDetails(details: any): Record<string, any> {
  if (!details) return {};

  if (typeof details === "string") {
    try {
      const parsed = JSON.parse(details);
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch {
      return {};
    }
  }

  if (typeof details === "object") return details;

  return {};
}

function cleanText(value: any) {
  if (value === null || value === undefined || value === "") return "-";

  const clean = String(value)
    .replace(/\s+/g, " ")
    .replace(/undefined|null/gi, "")
    .trim();

  return clean || "-";
}

function optionalText(value: any) {
  const clean = cleanText(value);
  return clean === "-" ? "" : clean;
}

function detailValue(event: AuditEvent, ...keys: string[]) {
  const details = toDetails(event.details);

  for (const key of keys) {
    const eventValue = (event as any)?.[key];

    if (eventValue !== undefined && eventValue !== null && eventValue !== "") {
      return eventValue;
    }

    const detail = details?.[key];

    if (detail !== undefined && detail !== null && detail !== "") {
      return detail;
    }
  }

  return "";
}

function eventTime(event: AuditEvent) {
  const details = toDetails(event.details);

  return (
    event.created_at ||
    event.timestamp ||
    event.updated_at ||
    details.created_at ||
    details.generated_at_utc ||
    details.event_timestamp_utc ||
    details.generated_at ||
    details.exported_at ||
    details.submitted_at ||
    details.deleted_at ||
    details.uploaded_at ||
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

  if (Number.isNaN(date.getTime())) {
    const fallback = new Date(clean);
    return Number.isNaN(fallback.getTime()) ? null : fallback;
  }

  return date;
}

function formatDate(value?: string) {
  const date = parseAuditDate(value);

  if (!date) return "-";

  try {
    return new Intl.DateTimeFormat("en-US", {
      timeZone: "America/New_York",
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
      timeZoneName: "short",
    }).format(date);
  } catch {
    return value || "-";
  }
}

function formatCurrency(value: any) {
  if (value === null || value === undefined || value === "") return "-";

  const numeric = Number(String(value).replace(/[$,]/g, ""));

  if (!Number.isFinite(numeric)) return cleanText(value);

  return numeric.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });
}

function formatNumber(value: any) {
  if (value === null || value === undefined || value === "") return "-";

  const numeric = Number(value);

  if (!Number.isFinite(numeric)) return cleanText(value);

  return numeric.toLocaleString("en-US");
}

function prettyAction(action?: string) {
  const clean = String(action || "").trim();

  const labels: Record<string, string> = {
    loss_run_uploaded: "Loss Run Uploaded",
    claim_record_saved: "Claim Saved",
    executive_report_generated: "Executive Report Generated",
    carrier_packet_generated: "Carrier Packet Generated",
    carrier_packet_pdf_generated: "Carrier Packet PDF Generated",
    carrier_packet_pdf_downloaded: "Carrier Packet PDF Downloaded",
    renewal_memo_generated: "Renewal Memo Generated",
    pdf_export_generated: "PDF Export Generated",
    account_profile_deleted: "Account Profile Deleted",
    account_profile_saved: "Account Profile Saved",
    account_profile_updated: "Account Profile Updated",
    profile_deleted: "Account Profile Deleted",
    user_login: "User Login",
    user_logout: "User Logout",
    user_invited: "User Invited",
    user_role_changed: "User Role Changed",
    billing_subscription_updated: "Billing Updated",
    platform_admin_stats_viewed: "Platform Admin Stats Viewed",
    platform_admin_users_viewed: "Platform Admin Users Viewed",
    platform_admin_organizations_viewed: "Platform Admin Organizations Viewed",
    support_lookup_searched: "Support Lookup Searched",
    audit_event: "Audit Event",
  };

  if (labels[clean]) return labels[clean];

  if (!clean) return "Audit Event";

  return clean
    .replace(/_/g, " ")
    .replace(/-/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function resourceLabel(event: AuditEvent) {
  const resource = String(event.resource_type || "").toLowerCase();
  const action = String(event.action || "").toLowerCase();

  if (resource === "report" || action.includes("report") || action.includes("packet") || action.includes("pdf")) {
    return "Report";
  }

  if (resource === "upload" || action.includes("upload") || action.includes("loss_run")) {
    return "Upload";
  }

  if (resource === "claim" || action.includes("claim")) {
    return "Claim";
  }

  if (resource === "account_profile" || action.includes("account_profile") || action.includes("profile")) {
    return "Account Profile";
  }

  if (resource === "billing" || action.includes("billing") || action.includes("subscription") || action.includes("checkout")) {
    return "Billing";
  }

  if (resource === "user" || action.includes("user")) {
    return "User";
  }

  if (resource === "support_lookup" || action.includes("support_lookup")) {
    return "Support";
  }

  return "System";
}

function eventTone(event: AuditEvent): Tone {
  const label = resourceLabel(event).toLowerCase();
  const action = String(event.action || "").toLowerCase();

  if (label === "report") return "purple";
  if (label === "upload") return "blue";
  if (label === "claim") return "emerald";
  if (label === "account profile") return "rose";
  if (label === "billing") return "amber";
  if (label === "user") return "cyan";
  if (label === "support") return "orange";
  if (action.includes("error") || action.includes("failed")) return "rose";

  return "slate";
}

function toneClasses(tone: Tone) {
  const map: Record<Tone, string> = {
    blue: "border-blue-400/30 bg-blue-500/10 text-blue-200",
    emerald: "border-emerald-400/30 bg-emerald-500/10 text-emerald-200",
    purple: "border-purple-400/30 bg-purple-500/10 text-purple-200",
    amber: "border-amber-400/30 bg-amber-500/10 text-amber-200",
    rose: "border-rose-400/30 bg-rose-500/10 text-rose-200",
    slate: "border-slate-400/30 bg-slate-500/10 text-slate-200",
    cyan: "border-cyan-400/30 bg-cyan-500/10 text-cyan-200",
    orange: "border-orange-400/30 bg-orange-500/10 text-orange-200",
  };

  return map[tone];
}

function eventUserName(event: AuditEvent) {
  const details = toDetails(event.details);

  return optionalText(
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

  return optionalText(
    event.user_email ||
      event.actor_email ||
      details.user_email ||
      details.actor_email ||
      fallbackEmail
  );
}

function eventResourceId(event: AuditEvent) {
  return cleanText(
    event.resource_id ||
      detailValue(
        event,
        "resource_id",
        "policy_number",
        "claim_number",
        "profile_id",
        "upload_id",
        "account_number"
      )
  );
}

function matchesCategory(event: AuditEvent, category: CategoryFilter) {
  if (category === "all") return true;

  const label = resourceLabel(event).toLowerCase();
  const action = String(event.action || "").toLowerCase();
  const resource = String(event.resource_type || "").toLowerCase();

  if (category === "reports") {
    return label === "report" || resource === "report" || action.includes("report") || action.includes("packet") || action.includes("pdf") || action.includes("memo");
  }

  if (category === "uploads") {
    return label === "upload" || resource === "upload" || action.includes("upload") || action.includes("loss_run");
  }

  if (category === "claims") {
    return label === "claim" || resource === "claim" || action.includes("claim");
  }

  if (category === "account_profiles") {
    return label === "account profile" || resource === "account_profile" || action.includes("account_profile") || action.includes("profile");
  }

  if (category === "users") {
    return label === "user" || resource === "user" || action.includes("user");
  }

  if (category === "billing") {
    return label === "billing" || resource === "billing" || action.includes("billing") || action.includes("subscription") || action.includes("checkout");
  }

  if (category === "system") {
    return label === "system";
  }

  return true;
}

function eventSearchText(event: AuditEvent) {
  const details = toDetails(event.details);

  return [
    event.action,
    event.resource_type,
    event.resource_id,
    event.user_email,
    event.user_full_name,
    event.actor_email,
    event.actor_name,
    JSON.stringify(details),
  ]
    .join(" ")
    .toLowerCase();
}

function eventTimestampNumber(event: AuditEvent) {
  const raw = eventTime(event);
  const date = parseAuditDate(raw);

  return date ? date.getTime() : 0;
}

function computeSummary(events: AuditEvent[], summary: AuditSummary | null) {
  const uploads = events.filter((event) => matchesCategory(event, "uploads")).length;
  const claims = events.filter((event) => matchesCategory(event, "claims")).length;
  const reports = events.filter((event) => matchesCategory(event, "reports")).length;
  const users = events.filter((event) => matchesCategory(event, "users")).length;

  return {
    total_events: summary?.total_events ?? events.length,
    uploads: summary?.uploads ?? uploads,
    claims: summary?.claims ?? claims,
    reports: summary?.reports ?? summary?.exports ?? reports,
    users: summary?.users ?? users,
    last_event_at: summary?.last_event_at || eventTime(events[0] || {}),
    source: summary?.source || "",
  };
}

function categoryOptions(): { value: CategoryFilter; label: string }[] {
  return [
    { value: "all", label: "All Activity" },
    { value: "reports", label: "Reports" },
    { value: "uploads", label: "Uploads" },
    { value: "claims", label: "Claims" },
    { value: "account_profiles", label: "Account Profiles" },
    { value: "users", label: "Users" },
    { value: "billing", label: "Billing" },
    { value: "system", label: "System" },
  ];
}

function SummaryCard({
  label,
  value,
  description,
  tone,
}: {
  label: string;
  value: any;
  description: string;
  tone: Tone;
}) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-5">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm text-slate-400">{label}</p>
        <span className={`rounded-xl border px-3 py-1 text-xs font-black ${toneClasses(tone)}`}>
          {label}
        </span>
      </div>
      <p className="mt-3 text-3xl font-black text-white">{formatNumber(value)}</p>
      <p className="mt-3 text-xs text-slate-500">{description}</p>
    </div>
  );
}

function DetailPill({
  label,
  value,
  tone = "slate",
}: {
  label: string;
  value: any;
  tone?: Tone;
}) {
  return (
    <div className={`min-w-0 rounded-xl border px-3 py-2 ${toneClasses(tone)}`}>
      <p className="text-[10px] uppercase tracking-[0.2em] opacity-70">{label}</p>
      <p className="mt-1 min-w-0 break-words text-sm font-bold leading-relaxed">{cleanText(value)}</p>
    </div>
  );
}

function ReportDetails({ event }: { event: AuditEvent }) {
  const reportType =
    detailValue(event, "report_type") ||
    (String(event.action || "").includes("carrier") ? "Carrier Submission Packet" : "Executive Underwriting Report");

  return (
    <div className="grid grid-cols-1 gap-2 md:grid-cols-3 [&>*]:min-w-0">
      <DetailPill label="Report Type" value={prettyAction(String(reportType))} tone="purple" />
      <DetailPill label="Policy Number" value={detailValue(event, "policy_number")} />
      <DetailPill label="Business" value={detailValue(event, "business_name", "insured_name", "company_name", "account_name")} />
      <DetailPill label="Account Number" value={detailValue(event, "account_number", "customer_number")} />
      <DetailPill label="Claim Count" value={detailValue(event, "claim_count", "total_claims", "claims_count") || "-"} />
      <DetailPill label="Total Incurred" value={formatCurrency(detailValue(event, "total_incurred", "incurred_total", "total_loss", "loss_total"))} />
      <DetailPill label="Open Claims" value={detailValue(event, "open_claims", "open_claim_count") || "-"} />
      <DetailPill label="Risk Level" value={detailValue(event, "risk_level", "renewal_risk_level") || "-"} />
      <DetailPill label="Renewal Score" value={detailValue(event, "renewal_score", "score") || "-"} />
    </div>
  );
}

function AccountProfileDetails({ event }: { event: AuditEvent }) {
  const details = toDetails(event.details);
  const deletedClaims = detailValue(event, "claims_deleted", "deleted_claims_count", "claim_count");
  const deletedProfiles = detailValue(event, "profiles_deleted", "deleted_profiles_count", "profile_count");
  const scope =
    details.delete_claims === true ||
    String(event.action || "").includes("delete") ||
    String(event.action || "").includes("deleted")
      ? "Account / file group deletion"
      : "Account profile activity";

  return (
    <div className="grid grid-cols-1 gap-2 md:grid-cols-3 [&>*]:min-w-0">
      <DetailPill label="Deleted Scope" value={scope} tone="rose" />
      <DetailPill label="Profile ID" value={detailValue(event, "profile_id") || event.resource_id} />
      <DetailPill label="Business Name" value={detailValue(event, "business_name", "insured_name", "company_name", "account_name")} />
      <DetailPill label="Carrier Name" value={detailValue(event, "carrier_name", "writing_carrier")} />
      <DetailPill label="Policy Number" value={detailValue(event, "policy_number")} />
      <DetailPill label="Account Number" value={detailValue(event, "account_number")} />
      <DetailPill label="Customer Number" value={detailValue(event, "customer_number")} />
      <DetailPill label="Profiles Deleted" value={deletedProfiles || "-"} />
      <DetailPill label="Claims Deleted" value={deletedClaims || "-"} />
    </div>
  );
}

function UploadDetails({ event }: { event: AuditEvent }) {
  return (
    <div className="grid grid-cols-1 gap-2 md:grid-cols-3 [&>*]:min-w-0">
      <DetailPill label="Filename" value={detailValue(event, "filename", "file_name", "original_filename")} tone="blue" />
      <DetailPill label="Policy Number" value={detailValue(event, "policy_number")} />
      <DetailPill label="Account Number" value={detailValue(event, "account_number", "customer_number")} />
      <DetailPill label="Claims Saved" value={detailValue(event, "claims_saved", "claim_count", "claims_count")} />
      <DetailPill label="Parser" value={detailValue(event, "parser", "parser_version", "source")} />
      <DetailPill label="Upload ID" value={detailValue(event, "upload_id") || event.resource_id} />
    </div>
  );
}

function ClaimDetails({ event }: { event: AuditEvent }) {
  return (
    <div className="grid grid-cols-1 gap-2 md:grid-cols-3 [&>*]:min-w-0">
      <DetailPill label="Claim Number" value={detailValue(event, "claim_number") || event.resource_id} tone="emerald" />
      <DetailPill label="Policy Number" value={detailValue(event, "policy_number")} />
      <DetailPill label="Status" value={detailValue(event, "status", "claim_status")} />
      <DetailPill label="Line of Business" value={detailValue(event, "line_of_business", "lob")} />
      <DetailPill label="Paid" value={formatCurrency(detailValue(event, "paid_amount", "paid"))} />
      <DetailPill label="Reserve" value={formatCurrency(detailValue(event, "reserve_amount", "reserve"))} />
      <DetailPill label="Total Incurred" value={formatCurrency(detailValue(event, "total_incurred", "incurred"))} />
      <DetailPill label="Loss Date" value={detailValue(event, "loss_date", "date_of_loss")} />
      <DetailPill label="Claimant" value={detailValue(event, "claimant_name", "claimant")} />
    </div>
  );
}

function GenericDetails({ event }: { event: AuditEvent }) {
  const details = toDetails(event.details);
  const entries = Object.entries(details)
    .filter(([key, value]) => {
      if (value === null || value === undefined || value === "") return false;
      if (typeof value === "object") return false;
      return !["created_at", "generated_at", "generated_at_utc", "event_timestamp_utc"].includes(key);
    })
    .slice(0, 9);

  if (!entries.length) {
    return (
      <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 text-sm text-slate-400">
        No additional details were saved for this event.
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-2 md:grid-cols-3 [&>*]:min-w-0">
      {entries.map(([key, value]) => (
        <DetailPill
          key={key}
          label={prettyAction(key)}
          value={String(value)}
        />
      ))}
    </div>
  );
}

function EventDetails({ event }: { event: AuditEvent }) {
  const label = resourceLabel(event).toLowerCase();

  if (label === "report") return <ReportDetails event={event} />;
  if (label === "account profile") return <AccountProfileDetails event={event} />;
  if (label === "upload") return <UploadDetails event={event} />;
  if (label === "claim") return <ClaimDetails event={event} />;

  return <GenericDetails event={event} />;
}

export default function AuditLogPage() {
  const router = useRouter();

  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [summary, setSummary] = useState<AuditSummary | null>(null);
  const [source, setSource] = useState("");
  const [currentUserEmail, setCurrentUserEmail] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [accessChecked, setAccessChecked] = useState(false);
  const [canAccess, setCanAccess] = useState(true);
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<CategoryFilter>("all");
  const [sortOrder, setSortOrder] = useState<SortOrder>("newest");

  const loadAuditLog = useCallback(async () => {
    const token = getToken();

    if (!token) {
      router.replace("/login?expired=1");
      return;
    }

    setRefreshing(true);
    setError("");

    try {
      try {
        const meRes = await fetch(`${API}/auth/me`, { headers: authHeaders() });

        if (meRes.status === 401) {
          router.replace("/login?expired=1");
          return;
        }

        if (meRes.ok) {
          const meData = await meRes.json();
          setCurrentUserEmail(meData?.email || meData?.user_email || "");
        }
      } catch {
        // Non-blocking.
      }

      try {
        const billingRes = await fetch(`${API}/billing/status`, {
          headers: authHeaders(),
        });

        if (billingRes.status === 401) {
          router.replace("/login?expired=1");
          return;
        }

        if (billingRes.ok) {
          const billingData = await billingRes.json();

          if (!canAccessAuditLogsFromBilling(billingData)) {
            setCanAccess(false);
            setAccessChecked(true);
            setEvents([]);
            setSummary(null);
            return;
          }
        }
      } catch {
        // Backend still protects the route. Do not block page if billing endpoint is unavailable.
      }

      setCanAccess(true);
      setAccessChecked(true);

      const [summaryRes, listRes] = await Promise.all([
        fetch(`${API}/audit-logs/summary?limit=500`, {
          headers: authHeaders(),
        }),
        fetch(`${API}/audit-logs/?limit=250`, {
          headers: authHeaders(),
        }),
      ]);

      if ([summaryRes.status, listRes.status].includes(401)) {
        router.replace("/login?expired=1");
        return;
      }

      if ([summaryRes.status, listRes.status].includes(403)) {
        setCanAccess(false);
        setAccessChecked(true);
        setEvents([]);
        setSummary(null);
        return;
      }

      if (!listRes.ok) {
        throw new Error("Audit Log could not be loaded.");
      }

      const listData = await listRes.json();
      const summaryData = summaryRes.ok ? await summaryRes.json() : null;

      const nextEvents = Array.isArray(listData?.events) ? listData.events : [];

      setEvents(nextEvents);
      setSummary(summaryData || null);
      setSource(listData?.source || summaryData?.source || "");
    } catch (err: any) {
      setError(err?.message || "Audit Log could not be loaded.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [router]);

  useEffect(() => {
    loadAuditLog();
  }, [loadAuditLog]);

  const sortedAllEvents = useMemo(() => {
    return [...events].sort((a, b) => eventTimestampNumber(b) - eventTimestampNumber(a));
  }, [events]);

  const computedSummary = useMemo(() => {
    return computeSummary(sortedAllEvents, summary);
  }, [sortedAllEvents, summary]);

  const filteredEvents = useMemo(() => {
    const cleanSearch = search.trim().toLowerCase();

    return sortedAllEvents.filter((event) => {
      if (!matchesCategory(event, categoryFilter)) return false;
      if (!cleanSearch) return true;

      return eventSearchText(event).includes(cleanSearch);
    });
  }, [categoryFilter, search, sortedAllEvents]);

  const sortedAuditEvents = useMemo(() => {
    const sourceEvents = Array.isArray(filteredEvents) ? filteredEvents : [];

    return [...sourceEvents].sort((a, b) => {
      const diff = eventTimestampNumber(b) - eventTimestampNumber(a);
      return sortOrder === "newest" ? diff : -diff;
    });
  }, [filteredEvents, sortOrder]);

  const visibleEvents = sortedAuditEvents.slice(0, 100);
  const lastEventTime = sortedAllEvents.length ? eventTime(sortedAllEvents[0]) : computedSummary.last_event_at;

  if (!accessChecked && loading) {
    return (
      <main className="min-h-screen bg-slate-950 px-6 py-10 text-white">
        <div className="mx-auto max-w-6xl rounded-3xl border border-white/10 bg-white/[0.04] p-8">
          <p className="text-lg font-bold">Loading Audit Log...</p>
        </div>
      </main>
    );
  }

  if (!canAccess) {
    return (
      <main className="min-h-screen bg-slate-950 px-6 py-10 text-white">
        <div className="mx-auto max-w-4xl rounded-3xl border border-amber-400/30 bg-amber-500/10 p-8">
          <p className="text-xs uppercase tracking-[0.35em] text-amber-200">Audit Log</p>
          <h1 className="mt-3 text-3xl font-black">Agency package required</h1>
          <p className="mt-3 text-slate-300">
            Audit Logs are available on Agency and Founding Agency packages.
          </p>
          <button
            onClick={() => router.push("/settings")}
            className="mt-6 rounded-xl border border-white/10 px-5 py-3 font-bold text-white hover:bg-white/10"
          >
            Back to Settings
          </button>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-950 text-white">
      <section className="border-b border-white/10 bg-slate-950/90 px-6 py-8">
        <div className="mx-auto flex max-w-7xl flex-col gap-5 md:flex-row md:items-end md:justify-between">
          <div>
            <button
              onClick={() => router.push("/settings")}
              className="rounded-xl border border-white/10 px-4 py-2 text-sm font-bold text-slate-200 hover:bg-white/10"
            >
              Back to Settings
            </button>
            <div className="mt-6 flex flex-wrap items-center gap-3">
              <h1 className="text-4xl font-black">Audit Log</h1>
              <span className="rounded-full border border-blue-400/30 bg-blue-500/10 px-4 py-1 text-xs font-black uppercase tracking-[0.25em] text-blue-200">
                Compliance Console
              </span>
            </div>
            <p className="mt-2 text-slate-400">
              A clean activity timeline for uploads, claims, reports, exports, account profiles, users, billing, and system events.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3">
              <p className="text-[10px] uppercase tracking-[0.25em] text-slate-500">Source</p>
              <p className="text-sm font-black text-white">{source || "Audit Log"}</p>
            </div>
            <button
              onClick={loadAuditLog}
              disabled={refreshing}
              className="rounded-xl bg-blue-600 px-5 py-3 font-black text-white hover:bg-blue-700 disabled:opacity-60"
            >
              {refreshing ? "Refreshing..." : "Refresh"}
            </button>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl space-y-6 px-6 py-8">
        {error && (
          <div className="rounded-2xl border border-rose-400/30 bg-rose-500/10 p-4 text-rose-100">
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
          <SummaryCard label="Total" value={computedSummary.total_events} description="Combined organization activity records." tone="slate" />
          <SummaryCard label="Uploads" value={computedSummary.uploads} description="Loss run uploads and file activity." tone="blue" />
          <SummaryCard label="Claims" value={computedSummary.claims} description="Claim records derived from saved claims." tone="emerald" />
          <SummaryCard label="Reports" value={computedSummary.reports} description="Generated reports, packets, and memos." tone="purple" />
        </div>

        <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-5">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <h2 className="text-2xl font-black">Activity Filters</h2>
              <p className="text-sm text-slate-400">
                Search policy numbers, claim numbers, report names, users, deleted profiles, or validation results.
              </p>
            </div>

            <div className="flex flex-col gap-3 md:flex-row">
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search audit activity..."
                className="min-w-[280px] rounded-xl border border-white/10 bg-slate-950 px-4 py-3 text-white outline-none focus:border-blue-400"
              />

              <select
                value={categoryFilter}
                onChange={(event) => setCategoryFilter(event.target.value as CategoryFilter)}
                className="rounded-xl border border-white/10 bg-slate-950 px-4 py-3 text-white outline-none focus:border-blue-400"
              >
                {categoryOptions().map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>

              <select
                value={sortOrder}
                onChange={(event) => setSortOrder(event.target.value as SortOrder)}
                className="rounded-xl border border-white/10 bg-slate-950 px-4 py-3 text-white outline-none focus:border-blue-400"
              >
                <option value="newest">Newest First</option>
                <option value="oldest">Oldest First</option>
              </select>
            </div>
          </div>
        </div>

        <div className="overflow-hidden rounded-2xl border border-white/10 bg-white/[0.04]">
          <div className="flex flex-col gap-2 border-b border-white/10 p-5 md:flex-row md:items-end md:justify-between">
            <div>
              <h2 className="text-2xl font-black">Recent Activity</h2>
              <p className="text-sm text-blue-200">
                Showing {visibleEvents.length} of {filteredEvents.length} filtered records.
              </p>
            </div>
            <p className="text-sm text-slate-500">
              Last event: {formatDate(lastEventTime)}
            </p>
          </div>

          {loading ? (
            <div className="p-8 text-slate-300">Loading activity...</div>
          ) : visibleEvents.length === 0 ? (
            <div className="p-8 text-slate-300">No audit events match the selected filters.</div>
          ) : (
            <div className="divide-y divide-white/10">
              {visibleEvents.map((event, index) => {
                const tone = eventTone(event);
                const userName = eventUserName(event);
                const userEmail = eventUserEmail(event, currentUserEmail);
                const timeValue = eventTime(event);

                return (
                  <article
                    key={`${event.id || "event"}-${index}`}
                    className="grid grid-cols-1 gap-5 p-5 lg:grid-cols-[190px_1fr]"
                  >
                    <aside className="min-w-0 text-sm">
                      <p className="text-xs uppercase tracking-[0.35em] text-slate-500">Time</p>
                      <p className="mt-2 break-words text-sm font-bold leading-relaxed text-slate-100">
                        {formatDate(timeValue)}
                      </p>

                      <p className="mt-5 text-xs uppercase tracking-[0.35em] text-slate-500">User</p>
                      <p className="mt-2 break-words font-bold text-white">{userName || "-"}</p>
                      <p className="mt-1 break-words text-slate-300">{userEmail || "-"}</p>

                      <p className="mt-5 text-xs uppercase tracking-[0.35em] text-slate-500">Resource ID</p>
                      <p className="mt-2 break-words text-blue-200">{eventResourceId(event)}</p>
                    </aside>

                    <section className="min-w-0 space-y-4">
                      <div className="flex flex-wrap items-center gap-3">
                        <span className={`rounded-full border px-3 py-1 text-xs font-black ${toneClasses(tone)}`}>
                          {resourceLabel(event)}
                        </span>
                        <h3 className="min-w-0 break-words text-xl font-black tracking-tight">
                          {prettyAction(event.action)}
                        </h3>
                      </div>

                      <EventDetails event={event} />

                      <details className="rounded-xl border border-white/10 bg-slate-950/50">
                        <summary className="cursor-pointer px-4 py-3 text-sm font-bold text-slate-200">
                          View technical details
                        </summary>
                        <pre className="max-h-80 overflow-auto border-t border-white/10 p-4 text-xs text-slate-300">
                          {JSON.stringify(
                            {
                              id: event.id,
                              created_at: event.created_at,
                              timestamp: event.timestamp,
                              action: event.action,
                              resource_type: event.resource_type,
                              resource_id: event.resource_id,
                              details: toDetails(event.details),
                            },
                            null,
                            2
                          )}
                        </pre>
                      </details>
                    </section>
                  </article>
                );
              })}
            </div>
          )}
        </div>
      </section>
    </main>
  );
}

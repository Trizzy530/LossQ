"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";

type ClaimStatus = "Open" | "Pending" | "Reopened" | "Closed" | string;

type Claim = {
  id?: string;
  claim_id?: string;
  claimNumber?: string;
  claim_number?: string;
  claimant?: string;
  insured?: string;
  policyNumber?: string;
  policy_number?: string;
  status?: ClaimStatus;
  lossDate?: string;
  loss_date?: string;
  reportedDate?: string;
  reported_date?: string;
  closedDate?: string;
  closed_date?: string;
  causeOfLoss?: string;
  cause_of_loss?: string;
  description?: string;
  paid?: number | string;
  reserve?: number | string;
  incurred?: number | string;
  deductible?: number | string;
  litigation?: boolean;
  attorneyInvolved?: boolean;
  attorney_involved?: boolean;
  notes?: string;
  [key: string]: unknown;
};

type SeverityResult = {
  score: number;
  label: "Low" | "Moderate" | "High" | "Critical";
  color: string;
};

type ReserveResult = {
  label: "Adequate" | "Watch" | "Under Reserved" | "Review Needed";
  detail: string;
  color: string;
};

type ExposureResult = {
  label: "Low" | "Moderate" | "High";
  detail: string;
  color: string;
};

type FraudResult = {
  label: "Low" | "Moderate" | "Elevated";
  indicators: string[];
  color: string;
};

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  "https://lossq-production.up.railway.app";

function money(value: unknown): number {
  if (typeof value === "number") return Number.isFinite(value) ? value : 0;
  if (typeof value === "string") {
    const cleaned = value.replace(/[$,\s]/g, "");
    const parsed = Number(cleaned);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}

function formatCurrency(value: unknown): string {
  return money(value).toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });
}

function formatDate(value: unknown): string {
  if (!value || typeof value !== "string") return "Not available";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function getClaimId(claim: Claim): string {
  return String(claim.claim_id || claim.claimNumber || claim.claim_number || claim.id || "Unknown");
}

function getStatus(claim: Claim): string {
  return String(claim.status || "Open");
}

function getIncurred(claim: Claim): number {
  const explicit = money(claim.incurred);
  if (explicit > 0) return explicit;
  return money(claim.paid) + money(claim.reserve);
}

function statusRank(status: string): number {
  const normalized = status.toLowerCase();
  if (normalized.includes("open")) return 1;
  if (normalized.includes("pending") || normalized.includes("reopened")) return 2;
  if (normalized.includes("closed")) return 3;
  return 2;
}

function sortClaims(a: Claim, b: Claim): number {
  const statusDiff = statusRank(getStatus(a)) - statusRank(getStatus(b));
  if (statusDiff !== 0) return statusDiff;
  return getIncurred(b) - getIncurred(a);
}

function getStatusBadge(status: string): string {
  const normalized = status.toLowerCase();
  if (normalized.includes("closed")) return "bg-slate-700 text-white border-slate-600";
  if (normalized.includes("reopened")) return "bg-orange-100 text-orange-800 border-orange-200";
  if (normalized.includes("pending")) return "bg-yellow-100 text-yellow-800 border-yellow-200";
  return "bg-green-100 text-green-800 border-green-200";
}

function calculateSeverity(claim: Claim): SeverityResult {
  const incurred = getIncurred(claim);
  const reserve = money(claim.reserve);
  const status = getStatus(claim).toLowerCase();

  let score = 0;
  if (incurred >= 250000) score += 45;
  else if (incurred >= 100000) score += 35;
  else if (incurred >= 50000) score += 25;
  else if (incurred >= 15000) score += 15;
  else score += 5;

  if (reserve >= 100000) score += 20;
  else if (reserve >= 50000) score += 12;
  else if (reserve >= 15000) score += 8;

  if (status.includes("reopened")) score += 15;
  if (claim.litigation || claim.attorneyInvolved || claim.attorney_involved) score += 20;

  score = Math.min(100, score);

  if (score >= 80) return { score, label: "Critical", color: "bg-red-100 text-red-800 border-red-200" };
  if (score >= 60) return { score, label: "High", color: "bg-orange-100 text-orange-800 border-orange-200" };
  if (score >= 35) return { score, label: "Moderate", color: "bg-yellow-100 text-yellow-800 border-yellow-200" };
  return { score, label: "Low", color: "bg-green-100 text-green-800 border-green-200" };
}

function analyzeReserve(claim: Claim): ReserveResult {
  const paid = money(claim.paid);
  const reserve = money(claim.reserve);
  const incurred = getIncurred(claim);
  const status = getStatus(claim).toLowerCase();

  if (status.includes("closed")) {
    return {
      label: "Adequate",
      detail: "Claim is closed. Reserve adequacy concern is reduced unless reopened.",
      color: "bg-slate-100 text-slate-800 border-slate-200",
    };
  }

  if (incurred > 0 && reserve / incurred < 0.15 && paid > 25000) {
    return {
      label: "Under Reserved",
      detail: "Reserve appears low compared with paid and total incurred activity.",
      color: "bg-red-100 text-red-800 border-red-200",
    };
  }

  if (reserve === 0 && incurred > 10000) {
    return {
      label: "Review Needed",
      detail: "No reserve is posted despite meaningful incurred activity.",
      color: "bg-orange-100 text-orange-800 border-orange-200",
    };
  }

  if (reserve > 0 && incurred > 50000) {
    return {
      label: "Watch",
      detail: "Reserve is present, but claim size warrants continued monitoring.",
      color: "bg-yellow-100 text-yellow-800 border-yellow-200",
    };
  }

  return {
    label: "Adequate",
    detail: "Reserve position appears reasonable based on available paid and incurred data.",
    color: "bg-green-100 text-green-800 border-green-200",
  };
}

function analyzeLitigation(claim: Claim): ExposureResult {
  const text = `${claim.description || ""} ${claim.notes || ""} ${claim.causeOfLoss || ""} ${claim.cause_of_loss || ""}`.toLowerCase();
  const incurred = getIncurred(claim);
  const attorney = Boolean(claim.litigation || claim.attorneyInvolved || claim.attorney_involved);

  if (
    attorney ||
    text.includes("attorney") ||
    text.includes("lawsuit") ||
    text.includes("litigation") ||
    text.includes("demand")
  ) {
    return {
      label: "High",
      detail: "Attorney, lawsuit, demand, or litigation indicators are present.",
      color: "bg-red-100 text-red-800 border-red-200",
    };
  }

  if (incurred >= 100000 || text.includes("injury") || text.includes("bodily") || text.includes("fatal")) {
    return {
      label: "Moderate",
      detail: "Large loss or injury-related language may increase litigation exposure.",
      color: "bg-yellow-100 text-yellow-800 border-yellow-200",
    };
  }

  return {
    label: "Low",
    detail: "No major litigation indicators detected from available claim details.",
    color: "bg-green-100 text-green-800 border-green-200",
  };
}

function analyzeFraud(claim: Claim): FraudResult {
  const indicators: string[] = [];
  const text = `${claim.description || ""} ${claim.notes || ""}`.toLowerCase();
  const reported = new Date(String(claim.reportedDate || claim.reported_date || ""));
  const loss = new Date(String(claim.lossDate || claim.loss_date || ""));

  if (!Number.isNaN(reported.getTime()) && !Number.isNaN(loss.getTime())) {
    const days = Math.round((reported.getTime() - loss.getTime()) / 86400000);
    if (days > 14) indicators.push("Late reporting");
  }

  if (text.includes("conflicting") || text.includes("inconsistent")) indicators.push("Inconsistent description");
  if (text.includes("prior") || text.includes("history")) indicators.push("Prior claim pattern noted");
  if (text.includes("suspicious") || text.includes("questionable")) indicators.push("Questionable facts noted");
  if (getIncurred(claim) > 0 && money(claim.reserve) === 0 && !getStatus(claim).toLowerCase().includes("closed")) {
    indicators.push("No reserve on active incurred claim");
  }

  if (indicators.length >= 3) {
    return { label: "Elevated", indicators, color: "bg-red-100 text-red-800 border-red-200" };
  }

  if (indicators.length >= 1) {
    return { label: "Moderate", indicators, color: "bg-yellow-100 text-yellow-800 border-yellow-200" };
  }

  return {
    label: "Low",
    indicators: ["No major fraud indicators detected"],
    color: "bg-green-100 text-green-800 border-green-200",
  };
}

function getRiskTier(severity: SeverityResult, litigation: ExposureResult, fraud: FraudResult): {
  label: string;
  color: string;
} {
  if (severity.score >= 80 || litigation.label === "High" || fraud.label === "Elevated") {
    return { label: "Tier 1 - Critical", color: "bg-red-600 text-white border-red-700" };
  }

  if (severity.score >= 60 || litigation.label === "Moderate" || fraud.label === "Moderate") {
    return { label: "Tier 2 - Watch", color: "bg-orange-500 text-white border-orange-600" };
  }

  if (severity.score >= 35) {
    return { label: "Tier 3 - Moderate", color: "bg-yellow-500 text-white border-yellow-600" };
  }

  return { label: "Tier 4 - Low", color: "bg-green-600 text-white border-green-700" };
}

function getRecommendation(
  claim: Claim,
  severity: SeverityResult,
  reserve: ReserveResult,
  litigation: ExposureResult,
  fraud: FraudResult
): string {
  if (fraud.label === "Elevated") {
    return "Escalate for SIU review, validate documentation, and pause underwriting credit until facts are confirmed.";
  }

  if (litigation.label === "High" || severity.label === "Critical") {
    return "Refer to senior underwriting. Maintain conservative loss pick, review reserves, and require updated claim notes before renewal action.";
  }

  if (reserve.label === "Under Reserved" || reserve.label === "Review Needed") {
    return "Request updated reserve rationale from claims team before final underwriting recommendation.";
  }

  if (getStatus(claim).toLowerCase().includes("closed") && severity.label === "Low") {
    return "Closed low-severity claim. Minimal underwriting impact unless frequency trend is present.";
  }

  return "Monitor claim development and include in renewal memo as a standard loss activity item.";
}

export default function ClaimDetailPage() {
  const router = useRouter();
  const params = useParams();
  const claimId = String(params?.id || "");

  const [claim, setClaim] = useState<Claim | null>(null);
  const [relatedClaims, setRelatedClaims] = useState<Claim[]>([]);
  const [loading, setLoading] = useState(true);
  const [authChecking, setAuthChecking] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const validateSession = useCallback((): boolean => {
    const token =
      localStorage.getItem("lossq_token") ||
      localStorage.getItem("token") ||
      sessionStorage.getItem("lossq_token") ||
      sessionStorage.getItem("token");

    const loginTime = localStorage.getItem("lossq_login_time");
    const now = Date.now();
    const twentyFourHours = 24 * 60 * 60 * 1000;

    if (!token) {
      router.replace("/login");
      return false;
    }

    if (loginTime && now - Number(loginTime) > twentyFourHours) {
      localStorage.removeItem("lossq_token");
      localStorage.removeItem("token");
      localStorage.removeItem("lossq_login_time");
      sessionStorage.removeItem("lossq_token");
      sessionStorage.removeItem("token");
      router.replace("/login?expired=1");
      return false;
    }

    if (!loginTime) localStorage.setItem("lossq_login_time", String(now));
    return true;
  }, [router]);

  const fetchClaim = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const token =
        localStorage.getItem("lossq_token") ||
        localStorage.getItem("token") ||
        sessionStorage.getItem("lossq_token") ||
        sessionStorage.getItem("token");

      const headers: HeadersInit = {
        "Content-Type": "application/json",
      };

      if (token) headers.Authorization = `Bearer ${token}`;

      const endpoints = [
        `${API_BASE}/claims/${encodeURIComponent(claimId)}`,
        `${API_BASE}/api/claims/${encodeURIComponent(claimId)}`,
        `${API_BASE}/claims`,
        `${API_BASE}/api/claims`,
      ];

      let foundClaim: Claim | null = null;
      let allClaims: Claim[] = [];

      for (const endpoint of endpoints) {
        try {
          const response = await fetch(endpoint, {
            method: "GET",
            headers,
            cache: "no-store",
          });

          if (response.status === 401 || response.status === 403) {
            router.replace("/login");
            return;
          }

          if (!response.ok) continue;

          const data = await response.json();

          if (Array.isArray(data)) {
            allClaims = data;
            foundClaim =
              data.find((item: Claim) => String(getClaimId(item)) === claimId || String(item.id) === claimId) || null;
          } else if (Array.isArray(data?.claims)) {
            allClaims = data.claims;
            foundClaim =
              data.claims.find(
                (item: Claim) => String(getClaimId(item)) === claimId || String(item.id) === claimId
              ) || null;
          } else if (data?.claim) {
            foundClaim = data.claim;
          } else if (data && typeof data === "object") {
            foundClaim = data;
          }

          if (foundClaim) break;
        } catch {
          continue;
        }
      }

      if (!foundClaim) {
        throw new Error("Claim could not be found. Please retry or return to the dashboard.");
      }

      setClaim(foundClaim);
      setRelatedClaims(allClaims.sort(sortClaims));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load claim details.");
    } finally {
      setLoading(false);
    }
  }, [claimId, router]);

  useEffect(() => {
    const ok = validateSession();
    setAuthChecking(false);
    if (ok) fetchClaim();
  }, [fetchClaim, validateSession]);

  const analysis = useMemo(() => {
    if (!claim) return null;

    const severity = calculateSeverity(claim);
    const reserve = analyzeReserve(claim);
    const litigation = analyzeLitigation(claim);
    const fraud = analyzeFraud(claim);
    const riskTier = getRiskTier(severity, litigation, fraud);
    const recommendation = getRecommendation(claim, severity, reserve, litigation, fraud);

    return { severity, reserve, litigation, fraud, riskTier, recommendation };
  }, [claim]);

  if (authChecking || loading) {
    return (
      <main className="min-h-screen bg-slate-950 text-white flex items-center justify-center p-6">
        <div className="w-full max-w-xl rounded-2xl border border-slate-800 bg-slate-900/80 p-8 shadow-2xl">
          <div className="mb-4 h-12 w-12 animate-spin rounded-full border-4 border-slate-700 border-t-blue-500" />
          <h1 className="text-2xl font-bold">Loading claim analysis...</h1>
          <p className="mt-2 text-slate-300">Validating your session and preparing the claim file.</p>
        </div>
      </main>
    );
  }

  if (error || !claim || !analysis) {
    return (
      <main className="min-h-screen bg-slate-950 text-white flex items-center justify-center p-6">
        <div className="w-full max-w-xl rounded-2xl border border-red-900/60 bg-slate-900 p-8 shadow-2xl">
          <h1 className="text-2xl font-bold text-red-300">Claim page could not load</h1>
          <p className="mt-3 text-slate-300">{error || "Unable to load claim details."}</p>
          <div className="mt-6 flex flex-wrap gap-3">
            <button
              onClick={fetchClaim}
              className="rounded-xl bg-blue-600 px-5 py-3 font-semibold text-white hover:bg-blue-500"
            >
              Retry
            </button>
            <button
              onClick={() => router.push("/dashboard")}
              className="rounded-xl border border-slate-700 px-5 py-3 font-semibold text-slate-100 hover:bg-slate-800"
            >
              Back to dashboard
            </button>
          </div>
        </div>
      </main>
    );
  }

  const status = getStatus(claim);
  const incurred = getIncurred(claim);

  return (
    <main className="min-h-screen bg-slate-950 text-white">
      <div className="mx-auto max-w-7xl px-6 py-8">
        <div className="mb-6 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <button
              onClick={() => router.push("/dashboard")}
              className="mb-4 rounded-xl border border-slate-700 px-4 py-2 text-sm font-semibold text-slate-200 hover:bg-slate-800"
            >
              ← Back to dashboard
            </button>
            <h1 className="text-3xl font-bold tracking-tight">Claim Analysis</h1>
            <p className="mt-1 text-slate-400">Claim #{getClaimId(claim)}</p>
          </div>

          <div className="flex flex-wrap gap-3">
            <span className={`rounded-full border px-4 py-2 text-sm font-bold ${getStatusBadge(status)}`}>
              {status}
            </span>
            <span className={`rounded-full border px-4 py-2 text-sm font-bold ${analysis.riskTier.color}`}>
              {analysis.riskTier.label}
            </span>
          </div>
        </div>

        <section className="grid gap-4 md:grid-cols-4">
          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5 shadow-xl">
            <p className="text-sm text-slate-400">Total Incurred</p>
            <p className="mt-2 text-2xl font-bold">{formatCurrency(incurred)}</p>
          </div>
          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5 shadow-xl">
            <p className="text-sm text-slate-400">Paid</p>
            <p className="mt-2 text-2xl font-bold">{formatCurrency(claim.paid)}</p>
          </div>
          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5 shadow-xl">
            <p className="text-sm text-slate-400">Reserve</p>
            <p className="mt-2 text-2xl font-bold">{formatCurrency(claim.reserve)}</p>
          </div>
          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5 shadow-xl">
            <p className="text-sm text-slate-400">Severity Score</p>
            <p className="mt-2 text-2xl font-bold">{analysis.severity.score}/100</p>
          </div>
        </section>

        <section className="mt-6 grid gap-6 lg:grid-cols-3">
          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-xl lg:col-span-2">
            <h2 className="text-xl font-bold">Claim Details</h2>
            <div className="mt-5 grid gap-4 md:grid-cols-2">
              <Info label="Claimant" value={String(claim.claimant || "Not available")} />
              <Info label="Insured" value={String(claim.insured || "Not available")} />
              <Info label="Policy Number" value={String(claim.policyNumber || claim.policy_number || "Not available")} />
              <Info label="Cause of Loss" value={String(claim.causeOfLoss || claim.cause_of_loss || "Not available")} />
              <Info label="Loss Date" value={formatDate(claim.lossDate || claim.loss_date)} />
              <Info label="Reported Date" value={formatDate(claim.reportedDate || claim.reported_date)} />
            </div>
            <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950 p-4">
              <p className="text-sm font-semibold text-slate-400">Description</p>
              <p className="mt-2 leading-7 text-slate-200">
                {String(claim.description || claim.notes || "No claim narrative available.")}
              </p>
            </div>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-xl">
            <h2 className="text-xl font-bold">AI Underwriting Recommendation</h2>
            <p className="mt-4 rounded-xl border border-blue-900/60 bg-blue-950/40 p-4 leading-7 text-blue-100">
              {analysis.recommendation}
            </p>
          </div>
        </section>

        <section className="mt-6 grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <AnalysisCard title="Claim Severity" badge={analysis.severity.label} color={analysis.severity.color}>
            Score: {analysis.severity.score}/100 based on incurred value, reserve, status, and escalation indicators.
          </AnalysisCard>

          <AnalysisCard title="Reserve Adequacy" badge={analysis.reserve.label} color={analysis.reserve.color}>
            {analysis.reserve.detail}
          </AnalysisCard>

          <AnalysisCard title="Litigation Exposure" badge={analysis.litigation.label} color={analysis.litigation.color}>
            {analysis.litigation.detail}
          </AnalysisCard>

          <AnalysisCard title="Fraud Indicators" badge={analysis.fraud.label} color={analysis.fraud.color}>
            {analysis.fraud.indicators.join(", ")}
          </AnalysisCard>
        </section>

        <section className="mt-6 rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-xl">
          <h2 className="text-xl font-bold">Timeline Visualization</h2>
          <div className="mt-6 grid gap-4 md:grid-cols-4">
            <TimelineItem title="Loss Occurred" value={formatDate(claim.lossDate || claim.loss_date)} />
            <TimelineItem title="Claim Reported" value={formatDate(claim.reportedDate || claim.reported_date)} />
            <TimelineItem title="Current Status" value={status} />
            <TimelineItem title="Closed Date" value={formatDate(claim.closedDate || claim.closed_date)} />
          </div>
        </section>

        {relatedClaims.length > 0 && (
          <section className="mt-6 rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-xl">
            <h2 className="text-xl font-bold">Claims Analysis</h2>
            <p className="mt-1 text-sm text-slate-400">
              Sorted by open claims first, pending/reopened second, closed last, then highest incurred within each group.
            </p>

            <div className="mt-5 overflow-x-auto">
              <table className="w-full min-w-[850px] border-collapse text-left">
                <thead>
                  <tr className="border-b border-slate-800 text-sm text-slate-400">
                    <th className="py-3 pr-4">Claim</th>
                    <th className="py-3 pr-4">Status</th>
                    <th className="py-3 pr-4">Loss Date</th>
                    <th className="py-3 pr-4">Cause</th>
                    <th className="py-3 pr-4 text-right">Paid</th>
                    <th className="py-3 pr-4 text-right">Reserve</th>
                    <th className="py-3 pr-4 text-right">Incurred</th>
                  </tr>
                </thead>
                <tbody>
                  {relatedClaims.map((item, index) => (
                    <tr
                      key={`${getClaimId(item)}-${index}`}
                      onClick={() => router.push(`/claims/${encodeURIComponent(getClaimId(item))}`)}
                      className="cursor-pointer border-b border-slate-800/70 text-sm hover:bg-slate-800/50"
                    >
                      <td className="py-4 pr-4 font-semibold text-white">{getClaimId(item)}</td>
                      <td className="py-4 pr-4">
                        <span className={`rounded-full border px-3 py-1 text-xs font-bold ${getStatusBadge(getStatus(item))}`}>
                          {getStatus(item)}
                        </span>
                      </td>
                      <td className="py-4 pr-4 text-slate-300">{formatDate(item.lossDate || item.loss_date)}</td>
                      <td className="py-4 pr-4 text-slate-300">
                        {String(item.causeOfLoss || item.cause_of_loss || "Not available")}
                      </td>
                      <td className="py-4 pr-4 text-right text-slate-300">{formatCurrency(item.paid)}</td>
                      <td className="py-4 pr-4 text-right text-slate-300">{formatCurrency(item.reserve)}</td>
                      <td className="py-4 pr-4 text-right font-bold text-white">{formatCurrency(getIncurred(item))}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </div>
    </main>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
      <p className="text-sm font-semibold text-slate-400">{label}</p>
      <p className="mt-1 font-bold text-white">{value}</p>
    </div>
  );
}

function AnalysisCard({
  title,
  badge,
  color,
  children,
}: {
  title: string;
  badge: string;
  color: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5 shadow-xl">
      <div className="flex items-center justify-between gap-3">
        <h3 className="font-bold">{title}</h3>
        <span className={`rounded-full border px-3 py-1 text-xs font-bold ${color}`}>{badge}</span>
      </div>
      <p className="mt-4 text-sm leading-6 text-slate-300">{children}</p>
    </div>
  );
}

function TimelineItem({ title, value }: { title: string; value: string }) {
  return (
    <div className="relative rounded-xl border border-slate-800 bg-slate-950 p-4">
      <div className="mb-3 h-3 w-3 rounded-full bg-blue-500 shadow-[0_0_0_6px_rgba(59,130,246,0.15)]" />
      <p className="text-sm font-semibold text-slate-400">{title}</p>
      <p className="mt-1 font-bold text-white">{value}</p>
    </div>
  );
}
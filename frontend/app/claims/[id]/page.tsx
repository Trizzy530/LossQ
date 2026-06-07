"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";

const API =
  process.env.NEXT_PUBLIC_API_URL || "https://lossq-production.up.railway.app";

type AnyObject = Record<string, any>;

async function safeJson(res: Response) {
  try {
    return await res.json();
  } catch {
    return null;
  }
}

function clean(value: any) {
  if (value === null || value === undefined || value === "") return "-";
  return String(value);
}

function money(value: any) {
  const numberValue = Number(value || 0);
  return `$${numberValue.toLocaleString()}`;
}

function numberValue(value: any) {
  const parsed = Number(value || 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

function boolValue(value: any) {
  if (value === true) return true;
  if (value === false) return false;

  const normalized = String(value || "").trim().toLowerCase();

  return [
    "yes",
    "y",
    "true",
    "1",
    "litigation",
    "attorney",
    "attorney involved",
    "suit",
    "lawsuit",
    "represented",
  ].some((item) => normalized.includes(item));
}

function getValue(obj: AnyObject | null | undefined, keys: string[]) {
  if (!obj) return undefined;

  for (const key of keys) {
    if (obj[key] !== undefined && obj[key] !== null && obj[key] !== "") {
      return obj[key];
    }
  }

  return undefined;
}

function normalizeClaimPayload(data: any): AnyObject | null {
  if (!data) return null;
  if (Array.isArray(data)) return data[0] || null;
  if (data.claim && typeof data.claim === "object") return data.claim;
  if (data.data && typeof data.data === "object") return data.data;
  if (data.result && typeof data.result === "object") return data.result;
  if (typeof data === "object") return data;
  return null;
}

function getClaimNumber(claim: AnyObject | null | undefined) {
  return clean(
    getValue(claim, ["claim_number", "claimNo", "claim_no", "number", "claimNumber"])
  );
}

function getPolicyNumber(claim: AnyObject | null | undefined) {
  return clean(getValue(claim, ["policy_number", "policyNumber", "policy_no"]));
}

function sameText(a: any, b: any) {
  return String(a || "").trim().toUpperCase() === String(b || "").trim().toUpperCase();
}

function parseMaybeJson(value: string | null) {
  if (!value) return null;
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

function collectClaimsFromStorage(): AnyObject[] {
  if (typeof window === "undefined") return [];

  const storageKeys = [
    "lossq_claims",
    "lossq_visible_claims",
    "lossq_uploaded_claims",
    "lossq_last_upload_claims",
    "lossq_last_upload_review",
    "lossq_last_upload_result",
    "lossq_dashboard_state",
    "lossq_selected_claim",
  ];

  const claims: AnyObject[] = [];

  function addFromValue(value: any) {
    if (!value) return;

    if (Array.isArray(value)) {
      value.forEach((item) => {
        if (item && typeof item === "object") claims.push(item);
      });
      return;
    }

    if (value.claim && typeof value.claim === "object") {
      claims.push(value.claim);
    }

    if (value.selectedClaim && typeof value.selectedClaim === "object") {
      claims.push(value.selectedClaim);
    }

    ["claims", "parsed_claims", "saved_claim_rows", "visibleClaims"].forEach((key) => {
      if (Array.isArray(value[key])) {
        value[key].forEach((item: any) => {
          if (item && typeof item === "object") claims.push(item);
        });
      }
    });

    if (value.profile && Array.isArray(value.profile.claims)) {
      value.profile.claims.forEach((item: any) => {
        if (item && typeof item === "object") claims.push(item);
      });
    }
  }

  for (const key of storageKeys) {
    addFromValue(parseMaybeJson(localStorage.getItem(key)));
    addFromValue(parseMaybeJson(sessionStorage.getItem(key)));
  }

  // Also scan all LossQ keys in case the dashboard used a newer cache key.
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i) || "";
    if (key.toLowerCase().includes("lossq")) {
      addFromValue(parseMaybeJson(localStorage.getItem(key)));
    }
  }

  const deduped: AnyObject[] = [];
  const seen = new Set<string>();

  for (const claim of claims) {
    const key = [
      claim.id || "",
      getClaimNumber(claim),
      getPolicyNumber(claim),
      claim.total_incurred || "",
    ].join("|");

    if (!seen.has(key)) {
      seen.add(key);
      deduped.push(claim);
    }
  }

  return deduped;
}

function findStoredClaim(claimId: string, queryClaimNumber?: string | null, queryPolicyNumber?: string | null) {
  const claims = collectClaimsFromStorage();

  return (
    claims.find((item) => sameText(item?.id, claimId)) ||
    claims.find((item) => sameText(getClaimNumber(item), claimId)) ||
    (queryClaimNumber
      ? claims.find(
          (item) =>
            sameText(getClaimNumber(item), queryClaimNumber) &&
            (!queryPolicyNumber || sameText(getPolicyNumber(item), queryPolicyNumber))
        )
      : null) ||
    null
  );
}

function getClaimDisplay(claim: AnyObject | null, fallbackId: string) {
  const paid = numberValue(
    getValue(claim, ["paid_amount", "paid", "total_paid", "paid_loss", "paidLoss"])
  );

  const reserve = numberValue(
    getValue(claim, [
      "reserve_amount",
      "reserve",
      "total_reserved",
      "case_reserve",
      "caseReserve",
      "outstanding_reserve",
    ])
  );

  const incurredRaw = getValue(claim, [
    "total_incurred",
    "incurred",
    "gross_incurred",
    "total",
    "loss_total",
  ]);

  const totalIncurred = incurredRaw !== undefined ? numberValue(incurredRaw) : paid + reserve;

  const litigationRaw = getValue(claim, [
    "litigation",
    "litigation_flag",
    "litigation_status",
    "attorney_involved",
    "attorney",
    "suit",
    "represented",
    "lit",
  ]);

  const litigation = boolValue(litigationRaw);
  const status = clean(getValue(claim, ["status", "claim_status", "claimStatus"]));
  const isOpen = status.toLowerCase().includes("open");

  let severity = "Low";
  if (totalIncurred >= 100000 || litigation) severity = "High";
  else if (totalIncurred >= 25000 || reserve >= 15000 || isOpen) severity = "Moderate";

  let reservePressure = "Low";
  if (reserve >= 75000) reservePressure = "High";
  else if (reserve >= 15000) reservePressure = "Moderate";

  return {
    claimNumber: clean(
      getValue(claim, ["claim_number", "claimNo", "claim_no", "number", "claimNumber"]) ||
        fallbackId
    ),
    policyNumber: clean(getValue(claim, ["policy_number", "policyNumber", "policy_no"])),
    lineOfBusiness: clean(
      getValue(claim, [
        "line_of_business",
        "lob",
        "coverage",
        "policy_type",
        "line",
        "coverage_type",
      ])
    ),
    status,
    lossDate: clean(getValue(claim, ["loss_date", "date_of_loss", "lossDt", "lossDate"])),
    reportedDate: clean(
      getValue(claim, ["reported_date", "report_date", "reportedDate", "date_reported"])
    ),
    claimant: clean(getValue(claim, ["claimant", "claimant_name", "injured_party"])),
    causeOfLoss: clean(
      getValue(claim, [
        "cause_of_loss",
        "loss_description",
        "description",
        "claim_description",
        "notes",
        "loss_cause",
      ])
    ),
    paid,
    reserve,
    totalIncurred,
    litigation,
    litigationRaw,
    severity,
    reservePressure,
    adjuster: clean(getValue(claim, ["adjuster", "examiner", "claim_adjuster"])),
    state: clean(getValue(claim, ["state", "loss_state", "jurisdiction"])),
    sourceFile: clean(getValue(claim, ["source_file", "file_name", "uploaded_file"])),
    underwritingNotes: clean(
      getValue(claim, [
        "underwriting_notes",
        "uw_notes",
        "notes",
        "description",
        "loss_description",
        "claim_description",
      ])
    ),
  };
}

function MetricCard({ label, value, subtext }: { label: string; value: any; subtext?: string }) {
  return (
    <div className="relative overflow-hidden rounded-3xl border border-white/10 bg-white/[0.07] p-5 backdrop-blur-2xl shadow-[0_0_40px_rgba(59,130,246,0.10)]">
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-blue-300/70 to-transparent" />
      <p className="text-xs uppercase tracking-[0.3em] text-blue-300">{label}</p>
      <p className="mt-3 text-2xl font-black text-white">{value}</p>
      {subtext && <p className="mt-2 text-sm text-slate-400">{subtext}</p>}
    </div>
  );
}

function DetailCard({ label, value }: { label: string; value: any }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-slate-950/60 p-4 shadow-inner shadow-blue-950/10">
      <p className="text-xs uppercase tracking-[0.25em] text-blue-300 mb-2">{label}</p>
      <p className="text-base font-semibold text-white break-words">{clean(value)}</p>
    </div>
  );
}

function Pill({ children, tone = "blue" }: { children: React.ReactNode; tone?: "blue" | "green" | "yellow" | "red" | "purple" }) {
  const tones: Record<string, string> = {
    blue: "border-blue-400/30 bg-blue-500/10 text-blue-200",
    green: "border-emerald-400/30 bg-emerald-500/10 text-emerald-200",
    yellow: "border-amber-400/30 bg-amber-500/10 text-amber-200",
    red: "border-red-400/30 bg-red-500/10 text-red-200",
    purple: "border-purple-400/30 bg-purple-500/10 text-purple-200",
  };

  return (
    <span className={`inline-flex rounded-full border px-4 py-2 text-sm font-bold ${tones[tone]}`}>
      {children}
    </span>
  );
}

function Panel({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <section className="relative overflow-hidden rounded-[2rem] border border-white/10 bg-white/[0.07] p-6 md:p-8 backdrop-blur-2xl shadow-[0_0_55px_rgba(15,23,42,0.40)]">
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan-300/60 to-transparent" />
      <div className="mb-6">
        <h2 className="text-2xl font-black text-white">{title}</h2>
        {subtitle && <p className="mt-2 text-sm text-slate-400">{subtitle}</p>}
      </div>
      {children}
    </section>
  );
}

export default function ClaimDetailPage() {
  const router = useRouter();
  const params = useParams();
  const searchParams = useSearchParams();
  const claimId = String(params?.id || "");

  const queryClaimNumber = searchParams?.get("claim_number");
  const queryPolicyNumber = searchParams?.get("policy_number");

  const [claim, setClaim] = useState<AnyObject | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [source, setSource] = useState("");

  function getToken() {
    if (typeof window === "undefined") return null;
    return localStorage.getItem("lossq_token");
  }

  function authHeaders(): Record<string, string> {
    const token = getToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  }

  function clearSession() {
    localStorage.removeItem("lossq_token");
    localStorage.removeItem("lossq_user");
    localStorage.removeItem("lossq_login_time");
    sessionStorage.removeItem("lossq_welcome");
  }

  function backToClaimsTab() {
    router.push("/dashboard?tool=claims");
  }

  useEffect(() => {
    async function loadClaim() {
      const token = getToken();

      if (!token) {
        router.replace("/login?fresh=1");
        return;
      }

      if (!claimId) {
        setMessage("No claim ID found.");
        setLoading(false);
        return;
      }

      try {
        setLoading(true);
        setMessage("");
        setSource("");

        let foundClaim: AnyObject | null = null;

        // 1. Try direct database ID route.
        const detailRes = await fetch(`${API}/claims/${encodeURIComponent(claimId)}`, {
          headers: authHeaders(),
        });

        if (detailRes.status === 401 || detailRes.status === 403) {
          clearSession();
          router.replace("/login?expired=1");
          return;
        }

        if (detailRes.ok) {
          foundClaim = normalizeClaimPayload(await safeJson(detailRes));
          if (foundClaim) setSource("Database claim detail");
        }

        // 2. Try backend claim_number + policy lookup if URL has query params.
        if (!foundClaim && queryClaimNumber) {
          const lookupUrl = new URL(`${API}/claims/lookup`);
          lookupUrl.searchParams.set("claim_number", queryClaimNumber);
          if (queryPolicyNumber) lookupUrl.searchParams.set("policy_number", queryPolicyNumber);

          const lookupRes = await fetch(lookupUrl.toString(), {
            headers: authHeaders(),
          });

          if (lookupRes.ok) {
            foundClaim = normalizeClaimPayload(await safeJson(lookupRes));
            if (foundClaim) setSource("Backend claim lookup");
          }
        }

        // 3. Try claims list from backend.
        if (!foundClaim) {
          const listUrl = new URL(`${API}/claims/`);
          if (queryPolicyNumber) listUrl.searchParams.set("policy_number", queryPolicyNumber);

          const listRes = await fetch(listUrl.toString(), {
            headers: authHeaders(),
          });

          if (listRes.status === 401 || listRes.status === 403) {
            clearSession();
            router.replace("/login?expired=1");
            return;
          }

          if (listRes.ok) {
            const listData = await safeJson(listRes);
            const list = Array.isArray(listData)
              ? listData
              : Array.isArray(listData?.claims)
                ? listData.claims
                : [];

            foundClaim =
              list.find((item: AnyObject) => sameText(item?.id, claimId)) ||
              list.find((item: AnyObject) => sameText(getClaimNumber(item), claimId)) ||
              (queryClaimNumber
                ? list.find(
                    (item: AnyObject) =>
                      sameText(getClaimNumber(item), queryClaimNumber) &&
                      (!queryPolicyNumber || sameText(getPolicyNumber(item), queryPolicyNumber))
                  )
                : null) ||
              null;

            if (foundClaim) setSource("Backend claims list");
          }
        }

        // 4. Last fallback: local/session storage, so stale numeric IDs do not
        // create a dead page when the visible claim row has the real claim data.
        if (!foundClaim) {
          foundClaim = findStoredClaim(claimId, queryClaimNumber, queryPolicyNumber);
          if (foundClaim) setSource("Dashboard cached claim preview");
        }

        if (!foundClaim) {
          setClaim(null);
          setMessage(
            "Claim could not be loaded. Re-open the Claims tab, or re-upload the loss run after the backend deployment finishes so the claim receives a saved database ID."
          );
          return;
        }

        setClaim(foundClaim);
      } catch (error: any) {
        setClaim(null);
        setMessage(`Claim could not be loaded. ${error?.message || "Unknown error"}`);
      } finally {
        setLoading(false);
      }
    }

    loadClaim();
  }, [claimId, queryClaimNumber, queryPolicyNumber]);

  const display = useMemo(() => getClaimDisplay(claim, queryClaimNumber || claimId), [claim, claimId, queryClaimNumber]);

  const litigationTone = display.litigation ? "red" : "green";
  const statusTone = display.status.toLowerCase().includes("open") ? "yellow" : "green";
  const severityTone =
    display.severity === "High" ? "red" : display.severity === "Moderate" ? "yellow" : "green";
  const reserveTone =
    display.reservePressure === "High" ? "red" : display.reservePressure === "Moderate" ? "yellow" : "green";

  if (loading) {
    return (
      <main className="min-h-screen bg-[#020617] text-white flex items-center justify-center px-6">
        <div className="fixed inset-0 bg-[radial-gradient(circle_at_top_left,#1d4ed866,transparent_28%),radial-gradient(circle_at_top_right,#0ea5e955,transparent_30%),radial-gradient(circle_at_bottom,#312e8155,transparent_35%)]" />
        <div className="relative text-center">
          <div className="mx-auto mb-5 h-14 w-14 animate-spin rounded-full border-4 border-blue-400/20 border-t-blue-400 shadow-[0_0_35px_rgba(96,165,250,0.55)]" />
          <h1 className="text-3xl font-black">Loading Claim Intelligence...</h1>
          <p className="text-slate-400 mt-2">Pulling claim detail, financials, and litigation signals.</p>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#020617] text-white overflow-hidden">
      <div className="fixed inset-0 bg-[radial-gradient(circle_at_top_left,#1d4ed866,transparent_28%),radial-gradient(circle_at_top_right,#0ea5e955,transparent_30%),radial-gradient(circle_at_bottom,#312e8155,transparent_35%)]" />
      <div className="fixed inset-0 bg-[linear-gradient(to_right,rgba(255,255,255,0.04)_1px,transparent_1px),linear-gradient(to_bottom,rgba(255,255,255,0.04)_1px,transparent_1px)] bg-[size:72px_72px] opacity-20" />
      <div className="fixed left-1/2 top-16 h-72 w-72 -translate-x-1/2 rounded-full bg-cyan-500/10 blur-3xl" />

      <section className="relative mx-auto max-w-7xl px-5 md:px-8 py-8 pb-20">
        <button
          onClick={backToClaimsTab}
          className="mb-8 rounded-2xl border border-white/10 bg-white/5 px-5 py-3 text-sm font-bold text-slate-200 backdrop-blur-xl hover:border-blue-300/50 hover:bg-blue-500/10 hover:text-white"
        >
          ← Back to Claims Tab
        </button>

        <header className="mb-8 rounded-[2rem] border border-white/10 bg-slate-950/70 p-6 md:p-8 backdrop-blur-2xl shadow-[0_0_70px_rgba(59,130,246,0.12)]">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-cyan-400/30 bg-cyan-500/10 px-4 py-2 text-sm text-cyan-200">
                <span className="h-2 w-2 rounded-full bg-cyan-300 shadow-[0_0_18px_#67e8f9]" />
                Claim Intelligence File
              </div>

              <p className="text-sm uppercase tracking-[0.35em] text-blue-300">
                Claim Analysis
              </p>

              <h1 className="mt-3 text-4xl md:text-6xl font-black tracking-tight">
                {display.claimNumber}
              </h1>

              <p className="mt-4 max-w-3xl text-slate-300">
                Modern claim detail view with underwriting context, litigation factor,
                financial pressure, reserve status, and source claim fields.
              </p>

              {source && (
                <p className="mt-3 text-xs text-slate-500">
                  Source: {source}
                </p>
              )}
            </div>

            <div className="grid grid-cols-2 gap-3 min-w-[280px]">
              <Pill tone={statusTone}>{display.status}</Pill>
              <Pill tone={severityTone}>{display.severity} Severity</Pill>
              <Pill tone={litigationTone}>
                {display.litigation ? "Litigation Present" : "No Litigation"}
              </Pill>
              <Pill tone={reserveTone}>{display.reservePressure} Reserve Pressure</Pill>
            </div>
          </div>
        </header>

        {message && (
          <div className="mb-6 rounded-3xl border border-red-400/30 bg-red-500/10 p-5 text-red-100">
            {message}
          </div>
        )}

        {!claim && !message && (
          <Panel title="No Claim Data Found">
            <p className="text-slate-300">LossQ could not find a matching claim for this detail page.</p>
          </Panel>
        )}

        {claim && (
          <>
            <section className="grid grid-cols-1 md:grid-cols-4 gap-5 mb-8">
              <MetricCard label="Total Incurred" value={money(display.totalIncurred)} />
              <MetricCard label="Paid" value={money(display.paid)} />
              <MetricCard label="Reserve" value={money(display.reserve)} />
              <MetricCard
                label="Litigation Factor"
                value={display.litigation ? "High" : "Low"}
                subtext={display.litigation ? "Attorney / suit signal detected" : "No litigation signal detected"}
              />
            </section>

            <section className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
              <div className="lg:col-span-2">
                <Panel title="Claim Overview" subtitle="Core claim information pulled from the selected loss-run record.">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <DetailCard label="Claim Number" value={display.claimNumber} />
                    <DetailCard label="Policy Number" value={display.policyNumber} />
                    <DetailCard label="Line of Business" value={display.lineOfBusiness} />
                    <DetailCard label="Status" value={display.status} />
                    <DetailCard label="Loss Date" value={display.lossDate} />
                    <DetailCard label="Reported Date" value={display.reportedDate} />
                    <DetailCard label="Claimant" value={display.claimant} />
                    <DetailCard label="Cause of Loss" value={display.causeOfLoss} />
                    <DetailCard label="Adjuster / Examiner" value={display.adjuster} />
                    <DetailCard label="Jurisdiction / State" value={display.state} />
                  </div>
                </Panel>
              </div>

              <Panel title="Risk Signals" subtitle="Fast underwriting indicators for this individual claim.">
                <div className="space-y-4">
                  <DetailCard label="Severity Level" value={display.severity} />
                  <DetailCard label="Reserve Pressure" value={display.reservePressure} />
                  <DetailCard
                    label="Litigation Factor"
                    value={
                      display.litigation
                        ? clean(display.litigationRaw || "Litigation / attorney involvement detected")
                        : "No litigation flag detected"
                    }
                  />
                  <DetailCard label="Source File" value={display.sourceFile} />
                </div>
              </Panel>
            </section>

            <section className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
              <Panel title="Financial Breakdown" subtitle="Paid, reserve, and incurred values used for severity review.">
                <div className="grid grid-cols-1 gap-4">
                  <DetailCard label="Paid Amount" value={money(display.paid)} />
                  <DetailCard label="Case Reserve" value={money(display.reserve)} />
                  <DetailCard label="Total Incurred" value={money(display.totalIncurred)} />
                </div>
              </Panel>

              <Panel title="Loss Narrative" subtitle="Claim description, loss cause, or underwriting notes.">
                <div className="rounded-2xl border border-white/10 bg-slate-950/60 p-5 text-slate-300 leading-7">
                  {display.underwritingNotes !== "-"
                    ? display.underwritingNotes
                    : "No underwriting notes are available for this claim yet."}
                </div>
              </Panel>
            </section>

            <Panel title="Underwriting Position" subtitle="LossQ working view for how this claim may affect renewal or market appetite.">
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                <div className="rounded-2xl border border-white/10 bg-slate-950/60 p-5">
                  <p className="text-xs uppercase tracking-[0.25em] text-blue-300 mb-3">Carrier Concern</p>
                  <p className="text-slate-300 leading-7">
                    {display.litigation
                      ? "Litigation or attorney involvement may increase underwriting scrutiny and reserve review."
                      : display.reserve > 0
                        ? "Open reserve should be validated before renewal submission."
                        : "No major litigation or reserve concern detected from the available fields."}
                  </p>
                </div>

                <div className="rounded-2xl border border-white/10 bg-slate-950/60 p-5">
                  <p className="text-xs uppercase tracking-[0.25em] text-blue-300 mb-3">Broker Action</p>
                  <p className="text-slate-300 leading-7">
                    {display.litigation
                      ? "Request current adjuster notes, demand status, defense posture, and expected resolution."
                      : display.reserve > 0
                        ? "Confirm whether the reserve is current and whether closure is expected before marketing."
                        : "Keep this claim in the loss summary and confirm final paid status."}
                  </p>
                </div>

                <div className="rounded-2xl border border-white/10 bg-slate-950/60 p-5">
                  <p className="text-xs uppercase tracking-[0.25em] text-blue-300 mb-3">Renewal Impact</p>
                  <p className="text-slate-300 leading-7">
                    {display.severity === "High"
                      ? "High-severity claim. Expect pricing, appetite, or underwriting questions."
                      : display.severity === "Moderate"
                        ? "Moderate claim impact. Include context and mitigation in the renewal story."
                        : "Low-severity signal based on available paid, reserve, and litigation fields."}
                  </p>
                </div>
              </div>
            </Panel>

            <div className="mt-6">
              <Panel
                title="Claim Data Quality"
                subtitle="Clean validation summary for this claim record."
              >
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <DetailCard
                    label="Record Status"
                    value={display.claimNumber !== "-" ? "Claim loaded successfully" : "Needs review"}
                  />
                  <DetailCard
                    label="Financial Mapping"
                    value={display.totalIncurred === display.paid + display.reserve ? "Balanced" : "Review totals"}
                  />
                  <DetailCard
                    label="Backend Source"
                    value={source || "Normalized LossQ claim record"}
                  />
                </div>
              </Panel>
            </div>
          </>
        )}
      </section>
    </main>
  );
}

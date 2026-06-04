"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

const API =
  process.env.NEXT_PUBLIC_API_URL || "https://lossq-production.up.railway.app";

const SESSION_TIMEOUT_MS = 1000 * 60 * 60 * 24;
const PROFILE_CACHE_KEY = "lossq_account_profiles";

type AnyObject = Record<string, any>;

type ToolKey =
  | "overview"
  | "profiles"
  | "upload"
  | "renewal-risk"
  | "decision"
  | "carrier-appetite"
  | "submission-readiness"
  | "carrier-match"
  | "premium-forecast"
  | "submission-builder"
  | "summary"
  | "memo"
  | "charts"
  | "claims";

async function safeJson(res: Response) {
  try {
    return await res.json();
  } catch {
    return null;
  }
}

function objectToChartData(data: Record<string, number>) {
  return Object.entries(data || {}).map(([name, value]) => ({
    name,
    value: Number(value || 0),
  }));
}


function normalizePolicyNumber(value: any) {
  return String(value || "").trim().toUpperCase();
}

function getClaimPolicyNumber(claim: any) {
  return normalizePolicyNumber(
    claim?.policy_number ||
      claim?.policyNumber ||
      claim?.policy_no ||
      claim?.policy ||
      claim?.policy_id
  );
}

function toMoneyNumber(value: any) {
  if (value === null || value === undefined || value === "") return 0;

  const cleaned = String(value).replace(/[$,]/g, "").trim();
  const parsed = Number(cleaned);

  return Number.isFinite(parsed) ? parsed : 0;
}

function getClaimIncurred(claim: any) {
  const direct =
    claim?.total_incurred ??
    claim?.totalIncurred ??
    claim?.incurred ??
    claim?.incurred_amount ??
    claim?.loss_amount ??
    claim?.amount;

  const directValue = toMoneyNumber(direct);

  if (directValue > 0) return directValue;

  return (
    toMoneyNumber(claim?.paid_amount || claim?.paid || claim?.paid_loss) +
    toMoneyNumber(claim?.reserve_amount || claim?.reserve || claim?.outstanding_reserve)
  );
}


function getClaimPaid(claim: any) {
  return toMoneyNumber(claim?.paid_amount || claim?.paid || claim?.total_paid || claim?.paid_loss);
}

function getClaimReserve(claim: any) {
  return toMoneyNumber(
    claim?.reserve_amount ||
      claim?.reserve ||
      claim?.total_reserved ||
      claim?.outstanding_reserve ||
      claim?.case_reserve
  );
}

function getClaimStatus(claim: any) {
  return String(claim?.status || claim?.claim_status || "").trim().toLowerCase();
}

function isOpenClaim(claim: any) {
  return ["open", "reopened", "re-opened", "pending", "active"].includes(
    getClaimStatus(claim)
  );
}

function isClosedClaim(claim: any) {
  return ["closed", "close"].includes(getClaimStatus(claim));
}

function boolLike(value: any) {
  if (typeof value === "boolean") return value;
  const normalized = String(value || "").trim().toLowerCase();
  return ["true", "yes", "y", "1", "litigation", "litigated", "suit", "attorney"].includes(
    normalized
  );
}

function hasClaimLitigation(claim: any) {
  return (
    boolLike(claim?.litigation) ||
    boolLike(claim?.is_litigated) ||
    boolLike(claim?.attorney_assigned) ||
    boolLike(claim?.suit_filed) ||
    String(claim?.litigation_status || "").toLowerCase().includes("litigation") ||
    String(claim?.description || "").toLowerCase().includes("attorney") ||
    String(claim?.description || "").toLowerCase().includes("counsel")
  );
}

function isFlaggedClaim(claim: any) {
  return (
    boolLike(claim?.flagged) ||
    Boolean(claim?.flag) ||
    hasClaimLitigation(claim) ||
    getClaimIncurred(claim) >= 100000 ||
    getClaimReserve(claim) >= 25000
  );
}

function getClaimLineOfBusiness(claim: any) {
  return (
    String(
      claim?.line_of_business ||
        claim?.lob ||
        claim?.coverage ||
        claim?.coverage_line ||
        claim?.claim_type ||
        "Unclassified"
    ).trim() || "Unclassified"
  );
}

function getClaimLossDate(claim: any) {
  return String(
    claim?.date_of_loss ||
      claim?.loss_date ||
      claim?.dol ||
      claim?.accident_date ||
      ""
  ).trim();
}

function getClaimYear(claim: any) {
  const raw = getClaimLossDate(claim);
  const match = raw.match(/(\d{4})|(\d{1,2})[\/-](\d{1,2})[\/-](\d{2,4})/);

  if (!match) return "Unknown";

  if (match[1]) return match[1];

  const year = match[4] || "";
  return year.length === 2 ? `20${year}` : year || "Unknown";
}

function daysSinceClaim(claim: any) {
  const raw = getClaimLossDate(claim);
  const parsed = raw ? new Date(raw) : null;

  if (!parsed || Number.isNaN(parsed.getTime())) {
    return 0;
  }

  return Math.max(
    0,
    Math.floor((Date.now() - parsed.getTime()) / (1000 * 60 * 60 * 24))
  );
}

function incrementChartValue(
  source: Record<string, number>,
  key: string,
  value: number
) {
  source[key] = Number(source[key] || 0) + Number(value || 0);
}

function buildLocalDashboardIntelligence(visibleClaims: any[]) {
  const totalClaims = visibleClaims.length;
  const openClaims = visibleClaims.filter(isOpenClaim).length;
  const closedClaims = visibleClaims.filter(isClosedClaim).length;
  const litigationClaims = visibleClaims.filter(hasClaimLitigation).length;
  const flaggedClaims = visibleClaims.filter(isFlaggedClaim).length;
  const totalPaid = visibleClaims.reduce((sum, claim) => sum + getClaimPaid(claim), 0);
  const totalReserve = visibleClaims.reduce((sum, claim) => sum + getClaimReserve(claim), 0);
  const totalIncurred = visibleClaims.reduce((sum, claim) => sum + getClaimIncurred(claim), 0);
  const largestLoss = Math.max(0, ...visibleClaims.map((claim) => getClaimIncurred(claim)));
  const averageSeverity = totalClaims ? totalIncurred / totalClaims : 0;
  const openClaimPercentage = totalClaims ? (openClaims / totalClaims) * 100 : 0;
  const largeClaims = visibleClaims.filter((claim) => getClaimIncurred(claim) >= 100000).length;
  const severeClaims = visibleClaims.filter((claim) => getClaimIncurred(claim) >= 250000).length;
  const highReserveClaims = visibleClaims.filter((claim) => getClaimReserve(claim) >= 25000).length;

  const incurredByYear: Record<string, number> = {};
  const incurredByLine: Record<string, number> = {};
  const openClaimAging: Record<string, number> = {
    "0-30 Days": 0,
    "31-90 Days": 0,
    "91-180 Days": 0,
    "181+ Days": 0,
  };
  const severityDistribution: Record<string, number> = {
    "Under $25k": 0,
    "$25k-$99k": 0,
    "$100k-$249k": 0,
    "$250k+": 0,
  };

  visibleClaims.forEach((claim) => {
    const incurred = getClaimIncurred(claim);
    incrementChartValue(incurredByYear, getClaimYear(claim), incurred);
    incrementChartValue(incurredByLine, getClaimLineOfBusiness(claim), incurred);

    if (isOpenClaim(claim)) {
      const age = daysSinceClaim(claim);
      if (age <= 30) openClaimAging["0-30 Days"] += 1;
      else if (age <= 90) openClaimAging["31-90 Days"] += 1;
      else if (age <= 180) openClaimAging["91-180 Days"] += 1;
      else openClaimAging["181+ Days"] += 1;
    }

    if (incurred >= 250000) severityDistribution["$250k+"] += 1;
    else if (incurred >= 100000) severityDistribution["$100k-$249k"] += 1;
    else if (incurred >= 25000) severityDistribution["$25k-$99k"] += 1;
    else severityDistribution["Under $25k"] += 1;
  });

  let renewalScore = 100;
  renewalScore -= Math.min(totalClaims * 3, 22);
  renewalScore -= Math.min(openClaims * 7, 28);
  renewalScore -= Math.min(litigationClaims * 12, 36);
  renewalScore -= Math.min(flaggedClaims * 4, 20);
  renewalScore -= Math.min(largeClaims * 10, 25);
  renewalScore -= Math.min(severeClaims * 15, 35);
  renewalScore -= Math.min(highReserveClaims * 5, 20);

  if (totalIncurred >= 1000000) renewalScore -= 25;
  else if (totalIncurred >= 500000) renewalScore -= 18;
  else if (totalIncurred >= 250000) renewalScore -= 10;
  else if (totalIncurred >= 100000) renewalScore -= 5;

  if (totalReserve >= 500000) renewalScore -= 20;
  else if (totalReserve >= 250000) renewalScore -= 14;
  else if (totalReserve >= 100000) renewalScore -= 8;
  else if (totalReserve >= 50000) renewalScore -= 4;

  if (averageSeverity >= 250000) renewalScore -= 20;
  else if (averageSeverity >= 100000) renewalScore -= 12;
  else if (averageSeverity >= 50000) renewalScore -= 6;

  if (openClaimPercentage >= 50) renewalScore -= 8;
  else if (openClaimPercentage >= 25) renewalScore -= 4;

  renewalScore = Math.max(0, Math.min(100, Math.round(renewalScore)));

  const renewalRiskLevel =
    renewalScore >= 80
      ? "Low"
      : renewalScore >= 60
      ? "Moderate"
      : renewalScore >= 40
      ? "High"
      : "Critical";

  const renewalProbability = Math.max(
    0,
    Math.min(
      100,
      renewalScore -
        (openClaims >= 3 ? 8 : 0) -
        (litigationClaims > 0 ? 10 : 0) -
        (severeClaims > 0 ? 10 : 0)
    )
  );

  let appetiteScore = renewalProbability;
  appetiteScore -= litigationClaims > 0 ? 8 : 0;
  appetiteScore -= severeClaims > 0 ? 10 : 0;
  appetiteScore -= openClaims >= 3 ? 6 : 0;
  appetiteScore -= totalReserve >= 250000 ? 10 : totalReserve >= 100000 ? 5 : 0;
  appetiteScore -= totalClaims >= 10 ? 8 : totalClaims >= 5 ? 4 : 0;
  appetiteScore = Math.max(0, Math.min(100, Math.round(appetiteScore)));

  const appetiteLevel =
    appetiteScore >= 85
      ? "Preferred"
      : appetiteScore >= 70
      ? "Strong"
      : appetiteScore >= 55
      ? "Moderate"
      : appetiteScore >= 40
      ? "Limited"
      : "Distressed";

  const expectedPremiumImpact =
    renewalProbability >= 85
      ? "Flat to +5%"
      : renewalProbability >= 70
      ? "+5% to +15%"
      : renewalProbability >= 50
      ? "+15% to +35%"
      : "+35% or higher / possible non-renewal concern";

  const marketabilityScore = appetiteScore;

  const estimatedCurrentPremium =
    totalClaims === 0 ? 0 : Math.max(25000, Math.round(totalIncurred * 0.55 + 60000));
  const lossRatio = estimatedCurrentPremium ? totalIncurred / estimatedCurrentPremium : 0;

  let expectedIncrease = 3;

  if (lossRatio >= 2) expectedIncrease += 35;
  else if (lossRatio >= 1.25) expectedIncrease += 25;
  else if (lossRatio >= 0.75) expectedIncrease += 15;
  else if (lossRatio >= 0.5) expectedIncrease += 8;
  else if (lossRatio <= 0.2) expectedIncrease -= 2;

  if (totalClaims >= 10) expectedIncrease += 12;
  else if (totalClaims >= 5) expectedIncrease += 7;
  else if (totalClaims >= 3) expectedIncrease += 4;

  if (largestLoss >= 250000) expectedIncrease += 15;
  else if (largestLoss >= 100000) expectedIncrease += 8;
  else if (largestLoss >= 50000) expectedIncrease += 4;

  expectedIncrease += Math.min(openClaims * 4, 16);
  expectedIncrease += openClaimPercentage >= 50 ? 8 : openClaimPercentage >= 25 ? 4 : 0;
  expectedIncrease += Math.min(litigationClaims * 10, 25);
  expectedIncrease += totalReserve >= 250000 ? 12 : totalReserve >= 100000 ? 8 : totalReserve >= 25000 ? 4 : 0;

  if (renewalScore < 50) expectedIncrease += 15;
  else if (renewalScore < 70) expectedIncrease += 8;

  if (marketabilityScore < 50) expectedIncrease += 10;
  else if (marketabilityScore < 70) expectedIncrease += 5;

  expectedIncrease = Math.max(-5, Math.min(95, Math.round(expectedIncrease)));

  const bestCasePercent = Math.max(-5, expectedIncrease - 10);
  const worstCasePercent = Math.min(125, expectedIncrease + 20);
  const expectedRenewalPremium = Math.round(
    estimatedCurrentPremium * (1 + expectedIncrease / 100)
  );
  const confidenceScore =
    totalClaims === 0 ? 0 : Math.max(35, Math.min(92, 70 + (totalClaims >= 3 ? 8 : 0) + (totalReserve > 0 ? 5 : 0)));

  const renewalDrivers = [
    totalClaims > 0
      ? `${totalClaims} account-specific claim(s) identified.`
      : "No verified claims are attached to this account.",
    openClaims > 0 ? `${openClaims} open claim(s) may continue to develop.` : "",
    litigationClaims > 0 ? `${litigationClaims} litigated claim(s) create renewal uncertainty.` : "",
    totalIncurred > 0 ? `Total incurred losses are $${totalIncurred.toLocaleString()}.` : "",
    totalReserve > 0 ? `Outstanding reserves total $${totalReserve.toLocaleString()}.` : "",
    largeClaims > 0 ? `${largeClaims} large claim(s) exceed $100,000.` : "",
  ].filter(Boolean);

  const carrierConcerns = [
    openClaims > 0 ? "Open claims may continue developing before renewal." : "",
    totalReserve >= 50000 ? "Outstanding reserves may pressure pricing and terms." : "",
    litigationClaims > 0 ? "Litigation increases uncertainty around ultimate severity." : "",
    totalClaims >= 5 ? "Claim frequency may raise carrier concerns." : "",
    largeClaims > 0 ? "Large losses require corrective-action documentation." : "",
  ].filter(Boolean);

  if (carrierConcerns.length === 0) {
    carrierConcerns.push("No major carrier concerns detected from verified claim data.");
  }

  const brokerRecommendation =
    renewalRiskLevel === "Low"
      ? "Proceed with standard renewal marketing and highlight favorable loss performance."
      : renewalRiskLevel === "Moderate"
      ? "Prepare a broker narrative explaining open claims, reserves, and corrective actions before marketing."
      : renewalRiskLevel === "High"
      ? "Build a detailed renewal strategy with claim narratives, reserve updates, litigation status, and loss-control documentation."
      : "Treat as a critical renewal. Obtain updated claim narratives, litigation updates, reserve explanations, and a corrective-action plan before approaching markets.";

  const renewalSummary = `The selected account has a renewal score of ${renewalScore}/100, indicating ${renewalRiskLevel.toLowerCase()} renewal risk. The score is based on ${totalClaims} claim(s), ${openClaims} open claim(s), $${totalIncurred.toLocaleString()} in total incurred losses, $${totalReserve.toLocaleString()} in reserves, and ${litigationClaims} litigated claim(s).`;

  const carrierMatches = [
    { carrier: "Travelers", base: 88, reason: "Strong middle-market appetite" },
    { carrier: "Liberty Mutual", base: 85, reason: "Broad commercial appetite" },
    { carrier: "Nationwide", base: 83, reason: "Good frequency tolerance" },
    { carrier: "The Hartford", base: 82, reason: "Commercial package and middle-market underwriting" },
    { carrier: "Chubb", base: 81, reason: "Quality risk selection and controlled loss performance" },
    { carrier: "Hanover", base: 80, reason: "Regional underwriting flexibility" },
    { carrier: "Zurich", base: 79, reason: "Complex commercial underwriting" },
    { carrier: "CNA", base: 78, reason: "Strong risk-control focus" },
    { carrier: "Progressive Commercial", base: 74, reason: "Commercial auto focus" },
    { carrier: "Berkley", base: 72, reason: "Specialty commercial underwriting" },
  ]
    .map((carrier) => {
      const score = Math.max(
        0,
        Math.min(
          100,
          Math.round(carrier.base + (appetiteScore - 70) * 0.25 + (renewalProbability - 70) * 0.15)
        )
      );

      const fit =
        score >= 85 ? "Excellent" : score >= 75 ? "Strong" : score >= 65 ? "Moderate" : "Limited";

      return {
        carrier: carrier.carrier,
        match_score: score,
        fit,
        reason:
          fit === "Limited"
            ? `${carrier.reason}; limited by current loss frequency, reserves, litigation, or severity.`
            : carrier.reason,
      };
    })
    .sort((a, b) => b.match_score - a.match_score);

  const forecastDrivers = [
    `Estimated loss ratio: ${(lossRatio * 100).toFixed(1)}%`,
    `${totalClaims} account-specific claim(s)`,
    openClaims ? `${openClaims} open claim(s)` : "",
    litigationClaims ? `${litigationClaims} litigated claim(s)` : "",
    largestLoss ? `Largest loss: $${largestLoss.toLocaleString()}` : "",
    totalReserve ? `Reserve exposure: $${totalReserve.toLocaleString()}` : "",
    renewalScore < 70 ? `Renewal score pressure: ${renewalScore}/100` : "",
  ].filter(Boolean);

  return {
    totalClaims,
    openClaims,
    closedClaims,
    litigationClaims,
    flaggedClaims,
    totalPaid,
    totalReserve,
    totalIncurred,
    largestLoss,
    averageSeverity,
    renewalScore,
    renewalRiskLevel,
    renewalProbability,
    appetiteScore,
    appetiteLevel,
    expectedPremiumImpact,
    marketabilityScore,
    renewalDrivers,
    carrierConcerns,
    brokerRecommendation,
    renewalSummary,
    carrierMatches,
    currentPremium: estimatedCurrentPremium,
    expectedRenewalPremium,
    expectedIncrease,
    bestCasePercent,
    worstCasePercent,
    confidenceScore,
    likelyRangePercent: `${bestCasePercent}% to ${worstCasePercent}%`,
    forecastDrivers,
    forecastSummary:
      totalClaims === 0
        ? "No premium forecast is available because no verified claims are attached to the active account."
        : `LossQ projects an expected renewal premium of $${expectedRenewalPremium.toLocaleString()}, representing an estimated ${expectedIncrease}% change from the modeled current premium of $${estimatedCurrentPremium.toLocaleString()}. Forecast confidence is ${confidenceScore}%. The projection is driven by loss ratio, claim frequency, severity, open claim load, litigation, reserve pressure, renewal score, and claim trend.`,
    reservePressure:
      totalReserve >= 250000 ? "Critical" : totalReserve >= 100000 ? "High" : totalReserve >= 50000 ? "Moderate" : "Low",
    trendNote:
      totalClaims === 0
        ? "No trend intelligence available because no verified claims are attached to the account."
        : `LossQ is charting ${totalClaims} verified claim(s), ${openClaims} open claim(s), ${litigationClaims} litigated claim(s), and $${totalIncurred.toLocaleString()} in total incurred losses from the active account policy schedule.`,
    lossTrendData: objectToChartData(incurredByYear),
    agingData: objectToChartData(openClaimAging),
    severityData: objectToChartData(severityDistribution),
    lineData: objectToChartData(incurredByLine),
  };
}

function moneyDisplay(value: any) {
  return `$${Number(value || 0).toLocaleString()}`;
}

function dataUnavailableText(hasActiveAccount: boolean) {
  return hasActiveAccount
    ? "LossQ does not have verified claims attached to this account yet. Upload or review the loss run before relying on underwriting outputs."
    : "Select or upload an account before generating underwriting intelligence.";
}


function normalizeProfiles(data: any): AnyObject[] {
  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.profiles)) return data.profiles;
  if (Array.isArray(data?.accounts)) return data.accounts;
  if (data && typeof data === "object" && data.policy_number) return [data];
  return [];
}

function getCachedProfiles(): AnyObject[] {
  if (typeof window === "undefined") return [];

  try {
    const raw = localStorage.getItem(PROFILE_CACHE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function setCachedProfiles(profiles: AnyObject[]) {
  if (typeof window === "undefined") return;
  localStorage.setItem(PROFILE_CACHE_KEY, JSON.stringify(profiles));
}

function mergeProfiles(existing: AnyObject[], incoming: AnyObject[]) {
  const map = new Map<string, AnyObject>();

  existing.forEach((item) => {
    const key = item?.policy_number || item?.id;
    if (key) map.set(String(key), item);
  });

  incoming.forEach((item) => {
    const key = item?.policy_number || item?.id;
    if (key) {
      map.set(String(key), {
        ...(map.get(String(key)) || {}),
        ...item,
      });
    }
  });

  return Array.from(map.values());
}

export default function DashboardPage() {
  const router = useRouter();

  const [activeTool, setActiveTool] = useState<ToolKey>("overview");

  const [claims, setClaims] = useState<any[]>([]);
  const [summary, setSummary] = useState<any>({});
  const [decision, setDecision] = useState<any>({});
  const [carrierAppetite, setCarrierAppetite] = useState<any>({});
  const [submissionReadiness, setSubmissionReadiness] = useState<any>({});
  const [carrierMatch, setCarrierMatch] = useState<any>({});
  const [premiumForecast, setPremiumForecast] = useState<any>({});
  const [submissionBuilder, setSubmissionBuilder] = useState<any>({});
  const [timeline, setTimeline] = useState<any>({});
  const [profile, setProfile] = useState<any>({});
  const [profiles, setProfiles] = useState<any[]>([]);
  const [files, setFiles] = useState<FileList | null>(null);

  const [message, setMessage] = useState("");
  const [authReady, setAuthReady] = useState(false);
  const [dashboardLoading, setDashboardLoading] = useState(true);
  const [dashboardError, setDashboardError] = useState("");

  const [copilotOpen, setCopilotOpen] = useState(false);
  const [copilotQuestion, setCopilotQuestion] = useState("");
  const [copilotAnswer, setCopilotAnswer] = useState("");
  const [copilotLoading, setCopilotLoading] = useState(false);

  const [renewalMemo, setRenewalMemo] = useState("");
  const [memoLoading, setMemoLoading] = useState(false);

  useEffect(() => {
    async function validateSession() {
      const token = localStorage.getItem("lossq_token");
      const loginTime = localStorage.getItem("lossq_login_time");

      if (!token) {
        router.replace("/login?fresh=1");
        return;
      }

      if (!loginTime) {
        localStorage.setItem("lossq_login_time", Date.now().toString());
      }

      if (loginTime) {
        const expired = Date.now() - Number(loginTime) > SESSION_TIMEOUT_MS;

        if (expired) {
          clearSession();
          router.replace("/login?expired=1");
          return;
        }
      }

      try {
        const validateRes = await fetch(`${API}/auth/validate`, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });

        if (validateRes.status === 401 || validateRes.status === 403) {
          clearSession();
          router.replace("/login?expired=1");
          return;
        }
      } catch {
        setMessage("Session validation skipped. Backend validation unavailable.");
      }

      setAuthReady(true);
      await loadDashboard();
    }

    validateSession();
  }, []);

  function clearSession() {
    localStorage.removeItem("lossq_token");
    localStorage.removeItem("lossq_user");
    localStorage.removeItem("lossq_login_time");
    sessionStorage.removeItem("lossq_welcome");
  }

  function getToken() {
    if (typeof window === "undefined") return null;
    return localStorage.getItem("lossq_token");
  }

  function authHeaders(): Record<string, string> {
    const token = getToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  }

  function updateProfileList(incomingProfiles: AnyObject[]) {
    setProfiles((prev) => {
      const merged = mergeProfiles(prev, incomingProfiles);
      setCachedProfiles(merged);
      return merged;
    });
  }

  async function loadProfileList() {
    const cached = getCachedProfiles();

    if (cached.length > 0) {
      setProfiles(cached);
    }

    try {
      const profilesRes = await fetch(`${API}/account-profile/all`, {
        headers: authHeaders(),
      });

      if (profilesRes.status === 401 || profilesRes.status === 403) {
        clearSession();
        router.replace("/login?expired=1");
        return cached;
      }

      if (profilesRes.ok) {
        const profilesData = await safeJson(profilesRes);
        const normalized = normalizeProfiles(profilesData);

        if (normalized.length > 0) {
          const merged = mergeProfiles(cached, normalized);
          setProfiles(merged);
          setCachedProfiles(merged);
          return merged;
        }
      }
    } catch {
      if (cached.length > 0) {
        setMessage("Loaded saved account workspace. Backend profile list unavailable.");
      }
    }

    return cached;
  }

  function newBlankProfile() {
    setProfile({
      business_name: "",
      carrier_name: "",
      agency_name: "",
      policy_number: "",
      effective_date: "",
      expiration_date: "",
      evaluation_date: "",
    });

    setClaims([]);
    setSummary({});
    setDecision({});
    setCarrierAppetite({});
    setSubmissionReadiness({});
    setCarrierMatch({});
    setTimeline({});
    setRenewalMemo("");
    setCopilotAnswer("");
    setMessage("New blank account profile started.");
    setActiveTool("profiles");
  }

  async function loadDashboard(policyNumberOverride?: string) {
    if (!getToken()) {
      router.replace("/login?fresh=1");
      return;
    }

    setDashboardLoading(true);
    setDashboardError("");

    try {
      await loadProfileList();

      let activeProfile = profile;

      if (policyNumberOverride) {
        const selectedRes = await fetch(
          `${API}/account-profile/policy/${encodeURIComponent(policyNumberOverride)}`,
          { headers: authHeaders() }
        );

        if (selectedRes.status === 401 || selectedRes.status === 403) {
          clearSession();
          router.replace("/login?expired=1");
          return;
        }

        if (selectedRes.ok) {
          const fetchedProfile = (await safeJson(selectedRes)) || {};
          const cachedMatch = getCachedProfiles().find(
            (item) => item?.policy_number === policyNumberOverride
          );

          activeProfile = {
            ...(cachedMatch || {}),
            ...fetchedProfile,
            policies:
              fetchedProfile?.policies ||
              cachedMatch?.policies ||
              profile?.policies ||
              [],
            validation:
              fetchedProfile?.validation ||
              cachedMatch?.validation ||
              profile?.validation ||
              {},
          };

          setProfile(activeProfile || {});
          if (activeProfile?.policy_number) {
            updateProfileList([activeProfile]);
          }
        } else {
          const cachedMatch = getCachedProfiles().find(
            (item) => item?.policy_number === policyNumberOverride
          );

          if (cachedMatch) {
            activeProfile = cachedMatch;
            setProfile(cachedMatch);
          }
        }
      } else {
        const profileRes = await fetch(`${API}/account-profile/`, {
          headers: authHeaders(),
        });

        if (profileRes.status === 401 || profileRes.status === 403) {
          clearSession();
          router.replace("/login?expired=1");
          return;
        }

        if (profileRes.ok) {
          const fetchedProfile = (await safeJson(profileRes)) || {};
          const cachedMatch = getCachedProfiles().find(
            (item) => item?.policy_number === fetchedProfile?.policy_number
          );

          activeProfile = {
            ...(cachedMatch || {}),
            ...fetchedProfile,
            policies:
              fetchedProfile?.policies ||
              cachedMatch?.policies ||
              profile?.policies ||
              [],
            validation:
              fetchedProfile?.validation ||
              cachedMatch?.validation ||
              profile?.validation ||
              {},
          };

          setProfile(activeProfile || {});
          if (activeProfile?.policy_number) {
            updateProfileList([activeProfile]);
          }
        } else {
          const cachedProfiles = getCachedProfiles();
          if (cachedProfiles.length > 0 && !activeProfile?.policy_number) {
            activeProfile = cachedProfiles[0];
            setProfile(cachedProfiles[0]);
          }
        }
      }

      const policyNumber =
        policyNumberOverride ||
        activeProfile?.policy_number ||
        profile?.policy_number ||
        "";

      const hasPolicy = policyNumber && policyNumber !== "Policy Not Set";

      /*
        Always fetch all organization claims here.
        The dashboard filters locally through visibleClaims so account policies
        like SA-ACCT-580219 can count child-policy claims such as SA-AUTO,
        SA-GL, SA-CARGO, and SA-WC correctly.
      */
      const claimsRes = await fetch(`${API}/claims/`, { headers: authHeaders() });

      if (claimsRes.status === 401 || claimsRes.status === 403) {
        clearSession();
        router.replace("/login?expired=1");
        return;
      }

      if (claimsRes.ok) {
        const claimsData = await safeJson(claimsRes);
        setClaims(Array.isArray(claimsData) ? claimsData : []);
      } else {
        setClaims([]);
      }

      const summaryUrl = hasPolicy
        ? `${API}/summary/underwriting?policy_number=${encodeURIComponent(policyNumber)}`
        : `${API}/summary/underwriting`;

      const summaryRes = await fetch(summaryUrl, { headers: authHeaders() });

      if (summaryRes.status === 401 || summaryRes.status === 403) {
        clearSession();
        router.replace("/login?expired=1");
        return;
      }

      if (summaryRes.ok) {
        setSummary((await safeJson(summaryRes)) || {});
      } else {
        setSummary({});
      }

      const decisionUrl = hasPolicy
        ? `${API}/renewal/decision?policy_number=${encodeURIComponent(policyNumber)}`
        : `${API}/renewal/decision`;

      const decisionRes = await fetch(decisionUrl, { headers: authHeaders() });

      if (decisionRes.status === 401 || decisionRes.status === 403) {
        clearSession();
        router.replace("/login?expired=1");
        return;
      }

      if (decisionRes.ok) {
        setDecision((await safeJson(decisionRes)) || {});
      } else {
        setDecision({});
      }

      const appetiteUrl = hasPolicy
        ? `${API}/renewal/carrier-appetite?policy_number=${encodeURIComponent(policyNumber)}`
        : `${API}/renewal/carrier-appetite`;

      const appetiteRes = await fetch(appetiteUrl, { headers: authHeaders() });

      if (appetiteRes.status === 401 || appetiteRes.status === 403) {
        clearSession();
        router.replace("/login?expired=1");
        return;
      }

      if (appetiteRes.ok) {
        setCarrierAppetite((await safeJson(appetiteRes)) || {});
      } else {
        setCarrierAppetite({});
      }

      const readinessUrl = hasPolicy
        ? `${API}/renewal/submission-readiness?policy_number=${encodeURIComponent(policyNumber)}`
        : `${API}/renewal/submission-readiness`;

      const readinessRes = await fetch(readinessUrl, { headers: authHeaders() });

      if (readinessRes.status === 401 || readinessRes.status === 403) {
        clearSession();
        router.replace("/login?expired=1");
        return;
      }

      if (readinessRes.ok) {
        setSubmissionReadiness((await safeJson(readinessRes)) || {});
      } else {
        setSubmissionReadiness({});
      }
const carrierMatchUrl = hasPolicy
  ? `${API}/renewal/carrier-match?policy_number=${encodeURIComponent(policyNumber)}`
  : `${API}/renewal/carrier-match`;

const carrierMatchRes = await fetch(carrierMatchUrl, {
  headers: authHeaders(),
});

if (carrierMatchRes.ok) {
  setCarrierMatch((await safeJson(carrierMatchRes)) || {});
} else {
  setCarrierMatch({});
}

const premiumForecastUrl = hasPolicy
  ? `${API}/renewal/premium-forecast?policy_number=${encodeURIComponent(policyNumber)}`
  : `${API}/renewal/premium-forecast`;

const premiumForecastRes = await fetch(premiumForecastUrl, {
  headers: authHeaders(),
});

if (premiumForecastRes.ok) {
  setPremiumForecast((await safeJson(premiumForecastRes)) || {});
} else {
  setPremiumForecast({});
}

const submissionBuilderUrl = hasPolicy
  ? `${API}/submission-builder/?policy_number=${encodeURIComponent(policyNumber)}`
  : `${API}/submission-builder/`;

const submissionBuilderRes = await fetch(submissionBuilderUrl, {
  headers: authHeaders(),
});

if (submissionBuilderRes.ok) {
  setSubmissionBuilder((await safeJson(submissionBuilderRes)) || {});
} else {
  setSubmissionBuilder({});
} 
     const timelineUrl = hasPolicy
        ? `${API}/timeline/analytics?policy_number=${encodeURIComponent(policyNumber)}`
        : `${API}/timeline/analytics`;

      const timelineRes = await fetch(timelineUrl, { headers: authHeaders() });

      if (timelineRes.status === 401 || timelineRes.status === 403) {
        clearSession();
        router.replace("/login?expired=1");
        return;
      }



      if (timelineRes.ok) {
        setTimeline((await safeJson(timelineRes)) || {});
      } else {
        setTimeline({});
      }
    } catch {
      setDashboardError("Dashboard could not load. Confirm backend is running.");
      setClaims([]);
      setSummary({});
      setDecision({});
      setCarrierAppetite({});
      setSubmissionReadiness({});
      setCarrierMatch({});
      setTimeline({});
    } finally {
      setDashboardLoading(false);
    }
  }

  async function selectAccount(policyNumber: string) {
    if (!policyNumber) return;

    setMessage(`Loading policy ${policyNumber}...`);
    setCopilotAnswer("");
    setRenewalMemo("");
    setClaims([]);
    setSummary({});
    setDecision({});
    setCarrierAppetite({});
    setSubmissionReadiness({});
    setCarrierMatch({});
    setTimeline({});

    await loadDashboard(policyNumber);

    setMessage(`Loaded policy ${policyNumber}.`);
  }

  async function deleteProfile(policyNumber: string) {
  const confirmed = confirm(`Delete profile ${policyNumber}?`);
  if (!confirmed) return;

  const removeProfileLocally = () => {
    setProfiles((prev) => {
      const next = prev.filter((p) => p.policy_number !== policyNumber);
      setCachedProfiles(next);
      return next;
    });

    if (profile?.policy_number === policyNumber) {
      newBlankProfile();
    }
  };

  try {
    setMessage(`Deleting profile ${policyNumber}...`);

    const res = await fetch(
  `${API}/account-profile/delete?policy_number=${encodeURIComponent(policyNumber)}`,
  {
    method: "DELETE",
    headers: authHeaders(),
  }
);

    if (res.status === 401 || res.status === 403) {
      clearSession();
      router.replace("/login?expired=1");
      return;
    }

    if (!res.ok) {
      removeProfileLocally();
      setMessage(
        `Removed profile ${policyNumber} from workspace. Backend returned ${res.status}.`
      );
      return;
    }

    removeProfileLocally();
    setMessage(`Deleted profile ${policyNumber}.`);
  } catch {
    removeProfileLocally();
    setMessage(`Deleted local profile ${policyNumber}. Backend delete unavailable.`);
  }
}

  async function saveProfile() {
    const payload = {
      business_name: profile.business_name || "",
      carrier_name: profile.carrier_name || "",
      agency_name: profile.agency_name || "",
      policy_number: profile.policy_number || "",
      effective_date: profile.effective_date || "",
      expiration_date: profile.expiration_date || "",
      evaluation_date: profile.evaluation_date || "",
    };

    if (!payload.policy_number) {
      setMessage("Policy number is required before saving.");
      return;
    }

    try {
      const res = await fetch(`${API}/account-profile/`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify(payload),
      });

      if (res.status === 401 || res.status === 403) {
        clearSession();
        router.replace("/login?expired=1");
        return;
      }

      if (!res.ok) {
        updateProfileList([payload]);
        setMessage("Saved profile locally. Backend save failed.");
        return;
      }

      const savedData = await safeJson(res);
      const savedProfile = savedData?.policy_number ? savedData : payload;

      setProfile(savedProfile);
      updateProfileList([savedProfile]);
      setMessage("Account profile saved.");
      await loadDashboard(savedProfile.policy_number);
    } catch {
      updateProfileList([payload]);
      setMessage("Saved profile locally. Backend save unavailable.");
    }
  }

  async function lookupPolicy() {
    if (!profile.policy_number) {
      setMessage("Enter a policy number first.");
      return;
    }

    try {
      const res = await fetch(
        `${API}/account-profile/policy/${encodeURIComponent(profile.policy_number)}`,
        { headers: authHeaders() }
      );

      if (res.status === 401 || res.status === 403) {
        clearSession();
        router.replace("/login?expired=1");
        return;
      }

      if (!res.ok) {
        const cachedMatch = getCachedProfiles().find(
          (item) => item?.policy_number === profile.policy_number
        );

        if (cachedMatch) {
          setProfile(cachedMatch);
          setCopilotAnswer("");
          await loadDashboard(cachedMatch.policy_number);
          setMessage("Account profile loaded from saved workspace.");
          return;
        }

        setMessage("No account found for that policy number.");
        return;
      }

      const data = await safeJson(res);
      setProfile(data || {});
      if (data?.policy_number) {
        updateProfileList([data]);
      }
      setCopilotAnswer("");
      await loadDashboard(data?.policy_number);
      setMessage("Account profile loaded.");
    } catch {
      const cachedMatch = getCachedProfiles().find(
        (item) => item?.policy_number === profile.policy_number
      );

      if (cachedMatch) {
        setProfile(cachedMatch);
        setCopilotAnswer("");
        await loadDashboard(cachedMatch.policy_number);
        setMessage("Account profile loaded from saved workspace.");
        return;
      }

      setMessage("Lookup failed.");
    }
  }

  async function uploadFiles() {
  const selectedFiles = files ? Array.from(files) : [];

  if (selectedFiles.length === 0) {
    setMessage("Please select one or more PDF, Excel, or CSV files first.");
    return;
  }

  try {
    setMessage("Uploading and analyzing loss runs...");

    const formData = new FormData();

    /*
      IMPORTANT:
      Do not force the old selected policy number into a new upload.
      The parser should decide the account number, policy schedule, and claim policies.
    */

    let endpoint = `${API}/upload/loss-run`;

    if (selectedFiles.length === 1) {
      formData.append("file", selectedFiles[0]);
    } else {
      endpoint = `${API}/upload/loss-runs`;
      selectedFiles.forEach((file) => formData.append("files", file));
    }

    const res = await fetch(endpoint, {
      method: "POST",
      headers: authHeaders(),
      body: formData,
    });

    const data = await safeJson(res);

    if (res.status === 401 || res.status === 403) {
      clearSession();
      router.replace("/login?expired=1");
      return;
    }

    if (!res.ok) {
      setMessage(`Upload failed. Backend returned ${res.status}: ${JSON.stringify(data)}`);
      return;
    }

    const uploadedFileNames = selectedFiles.map((file) => file.name).join(", ");

    if (typeof window !== "undefined") {
      localStorage.setItem(
        "lossq_last_upload_review",
        JSON.stringify({
          uploaded_at: new Date().toISOString(),
          uploaded_files: data?.uploaded_files || selectedFiles.map((file) => file.name),
          profile: data?.profile || {},
          policies: data?.policies || data?.profile?.policies || [],
          claims: data?.claims || data?.parsed_claims || data?.saved_claim_rows || [],
          validation: data?.validation || data?.profile?.validation || {},
          saved_claims: data?.saved_claims || 0,
          raw_response: data || {},
        })
      );
    }

    setMessage(
      `Upload complete. Saved ${data?.saved_claims || 0} claim(s). New file: ${uploadedFileNames}`
    );

    if (data?.profile) {
      const uploadedProfile = {
        ...data.profile,
        policies: data?.policies || data?.profile?.policies || [],
        validation: data?.validation || data?.profile?.validation || {},
      };

      setProfile(uploadedProfile);
      updateProfileList([uploadedProfile]);
    }

    /*
      Fetch all org claims after upload.
      The dashboard will filter them locally by profile.policies.
      This is required because the account policy is SA-ACCT-580219,
      but claims belong to SA-AUTO, SA-GL, SA-CARGO, and SA-WC.
    */
    const claimsRes = await fetch(`${API}/claims/`, {
      headers: authHeaders(),
    });

    const claimsData = await safeJson(claimsRes);

    if (claimsRes.ok && Array.isArray(claimsData)) {
      setClaims(claimsData);
    }

   const uploadedPolicyNumber =
  data?.profile?.policy_number ||
  data?.profile?.account_number ||
  profile?.policy_number ||
  "";

if (uploadedPolicyNumber) {
  await loadDashboard(uploadedPolicyNumber);
}

setActiveTool("overview");
  } catch (error: any) {
    setMessage(
      `Upload failed before completion. Backend may have crashed. Error: ${
        error?.message || "Unknown error"
      }`
    );
  }
}

async function downloadPdf(url: string, filename: string) {
  const res = await fetch(url, { headers: authHeaders() });

  if (res.status === 401 || res.status === 403) {
    clearSession();
    router.replace("/login?expired=1");
    return;
  }

  if (!res.ok) {
    setMessage("Could not generate report.");
    return;
  }

  const blob = await res.blob();
  const objectUrl = window.URL.createObjectURL(blob);

  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = filename;
  a.click();

  window.URL.revokeObjectURL(objectUrl);
}

async function exportCarrierLossRun() {
  const policy = profile?.policy_number
    ? `?policy_number=${encodeURIComponent(profile.policy_number)}`
    : "";

  await downloadPdf(
    `${API}/reports/loss-run-template-pdf${policy}`,
    "lossq_carrier_loss_run.pdf"
  );
}

async function exportExecutiveReport() {
  const policy = profile?.policy_number
    ? `?policy_number=${encodeURIComponent(profile.policy_number)}`
    : "";

  setMessage("Generating executive underwriting report...");

  await downloadPdf(
    `${API}/reports/executive-report-pdf${policy}`,
    "lossq_executive_underwriting_report.pdf"
  );

  setMessage("Executive underwriting report generated.");
}


  async function generateRenewalMemo() {
    if (!profile?.policy_number) {
      setRenewalMemo("Select a policy/account first.");
      return;
    }

    setMemoLoading(true);
    setRenewalMemo(`Generating renewal memo for ${profile.policy_number}...`);

    try {
      const policy = `?policy_number=${encodeURIComponent(profile.policy_number)}`;

      const res = await fetch(`${API}/renewal/memo${policy}`, {
        headers: authHeaders(),
      });

      const data = await safeJson(res);

      if (res.status === 401 || res.status === 403) {
        clearSession();
        router.replace("/login?expired=1");
        return;
      }

      if (!res.ok) {
        setRenewalMemo(JSON.stringify(data));
        return;
      }

      setRenewalMemo(
        `Policy analyzed: ${data?.policy_number || profile.policy_number}\nClaims used: ${
          data?.claims_used ?? visibleClaims.length
        }\n\n${data?.memo || "No memo generated."}`
      );
    } catch {
      setRenewalMemo("Memo failed.");
    } finally {
      setMemoLoading(false);
    }
  }

 async function generateCarrierPacket() {
  const policy = profile?.policy_number
    ? `?policy_number=${encodeURIComponent(profile.policy_number)}`
    : "";

  setMessage("Generating carrier submission packet...");

  await downloadPdf(
    `${API}/reports/carrier-packet-pdf${policy}`,
    "lossq_carrier_submission_packet.pdf"
  );

  setMessage("Carrier submission packet generated.");
}

  function copyRenewalMemo() {
    navigator.clipboard.writeText(renewalMemo || "");
    setMessage("Renewal memo copied.");
  }

  async function askCopilot(questionOverride?: string) {
    const question = questionOverride || copilotQuestion;

    if (!question.trim()) {
      setCopilotAnswer("Ask a question first.");
      return;
    }

    if (!profile?.policy_number) {
      setCopilotAnswer(
        "Select a policy/account first so Copilot analyzes the correct claims."
      );
      setCopilotOpen(true);
      return;
    }

    setCopilotOpen(true);
    setCopilotLoading(true);
    setCopilotAnswer(`Thinking about policy ${profile.policy_number}...`);

    try {
      const res = await fetch(`${API}/copilot/ask`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify({
          question,
          policy_number: profile.policy_number,
        }),
      });

      const data = await safeJson(res);

      if (res.status === 401 || res.status === 403) {
        clearSession();
        router.replace("/login?expired=1");
        return;
      }

      if (!res.ok) {
        setCopilotAnswer(JSON.stringify(data));
        return;
      }

      setCopilotAnswer(
        `Policy analyzed: ${data?.policy_number || profile.policy_number}\nClaims used: ${
          data?.claims_used ?? visibleClaims.length
        }\n\n${data?.answer || "No answer returned."}`
      );
      setCopilotQuestion(question);
    } catch {
      setCopilotAnswer("Copilot failed.");
    } finally {
      setCopilotLoading(false);
    }
  }

  function logout() {
    clearSession();
    router.replace("/login?fresh=1");
  }

const policySchedule = Array.isArray(profile?.policies) ? profile.policies : [];

const activePolicyNumbers = policySchedule
  .map((item: any) => normalizePolicyNumber(item?.policy_number))
  .filter(Boolean);

const activeAccountPolicyNumber = normalizePolicyNumber(profile?.policy_number);

const hasActiveAccount = Boolean(
  profile?.business_name ||
    profile?.carrier_name ||
    profile?.policy_number ||
    activePolicyNumbers.length > 0
);

const visibleClaims = hasActiveAccount
  ? claims.filter((claim: any) => {
      const claimPolicy = getClaimPolicyNumber(claim);

      if (activePolicyNumbers.length > 0) {
        return activePolicyNumbers.includes(claimPolicy);
      }

      if (activeAccountPolicyNumber) {
        return claimPolicy === activeAccountPolicyNumber;
      }

      return false;
    })
  : [];

const totalClaims = visibleClaims.length;
const openClaims = visibleClaims.filter(
  (c: any) => String(c.status || "").toLowerCase() === "open"
).length;

const totalIncurred = visibleClaims.reduce(
  (sum: number, c: any) => sum + getClaimIncurred(c),
  0
);

const scheduleClaimStats = visibleClaims.reduce((acc: AnyObject, claim: any) => {
  const claimPolicy = getClaimPolicyNumber(claim);
  if (!claimPolicy) return acc;

  if (!acc[claimPolicy]) {
    acc[claimPolicy] = { count: 0, totalIncurred: 0 };
  }

  acc[claimPolicy].count += 1;
  acc[claimPolicy].totalIncurred += getClaimIncurred(claim);

  return acc;
}, {});

const flaggedClaims = visibleClaims.filter(isFlaggedClaim).length;

const localIntelligence = buildLocalDashboardIntelligence(visibleClaims);
const hasCredibleLossData =
  hasActiveAccount && localIntelligence.totalClaims > 0 && localIntelligence.totalIncurred > 0;

const totalClaimsDisplay = hasActiveAccount ? totalClaims : "-";
const openClaimsDisplay = hasActiveAccount ? openClaims : "-";
const totalIncurredDisplay = hasActiveAccount
  ? `$${Number(totalIncurred).toLocaleString()}`
  : "-";
const flaggedClaimsDisplay = hasActiveAccount ? flaggedClaims : "-";

const displayedRenewalScore = hasCredibleLossData
  ? localIntelligence.renewalScore
  : "-";
const displayedRenewalRiskLevel = hasCredibleLossData
  ? localIntelligence.renewalRiskLevel
  : "Insufficient Data";
const displayedRenewalProbability = hasCredibleLossData
  ? `${localIntelligence.renewalProbability}%`
  : "-";
const displayedCarrierAppetiteScore = hasCredibleLossData
  ? `${localIntelligence.appetiteScore}/100`
  : "-";
const displayedSubmissionReadinessScore = hasCredibleLossData
  ? submissionReadiness?.submission_readiness_score !== undefined
    ? `${submissionReadiness.submission_readiness_score}/100`
    : "-"
  : "-";
const underwritingDataMessage = dataUnavailableText(hasActiveAccount);

const lossTrendData = localIntelligence.lossTrendData;
const agingData = localIntelligence.agingData;
const severityData = localIntelligence.severityData;
const lineData = localIntelligence.lineData;

  if (!authReady) {
    return <LoadingScreen title="Checking session..." subtitle="Validating your LossQ access" />;
  }

  if (dashboardLoading) {
    return <LoadingScreen title="Loading LossQ..." subtitle="Preparing underwriting workspace" />;
  }

  if (dashboardError) {
    return (
      <main className="min-h-screen bg-[#020617] text-white flex items-center justify-center px-6">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,#1d4ed855,transparent_35%),radial-gradient(circle_at_bottom_right,#0ea5e955,transparent_30%)]" />
        <div className="relative bg-white/10 backdrop-blur-xl border border-red-400/40 rounded-3xl p-10 max-w-lg w-full text-center shadow-2xl">
          <h1 className="text-3xl font-bold mb-4 text-red-300">Dashboard Error</h1>
          <p className="text-slate-300 mb-6">{dashboardError}</p>

          <button
            onClick={() => loadDashboard()}
            className="bg-blue-600 hover:bg-blue-500 px-6 py-3 rounded-xl font-semibold shadow-lg shadow-blue-600/30"
          >
            Retry
          </button>

          <button
            onClick={logout}
            className="block mx-auto mt-4 text-slate-400 hover:text-white text-sm"
          >
            Return to login
          </button>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#020617] text-white overflow-hidden">
      <div className="fixed inset-0 bg-[radial-gradient(circle_at_top_left,#1d4ed866,transparent_28%),radial-gradient(circle_at_top_right,#0ea5e955,transparent_30%),radial-gradient(circle_at_bottom,#312e8155,transparent_35%)]" />
      <div className="fixed inset-0 bg-[linear-gradient(to_right,rgba(255,255,255,0.04)_1px,transparent_1px),linear-gradient(to_bottom,rgba(255,255,255,0.04)_1px,transparent_1px)] bg-[size:72px_72px] opacity-20" />

      <div className="relative flex min-h-screen">
        <aside
  className="hidden lg:flex fixed left-4 top-4 bottom-4 w-72 shrink-0 flex-col rounded-3xl border border-white/10 bg-slate-950/85 backdrop-blur-2xl p-5 z-50 overflow-y-auto shadow-[0_0_50px_rgba(59,130,246,0.18)]"
>
  <div className="mb-8">
    <img
      src="/lossq-logo-style2.png"
      alt="LossQ"
      className="w-full rounded-2xl border border-blue-400/20 shadow-[0_0_35px_rgba(59,130,246,0.22)]"
    />

    <div className="mt-4 text-center">
      <div className="text-xs uppercase tracking-[0.35em] text-blue-300">
        Underwriting Intelligence Platform
      </div>
    </div>
  </div>

  <ToolButton active={activeTool === "overview"} onClick={() => setActiveTool("overview")}>
    Overview
  </ToolButton>

  <ToolButton active={activeTool === "profiles"} onClick={() => setActiveTool("profiles")}>
    Carrier Profiles
  </ToolButton>

  <ToolButton active={activeTool === "upload"} onClick={() => setActiveTool("upload")}>
    Upload Center
  </ToolButton>

  <ToolButton active={activeTool === "submission-builder"} onClick={() => setActiveTool("submission-builder")}>
    Submission Builder
  </ToolButton>

  <ToolButton active={activeTool === "renewal-risk"} onClick={() => setActiveTool("renewal-risk")}>
    Renewal Risk
  </ToolButton>

  <ToolButton active={activeTool === "premium-forecast"} onClick={() => setActiveTool("premium-forecast")}>
    Premium Forecast
  </ToolButton>

  <ToolButton active={activeTool === "decision"} onClick={() => setActiveTool("decision")}>
    Underwriter Decision
  </ToolButton>

  <ToolButton active={activeTool === "carrier-appetite"} onClick={() => setActiveTool("carrier-appetite")}>
    Carrier Appetite
  </ToolButton>

  <ToolButton active={activeTool === "submission-readiness"} onClick={() => setActiveTool("submission-readiness")}>
    Submission Readiness
  </ToolButton>

  <ToolButton active={activeTool === "carrier-match"} onClick={() => setActiveTool("carrier-match")}>
    Carrier Match
  </ToolButton>

  <ToolButton active={activeTool === "summary"} onClick={() => setActiveTool("summary")}>
    AI Summary
  </ToolButton>

  <ToolButton active={activeTool === "memo"} onClick={() => setActiveTool("memo")}>
    Renewal Memo
  </ToolButton>

  <ToolButton active={activeTool === "charts"} onClick={() => setActiveTool("charts")}>
    Charts
  </ToolButton>

  <ToolButton active={activeTool === "claims"} onClick={() => setActiveTool("claims")}>
    Claims
  </ToolButton>

  <div className="mt-auto space-y-3 pt-6 border-t border-white/10">
    <NavButton href="/settings">Settings</NavButton>

    <a
      href="/carrier-workspace"
      className="btn-purple block text-center"
    >
      Carrier Workspace
    </a>

    <button
      onClick={logout}
      className="btn-danger w-full"
    >
      Logout
    </button>
  </div>
</aside>

        <section className="flex-1 px-5 md:px-8 py-8 pb-32 max-w-7xl mx-auto w-full lg:ml-72">
          <header className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between mb-8">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-blue-400/30 bg-blue-500/10 px-4 py-2 text-sm text-blue-200 mb-5">
                <span className="h-2 w-2 rounded-full bg-blue-400 shadow-[0_0_18px_#60a5fa]" />
                AI Underwriting Command Center
              </div>

              <h1 className="text-4xl md:text-6xl font-black tracking-tight">
                LossQ Dashboard
              </h1>

              <p className="text-slate-300 mt-3 max-w-2xl">
                Select a tool from the sidebar to analyze claims, renewal risk, underwriting decisions, reports, and carrier strategy.
              </p>
            </div>

            <div className="flex flex-wrap gap-3">
              <button onClick={() => setCopilotOpen(true)} className="btn-primary">
                Open Copilot
              </button>
              <button onClick={logout} className="btn-danger lg:hidden">
                Logout
              </button>
            </div>
          </header>

          <div className="lg:hidden glass-panel p-4 mb-6 overflow-x-auto">
            <div className="flex gap-3 min-w-max">
              <MobileToolButton active={activeTool === "overview"} onClick={() => setActiveTool("overview")}>Overview</MobileToolButton>
              <MobileToolButton active={activeTool === "profiles"} onClick={() => setActiveTool("profiles")}>Profiles</MobileToolButton>
              <MobileToolButton active={activeTool === "upload"} onClick={() => setActiveTool("upload")}>Upload</MobileToolButton>
              <MobileToolButton active={activeTool === "renewal-risk"} onClick={() => setActiveTool("renewal-risk")}>Renewal Risk</MobileToolButton>
              <MobileToolButton active={activeTool === "decision"} onClick={() => setActiveTool("decision")}>Decision</MobileToolButton>
              <MobileToolButton active={activeTool === "carrier-appetite"} onClick={() => setActiveTool("carrier-appetite")}>Carrier Appetite</MobileToolButton>
              <MobileToolButton active={activeTool === "submission-readiness"} onClick={() => setActiveTool("submission-readiness")}>Submission Readiness</MobileToolButton>
              <MobileToolButton active={activeTool === "carrier-match"} onClick={() => setActiveTool("carrier-match")}>Carrier Match</MobileToolButton>
<MobileToolButton active={activeTool === "premium-forecast"} onClick={() => setActiveTool("premium-forecast")}>
  Premium Forecast
</MobileToolButton>
<MobileToolButton active={activeTool === "submission-builder"} onClick={() => setActiveTool("submission-builder")}>
  Submission Builder
</MobileToolButton>
              <MobileToolButton active={activeTool === "summary"} onClick={() => setActiveTool("summary")}>Summary</MobileToolButton>
              <MobileToolButton active={activeTool === "memo"} onClick={() => setActiveTool("memo")}>Memo</MobileToolButton>
              <MobileToolButton active={activeTool === "charts"} onClick={() => setActiveTool("charts")}>Charts</MobileToolButton>
              <MobileToolButton active={activeTool === "claims"} onClick={() => setActiveTool("claims")}>Claims</MobileToolButton>
            </div>
          </div>

          {message && (
            <div className="glass-panel mb-6 p-4 text-slate-200 border-blue-400/20">
              {message}
            </div>
          )}

          {activeTool === "overview" && (
            <>
              <section className="grid grid-cols-1 md:grid-cols-4 gap-5 mb-8">
                <MetricCard title="Total Claims" value={totalClaimsDisplay} />
                <MetricCard title="Open Claims" value={openClaimsDisplay} />
                <MetricCard title="Total Incurred" value={totalIncurredDisplay} />
                <MetricCard title="Renewal Score" value={displayedRenewalScore} />
              </section>

              <section className="grid grid-cols-1 md:grid-cols-4 gap-5 mb-8">
                <MetricCard title="Risk Level" value={displayedRenewalRiskLevel} />
                <MetricCard title="Renewal Probability" value={displayedRenewalProbability} />
                <MetricCard title="Carrier Appetite" value={displayedCarrierAppetiteScore} />
                <MetricCard title="Submission Readiness" value={displayedSubmissionReadinessScore} />
              </section>

              <section className="glass-panel p-6 md:p-8">
                <h2 className="text-2xl md:text-3xl font-bold mb-4">Account Snapshot</h2>

                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                  <ProfileDetail label="Insured" value={profile?.business_name || "-"} />
                  <ProfileDetail
                    label="Writing Carrier"
                    value={profile?.writing_carrier || profile?.carrier_name || "-"}
                  />
                  <ProfileDetail label="Carrier" value={profile?.carrier_name || "-"} />
                  <ProfileDetail
                    label="Account Number"
                    value={profile?.account_number || profile?.customer_number || "-"}
                  />
                  <ProfileDetail label="Producing Agency" value={profile?.agency_name || "-"} />
                  <ProfileDetail label="Account / Policy" value={profile?.policy_number || "-"} />
                  <ProfileDetail label="Effective Date" value={profile?.effective_date || "-"} />
                  <ProfileDetail label="Expiration Date" value={profile?.expiration_date || "-"} />
                </div>

                {policySchedule.length > 0 && (
                  <div className="mt-8 rounded-3xl border border-white/10 bg-slate-950/50 p-5">
                    <div className="mb-4">
                      <p className="text-xs uppercase tracking-[0.25em] text-blue-300">
                        Policies on Account
                      </p>
                      <h3 className="mt-2 text-xl font-bold text-white">Policy Schedule</h3>
                      <p className="mt-1 text-sm text-slate-400">
                        Policy Number, Line / Coverage, policy period, claim count, and total incurred.
                      </p>
                    </div>

                    <div className="overflow-x-auto">
                      <table className="w-full min-w-[950px] text-sm">
                        <thead>
                          <tr className="border-b border-white/10 text-left text-slate-300">
                            <th className="py-3 pr-4">Policy Type / Coverage</th>
                            <th className="py-3 pr-4">Policy Number</th>
                            <th className="py-3 pr-4">Writing Carrier</th>
                            <th className="py-3 pr-4">Carrier</th>
                            <th className="py-3 pr-4">Effective</th>
                            <th className="py-3 pr-4">Expiration</th>
                            <th className="py-3 pr-4">Claims</th>
                            <th className="py-3 pr-4">Total Incurred</th>
                          </tr>
                        </thead>

                        <tbody>
                          {policySchedule.map((policy: any, index: number) => (
                            <tr
                              key={policy.policy_number || index}
                              className="border-b border-white/10"
                            >
                              <td className="py-3 pr-4 text-white">
                                {policy.policy_type ||
                                  policy.line_coverage ||
                                  policy.line_of_business ||
                                  policy.coverage ||
                                  policy.lob ||
                                  "Needs Review"}
                              </td>
                              <td className="py-3 pr-4 font-semibold text-blue-200">
                                {policy.policy_number || "-"}
                              </td>
                              <td className="py-3 pr-4">
                                {policy.writing_carrier ||
                                  profile?.writing_carrier ||
                                  profile?.carrier_name ||
                                  "-"}
                              </td>
                              <td className="py-3 pr-4">
                                {policy.carrier || profile?.carrier_name || "-"}
                              </td>
                              <td className="py-3 pr-4">{policy.effective_date || "-"}</td>
                              <td className="py-3 pr-4">{policy.expiration_date || "-"}</td>
                              <td className="py-3 pr-4">
                                {scheduleClaimStats[normalizePolicyNumber(policy.policy_number)]
                                  ?.count ??
                                  policy.claim_count ??
                                  0}
                              </td>
                              <td className="py-3 pr-4">
                                ${Number(
                                  scheduleClaimStats[normalizePolicyNumber(policy.policy_number)]
                                    ?.totalIncurred ??
                                    policy.total_incurred ??
                                    0
                                ).toLocaleString()}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </section>
            </>
          )}
          
       

          {activeTool === "profiles" && (
            <>
              <section className="glass-panel p-6 md:p-8 mb-8">
                <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
                  <div className="flex-1">
                    <h2 className="text-2xl md:text-3xl font-bold">Carrier Profile Workspace</h2>
                    <p className="text-slate-400 mt-2">
                      Select a saved carrier profile or create a new company profile.
                    </p>

                    <div className="mt-6 max-w-2xl">
                      <label className="block text-sm text-blue-200 mb-2">
                        Saved Carrier Profiles
                      </label>

                      <select
                        value={profile?.policy_number || ""}
                        onChange={(e) => selectAccount(e.target.value)}
                        className="w-full rounded-2xl bg-slate-950/70 border border-white/10 px-4 py-4 text-white outline-none focus:border-blue-400 focus:ring-4 focus:ring-blue-500/20"
                      >
                        <option value="">Select saved profile...</option>
                        {profiles.map((item) => (
                          <option key={item.id || item.policy_number} value={item.policy_number}>
                            {(item.business_name || "Unnamed Business") +
                              " — " +
                              (item.policy_number || "No Policy Number")}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-3">
                    <button onClick={newBlankProfile} className="btn-secondary">
                      New Company Profile
                    </button>

                    {profile?.policy_number && (
                      <button
                        type="button"
                        onClick={() => deleteProfile(profile.policy_number)}
                        className="btn-danger"
                      >
                        Delete Profile
                      </button>
                    )}
                  </div>
                </div>
              </section>

              <section className="glass-panel p-6 md:p-8">
                <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between mb-6">
                  <h2 className="text-2xl md:text-3xl font-bold">Carrier Account Profile</h2>

                  <div className="flex gap-3">
                    <button onClick={lookupPolicy} className="btn-secondary">Lookup</button>
                    <button onClick={saveProfile} className="btn-success">Save Profile</button>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                  <Input label="Insured" value={profile?.business_name || ""} onChange={(v) => setProfile({ ...profile, business_name: v })} />
                  <Input label="Writing Carrier" value={profile?.carrier_name || ""} onChange={(v) => setProfile({ ...profile, carrier_name: v })} />
                  <Input label="Producing Agency" value={profile?.agency_name || ""} onChange={(v) => setProfile({ ...profile, agency_name: v })} />
                  <Input label="Policy Number" value={profile?.policy_number || ""} onChange={(v) => setProfile({ ...profile, policy_number: v })} />
                  <Input label="Effective Date" value={profile?.effective_date || ""} onChange={(v) => setProfile({ ...profile, effective_date: v })} />
                  <Input label="Expiration Date" value={profile?.expiration_date || ""} onChange={(v) => setProfile({ ...profile, expiration_date: v })} />
                  <Input label="Evaluation Date" value={profile?.evaluation_date || ""} onChange={(v) => setProfile({ ...profile, evaluation_date: v })} />
                </div>
              </section>
            </>
          )}

          {activeTool === "upload" && (
            <section className="glass-panel p-6 md:p-8">
              <h2 className="text-2xl md:text-3xl font-bold mb-5">Upload & Report Center</h2>

              <div className="flex flex-wrap gap-4 items-center">
                <input
                  type="file"
                  multiple
                  accept=".pdf,.xlsx,.csv"
                  onChange={(e) => setFiles(e.target.files)}
                  className="text-sm text-slate-300 file:mr-4 file:rounded-xl file:border-0 file:bg-blue-600 file:px-4 file:py-3 file:text-white file:font-semibold"
                />

                <button onClick={uploadFiles} className="btn-primary">Upload & Analyze</button>
                <button onClick={exportCarrierLossRun} className="btn-success">Export Carrier Loss Run</button>
                <button onClick={exportExecutiveReport} className="btn-success">Export Executive Report</button>
                <button onClick={generateCarrierPacket} className="btn-purple">Generate Carrier Packet</button>
                <a href="/review" className="btn-secondary">Review Extraction</a>
                <a href="/carrier-workspace" className="btn-purple">Carrier Workspace</a>
              </div>
            </section>
          )}

          {activeTool === "renewal-risk" && (
            <section className="glass-panel p-6 md:p-8">
              <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <p className="text-sm uppercase tracking-[0.25em] text-blue-300 mb-3">
                    Renewal Risk Engine
                  </p>

                  <h2 className="text-2xl md:text-3xl font-bold">
                    Renewal Risk Score
                  </h2>

                  <p className="text-slate-400 mt-2 max-w-3xl">
                    Policy-specific renewal risk based on claims, reserves, severity,
                    litigation, frequency, and open claim pressure.
                  </p>
                </div>

                <div className="rounded-3xl border border-white/10 bg-slate-950/70 px-8 py-6 text-center min-w-[180px]">
                  <div className="text-5xl font-black">
                    {displayedRenewalScore}
                  </div>
                  <div className="text-slate-400 text-sm mt-1">out of 100</div>

                  <div className="mt-4 inline-flex rounded-full border border-blue-400/30 bg-blue-500/10 px-4 py-2 text-sm font-bold text-blue-200">
                    {displayedRenewalRiskLevel}
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-8">
                <ListCard title="Renewal Drivers" items={hasCredibleLossData ? localIntelligence.renewalDrivers : [underwritingDataMessage]} color="blue" />
                <ListCard title="Carrier Concerns" items={hasCredibleLossData ? localIntelligence.carrierConcerns : [underwritingDataMessage]} color="red" />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
                <TextCard title="Broker Recommendation" text={hasCredibleLossData ? localIntelligence.brokerRecommendation : underwritingDataMessage} />
                <TextCard title="Renewal Summary" text={hasCredibleLossData ? localIntelligence.renewalSummary : underwritingDataMessage} />
              </div>
            </section>
          )}

          {activeTool === "decision" && (
            <section className="glass-panel p-6 md:p-8">
              <p className="text-sm uppercase tracking-[0.25em] text-purple-300 mb-3">
                Underwriter Decision Engine
              </p>

              <h2 className="text-2xl md:text-3xl font-bold mb-6">
                Carrier Placement Intelligence
              </h2>

              <div className="grid grid-cols-1 md:grid-cols-4 gap-5 mb-8">
                <MetricCard title="Renewal Probability" value={displayedRenewalProbability} />
                <MetricCard title="Premium Impact" value={hasCredibleLossData ? localIntelligence.expectedPremiumImpact : "-"} />
                <MetricCard title="Carrier Appetite" value={hasCredibleLossData ? localIntelligence.appetiteLevel : "-"} />
                <MetricCard title="Marketability Score" value={hasCredibleLossData ? `${localIntelligence.marketabilityScore}/100` : "-"} />
              </div>

              <TextCard title="Submission Readiness" text={hasCredibleLossData ? decision?.submission_readiness || "Marketable with broker narrative and claim support." : underwritingDataMessage} />

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
                <ListCard title="Underwriting Concerns" items={hasCredibleLossData ? localIntelligence.carrierConcerns : [underwritingDataMessage]} color="red" />
                <ListCard title="Best Market Types" items={hasCredibleLossData ? decision?.best_market_types || ["Regional commercial insurance markets", "Specialty underwriting programs"] : [underwritingDataMessage]} color="purple" />
              </div>

              <div className="mt-6">
                <TextCard title="Underwriter Decision Summary" text={hasCredibleLossData ? decision?.underwriter_decision_summary || localIntelligence.renewalSummary : underwritingDataMessage} />
              </div>
            </section>
          )}

          {activeTool === "carrier-appetite" && (
            <section className="glass-panel p-6 md:p-8">
              <p className="text-sm uppercase tracking-[0.25em] text-blue-300 mb-3">
                Carrier Appetite Engine
              </p>

              <h2 className="text-2xl md:text-3xl font-bold mb-6">
                Market Appetite Strategy
              </h2>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-8">
                <MetricCard title="Appetite Score" value={displayedCarrierAppetiteScore} />
                <MetricCard title="Appetite Level" value={hasCredibleLossData ? localIntelligence.appetiteLevel : "-"} />
                <MetricCard title="Best Market" value={hasCredibleLossData ? localIntelligence.carrierMatches?.[0]?.fit || "-" : "-"} />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <ListCard
                  title="Best Fit Markets"
                  items={
                    hasCredibleLossData
                      ? localIntelligence.carrierMatches.slice(0, 3).map(
                          (item: any) =>
                            `${item.carrier} — ${item.match_score}/100 — ${item.fit}`
                        )
                      : [underwritingDataMessage]
                  }
                  color="blue"
                />

                <ListCard
                  title="Appetite Reasons"
                  items={hasCredibleLossData ? localIntelligence.carrierConcerns : [underwritingDataMessage]}
                  color="purple"
                />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
                <TextCard
                  title="Market Strategy"
                  text={hasCredibleLossData ? carrierAppetite?.market_strategy || "Market with a broker narrative focused on claim status, reserves, litigation posture, and corrective actions." : underwritingDataMessage}
                />

                <TextCard
                  title="Placement Summary"
                  text={hasCredibleLossData ? carrierAppetite?.placement_summary || localIntelligence.renewalSummary : underwritingDataMessage}
                />
              </div>
            </section>
          )}

          {activeTool === "submission-readiness" && (
            <section className="glass-panel p-6 md:p-8">
              <p className="text-sm uppercase tracking-[0.25em] text-green-300 mb-3">
                Submission Readiness Engine
              </p>

              <h2 className="text-2xl md:text-3xl font-bold mb-6">
                Submission Checklist & Carrier Confidence
              </h2>

              <div className="grid grid-cols-1 md:grid-cols-4 gap-5 mb-8">
                <MetricCard title="Readiness Score" value={submissionReadiness?.submission_readiness_score !== undefined ? `${submissionReadiness.submission_readiness_score}/100` : "-"} />
                <MetricCard title="Readiness Level" value={submissionReadiness?.submission_readiness_level || "-"} />
                <MetricCard title="Carrier Confidence" value={submissionReadiness?.carrier_confidence || "-"} />
                <MetricCard title="Submission Quality" value={submissionReadiness?.submission_quality || "-"} />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <ListCard
                  title="Missing Items"
                  items={submissionReadiness?.missing_items || ["No missing items available."]}
                  color="red"
                />

                <ListCard
                  title="Required Documents"
                  items={submissionReadiness?.required_documents || ["No required documents available."]}
                  color="blue"
                />
              </div>

              <div className="mt-6">
                <ListCard
                  title="Recommended Actions"
                  items={submissionReadiness?.recommended_actions || ["No recommended actions available."]}
                  color="purple"
                />
              </div>

              <div className="mt-6">
                <TextCard
                  title="Readiness Summary"
                  text={submissionReadiness?.readiness_summary || "No readiness summary available yet."}
                />
              </div>
            </section>
          )}

          {activeTool === "carrier-match" && (
  <section className="glass-panel p-6 md:p-8">
    <p className="text-sm uppercase tracking-[0.25em] text-purple-300 mb-3">
      Carrier Match Engine
    </p>

    <h2 className="text-2xl md:text-3xl font-bold mb-6">
      Named Carrier Matching
    </h2>

    <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-8">
      <MetricCard
        title="Recommended Carrier"
        value={hasCredibleLossData ? localIntelligence.carrierMatches?.[0]?.carrier || "-" : "-"}
      />
      <MetricCard
        title="Match Score"
        value={
          hasCredibleLossData
            ? `${localIntelligence.carrierMatches?.[0]?.match_score || 0}/100`
            : "-"
        }
      />
      <MetricCard
        title="Carriers Ranked"
        value={hasCredibleLossData ? localIntelligence.carrierMatches.length : 0}
      />
    </div>

    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <ListCard
        title="Top Carrier Matches"
        items={
          hasCredibleLossData
            ? localIntelligence.carrierMatches.slice(0, 5).map(
                (item: any) =>
                  `${item.carrier} — ${item.match_score}/100 — ${item.fit}`
              )
            : [underwritingDataMessage]
        }
        color="purple"
      />

      <ListCard
        title="Carrier Match Reasons"
        items={
          hasCredibleLossData
            ? localIntelligence.carrierMatches.slice(0, 5).map(
                (item: any) => `${item.carrier}: ${item.reason}`
              )
            : [underwritingDataMessage]
        }
        color="blue"
      />
    </div>

    <div className="mt-6">
      <TextCard
        title="Carrier Match Summary"
        text={
          hasCredibleLossData
          ? carrierMatch?.carrier_match_summary ||
            `LossQ recommends ${localIntelligence.carrierMatches?.[0]?.carrier || "the best available market"} with a ${localIntelligence.carrierMatches?.[0]?.match_score || 0}/100 score based on verified account-specific claims.`
          : underwritingDataMessage
        }
      />
    </div>
  </section>
)}

{activeTool === "premium-forecast" && (
  <section className="glass-panel p-6 md:p-8">
    <p className="text-sm uppercase tracking-[0.25em] text-green-300 mb-3">
      Premium Forecast Engine
    </p>

    <h2 className="text-2xl md:text-3xl font-bold mb-6">
      Renewal Premium Projection
    </h2>

    <div className="grid grid-cols-1 md:grid-cols-4 gap-5 mb-8">
      <MetricCard
        title="Current Premium"
        value={hasCredibleLossData ? moneyDisplay(localIntelligence.currentPremium) : "-"}
      />

      <MetricCard
        title="Expected Renewal"
        value={hasCredibleLossData ? moneyDisplay(localIntelligence.expectedRenewalPremium) : "-"}
      />

      <MetricCard
        title="Expected Increase"
        value={hasCredibleLossData ? `${localIntelligence.expectedIncrease}%` : "-"}
      />

      <MetricCard
        title="Confidence"
        value={hasCredibleLossData ? `${localIntelligence.confidenceScore}%` : "-"}
      />
    </div>

    <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-8">
      <MetricCard
        title="Best Case"
        value={hasCredibleLossData ? `${localIntelligence.bestCasePercent}%` : "-"}
      />

      <MetricCard
        title="Likely Range"
        value={hasCredibleLossData ? localIntelligence.likelyRangePercent : "-"}
      />

      <MetricCard
        title="Worst Case"
        value={hasCredibleLossData ? `${localIntelligence.worstCasePercent}%` : "-"}
      />
    </div>

    <ListCard
      title="Forecast Drivers"
      items={
        hasCredibleLossData ? localIntelligence.forecastDrivers : [underwritingDataMessage]
      }
      color="blue"
    />

    <div className="mt-6">
      <TextCard
        title="Forecast Summary"
        text={
          hasCredibleLossData ? localIntelligence.forecastSummary : underwritingDataMessage
        }
      />
    </div>
  </section>
)}

{activeTool === "submission-builder" && (
  <section className="glass-panel p-6 md:p-8">
    <p className="text-sm uppercase tracking-[0.25em] text-blue-300 mb-3">
      Submission Builder Engine
    </p>

    <h2 className="text-2xl md:text-3xl font-bold mb-4">
      Carrier Submission Package
    </h2>

    <p className="text-slate-400 mb-6">
      Select an active carrier profile, then generate a complete underwriting submission package for that account.
    </p>

    <div className="rounded-3xl border border-white/10 bg-slate-950/60 p-5 mb-8">
      <label className="block text-sm text-blue-200 mb-2">
        Select Account / Policy
      </label>

      <div className="flex flex-col md:flex-row gap-4">
        <select
          value={profile?.policy_number || ""}
          onChange={(e) => selectAccount(e.target.value)}
          className="flex-1 rounded-2xl bg-slate-950/70 border border-white/10 px-4 py-4 text-white outline-none focus:border-blue-400 focus:ring-4 focus:ring-blue-500/20"
        >
          <option value="">Select active profile...</option>

          {profiles.map((item) => (
            <option key={item.id || item.policy_number} value={item.policy_number}>
              {(item.business_name || "Unnamed Business") +
                " — " +
                (item.carrier_name || "No Carrier") +
                " — " +
                (item.policy_number || "No Policy")}
            </option>
          ))}
        </select>

        <button
  onClick={async () => {
    if (!profile?.policy_number) {
      setMessage("Select an account/profile first.");
      return;
    }

    setMessage(`Generating submission package for ${profile.policy_number}...`);

    await loadDashboard(profile.policy_number);

    setActiveTool("submission-builder");
    setMessage(`Submission package generated for ${profile.policy_number}.`);
  }}
  className="btn-primary"
>
  Generate Package
</button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-5">
        <ProfileDetail label="Insured" value={profile?.business_name || "-"} />
        <ProfileDetail label="Carrier" value={profile?.carrier_name || "-"} />
        <ProfileDetail label="Policy" value={profile?.policy_number || "-"} />
      </div>
    </div>

    <div className="grid grid-cols-1 md:grid-cols-4 gap-5 mb-8">
      <MetricCard title="Renewal Score" value={displayedRenewalScore} />
      <MetricCard title="Risk Level" value={displayedRenewalRiskLevel} />
      <MetricCard
        title="Premium Forecast"
        value={
          hasCredibleLossData
            ? `${localIntelligence.expectedIncrease}%`
            : "-"
        }
      />
      <MetricCard
        title="Submission Readiness"
        value={
          displayedSubmissionReadinessScore
        }
      />
    </div>

    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <TextCard
        title="Underwriter Narrative"
        text={
          submissionBuilder?.underwriter_narrative ||
          "No underwriter narrative available yet."
        }
      />

      <TextCard
        title="Executive Summary"
        text={
          submissionBuilder?.executive_summary ||
          "No executive summary available yet."
        }
      />
    </div>

    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
      <TextCard
        title="Broker Marketing Memo"
        text={
          submissionBuilder?.broker_marketing_memo ||
          "No broker marketing memo available yet."
        }
      />

      <TextCard
        title="Renewal Strategy"
        text={
          submissionBuilder?.renewal_strategy ||
          "No renewal strategy available yet."
        }
      />
    </div>

    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
      <TextCard
        title="Carrier Appetite"
        text={
          carrierAppetite?.placement_summary ||
          carrierAppetite?.market_strategy ||
          "No carrier appetite summary available yet."
        }
      />

      <TextCard
        title="Premium Forecast"
        text={
          hasCredibleLossData ? localIntelligence.forecastSummary : underwritingDataMessage
        }
      />
    </div>

    <div className="mt-6">
      <TextCard
        title="Carrier Submission Email"
        text={
          submissionBuilder?.carrier_submission_email ||
          "No carrier submission email available yet."
        }
      />
    </div>

    <div className="mt-6">
      <ListCard
        title="Loss Explanations"
        items={
          submissionBuilder?.loss_explanations?.length
            ? submissionBuilder.loss_explanations.map(
                (item: any) =>
                  `${item.claim_number} — ${item.explanation} Broker position: ${item.broker_position}`
              )
            : ["No loss explanations available yet."]
        }
        color="purple"
      />
    </div>

    <div className="mt-8 flex flex-wrap gap-4">
      <button onClick={exportExecutiveReport} className="btn-success">
        Export Executive Report
      </button>

      <button onClick={generateCarrierPacket} className="btn-purple">
        Generate Carrier Packet
      </button>

      <button onClick={() => setActiveTool("memo")} className="btn-secondary">
        Open Renewal Memo
      </button>
    </div>
  </section>
)}

          {activeTool === "summary" && (
            <section className="glass-panel p-6 md:p-8">
              <h2 className="text-2xl md:text-3xl font-bold mb-5">AI Underwriting Summary</h2>
              <p className="text-slate-300 leading-8">{hasCredibleLossData ? summary?.summary || localIntelligence.renewalSummary : underwritingDataMessage}</p>
              <p className="text-blue-200 mt-6">{hasCredibleLossData ? summary?.recommendation || localIntelligence.brokerRecommendation : "Upload or review verified claims before relying on AI intelligence."}</p>
            </section>
          )}

          {activeTool === "memo" && (
            <section className="glass-panel p-6 md:p-8">
              <h2 className="text-2xl md:text-3xl font-bold mb-6">AI Renewal Memo</h2>

              <div className="flex gap-4 mb-5">
                <button onClick={generateRenewalMemo} disabled={memoLoading} className="btn-purple disabled:opacity-50">
                  {memoLoading ? "Generating..." : "Generate Renewal Memo"}
                </button>

                {renewalMemo && (
                  <button onClick={copyRenewalMemo} className="btn-secondary">
                    Copy Memo
                  </button>
                )}
              </div>

              <div className="rounded-2xl border border-white/10 bg-slate-950/70 p-5 max-h-[520px] overflow-y-auto">
                <pre className="whitespace-pre-wrap text-slate-300 leading-7 text-sm">
                  {renewalMemo || "Generate a memo above."}
                </pre>
              </div>
            </section>
          )}

          {activeTool === "charts" && (
            <section className="glass-panel p-6 md:p-8">
              <h2 className="text-2xl md:text-3xl font-bold mb-3">
                Interactive Claim Development Charts
              </h2>

              <p className="text-slate-400 mb-6">
                Visualize loss trends, claim aging, severity distribution, and line-of-business concentration.
              </p>

              <div className="grid grid-cols-1 md:grid-cols-4 gap-5 mb-8">
                <MetricCard title="Reserve Pressure" value={hasCredibleLossData ? localIntelligence.reservePressure : "-"} />
                <MetricCard title="Open Claims" value={hasCredibleLossData ? localIntelligence.openClaims : "-"} />
                <MetricCard title="Total Reserve" value={hasCredibleLossData ? moneyDisplay(localIntelligence.totalReserve) : "-"} />
                <MetricCard title="Total Incurred" value={hasCredibleLossData ? moneyDisplay(localIntelligence.totalIncurred) : "-"} />
              </div>

              <div className="rounded-2xl border border-white/10 bg-slate-950/70 p-5 mb-6">
                <h3 className="font-semibold mb-2">Trend Intelligence</h3>
                <p className="text-slate-300">{hasCredibleLossData ? localIntelligence.trendNote : underwritingDataMessage}</p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <ChartCard title="Incurred Loss Trend">
                  <ResponsiveContainer width="100%" height={280}>
                    <LineChart data={lossTrendData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                      <XAxis dataKey="name" stroke="#94a3b8" />
                      <YAxis stroke="#94a3b8" />
                      <Tooltip contentStyle={{ backgroundColor: "#0f172a", border: "1px solid #334155", color: "#fff" }} />
                      <Line type="monotone" dataKey="value" stroke="#38bdf8" strokeWidth={4} dot={{ fill: "#38bdf8", strokeWidth: 2, r: 5 }} />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>

                <ChartCard title="Open Claim Aging">
                  <ResponsiveContainer width="100%" height={280}>
                    <BarChart data={agingData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                      <XAxis dataKey="name" stroke="#94a3b8" />
                      <YAxis stroke="#94a3b8" />
                      <Tooltip contentStyle={{ backgroundColor: "#0f172a", border: "1px solid #334155", color: "#fff" }} />
                      <Bar dataKey="value" fill="#f59e0b" radius={[8, 8, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </ChartCard>

                <ChartCard title="Severity Distribution">
                  <ResponsiveContainer width="100%" height={280}>
                    <PieChart>
                      <Pie data={severityData} dataKey="value" nameKey="name" outerRadius={100} label>
                        {severityData.map((_, index) => {
                          const colors = ["#22c55e", "#eab308", "#f97316", "#ef4444"];
                          return <Cell key={`cell-${index}`} fill={colors[index % colors.length]} />;
                        })}
                      </Pie>
                      <Tooltip contentStyle={{ backgroundColor: "#0f172a", border: "1px solid #334155", color: "#fff" }} />
                    </PieChart>
                  </ResponsiveContainer>
                </ChartCard>

                <ChartCard title="Incurred by Line of Business">
                  <ResponsiveContainer width="100%" height={280}>
                    <BarChart data={lineData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                      <XAxis dataKey="name" stroke="#94a3b8" />
                      <YAxis stroke="#94a3b8" />
                      <Tooltip contentStyle={{ backgroundColor: "#0f172a", border: "1px solid #334155", color: "#fff" }} />
                      <Bar dataKey="value" fill="#8b5cf6" radius={[8, 8, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </ChartCard>
              </div>
            </section>
          )}

          {activeTool === "claims" && (
            <section className="glass-panel p-6 md:p-8">
              <h2 className="text-2xl md:text-3xl font-bold mb-6">Claims Analysis</h2>

              <div className="grid grid-cols-1 md:grid-cols-4 gap-5 mb-8">
                <MetricCard title="Total Claims" value={totalClaimsDisplay} />
		<MetricCard title="Open Claims" value={openClaimsDisplay} />
		<MetricCard title="Flagged Claims" value={flaggedClaimsDisplay} />
		<MetricCard title="Total Incurred" value={totalIncurredDisplay} />
              </div>

              <div className="overflow-x-auto">
                <table className="w-full min-w-[900px]">
                  <thead>
                    <tr className="border-b border-white/10 text-left text-slate-300">
                      <th className="pb-4">Claim #</th>
                      <th className="pb-4">Line</th>
                      <th className="pb-4">Status</th>
                      <th className="pb-4">Paid</th>
                      <th className="pb-4">Reserve</th>
                      <th className="pb-4">Total</th>
                      <th className="pb-4">Policy</th>
                      <th className="pb-4">Flag</th>
                    </tr>
                  </thead>

<tbody>
  {visibleClaims.map((claim: any) => (
    <tr
      key={claim.id || claim.claim_number}
      className="border-b border-white/10 text-slate-300"
    >
      <td className="py-4">
        {claim.id ? (
          <a
            href={`/claims/${claim.id}`}
            className="text-blue-300 hover:text-blue-200 underline"
          >
            {claim.claim_number || "Unnamed Claim"}
          </a>
        ) : (
          claim.claim_number || "Unnamed Claim"
        )}
      </td>

      <td>{claim.line_of_business || "-"}</td>
      <td>{claim.status || "-"}</td>
      <td>${Number(claim.paid_amount || 0).toLocaleString()}</td>
      <td>${Number(claim.reserve_amount || 0).toLocaleString()}</td>
      <td>${Number(getClaimIncurred(claim)).toLocaleString()}</td>
      <td>{claim.policy_number || "-"}</td>

      <td>
        {claim.flag ? (
          <span className="text-red-300">{claim.flag}</span>
        ) : (
          <span className="text-slate-500">None</span>
        )}
      </td>
    </tr>
  ))}
</tbody>
</table>
</div>
</section>
)}
</section>
</div>

<button

        onClick={() => setCopilotOpen(!copilotOpen)}
        className="fixed bottom-6 right-6 z-50 rounded-full bg-blue-600 hover:bg-blue-500 px-6 py-4 font-semibold shadow-2xl shadow-blue-600/40"
      >
        {copilotOpen ? "Close Copilot" : "Ask Copilot"}
      </button>

      {copilotOpen && (
        <div className="fixed bottom-24 right-6 z-50 w-[420px] max-w-[calc(100vw-3rem)] bg-slate-950/95 backdrop-blur-xl border border-blue-400/30 rounded-3xl shadow-2xl shadow-blue-900/40 overflow-hidden">
          <div className="bg-white/5 px-5 py-4 flex justify-between border-b border-white/10">
            <div>
              <h2 className="font-semibold">AI Underwriting Copilot</h2>
              <p className="text-xs text-slate-400">
                Account: {profile?.business_name || "No account selected"} | Policy: {profile?.policy_number || "-"}
              </p>
            </div>

            <button onClick={() => setCopilotOpen(false)} className="text-slate-400 hover:text-white">
              ✕
            </button>
          </div>

          <div className="p-5 max-h-[520px] overflow-y-auto">
            {[
              "What are the biggest renewal concerns?",
              "Summarize litigation exposure.",
              "What claims should concern carriers?",
              "What should the broker explain before submission?",
            ].map((q) => (
              <button
                key={q}
                onClick={() => askCopilot(q)}
                className="w-full text-left bg-white/5 hover:bg-white/10 border border-white/10 rounded-xl px-3 py-2 text-sm mb-2"
              >
                {q}
              </button>
            ))}

            <div className="flex gap-2 mt-4">
              <input
                value={copilotQuestion}
                onChange={(e) => setCopilotQuestion(e.target.value)}
                placeholder="Ask a question..."
                className="flex-1 bg-slate-950 border border-white/10 rounded-xl px-3 py-2 text-sm outline-none focus:border-blue-400"
              />

              <button onClick={() => askCopilot()} disabled={copilotLoading} className="btn-primary disabled:opacity-50">
                {copilotLoading ? "..." : "Ask"}
              </button>
            </div>

            {copilotAnswer && (
              <div className="bg-white/5 border border-white/10 rounded-2xl p-4 mt-4">
                <p className="text-slate-300 whitespace-pre-line text-sm leading-7">
                  {copilotAnswer}
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      <style jsx global>{`
        .glass-panel {
          border-radius: 1.5rem;
          border: 1px solid rgba(255, 255, 255, 0.1);
          background: rgba(15, 23, 42, 0.68);
          backdrop-filter: blur(18px);
          box-shadow: 0 24px 80px rgba(2, 6, 23, 0.45);
        }

        .btn-primary {
          border-radius: 0.9rem;
          background: linear-gradient(135deg, #2563eb, #0ea5e9);
          padding: 0.75rem 1.15rem;
          font-weight: 700;
          color: white;
          box-shadow: 0 14px 35px rgba(37, 99, 235, 0.25);
          transition: 0.2s ease;
        }

        .btn-primary:hover {
          transform: translateY(-1px);
          filter: brightness(1.08);
        }

        .btn-secondary {
          border-radius: 0.9rem;
          border: 1px solid rgba(255, 255, 255, 0.12);
          background: rgba(255, 255, 255, 0.07);
          padding: 0.75rem 1.15rem;
          font-weight: 700;
          color: white;
          transition: 0.2s ease;
        }

        .btn-secondary:hover {
          background: rgba(255, 255, 255, 0.12);
        }

        .btn-success {
          border-radius: 0.9rem;
          background: linear-gradient(135deg, #059669, #22c55e);
          padding: 0.75rem 1.15rem;
          font-weight: 700;
          color: white;
          box-shadow: 0 14px 35px rgba(34, 197, 94, 0.2);
        }

        .btn-purple {
          border-radius: 0.9rem;
          background: linear-gradient(135deg, #7c3aed, #a855f7);
          padding: 0.75rem 1.15rem;
          font-weight: 700;
          color: white;
          box-shadow: 0 14px 35px rgba(168, 85, 247, 0.2);
        }

        .btn-danger {
          border-radius: 0.9rem;
          background: linear-gradient(135deg, #dc2626, #f43f5e);
          padding: 0.75rem 1.15rem;
          font-weight: 700;
          color: white;
          box-shadow: 0 14px 35px rgba(244, 63, 94, 0.2);
        }
      `}</style>
    </main>
  );
}

function LoadingScreen({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <main className="min-h-screen bg-[#020617] text-white flex items-center justify-center px-6">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,#1d4ed866,transparent_35%)]" />
      <div className="relative text-center rounded-3xl border border-white/10 bg-white/10 backdrop-blur-xl p-10 shadow-2xl">
        <div className="mx-auto mb-5 h-12 w-12 rounded-full border-4 border-blue-400/30 border-t-blue-400 animate-spin" />
        <div className="text-3xl font-bold mb-3">{title}</div>
        <div className="text-slate-400">{subtitle}</div>
      </div>
    </main>
  );
}

function NavButton({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a href={href} className="btn-secondary block text-center">
      {children}
    </a>
  );
}

function ToolButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`mb-2 rounded-2xl px-4 py-3 text-left font-semibold transition ${
        active
          ? "bg-blue-600 text-white shadow-lg shadow-blue-600/20"
          : "text-slate-300 hover:bg-white/10 hover:text-white"
      }`}
    >
      {children}
    </button>
  );
}

function MobileToolButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`rounded-xl px-4 py-2 text-sm font-semibold whitespace-nowrap ${
        active ? "bg-blue-600 text-white" : "bg-white/10 text-slate-300"
      }`}
    >
      {children}
    </button>
  );
}

function ProfileDetail({ label, value }: { label: string; value: any }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-slate-950/60 p-4">
      <div className="text-xs uppercase tracking-[0.2em] text-blue-300 mb-2">{label}</div>
      <div className="font-bold break-words">{value || "-"}</div>
    </div>
  );
}

function Input({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div>
      <label className="block text-sm text-blue-200 mb-2">{label}</label>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full bg-slate-950/70 border border-white/10 rounded-2xl px-4 py-3 outline-none focus:border-blue-400 focus:ring-4 focus:ring-blue-500/20"
      />
    </div>
  );
}

function MetricCard({ title, value }: { title: string; value: any }) {
  return (
    <div className="rounded-3xl border border-white/10 bg-white/[0.07] backdrop-blur-xl p-6 shadow-2xl shadow-slate-950/30">
      <div className="text-slate-400 mb-3 text-sm">{title}</div>
      <div className="text-2xl font-black break-words">{value || "-"}</div>
    </div>
  );
}

function TextCard({ title, text }: { title: string; text: string }) {
  return (
    <div className="rounded-3xl border border-white/10 bg-slate-950/60 p-5">
      <h3 className="font-bold text-lg mb-3">{title}</h3>
      <p className="text-slate-300 leading-7">{text}</p>
    </div>
  );
}

function ListCard({
  title,
  items,
  color,
}: {
  title: string;
  items: string[];
  color: "blue" | "red" | "purple";
}) {
  const dot =
    color === "red"
      ? "bg-red-400"
      : color === "purple"
      ? "bg-purple-400"
      : "bg-blue-400";

  return (
    <div className="rounded-3xl border border-white/10 bg-white/[0.05] p-5">
      <h3 className="font-bold text-lg mb-4">{title}</h3>
      <ul className="space-y-3 text-slate-300">
        {items.map((item: string, index: number) => (
          <li key={index} className="flex gap-3">
            <span className={`mt-2 h-2 w-2 rounded-full ${dot}`} />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ChartCard({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded-3xl border border-white/10 bg-slate-950/60 p-5">
      <h3 className="font-bold mb-4">{title}</h3>
      {children}
    </div>
  );
}
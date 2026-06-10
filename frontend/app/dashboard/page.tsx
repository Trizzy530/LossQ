"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, useRef, type ReactNode } from "react";
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
const SELECTED_POLICY_CACHE_KEY = "lossq_selected_policy_number";
const SELECTED_CLAIM_CACHE_KEY = "lossq_selected_claim";
const CURRENT_UPLOAD_CACHE_KEY = "lossq_current_upload_claims";

type AnyObject = Record<string, any>;

type ToolKey =
  | "overview"
  | "profiles"
  | "upload"
  | "exposure-inputs"
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


function isOpenClaimStatus(claim: any) {
  const status = String(claim?.status || "").trim().toLowerCase();

  if (!status) return false;

  return [
    "open",
    "pending",
    "reopened",
    "active",
    "in progress",
    "watch",
  ].includes(status);
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

function normalizeProfiles(data: any): AnyObject[] {
  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.profiles)) return data.profiles;
  if (Array.isArray(data?.accounts)) return data.accounts;
  if (data && typeof data === "object" && data.policy_number) return [data];
  return [];
}

function firstNonEmptyArray(...values: any[]) {
  for (const value of values) {
    if (Array.isArray(value) && value.length > 0) return value;
  }

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


function getCachedSelectedPolicy() {
  if (typeof window === "undefined") return "";
  return normalizePolicyNumber(localStorage.getItem(SELECTED_POLICY_CACHE_KEY));
}

function setCachedSelectedPolicy(policyNumber: any) {
  if (typeof window === "undefined") return;

  const normalized = normalizePolicyNumber(policyNumber);

  if (normalized) {
    localStorage.setItem(SELECTED_POLICY_CACHE_KEY, normalized);
  }
}

function clearCachedSelectedPolicy() {
  if (typeof window === "undefined") return;
  localStorage.removeItem(SELECTED_POLICY_CACHE_KEY);
}

function getCachedSelectedClaim(): AnyObject | null {
  if (typeof window === "undefined") return null;

  try {
    const raw =
      sessionStorage.getItem(SELECTED_CLAIM_CACHE_KEY) ||
      localStorage.getItem(SELECTED_CLAIM_CACHE_KEY);

    const parsed = raw ? JSON.parse(raw) : null;
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch {
    return null;
  }
}

function setCachedSelectedClaim(claim: AnyObject) {
  if (typeof window === "undefined") return;

  if (claim && typeof claim === "object") {
    const value = JSON.stringify(claim);
    sessionStorage.setItem(SELECTED_CLAIM_CACHE_KEY, value);
    localStorage.setItem(SELECTED_CLAIM_CACHE_KEY, value);
  }
}

function clearCachedSelectedClaim() {
  if (typeof window === "undefined") return;

  sessionStorage.removeItem(SELECTED_CLAIM_CACHE_KEY);
  localStorage.removeItem(SELECTED_CLAIM_CACHE_KEY);
}


function getCachedLastUploadReview(): AnyObject {
  if (typeof window === "undefined") return {};

  try {
    const raw = localStorage.getItem("lossq_last_upload_review");
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function clearCachedLastUploadReview() {
  if (typeof window === "undefined") return;
  localStorage.removeItem("lossq_last_upload_review");
}

function getCachedCurrentUpload(): AnyObject {
  if (typeof window === "undefined") return {};

  try {
    const raw = localStorage.getItem(CURRENT_UPLOAD_CACHE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function setCachedCurrentUpload(upload: AnyObject) {
  if (typeof window === "undefined") return;
  localStorage.setItem(CURRENT_UPLOAD_CACHE_KEY, JSON.stringify(upload || {}));
}

function clearCachedCurrentUpload() {
  if (typeof window === "undefined") return;
  localStorage.removeItem(CURRENT_UPLOAD_CACHE_KEY);
}

function claimMatchesPolicySet(claim: any, policySet: Set<string>) {
  if (!policySet || policySet.size === 0) return false;
  return policySet.has(getClaimPolicyNumber(claim));
}

function mergeClaimsByNumber(existing: any[], incoming: any[]) {
  const map = new Map<string, any>();

  [...existing, ...incoming].forEach((claim) => {
    const key = `${claim?.claim_number || claim?.claimNumber || claim?.id || Math.random()}-${getClaimPolicyNumber(claim)}`;
    map.set(key, claim);
  });

  return Array.from(map.values());
}

function getClaimNumberValue(claim: any) {
  return String(claim?.claim_number || claim?.claimNumber || claim?.number || "").trim().toUpperCase();
}

function sameClaimRecord(a: any, b: any) {
  return (
    getClaimNumberValue(a) &&
    getClaimNumberValue(a) === getClaimNumberValue(b) &&
    getClaimPolicyNumber(a) === getClaimPolicyNumber(b)
  );
}


function cleanMoneyInput(value: any) {
  return String(value || "")
    .replace(/[^0-9.\-]/g, "")
    .trim();
}

function findTextValue(rawText: string, labels: string[]) {
  const text = String(rawText || "");
  const lines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  for (const label of labels) {
    const safe = label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const inline = new RegExp(`${safe}\\s*[:=\\-]?\\s*([^\\n\\r|]+)`, "i");
    const inlineMatch = text.match(inline);
    if (inlineMatch?.[1]) {
      const value = inlineMatch[1].trim();
      if (value && value.length < 120) return value;
    }

    const lineIndex = lines.findIndex((line) =>
      line.toLowerCase().includes(label.toLowerCase())
    );

    if (lineIndex >= 0 && lines[lineIndex + 1]) {
      const value = lines[lineIndex + 1].trim();
      if (value && value.length < 120) return value;
    }
  }

  return "";
}

function extractExposureInputsFromUploadText(rawText: string) {
  const text = String(rawText || "");

  if (!text.trim()) return {};

  const exposure: AnyObject = {
    current_premium: cleanMoneyInput(
      findTextValue(text, [
        "Current Premium",
        "Expiring Premium",
        "Annual Premium",
        "Premium",
      ])
    ),
    expiring_premium: cleanMoneyInput(
      findTextValue(text, [
        "Expiring Premium",
        "Prior Premium",
        "Current Term Premium",
      ])
    ),
    target_renewal_premium: cleanMoneyInput(
      findTextValue(text, [
        "Target Renewal Premium",
        "Target Premium",
        "Renewal Target",
      ])
    ),
    exposure_basis:
      findTextValue(text, [
        "Exposure Basis",
        "Rating Basis",
        "Premium Basis",
      ]) || "",
    payroll: cleanMoneyInput(
      findTextValue(text, [
        "Payroll",
        "Estimated Payroll",
        "Annual Payroll",
      ])
    ),
    revenue: cleanMoneyInput(
      findTextValue(text, [
        "Revenue",
        "Sales",
        "Gross Sales",
        "Annual Revenue",
        "Receipts",
      ])
    ),
    sales: cleanMoneyInput(
      findTextValue(text, [
        "Sales",
        "Gross Sales",
      ])
    ),
    receipts: cleanMoneyInput(
      findTextValue(text, [
        "Receipts",
        "Gross Receipts",
      ])
    ),
    employee_count:
      findTextValue(text, [
        "Employee Count",
        "Employees",
        "Number of Employees",
      ]) || "",
    vehicle_count:
      findTextValue(text, [
        "Vehicle Count",
        "Power Units",
        "Autos",
        "Scheduled Autos",
      ]) || "",
    driver_count:
      findTextValue(text, [
        "Driver Count",
        "Drivers",
        "Number of Drivers",
      ]) || "",
    property_tiv: cleanMoneyInput(
      findTextValue(text, [
        "Property TIV",
        "TIV",
        "Total Insured Value",
      ])
    ),
    tiv: cleanMoneyInput(
      findTextValue(text, [
        "TIV",
        "Total Insured Value",
      ])
    ),
    building_value: cleanMoneyInput(
      findTextValue(text, [
        "Building Value",
        "Building Limit",
      ])
    ),
    contents_value: cleanMoneyInput(
      findTextValue(text, [
        "Contents Value",
        "Business Personal Property",
        "BPP",
      ])
    ),
    square_footage:
      findTextValue(text, [
        "Square Footage",
        "Sq Ft",
        "Sq. Ft.",
      ]) || "",
    location_count:
      findTextValue(text, [
        "Location Count",
        "Locations",
        "Number of Locations",
      ]) || "",
    unit_count:
      findTextValue(text, [
        "Unit Count",
        "Units",
      ]) || "",
    class_code:
      findTextValue(text, [
        "Class Code",
        "Class Codes",
        "WC Code",
        "GL Class",
      ]) || "",
    class_codes:
      findTextValue(text, [
        "Class Codes",
        "Class Code",
        "WC Code",
        "GL Class",
      ]) || "",
    limits:
      findTextValue(text, [
        "Policy Limits",
        "Limits",
        "Coverage Limit",
      ]) || "",
    coverage_limit:
      findTextValue(text, [
        "Coverage Limit",
        "Policy Limits",
        "Limits",
      ]) || "",
    deductible:
      findTextValue(text, [
        "Deductible",
      ]) || "",
    retention:
      findTextValue(text, [
        "Retention",
        "SIR",
        "Self Insured Retention",
      ]) || "",
    cargo_limit:
      findTextValue(text, [
        "Cargo Limit",
        "Motor Truck Cargo Limit",
      ]) || "",
    umbrella_limit:
      findTextValue(text, [
        "Umbrella Limit",
        "Excess Limit",
        "Umbrella / Excess Limit",
      ]) || "",
    experience_mod:
      findTextValue(text, [
        "Experience Mod",
        "Experience Modification",
        "E-Mod",
        "Mod",
      ]) || "",
    mod:
      findTextValue(text, [
        "Experience Mod",
        "E-Mod",
        "Mod",
      ]) || "",
    exposure_change_percent:
      findTextValue(text, [
        "Exposure Change %",
        "Exposure Change",
        "Projected Change",
      ]) || "",
  };

  Object.keys(exposure).forEach((key) => {
    if (exposure[key] === "" || exposure[key] === null || exposure[key] === undefined) {
      delete exposure[key];
    }
  });

  return exposure;
}

function isBadCarrierValue(value: any) {
  const text = String(value || "").trim().toLowerCase();

  if (!text) return true;

  return [
    "exposure basis",
    "premium worksheet",
    "rating basis",
    "current premium",
    "expiring premium",
    "line coverage",
    "line-of-business",
    "line of business",
    "policy schedule",
    "coverage schedule",
    "carrier",
    "writing carrier",
  ].includes(text);
}

function chooseCleanCarrier(...values: any[]) {
  for (const value of values) {
    const cleaned = String(value || "").trim();
    if (cleaned && !isBadCarrierValue(cleaned)) return cleaned;
  }

  return "";
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

  useEffect(() => {
    if (typeof window === "undefined") return;

    const toolParam = new URLSearchParams(window.location.search).get("tool");
    const allowedTools: ToolKey[] = [
      "overview",
      "profiles",
      "upload",
      "exposure-inputs",
      "renewal-risk",
      "decision",
      "carrier-appetite",
      "submission-readiness",
      "carrier-match",
      "premium-forecast",
      "submission-builder",
      "summary",
      "memo",
      "charts",
      "claims",
    ];

    if (toolParam && allowedTools.includes(toolParam as ToolKey)) {
      setActiveTool(toolParam as ToolKey);
    }
  }, []);

  const [claims, setClaims] = useState<any[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const activeProfileRef = useRef<any>({});
  const dashboardLoadingRef = useRef(false);
  const loadVersionRef = useRef(0);
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
function getAccountDisplayName(item: any) {
  return (
    item?.business_name ||
    item?.insured ||
    item?.named_insured ||
    item?.account_name ||
    item?.customer_name ||
    item?.company_name ||
    item?.name ||
    ""
  );
}

function normalizeProfileName(item: any) {
  const accountName = getAccountDisplayName(item);

  return {
    ...item,
    business_name: accountName || item?.business_name || "",
    insured: item?.insured || accountName || "",
  };
}
  const [files, setFiles] = useState<FileList | null>(null);


  const [message, setMessage] = useState("");
  const [authReady, setAuthReady] = useState(false);
  const [dashboardLoading, setDashboardLoading] = useState(true);
  const [dashboardError, setDashboardError] = useState("");

  const [copilotOpen, setCopilotOpen] = useState(false);
  const [copilotQuestion, setCopilotQuestion] = useState("");
  const [copilotAnswer, setCopilotAnswer] = useState("");
  const [copilotLoading, setCopilotLoading] = useState(false);
  const [selectedClaimDetail, setSelectedClaimDetail] = useState<any | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const toolParam = new URLSearchParams(window.location.search).get("tool");

    if (toolParam !== "claims") return;

    const cachedClaim = getCachedSelectedClaim();

    if (cachedClaim) {
      setSelectedClaimDetail(cachedClaim);
    }
  }, []);


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
      await loadDashboard(getCachedSelectedPolicy());
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
    const cleanedIncoming = (incomingProfiles || [])
      .filter(Boolean)
      .map((item) => normalizeProfileName(item));

    setProfiles((prev) => {
      const merged = [...cleanedIncoming, ...prev.map((item) => normalizeProfileName(item))];
      const seen = new Set<string>();

      const next = merged.filter((item) => {
        const key =
          item?.policy_number ||
          item?.account_number ||
          item?.id ||
          `${getAccountDisplayName(item)}-${item?.carrier_name || ""}`;

        if (!key) return true;
        if (seen.has(String(key))) return false;

        seen.add(String(key));
        return true;
      });

      setCachedProfiles(next);
      return next;
    });
  }

  async function loadProfileList() {
    try {
      const cachedProfiles = getCachedProfiles();

      if (Array.isArray(cachedProfiles) && cachedProfiles.length > 0) {
        const normalizedCached = cachedProfiles.map((item: AnyObject) =>
          normalizeProfileName(item)
        );
        setProfiles(normalizedCached);
      }

      const profilesRes = await fetch(`${API}/account-profile/all`, {
        headers: authHeaders(),
      });

      if (profilesRes.status === 401 || profilesRes.status === 403) {
        clearSession();
        router.replace("/login?expired=1");
        return;
      }

      if (!profilesRes.ok) {
        return;
      }

      const data = await safeJson(profilesRes);
      const serverProfiles = Array.isArray(data)
        ? data
        : Array.isArray(data?.profiles)
        ? data.profiles
        : [];

      updateProfileList(serverProfiles);
    } catch {
      // Keep dashboard usable if profile list fetch fails.
    }
  }

  function newBlankProfile() {
    resetActiveWorkspace("New blank account profile started.");
    setActiveTool("profiles");
  }

  function resetActiveWorkspace(messageText?: string) {
    setProfile({
      business_name: "",
      carrier_name: "",
      writing_carrier: "",
      agency_name: "",
      account_number: "",
      customer_number: "",
      producer_number: "",
      policy_number: "",
      effective_date: "",
      expiration_date: "",
      evaluation_date: "",
      policies: [],
      validation: {},
      raw_text_preview: "",
    });

    setClaims([]);
    setSummary({});
    setDecision({});
    setCarrierAppetite({});
    setSubmissionReadiness({});
    setCarrierMatch({});
    setPremiumForecast({});
    setSubmissionBuilder({});
    setTimeline({});
    setRenewalMemo("");
    setCopilotAnswer("");
    setSelectedClaimDetail(null);

    clearCachedSelectedPolicy();
    clearCachedSelectedClaim();
    clearCachedLastUploadReview();
    clearCachedCurrentUpload();

    if (messageText) {
      setMessage(messageText);
    }
  }

  async function loadDashboard(policyNumberOverride?: string, skipProfileList = false) {
    if (!getToken()) {
      router.replace("/login?fresh=1");
      return;
    }

    setDashboardLoading(true);
    const myVersion = ++loadVersionRef.current;
    setDashboardError("");

    const cachedPolicyNumber = getCachedSelectedPolicy();
    const requestedPolicyNumber = normalizePolicyNumber(policyNumberOverride || cachedPolicyNumber);

    try {
      if (!skipProfileList) await loadProfileList();

    // Pre-load ref from cache immediately so filteredVisibleClaims has correct policies on first render
    if (requestedPolicyNumber) {
      const earlyMatch = getCachedProfiles().find((p: any) =>
        normalizePolicyNumber(p?.policy_number) === requestedPolicyNumber ||
        (p?.policies || []).some((pol: any) => normalizePolicyNumber(pol?.policy_number) === requestedPolicyNumber)
      );
      if (earlyMatch && (earlyMatch.policies || []).length > 0) {
        activeProfileRef.current = earlyMatch;
      }
    }

      let activeProfile = profile;

      if (requestedPolicyNumber) {
        const selectedRes = await fetch(
          `${API}/account-profile/policy/${encodeURIComponent(requestedPolicyNumber)}`,
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
            (item) => normalizePolicyNumber(item?.policy_number) === requestedPolicyNumber
          );

          activeProfile = {
            ...(cachedMatch || {}),
            ...fetchedProfile,
            policies:
              ((fetchedProfile?.policies?.length || 0) >= (cachedMatch?.policies?.length || 0)
                ? fetchedProfile?.policies
                : cachedMatch?.policies) ||
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

          activeProfileRef.current = activeProfile || {};
          setProfile(activeProfile || {});
          if (activeProfile?.policy_number) {
            updateProfileList([activeProfile]);
          }
        } else {
          const cachedMatch = getCachedProfiles().find(
            (item) => normalizePolicyNumber(item?.policy_number) === requestedPolicyNumber
          );

          if (cachedMatch) {
  activeProfile = normalizeProfileName(cachedMatch);
  setProfile(activeProfile);
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

          activeProfile = normalizeProfileName({
  ...(cachedMatch || {}),
  ...fetchedProfile,

  business_name:
    fetchedProfile?.business_name ||
    fetchedProfile?.insured ||
    fetchedProfile?.named_insured ||
    fetchedProfile?.account_name ||
    cachedMatch?.business_name ||
    cachedMatch?.insured ||
    cachedMatch?.named_insured ||
    cachedMatch?.account_name ||
    "",

  insured:
    fetchedProfile?.insured ||
    fetchedProfile?.business_name ||
    fetchedProfile?.named_insured ||
    fetchedProfile?.account_name ||
    cachedMatch?.insured ||
    cachedMatch?.business_name ||
    cachedMatch?.named_insured ||
    cachedMatch?.account_name ||
    "",

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
});

          setProfile(activeProfile || {});
          activeProfileRef.current = activeProfile || {};
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
        requestedPolicyNumber ||
        activeProfile?.policy_number ||
        profile?.policy_number ||
        "";

      const hasPolicy = policyNumber && policyNumber !== "Policy Not Set";

      if (hasPolicy) {
        setCachedSelectedPolicy(policyNumber);
      }

      /*
        Always fetch all organization claims here.
        The dashboard filters locally through visibleClaims so account policies
        like SA-ACCT-580219 can count child-policy claims such as SA-AUTO,
        SA-GL, SA-CARGO, and SA-WC correctly.
      */
      const claimsRes = await fetch(`${API}/claims/${(() => { const refPols = (activeProfileRef.current?.policies || []).map((p: any) => (p?.policy_number || '').trim().toUpperCase()).filter(Boolean); const cachedPols = getCachedProfiles().filter((p: any) => normalizePolicyNumber(p?.policy_number) === normalizePolicyNumber(requestedPolicyNumber) || (p?.policies || []).some((pol: any) => normalizePolicyNumber(pol?.policy_number) === normalizePolicyNumber(requestedPolicyNumber))).flatMap((p: any) => (p?.policies || []).map((pol: any) => (pol?.policy_number || '').trim().toUpperCase())); const ps = [...new Set([requestedPolicyNumber, ...refPols, ...cachedPols].filter(Boolean))]; return ps.length > 0 ? '?policy_numbers=' + ps.join(',') : ''; })()}`, { headers: authHeaders() });

      if (claimsRes.status === 401 || claimsRes.status === 403) {
        clearSession();
        router.replace("/login?expired=1");
        return;
      }

      if (claimsRes.ok) {
        const claimsData = await safeJson(claimsRes);
        const serverClaims = Array.isArray(claimsData)
          ? claimsData
          : Array.isArray(claimsData?.claims)
          ? claimsData.claims
          : [];

        const cachedUploadForPolicy = getCachedCurrentUpload();
        const policySet = new Set(
          [
            policyNumber,
            activeProfile?.policy_number,
            activeProfile?.account_number,
            activeProfile?.customer_number,
            ...firstNonEmptyArray(activeProfile?.policies, profile?.policies).map(
              (item: any) => item?.policy_number
            ),
            // Also include all policies from cached profiles matching this account
            ...getCachedProfiles()
              .filter((p: any) =>
                normalizePolicyNumber(p?.policy_number) === normalizePolicyNumber(policyNumber) ||
                normalizePolicyNumber(p?.account_number) === normalizePolicyNumber(policyNumber) ||
                (p?.policies || []).some((pol: any) => normalizePolicyNumber(pol?.policy_number) === normalizePolicyNumber(policyNumber))
              )
              .flatMap((p: any) => (p?.policies || []).map((pol: any) => pol?.policy_number))
          ]
            .map((item: any) => normalizePolicyNumber(item))
            .filter(Boolean)
        );


        const serverMatches = policySet.size > 0
          ? serverClaims.filter((claim: any) => claimMatchesPolicySet(claim, policySet))
          : serverClaims;

        const currentUpload = getCachedCurrentUpload();
        const currentUploadPolicies = new Set(
          (Array.isArray(currentUpload?.policy_numbers) ? currentUpload.policy_numbers : [])
            .map((item: any) => normalizePolicyNumber(item))
            .filter(Boolean)
        );
        const currentUploadClaims = Array.isArray(currentUpload?.claims)
          ? currentUpload.claims
          : [];
        const currentUploadMatches = currentUploadClaims.filter((claim: any) =>
          claimMatchesPolicySet(claim, policySet)
        );
        const currentUploadApplies =
          currentUploadMatches.length > 0 &&
          Array.from(policySet).some((policy) => currentUploadPolicies.has(policy));

        const cachedUpload = getCachedLastUploadReview();
        const cachedUploadClaims = Array.isArray(cachedUpload?.claims)
          ? cachedUpload.claims
          : [];
        const cachedMatches = currentUploadApplies
          ? []
          : cachedUploadClaims.filter((claim: any) => claimMatchesPolicySet(claim, policySet));

        // Priority:
        // 1. Current upload response for this selected policy/account.
        // 2. Backend server matches for the selected policy/account.
        // 3. Older cache only when no current upload is active.
        // 4. Empty array. Never fall back to unrelated organization-wide claims.
        if (currentUploadApplies) {
        if (myVersion === loadVersionRef.current) setClaims(currentUploadMatches);
        } else if (serverMatches.length > 0) {
        if (myVersion === loadVersionRef.current) setClaims(serverMatches);
        } else if (cachedMatches.length > 0) {
        if (myVersion === loadVersionRef.current) setClaims(cachedMatches);
        } else {
          if (myVersion === loadVersionRef.current) setClaims([]);
        }
      } else {
        const currentUpload = getCachedCurrentUpload();
        const currentUploadClaims = Array.isArray(currentUpload?.claims)
          ? currentUpload.claims
          : [];
        if (myVersion === loadVersionRef.current) setClaims(currentUploadClaims.length > 0 ? currentUploadClaims : []);
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
      console.log("CATCH BLOCK HIT:", arguments[0] || "unknown error");
      setDashboardError("Dashboard could not load. Confirm backend is running.");
      if (myVersion === loadVersionRef.current) setClaims([]);
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

    const normalizedPolicy = normalizePolicyNumber(policyNumber);

    setCachedSelectedPolicy(normalizedPolicy);

    // Clear stale dashboard state immediately so the previous profile's claims
    // cannot remain visible while the new account is loading.
    setClaims([]);
    setSelectedClaimDetail(null);
    clearCachedSelectedClaim();
    clearCachedCurrentUpload();

    setMessage(`Loading policy ${normalizedPolicy}...`);
    setCopilotAnswer("");
    setRenewalMemo("");
    setSummary({});
    setDecision({});
    setCarrierAppetite({});
    setSubmissionReadiness({});
    setCarrierMatch({});
    setPremiumForecast({});
    setSubmissionBuilder({});
    setTimeline({});

    // Pre-load the full profile from cache so policySet includes all sibling policies.
    const cachedMatch = getCachedProfiles().find(
      (p: any) =>
        normalizePolicyNumber(p?.policy_number) === normalizedPolicy ||
        normalizePolicyNumber(p?.account_number) === normalizedPolicy ||
        normalizePolicyNumber(p?.customer_number) === normalizedPolicy ||
        (p?.policies || []).some(
          (pol: any) => normalizePolicyNumber(pol?.policy_number) === normalizedPolicy
        )
    );

    if (cachedMatch) {
      activeProfileRef.current = cachedMatch;
      setProfile(cachedMatch);
    } else {
      activeProfileRef.current = {};
    }

    await loadDashboard(normalizedPolicy, true);
    setMessage(`Loaded policy ${normalizedPolicy}.`);
  }
  async function deleteProfile(profileToDelete: any) {
    const profileId = profileToDelete?.id;
    const policyNumber =
    profileToDelete?.policy_number ||
    profileToDelete?.account_number ||
    profileToDelete?.customer_number ||
    "";

  const profileLabel =
    profileToDelete?.business_name ||
    profileToDelete?.insured ||
    profileToDelete?.named_insured ||
    profileToDelete?.account_name ||
    policyNumber ||
    "this profile";

  if (!profileId && !policyNumber) {
    setMessage("No saved profile selected to delete.");
    return;
  }

  const confirmed = confirm(`Delete ${profileLabel}?`);
  if (!confirmed) return;

  const removeProfileLocally = () => {
    setProfiles((prev) => {
      const next = prev.filter((p) => {
        if (profileId && p?.id === profileId) return false;

        const existingPolicy =
          p?.policy_number ||
          p?.account_number ||
          p?.customer_number ||
          "";

        if (!profileId && policyNumber && existingPolicy === policyNumber) return false;
        return true;
      });

      setCachedProfiles(next);
      return next;
    });

    resetActiveWorkspace();
    setActiveTool("profiles");
  };

  // Clear the UI immediately so charts and Recharts data arrays reset right away.
  removeProfileLocally();
  setMessage(`Deleting ${profileLabel}...`);

  try {
    const deleteUrl = profileId
      ? `${API}/account-profile/id/${encodeURIComponent(String(profileId))}?delete_claims=true`
      : `${API}/account-profile/?policy_number=${encodeURIComponent(policyNumber)}&delete_claims=true`;

    const res = await fetch(deleteUrl, {
      method: "DELETE",
      headers: authHeaders(),
    });

    if (res.status === 401 || res.status === 403) {
      clearSession();
      router.replace("/login?expired=1");
      return;
    }

    const data = await safeJson(res);

    if (!res.ok || data?.deleted === false) {
      setMessage(
        `Removed ${profileLabel} from workspace. Backend response: ${
          data?.message || res.status
        }`
      );
      return;
    }

    setMessage(`Deleted ${profileLabel}.`);
  } catch {
    setMessage(`Deleted local profile ${profileLabel}. Backend delete unavailable.`);
  }
}


async function saveProfile() {
  const payload = {
    id: profile?.id || null,
    business_name: profile?.business_name || "",
    carrier_name: profile?.carrier_name || "",
    writing_carrier: profile?.writing_carrier || profile?.carrier_name || "",
    agency_name: profile?.agency_name || "",
    account_number: profile?.account_number || profile?.policy_number || "",
    customer_number: profile?.customer_number || profile?.account_number || profile?.policy_number || "",
    producer_number: profile?.producer_number || "",
    policy_number: profile?.policy_number || profile?.account_number || "",
    effective_date: profile?.effective_date || "",
    expiration_date: profile?.expiration_date || "",
    evaluation_date: profile?.evaluation_date || "",
    policies: Array.isArray(profile?.policies) ? profile.policies : [],
    validation: profile?.validation || {},
    raw_text_preview: profile?.raw_text_preview || "",
  };

  const saveKey =
    payload.account_number ||
    payload.customer_number ||
    payload.policy_number;

  if (!saveKey) {
    setMessage("Account number or policy number is required before saving.");
    return;
  }

  try {
    setMessage("Saving account profile...");

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
    const savedProfile = savedData?.id ? savedData : payload;

    setProfile(savedProfile);
    updateProfileList([savedProfile]);

    const selectedPolicy =
      savedProfile?.policy_number ||
      savedProfile?.account_number ||
      savedProfile?.customer_number ||
      "";

    if (selectedPolicy) {
      setCachedSelectedPolicy(selectedPolicy);
      await loadDashboard(selectedPolicy);
    }

    setMessage("Account profile saved.");
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


  function saveExposureInputs() {
    const selectedPolicy =
      profile?.policy_number ||
      profile?.account_number ||
      profile?.customer_number ||
      getCachedSelectedPolicy();

    const nextProfile = {
      ...profile,
      policy_number: profile?.policy_number || selectedPolicy || "",
      account_number: profile?.account_number || selectedPolicy || "",
      customer_number: profile?.customer_number || profile?.account_number || selectedPolicy || "",
    };

    setProfile(nextProfile);
    updateProfileList([nextProfile]);

    if (selectedPolicy) {
      setCachedSelectedPolicy(selectedPolicy);
    }

    setMessage("Exposure inputs saved locally for the selected account. Use Save Profile to sync the full account profile.");
  }

  async function uploadFiles() {
  if (isUploading) return;
  const selectedFiles = files ? Array.from(files) : [];
  if (selectedFiles.length === 0) {
    setMessage("Please select one or more PDF, Excel, or CSV files first.");
    return;
  }
  try {
    setIsUploading(true);
    clearCachedLastUploadReview();
    clearCachedCurrentUpload();
    setMessage("Uploading and analyzing loss runs with V2 parser...");
    
     const uploadResults: any[] = [];

    /*
      IMPORTANT:
      Universal OCR + Document Intelligence V2 currently accepts one file at a time.
      For multiple files, we upload each file through /upload/loss-run separately.
      Do not force the old selected policy number into a new upload.
      The parser should decide the account number, policy schedule, and claim policies.
    */

    for (const file of selectedFiles) {
      const formData = new FormData();
      formData.append("file", file);

      const res = await fetch(`${API}/upload/loss-run`, {
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

      console.log("LOSSQ_UPLOAD_DEBUG", data);
      uploadResults.push(data);
    }

    const primaryData = uploadResults[uploadResults.length - 1] || {};
    const primaryProfile =
      primaryData?.profile ||
      primaryData?.account_profile ||
      primaryData?.accountProfile ||
      {};
    const uploadedFileNames = selectedFiles.map((file) => file.name).join(", ");

    const combinedClaims = uploadResults.flatMap((item) =>
      firstNonEmptyArray(
        item?.saved_claim_rows,
        item?.claims,
        item?.parsed_claims,
        item?.claim_rows,
        item?.normalized_claims
      )
    );

    const combinedPolicies = uploadResults.flatMap((item) =>
      firstNonEmptyArray(
        item?.policies,
        item?.profile?.policies,
        item?.account_profile?.policies
      )
    );

    const totalSavedClaims = uploadResults.reduce(
      (sum, item) => sum + Number(item?.saved_claims || item?.claim_count || 0),
      0
    );

    if (typeof window !== "undefined") {
      localStorage.setItem(
        "lossq_last_upload_review",
        JSON.stringify({
          uploaded_at: new Date().toISOString(),
          uploaded_files: uploadResults.flatMap((item) => item?.uploaded_files || []).length
            ? uploadResults.flatMap((item) => item?.uploaded_files || [])
            : selectedFiles.map((file) => file.name),
          profile: primaryProfile || {},
          policies: combinedPolicies,
          claims: combinedClaims,
          saved_claim_rows: uploadResults.flatMap((item) =>
            firstNonEmptyArray(item?.saved_claim_rows, item?.claims, item?.parsed_claims)
          ),
          validation: primaryData?.validation || primaryProfile?.validation || {},
          saved_claims: totalSavedClaims,
          raw_response: uploadResults.length === 1 ? primaryData : uploadResults,
        })
      );
    }

    setMessage(
      `Upload complete using V2 parser. Saved ${totalSavedClaims} claim(s). New file(s): ${uploadedFileNames}`
    );

    window.setTimeout(() => {
      setMessage((current) =>
        current.startsWith("Upload complete using V2 parser") ? "" : current
      );
    }, 5000);

    if (primaryProfile && Object.keys(primaryProfile).length > 0) {
      const claimPolicyNumbers = Array.from(
        new Set(
          combinedClaims
            .map((claim: any) => claim?.policy_number || claim?.policyNumber || claim?.policy_no)
            .map((item: any) => normalizePolicyNumber(item))
            .filter(Boolean)
        )
      );

      const fallbackPolicies = claimPolicyNumbers.map((policyNumber) => ({
        policy_type: "Uploaded Loss Run",
        policy_number: policyNumber,
        carrier: primaryProfile?.carrier_name || primaryProfile?.writing_carrier || "",
        effective_date: primaryProfile?.effective_date || "",
        expiration_date: primaryProfile?.expiration_date || "",
      }));

      const uploadRawText =
      primaryData?.raw_text_preview ||
      primaryData?.raw_text ||
      primaryData?.text ||
      primaryProfile?.raw_text_preview ||
      primaryProfile?.raw_text ||
      "";

    const extractedExposureInputs = extractExposureInputsFromUploadText(uploadRawText);

    const cleanCarrierName = chooseCleanCarrier(
      primaryProfile?.carrier_name,
      primaryProfile?.writing_carrier,
      primaryData?.carrier_name,
      primaryData?.writing_carrier,
      primaryData?.account_profile?.carrier_name,
      primaryData?.account_profile?.writing_carrier
    );

    const uploadedProfile = {
        ...primaryProfile,
        ...extractedExposureInputs,
        carrier_name: cleanCarrierName || primaryProfile?.carrier_name || "",
        writing_carrier: cleanCarrierName || primaryProfile?.writing_carrier || primaryProfile?.carrier_name || "",

        insured:
          primaryProfile?.insured ||
          primaryProfile?.business_name ||
          primaryProfile?.named_insured ||
          primaryData?.business_name ||
          "",

        business_name:
          primaryProfile?.business_name ||
          primaryProfile?.insured ||
          primaryProfile?.named_insured ||
          primaryData?.business_name ||
          "",

        policy_number:
          primaryProfile?.policy_number ||
          primaryProfile?.account_number ||
          claimPolicyNumbers[0] ||
          "",

        policies: firstNonEmptyArray(
          primaryData?.policies,
          primaryProfile?.policies,
          primaryData?.account_profile?.policies,
          combinedPolicies,
          fallbackPolicies
        ),

        validation: primaryData?.validation || primaryProfile?.validation || {},
      };

      setProfile(uploadedProfile);
      updateProfileList([uploadedProfile]);
    }

    // Show the freshly parsed claim rows immediately. loadDashboard may fetch
    // /claims/, but /claims/ can be limited/stale, so we re-apply combinedClaims below.
    setClaims(combinedClaims);

    const uploadedPolicyNumber =
      primaryProfile?.policy_number ||
      primaryProfile?.account_number ||
      primaryProfile?.customer_number ||
      primaryData?.account_profile?.policy_number ||
      primaryData?.policy_number ||
      combinedClaims.find((claim: any) => claim?.policy_number || claim?.policyNumber || claim?.policy_no)?.policy_number ||
      "";

    const uploadPolicySet = Array.from(
      new Set(
        [
          uploadedPolicyNumber,
          ...combinedPolicies.map((item: any) => item?.policy_number),
          ...combinedClaims.map((claim: any) => claim?.policy_number || claim?.policyNumber || claim?.policy_no),
        ]
          .map((item: any) => normalizePolicyNumber(item))
          .filter(Boolean)
      )
    );

    const currentUploadSnapshot = {
      uploaded_at: new Date().toISOString(),
      policy_number: normalizePolicyNumber(uploadedPolicyNumber),
      policy_numbers: uploadPolicySet,
      profile: primaryProfile || {},
      policies: combinedPolicies,
      claims: combinedClaims,
      saved_claim_rows: combinedClaims,
      validation: primaryData?.validation || primaryProfile?.validation || {},
    };

    if (combinedClaims.length > 0) {
      setCachedCurrentUpload(currentUploadSnapshot);
    }

    if (uploadedPolicyNumber) {
      setCachedSelectedPolicy(uploadedPolicyNumber);
      await loadDashboard(uploadedPolicyNumber);
    } else {
      await loadDashboard();
    }

    // Keep the current upload authoritative after dashboard reload.
    // This prevents a stale /claims/ or old upload cache response from replacing the freshly parsed rows.
    if (combinedClaims.length > 0) {
      setClaims(combinedClaims);
    }

    setActiveTool("overview");

    window.setTimeout(() => {
      setMessage((current) =>
        current.includes("Upload complete using V2 parser") ? "" : current
      );
    }, 6000);
  } catch (error: any) {
    setMessage(
      `Upload failed before completion. Backend may have crashed. Error: ${
        error?.message || "Unknown error"
      }`
    );
  } finally {
    setIsUploading(false);
  }
}

async function downloadPdf(url: string, filename: string, init?: RequestInit) {
  const baseHeaders: Record<string, string> = {
    ...authHeaders(),
  };

  const initHeaders = (init?.headers || {}) as Record<string, string>;

  const res = await fetch(url, {
    ...init,
    headers: {
      ...baseHeaders,
      ...initHeaders,
    },
  });

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

function buildReportQuery() {
  const params = new URLSearchParams();

  if (profile?.id) {
    params.set("profile_id", String(profile.id));
  }

  if (profile?.policy_number) {
    params.set("policy_number", profile.policy_number);
  }

  if (profile?.account_number) {
    params.set("account_number", profile.account_number);
  }

  if (profile?.customer_number) {
    params.set("customer_number", profile.customer_number);
  }

  const query = params.toString();
  return query ? `?${query}` : "";
}

function buildReportPayload() {
  const currentUpload = getCachedCurrentUpload();
  const cachedUpload = getCachedLastUploadReview();

  const currentUploadClaims = Array.isArray(currentUpload?.claims) ? currentUpload.claims : [];
  const cachedUploadClaims = Array.isArray(cachedUpload?.claims) ? cachedUpload.claims : [];

  const currentUploadPolicies = new Set(
    (Array.isArray(currentUpload?.policy_numbers) ? currentUpload.policy_numbers : [])
      .map((item: any) => normalizePolicyNumber(item))
      .filter(Boolean)
  );

  const currentUploadApplies =
    currentUploadClaims.length > 0 &&
    (activePolicyNumbers.length === 0 && currentUploadClaims.length > 0) ||
    activePolicyNumbers.some((policyNumber) => currentUploadPolicies.has(policyNumber));

  const reportClaims =
    currentUploadApplies
      ? currentUploadClaims
      : visibleClaims.length > 0
      ? visibleClaims
      : claims.length > 0
      ? claims
      : cachedUploadClaims;

  const claimPolicyNumbers = Array.from(
    new Set(
      reportClaims
        .map((claim: any) => claim?.policy_number || claim?.policyNumber || claim?.policy_no)
        .map((item: any) => normalizePolicyNumber(item))
        .filter(Boolean)
    )
  );

  const policyNumbersForReport =
    activePolicyNumbers.length > 0 ? activePolicyNumbers : claimPolicyNumbers;

  return {
    profile: displayProfile || profile || currentUpload?.profile || cachedUpload?.profile || {},
    claims: reportClaims,
    summary: effectiveSummary || summary || {},
    decision: effectiveDecision || decision || {},
    carrier_appetite: effectiveCarrierAppetite || carrierAppetite || {},
    carrier_match: effectiveCarrierMatch || carrierMatch || {},
    premium_forecast: effectivePremiumForecast || premiumForecast || {},
    submission_readiness: effectiveSubmissionReadiness || submissionReadiness || {},
    policy_numbers_used: policyNumbersForReport,
    profile_id: profile?.id || displayProfile?.id || null,
  };
}


async function exportCarrierLossRun() {
  const query = buildReportQuery();

  await downloadPdf(
    `${API}/reports/loss-run-template-pdf${query}`,
    "lossq_carrier_loss_run.pdf"
  );
}

async function exportExecutiveReport() {
  const query = buildReportQuery();

  setMessage("Generating executive underwriting report...");

  await downloadPdf(
    `${API}/reports/executive-report-pdf${query}`,
    "lossq_executive_underwriting_report.pdf",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(buildReportPayload()),
    }
  );

  setMessage("Executive underwriting report generated.");
}


  async function generateRenewalMemo() {
    const selectedPolicy =
      displayProfile?.policy_number ||
      profile?.policy_number ||
      displayProfile?.account_number ||
      profile?.account_number ||
      displayProfile?.customer_number ||
      profile?.customer_number ||
      getCachedSelectedPolicy();

    const selectedName =
      displayProfile?.business_name ||
      displayProfile?.insured ||
      profile?.business_name ||
      profile?.insured ||
      "Selected Account";

    if (!selectedPolicy && visibleClaims.length === 0) {
      setRenewalMemo("Select a policy/account or upload claims first.");
      return;
    }

    setMemoLoading(true);
    setRenewalMemo(`Generating renewal memo for ${selectedPolicy || selectedName}...`);

    const buildLocalMemo = () => {
      const claimsUsed = visibleClaims.length || claims.length || 0;
      const openCount = openClaims || 0;
      const incurred = Number(totalIncurred || 0).toLocaleString();
      const reserve = Number(totalReserve || 0).toLocaleString();
      const riskLevel = effectiveSummary?.renewal_risk_level || localRenewalRiskLevel || "Needs Review";
      const score = effectiveSummary?.renewal_score ?? localRenewalScore ?? "Not Rated";
      const drivers = Array.isArray(effectiveSummary?.renewal_drivers)
        ? effectiveSummary.renewal_drivers
        : localRenewalDrivers || [];
      const concerns = Array.isArray(effectiveSummary?.carrier_concerns)
        ? effectiveSummary.carrier_concerns
        : [];

      return [
        `LOSSQ AI RENEWAL MEMO`,
        ``,
        `Account: ${selectedName}`,
        `Policy / Account Number: ${selectedPolicy || "Not Set"}`,
        `Renewal Score: ${score}`,
        `Renewal Risk Level: ${riskLevel}`,
        `Claims Reviewed: ${claimsUsed}`,
        `Open Claims: ${openCount}`,
        `Total Incurred: $${incurred}`,
        `Total Reserve: $${reserve}`,
        ``,
        `Executive Summary`,
        effectiveSummary?.renewal_summary ||
          `LossQ reviewed the loaded claim activity for ${selectedName}. The account currently reflects ${claimsUsed} claim(s), ${openCount} open claim(s), and $${incurred} in total incurred losses. Renewal risk is ${riskLevel}.`,
        ``,
        `Renewal Drivers`,
        ...(drivers.length ? drivers.map((item: any) => `- ${item}`) : [`- Claims loaded for underwriting review.`]),
        ``,
        `Carrier Concerns`,
        ...(concerns.length ? concerns.map((item: any) => `- ${item}`) : [`- Confirm open claim status, reserve adequacy, and corrective-action documentation before carrier submission.`]),
        ``,
        `Broker Recommendation`,
        effectiveSummary?.broker_recommendation ||
          `Prepare updated loss runs, explain open claims, confirm reserves, document corrective actions, and include a clear broker narrative before approaching renewal markets.`,
      ].join("\n");
    };

    try {
      const policy = selectedPolicy
        ? `?policy_number=${encodeURIComponent(selectedPolicy)}`
        : "";

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
        setRenewalMemo(buildLocalMemo());
        setMessage(`Backend memo route returned ${res.status}. LossQ generated a local renewal memo from visible claims.`);
        return;
      }

      const backendMemo =
        data?.memo ||
        data?.renewal_memo ||
        data?.content ||
        data?.summary ||
        "";

      if (!backendMemo || String(backendMemo).toLowerCase().includes("insufficient")) {
        setRenewalMemo(buildLocalMemo());
        setMessage("Backend memo did not return enough account detail. LossQ generated a local renewal memo from visible claims.");
        return;
      }

      setRenewalMemo(
        `Policy analyzed: ${data?.policy_number || selectedPolicy || "Selected Account"}\nClaims used: ${
          data?.claims_used ?? visibleClaims.length
        }\n\n${backendMemo}`
      );
    } catch (error: any) {
      setRenewalMemo(buildLocalMemo());
      setMessage(`Backend memo failed. LossQ generated a local renewal memo from visible claims.`);
    } finally {
      setMemoLoading(false);
    }
  }


  async function generateCarrierPacket() {
    const query = buildReportQuery();

    setMessage("Generating carrier submission packet...");

    await downloadPdf(
      `${API}/reports/carrier-packet-pdf${query}`,
      "lossq_carrier_submission_packet.pdf",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(buildReportPayload()),
      }
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

  async function openClaimRecord(claim: any) {
    if (!claim) return;

    setSelectedClaimDetail(claim);
    setCachedSelectedClaim(claim);

    const claimNumber =
      claim?.claim_number ||
      claim?.claimNumber ||
      claim?.claim_no ||
      claim?.number ||
      "";

    const policyNumber =
      claim?.policy_number ||
      claim?.policyNumber ||
      claim?.policy_no ||
      profile?.policy_number ||
      "";

    if (claim?.id) {
      router.push(
        `/claims/${claim.id}?claim_number=${encodeURIComponent(
          claimNumber
        )}&policy_number=${encodeURIComponent(policyNumber)}`
      );
      return;
    }

    try {
      setMessage(`Opening claim ${getClaimNumberValue(claim)} detail...`);

      const res = await fetch(`${API}/claims/`, { headers: authHeaders() });
      const data = res.ok ? await safeJson(res) : null;

      const serverClaims = Array.isArray(data)
        ? data
        : Array.isArray(data?.claims)
        ? data.claims
        : [];

      const match = serverClaims.find((item: any) => sameClaimRecord(item, claim));

      if (match?.id) {
        const mergedClaim = {
          ...claim,
          ...match,
        };

        setCachedSelectedClaim(mergedClaim);

        router.push(
          `/claims/${match.id}?claim_number=${encodeURIComponent(
            claimNumber || match?.claim_number || ""
          )}&policy_number=${encodeURIComponent(
            policyNumber || match?.policy_number || ""
          )}`
        );
        return;
      }

      setMessage(
        "Claim detail opened in preview because the saved database claim ID was not returned."
      );
    } catch {
      setMessage("Claim detail opened in preview because claim lookup failed.");
    }
  }

  function logout() {
    clearSession();
    router.replace("/login?fresh=1");
  }

const backendAccountProfile =
  summary?.account_profile ||
  submissionBuilder?.account_profile ||
  premiumForecast?.account_profile ||
  carrierMatch?.account_profile ||
  carrierAppetite?.account_profile ||
  decision?.account_profile ||
  {};

const backendPolicyNumbers = [
  ...(Array.isArray(summary?.policy_numbers_used) ? summary.policy_numbers_used : []),
  ...(Array.isArray(submissionBuilder?.policy_numbers_used)
    ? submissionBuilder.policy_numbers_used
    : []),
  ...(Array.isArray(premiumForecast?.policy_numbers_used)
    ? premiumForecast.policy_numbers_used
    : []),
  ...(Array.isArray(carrierMatch?.policy_numbers_used) ? carrierMatch.policy_numbers_used : []),
  ...(Array.isArray(carrierAppetite?.policy_numbers_used)
    ? carrierAppetite.policy_numbers_used
    : []),
  ...(Array.isArray(decision?.policy_numbers_used) ? decision.policy_numbers_used : []),
];

/*
  Guardrail: backendPolicyNumbers are useful for intelligence widgets, but they must
  NOT drive the Claims tab filter. Some backend endpoints can return stale policy
  numbers from the previously selected account when a newly uploaded file saved
  zero claims. Claims filtering must rely only on the selected profile/account and
  the selected profile's own policy schedule.
*/

const recoveredPolicySchedule = firstNonEmptyArray(
  (activeProfileRef.current?.policies?.length || 0) > 0 ? activeProfileRef.current.policies : null,
  profile?.policies,
  backendAccountProfile?.policies,
  summary?.account_profile?.policies,
  submissionBuilder?.account_profile?.policies
);

const displayProfile = {
  ...(backendAccountProfile || {}),
  ...(profile || {}),
  policies: recoveredPolicySchedule,
};

const claimBasedPolicySchedule = Object.values(
  (claims || []).reduce((acc: any, claim: any) => {
    const line =
      claim?.line_of_business ||
      claim?.lob ||
      claim?.coverage_line ||
      claim?.coverage ||
      claim?.claim_type ||
      "Other Commercial Line";

    const key = String(line || "Other Commercial Line").trim();

    if (!acc[key]) {
      acc[key] = {
        policy_type: key,
        line_of_business: key,
        coverage: key,
        policy_number:
          claim?.policy_number ||
          displayProfile?.policy_number ||
          displayProfile?.account_number ||
          "",
        writing_carrier:
          claim?.writing_carrier ||
          claim?.carrier_name ||
          displayProfile?.writing_carrier ||
          displayProfile?.carrier_name ||
          "",
        carrier:
          claim?.carrier ||
          claim?.carrier_name ||
          displayProfile?.carrier_name ||
          "",
        effective_date: displayProfile?.effective_date || "",
        expiration_date: displayProfile?.expiration_date || "",
        claim_count: 0,
        total_incurred: 0,
      };
    }

    acc[key].claim_count += 1;
    acc[key].total_incurred += Number(
      claim?.total_incurred ||
      claim?.incurred ||
      claim?.total ||
      0
    );

    return acc;
  }, {})
);

const policySchedule =
  recoveredPolicySchedule.length > 0 ? recoveredPolicySchedule : claimBasedPolicySchedule;

const activeAccountPolicyNumber = normalizePolicyNumber(displayProfile?.policy_number);
const activeAccountNumber = normalizePolicyNumber(displayProfile?.account_number);
const activeCustomerNumber = normalizePolicyNumber(displayProfile?.customer_number);

const activePolicyNumbers = Array.from(
  new Set(
    [
      ...policySchedule.map((item: any) => item?.policy_number),
      activeAccountPolicyNumber,
      activeAccountNumber,
      activeCustomerNumber,
    ]
      .map((item: any) => normalizePolicyNumber(item))
      .filter(Boolean)
  )
);

const hasActiveAccount = Boolean(
  getAccountDisplayName(displayProfile) ||
    displayProfile?.carrier_name ||
    displayProfile?.policy_number ||
    activePolicyNumbers.length > 0 ||
    summary?.claims_used != null
);
const filteredVisibleClaims = claims;

const currentUploadReview = getCachedCurrentUpload();
const currentUploadClaims = Array.isArray(currentUploadReview?.claims)
  ? currentUploadReview.claims
  : [];
const currentUploadPolicySet = new Set(
  [
    currentUploadReview?.profile?.policy_number,
    currentUploadReview?.profile?.account_number,
    ...(Array.isArray(currentUploadReview?.policy_numbers)
      ? currentUploadReview.policy_numbers
      : []),
    ...(Array.isArray(currentUploadReview?.policies)
      ? currentUploadReview.policies.map((item: any) => item?.policy_number)
      : []),
  ]
    .map((item: any) => normalizePolicyNumber(item))
    .filter(Boolean)
);
const currentUploadMatches = currentUploadClaims.filter((claim: any) => {
  const claimPolicy = getClaimPolicyNumber(claim);

  if (activePolicyNumbers.length > 0) {
    return activePolicyNumbers.includes(claimPolicy);
  }

  if (currentUploadPolicySet.size > 0) {
    return currentUploadPolicySet.has(claimPolicy);
  }

  return false;
});

const lastUploadReview = getCachedLastUploadReview();
const lastUploadClaims = Array.isArray(lastUploadReview?.claims)
  ? lastUploadReview.claims
  : [];
const lastUploadPolicySet = new Set(
  [
    lastUploadReview?.profile?.policy_number,
    lastUploadReview?.profile?.account_number,
    ...(Array.isArray(lastUploadReview?.policies)
      ? lastUploadReview.policies.map((item: any) => item?.policy_number)
      : []),
  ]
    .map((item: any) => normalizePolicyNumber(item))
    .filter(Boolean)
);

const visibleClaims =
  filteredVisibleClaims.length > 0
    ? filteredVisibleClaims
    : currentUploadMatches.length > 0
    ? currentUploadMatches
    : activePolicyNumbers.some((policyNumber) => lastUploadPolicySet.has(policyNumber))
    ? lastUploadClaims
    : [];

function hasValidatedClaimData(claim: any) {
  if (!claim || typeof claim !== "object") return false;

  const hasClaimNumber = Boolean(getClaimNumberValue(claim));
  const hasPolicy = Boolean(getClaimPolicyNumber(claim));
  const hasAmount =
    getClaimIncurred(claim) > 0 ||
    toMoneyNumber(claim?.paid_amount || claim?.paid || claim?.paid_loss) > 0 ||
    toMoneyNumber(claim?.reserve_amount || claim?.reserve || claim?.outstanding_reserve) > 0;

  return hasClaimNumber && hasPolicy && hasAmount;
}

const validatedVisibleClaims = visibleClaims.filter((claim: any) => hasValidatedClaimData(claim));
const intelligenceClaims = validatedVisibleClaims.length > 0 ? validatedVisibleClaims : visibleClaims;
const validatedClaimsAvailable = intelligenceClaims.length > 0;

const backendMetrics =
  summary?.renewal_metrics ||
  summary?.metrics ||
  decision?.decision_metrics ||
  carrierAppetite?.appetite_metrics ||
  premiumForecast?.forecast_metrics ||
  submissionBuilder?.supporting_intelligence?.summary?.renewal_metrics ||
  submissionBuilder?.supporting_intelligence?.summary?.metrics ||
  {};

const backendClaimsUsed =
  summary?.claims_used ??
  submissionBuilder?.claims_used ??
  premiumForecast?.claims_used ??
  carrierMatch?.claims_used ??
  carrierAppetite?.claims_used ??
  decision?.claims_used;

const totalClaims = hasActiveAccount
  ? visibleClaims.length
  : Number(backendMetrics?.total_claims ?? backendClaimsUsed ?? 0);

const openClaims = hasActiveAccount
  ? visibleClaims.filter((c: any) => String(c.status || "").toLowerCase() === "open").length
  : Number(backendMetrics?.open_claims ?? 0);

const totalIncurred = hasActiveAccount
  ? visibleClaims.reduce((sum: number, c: any) => sum + getClaimIncurred(c), 0)
  : Number(backendMetrics?.total_incurred ?? 0);

const openVisibleClaims = visibleClaims.filter((claim: any) => isOpenClaimStatus(claim));
const closedVisibleClaims = visibleClaims.filter((claim: any) => !isOpenClaimStatus(claim));
const groupedVisibleClaims = [...openVisibleClaims, ...closedVisibleClaims];

const localClaimTotal = intelligenceClaims.reduce((sum: number, c: any) => sum + getClaimIncurred(c), 0);
const localOpenClaimCount = intelligenceClaims.filter((claim: any) => isOpenClaimStatus(claim)).length;
const localLitigationCount = intelligenceClaims.filter((c: any) => {
  const text = `${c?.litigation || ""} ${c?.litigation_status || ""} ${c?.description || ""} ${c?.flag || ""}`.toLowerCase();
  return text.includes("litigation") || text.includes("attorney") || text.includes("suit");
}).length;
const localLargeLossCount = intelligenceClaims.filter((c: any) => getClaimIncurred(c) >= 50000).length;
const localRenewalPenalty = Math.min(70, localOpenClaimCount * 10 + localLitigationCount * 15 + localLargeLossCount * 10 + Math.max(0, intelligenceClaims.length - 3) * 4);
const localRenewalScore = intelligenceClaims.length > 0 ? Math.max(30, 92 - localRenewalPenalty) : null;
const localRenewalRiskLevel =
  localRenewalScore == null
    ? "Insufficient Data"
    : localRenewalScore >= 80
    ? "Low"
    : localRenewalScore >= 65
    ? "Moderate"
    : localRenewalScore >= 50
    ? "High"
    : "Critical";
const localCarrierAppetiteScore = localRenewalScore == null ? null : Math.max(20, Math.min(95, localRenewalScore - localLargeLossCount * 4));
const localSubmissionReadinessScore = intelligenceClaims.length > 0 ? Math.min(95, 70 + Math.min(20, visibleClaims.length * 3)) : null;

const backendInsufficientText = JSON.stringify({ summary, decision, carrierAppetite, submissionReadiness, premiumForecast, carrierMatch }).toLowerCase();
const backendSaysInsufficient =
  backendInsufficientText.includes("insufficient") ||
  backendInsufficientText.includes("no account-specific claims") ||
  backendInsufficientText.includes("no account specific claims") ||
  backendInsufficientText.includes("no validated claims") ||
  backendInsufficientText.includes("not parsed or validated") ||
  backendInsufficientText.includes("claims were not parsed") ||
  backendInsufficientText.includes("no carrier match generated") ||
  Number(backendClaimsUsed || 0) === 0;

const localRenewalDrivers = [
  `${intelligenceClaims.length} claim(s) analyzed for the selected account.`,
  `${localOpenClaimCount} open claim(s).`,
  `$${Number(localClaimTotal || 0).toLocaleString()} total incurred.`,
  `${localLargeLossCount} large loss claim(s) at or above $50,000.`,
  `${localLitigationCount} litigation/attorney indicator(s).`,
];

const effectiveSummary =
  validatedClaimsAvailable
    ? {
        ...(summary || {}),
        renewal_score: localRenewalScore,
        renewal_risk_level: localRenewalRiskLevel,
        renewal_drivers: localRenewalDrivers,
        carrier_concerns:
          localOpenClaimCount > 0 || localLargeLossCount > 0 || localLitigationCount > 0
            ? [
                localOpenClaimCount > 0
                  ? "Open claim activity requires underwriting review."
                  : "Open claim count is controlled.",
                localLargeLossCount > 0
                  ? "Large loss severity may affect renewal terms."
                  : "No claim over the large-loss threshold was detected.",
                localLitigationCount > 0
                  ? "Litigation/attorney involvement should be documented."
                  : "No litigation indicator detected from visible claims.",
              ]
            : ["Claims loaded. No major severity indicator detected from visible claims."],
        broker_recommendation:
          "Use the loaded claims to prepare a carrier narrative, explain open claims, confirm reserves, and document corrective actions before submission.",
        renewal_summary:
          `LossQ analyzed ${intelligenceClaims.length} claim(s) for the selected account with $${Number(localClaimTotal || 0).toLocaleString()} total incurred. Renewal risk is ${localRenewalRiskLevel}.`,
        claims_used: intelligenceClaims.length,
        policy_numbers_used: activePolicyNumbers.length > 0 ? activePolicyNumbers : Array.from(currentUploadPolicySet),
        data_source: backendSaysInsufficient ? "local_visible_claims_fallback" : "local_visible_claims",
      }
    : summary;

const effectiveDecision =
  validatedClaimsAvailable
    ? {
        ...(decision || {}),
        renewal_probability: Math.max(35, Math.min(95, localRenewalScore || 50)),
        expected_premium_impact:
          localRenewalRiskLevel === "Low"
            ? "Flat to modest increase"
            : localRenewalRiskLevel === "Moderate"
            ? "Moderate increase possible"
            : "Increase or restriction likely",
        carrier_appetite: localCarrierAppetiteScore && localCarrierAppetiteScore >= 75 ? "Standard / Preferred" : "Selective",
        marketability_score: localCarrierAppetiteScore,
        submission_readiness:
          "Claims are loaded. Complete carrier narrative, open-claim explanations, reserve notes, and corrective actions before submission.",
        underwriting_concerns: [
          `${intelligenceClaims.length} claim(s) in the selected account.`,
          `${localOpenClaimCount} open claim(s).`,
          `${localLargeLossCount} large loss claim(s) over $50,000.`,
          `${localLitigationCount} litigation/attorney indicator(s).`,
        ],
        best_market_types: ["Standard market", "Middle-market commercial carrier", "E&S backup if loss activity worsens"],
        underwriter_decision_summary:
          `The account has ${visibleClaims.length} loaded claim(s) and $${Number(localClaimTotal || 0).toLocaleString()} total incurred. Review open claims, large losses, and reserve adequacy before final carrier decision.`,
        claims_used: intelligenceClaims.length,
        policy_numbers_used: activePolicyNumbers.length > 0 ? activePolicyNumbers : Array.from(currentUploadPolicySet),
        data_source: backendSaysInsufficient ? "local_visible_claims_fallback" : "local_visible_claims",
      }
    : decision;

const localClaimLines = Array.from(
  new Set(
    intelligenceClaims
      .map((claim: any) =>
        String(
          claim?.line_of_business ||
            claim?.lineOfBusiness ||
            claim?.claim_type ||
            claim?.claimType ||
            claim?.coverage ||
            ""
        ).toLowerCase()
      )
      .filter(Boolean)
  )
);

const appetiteHasAuto = localClaimLines.some(
  (line) => line.includes("auto") || line.includes("truck")
);
const appetiteHasGL = localClaimLines.some(
  (line) => line.includes("general") || line.includes("liability")
);
const appetiteHasWC = localClaimLines.some(
  (line) => line.includes("worker") || line.includes("comp")
);
const appetiteHasCargo = localClaimLines.some((line) => line.includes("cargo"));

const appetiteOpenClaimsCount = intelligenceClaims.filter((claim: any) =>
  isOpenClaimStatus(claim)
).length;

const appetiteTotalReserve = intelligenceClaims.reduce((sum: number, claim: any) => {
  return (
    sum +
    toMoneyNumber(
      claim?.reserve_amount ||
        claim?.reserveAmount ||
        claim?.reserve ||
        claim?.outstanding_reserve ||
        0
    )
  );
}, 0);

const appetiteHasLargeLoss = intelligenceClaims.some(
  (claim: any) => getClaimIncurred(claim) >= 50000
);

const appetiteHasOpenReserveConcern =
  appetiteOpenClaimsCount > 0 && appetiteTotalReserve > 25000;

const localCarrierBuckets = [];

if (appetiteHasAuto) {
  localCarrierBuckets.push({
    carrier_type: appetiteHasOpenReserveConcern
      ? "Transportation / Commercial Auto Selective Market"
      : "Transportation-Focused Standard Auto Market",
    match_score: Math.max(
      35,
      Math.min(92, (localCarrierAppetiteScore || 60) + (appetiteHasOpenReserveConcern ? -8 : 6))
    ),
    fit: appetiteHasOpenReserveConcern ? "Conditional fit" : "Strong fit",
  });
}

if (appetiteHasGL) {
  localCarrierBuckets.push({
    carrier_type: appetiteHasLargeLoss
      ? "Regional Casualty / General Liability Selective Market"
      : "Regional General Liability Market",
    match_score: Math.max(
      35,
      Math.min(90, (localCarrierAppetiteScore || 60) + (appetiteHasLargeLoss ? -5 : 4))
    ),
    fit: appetiteHasLargeLoss ? "Moderate fit with narrative" : "Moderate fit",
  });
}

if (appetiteHasWC) {
  localCarrierBuckets.push({
    carrier_type:
      appetiteOpenClaimsCount > 0
        ? "Workers Comp Loss-Sensitive Market"
        : "Workers Comp Standard Market",
    match_score: Math.max(
      35,
      Math.min(88, (localCarrierAppetiteScore || 60) - (appetiteOpenClaimsCount > 0 ? 6 : 0))
    ),
    fit: appetiteOpenClaimsCount > 0 ? "Conditional fit" : "Standard fit",
  });
}

if (appetiteHasCargo) {
  localCarrierBuckets.push({
    carrier_type: "Motor Truck Cargo Market",
    match_score: Math.max(40, Math.min(90, (localCarrierAppetiteScore || 60) + 3)),
    fit: "Line-specific fit",
  });
}

if (localCarrierBuckets.length === 0) {
  localCarrierBuckets.push({
    carrier_type: "Commercial Casualty Market",
    match_score: localCarrierAppetiteScore || 60,
    fit: "Needs coverage classification",
  });
}

const effectiveCarrierAppetite =
  validatedClaimsAvailable
    ? {
        ...(carrierAppetite || {}),
        carrier_appetite_score: localCarrierAppetiteScore,
        carrier_appetite_level:
          localCarrierAppetiteScore == null
            ? "Not Rated"
            : localCarrierAppetiteScore >= 80
            ? "Preferred"
            : localCarrierAppetiteScore >= 65
            ? "Standard"
            : "Selective",
        best_fit_carriers: localCarrierBuckets.sort(
          (a, b) => Number(b.match_score || 0) - Number(a.match_score || 0)
        ),
        carrier_match_reasons: [
          `${intelligenceClaims.length} claim(s) are loaded across ${
            localClaimLines.length || 1
          } coverage line(s).`,
          appetiteHasOpenReserveConcern
            ? "Open reserve exposure requires a clear claim-status and reserve adequacy narrative."
            : "Reserve exposure appears manageable based on currently visible claims.",
          appetiteHasLargeLoss
            ? "Large-loss activity may limit preferred-market appetite until the account story is explained."
            : "No severe large-loss concentration is currently driving the appetite result.",
          appetiteHasAuto
            ? "Transportation and commercial auto markets should be prioritized because auto liability claims are present."
            : "Market selection should follow the dominant coverage lines shown in the claim data.",
        ],
        market_strategy: appetiteHasOpenReserveConcern
          ? "Market this account through transportation-focused and selective casualty channels first. Include a clear loss narrative, open-claim status, reserve explanation, corrective actions, driver/safety controls, and claim closure plan."
          : "Market this account to standard commercial markets first, with regional and selective markets as backup. Include loss narrative, corrective actions, and current claim status notes.",
        placement_summary:
          localCarrierAppetiteScore != null && localCarrierAppetiteScore >= 65
            ? `Claims are loaded for this account. Appetite is ${localCarrierAppetiteScore}/100, making the account marketable in standard-to-selective channels depending on carrier tolerance by line of business.`
            : `Claims are loaded for this account. Appetite is ${localCarrierAppetiteScore || 0}/100, so the account should be approached through selective markets with a strong underwriting narrative.`,
        claims_used: intelligenceClaims.length,
        policy_numbers_used:
          activePolicyNumbers.length > 0 ? activePolicyNumbers : Array.from(currentUploadPolicySet),
        data_source: backendSaysInsufficient
          ? "local_visible_claims_fallback"
          : "local_visible_claims",
      }
    : carrierAppetite;


function isInsufficientBackendMessage(value: any) {
  const text = String(value || "").toLowerCase();

  return (
    !text ||
    text.includes("insufficient") ||
    text.includes("no validated claims") ||
    text.includes("no carrier match generated") ||
    text.includes("claims were not parsed") ||
    text.includes("not parsed or validated") ||
    text.includes("claims were not validated") ||
    text.includes("no account-specific claims") ||
    text.includes("no account specific claims") ||
    text.includes("no forecast generated")
  );
}

const hasRealCurrentPremium =
  Number(premiumForecast?.current_premium || 0) > 0 ||
  Number(premiumForecast?.currentPremium || 0) > 0 ||
  Number(profile?.current_premium || 0) > 0 ||
  Number(displayProfile?.current_premium || 0) > 0;

const realCurrentPremium =
  Number(premiumForecast?.current_premium || 0) ||
  Number(premiumForecast?.currentPremium || 0) ||
  Number(profile?.current_premium || 0) ||
  Number(displayProfile?.current_premium || 0) ||
  0;

const localPremiumIncreasePercent =
  intelligenceClaims.length > 0
    ? localRenewalRiskLevel === "Low"
      ? 5
      : localRenewalRiskLevel === "Moderate"
      ? 12
      : localRenewalRiskLevel === "High"
      ? 25
      : 40
    : null;

const localPremiumConfidence =
  intelligenceClaims.length > 0
    ? Math.min(85, 55 + Math.min(30, intelligenceClaims.length * 5))
    : null;

const localPremiumBestCase =
  localPremiumIncreasePercent != null
    ? Math.max(0, localPremiumIncreasePercent - 8)
    : null;

const localPremiumWorstCase =
  localPremiumIncreasePercent != null
    ? localPremiumIncreasePercent + 18
    : null;

const localExpectedRenewalPremium =
  hasRealCurrentPremium && localPremiumIncreasePercent != null
    ? Math.round(realCurrentPremium * (1 + localPremiumIncreasePercent / 100))
    : null;

const premiumBackendHasUsableForecast =
  Number(premiumForecast?.current_premium || 0) > 0 &&
  Number(premiumForecast?.expected_renewal_premium || 0) > 0 &&
  !isInsufficientBackendMessage(premiumForecast?.forecast_summary);

const localForecastDrivers =
  intelligenceClaims.length > 0
    ? [
        `${intelligenceClaims.length} validated claim row(s) loaded for the selected account.`,
        `${localOpenClaimCount} open claim(s) affecting renewal pressure.`,
        `$${Number(localClaimTotal || 0).toLocaleString()} total incurred losses.`,
        `${localLargeLossCount} large loss claim(s) at or above $50,000.`,
        `${localLitigationCount} litigation/attorney indicator(s).`,
        hasRealCurrentPremium
          ? `Current premium of $${Number(realCurrentPremium || 0).toLocaleString()} was used to estimate renewal premium.`
          : "Current premium/exposure data is missing, so LossQ is showing a claim-based pressure estimate instead of a renewal dollar projection.",
      ]
    : ["No validated claims were available."];

const effectivePremiumForecast =
  validatedClaimsAvailable
    ? {
        ...(premiumForecast || {}),

        forecast_type: hasRealCurrentPremium
          ? "premium_projection"
          : "claim_based_pressure_estimate",

        current_premium: hasRealCurrentPremium ? realCurrentPremium : null,

        expected_renewal_premium:
          premiumBackendHasUsableForecast
            ? premiumForecast.expected_renewal_premium
            : localExpectedRenewalPremium,

        expected_increase_percent:
          premiumBackendHasUsableForecast
            ? premiumForecast.expected_increase_percent
            : localPremiumIncreasePercent,

        confidence_score:
          premiumBackendHasUsableForecast
            ? premiumForecast.confidence_score
            : localPremiumConfidence,

        best_case_percent:
          premiumBackendHasUsableForecast
            ? premiumForecast.best_case_percent
            : localPremiumBestCase,

        likely_range_percent:
          premiumBackendHasUsableForecast
            ? premiumForecast.likely_range_percent
            : localPremiumIncreasePercent != null
            ? `${Math.max(0, localPremiumIncreasePercent - 5)}% to ${
                localPremiumIncreasePercent + 10
              }%`
            : "-",

        worst_case_percent:
          premiumBackendHasUsableForecast
            ? premiumForecast.worst_case_percent
            : localPremiumWorstCase,

        forecast_drivers:
          premiumBackendHasUsableForecast &&
          Array.isArray(premiumForecast?.forecast_drivers) &&
          premiumForecast.forecast_drivers.length > 0 &&
          !premiumForecast.forecast_drivers.some((item: any) =>
            isInsufficientBackendMessage(item)
          )
            ? premiumForecast.forecast_drivers
            : localForecastDrivers,

        forecast_summary:
          premiumBackendHasUsableForecast
            ? premiumForecast.forecast_summary
            : hasRealCurrentPremium
            ? `LossQ generated a claim-based renewal premium projection using ${intelligenceClaims.length} validated claim row(s), $${Number(localClaimTotal || 0).toLocaleString()} total incurred, ${localOpenClaimCount} open claim(s), ${localLargeLossCount} large loss claim(s), and a current premium of $${Number(realCurrentPremium || 0).toLocaleString()}. Estimated pressure is approximately ${localPremiumIncreasePercent ?? 0}%.`
            : `LossQ has validated claim rows for this account, but no current premium or exposure basis was provided. No renewal dollar amount is being projected. The displayed ${localPremiumIncreasePercent ?? 0}% is a claims-derived renewal pressure estimate based on claim frequency, severity, open claims, litigation indicators, and total incurred losses.`,

        claims_used: intelligenceClaims.length,
        policy_numbers_used:
          activePolicyNumbers.length > 0 ? activePolicyNumbers : Array.from(currentUploadPolicySet),
        data_source: "local_visible_claims",
      }
    : premiumForecast;



const premiumAccuracyStatus = (() => {
  const currentPremium = Number(effectivePremiumForecast?.current_premium || 0);
  const expectedRenewal = Number(effectivePremiumForecast?.expected_renewal_premium || 0);

  const hasUniversalExposureBasis = Boolean(
    displayProfile?.payroll ||
      displayProfile?.revenue ||
      displayProfile?.sales ||
      displayProfile?.receipts ||
      displayProfile?.employee_count ||
      displayProfile?.employeeCount ||
      displayProfile?.vehicle_count ||
      displayProfile?.vehicleCount ||
      displayProfile?.driver_count ||
      displayProfile?.driverCount ||
      displayProfile?.property_tiv ||
      displayProfile?.tiv ||
      displayProfile?.building_value ||
      displayProfile?.contents_value ||
      displayProfile?.square_footage ||
      displayProfile?.location_count ||
      displayProfile?.unit_count ||
      displayProfile?.class_code ||
      displayProfile?.class_codes ||
      displayProfile?.limits ||
      displayProfile?.deductible ||
      displayProfile?.retention ||
      displayProfile?.experience_mod ||
      displayProfile?.mod ||
      displayProfile?.coverage_limit ||
      displayProfile?.cyber_revenue ||
      displayProfile?.professional_revenue ||
      displayProfile?.cargo_limit ||
      displayProfile?.umbrella_limit ||
      displayProfile?.exposure_basis
  );

  const detectedLines = Array.from(
    new Set(
      [
        ...policySchedule.map((item: any) =>
          String(
            item?.policy_type ||
              item?.line_coverage ||
              item?.line_of_business ||
              item?.coverage ||
              ""
          ).trim()
        ),
        ...intelligenceClaims.map((claim: any) =>
          String(
            claim?.line_of_business ||
              claim?.lob ||
              claim?.coverage_line ||
              claim?.coverage ||
              claim?.claim_type ||
              ""
          ).trim()
        ),
      ].filter(Boolean)
    )
  );

  const lineText =
    detectedLines.length > 0
      ? detectedLines.slice(0, 6).join(", ")
      : "commercial lines of business";

  if (!currentPremium || currentPremium <= 0) {
    return {
      level: "Premium Projection Unavailable",
      confidence: "Insufficient",
      message:
        `Add current premium and exposure basis before relying on a renewal dollar projection. LossQ can still show claim-based renewal pressure across ${lineText}.`,
      allowDollarProjection: false,
    };
  }

  if (!hasUniversalExposureBasis) {
    return {
      level: "Limited Confidence Projection",
      confidence: "Limited",
      message:
        "Current premium is available, but exposure data is missing. Add the exposure basis for the applicable line of business, such as payroll, revenue, sales, class codes, property values, TIV, limits, deductibles, retention, vehicle/unit counts, employee count, or location data.",
      allowDollarProjection: true,
    };
  }

  if (validatedClaimsAvailable && expectedRenewal > 0) {
    return {
      level: "High Confidence Estimate",
      confidence: "Strong",
      message:
        `LossQ has current premium, claim activity, and exposure basis for ${lineText}. This is a defensible renewal premium range, not a guaranteed carrier quote.`,
      allowDollarProjection: true,
    };
  }

  return {
    level: "Moderate Confidence Estimate",
    confidence: "Moderate",
    message:
      "LossQ has partial premium and exposure data. Confirm claim totals, exposure changes, limits, deductibles, retention, class codes, coverage terms, and carrier appetite before final pricing.",
    allowDollarProjection: true,
  };
})();

const backendTopCarriersAreUsable =
  Array.isArray(carrierMatch?.top_carriers) &&
  carrierMatch.top_carriers.length > 0 &&
  !carrierMatch.top_carriers.some((item: any) =>
    isInsufficientBackendMessage(
      `${item?.carrier || ""} ${item?.reason || ""} ${item?.fit || ""} ${item?.summary || ""}`
    )
  );

const realCarrierDatabaseAvailable = Boolean(
  carrierMatch?.carrier_database_enabled ||
    carrierMatch?.real_carrier_database_enabled ||
    carrierMatch?.source === "carrier_database" ||
    carrierMatch?.data_source === "carrier_database"
);

const lineBasedMarketCategories = [];

if (appetiteHasAuto) {
  lineBasedMarketCategories.push({
    market_category: appetiteHasOpenReserveConcern
      ? "Transportation selective market"
      : "Transportation standard market",
    match_score: Math.max(
      35,
      Math.min(92, (localCarrierAppetiteScore || 60) + (appetiteHasOpenReserveConcern ? -8 : 6))
    ),
    fit: appetiteHasOpenReserveConcern
      ? "Conditional market category"
      : "Strong market category",
    reason: appetiteHasOpenReserveConcern
      ? "Auto liability is present with open reserve pressure. Underwriters will need reserve notes, claim status, driver controls, and corrective actions."
      : "Auto liability claims are present, but current visible reserve pressure appears manageable.",
  });
}

if (appetiteHasGL) {
  lineBasedMarketCategories.push({
    market_category: appetiteHasLargeLoss
      ? "Regional casualty selective market"
      : "Regional general liability market",
    match_score: Math.max(
      35,
      Math.min(90, (localCarrierAppetiteScore || 60) + (appetiteHasLargeLoss ? -5 : 4))
    ),
    fit: appetiteHasLargeLoss
      ? "Moderate market category with narrative"
      : "Moderate market category",
    reason: appetiteHasLargeLoss
      ? "General liability or casualty severity may require a detailed loss narrative before standard-market placement."
      : "General liability exposure appears marketable through regional casualty channels based on visible claims.",
  });
}

if (appetiteHasWC) {
  lineBasedMarketCategories.push({
    market_category:
      appetiteOpenClaimsCount > 0
        ? "Workers comp loss-sensitive market"
        : "Workers comp standard market",
    match_score: Math.max(
      35,
      Math.min(88, (localCarrierAppetiteScore || 60) - (appetiteOpenClaimsCount > 0 ? 6 : 0))
    ),
    fit: appetiteOpenClaimsCount > 0
      ? "Conditional market category"
      : "Standard market category",
    reason: appetiteOpenClaimsCount > 0
      ? "Open claim activity may require loss-sensitive underwriting review."
      : "Workers comp exposure can be reviewed in standard channels if payroll/exposure data supports it.",
  });
}

if (appetiteHasCargo) {
  lineBasedMarketCategories.push({
    market_category: "Motor truck cargo market",
    match_score: Math.max(40, Math.min(90, (localCarrierAppetiteScore || 60) + 3)),
    fit: "Line-specific market category",
    reason: "Cargo exposure should be reviewed separately using cargo losses, limits, radius, commodities, and theft controls.",
  });
}

if (lineBasedMarketCategories.length === 0) {
  lineBasedMarketCategories.push({
    market_category: "Needs coverage classification",
    match_score: localCarrierAppetiteScore || 0,
    fit: "Not enough line-of-business data",
    reason: "LossQ needs validated policy line or coverage data before recommending a market category.",
  });
}

const sortedMarketCategories = lineBasedMarketCategories.sort(
  (a, b) => Number(b.match_score || 0) - Number(a.match_score || 0)
);

const effectiveCarrierMatch =
  validatedClaimsAvailable
    ? {
        ...(carrierMatch || {}),
        recommended_carrier:
          realCarrierDatabaseAvailable && !isInsufficientBackendMessage(carrierMatch?.recommended_carrier)
            ? carrierMatch.recommended_carrier
            : "No named carrier selected - ” market category only",
        recommended_market_category:
          sortedMarketCategories[0]?.market_category || "Needs coverage classification",
        recommended_score:
          carrierMatch?.recommended_score ??
          sortedMarketCategories[0]?.match_score ??
          Math.max(45, Math.min(90, localCarrierAppetiteScore || 60)),
        top_carriers:
          realCarrierDatabaseAvailable && backendTopCarriersAreUsable
            ? carrierMatch.top_carriers
            : [],
        market_categories: sortedMarketCategories,
        carrier_match_summary:
          realCarrierDatabaseAvailable && !isInsufficientBackendMessage(carrierMatch?.carrier_match_summary)
            ? carrierMatch.carrier_match_summary
            : `LossQ did not use a real carrier database for this result. This is a claims-derived market category recommendation based on ${intelligenceClaims.length} validated claim row(s), $${Number(localClaimTotal || 0).toLocaleString()} total incurred, ${localOpenClaimCount} open claim(s), ${localLargeLossCount} large loss claim(s), and ${localLitigationCount} litigation/attorney indicator(s).`,
        claims_used: intelligenceClaims.length,
        policy_numbers_used:
          activePolicyNumbers.length > 0 ? activePolicyNumbers : Array.from(currentUploadPolicySet),
        data_source: backendSaysInsufficient
          ? "local_visible_claims_fallback"
          : "local_visible_claims",
        result_type: realCarrierDatabaseAvailable
          ? "named_carrier_match"
          : "market_category_only",
      }
    : carrierMatch;


const effectiveSubmissionReadiness =
  validatedClaimsAvailable
    ? {
        ...(submissionReadiness || {}),
        submission_readiness_score: backendSaysInsufficient
          ? localSubmissionReadinessScore
          : submissionReadiness?.submission_readiness_score ?? localSubmissionReadinessScore,
        submission_readiness_level: backendSaysInsufficient
          ? localSubmissionReadinessScore && localSubmissionReadinessScore >= 85
            ? "Strong"
            : "Needs Review"
          : submissionReadiness?.submission_readiness_level ||
            (localSubmissionReadinessScore && localSubmissionReadinessScore >= 85 ? "Strong" : "Needs Review"),
        carrier_confidence: backendSaysInsufficient
          ? localOpenClaimCount > 0
            ? "Moderate"
            : "Good"
          : submissionReadiness?.carrier_confidence || (localOpenClaimCount > 0 ? "Moderate" : "Good"),
        submission_quality: backendSaysInsufficient
          ? "Claims loaded from the selected account; narrative review required."
          : submissionReadiness?.submission_quality || "Claims loaded; narrative review required.",
        missing_items: backendSaysInsufficient
          ? localOpenClaimCount > 0
            ? ["Open claim status updates", "Corrective action summary", "Carrier-ready loss narrative"]
            : ["Carrier-ready loss narrative"]
          : submissionReadiness?.missing_items ||
            (localOpenClaimCount > 0 ? ["Open claim status updates", "Corrective action summary"] : ["Carrier-ready loss narrative"]),
        required_documents: backendSaysInsufficient
          ? ["Validated loss runs", "Parsed claim rows", "Claim narrative", "Operations overview"]
          : submissionReadiness?.required_documents || ["Loss runs", "Claim narrative", "Operations overview"],
        recommended_actions: backendSaysInsufficient
          ? ["Review extracted claim rows", "Confirm claim amounts", "Explain open claims", "Add safety/controls narrative"]
          : submissionReadiness?.recommended_actions || ["Confirm claim amounts", "Explain open claims", "Add safety/controls narrative"],
        readiness_summary: backendSaysInsufficient
          ? `Submission has ${visibleClaims.length} loaded claim(s) with $${Number(localClaimTotal || 0).toLocaleString()} total incurred. Backend readiness was insufficient, so LossQ is using the visible claim rows until backend intelligence catches up.`
          : submissionReadiness?.readiness_summary ||
            `Submission has ${visibleClaims.length} loaded claim(s). Add narrative context before carrier release.`,
      }
    : submissionReadiness;

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

const flaggedClaims = hasActiveAccount
  ? visibleClaims.filter((c: any) => c.flag).length
  : Number(backendMetrics?.flagged_claims ?? 0);

const totalClaimsDisplay = hasActiveAccount ? totalClaims : "-";
const openClaimsDisplay = hasActiveAccount ? openClaims : "-";
const totalIncurredDisplay = hasActiveAccount
  ? `$${Number(totalIncurred || 0).toLocaleString()}`
  : "-";
const flaggedClaimsDisplay = hasActiveAccount ? flaggedClaims : "-";

const totalReserve = hasActiveAccount
  ? visibleClaims.reduce(
      (sum: number, c: any) =>
        sum + toMoneyNumber(c?.reserve_amount ?? c?.reserve ?? c?.outstanding_reserve),
      0
    )
  : Number(backendMetrics?.total_reserve ?? timeline?.total_reserve ?? 0);

const closedClaims = hasActiveAccount
  ? visibleClaims.filter((c: any) => String(c.status || "").toLowerCase() === "closed").length
  : Number(backendMetrics?.closed_claims ?? Math.max(totalClaims - openClaims, 0));

const litigationClaims = hasActiveAccount
  ? visibleClaims.filter((c: any) => {
      const text = `${c?.litigation || ""} ${c?.claim_status || ""} ${c?.description || ""}`.toLowerCase();
      return text.includes("litigation") || text.includes("litigated") || text.includes("attorney");
    }).length
  : Number(backendMetrics?.litigation_claims ?? 0);

function chartHasData(rows: any[]) {
  return Array.isArray(rows) && rows.some((item) => Number(item?.value || 0) > 0);
}

function buildVisibleClaimYearlyData() {
  const grouped: Record<string, number> = {};

  visibleClaims.forEach((claim: any) => {
    const rawDate = claim?.loss_date || claim?.date_of_loss || claim?.claim_date || "Unknown";
    const yearMatch = String(rawDate).match(/(20\d{2}|19\d{2})/);
    const year = yearMatch?.[1] || "Unknown";
    grouped[year] = (grouped[year] || 0) + getClaimIncurred(claim);
  });

  return objectToChartData(grouped);
}

function buildVisibleClaimLineData() {
  const grouped: Record<string, number> = {};

  visibleClaims.forEach((claim: any) => {
    const line =
      claim?.line_of_business ||
      claim?.coverage ||
      claim?.policy_type ||
      claim?.lob ||
      "Unknown";

    grouped[String(line)] = (grouped[String(line)] || 0) + getClaimIncurred(claim);
  });

  return objectToChartData(grouped);
}

function buildPolicyScheduleLineData() {
  const grouped: Record<string, number> = {};

  policySchedule.forEach((policy: any) => {
    const line =
      policy?.policy_type ||
      policy?.line_coverage ||
      policy?.line_of_business ||
      policy?.coverage ||
      "Policy";

    const policyNumber = normalizePolicyNumber(policy?.policy_number);
    const scheduledIncurred = Number(
      scheduleClaimStats[policyNumber]?.totalIncurred ?? policy?.total_incurred ?? 0
    );

    if (scheduledIncurred > 0) {
      grouped[String(line)] = (grouped[String(line)] || 0) + scheduledIncurred;
    }
  });

  return objectToChartData(grouped);
}

const chartSourceReady = hasActiveAccount && (visibleClaims.length > 0 || claims.length > 0);
const chartTimeline = chartSourceReady ? timeline : {};
const chartBackendMetrics = chartSourceReady ? backendMetrics : {};

const timelineLossTrendData = objectToChartData(chartTimeline?.incurred_by_year || {});
const backendLossTrendData = objectToChartData(chartBackendMetrics?.yearly_incurred || {});
const visibleLossTrendData = buildVisibleClaimYearlyData();
const lossTrendData = chartSourceReady && chartHasData(timelineLossTrendData)
  ? timelineLossTrendData
  : chartSourceReady && chartHasData(backendLossTrendData)
  ? backendLossTrendData
  : chartSourceReady && chartHasData(visibleLossTrendData)
  ? visibleLossTrendData
  : chartSourceReady && totalIncurred > 0
  ? [{ name: "Account Total", value: totalIncurred }]
  : [];

const timelineAgingData = objectToChartData(chartTimeline?.open_claim_aging || {});
const agingData = chartSourceReady && chartHasData(timelineAgingData)
  ? timelineAgingData
  : chartSourceReady && totalClaims > 0
  ? [
      { name: "Open", value: openClaims },
      { name: "Closed", value: closedClaims },
    ]
  : [];

const timelineSeverityData = objectToChartData(chartTimeline?.severity_heatmap || {});
const severityData = chartSourceReady && chartHasData(timelineSeverityData)
  ? timelineSeverityData
  : chartSourceReady && totalClaims > 0
  ? [
      { name: "Standard Claims", value: Math.max(totalClaims - litigationClaims - flaggedClaims, 0) },
      { name: "Flagged", value: flaggedClaims },
      { name: "Litigation", value: litigationClaims },
      { name: "Open", value: openClaims },
    ].filter((item) => Number(item.value || 0) > 0)
  : [];

const timelineLineData = objectToChartData(chartTimeline?.incurred_by_line || {});
const visibleLineData = buildVisibleClaimLineData();
const policyLineData = buildPolicyScheduleLineData();
const lineData = chartSourceReady && chartHasData(timelineLineData)
  ? timelineLineData
  : chartSourceReady && chartHasData(visibleLineData)
  ? visibleLineData
  : chartSourceReady && chartHasData(policyLineData)
  ? policyLineData
  : chartSourceReady && totalIncurred > 0
  ? [{ name: "Account Total", value: totalIncurred }]
  : [];

const reservePressureDisplay =
  chartSourceReady
    ? chartTimeline?.reserve_pressure ||
      (totalReserve > totalIncurred && totalReserve > 0
        ? "High"
        : openClaims > 0
        ? "Elevated"
        : "Low")
    : "-";

const trendNoteDisplay =
  timeline?.trend_note ||
  (totalClaims > 0
    ? `LossQ reviewed ${totalClaims} account-specific claim(s), including ${openClaims} open claim(s), ${litigationClaims} litigation claim(s), $${Number(totalIncurred || 0).toLocaleString()} incurred, and $${Number(totalReserve || 0).toLocaleString()} reserved.`
    : "No trend intelligence available yet.");

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

  <ToolButton active={activeTool === "exposure-inputs"} onClick={() => setActiveTool("exposure-inputs")}>
    Exposure Inputs
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
              <MobileToolButton active={activeTool === "exposure-inputs"} onClick={() => setActiveTool("exposure-inputs")}>Exposure Inputs</MobileToolButton>
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
                <MetricCard title="Renewal Score" value={effectiveSummary?.renewal_score ?? "-"} />
              </section>

              <section className="grid grid-cols-1 md:grid-cols-4 gap-5 mb-8">
                <MetricCard title="Risk Level" value={effectiveSummary?.renewal_risk_level || "Not Rated"} />
                <MetricCard title="Renewal Probability" value={effectiveDecision?.renewal_probability != null ? `${effectiveDecision.renewal_probability}%` : "-"} />
                <MetricCard title="Carrier Appetite" value={effectiveCarrierAppetite?.carrier_appetite_score != null ? `${effectiveCarrierAppetite.carrier_appetite_score}/100` : "-"} />
                <MetricCard title="Submission Readiness" value={effectiveSubmissionReadiness?.submission_readiness_score != null ? `${effectiveSubmissionReadiness.submission_readiness_score}/100` : "-"} />
              </section>

              <section className="glass-panel p-6 md:p-8">
                <h2 className="text-2xl md:text-3xl font-bold mb-4">Account Snapshot</h2>

                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                  <ProfileDetail label="Insured" value={displayProfile?.business_name || "-"} />
                  <ProfileDetail
                    label="Writing Carrier"
                    value={displayProfile?.writing_carrier || displayProfile?.carrier_name || "-"}
                  />
                  <ProfileDetail label="Carrier" value={displayProfile?.carrier_name || "-"} />
                  <ProfileDetail
                    label="Account Number"
                    value={displayProfile?.account_number || displayProfile?.customer_number || "-"}
                  />
                  <ProfileDetail label="Producing Agency" value={displayProfile?.agency_name || "-"} />
                  <ProfileDetail label="Account / Policy" value={displayProfile?.policy_number || "-"} />
                  <ProfileDetail label="Effective Date" value={displayProfile?.effective_date || "-"} />
                  <ProfileDetail label="Expiration Date" value={displayProfile?.expiration_date || "-"} />
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
                                  displayProfile?.writing_carrier ||
                                  displayProfile?.carrier_name ||
                                  "-"}
                              </td>
                              <td className="py-3 pr-4">
                                {policy.carrier || displayProfile?.carrier_name || "-"}
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

              {Array.isArray(profile?.policies) && profile.policies.length > 0 && (
                <section className="glass-panel p-6 md:p-8 mt-6">
                  <div className="flex flex-col gap-2 mb-5">
                    <h2 className="text-2xl md:text-3xl font-bold">
                      Policy Lines / Coverage Schedule
                    </h2>
                    <p className="text-sm text-slate-400">
                      Multiple lines of business detected from this uploaded loss run.
                    </p>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                    {profile.policies.map((pol: any, index: number) => {
                      const policyNumber =
                        pol?.policy_number ||
                        pol?.policy_no ||
                        pol?.policy ||
                        pol?.account_number ||
                        "";

                      const lineOfBusiness =
                        pol?.line_of_business ||
                        pol?.lob ||
                        pol?.coverage_line ||
                        pol?.coverage ||
                        pol?.policy_line ||
                        pol?.line ||
                        "Commercial Line";

                      const carrierName =
                        pol?.carrier_name ||
                        pol?.writing_carrier ||
                        profile?.carrier_name ||
                        profile?.writing_carrier ||
                        "Carrier Not Set";

                      const effectiveDate =
                        pol?.effective_date ||
                        pol?.policy_effective_date ||
                        profile?.effective_date ||
                        "Not Set";

                      const expirationDate =
                        pol?.expiration_date ||
                        pol?.policy_expiration_date ||
                        pol?.expiry_date ||
                        profile?.expiration_date ||
                        "Not Set";

                      const policyClaimCount = claims.filter((claim: any) => {
                        const claimPolicy = normalizePolicyNumber(claim?.policy_number);
                        const schedulePolicy = normalizePolicyNumber(policyNumber);
                        const claimLob = String(
                          claim?.line_of_business ||
                          claim?.lob ||
                          claim?.coverage_line ||
                          ""
                        ).toLowerCase();

                        const scheduleLob = String(lineOfBusiness || "").toLowerCase();

                        return (
                          (schedulePolicy && claimPolicy === schedulePolicy) ||
                          (scheduleLob && claimLob && claimLob.includes(scheduleLob))
                        );
                      }).length;

                      return (
                        <div
                          key={`${policyNumber || lineOfBusiness}-${index}`}
                          className="rounded-2xl border border-white/10 bg-white/5 p-5"
                        >
                          <p className="text-xs uppercase tracking-[0.25em] text-blue-300 mb-2">
                            {lineOfBusiness}
                          </p>

                          <div className="space-y-2 text-sm">
                            <div>
                              <p className="text-slate-400">Policy Number</p>
                              <p className="font-semibold text-white">
                                {policyNumber || "Not Set"}
                              </p>
                            </div>

                            <div>
                              <p className="text-slate-400">Carrier</p>
                              <p className="font-semibold text-white">
                                {carrierName}
                              </p>
                            </div>

                            <div className="grid grid-cols-2 gap-3">
                              <div>
                                <p className="text-slate-400">Effective</p>
                                <p className="font-semibold text-white">
                                  {effectiveDate}
                                </p>
                              </div>

                              <div>
                                <p className="text-slate-400">Expiration</p>
                                <p className="font-semibold text-white">
                                  {expirationDate}
                                </p>
                              </div>
                            </div>

                            <div>
                              <p className="text-slate-400">Claims</p>
                              <p className="font-semibold text-white">
                                {policyClaimCount}
                              </p>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </section>
              )}

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
                            {(getAccountDisplayName(item) || "Unnamed Business") +
                              " - ” " +
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
                        onClick={() => deleteProfile(profile)}
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


          {activeTool === "exposure-inputs" && (
            <section className="glass-panel p-6 md:p-8">
              <p className="text-sm uppercase tracking-[0.25em] text-green-300 mb-3">
                Universal Forecast Inputs
              </p>

              <h2 className="text-2xl md:text-3xl font-bold mb-4">
                Universal Premium & Exposure Inputs
              </h2>

              <p className="text-slate-400 mb-8 max-w-4xl">
                Manually enter premium, exposure, limits, class, and underwriting data for any commercial line of business. These inputs improve LossQ's premium forecast confidence across Auto, General Liability, Workers Comp, Property, Cargo, Cyber, EPLI, D&O, E&O, Inland Marine, Umbrella, BOP, and other commercial policies.
              </p>

              <div className="rounded-3xl border border-blue-400/20 bg-blue-500/10 p-5 mb-8">
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                  <ProfileDetail label="Account" value={displayProfile?.business_name || profile?.business_name || "-"} />
                  <ProfileDetail label="Policy / Account" value={displayProfile?.policy_number || profile?.policy_number || displayProfile?.account_number || profile?.account_number || "-"} />
                  <ProfileDetail label="Carrier" value={displayProfile?.carrier_name || profile?.carrier_name || "-"} />
                  <ProfileDetail label="Detected Lines" value={policySchedule.length > 0 ? `${policySchedule.length} line(s)` : "Manual Input"} />
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                <Input label="Current Premium" value={profile?.current_premium || ""} onChange={(v) => setProfile({ ...profile, current_premium: v })} />
                <Input label="Expiring Premium" value={profile?.expiring_premium || ""} onChange={(v) => setProfile({ ...profile, expiring_premium: v })} />
                <Input label="Target Renewal Premium" value={profile?.target_renewal_premium || ""} onChange={(v) => setProfile({ ...profile, target_renewal_premium: v })} />

                <Input label="Primary Line of Business" value={profile?.line_of_business || ""} onChange={(v) => setProfile({ ...profile, line_of_business: v })} />
                <Input label="State" value={profile?.state || ""} onChange={(v) => setProfile({ ...profile, state: v })} />
                <Input label="Class Code(s)" value={profile?.class_code || profile?.class_codes || ""} onChange={(v) => setProfile({ ...profile, class_code: v, class_codes: v })} />

                <Input label="Policy Limits" value={profile?.limits || profile?.coverage_limit || ""} onChange={(v) => setProfile({ ...profile, limits: v, coverage_limit: v })} />
                <Input label="Deductible" value={profile?.deductible || ""} onChange={(v) => setProfile({ ...profile, deductible: v })} />
                <Input label="Retention / SIR" value={profile?.retention || ""} onChange={(v) => setProfile({ ...profile, retention: v })} />

                <Input label="Payroll" value={profile?.payroll || ""} onChange={(v) => setProfile({ ...profile, payroll: v })} />
                <Input label="Revenue / Sales" value={profile?.revenue || profile?.sales || ""} onChange={(v) => setProfile({ ...profile, revenue: v, sales: v })} />
                <Input label="Receipts" value={profile?.receipts || ""} onChange={(v) => setProfile({ ...profile, receipts: v })} />

                <Input label="Employee Count" value={profile?.employee_count || ""} onChange={(v) => setProfile({ ...profile, employee_count: v })} />
                <Input label="Vehicle Count" value={profile?.vehicle_count || ""} onChange={(v) => setProfile({ ...profile, vehicle_count: v })} />
                <Input label="Driver Count" value={profile?.driver_count || ""} onChange={(v) => setProfile({ ...profile, driver_count: v })} />

                <Input label="Property TIV" value={profile?.property_tiv || profile?.tiv || ""} onChange={(v) => setProfile({ ...profile, property_tiv: v, tiv: v })} />
                <Input label="Building Value" value={profile?.building_value || ""} onChange={(v) => setProfile({ ...profile, building_value: v })} />
                <Input label="Contents Value" value={profile?.contents_value || ""} onChange={(v) => setProfile({ ...profile, contents_value: v })} />

                <Input label="Square Footage" value={profile?.square_footage || ""} onChange={(v) => setProfile({ ...profile, square_footage: v })} />
                <Input label="Location Count" value={profile?.location_count || ""} onChange={(v) => setProfile({ ...profile, location_count: v })} />
                <Input label="Unit Count" value={profile?.unit_count || ""} onChange={(v) => setProfile({ ...profile, unit_count: v })} />

                <Input label="Cargo Limit" value={profile?.cargo_limit || ""} onChange={(v) => setProfile({ ...profile, cargo_limit: v })} />
                <Input label="Umbrella / Excess Limit" value={profile?.umbrella_limit || ""} onChange={(v) => setProfile({ ...profile, umbrella_limit: v })} />
                <Input label="Experience Mod" value={profile?.experience_mod || profile?.mod || ""} onChange={(v) => setProfile({ ...profile, experience_mod: v, mod: v })} />

                <Input label="Exposure Change %" value={profile?.exposure_change_percent || ""} onChange={(v) => setProfile({ ...profile, exposure_change_percent: v })} />
                <Input label="Cyber Revenue" value={profile?.cyber_revenue || ""} onChange={(v) => setProfile({ ...profile, cyber_revenue: v })} />
                <Input label="Professional Revenue" value={profile?.professional_revenue || ""} onChange={(v) => setProfile({ ...profile, professional_revenue: v })} />
              </div>

              <div className="mt-6">
                <label className="block text-sm text-blue-200 mb-2">
                  Notes / Underwriter Comments
                </label>
                <textarea
                  value={profile?.underwriter_notes || ""}
                  onChange={(e) => setProfile({ ...profile, underwriter_notes: e.target.value })}
                  className="w-full min-h-[150px] rounded-2xl bg-slate-950/70 border border-white/10 px-4 py-4 text-white outline-none focus:border-blue-400 focus:ring-4 focus:ring-blue-500/20"
                  placeholder="Enter exposure assumptions, underwriting notes, class details, loss control updates, or renewal pricing assumptions..."
                />
              </div>

              <div className="mt-8 flex flex-wrap gap-4">
                <button onClick={saveExposureInputs} className="btn-success">
                  Save Exposure Inputs
                </button>
                <button onClick={saveProfile} className="btn-secondary">
                  Save Full Profile
                </button>
                <button onClick={() => setActiveTool("premium-forecast")} className="btn-purple">
                  Open Premium Forecast
                </button>
              </div>
            </section>
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

                <button onClick={uploadFiles} disabled={isUploading} className="btn-primary" style={{opacity: isUploading ? 0.5 : 1, cursor: isUploading ? 'not-allowed' : 'pointer'}}>{isUploading ? "Uploading..." : "Upload & Analyze"}</button>
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
                    {effectiveSummary?.renewal_score ?? "-"}
                  </div>
                  <div className="text-slate-400 text-sm mt-1">out of 100</div>

                  <div className="mt-4 inline-flex rounded-full border border-blue-400/30 bg-blue-500/10 px-4 py-2 text-sm font-bold text-blue-200">
                    {effectiveSummary?.renewal_risk_level || "Not Rated"}
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-8">
                <ListCard title="Renewal Drivers" items={effectiveSummary?.renewal_drivers || ["No renewal drivers available."]} color="blue" />
                <ListCard title="Carrier Concerns" items={effectiveSummary?.carrier_concerns || ["No carrier concerns available."]} color="red" />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
                <TextCard title="Broker Recommendation" text={effectiveSummary?.broker_recommendation || "Upload claims to generate a broker recommendation."} />
                <TextCard title="Renewal Summary" text={effectiveSummary?.renewal_summary || "No renewal summary available yet."} />
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
                <MetricCard title="Renewal Probability" value={effectiveDecision?.renewal_probability != null ? `${effectiveDecision.renewal_probability}%` : "-"} />
                <MetricCard title="Premium Impact" value={effectiveDecision?.expected_premium_impact || "-"} />
                <MetricCard title="Carrier Appetite" value={effectiveDecision?.carrier_appetite || "-"} />
                <MetricCard title="Marketability Score" value={effectiveDecision?.marketability_score != null ? `${effectiveDecision.marketability_score}/100` : "-"} />
              </div>

              <TextCard title="Submission Readiness" text={effectiveDecision?.submission_readiness || "No submission readiness available yet."} />

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
                <ListCard title="Underwriting Concerns" items={effectiveDecision?.underwriting_concerns || ["No underwriting concerns available."]} color="red" />
                <ListCard title="Best Market Types" items={effectiveDecision?.best_market_types || ["No market recommendation available."]} color="purple" />
              </div>

              <div className="mt-6">
                <TextCard title="Underwriter Decision Summary" text={effectiveDecision?.underwriter_decision_summary || "No decision summary available yet."} />
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
                <MetricCard title="Appetite Score" value={effectiveCarrierAppetite?.carrier_appetite_score != null ? `${effectiveCarrierAppetite.carrier_appetite_score}/100` : "-"} />
                <MetricCard title="Appetite Level" value={effectiveCarrierAppetite?.carrier_appetite_level || "-"} />
                <MetricCard title="Best Market" value={effectiveCarrierAppetite?.best_fit_carriers?.[0]?.carrier_type || "-"} />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <ListCard
                  title="Best Fit Markets"
                  items={
                    effectiveCarrierAppetite?.best_fit_carriers?.length
                      ? effectiveCarrierAppetite.best_fit_carriers.map(
                          (item: any) =>
                            `${item.carrier_type} - ” ${item.match_score}/100 - ” ${item.fit}`
                        )
                      : ["No best fit markets available."]
                  }
                  color="blue"
                />

                <ListCard
                  title="Appetite Reasons"
                  items={effectiveCarrierAppetite?.carrier_match_reasons || ["No carrier appetite reasons available."]}
                  color="purple"
                />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
                <TextCard
                  title="Market Strategy"
                  text={effectiveCarrierAppetite?.market_strategy || "No market strategy available yet."}
                />

                <TextCard
                  title="Placement Summary"
                  text={effectiveCarrierAppetite?.placement_summary || "No placement summary available yet."}
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
                <MetricCard title="Readiness Score" value={effectiveSubmissionReadiness?.submission_readiness_score != null ? `${effectiveSubmissionReadiness.submission_readiness_score}/100` : "-"} />
                <MetricCard title="Readiness Level" value={effectiveSubmissionReadiness?.submission_readiness_level || "-"} />
                <MetricCard title="Carrier Confidence" value={effectiveSubmissionReadiness?.carrier_confidence || "-"} />
                <MetricCard title="Submission Quality" value={effectiveSubmissionReadiness?.submission_quality || "-"} />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <ListCard
                  title="Missing Items"
                  items={effectiveSubmissionReadiness?.missing_items || ["No missing items available."]}
                  color="red"
                />

                <ListCard
                  title="Required Documents"
                  items={effectiveSubmissionReadiness?.required_documents || ["No required documents available."]}
                  color="blue"
                />
              </div>

              <div className="mt-6">
                <ListCard
                  title="Recommended Actions"
                  items={effectiveSubmissionReadiness?.recommended_actions || ["No recommended actions available."]}
                  color="purple"
                />
              </div>

              <div className="mt-6">
                <TextCard
                  title="Readiness Summary"
                  text={effectiveSubmissionReadiness?.readiness_summary || "No readiness summary available yet."}
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
        value={effectiveCarrierMatch?.recommended_carrier || "-"}
      />
      <MetricCard
        title="Match Score"
        value={
          effectiveCarrierMatch?.recommended_score != null
            ? `${effectiveCarrierMatch.recommended_score}/100`
            : "-"
        }
      />
      <MetricCard
        title="Carriers Ranked"
        value={effectiveCarrierMatch?.top_carriers?.length || 0}
      />
    </div>

    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <ListCard
        title="Top Carrier Matches"
        items={
          effectiveCarrierMatch?.top_carriers?.length
            ? effectiveCarrierMatch.top_carriers.map(
                (item: any) =>
                  `${item.carrier || item.carrier_name || 'Carrier'} - ” ${item.match_score ?? item.recommended_score ?? item.score ?? '-'}/100 - ” ${item.fit || item.appetite || 'Market fit'}`
              )
            : ["No carrier matches available yet."]
        }
        color="purple"
      />

      <ListCard
        title="Carrier Match Reasons"
        items={
          effectiveCarrierMatch?.top_carriers?.length
            ? effectiveCarrierMatch.top_carriers.map(
                (item: any) => `${item.carrier || item.carrier_name || 'Carrier'}: ${item.reason || item.match_reason || item.fit || 'Claims data supports underwriting review.'}`
              )
            : ["No carrier match reasons available yet."]
        }
        color="blue"
      />
    </div>

    <div className="mt-6">
      <TextCard
        title="Carrier Match Summary"
        text={
          effectiveCarrierMatch?.carrier_match_summary ||
          "No carrier match summary available yet."
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

    <div className="mb-8 rounded-3xl border border-blue-400/30 bg-blue-500/10 p-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.25em] text-blue-300">
            Premium Accuracy Guardrail
          </p>
          <h3 className="mt-2 text-xl font-bold text-white">
            {premiumAccuracyStatus.level}
          </h3>
          <p className="mt-2 text-sm leading-6 text-slate-300">
            {premiumAccuracyStatus.message}
          </p>
        </div>

        <div className="rounded-2xl border border-white/10 bg-slate-950/70 px-5 py-4 text-center min-w-[170px]">
          <p className="text-xs uppercase tracking-[0.2em] text-slate-400">
            Pricing Confidence
          </p>
          <p className="mt-2 text-2xl font-black text-blue-200">
            {premiumAccuracyStatus.confidence}
          </p>
        </div>
      </div>
    </div>

    <div className="grid grid-cols-1 md:grid-cols-4 gap-5 mb-8">
      <MetricCard
        title="Current Premium"
        value={`$${Number(
          effectivePremiumForecast?.current_premium || 0
        ).toLocaleString()}`}
      />

      <MetricCard
        title="Expected Renewal"
        value={`$${Number(
          effectivePremiumForecast?.expected_renewal_premium || 0
        ).toLocaleString()}`}
      />

      <MetricCard
        title="Expected Increase"
        value={`${effectivePremiumForecast?.expected_increase_percent || 0}%`}
      />

      <MetricCard
        title="Confidence"
        value={`${effectivePremiumForecast?.confidence_score || 0}%`}
      />
    </div>

    <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-8">
      <MetricCard
        title="Best Case"
        value={`${effectivePremiumForecast?.best_case_percent || 0}%`}
      />

      <MetricCard
        title="Likely Range"
        value={effectivePremiumForecast?.likely_range_percent || "-"}
      />

      <MetricCard
        title="Worst Case"
        value={`${effectivePremiumForecast?.worst_case_percent || 0}%`}
      />
    </div>

    <ListCard
      title="Forecast Drivers"
      items={
        effectivePremiumForecast?.forecast_drivers || [
          "No forecast drivers available."
        ]
      }
      color="blue"
    />

    <div className="mt-6">
      <TextCard
        title="Forecast Summary"
        text={
          effectivePremiumForecast?.forecast_summary ||
          "No forecast summary available."
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
                " - ” " +
                (item.carrier_name || "No Carrier") +
                " - ” " +
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
        <ProfileDetail label="Insured" value={displayProfile?.business_name || "-"} />
        <ProfileDetail label="Carrier" value={displayProfile?.carrier_name || "-"} />
        <ProfileDetail label="Policy" value={displayProfile?.policy_number || "-"} />
      </div>
    </div>

    <div className="grid grid-cols-1 md:grid-cols-4 gap-5 mb-8">
      <MetricCard title="Renewal Score" value={effectiveSummary?.renewal_score ?? "-"} />
      <MetricCard title="Risk Level" value={effectiveSummary?.renewal_risk_level || "Not Rated"} />
      <MetricCard
        title="Premium Forecast"
        value={
          effectivePremiumForecast?.expected_increase_percent != null
            ? `${effectivePremiumForecast.expected_increase_percent}%`
            : "-"
        }
      />
      <MetricCard
        title="Submission Readiness"
        value={
          effectiveSubmissionReadiness?.submission_readiness_score != null
            ? `${effectiveSubmissionReadiness.submission_readiness_score}/100`
            : "-"
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
          effectiveCarrierAppetite?.placement_summary ||
          effectiveCarrierAppetite?.market_strategy ||
          "No carrier appetite summary available yet."
        }
      />

      <TextCard
        title="Premium Forecast"
        text={
          effectivePremiumForecast?.forecast_summary ||
          "No premium forecast summary available yet."
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
                  `${item.claim_number} - ” ${item.explanation} Broker position: ${item.broker_position}`
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
              <p className="text-slate-300 leading-8">{summary?.summary || "No summary available."}</p>
              <p className="text-blue-200 mt-6">{summary?.recommendation || "Upload claims to generate intelligence."}</p>
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
                <MetricCard title="Reserve Pressure" value={reservePressureDisplay} />
                <MetricCard title="Open Claims" value={hasActiveAccount ? openClaims : "-"} />
                <MetricCard title="Total Reserve" value={hasActiveAccount ? `$${Number(totalReserve || 0).toLocaleString()}` : "-"} />
                <MetricCard title="Total Incurred" value={totalIncurredDisplay} />
              </div>

              <div className="rounded-2xl border border-white/10 bg-slate-950/70 p-5 mb-6">
                <h3 className="font-semibold mb-2">Trend Intelligence</h3>
                <p className="text-slate-300">{trendNoteDisplay}</p>
              </div>

              {policySchedule.length > 0 && (
                <div className="rounded-2xl border border-white/10 bg-slate-950/70 p-5 mb-6 overflow-x-auto">
                  <h3 className="font-semibold mb-3">Policies Feeding This Analysis</h3>
                  <table className="w-full min-w-[760px] text-sm">
                    <thead>
                      <tr className="border-b border-white/10 text-left text-slate-300">
                        <th className="py-3 pr-4">Line / Coverage</th>
                        <th className="py-3 pr-4">Policy Number</th>
                        <th className="py-3 pr-4">Claims</th>
                        <th className="py-3 pr-4">Total Incurred</th>
                      </tr>
                    </thead>
                    <tbody>
                      {policySchedule.map((policy: any, index: number) => {
                        const policyNumber = normalizePolicyNumber(policy?.policy_number);
                        const stats = scheduleClaimStats[policyNumber];
                        return (
                          <tr key={policy?.policy_number || index} className="border-b border-white/10">
                            <td className="py-3 pr-4 text-white">
                              {policy?.policy_type || policy?.line_coverage || policy?.line_of_business || policy?.coverage || "Policy"}
                            </td>
                            <td className="py-3 pr-4 font-semibold text-blue-200">
                              {policy?.policy_number || "-"}
                            </td>
                            <td className="py-3 pr-4">
                              {stats?.count ?? policy?.claim_count ?? "-"}
                            </td>
                            <td className="py-3 pr-4">
                              ${Number(stats?.totalIncurred ?? policy?.total_incurred ?? 0).toLocaleString()}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}

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
  {visibleClaims.length === 0 && (
    <tr className="border-b border-white/10 text-slate-400">
      <td className="py-6 text-center" colSpan={8}>
        No claims found for the selected account. Upload or select another account to view claim-level detail.
      </td>
    </tr>
  )}

  {groupedVisibleClaims.map((claim: any) => (
    <tr
      key={claim.id || claim.claim_number}
      className="border-b border-white/10 text-slate-300"
    >
      <td className="py-4">
        <button
          type="button"
          onClick={() => openClaimRecord(claim)}
          className="text-left text-blue-300 hover:text-blue-200 underline"
        >
          {claim.claim_number || "Unnamed Claim"}
        </button>
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

{selectedClaimDetail && (
  <div className="mt-6 rounded-2xl border border-blue-400/20 bg-blue-500/10 p-5">
    <div className="flex items-start justify-between gap-4">
      <div>
        <p className="text-xs uppercase tracking-[0.25em] text-blue-200">Claim Detail Preview</p>
        <h3 className="mt-2 text-xl font-bold text-white">{selectedClaimDetail.claim_number || "Unnamed Claim"}</h3>
      </div>
      <button
        type="button"
        onClick={() => setSelectedClaimDetail(null)}
        className="rounded-lg border border-white/10 px-3 py-2 text-sm text-slate-300 hover:bg-white/10"
      >
        Close
      </button>
    </div>

    <div className="mt-4 grid grid-cols-1 md:grid-cols-4 gap-3 text-sm">
      {[
        ["Policy", selectedClaimDetail.policy_number || "-"],
        ["Line", selectedClaimDetail.line_of_business || selectedClaimDetail.claim_type || "-"],
        ["Status", selectedClaimDetail.status || "-"],
        ["Total", `$${Number(getClaimIncurred(selectedClaimDetail)).toLocaleString()}`],
      ].map(([label, value]) => (
        <div key={label} className="rounded-xl border border-white/10 bg-slate-950/70 p-3">
          <p className="text-[10px] uppercase tracking-[0.2em] text-slate-500">{label}</p>
          <p className="mt-1 font-semibold text-white">{value}</p>
        </div>
      ))}
    </div>

    <p className="mt-4 text-slate-300">
      {selectedClaimDetail.description || "No description available."}
    </p>
  </div>
)}
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
                 Account: {getAccountDisplayName(profile) || "No account selected"} | Policy: {displayProfile?.policy_number || "N/A"}
              </p>
            </div>

            <button onClick={() => setCopilotOpen(false)} className="text-slate-400 hover:text-white">
              âœ•
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

























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
          activeProfile = await safeJson(selectedRes);
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
          activeProfile = await safeJson(profileRes);
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

      const claimsUrl = hasPolicy
        ? `${API}/claims/?policy_number=${encodeURIComponent(policyNumber)}`
        : `${API}/claims/`;

      const claimsRes = await fetch(claimsUrl, { headers: authHeaders() });

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
    setTimeline({});

    await loadDashboard(policyNumber);

    setMessage(`Loaded policy ${policyNumber}.`);
  }

  async function deleteProfile(policyNumber: string) {
    const confirmed = confirm(`Delete profile ${policyNumber}?`);
    if (!confirmed) return;

    try {
      const res = await fetch(
        `${API}/account-profile/${encodeURIComponent(policyNumber)}`,
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
        setMessage("Failed to delete profile.");
        return;
      }

      setProfiles((prev) => {
        const next = prev.filter((p) => p.policy_number !== policyNumber);
        setCachedProfiles(next);
        return next;
      });

      if (profile?.policy_number === policyNumber) {
        newBlankProfile();
      }

      setMessage(`Deleted profile ${policyNumber}.`);
    } catch {
      setProfiles((prev) => {
        const next = prev.filter((p) => p.policy_number !== policyNumber);
        setCachedProfiles(next);
        return next;
      });

      if (profile?.policy_number === policyNumber) {
        newBlankProfile();
      }

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
    if (!files || files.length === 0) {
      setMessage("Please select one or more PDF, Excel, or CSV files first.");
      return;
    }

    if (!profile.policy_number || profile.policy_number === "Policy Not Set") {
      setMessage("Select or enter a policy number before uploading.");
      return;
    }

    setMessage("Uploading and analyzing loss runs...");

    const formData = new FormData();
    formData.append("policy_number", profile.policy_number);

    let endpoint = `${API}/upload/loss-run`;

    if (files.length === 1) {
      formData.append("file", files[0]);
    } else {
      endpoint = `${API}/upload/loss-runs`;
      Array.from(files).forEach((file) => formData.append("files", file));
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
      setMessage(`Upload failed: ${JSON.stringify(data)}`);
      return;
    }

    setMessage(`Upload complete. Saved ${data?.saved_claims || 0} claim(s).`);
    await loadDashboard(profile.policy_number);
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

    await downloadPdf(
      `${API}/reports/underwriting-pdf${policy}`,
      "lossq_executive_report.pdf"
    );
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
          data?.claims_used ?? claims.length
        }\n\n${data?.memo || "No memo generated."}`
      );
    } catch {
      setRenewalMemo("Memo failed.");
    } finally {
      setMemoLoading(false);
    }
  }

  async function generateCarrierPacket() {
    await generateRenewalMemo();
    await exportCarrierLossRun();
    setMessage("Carrier packet generated.");
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
          data?.claims_used ?? claims.length
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

  const totalClaims = claims.length;
  const openClaims = claims.filter((c) => c.status === "Open").length;
  const totalIncurred = claims.reduce(
    (sum, c) => sum + Number(c.total_incurred || 0),
    0
  );
  const flaggedClaims = claims.filter((c) => c.flag).length;

  const lossTrendData = objectToChartData(timeline?.incurred_by_year || {});
  const agingData = objectToChartData(timeline?.open_claim_aging || {});
  const severityData = objectToChartData(timeline?.severity_heatmap || {});
  const lineData = objectToChartData(timeline?.incurred_by_line || {});

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
        <aside className="hidden lg:flex w-72 shrink-0 flex-col border-r border-white/10 bg-slate-950/70 backdrop-blur-xl p-5">
          <div className="mb-8">
            <div className="text-2xl font-black">LossQ</div>
            <div className="text-sm text-slate-400 mt-1">AI Underwriting Suite</div>
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
          <ToolButton active={activeTool === "renewal-risk"} onClick={() => setActiveTool("renewal-risk")}>
            Renewal Risk
          </ToolButton>
          <ToolButton active={activeTool === "decision"} onClick={() => setActiveTool("decision")}>
            Underwriter Decision
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

          <div className="mt-auto space-y-3">
            <NavButton href="/">Landing</NavButton>
            <NavButton href="/settings">Settings</NavButton>
            <a href="/carrier-workspace" className="btn-purple block text-center">Carrier Workspace</a>
            <button onClick={logout} className="btn-danger w-full">Logout</button>
          </div>
        </aside>

        <section className="flex-1 px-5 md:px-8 py-8 pb-32 max-w-7xl mx-auto w-full">
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
                <MetricCard title="Total Claims" value={totalClaims} />
                <MetricCard title="Open Claims" value={openClaims} />
                <MetricCard title="Total Incurred" value={`$${Number(totalIncurred).toLocaleString()}`} />
                <MetricCard title="Renewal Score" value={summary?.renewal_score ?? "-"} />
              </section>

              <section className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-8">
                <MetricCard title="Risk Level" value={summary?.renewal_risk_level || "Not Rated"} />
                <MetricCard title="Renewal Probability" value={decision?.renewal_probability !== undefined ? `${decision.renewal_probability}%` : "-"} />
                <MetricCard title="Marketability Score" value={decision?.marketability_score !== undefined ? `${decision.marketability_score}/100` : "-"} />
              </section>

              <section className="glass-panel p-6 md:p-8">
                <h2 className="text-2xl md:text-3xl font-bold mb-4">Account Snapshot</h2>
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                  <ProfileDetail label="Business" value={profile?.business_name || "-"} />
                  <ProfileDetail label="Policy" value={profile?.policy_number || "-"} />
                  <ProfileDetail label="Carrier" value={profile?.carrier_name || "-"} />
                  <ProfileDetail label="Agency" value={profile?.agency_name || "-"} />
                </div>
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
                  <Input label="Business Name" value={profile?.business_name || ""} onChange={(v) => setProfile({ ...profile, business_name: v })} />
                  <Input label="Carrier Name" value={profile?.carrier_name || ""} onChange={(v) => setProfile({ ...profile, carrier_name: v })} />
                  <Input label="Agency Name" value={profile?.agency_name || ""} onChange={(v) => setProfile({ ...profile, agency_name: v })} />
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
                    {summary?.renewal_score ?? "-"}
                  </div>
                  <div className="text-slate-400 text-sm mt-1">out of 100</div>

                  <div className="mt-4 inline-flex rounded-full border border-blue-400/30 bg-blue-500/10 px-4 py-2 text-sm font-bold text-blue-200">
                    {summary?.renewal_risk_level || "Not Rated"}
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-8">
                <ListCard title="Renewal Drivers" items={summary?.renewal_drivers || ["No renewal drivers available."]} color="blue" />
                <ListCard title="Carrier Concerns" items={summary?.carrier_concerns || ["No carrier concerns available."]} color="red" />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
                <TextCard title="Broker Recommendation" text={summary?.broker_recommendation || "Upload claims to generate a broker recommendation."} />
                <TextCard title="Renewal Summary" text={summary?.renewal_summary || "No renewal summary available yet."} />
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
                <MetricCard title="Renewal Probability" value={decision?.renewal_probability !== undefined ? `${decision.renewal_probability}%` : "-"} />
                <MetricCard title="Premium Impact" value={decision?.expected_premium_impact || "-"} />
                <MetricCard title="Carrier Appetite" value={decision?.carrier_appetite || "-"} />
                <MetricCard title="Marketability Score" value={decision?.marketability_score !== undefined ? `${decision.marketability_score}/100` : "-"} />
              </div>

              <TextCard title="Submission Readiness" text={decision?.submission_readiness || "No submission readiness available yet."} />

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
                <ListCard title="Underwriting Concerns" items={decision?.underwriting_concerns || ["No underwriting concerns available."]} color="red" />
                <ListCard title="Best Market Types" items={decision?.best_market_types || ["No market recommendation available."]} color="purple" />
              </div>

              <div className="mt-6">
                <TextCard title="Underwriter Decision Summary" text={decision?.underwriter_decision_summary || "No decision summary available yet."} />
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
                <MetricCard title="Reserve Pressure" value={timeline?.reserve_pressure || "Low"} />
                <MetricCard title="Open Claims" value={timeline?.open_claims || 0} />
                <MetricCard title="Total Reserve" value={`$${Number(timeline?.total_reserve || 0).toLocaleString()}`} />
                <MetricCard title="Total Incurred" value={`$${Number(timeline?.total_incurred || 0).toLocaleString()}`} />
              </div>

              <div className="rounded-2xl border border-white/10 bg-slate-950/70 p-5 mb-6">
                <h3 className="font-semibold mb-2">Trend Intelligence</h3>
                <p className="text-slate-300">{timeline?.trend_note || "No trend intelligence available yet."}</p>
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
                <MetricCard title="Total Claims" value={totalClaims} />
                <MetricCard title="Open Claims" value={openClaims} />
                <MetricCard title="Flagged Claims" value={flaggedClaims} />
                <MetricCard title="Total Incurred" value={`$${Number(totalIncurred).toLocaleString()}`} />
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
                    {claims.length === 0 ? (
                      <tr>
                        <td colSpan={8} className="py-6 text-slate-400">
                          No claims found for this policy.
                        </td>
                      </tr>
                    ) : (
                      [...claims]
                        .sort((a, b) => {
                          const statusOrder: Record<string, number> = {
                            Open: 0,
                            Pending: 1,
                            Reopened: 2,
                            Closed: 3,
                          };

                          const aStatus = statusOrder[a.status] ?? 9;
                          const bStatus = statusOrder[b.status] ?? 9;

                          if (aStatus !== bStatus) return aStatus - bStatus;

                          return Number(b.total_incurred || 0) - Number(a.total_incurred || 0);
                        })
                        .map((claim) => (
                          <tr key={claim.id || claim.claim_number} className="border-b border-white/10 text-slate-300">
                            <td className="py-4">
                              {claim.id ? (
                                <a href={`/claims/${claim.id}`} className="text-blue-300 hover:text-blue-200 underline">
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
                            <td>${Number(claim.total_incurred || 0).toLocaleString()}</td>
                            <td>{claim.policy_number || "-"}</td>
                            <td>
                              {claim.flag ? (
                                <span className="text-red-300">{claim.flag}</span>
                              ) : (
                                <span className="text-slate-500">None</span>
                              )}
                            </td>
                          </tr>
                        ))
                    )}
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
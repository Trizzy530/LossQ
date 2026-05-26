"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
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

export default function DashboardPage() {
  const router = useRouter();
  

  const [ready, setReady] = useState(false);
  const [claims, setClaims] = useState<any[]>([]);
  const [summary, setSummary] = useState<any>({});
  const [timeline, setTimeline] = useState<any>({});
  const [profile, setProfile] = useState<any>({});
  const [profiles, setProfiles] = useState<any[]>([]);
  const [files, setFiles] = useState<FileList | null>(null);
  const [message, setMessage] = useState("");

  const [copilotOpen, setCopilotOpen] = useState(false);
  const [copilotQuestion, setCopilotQuestion] = useState("");
  const [copilotAnswer, setCopilotAnswer] = useState("");
  const [copilotLoading, setCopilotLoading] = useState(false);

  const [renewalMemo, setRenewalMemo] = useState("");
  const [memoLoading, setMemoLoading] = useState(false);

  const [welcome, setWelcome] = useState(false);

  useEffect(() => {
    const token = getToken();

    if (!token) {
      router.replace("/login");
      return;
    }

    setWelcome(window.location.search.includes("welcome=1"));
    setReady(true);
    loadDashboard();
  }, []);

  function getToken() {
    if (typeof window === "undefined") return null;
    return localStorage.getItem("lossq_token");
  }

  function authHeaders(): Record<string, string> {
  const token = getToken();

  if (!token) {
    return {};
  }

  return {
    Authorization: `Bearer ${token}`,
  };
}

  function logout() {
    localStorage.removeItem("lossq_token");
    localStorage.removeItem("lossq_user");
    router.replace("/login");
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
    setTimeline({});
    setRenewalMemo("");
    setCopilotAnswer("");
    setMessage("New blank account profile started.");
  }

  async function loadDashboard(policyNumberOverride?: string) {
    if (!getToken()) {
      router.replace("/login");
      return;
    }

    try {
      const profilesRes = await fetch(`${API}/account-profile/all`, {
        headers: authHeaders(),
      });

      if (profilesRes.ok) {
        const profilesData = await safeJson(profilesRes);
        setProfiles(Array.isArray(profilesData) ? profilesData : []);
      }

      let activeProfile = profile;

      if (policyNumberOverride) {
        const selectedRes = await fetch(
          `${API}/account-profile/policy/${encodeURIComponent(policyNumberOverride)}`,
          { headers: authHeaders() }
        );

        if (selectedRes.ok) {
          activeProfile = await safeJson(selectedRes);
          setProfile(activeProfile || {});
        }
      } else {
        const profileRes = await fetch(`${API}/account-profile/`, {
          headers: authHeaders(),
        });

        if (profileRes.ok) {
          activeProfile = await safeJson(profileRes);
          setProfile(activeProfile || {});
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

      if (summaryRes.ok) {
        setSummary((await safeJson(summaryRes)) || {});
      } else {
        setSummary({});
      }

      const timelineUrl = hasPolicy
        ? `${API}/timeline/analytics?policy_number=${encodeURIComponent(policyNumber)}`
        : `${API}/timeline/analytics`;

      const timelineRes = await fetch(timelineUrl, { headers: authHeaders() });

      if (timelineRes.ok) {
        setTimeline((await safeJson(timelineRes)) || {});
      } else {
        setTimeline({});
      }
    } catch {
      setMessage("Dashboard could not load. Confirm backend is running.");
      setClaims([]);
      setSummary({});
      setTimeline({});
    }
  }

  async function selectAccount(policyNumber: string) {
    if (!policyNumber) return;
    setMessage(`Loading policy ${policyNumber}...`);
    setCopilotAnswer("");
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

      if (!res.ok) {
        setMessage("Failed to delete profile.");
        return;
      }

      setProfiles((prev) => prev.filter((p) => p.policy_number !== policyNumber));

      if (profile?.policy_number === policyNumber) {
        newBlankProfile();
      }

      setMessage(`Deleted profile ${policyNumber}.`);
    } catch {
      setMessage("Delete failed.");
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

    const res = await fetch(`${API}/account-profile/`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(),
      },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      setMessage("Could not save account profile.");
      return;
    }

    setMessage("Account profile saved.");
    await loadDashboard(payload.policy_number);
  }

  async function lookupPolicy() {
    if (!profile.policy_number) {
      setMessage("Enter a policy number first.");
      return;
    }

    const res = await fetch(
      `${API}/account-profile/policy/${encodeURIComponent(profile.policy_number)}`,
      { headers: authHeaders() }
    );

    if (!res.ok) {
      setMessage("No account found for that policy number.");
      return;
    }

    const data = await safeJson(res);
    setProfile(data || {});
    setCopilotAnswer("");
    await loadDashboard(data?.policy_number);
    setMessage("Account profile loaded.");
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

    if (!res.ok) {
      setMessage(`Upload failed: ${JSON.stringify(data)}`);
      return;
    }

    setMessage(`Upload complete. Saved ${data?.saved_claims || 0} claim(s).`);
    await loadDashboard(profile.policy_number);
  }

  async function downloadPdf(url: string, filename: string) {
    const res = await fetch(url, { headers: authHeaders() });

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

      if (!res.ok) {
        setRenewalMemo(JSON.stringify(data));
        return;
      }

      setRenewalMemo(
        `Policy analyzed: ${data?.policy_number || profile.policy_number}\nClaims used: ${data?.claims_used ?? claims.length}\n\n${data?.memo || "No memo generated."}`
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
      setCopilotAnswer("Select a policy/account first so Copilot analyzes the correct claims.");
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

      if (!res.ok) {
        setCopilotAnswer(JSON.stringify(data));
        return;
      }

      setCopilotAnswer(
        `Policy analyzed: ${data?.policy_number || profile.policy_number}\nClaims used: ${data?.claims_used ?? claims.length}\n\n${data?.answer || "No answer returned."}`
      );
      setCopilotQuestion(question);
    } catch {
      setCopilotAnswer("Copilot failed.");
    } finally {
      setCopilotLoading(false);
    }
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

  if (!ready) {
    return (
      <main className="min-h-screen bg-slate-950 text-white flex items-center justify-center">
        Loading dashboard...
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-950 text-white p-10">
      <div className="max-w-7xl mx-auto pb-32">
        <header className="flex justify-between items-start mb-10">
          <div>
            <h1 className="text-5xl font-bold">LossQ Dashboard</h1>
            <p className="text-slate-400 mt-2">
              AI underwriting operating system for commercial loss runs
            </p>
          </div>

          <div className="flex gap-4">
            <a href="/" className="bg-slate-800 hover:bg-slate-700 px-5 py-3 rounded-lg">
              Landing
            </a>
            <button onClick={() => setCopilotOpen(true)} className="bg-blue-600 hover:bg-blue-700 px-5 py-3 rounded-lg">
              Open Copilot
            </button>
            <button onClick={logout} className="bg-red-600 hover:bg-red-700 px-5 py-3 rounded-lg">
              Logout
            </button>
          </div>
        </header>

        {welcome && (
          <div className="bg-emerald-600/20 border border-emerald-500 rounded-xl p-4 mb-6 text-emerald-200">
            Welcome to LossQ. Your account was created successfully.
          </div>
        )}

        {message && (
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 mb-6 text-slate-300">
            {message}
          </div>
        )}

      </div>
    </main>
  );
}

 
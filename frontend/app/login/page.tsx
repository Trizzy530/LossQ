"use client";

import { useEffect, useState } from "react";
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

const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

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

  useEffect(() => {
    loadDashboard();
  }, []);

  function getToken() {
    return localStorage.getItem("lossq_token");
  }

  function authHeaders() {
    return { Authorization: `Bearer ${getToken()}` };
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
      window.location.href = "/login";
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

  function logout() {
    localStorage.removeItem("lossq_token");
    localStorage.removeItem("lossq_user");
    window.location.href = "/login";
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
            <a href="/landing" className="bg-slate-800 hover:bg-slate-700 px-5 py-3 rounded-lg">
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

        {message && (
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 mb-6 text-slate-300">
            {message}
          </div>
        )}

        <section className="bg-slate-900 border border-slate-800 rounded-xl p-6 mb-10">
          <h2 className="text-3xl font-semibold mb-4">Account Workspace</h2>

          {profiles.length === 0 ? (
            <p className="text-slate-400">No saved accounts yet. Save a profile below.</p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {profiles.map((item) => (
                <div
                  key={item.id}
                  className={`rounded-xl border p-4 ${
                    profile?.policy_number === item.policy_number
                      ? "border-blue-500 bg-blue-500/10"
                      : "border-slate-800 bg-slate-950"
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => selectAccount(item.policy_number)}
                    className="w-full text-left"
                  >
                    <p className="font-bold">{item.business_name || "-"}</p>
                    <p className="text-slate-400 text-sm">{item.carrier_name || "-"}</p>
                    <p className="text-blue-400 text-sm mt-2">{item.policy_number || "-"}</p>
                  </button>

                  <button
                    type="button"
                    onClick={() => deleteProfile(item.policy_number)}
                    className="mt-4 w-full bg-red-600 hover:bg-red-700 px-4 py-2 rounded-lg text-sm font-semibold"
                  >
                    Delete Profile
                  </button>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="bg-slate-900 border border-slate-800 rounded-xl p-6 mb-10">
          <div className="flex justify-between items-center mb-6">
            <h2 className="text-3xl font-semibold">Carrier Account Profile</h2>

            <div className="flex gap-3">
              <button onClick={newBlankProfile} className="bg-slate-700 hover:bg-slate-600 px-5 py-3 rounded-lg font-semibold">
                New Blank Profile
              </button>
              <button onClick={saveProfile} className="bg-emerald-600 hover:bg-emerald-700 px-5 py-3 rounded-lg font-semibold">
                Save Profile
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            <Input label="Business Name" value={profile?.business_name || ""} onChange={(v) => setProfile({ ...profile, business_name: v })} />
            <Input label="Carrier Name" value={profile?.carrier_name || ""} onChange={(v) => setProfile({ ...profile, carrier_name: v })} />
            <Input label="Agency Name" value={profile?.agency_name || ""} onChange={(v) => setProfile({ ...profile, agency_name: v })} />

            <div>
              <label className="block text-sm text-slate-400 mb-2">Policy Number</label>
              <div className="flex gap-2">
                <input
                  value={profile?.policy_number || ""}
                  onChange={(e) => setProfile({ ...profile, policy_number: e.target.value })}
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg px-4 py-3"
                />
                <button onClick={lookupPolicy} className="bg-blue-600 hover:bg-blue-700 px-4 py-3 rounded-lg font-semibold">
                  Lookup
                </button>
              </div>
            </div>

            <Input label="Effective Date" value={profile?.effective_date || ""} onChange={(v) => setProfile({ ...profile, effective_date: v })} />
            <Input label="Expiration Date" value={profile?.expiration_date || ""} onChange={(v) => setProfile({ ...profile, expiration_date: v })} />
            <Input label="Evaluation Date" value={profile?.evaluation_date || ""} onChange={(v) => setProfile({ ...profile, evaluation_date: v })} />
          </div>
        </section>

        <section className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-10">
          <MetricCard title="Business" value={profile?.business_name || "-"} />
          <MetricCard title="Policy Number" value={profile?.policy_number || "-"} />
          <MetricCard title="Carrier" value={profile?.carrier_name || "-"} />
          <MetricCard title="Total Claims" value={totalClaims} />
        </section>

        <section className="bg-slate-900 border border-slate-800 rounded-xl p-6 mb-10">
          <h2 className="text-3xl font-semibold mb-4">Upload & Report Center</h2>

          <div className="flex flex-wrap gap-4 items-center">
            <input
              type="file"
              multiple
              accept=".pdf,.xlsx,.csv"
              onChange={(e) => setFiles(e.target.files)}
              className="text-sm text-slate-300 file:mr-4 file:rounded-lg file:border-0 file:bg-blue-600 file:px-4 file:py-2 file:text-white"
            />

            <button onClick={uploadFiles} className="bg-blue-600 hover:bg-blue-700 px-5 py-3 rounded-lg font-semibold">
              Upload & Analyze
            </button>
            <button onClick={exportCarrierLossRun} className="bg-emerald-600 hover:bg-emerald-700 px-5 py-3 rounded-lg font-semibold">
              Export Carrier Loss Run
            </button>
            <button onClick={exportExecutiveReport} className="bg-green-700 hover:bg-green-800 px-5 py-3 rounded-lg font-semibold">
              Export Executive Report
            </button>
            <button onClick={generateCarrierPacket} className="bg-purple-600 hover:bg-purple-700 px-5 py-3 rounded-lg font-semibold">
              Generate Carrier Packet
            </button>
          </div>
        </section>

        <section className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-10">
          <MetricCard title="Open Claims" value={openClaims} />
          <MetricCard title="Total Incurred" value={`$${Number(totalIncurred).toLocaleString()}`} />
          <MetricCard title="Flagged Issues" value={flaggedClaims} />
          <MetricCard title="Renewal Risk" value={summary?.renewal_risk || "GREEN"} />
        </section>

        <section className="bg-slate-900 border border-slate-800 rounded-xl p-6 mb-10">
          <h2 className="text-3xl font-semibold mb-5">AI Underwriting Summary</h2>
          <p className="text-slate-300 leading-8">{summary?.summary || "No summary available."}</p>
          <p className="text-slate-400 mt-6">{summary?.recommendation || "Upload claims to generate intelligence."}</p>
        </section>

        <details className="bg-slate-900 border border-slate-800 rounded-xl p-6 mb-10">
          <summary className="cursor-pointer text-2xl font-semibold">AI Renewal Memo</summary>

          <div className="mt-6">
            <div className="flex gap-4 mb-5">
              <button onClick={generateRenewalMemo} disabled={memoLoading} className="bg-purple-600 hover:bg-purple-700 px-5 py-3 rounded-lg font-semibold disabled:opacity-50">
                {memoLoading ? "Generating..." : "Generate Renewal Memo"}
              </button>

              {renewalMemo && (
                <button onClick={copyRenewalMemo} className="bg-slate-800 hover:bg-slate-700 px-5 py-3 rounded-lg font-semibold">
                  Copy Memo
                </button>
              )}
            </div>

            <div className="bg-slate-800 rounded-xl p-5 max-h-[420px] overflow-y-auto">
              <pre className="whitespace-pre-wrap text-slate-300 leading-7 text-sm">
                {renewalMemo || "Generate a memo above."}
              </pre>
            </div>
          </div>
        </details>

        <details className="bg-slate-900 border border-slate-800 rounded-xl p-6 mb-10">
          <summary className="cursor-pointer text-3xl font-semibold">
            Interactive Claim Development Charts
          </summary>

          <div className="mt-6">
            <p className="text-slate-400 mb-6">
              Visualize loss trends, claim aging, severity distribution, and line-of-business concentration.
            </p>

            <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
              <MetricCard title="Reserve Pressure" value={timeline?.reserve_pressure || "Low"} />
              <MetricCard title="Open Claims" value={timeline?.open_claims || 0} />
              <MetricCard title="Total Reserve" value={`$${Number(timeline?.total_reserve || 0).toLocaleString()}`} />
              <MetricCard title="Total Incurred" value={`$${Number(timeline?.total_incurred || 0).toLocaleString()}`} />
            </div>

            <div className="bg-slate-800 rounded-xl p-5 mb-6">
              <h3 className="font-semibold mb-2">Trend Intelligence</h3>
              <p className="text-slate-300">
                {timeline?.trend_note || "No trend intelligence available yet."}
              </p>
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
          </div>
        </details>

        <section className="bg-slate-900 border border-slate-800 rounded-xl p-6">
          <h2 className="text-3xl font-semibold mb-6">Claims Analysis</h2>

          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-700 text-left">
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
                  claims.map((claim) => (
                    <tr key={claim.id || claim.claim_number} className="border-b border-slate-800">
                      <td className="py-4">
                        {claim.id ? (
                          <a href={`/claims/${claim.id}`} className="text-blue-400 hover:text-blue-300 underline">
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
                      <td>{claim.flag ? <span className="text-red-400">{claim.flag}</span> : <span className="text-slate-400">None</span>}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <button
        onClick={() => setCopilotOpen(!copilotOpen)}
        className="fixed bottom-6 right-6 z-50 rounded-full bg-blue-600 hover:bg-blue-700 px-6 py-4 font-semibold shadow-2xl"
      >
        {copilotOpen ? "Close Copilot" : "Ask Copilot"}
      </button>

      {copilotOpen && (
        <div className="fixed bottom-24 right-6 z-50 w-[420px] max-w-[calc(100vw-3rem)] bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl overflow-hidden">
          <div className="bg-slate-800 px-5 py-4 flex justify-between">
            <div>
              <h2 className="font-semibold">AI Underwriting Copilot</h2>
              <p className="text-xs text-slate-400">
                Account: {profile?.business_name || "No account selected"} | Policy: {profile?.policy_number || "-"}
              </p>
            </div>

            <button onClick={() => setCopilotOpen(false)} className="text-slate-400 hover:text-white">✕</button>
          </div>

          <div className="p-5 max-h-[520px] overflow-y-auto">
            {[
              "What are the biggest renewal concerns?",
              "Summarize litigation exposure.",
              "What claims should concern carriers?",
              "What should the broker explain before submission?",
            ].map((q) => (
              <button key={q} onClick={() => askCopilot(q)} className="w-full text-left bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg px-3 py-2 text-sm mb-2">
                {q}
              </button>
            ))}

            <div className="flex gap-2 mt-4">
              <input
                value={copilotQuestion}
                onChange={(e) => setCopilotQuestion(e.target.value)}
                placeholder="Ask a question..."
                className="flex-1 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm"
              />

              <button onClick={() => askCopilot()} disabled={copilotLoading} className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg disabled:opacity-50">
                {copilotLoading ? "..." : "Ask"}
              </button>
            </div>

            {copilotAnswer && (
              <div className="bg-slate-800 rounded-xl p-4 mt-4">
                <p className="text-slate-300 whitespace-pre-line text-sm leading-7">
                  {copilotAnswer}
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </main>
  );
}

function MetricCard({ title, value }: { title: string; value: any }) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
      <div className="text-slate-400 mb-3">{title}</div>
      <div className="text-2xl font-bold break-words">{value || "-"}</div>
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
      <label className="block text-sm text-slate-400 mb-2">{label}</label>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full bg-slate-800 border border-slate-700 rounded-lg px-4 py-3"
      />
    </div>
  );
}

function ChartCard({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-slate-800 rounded-xl p-5">
      <h3 className="font-semibold mb-4">{title}</h3>
      {children}
    </div>
  );
}
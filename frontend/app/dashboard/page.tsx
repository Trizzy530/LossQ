"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

type CarrierProfile = {
  id?: string | number;
  business_name: string;
  carrier_name?: string;
  policy_number: string;
  effective_date?: string;
  expiration_date?: string;
  line_of_business?: string;
  premium?: string | number;
  contact_name?: string;
  contact_email?: string;
  notes?: string;
};

type Claim = {
  id?: string | number;
  claim_number?: string;
  claimant?: string;
  date_of_loss?: string;
  status?: string;
  loss_type?: string;
  paid?: number;
  reserve?: number;
  incurred?: number;
};

type DashboardData = {
  claims?: Claim[];
  underwriting_summary?: string;
  total_claims?: number;
  total_paid?: number;
  total_reserve?: number;
  total_incurred?: number;
};

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  "http://localhost:8000";

const emptyProfile: CarrierProfile = {
  business_name: "",
  carrier_name: "",
  policy_number: "",
  effective_date: "",
  expiration_date: "",
  line_of_business: "",
  premium: "",
  contact_name: "",
  contact_email: "",
  notes: "",
};

export default function DashboardPage() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const [token, setToken] = useState<string | null>(null);
  const [sessionChecking, setSessionChecking] = useState(true);
  const [loading, setLoading] = useState(true);
  const [backendError, setBackendError] = useState("");

  const [profiles, setProfiles] = useState<CarrierProfile[]>([]);
  const [selectedPolicyNumber, setSelectedPolicyNumber] = useState("");
  const [profile, setProfile] = useState<CarrierProfile>(emptyProfile);

  const [dashboard, setDashboard] = useState<DashboardData>({});
  const [claims, setClaims] = useState<Claim[]>([]);
  const [aiSummary, setAiSummary] = useState("");
  const [renewalMemo, setRenewalMemo] = useState("");
  const [copilotQuestion, setCopilotQuestion] = useState("");
  const [copilotAnswer, setCopilotAnswer] = useState("");

  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [lookingUp, setLookingUp] = useState(false);
  const [memoLoading, setMemoLoading] = useState(false);
  const [packetLoading, setPacketLoading] = useState(false);
  const [copilotLoading, setCopilotLoading] = useState(false);

  function getAuthHeaders(contentType = true): HeadersInit {
    const headers: HeadersInit = {};
    if (contentType) headers["Content-Type"] = "application/json";
    if (token) headers["Authorization"] = `Bearer ${token}`;
    return headers;
  }

  async function apiFetch(path: string, options: RequestInit = {}) {
    const res = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: {
        ...(options.headers || {}),
      },
    });

    if (res.status === 401 || res.status === 403) {
      logout();
      throw new Error("Session expired. Please log in again.");
    }

    if (!res.ok) {
      const text = await res.text();
      throw new Error(text || `Request failed: ${res.status}`);
    }

    const contentType = res.headers.get("content-type");
    if (contentType?.includes("application/json")) return res.json();
    return res.blob();
  }

  async function loadDashboard(policyNumber?: string) {
    try {
      setBackendError("");
      setLoading(true);

      const suffix = policyNumber
        ? `?policy_number=${encodeURIComponent(policyNumber)}`
        : "";

      const data = await apiFetch(`/dashboard${suffix}`, {
        headers: getAuthHeaders(false),
      });

      setDashboard(data || {});
      setClaims(data?.claims || []);
      setAiSummary(data?.underwriting_summary || data?.summary || "");
    } catch (err: any) {
      setBackendError(err?.message || "Dashboard failed to load.");
    } finally {
      setLoading(false);
    }
  }

  async function loadProfileList() {
    try {
      const data = await apiFetch("/carrier-profiles", {
        headers: getAuthHeaders(false),
      });

      const list = Array.isArray(data) ? data : data?.profiles || [];
      setProfiles(list);

      if (list.length && !selectedPolicyNumber) {
        const first = list[0];
        setSelectedPolicyNumber(first.policy_number);
        setProfile(first);
        await loadDashboard(first.policy_number);
      }
    } catch (err: any) {
      setBackendError(err?.message || "Carrier profiles failed to load.");
    }
  }

  async function selectAccount(policyNumber: string) {
    setSelectedPolicyNumber(policyNumber);

    const found = profiles.find((p) => p.policy_number === policyNumber);
    if (found) setProfile(found);

    await loadDashboard(policyNumber);
  }

  async function deleteProfile() {
    if (!profile.policy_number) return;

    const confirmed = window.confirm(
      `Delete ${profile.business_name || "this profile"}?`
    );
    if (!confirmed) return;

    try {
      await apiFetch(
        `/carrier-profiles/${encodeURIComponent(profile.policy_number)}`,
        {
          method: "DELETE",
          headers: getAuthHeaders(false),
        }
      );

      setProfile(emptyProfile);
      setSelectedPolicyNumber("");
      await loadProfileList();
    } catch (err: any) {
      alert(err?.message || "Profile delete failed.");
    }
  }

  async function saveProfile() {
    try {
      setSaving(true);

      const saved = await apiFetch("/carrier-profiles", {
        method: "POST",
        headers: getAuthHeaders(true),
        body: JSON.stringify(profile),
      });

      const savedProfile = saved?.profile || saved || profile;
      setProfile(savedProfile);
      setSelectedPolicyNumber(savedProfile.policy_number || profile.policy_number);
      await loadProfileList();
    } catch (err: any) {
      alert(err?.message || "Profile save failed.");
    } finally {
      setSaving(false);
    }
  }

  async function lookupPolicy() {
    if (!profile.policy_number) {
      alert("Enter a policy number first.");
      return;
    }

    try {
      setLookingUp(true);

      const data = await apiFetch(
        `/carrier-profiles/lookup/${encodeURIComponent(profile.policy_number)}`,
        {
          headers: getAuthHeaders(false),
        }
      );

      setProfile((prev) => ({
        ...prev,
        ...(data?.profile || data || {}),
      }));
    } catch (err: any) {
      alert(err?.message || "Policy lookup failed.");
    } finally {
      setLookingUp(false);
    }
  }

  async function uploadFiles(files: FileList | null) {
    if (!files?.length) return;

    try {
      setUploading(true);

      const formData = new FormData();
      Array.from(files).forEach((file) => formData.append("files", file));

      if (selectedPolicyNumber) {
        formData.append("policy_number", selectedPolicyNumber);
      }

      const headers: HeadersInit = {};
      if (token) headers["Authorization"] = `Bearer ${token}`;

      await apiFetch("/upload/loss-run", {
        method: "POST",
        headers,
        body: formData,
      });

      await loadProfileList();
      await loadDashboard(selectedPolicyNumber);
    } catch (err: any) {
      alert(err?.message || "Upload failed.");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function downloadBlob(path: string, filename: string) {
    const blob = await apiFetch(path, {
      headers: getAuthHeaders(false),
    });

    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  }

  async function exportCarrierLossRun() {
    if (!selectedPolicyNumber) return alert("Select a carrier profile first.");

    await downloadBlob(
      `/reports/carrier-loss-run?policy_number=${encodeURIComponent(
        selectedPolicyNumber
      )}`,
      `LossQ-carrier-loss-run-${selectedPolicyNumber}.pdf`
    );
  }

  async function exportExecutiveReport() {
    if (!selectedPolicyNumber) return alert("Select a carrier profile first.");

    await downloadBlob(
      `/reports/executive?policy_number=${encodeURIComponent(
        selectedPolicyNumber
      )}`,
      `LossQ-executive-report-${selectedPolicyNumber}.pdf`
    );
  }

  async function generateRenewalMemo() {
    if (!selectedPolicyNumber) return alert("Select a carrier profile first.");

    try {
      setMemoLoading(true);

      const data = await apiFetch("/summary/renewal-memo", {
        method: "POST",
        headers: getAuthHeaders(true),
        body: JSON.stringify({ policy_number: selectedPolicyNumber }),
      });

      setRenewalMemo(data?.memo || data?.renewal_memo || "");
    } catch (err: any) {
      alert(err?.message || "Renewal memo failed.");
    } finally {
      setMemoLoading(false);
    }
  }

  async function generateCarrierPacket() {
    if (!selectedPolicyNumber) return alert("Select a carrier profile first.");

    try {
      setPacketLoading(true);

      await downloadBlob(
        `/carrier-packet?policy_number=${encodeURIComponent(
          selectedPolicyNumber
        )}`,
        `LossQ-carrier-packet-${selectedPolicyNumber}.pdf`
      );
    } catch (err: any) {
      alert(err?.message || "Carrier packet failed.");
    } finally {
      setPacketLoading(false);
    }
  }

  async function copyRenewalMemo() {
    if (!renewalMemo) return;
    await navigator.clipboard.writeText(renewalMemo);
    alert("Renewal memo copied.");
  }

  async function askCopilot() {
    if (!copilotQuestion.trim()) return;

    try {
      setCopilotLoading(true);

      const data = await apiFetch("/copilot/ask", {
        method: "POST",
        headers: getAuthHeaders(true),
        body: JSON.stringify({
          question: copilotQuestion,
          policy_number: selectedPolicyNumber,
        }),
      });

      setCopilotAnswer(data?.answer || data?.response || "");
    } catch (err: any) {
      alert(err?.message || "Copilot failed.");
    } finally {
      setCopilotLoading(false);
    }
  }

  function logout() {
    localStorage.removeItem("lossq_token");
    localStorage.removeItem("lossq_session_started_at");
    sessionStorage.clear();
    router.push("/login");
  }

  function newCompanyProfile() {
    setProfile(emptyProfile);
    setSelectedPolicyNumber("");
  }

  useEffect(() => {
    const storedToken = localStorage.getItem("lossq_token");
    const sessionStarted = localStorage.getItem("lossq_session_started_at");

    if (!storedToken) {
      router.push("/login");
      return;
    }

    if (sessionStarted) {
      const age = Date.now() - Number(sessionStarted);
      const maxAge = 24 * 60 * 60 * 1000;

      if (age > maxAge) {
        logout();
        return;
      }
    } else {
      localStorage.setItem("lossq_session_started_at", String(Date.now()));
    }

    setToken(storedToken);
    setSessionChecking(false);
  }, [router]);

  useEffect(() => {
    if (!token) return;

    Promise.all([loadProfileList(), loadDashboard()]).finally(() =>
      setLoading(false)
    );
  }, [token]);

  const totals = useMemo(() => {
    const totalClaims = claims.length;
    const paid = claims.reduce((sum, c) => sum + Number(c.paid || 0), 0);
    const reserve = claims.reduce((sum, c) => sum + Number(c.reserve || 0), 0);
    const incurred = claims.reduce(
      (sum, c) => sum + Number(c.incurred || c.paid || 0),
      0
    );

    return {
      totalClaims: dashboard.total_claims || totalClaims,
      paid: dashboard.total_paid || paid,
      reserve: dashboard.total_reserve || reserve,
      incurred: dashboard.total_incurred || incurred,
    };
  }, [claims, dashboard]);

  if (sessionChecking) {
    return (
      <main className="min-h-screen bg-[#030712] text-white flex items-center justify-center">
        <div className="rounded-3xl border border-white/10 bg-white/5 p-8 shadow-2xl backdrop-blur-xl">
          <div className="h-10 w-10 animate-spin rounded-full border-2 border-blue-400 border-t-transparent mx-auto mb-4" />
          <p className="text-slate-300">Checking secure session...</p>
        </div>
      </main>
    );
  }

  if (loading) {
    return (
      <main className="min-h-screen bg-[#030712] text-white flex items-center justify-center">
        <div className="rounded-3xl border border-blue-400/20 bg-white/5 p-8 shadow-[0_0_80px_rgba(59,130,246,.25)] backdrop-blur-xl">
          <div className="h-10 w-10 animate-spin rounded-full border-2 border-blue-400 border-t-transparent mx-auto mb-4" />
          <p className="text-slate-300">Loading LossQ dashboard...</p>
        </div>
      </main>
    );
  }

  if (backendError) {
    return (
      <main className="min-h-screen bg-[#030712] text-white flex items-center justify-center p-6">
        <div className="max-w-lg rounded-3xl border border-red-400/20 bg-red-500/10 p-8 backdrop-blur-xl">
          <h1 className="text-2xl font-bold mb-3">Backend connection issue</h1>
          <p className="text-slate-300 mb-6">{backendError}</p>
          <button
            onClick={() => {
              setBackendError("");
              loadProfileList();
              loadDashboard(selectedPolicyNumber);
            }}
            className="rounded-xl bg-blue-500 px-5 py-3 font-semibold hover:bg-blue-400"
          >
            Retry
          </button>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#030712] text-white">
      <div className="fixed inset-0 -z-10 bg-[radial-gradient(circle_at_top_left,rgba(37,99,235,.35),transparent_35%),radial-gradient(circle_at_top_right,rgba(14,165,233,.20),transparent_30%),linear-gradient(180deg,#030712,#020617)]" />

      <header className="sticky top-0 z-30 border-b border-white/10 bg-black/30 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <div>
            <h1 className="text-2xl font-black tracking-tight">
              LossQ Underwriting AI
            </h1>
            <p className="text-sm text-slate-400">
              Claims intelligence, renewal strategy, and carrier-ready loss-run analytics
            </p>
          </div>

          <div className="flex gap-3">
            <button
              onClick={() => router.push("/carrier-workspace")}
              className="rounded-xl border border-blue-400/30 bg-blue-500/10 px-4 py-2 text-sm font-semibold text-blue-200 hover:bg-blue-500/20"
            >
              Carrier Workspace
            </button>
            <button
              onClick={logout}
              className="rounded-xl border border-white/10 px-4 py-2 text-sm font-semibold hover:bg-white/10"
            >
              Logout
            </button>
          </div>
        </div>
      </header>

      <section className="mx-auto max-w-7xl px-6 py-8">
        <div className="mb-8 rounded-[2rem] border border-white/10 bg-white/[0.06] p-8 shadow-[0_0_100px_rgba(37,99,235,.18)] backdrop-blur-xl">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <div className="mb-3 inline-flex rounded-full border border-blue-400/30 bg-blue-500/10 px-4 py-1 text-sm text-blue-200">
                AI-powered underwriting command center
              </div>
              <h2 className="max-w-3xl text-4xl font-black tracking-tight md:text-5xl">
                Turn messy loss runs into clean carrier intelligence.
              </h2>
              <p className="mt-4 max-w-2xl text-slate-300">
                Upload, analyze, summarize, export, and prepare renewal-ready
                carrier packets from one modern dashboard.
              </p>
            </div>

            <div className="grid min-w-[280px] gap-3">
              <button
                onClick={() => fileInputRef.current?.click()}
                className="rounded-2xl bg-blue-500 px-6 py-4 font-bold shadow-[0_0_35px_rgba(59,130,246,.35)] hover:bg-blue-400"
              >
                {uploading ? "Uploading..." : "Upload Loss Runs"}
              </button>

              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept=".pdf,.xlsx,.xls,.csv"
                onChange={(e) => uploadFiles(e.target.files)}
                className="hidden"
              />

              <button
                onClick={generateCarrierPacket}
                className="rounded-2xl border border-white/10 bg-white/10 px-6 py-4 font-bold hover:bg-white/15"
              >
                {packetLoading ? "Generating..." : "Generate Carrier Packet"}
              </button>
            </div>
          </div>
        </div>

        <div className="grid gap-5 md:grid-cols-4">
          <MetricCard label="Total Claims" value={totals.totalClaims} />
          <MetricCard label="Paid Losses" value={money(totals.paid)} />
          <MetricCard label="Reserves" value={money(totals.reserve)} />
          <MetricCard label="Total Incurred" value={money(totals.incurred)} />
        </div>

        <div className="mt-8 grid gap-6 lg:grid-cols-[420px_1fr]">
          <GlassPanel title="Carrier Profile">
            <label className="mb-2 block text-sm text-slate-400">
              Saved Carrier Profiles
            </label>

            <select
              value={selectedPolicyNumber}
              onChange={(e) => selectAccount(e.target.value)}
              className="mb-4 w-full rounded-2xl border border-white/10 bg-slate-950/80 px-4 py-3 text-white outline-none focus:border-blue-400"
            >
              <option value="">Select carrier profile</option>
              {profiles.map((p) => (
                <option key={p.policy_number} value={p.policy_number}>
                  {p.business_name || "Unnamed Business"} — {p.policy_number}
                </option>
              ))}
            </select>

            <div className="mb-5 rounded-2xl border border-blue-400/20 bg-blue-500/10 p-4">
              <p className="text-sm text-slate-400">Selected Profile</p>
              <h3 className="text-xl font-bold">
                {profile.business_name || "New Company Profile"}
              </h3>
              <p className="text-sm text-slate-300">
                {profile.carrier_name || "No carrier entered"} ·{" "}
                {profile.policy_number || "No policy number"}
              </p>
            </div>

            <ProfileInput
              label="Business Name"
              value={profile.business_name}
              onChange={(v) => setProfile({ ...profile, business_name: v })}
            />
            <ProfileInput
              label="Carrier Name"
              value={profile.carrier_name || ""}
              onChange={(v) => setProfile({ ...profile, carrier_name: v })}
            />
            <ProfileInput
              label="Policy Number"
              value={profile.policy_number}
              onChange={(v) => setProfile({ ...profile, policy_number: v })}
            />
            <ProfileInput
              label="Effective Date"
              type="date"
              value={profile.effective_date || ""}
              onChange={(v) => setProfile({ ...profile, effective_date: v })}
            />
            <ProfileInput
              label="Expiration Date"
              type="date"
              value={profile.expiration_date || ""}
              onChange={(v) => setProfile({ ...profile, expiration_date: v })}
            />
            <ProfileInput
              label="Line of Business"
              value={profile.line_of_business || ""}
              onChange={(v) => setProfile({ ...profile, line_of_business: v })}
            />

            <textarea
              value={profile.notes || ""}
              onChange={(e) => setProfile({ ...profile, notes: e.target.value })}
              placeholder="Carrier notes, underwriting details, renewal strategy..."
              className="mt-3 min-h-[110px] w-full rounded-2xl border border-white/10 bg-black/30 px-4 py-3 text-sm outline-none focus:border-blue-400"
            />

            <div className="mt-5 grid grid-cols-2 gap-3">
              <button onClick={newCompanyProfile} className="btn-secondary">
                New Company Profile
              </button>
              <button onClick={saveProfile} className="btn-primary">
                {saving ? "Saving..." : "Save Profile"}
              </button>
              <button onClick={lookupPolicy} className="btn-secondary">
                {lookingUp ? "Looking up..." : "Lookup"}
              </button>
              <button onClick={deleteProfile} className="btn-danger">
                Delete Profile
              </button>
            </div>
          </GlassPanel>

          <div className="grid gap-6">
            <GlassPanel title="AI Underwriting Summary">
              <p className="whitespace-pre-wrap text-slate-300">
                {aiSummary || "Upload loss runs or select a profile to generate underwriting intelligence."}
              </p>
            </GlassPanel>

            <GlassPanel title="Reports & Exports">
              <div className="grid gap-3 md:grid-cols-3">
                <button onClick={exportCarrierLossRun} className="btn-secondary">
                  Export Carrier Loss Run
                </button>
                <button onClick={exportExecutiveReport} className="btn-secondary">
                  Export Executive Report
                </button>
                <button onClick={generateRenewalMemo} className="btn-primary">
                  {memoLoading ? "Generating..." : "Generate Renewal Memo"}
                </button>
              </div>
            </GlassPanel>

            <GlassPanel title="Renewal Memo">
              <div className="mb-4 flex justify-end">
                <button onClick={copyRenewalMemo} className="btn-secondary">
                  Copy Renewal Memo
                </button>
              </div>
              <div className="min-h-[180px] whitespace-pre-wrap rounded-2xl border border-white/10 bg-black/30 p-5 text-slate-300">
                {renewalMemo || "No renewal memo generated yet."}
              </div>
            </GlassPanel>
          </div>
        </div>

        <div className="mt-8 grid gap-6 lg:grid-cols-2">
          <GlassPanel title="Claims Table">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-slate-400">
                  <tr className="border-b border-white/10">
                    <th className="py-3">Claim #</th>
                    <th className="py-3">Date</th>
                    <th className="py-3">Type</th>
                    <th className="py-3">Status</th>
                    <th className="py-3 text-right">Incurred</th>
                  </tr>
                </thead>
                <tbody>
                  {claims.length ? (
                    claims.map((claim, index) => (
                      <tr key={claim.id || index} className="border-b border-white/5">
                        <td className="py-3">{claim.claim_number || "—"}</td>
                        <td className="py-3">{claim.date_of_loss || "—"}</td>
                        <td className="py-3">{claim.loss_type || "—"}</td>
                        <td className="py-3">{claim.status || "—"}</td>
                        <td className="py-3 text-right">
                          {money(Number(claim.incurred || claim.paid || 0))}
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td className="py-6 text-slate-400" colSpan={5}>
                        No claims loaded yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </GlassPanel>

          <GlassPanel title="Loss Analytics">
            <div className="space-y-5">
              <Bar label="Paid" value={totals.paid} max={totals.incurred || 1} />
              <Bar label="Reserve" value={totals.reserve} max={totals.incurred || 1} />
              <Bar label="Incurred" value={totals.incurred} max={totals.incurred || 1} />
            </div>
          </GlassPanel>
        </div>

        <div className="mt-8">
          <GlassPanel title="LossQ Copilot">
            <div className="grid gap-4 md:grid-cols-[1fr_auto]">
              <input
                value={copilotQuestion}
                onChange={(e) => setCopilotQuestion(e.target.value)}
                placeholder="Ask about loss trends, renewal risk, reserves, claim frequency, or carrier strategy..."
                className="rounded-2xl border border-white/10 bg-black/30 px-4 py-4 outline-none focus:border-blue-400"
              />
              <button onClick={askCopilot} className="btn-primary">
                {copilotLoading ? "Thinking..." : "Ask Copilot"}
              </button>
            </div>

            {copilotAnswer && (
              <div className="mt-5 whitespace-pre-wrap rounded-2xl border border-blue-400/20 bg-blue-500/10 p-5 text-slate-200">
                {copilotAnswer}
              </div>
            )}
          </GlassPanel>
        </div>
      </section>
    </main>
  );
}

function MetricCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-3xl border border-white/10 bg-white/[0.06] p-6 shadow-[0_0_50px_rgba(37,99,235,.10)] backdrop-blur-xl">
      <p className="text-sm text-slate-400">{label}</p>
      <h3 className="mt-2 text-3xl font-black">{value}</h3>
    </div>
  );
}

function GlassPanel({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-3xl border border-white/10 bg-white/[0.06] p-6 shadow-[0_0_70px_rgba(15,23,42,.4)] backdrop-blur-xl">
      <h2 className="mb-5 text-xl font-black">{title}</h2>
      {children}
    </section>
  );
}

function ProfileInput({
  label,
  value,
  onChange,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
}) {
  return (
    <label className="mt-3 block">
      <span className="mb-1 block text-sm text-slate-400">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-2xl border border-white/10 bg-black/30 px-4 py-3 outline-none focus:border-blue-400"
      />
    </label>
  );
}

function Bar({ label, value, max }: { label: string; value: number; max: number }) {
  const width = Math.min(100, Math.round((value / max) * 100));

  return (
    <div>
      <div className="mb-2 flex justify-between text-sm">
        <span className="text-slate-300">{label}</span>
        <span className="text-slate-400">{money(value)}</span>
      </div>
      <div className="h-4 rounded-full bg-white/10">
        <div
          className="h-4 rounded-full bg-blue-500 shadow-[0_0_25px_rgba(59,130,246,.55)]"
          style={{ width: `${width}%` }}
        />
      </div>
    </div>
  );
}

function money(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value || 0);
}
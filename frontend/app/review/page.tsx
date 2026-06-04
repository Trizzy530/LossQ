"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_URL || "https://lossq-production.up.railway.app";
const REVIEW_KEY = "lossq_last_upload_review";

type AnyObject = Record<string, any>;

function money(value: any) {
  return `$${Number(value || 0).toLocaleString()}`;
}

function authHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const token = localStorage.getItem("lossq_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function blankPacket() {
  return {
    uploaded_at: "",
    uploaded_files: [],
    profile: {},
    policies: [],
    claims: [],
    validation: {},
    saved_claims: 0,
    raw_response: {},
  } as AnyObject;
}

function normalizeArray(value: any) {
  return Array.isArray(value) ? value : [];
}

export default function ReviewExtractionPage() {
  const router = useRouter();
  const [packet, setPacket] = useState<AnyObject>(blankPacket());
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem("lossq_token");
    if (!token) {
      router.replace("/login?fresh=1");
      return;
    }

    try {
      const raw = localStorage.getItem(REVIEW_KEY);
      if (raw) {
        setPacket({ ...blankPacket(), ...JSON.parse(raw) });
      } else {
        setMessage("No recent upload review packet found. Upload a loss run first, then return here.");
      }
    } catch {
      setMessage("Could not read the last upload review packet.");
    }
  }, [router]);

  const policies = normalizeArray(packet.policies || packet.profile?.policies);
  const claims = normalizeArray(packet.claims || packet.raw_response?.claims || packet.raw_response?.parsed_claims);
  const validation = packet.validation || packet.raw_response?.validation || {};

  const totals = useMemo(() => {
    const totalIncurred = claims.reduce((sum: number, claim: AnyObject) => {
      const incurred =
        Number(claim.total_incurred || claim.incurred || claim.total || 0) ||
        Number(claim.paid_amount || claim.paid || 0) + Number(claim.reserve_amount || claim.reserve || 0);
      return sum + incurred;
    }, 0);

    const openClaims = claims.filter((claim: AnyObject) =>
      String(claim.status || "").toLowerCase().includes("open")
    ).length;

    return {
      totalClaims: claims.length || packet.saved_claims || 0,
      openClaims,
      totalIncurred,
      policyCount: policies.length,
    };
  }, [claims, packet.saved_claims, policies.length]);

  function updateProfileField(field: string, value: string) {
    setPacket((prev) => ({
      ...prev,
      profile: {
        ...(prev.profile || {}),
        [field]: value,
      },
    }));
  }

  function updatePolicy(index: number, field: string, value: string) {
    setPacket((prev) => {
      const nextPolicies = normalizeArray(prev.policies || prev.profile?.policies).map((item: AnyObject, i: number) =>
        i === index ? { ...item, [field]: value } : item
      );
      return {
        ...prev,
        policies: nextPolicies,
        profile: {
          ...(prev.profile || {}),
          policies: nextPolicies,
        },
      };
    });
  }

  function updateClaim(index: number, field: string, value: string) {
    setPacket((prev) => {
      const currentClaims = normalizeArray(prev.claims || prev.raw_response?.claims || prev.raw_response?.parsed_claims);
      const nextClaims = currentClaims.map((item: AnyObject, i: number) =>
        i === index ? { ...item, [field]: value } : item
      );
      return {
        ...prev,
        claims: nextClaims,
      };
    });
  }

  function saveLocalReview() {
    localStorage.setItem(REVIEW_KEY, JSON.stringify(packet));
    setMessage("Review changes saved locally. You can return to the dashboard and continue.");
  }

  async function submitReviewedData() {
    setSaving(true);
    setMessage("Submitting reviewed extraction...");

    try {
      const res = await fetch(`${API}/review/confirm`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify({
          profile: packet.profile || {},
          policies,
          claims,
          validation,
          source: "manual_review_screen",
        }),
      });

      const data = await res.json().catch(() => null);

      if (res.status === 401 || res.status === 403) {
        localStorage.removeItem("lossq_token");
        router.replace("/login?expired=1");
        return;
      }

      if (!res.ok) {
        setMessage(`Backend review save failed with ${res.status}. Saved locally only. ${JSON.stringify(data)}`);
        saveLocalReview();
        return;
      }

      localStorage.setItem(REVIEW_KEY, JSON.stringify({ ...packet, confirmed_response: data }));
      setMessage("Reviewed extraction confirmed. You can now generate reports from the dashboard.");
    } catch (error: any) {
      saveLocalReview();
      setMessage(`Backend review save unavailable. Saved locally only. ${error?.message || "Unknown error"}`);
    } finally {
      setSaving(false);
    }
  }

  const warningItems = normalizeArray(validation.warnings || validation.warning_flags || validation.issues);
  const needsReviewItems = normalizeArray(validation.needs_review || validation.needs_manual_review || []);

  return (
    <main className="min-h-screen bg-[#020617] text-white px-5 py-8">
      <div className="fixed inset-0 bg-[radial-gradient(circle_at_top_left,#1d4ed866,transparent_28%),radial-gradient(circle_at_bottom_right,#0ea5e955,transparent_30%)]" />

      <div className="relative max-w-7xl mx-auto">
        <header className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between mb-8">
          <div>
            <p className="text-sm uppercase tracking-[0.3em] text-blue-300 mb-2">LossQ Validation</p>
            <h1 className="text-4xl md:text-5xl font-black">Manual Extraction Review</h1>
            <p className="text-slate-300 mt-3 max-w-3xl">
              Confirm the insured, policy schedule, claim count, and incurred totals before generating reports.
              LossQ should flag uncertain data instead of guessing.
            </p>
          </div>

          <div className="flex flex-wrap gap-3">
            <button onClick={() => router.push("/dashboard")} className="btn-secondary">Back to Dashboard</button>
            <button onClick={saveLocalReview} className="btn-secondary">Save Local Review</button>
            <button onClick={submitReviewedData} disabled={saving} className="btn-primary disabled:opacity-50">
              {saving ? "Saving..." : "Confirm Reviewed Data"}
            </button>
          </div>
        </header>

        {message && <div className="glass-panel p-4 mb-6 text-slate-200">{message}</div>}

        <section className="grid grid-cols-1 md:grid-cols-4 gap-5 mb-8">
          <Metric title="Policies Found" value={totals.policyCount} />
          <Metric title="Claims Found" value={totals.totalClaims} />
          <Metric title="Open Claims" value={totals.openClaims} />
          <Metric title="Total Incurred" value={money(totals.totalIncurred)} />
        </section>

        {(warningItems.length > 0 || needsReviewItems.length > 0) && (
          <section className="rounded-3xl border border-yellow-400/30 bg-yellow-500/10 p-6 mb-8">
            <h2 className="text-2xl font-bold text-yellow-200 mb-3">Needs Review</h2>
            <ul className="list-disc pl-6 space-y-2 text-yellow-100">
              {[...warningItems, ...needsReviewItems].map((item: any, index: number) => (
                <li key={index}>{typeof item === "string" ? item : JSON.stringify(item)}</li>
              ))}
            </ul>
          </section>
        )}

        <section className="glass-panel p-6 md:p-8 mb-8">
          <h2 className="text-2xl font-bold mb-5">Account Profile</h2>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <EditField label="Insured" value={packet.profile?.business_name || ""} onChange={(v) => updateProfileField("business_name", v)} />
            <EditField label="Writing Carrier" value={packet.profile?.writing_carrier || packet.profile?.carrier_name || ""} onChange={(v) => updateProfileField("writing_carrier", v)} />
            <EditField label="Carrier" value={packet.profile?.carrier_name || ""} onChange={(v) => updateProfileField("carrier_name", v)} />
            <EditField label="Account / Policy" value={packet.profile?.policy_number || ""} onChange={(v) => updateProfileField("policy_number", v)} />
            <EditField label="Account Number" value={packet.profile?.account_number || ""} onChange={(v) => updateProfileField("account_number", v)} />
            <EditField label="Producing Agency" value={packet.profile?.agency_name || ""} onChange={(v) => updateProfileField("agency_name", v)} />
            <EditField label="Effective Date" value={packet.profile?.effective_date || ""} onChange={(v) => updateProfileField("effective_date", v)} />
            <EditField label="Expiration Date" value={packet.profile?.expiration_date || ""} onChange={(v) => updateProfileField("expiration_date", v)} />
          </div>
        </section>

        <section className="glass-panel p-6 md:p-8 mb-8">
          <h2 className="text-2xl font-bold mb-5">Policy Schedule</h2>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1000px] text-sm">
              <thead>
                <tr className="border-b border-white/10 text-left text-slate-300">
                  <th className="py-3 pr-4">Coverage</th>
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
                {policies.map((policy: AnyObject, index: number) => (
                  <tr key={policy.policy_number || index} className="border-b border-white/10">
                    <td className="py-3 pr-4"><SmallInput value={policy.policy_type || policy.line_of_business || policy.coverage || ""} onChange={(v) => updatePolicy(index, "policy_type", v)} /></td>
                    <td className="py-3 pr-4"><SmallInput value={policy.policy_number || ""} onChange={(v) => updatePolicy(index, "policy_number", v)} /></td>
                    <td className="py-3 pr-4"><SmallInput value={policy.writing_carrier || ""} onChange={(v) => updatePolicy(index, "writing_carrier", v)} /></td>
                    <td className="py-3 pr-4"><SmallInput value={policy.carrier || ""} onChange={(v) => updatePolicy(index, "carrier", v)} /></td>
                    <td className="py-3 pr-4"><SmallInput value={policy.effective_date || ""} onChange={(v) => updatePolicy(index, "effective_date", v)} /></td>
                    <td className="py-3 pr-4"><SmallInput value={policy.expiration_date || ""} onChange={(v) => updatePolicy(index, "expiration_date", v)} /></td>
                    <td className="py-3 pr-4"><SmallInput value={String(policy.claim_count ?? "")} onChange={(v) => updatePolicy(index, "claim_count", v)} /></td>
                    <td className="py-3 pr-4"><SmallInput value={String(policy.total_incurred ?? "")} onChange={(v) => updatePolicy(index, "total_incurred", v)} /></td>
                  </tr>
                ))}
                {policies.length === 0 && (
                  <tr><td colSpan={8} className="py-5 text-slate-400">No policy schedule found. Add carrier parser rules or review the upload response.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </section>

        <section className="glass-panel p-6 md:p-8">
          <h2 className="text-2xl font-bold mb-5">Claim Review</h2>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1100px] text-sm">
              <thead>
                <tr className="border-b border-white/10 text-left text-slate-300">
                  <th className="py-3 pr-4">Claim Number</th>
                  <th className="py-3 pr-4">Policy Number</th>
                  <th className="py-3 pr-4">LOB</th>
                  <th className="py-3 pr-4">Status</th>
                  <th className="py-3 pr-4">Paid</th>
                  <th className="py-3 pr-4">Reserve</th>
                  <th className="py-3 pr-4">Total Incurred</th>
                  <th className="py-3 pr-4">Loss Date</th>
                </tr>
              </thead>
              <tbody>
                {claims.map((claim: AnyObject, index: number) => (
                  <tr key={claim.id || claim.claim_number || index} className="border-b border-white/10">
                    <td className="py-3 pr-4"><SmallInput value={claim.claim_number || ""} onChange={(v) => updateClaim(index, "claim_number", v)} /></td>
                    <td className="py-3 pr-4"><SmallInput value={claim.policy_number || ""} onChange={(v) => updateClaim(index, "policy_number", v)} /></td>
                    <td className="py-3 pr-4"><SmallInput value={claim.line_of_business || claim.coverage || ""} onChange={(v) => updateClaim(index, "line_of_business", v)} /></td>
                    <td className="py-3 pr-4"><SmallInput value={claim.status || ""} onChange={(v) => updateClaim(index, "status", v)} /></td>
                    <td className="py-3 pr-4"><SmallInput value={String(claim.paid_amount ?? claim.paid ?? "")} onChange={(v) => updateClaim(index, "paid_amount", v)} /></td>
                    <td className="py-3 pr-4"><SmallInput value={String(claim.reserve_amount ?? claim.reserve ?? "")} onChange={(v) => updateClaim(index, "reserve_amount", v)} /></td>
                    <td className="py-3 pr-4"><SmallInput value={String(claim.total_incurred ?? claim.incurred ?? "")} onChange={(v) => updateClaim(index, "total_incurred", v)} /></td>
                    <td className="py-3 pr-4"><SmallInput value={claim.loss_date || claim.date_of_loss || ""} onChange={(v) => updateClaim(index, "loss_date", v)} /></td>
                  </tr>
                ))}
                {claims.length === 0 && (
                  <tr><td colSpan={8} className="py-5 text-slate-400">No claim rows found in the saved review packet.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <style jsx global>{`
        .glass-panel { border: 1px solid rgba(255,255,255,.1); background: rgba(15,23,42,.72); backdrop-filter: blur(24px); border-radius: 1.5rem; box-shadow: 0 30px 80px rgba(0,0,0,.28); }
        .btn-primary { border-radius: 1rem; background: #2563eb; padding: .85rem 1.15rem; font-weight: 700; box-shadow: 0 0 28px rgba(37,99,235,.25); }
        .btn-primary:hover { background: #3b82f6; }
        .btn-secondary { border-radius: 1rem; border: 1px solid rgba(255,255,255,.12); background: rgba(15,23,42,.8); padding: .85rem 1.15rem; font-weight: 700; color: #dbeafe; }
        .btn-secondary:hover { background: rgba(30,41,59,.9); }
      `}</style>
    </main>
  );
}

function Metric({ title, value }: { title: string; value: any }) {
  return (
    <div className="glass-panel p-5">
      <div className="text-sm text-slate-400">{title}</div>
      <div className="text-3xl font-black mt-2">{value}</div>
    </div>
  );
}

function EditField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="block">
      <span className="block text-sm text-blue-200 mb-2">{label}</span>
      <input value={value} onChange={(e) => onChange(e.target.value)} className="w-full rounded-2xl bg-slate-950/70 border border-white/10 px-4 py-3 text-white outline-none focus:border-blue-400" />
    </label>
  );
}

function SmallInput({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <input value={value} onChange={(e) => onChange(e.target.value)} className="w-full min-w-[120px] rounded-xl bg-slate-950/70 border border-white/10 px-3 py-2 text-white outline-none focus:border-blue-400" />
  );
}
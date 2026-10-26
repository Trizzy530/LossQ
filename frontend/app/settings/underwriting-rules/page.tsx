"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_URL || "https://lossq-production.up.railway.app";

type Rule = {
  id: string;
  label: string;
  metric: string;
  operator: string;
  threshold: number;
  severity: "info" | "warning" | "critical";
  action: string;
  enabled: boolean;
};

const METRICS = [
  ["claim_count", "Claim count"],
  ["open_claim_count", "Open claim count"],
  ["total_incurred", "Total incurred"],
  ["total_reserve", "Total reserve"],
  ["max_single_claim", "Largest claim"],
  ["loss_ratio", "Loss ratio (decimal)"],
  ["litigated_claim_count", "Litigated claim count"],
];

const OPERATORS = [
  ["gte", "is at least"], ["gt", "is greater than"], ["lte", "is at most"],
  ["lt", "is less than"], ["eq", "equals"],
];

function token() {
  if (typeof window === "undefined") return "";
  return sessionStorage.getItem("lossq_tab_token") || localStorage.getItem("lossq_token") || "";
}

function newRule(index: number): Rule {
  return {
    id: `custom-rule-${index}`, label: "New underwriting rule", metric: "total_incurred",
    operator: "gte", threshold: 100000, severity: "warning", action: "Review this account.", enabled: true,
  };
}

export default function UnderwritingRulesPage() {
  const router = useRouter();
  const [name, setName] = useState("Organization underwriting rules");
  const [rules, setRules] = useState<Rule[]>([]);
  const [version, setVersion] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  async function loadRules() {
    const authToken = token();
    if (!authToken) {
      router.push("/login?fresh=1&next=/settings/underwriting-rules");
      return;
    }
    try {
      const response = await fetch(`${API}/loss-intelligence/rules`, {
        headers: { Authorization: `Bearer ${authToken}` },
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data?.detail || "Unable to load underwriting rules.");
      setName(data.name || "Organization underwriting rules");
      setRules(Array.isArray(data.rules) ? data.rules : []);
      setVersion(Number(data.version || 0));
    } catch (error: any) {
      setMessage(error?.message || "Unable to connect to LossQ backend.");
    } finally {
      setLoading(false);
    }
  }

  async function saveRules() {
    setSaving(true);
    setMessage("");
    try {
      const response = await fetch(`${API}/loss-intelligence/rules`, {
        method: "PUT",
        headers: { Authorization: `Bearer ${token()}`, "Content-Type": "application/json" },
        body: JSON.stringify({ name, rules }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data?.detail || "Unable to save underwriting rules.");
      setVersion(Number(data.version || version + 1));
      setRules(data.rules || rules);
      setMessage("Underwriting rules saved and versioned for your organization.");
    } catch (error: any) {
      setMessage(error?.message || "Unable to connect to LossQ backend.");
    } finally {
      setSaving(false);
    }
  }

  function updateRule(index: number, field: keyof Rule, value: string | number | boolean) {
    setRules((current) => current.map((rule, row) => row === index ? { ...rule, [field]: value } : rule));
  }

  useEffect(() => { loadRules(); }, []);

  if (loading) {
    return <main className="min-h-screen bg-[#020617] text-white grid place-items-center">Loading underwriting rules...</main>;
  }

  return (
    <main className="min-h-screen bg-[#020617] text-white px-5 py-8">
      <div className="mx-auto max-w-6xl">
        <header className="mb-8 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-sm font-bold uppercase tracking-[.25em] text-blue-300">Decision Governance</p>
            <h1 className="mt-2 text-4xl font-black">Underwriting Rules</h1>
            <p className="mt-2 max-w-3xl text-slate-300">
              Configure deterministic referral thresholds for your organization. Rules are versioned and every change is audited.
            </p>
          </div>
          <div className="flex gap-3">
            <button onClick={() => router.push("/settings")} className="rounded-xl border border-white/15 px-4 py-3 font-bold">Back</button>
            <button onClick={saveRules} disabled={saving || rules.length === 0} className="rounded-xl bg-blue-600 px-5 py-3 font-bold disabled:opacity-50">
              {saving ? "Saving..." : "Save Rules"}
            </button>
          </div>
        </header>

        {message && <div className="mb-6 rounded-2xl border border-blue-400/30 bg-blue-500/10 p-4 text-blue-100">{message}</div>}

        <section className="mb-6 rounded-3xl border border-white/10 bg-slate-900/70 p-6">
          <div className="grid gap-4 md:grid-cols-[1fr_auto] md:items-end">
            <label className="block">
              <span className="mb-2 block text-sm text-slate-300">Rule-set name</span>
              <input value={name} onChange={(event) => setName(event.target.value)} className="w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3" />
            </label>
            <div className="rounded-xl border border-white/10 bg-slate-950 px-4 py-3 text-slate-300">Version {version}</div>
          </div>
        </section>

        <div className="space-y-5">
          {rules.map((rule, index) => (
            <section key={`${rule.id}-${index}`} className="rounded-3xl border border-white/10 bg-slate-900/70 p-6">
              <div className="mb-5 flex items-center justify-between gap-4">
                <label className="flex items-center gap-3 font-bold">
                  <input type="checkbox" checked={rule.enabled} onChange={(event) => updateRule(index, "enabled", event.target.checked)} />
                  Enabled
                </label>
                <button onClick={() => setRules((current) => current.filter((_, row) => row !== index))} className="text-sm font-bold text-red-300">Remove</button>
              </div>
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                <Field label="Rule ID"><input value={rule.id} onChange={(event) => updateRule(index, "id", event.target.value)} className="input" /></Field>
                <Field label="Label"><input value={rule.label} onChange={(event) => updateRule(index, "label", event.target.value)} className="input" /></Field>
                <Field label="Metric"><select value={rule.metric} onChange={(event) => updateRule(index, "metric", event.target.value)} className="input">{METRICS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field>
                <Field label="Condition"><select value={rule.operator} onChange={(event) => updateRule(index, "operator", event.target.value)} className="input">{OPERATORS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field>
                <Field label="Threshold"><input type="number" step="any" value={rule.threshold} onChange={(event) => updateRule(index, "threshold", Number(event.target.value))} className="input" /></Field>
                <Field label="Severity"><select value={rule.severity} onChange={(event) => updateRule(index, "severity", event.target.value)} className="input"><option value="info">Info</option><option value="warning">Warning</option><option value="critical">Critical referral</option></select></Field>
                <div className="md:col-span-2"><Field label="Required action"><input value={rule.action} onChange={(event) => updateRule(index, "action", event.target.value)} className="input" /></Field></div>
              </div>
            </section>
          ))}
        </div>

        <button onClick={() => setRules((current) => [...current, newRule(current.length + 1)])} className="mt-6 rounded-xl border border-blue-400/30 bg-blue-500/10 px-5 py-3 font-bold text-blue-100">Add Rule</button>
      </div>
      <style jsx global>{`.input{width:100%;border-radius:.75rem;border:1px solid rgba(255,255,255,.1);background:#020617;padding:.75rem 1rem;color:white}.input:focus{outline:none;border-color:#60a5fa}`}</style>
    </main>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="block"><span className="mb-2 block text-sm text-slate-300">{label}</span>{children}</label>;
}

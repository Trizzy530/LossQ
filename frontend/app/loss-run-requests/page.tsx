"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_URL || "https://lossq-production.up.railway.app";

type RequestItem = {
  id: number;
  insured_name: string;
  carrier_name: string;
  policy_number?: string;
  contact_name?: string;
  contact_email?: string;
  status: string;
  authorization_received: boolean;
  next_follow_up_at?: string;
  notes?: string;
  needs_attention: boolean;
  updated_at: string;
};

const STATUS_LABELS: Record<string, string> = {
  draft: "Draft",
  authorization_needed: "Authorization needed",
  requested: "Requested",
  follow_up_due: "Follow-up due",
  received: "Received",
  processing: "Processing",
  completed: "Completed",
  cancelled: "Cancelled",
};

function authToken() {
  if (typeof window === "undefined") return "";
  return sessionStorage.getItem("lossq_tab_token") || localStorage.getItem("lossq_token") || "";
}

function formatDate(value?: string) {
  if (!value) return "Not scheduled";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function nextStatuses(status: string) {
  const options: Record<string, string[]> = {
    draft: ["authorization_needed", "requested", "cancelled"],
    authorization_needed: ["requested", "cancelled"],
    requested: ["follow_up_due", "received", "cancelled"],
    follow_up_due: ["requested", "received", "cancelled"],
    received: ["processing", "completed"],
    processing: ["completed", "follow_up_due"],
    completed: [],
    cancelled: ["draft"],
  };
  return options[status] || [];
}

export default function LossRunRequestsPage() {
  const router = useRouter();
  const [items, setItems] = useState<RequestItem[]>([]);
  const [counts, setCounts] = useState({ total: 0, attention: 0, received: 0, completed: 0 });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [attentionOnly, setAttentionOnly] = useState(false);
  const [form, setForm] = useState({
    insured_name: "",
    carrier_name: "",
    policy_number: "",
    contact_name: "",
    contact_email: "",
    authorization_received: false,
    next_follow_up_at: "",
    notes: "",
  });

  const visibleItems = useMemo(
    () => (attentionOnly ? items.filter((item) => item.needs_attention) : items),
    [attentionOnly, items],
  );

  async function apiFetch(path: string, init?: RequestInit) {
    const token = authToken();
    if (!token) {
      router.push("/login?fresh=1&next=/loss-run-requests");
      throw new Error("Sign in required.");
    }
    const response = await fetch(`${API}${path}`, {
      ...init,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...(init?.headers || {}),
      },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data?.detail || "LossQ could not complete this request.");
    return data;
  }

  async function loadRequests() {
    try {
      const data = await apiFetch("/loss-run-requests");
      setItems(Array.isArray(data.items) ? data.items : []);
      setCounts(data.counts || { total: 0, attention: 0, received: 0, completed: 0 });
    } catch (error: unknown) {
      setMessage(error instanceof Error ? error.message : "Unable to load request pipeline.");
    } finally {
      setLoading(false);
    }
  }

  async function createRequest(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setMessage("");
    try {
      await apiFetch("/loss-run-requests", {
        method: "POST",
        body: JSON.stringify({
          ...form,
          status: form.authorization_received ? "requested" : "authorization_needed",
          next_follow_up_at: form.next_follow_up_at ? new Date(form.next_follow_up_at).toISOString() : null,
        }),
      });
      setForm({ insured_name: "", carrier_name: "", policy_number: "", contact_name: "", contact_email: "", authorization_received: false, next_follow_up_at: "", notes: "" });
      setMessage("Request added to the organization pipeline.");
      await loadRequests();
    } catch (error: unknown) {
      setMessage(error instanceof Error ? error.message : "Unable to create request.");
    } finally {
      setSaving(false);
    }
  }

  async function moveRequest(item: RequestItem, status: string) {
    setMessage("");
    try {
      await apiFetch(`/loss-run-requests/${item.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          status,
          authorization_received: status === "requested" ? true : item.authorization_received,
          event_note: `Moved to ${STATUS_LABELS[status] || status} from the request pipeline.`,
        }),
      });
      await loadRequests();
    } catch (error: unknown) {
      setMessage(error instanceof Error ? error.message : "Unable to update request.");
    }
  }

  useEffect(() => { void loadRequests(); }, []);

  return (
    <main className="min-h-screen bg-[#020617] px-4 py-8 text-white sm:px-6">
      <div className="mx-auto max-w-7xl">
        <header className="mb-8 flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-sm font-bold uppercase tracking-[.26em] text-cyan-300">Pre-ingestion workflow</p>
            <h1 className="mt-2 text-4xl font-black sm:text-5xl">Loss Run Request Pipeline</h1>
            <p className="mt-3 max-w-3xl text-slate-300">Track authorization, carrier outreach, follow-ups, receipt, and processing in one auditable organization queue.</p>
          </div>
          <button onClick={() => router.push("/dashboard")} className="rounded-xl border border-white/15 px-5 py-3 font-bold hover:bg-white/10">Back to dashboard</button>
        </header>

        {message && <div className="mb-6 rounded-2xl border border-cyan-400/30 bg-cyan-500/10 p-4 text-cyan-50">{message}</div>}

        <section className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Metric label="Open pipeline" value={counts.total - counts.completed} />
          <Metric label="Needs attention" value={counts.attention} warning={counts.attention > 0} />
          <Metric label="Received / processing" value={counts.received} />
          <Metric label="Completed" value={counts.completed} />
        </section>

        <div className="grid gap-8 xl:grid-cols-[380px_1fr]">
          <form onSubmit={createRequest} className="h-fit rounded-3xl border border-white/10 bg-slate-900/80 p-6 shadow-2xl">
            <h2 className="text-2xl font-black">Start a request</h2>
            <p className="mt-2 text-sm text-slate-400">Authorization is required before LossQ marks outreach as sent.</p>
            <div className="mt-6 space-y-4">
              <Field label="Insured name" required value={form.insured_name} onChange={(value) => setForm({ ...form, insured_name: value })} />
              <Field label="Carrier" required value={form.carrier_name} onChange={(value) => setForm({ ...form, carrier_name: value })} />
              <Field label="Policy number" value={form.policy_number} onChange={(value) => setForm({ ...form, policy_number: value })} />
              <Field label="Carrier contact" value={form.contact_name} onChange={(value) => setForm({ ...form, contact_name: value })} />
              <Field label="Contact email" type="email" value={form.contact_email} onChange={(value) => setForm({ ...form, contact_email: value })} />
              <Field label="Next follow-up" type="datetime-local" value={form.next_follow_up_at} onChange={(value) => setForm({ ...form, next_follow_up_at: value })} />
              <label className="flex items-start gap-3 rounded-xl border border-white/10 bg-slate-950 p-4 text-sm">
                <input type="checkbox" className="mt-1" checked={form.authorization_received} onChange={(event) => setForm({ ...form, authorization_received: event.target.checked })} />
                <span><strong className="block text-white">Authorization confirmed</strong><span className="text-slate-400">The insured has authorized this loss-run request.</span></span>
              </label>
              <label className="block text-sm text-slate-300">Notes<textarea value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} className="mt-2 min-h-24 w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3 text-white" /></label>
            </div>
            <button disabled={saving} className="mt-5 w-full rounded-xl bg-cyan-400 px-5 py-3 font-black text-slate-950 hover:bg-cyan-300 disabled:opacity-50">{saving ? "Adding..." : form.authorization_received ? "Add as requested" : "Add for authorization"}</button>
          </form>

          <section>
            <div className="mb-4 flex items-center justify-between gap-4">
              <div><h2 className="text-2xl font-black">Organization queue</h2><p className="text-sm text-slate-400">Every status change is retained in the audit timeline.</p></div>
              <label className="flex items-center gap-2 text-sm font-bold text-slate-300"><input type="checkbox" checked={attentionOnly} onChange={(event) => setAttentionOnly(event.target.checked)} />Attention only</label>
            </div>
            {loading ? <div className="rounded-3xl border border-white/10 p-10 text-center text-slate-400">Loading request pipeline...</div> : visibleItems.length === 0 ? <div className="rounded-3xl border border-dashed border-white/15 p-10 text-center text-slate-400">No matching requests. Add the first account to start the pipeline.</div> : <div className="space-y-4">{visibleItems.map((item) => <RequestCard key={item.id} item={item} onMove={moveRequest} />)}</div>}
          </section>
        </div>
      </div>
    </main>
  );
}

function Metric({ label, value, warning = false }: { label: string; value: number; warning?: boolean }) {
  return <div className={`rounded-2xl border p-5 ${warning ? "border-amber-400/40 bg-amber-500/10" : "border-white/10 bg-slate-900/70"}`}><p className="text-sm text-slate-400">{label}</p><p className="mt-2 text-3xl font-black">{value}</p></div>;
}

function Field({ label, value, onChange, required = false, type = "text" }: { label: string; value: string; onChange: (value: string) => void; required?: boolean; type?: string }) {
  return <label className="block text-sm text-slate-300">{label}<input required={required} type={type} value={value} onChange={(event) => onChange(event.target.value)} className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3 text-white" /></label>;
}

function RequestCard({ item, onMove }: { item: RequestItem; onMove: (item: RequestItem, status: string) => void }) {
  return <article className={`rounded-3xl border p-5 ${item.needs_attention ? "border-amber-400/40 bg-amber-500/5" : "border-white/10 bg-slate-900/70"}`}>
    <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
      <div>
        <div className="flex flex-wrap items-center gap-2"><h3 className="text-xl font-black">{item.insured_name}</h3>{item.needs_attention && <span className="rounded-full bg-amber-400 px-3 py-1 text-xs font-black text-slate-950">ACTION DUE</span>}</div>
        <p className="mt-1 text-slate-300">{item.carrier_name}{item.policy_number ? ` · ${item.policy_number}` : ""}</p>
        <p className="mt-2 text-sm text-slate-400">Follow-up: {formatDate(item.next_follow_up_at)}</p>
        {(item.contact_name || item.contact_email) && <p className="mt-1 text-sm text-slate-400">Contact: {[item.contact_name, item.contact_email].filter(Boolean).join(" · ")}</p>}
      </div>
      <div className="min-w-52">
        <p className="mb-2 text-xs font-bold uppercase tracking-wider text-cyan-300">{STATUS_LABELS[item.status] || item.status}</p>
        <select defaultValue="" onChange={(event) => { if (event.target.value) onMove(item, event.target.value); event.currentTarget.value = ""; }} className="w-full rounded-xl border border-white/10 bg-slate-950 px-3 py-2 text-sm text-white">
          <option value="">Move to…</option>{nextStatuses(item.status).map((status) => <option key={status} value={status}>{STATUS_LABELS[status]}</option>)}
        </select>
      </div>
    </div>
    {item.notes && <p className="mt-4 rounded-xl bg-slate-950/70 p-3 text-sm text-slate-300">{item.notes}</p>}
  </article>;
}

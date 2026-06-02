"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";

const API =
  process.env.NEXT_PUBLIC_API_URL || "https://lossq-production.up.railway.app";

async function safeJson(res: Response) {
  try {
    return await res.json();
  } catch {
    return null;
  }
}

function money(value: any) {
  return `$${Number(value || 0).toLocaleString()}`;
}

function clean(value: any) {
  return value || "-";
}

export default function ClaimDetailPage() {
  const params = useParams();
  const router = useRouter();

  const claimId = params?.id;
  const [data, setData] = useState<any>(null);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);

  function authHeaders(): Record<string, string> {
    const token = localStorage.getItem("lossq_token");
    return token ? { Authorization: `Bearer ${token}` } : {};
  }

  async function loadClaim() {
    if (!claimId) return;

    setLoading(true);
    setMessage("");

    try {
      const res = await fetch(`${API}/claims/${claimId}`, {
        headers: authHeaders(),
      });

      const json = await safeJson(res);

      if (res.status === 401 || res.status === 403) {
        localStorage.removeItem("lossq_token");
        localStorage.removeItem("lossq_user");
        localStorage.removeItem("lossq_login_time");
        router.replace("/login");
        return;
      }

      if (!res.ok) {
        setMessage(json?.detail || "Claim intelligence could not be loaded.");
        return;
      }

      setData(json);
    } catch {
      setMessage("Claim intelligence failed to load.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadClaim();
  }, [claimId]);

  if (loading) {
    return (
      <main className="min-h-screen bg-[#030508] text-white flex items-center justify-center overflow-hidden">
        <BackgroundGlow />

        <div className="relative text-center">
          <div className="text-5xl font-black mb-4">
            Loss<span className="text-blue-500">Q</span>
          </div>
          <div className="text-blue-200 tracking-wide">
            Loading claim intelligence...
          </div>
        </div>
      </main>
    );
  }

  if (message) {
    return (
      <main className="min-h-screen bg-[#030508] text-white flex items-center justify-center px-6 overflow-hidden">
        <BackgroundGlow />

        <div className="relative max-w-xl w-full bg-white/5 backdrop-blur-xl border border-red-500/30 rounded-3xl p-10 shadow-2xl text-center">
          <div className="text-red-400 text-sm uppercase tracking-[0.3em] mb-3">
            Claim Error
          </div>

          <h1 className="text-4xl font-black mb-4">
            Intelligence Unavailable
          </h1>

          <p className="text-slate-300 mb-8">{message}</p>

          <div className="flex justify-center gap-4">
            <button
              onClick={loadClaim}
              className="bg-blue-600 hover:bg-blue-700 px-6 py-3 rounded-xl font-bold"
            >
              Retry
            </button>

            <a
              href="/dashboard"
              className="bg-white/10 hover:bg-white/15 border border-white/10 px-6 py-3 rounded-xl font-bold"
            >
              Back to Dashboard
            </a>
          </div>
        </div>
      </main>
    );
  }

  const claim = data?.claim || {};
  const severity = data?.severity || "Low";
  const severityScore = Number(data?.severity_score || 0);

  const riskColor =
    severity === "Catastrophic"
      ? "text-red-300 border-red-500/40 bg-red-500/10"
      : severity === "Severe"
      ? "text-orange-300 border-orange-500/40 bg-orange-500/10"
      : severity === "Moderate"
      ? "text-yellow-300 border-yellow-500/40 bg-yellow-500/10"
      : "text-emerald-300 border-emerald-500/40 bg-emerald-500/10";

  return (
    <main className="min-h-screen bg-[#030508] text-white overflow-hidden">
      <BackgroundGlow />

      <div className="relative max-w-7xl mx-auto px-6 py-10">
        <header className="flex flex-col lg:flex-row justify-between gap-6 items-start mb-10">
          <div>
            <div className="text-blue-400 text-sm uppercase tracking-[0.35em] mb-4">
              Claim Intelligence
            </div>

            <h1 className="text-5xl lg:text-7xl font-black tracking-tight">
              Claim{" "}
              <span className="text-blue-500">
                {clean(claim.claim_number)}
              </span>
            </h1>

            <p className="text-slate-400 mt-5 text-lg max-w-3xl">
              Modern underwriting view for claim timeline, severity, reserves,
              litigation indicators, and broker action strategy.
            </p>
          </div>

          <div className="flex gap-3">
            <a
              href="/dashboard"
              className="bg-white/10 hover:bg-white/15 border border-white/10 px-5 py-3 rounded-xl font-bold"
            >
              Back to Dashboard
            </a>
          </div>
        </header>

        <section className="grid grid-cols-1 md:grid-cols-4 gap-5 mb-8">
          <HeroMetric title="Status" value={clean(claim.status)} />
          <HeroMetric title="Severity" value={severity} badgeClass={riskColor} />
          <HeroMetric title="Score" value={`${severityScore}/100`} />
          <HeroMetric title="Renewal Impact" value={clean(data?.renewal_impact)} />
        </section>

        <section className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
          <GlassPanel className="lg:col-span-2">
            <div className="flex justify-between gap-6 items-start mb-6">
              <div>
                <h2 className="text-3xl font-black">AI Claim Narrative</h2>
                <p className="text-slate-400 mt-2">
                  AI-generated underwriting explanation for this individual claim.
                </p>
              </div>

              <div className={`border rounded-full px-4 py-2 text-sm font-bold ${riskColor}`}>
                {severity}
              </div>
            </div>

            <p className="text-slate-200 leading-8 text-lg">
              {data?.ai_summary || "No narrative available."}
            </p>
          </GlassPanel>

          <GlassPanel>
            <h2 className="text-3xl font-black mb-6">Financial Exposure</h2>

            <div className="space-y-4">
              <ExposureRow label="Paid" value={money(claim.paid_amount)} />
              <ExposureRow label="Reserve" value={money(claim.reserve_amount)} />
              <ExposureRow label="Total Incurred" value={money(claim.total_incurred)} highlight />
              <ExposureRow label="Reserve Concern" value={clean(data?.reserve_concern)} />
            </div>
          </GlassPanel>
        </section>

        <section className="grid grid-cols-1 lg:grid-cols-5 gap-5 mb-8">
          <TimelineCard title="Date of Loss" value={clean(claim.date_of_loss)} />
          <TimelineCard title="Date Reported" value={clean(claim.date_reported)} />
          <TimelineCard title="Date Closed" value={clean(claim.date_closed)} />
          <TimelineCard
            title="Claim Age"
            value={claim.claim_age ? `${claim.claim_age} days` : "-"}
          />
          <TimelineCard
            title="Open Days"
            value={claim.open_days ? `${claim.open_days} days` : "-"}
          />
        </section>

        <section className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          <GlassPanel>
            <h2 className="text-3xl font-black mb-6">Claim Summary</h2>

            <InfoGrid
              items={[
                ["Policy Number", claim.policy_number],
                ["Line of Business", claim.line_of_business],
                ["Claim Type", claim.claim_type],
                ["Cause of Loss", claim.cause_of_loss],
                ["Claimant Type", claim.claimant_type],
                ["Injury Type", claim.injury_type],
                ["Description", claim.description],
              ]}
            />
          </GlassPanel>

          <GlassPanel>
            <h2 className="text-3xl font-black mb-6">Litigation Intelligence</h2>

            <InfoGrid
              items={[
                ["Litigation", claim.litigation ? "Yes" : "No"],
                ["Litigation Status", claim.litigation_status],
                ["Attorney Assigned", claim.attorney_assigned ? "Yes" : "No"],
                ["Suit Filed", claim.suit_filed ? "Yes" : "No"],
                ["Venue State", claim.venue_state],
                ["Exposure", data?.litigation_exposure],
              ]}
            />
          </GlassPanel>
        </section>

        <section className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
  <ActionPanel
    title="Risk Factors"
    items={data?.risk_factors || []}
  />

  <ActionPanel
    title="Broker Actions"
    items={data?.broker_actions || []}
  />
</section>

<section className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
  <GlassPanel>
    <h2 className="text-3xl font-black mb-6">
      Underwriter Narrative
    </h2>

    <p className="text-slate-200 leading-8">
      {data?.underwriter_narrative ||
        "No narrative available."}
    </p>
  </GlassPanel>

  <GlassPanel>
    <h2 className="text-3xl font-black mb-6">
      Risk Summary
    </h2>

    <p className="text-slate-200 leading-8">
      {data?.risk_summary ||
        "No risk summary available."}
    </p>
  </GlassPanel>
</section>

<section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
  <GlassPanel>
    <h2 className="text-3xl font-black mb-6">
      Litigation Analysis
    </h2>

    <p className="text-slate-200 leading-8">
      {data?.litigation_analysis ||
        "No litigation analysis available."}
    </p>
  </GlassPanel>

  <ActionPanel
    title="Broker Talking Points"
    items={data?.broker_talking_points || []}
  />
</section>
      </div>
    </main>
  );
}

function BackgroundGlow() {
  return (
    <>
      <div className="fixed inset-0 bg-[linear-gradient(rgba(0,120,255,0.05)_1px,transparent_1px),linear-gradient(90deg,rgba(0,120,255,0.05)_1px,transparent_1px)] bg-[size:60px_60px]" />
      <div className="fixed inset-0 bg-[radial-gradient(circle_at_top_left,rgba(0,120,255,0.35),transparent_35%),radial-gradient(circle_at_bottom_right,rgba(37,99,235,0.22),transparent_35%)]" />
    </>
  );
}

function GlassPanel({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`bg-white/5 backdrop-blur-xl border border-white/10 rounded-3xl p-7 shadow-2xl ${className}`}
    >
      {children}
    </section>
  );
}

function HeroMetric({
  title,
  value,
  badgeClass = "text-blue-200 border-blue-500/30 bg-blue-500/10",
}: {
  title: string;
  value: any;
  badgeClass?: string;
}) {
  return (
    <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-3xl p-6 shadow-xl">
      <div className="text-slate-400 text-sm mb-3">{title}</div>
      <div className={`inline-flex border rounded-full px-4 py-2 text-xl font-black ${badgeClass}`}>
        {value || "-"}
      </div>
    </div>
  );
}

function TimelineCard({ title, value }: { title: string; value: any }) {
  return (
    <div className="bg-white/5 backdrop-blur-xl border border-blue-500/20 rounded-3xl p-6 shadow-xl">
      <div className="h-2 w-2 rounded-full bg-blue-400 shadow-[0_0_20px_rgba(59,130,246,1)] mb-4" />
      <div className="text-slate-400 text-sm mb-2">{title}</div>
      <div className="text-2xl font-black break-words">{value || "-"}</div>
    </div>
  );
}

function ExposureRow({
  label,
  value,
  highlight = false,
}: {
  label: string;
  value: any;
  highlight?: boolean;
}) {
  return (
    <div className="flex justify-between border-b border-white/10 pb-3 gap-4">
      <span className="text-slate-400">{label}</span>
      <span className={highlight ? "text-blue-300 font-black" : "text-white font-bold"}>
        {value || "-"}
      </span>
    </div>
  );
}

function InfoGrid({ items }: { items: [string, any][] }) {
  return (
    <div className="grid grid-cols-1 gap-4">
      {items.map(([label, value]) => (
        <div key={label} className="border-b border-white/10 pb-3">
          <div className="text-slate-500 text-sm mb-1">{label}</div>
          <div className="text-slate-200 break-words">{clean(value)}</div>
        </div>
      ))}
    </div>
  );
}

function ActionPanel({ title, items }: { title: string; items: string[] }) {
  return (
    <GlassPanel>
      <h2 className="text-3xl font-black mb-6">{title}</h2>

      {items.length === 0 ? (
        <p className="text-slate-400">No items identified.</p>
      ) : (
        <div className="space-y-3">
          {items.map((item, index) => (
            <div
              key={index}
              className="bg-blue-500/10 border border-blue-500/20 rounded-2xl px-4 py-3 text-slate-200"
            >
              {item}
            </div>
          ))}
        </div>
      )}
    </GlassPanel>
  );
}
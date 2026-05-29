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

function valueOrDash(value: any) {
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
        setMessage(json?.detail || "Claim could not be loaded.");
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
      <main className="min-h-screen bg-slate-950 text-white flex items-center justify-center">
        Loading claim intelligence...
      </main>
    );
  }

  if (message) {
    return (
      <main className="min-h-screen bg-slate-950 text-white flex items-center justify-center px-6">
        <div className="bg-slate-900 border border-red-500 rounded-2xl p-8 max-w-lg w-full text-center">
          <h1 className="text-3xl font-bold text-red-400 mb-4">
            Claim Error
          </h1>
          <p className="text-slate-300 mb-6">{message}</p>

          <button
            onClick={loadClaim}
            className="bg-blue-600 hover:bg-blue-700 px-5 py-3 rounded-lg font-semibold mr-3"
          >
            Retry
          </button>

          <a
            href="/dashboard"
            className="bg-slate-800 hover:bg-slate-700 px-5 py-3 rounded-lg font-semibold"
          >
            Back to Dashboard
          </a>
        </div>
      </main>
    );
  }

  const claim = data?.claim || {};

  return (
    <main className="min-h-screen bg-slate-950 text-white p-10">
      <div className="max-w-7xl mx-auto">
        <div className="flex justify-between items-start mb-10">
          <div>
            <h1 className="text-5xl font-bold">
              Claim {valueOrDash(claim.claim_number)}
            </h1>
            <p className="text-slate-400 mt-2">
              Claim intelligence, timeline, financials, and underwriting impact
            </p>
          </div>

          <a
            href="/dashboard"
            className="bg-slate-800 hover:bg-slate-700 px-5 py-3 rounded-lg"
          >
            Back to Dashboard
          </a>
        </div>

        <section className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-10">
          <Metric title="Status" value={claim.status || "-"} />
          <Metric title="Severity" value={data?.severity || "-"} />
          <Metric title="Severity Score" value={data?.severity_score ?? "-"} />
          <Metric title="Renewal Impact" value={data?.renewal_impact || "-"} />
        </section>

        <section className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-10">
          <Metric title="Paid" value={money(claim.paid_amount)} />
          <Metric title="Reserve" value={money(claim.reserve_amount)} />
          <Metric title="Total Incurred" value={money(claim.total_incurred)} />
        </section>

        <section className="bg-slate-900 border border-slate-800 rounded-2xl p-6 mb-10">
          <h2 className="text-3xl font-semibold mb-6">Claim Timeline</h2>

          <div className="grid grid-cols-1 md:grid-cols-5 gap-5">
            <Info title="Date of Loss" value={claim.date_of_loss} />
            <Info title="Date Reported" value={claim.date_reported} />
            <Info title="Date Closed" value={claim.date_closed} />
            <Info title="Claim Age" value={claim.claim_age ? `${claim.claim_age} days` : "-"} />
            <Info title="Open Days" value={claim.open_days ? `${claim.open_days} days` : "-"} />
          </div>
        </section>

        <section className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-10">
          <Panel title="Claim Summary">
            <Info title="Policy Number" value={claim.policy_number} />
            <Info title="Line of Business" value={claim.line_of_business} />
            <Info title="Claim Type" value={claim.claim_type} />
            <Info title="Cause of Loss" value={claim.cause_of_loss} />
            <Info title="Injury Type" value={claim.injury_type} />
            <Info title="Description" value={claim.description} />
          </Panel>

          <Panel title="Litigation Indicators">
            <Info title="Litigation" value={claim.litigation ? "Yes" : "No"} />
            <Info title="Litigation Status" value={claim.litigation_status} />
            <Info title="Attorney Assigned" value={claim.attorney_assigned ? "Yes" : "No"} />
            <Info title="Suit Filed" value={claim.suit_filed ? "Yes" : "No"} />
            <Info title="Venue State" value={claim.venue_state} />
            <Info title="Exposure" value={data?.litigation_exposure} />
          </Panel>
        </section>

        <section className="bg-slate-900 border border-slate-800 rounded-2xl p-6 mb-10">
          <h2 className="text-3xl font-semibold mb-5">AI Claim Narrative</h2>
          <p className="text-slate-300 leading-8">
            {data?.ai_summary || "No narrative available."}
          </p>
        </section>

        <section className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-10">
          <Panel title="Risk Factors">
            {data?.risk_factors?.length ? (
              <ul className="list-disc pl-6 space-y-2 text-slate-300">
                {data.risk_factors.map((item: string, index: number) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            ) : (
              <p className="text-slate-400">No major risk factors detected.</p>
            )}
          </Panel>

          <Panel title="Broker Actions">
            {data?.broker_actions?.length ? (
              <ul className="list-disc pl-6 space-y-2 text-slate-300">
                {data.broker_actions.map((item: string, index: number) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            ) : (
              <p className="text-slate-400">No broker actions available.</p>
            )}
          </Panel>
        </section>

        <section className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
          <h2 className="text-3xl font-semibold mb-5">Reserve Adequacy</h2>
          <p className="text-slate-300 leading-8">
            Reserve concern level:{" "}
            <span className="font-bold text-blue-400">
              {data?.reserve_concern || "-"}
            </span>
          </p>
        </section>
      </div>
    </main>
  );
}

function Metric({ title, value }: { title: string; value: any }) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
      <div className="text-slate-400 mb-2">{title}</div>
      <div className="text-2xl font-bold break-words">{value || "-"}</div>
    </div>
  );
}

function Info({ title, value }: { title: string; value: any }) {
  return (
    <div className="mb-4">
      <div className="text-slate-500 text-sm mb-1">{title}</div>
      <div className="text-slate-200 break-words">{valueOrDash(value)}</div>
    </div>
  );
}

function Panel({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
      <h2 className="text-3xl font-semibold mb-5">{title}</h2>
      {children}
    </section>
  );
}
"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

const API =
  process.env.NEXT_PUBLIC_API_URL || "https://lossq-production.up.railway.app";

export default function ClaimDetailPage() {
  const params = useParams();
  const claimId = params?.id as string;

  const [data, setData] = useState<any>(null);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (claimId) {
      loadClaim();
    }
  }, [claimId]);

  function getToken() {
    return localStorage.getItem("lossq_token");
  }

  async function loadClaim() {
    const token = getToken();

    if (!token) {
      window.location.href = "/login";
      return;
    }

    const res = await fetch(`${API}/claims/${claimId}`, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    const result = await res.json();

    if (!res.ok) {
      setMessage(JSON.stringify(result));
      return;
    }


    setData(result);
  }

  if (message) {
    return (
      <main className="min-h-screen bg-slate-950 text-white p-8">
        <a href="/dashboard" className="text-blue-400">
          ← Back to Dashboard
        </a>

        <p className="text-red-400 mt-6">{message}</p>
      </main>
    );
  }

  if (!data) {
    return (
      <main className="min-h-screen bg-slate-950 text-white p-8">
        Loading claim intelligence...
      </main>
    );
  }

  const claim = data.claim;

  return (
    <main className="min-h-screen bg-slate-950 text-white p-8">
      <div className="max-w-7xl mx-auto">
        <a href="/dashboard" className="text-blue-400 hover:text-blue-300">
          ← Back to Dashboard
        </a>

        <section className="bg-slate-900 border border-slate-800 rounded-xl p-8 mt-6 mb-8">
          <div className="flex justify-between gap-8">
            <div>
              <h1 className="text-4xl font-bold">{claim.claim_number}</h1>
              <p className="text-slate-400 mt-2">{claim.line_of_business}</p>
              <p className="text-slate-500 mt-1">Policy: {claim.policy_number || "Not assigned"}</p>
            </div>

            <div className="text-right">
              <p className="text-slate-400">Severity Score</p>
              <h2
                className={`text-5xl font-bold ${
                  data.severity_score >= 75
                    ? "text-red-400"
                    : data.severity_score >= 50
                    ? "text-orange-400"
                    : data.severity_score >= 25
                    ? "text-yellow-400"
                    : "text-green-400"
                }`}
              >
                {data.severity_score}/100
              </h2>
              <p className="text-slate-300 mt-2">{data.severity}</p>
            </div>
          </div>
        </section>

        <section className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
          <Card label="Paid" value={`$${Number(claim.paid_amount || 0).toLocaleString()}`} />
          <Card label="Reserve" value={`$${Number(claim.reserve_amount || 0).toLocaleString()}`} />
          <Card label="Total Incurred" value={`$${Number(claim.total_incurred || 0).toLocaleString()}`} />
          <Card label="Status" value={claim.status || "Unknown"} />
        </section>

        <section className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <RiskCard label="Litigation Risk" value={data.litigation_exposure} tone={data.litigation_exposure?.includes("Elevated") ? "red" : "green"} />
          <RiskCard label="Reserve Adequacy" value={data.reserve_concern} tone={data.reserve_concern === "High" ? "red" : data.reserve_concern === "Moderate" ? "yellow" : "green"} />
          <RiskCard label="Renewal Impact" value={data.renewal_impact} tone={data.renewal_impact?.includes("High") ? "red" : data.renewal_impact?.includes("Moderate") ? "yellow" : "green"} />
        </section>

        <section className="bg-slate-900 border border-slate-800 rounded-xl p-8 mb-8">
          <h2 className="text-2xl font-semibold mb-4">
            AI Claim Intelligence Summary
          </h2>

          <p className="text-slate-300 leading-8">
            {data.ai_summary}
          </p>
        </section>

        <section className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-8">
          <section className="bg-slate-900 border border-slate-800 rounded-xl p-8">
            <h2 className="text-2xl font-semibold mb-4">
              Carrier Concern Reasons
            </h2>

            {data.risk_factors?.length === 0 ? (
              <p className="text-slate-400">No major risk factors detected.</p>
            ) : (
              <div className="space-y-3">
                {data.risk_factors?.map((factor: string) => (
                  <div
                    key={factor}
                    className="bg-red-500/10 text-red-300 px-4 py-3 rounded-lg"
                  >
                    • {factor}
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="bg-slate-900 border border-slate-800 rounded-xl p-8">
            <h2 className="text-2xl font-semibold mb-4">
              Broker Recommendation Engine
            </h2>

            <div className="space-y-3">
              {data.broker_actions?.map((action: string) => (
                <div
                  key={action}
                  className="bg-blue-500/10 text-blue-300 px-4 py-3 rounded-lg"
                >
                  • {action}
                </div>
              ))}
            </div>
          </section>
        </section>

        <section className="bg-slate-900 border border-slate-800 rounded-xl p-8 mb-8">
          <h2 className="text-2xl font-semibold mb-4">
            Claim Details
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
            <Info label="Date of Loss" value={claim.date_of_loss} />
            <Info label="Claim Type" value={claim.claim_type} />
            <Info label="Cause of Loss" value={claim.cause_of_loss} />
            <Info label="Injury Type" value={claim.injury_type} />
            <Info label="Venue State" value={claim.venue_state} />
            <Info label="Litigation Status" value={claim.litigation_status} />
          </div>

          <h3 className="text-xl font-semibold mb-3">Description</h3>
          <p className="text-slate-300 whitespace-pre-line leading-7">
            {claim.description || "No description available."}
          </p>
        </section>
      </div>
    </main>
  );
}

function Card({ label, value }: { label: string; value: any }) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
      <p className="text-slate-400">{label}</p>
      <h2 className="text-2xl font-bold mt-2 break-words">{value || "-"}</h2>
    </div>
  );
}

function RiskCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "red" | "yellow" | "green";
}) {
  const color =
    tone === "red"
      ? "text-red-400"
      : tone === "yellow"
      ? "text-yellow-400"
      : "text-green-400";

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
      <p className="text-slate-400">{label}</p>
      <h2 className={`text-2xl font-bold mt-2 ${color}`}>
        {value || "-"}
      </h2>
    </div>
  );
}

function Info({ label, value }: { label: string; value: any }) {
  return (
    <div className="bg-slate-800 rounded-lg p-4">
      <p className="text-slate-400 text-sm">{label}</p>
      <p className="text-white font-semibold mt-1">{value || "Needs Review"}</p>
    </div>
  );
}

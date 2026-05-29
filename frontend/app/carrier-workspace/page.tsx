"use client";

import { useState } from "react";

const API =
  process.env.NEXT_PUBLIC_API_URL || "https://lossq-production.up.railway.app";

export default function CarrierWorkspacePage() {
  const [policyNumber, setPolicyNumber] = useState("");
  const [packet, setPacket] = useState<any>(null);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  function authHeaders(): Record<string, string> {
    const token = localStorage.getItem("lossq_token");
    return token ? { Authorization: `Bearer ${token}` } : {};
  }

  async function generatePacket() {
    if (!policyNumber.trim()) {
      setMessage("Enter a policy number first.");
      return;
    }

    setLoading(true);
    setMessage("");
    setPacket(null);

    try {
      const res = await fetch(`${API}/carrier-packet/generate`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify({
          policy_number: policyNumber.trim(),
        }),
      });

      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        setMessage(data.detail || "Could not generate carrier packet.");
        return;
      }

      setPacket(data);
      setMessage("Carrier packet generated.");
    } catch {
      setMessage("Carrier packet request failed.");
    } finally {
      setLoading(false);
    }
  }

async function downloadPdf() {
  if (!policyNumber.trim()) {
    setMessage("Enter a policy number first.");
    return;
  }

  try {
    const res = await fetch(`${API}/carrier-packet/pdf`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(),
      },
      body: JSON.stringify({
        policy_number: policyNumber.trim(),
      }),
    });

    if (!res.ok) {
      setMessage("Could not download PDF packet.");
      return;
    }

    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);

    const a = document.createElement("a");
    a.href = url;
    a.download = `lossq_carrier_packet_${policyNumber.trim()}.pdf`;
    a.click();

    window.URL.revokeObjectURL(url);
  } catch {
    setMessage("PDF download failed.");
  }
}

  return (
    <main className="min-h-screen bg-slate-950 text-white p-10">
      <div className="max-w-7xl mx-auto">
        <div className="flex justify-between items-start mb-10">
          <div>
            <h1 className="text-5xl font-bold">Carrier Workspace</h1>
            <p className="text-slate-400 mt-2">
              Generate broker-ready carrier submission packets from account loss data.
            </p>
          </div>

          <a
            href="/dashboard"
            className="bg-slate-800 hover:bg-slate-700 px-5 py-3 rounded-lg"
          >
            Back to Dashboard
          </a>
        </div>

        <section className="bg-slate-900 border border-slate-800 rounded-2xl p-6 mb-8">
          <h2 className="text-3xl font-semibold mb-5">Generate Carrier Packet</h2>

          <div className="flex flex-col md:flex-row gap-4">
            <input
              value={policyNumber}
              onChange={(e) => setPolicyNumber(e.target.value)}
              placeholder="Enter policy number"
              className="flex-1 bg-slate-800 border border-slate-700 rounded-lg px-4 py-3"
            />

            <button
              onClick={generatePacket}
              disabled={loading}
              className="bg-purple-600 hover:bg-purple-700 disabled:opacity-50 px-6 py-3 rounded-lg font-semibold"
            >
              {loading ? "Generating..." : "Generate Packet"}
            </button>
          </div>

          {message && (
            <div className="mt-5 bg-slate-800 border border-slate-700 rounded-lg p-4 text-slate-300">
              {message}
            </div>
          )}
        </section>
<button
  onClick={downloadPdf}
  disabled={loading}
  className="bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 px-6 py-3 rounded-lg font-semibold"
>
  Download PDF Packet
</button>
        {packet && (
          <>
            <section className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
              <Metric title="Policy" value={packet.policy_number} />
              <Metric title="Renewal Risk" value={packet.renewal_risk} />
              <Metric title="Risk Level" value={packet.risk_level} />
              <Metric title="Submission Strength" value={packet.submission_strength} />
            </section>

            <section className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
              <Metric title="Total Claims" value={packet.claim_metrics?.total_claims} />
              <Metric title="Open Claims" value={packet.claim_metrics?.open_claims} />
              <Metric
                title="Total Incurred"
                value={`$${Number(packet.claim_metrics?.total_incurred || 0).toLocaleString()}`}
              />
            </section>

            <Section title="Account Summary" content={packet.account_summary} />
            <Section title="Reserve Analysis" content={packet.reserve_analysis} />
            <Section title="Litigation Exposure" content={packet.litigation_exposure} />
            <Section title="Broker Strategy" content={packet.broker_strategy} />
            <Section title="Carrier Narrative" content={packet.carrier_narrative} />

            <section className="bg-slate-900 border border-slate-800 rounded-2xl p-6 mb-8">
              <h2 className="text-3xl font-semibold mb-5">Severity Drivers</h2>

              {packet.severity_drivers?.length === 0 ? (
                <p className="text-slate-400">No severity drivers identified.</p>
              ) : (
                <div className="space-y-4">
                  {packet.severity_drivers?.map((claim: any) => (
                    <div
                      key={claim.claim_number}
                      className="bg-slate-800 border border-slate-700 rounded-xl p-5"
                    >
                      <div className="flex justify-between gap-4 mb-2">
                        <h3 className="text-xl font-semibold">
                          Claim {claim.claim_number}
                        </h3>

                        <span className="text-blue-400 font-semibold">
                          ${Number(claim.total_incurred || 0).toLocaleString()}
                        </span>
                      </div>

                      <p className="text-slate-400 text-sm mb-2">
                        {claim.line_of_business || "-"} · {claim.status || "-"}
                      </p>

                      <p className="text-slate-300">
                        {claim.description || "No description available."}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <section className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
              <h2 className="text-3xl font-semibold mb-5">Recommendations</h2>

              <ul className="list-disc pl-6 space-y-3 text-slate-300">
                {packet.recommendations?.map((item: string, index: number) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            </section>
          </>
        )}
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

function Section({ title, content }: { title: string; content: string }) {
  return (
    <section className="bg-slate-900 border border-slate-800 rounded-2xl p-6 mb-8">
      <h2 className="text-3xl font-semibold mb-5">{title}</h2>
      <p className="text-slate-300 leading-8 whitespace-pre-line">
        {content || "No data available."}
      </p>
    </section>
  );
}
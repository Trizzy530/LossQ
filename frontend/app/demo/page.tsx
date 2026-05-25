"use client";

import { useState } from "react";

export default function DemoPage() {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<any>(null);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  const API = "http://127.0.0.1:8000";

  async function analyzeDemo() {
    if (!file) {
      setMessage("Please select a PDF, Excel, or CSV loss run first.");
      return;
    }

    setLoading(true);
    setMessage("Analyzing demo loss run...");
    setResult(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`${API}/demo/analyze`, {
        method: "POST",
        body: formData,
      });

      const data = await res.json();

      if (!res.ok) {
        setMessage(`Demo failed: ${JSON.stringify(data)}`);
        return;
      }

      setResult(data);
      setMessage("Demo analysis complete.");
    } catch (error: any) {
      setMessage(`Demo failed: ${error.message}`);
    } finally {
      setLoading(false);
    }
  }

  const analysis = result?.analysis;

  return (
    <main className="min-h-screen bg-slate-950 text-white p-8">
      <div className="max-w-6xl mx-auto">
        <header className="mb-10 flex justify-between items-start">
          <div>
            <div className="inline-flex items-center gap-3 mb-3">
              <div className="h-10 w-10 rounded-xl bg-blue-600 flex items-center justify-center font-bold">
                LQ
              </div>
              <span className="text-slate-400 text-sm">
                Instant Demo Mode
              </span>
            </div>

            <h1 className="text-5xl font-bold">Try LossQ Instantly</h1>

            <p className="text-slate-300 mt-3 max-w-2xl">
              Upload a sample loss run and receive instant underwriting intelligence.
              No login required. Demo uploads are analyzed only and are not saved
              to your broker dashboard.
            </p>
          </div>

          <div className="flex gap-3">
            <a
              href="/login"
              className="rounded-lg bg-slate-800 px-4 py-2 text-sm hover:bg-slate-700"
            >
              Login
            </a>

            <a
              href="/"
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm hover:bg-blue-700"
            >
              Dashboard
            </a>
          </div>
        </header>

        <section className="bg-slate-900 rounded-xl border border-slate-800 p-6 mb-10">
          <h2 className="text-2xl font-semibold mb-2">
            Upload Sample Loss Run
          </h2>

          <p className="text-slate-400 mb-4">
            Supported files: PDF, Excel, CSV.
          </p>

          <div className="flex flex-col md:flex-row gap-4 items-center">
            <input
              type="file"
              accept=".pdf,.xlsx,.csv"
              onChange={(event) => setFile(event.target.files?.[0] || null)}
              className="text-sm text-slate-300 file:mr-4 file:rounded-lg file:border-0 file:bg-blue-600 file:px-4 file:py-2 file:text-white"
            />

            <button
              onClick={analyzeDemo}
              disabled={loading}
              className="rounded-lg bg-blue-600 px-5 py-2 font-semibold hover:bg-blue-700 disabled:opacity-50"
            >
              {loading ? "Analyzing..." : "Analyze Instantly"}
            </button>
          </div>

          {message && (
            <p className="mt-4 text-sm text-slate-300">
              {message}
            </p>
          )}
        </section>

        {analysis && (
          <>
            <section className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-10">
              <Card label="Claims Found" value={result.claims_found} />
              <Card label="Risk Level" value={analysis.risk_level} />
              <Card label="Renewal Risk" value={analysis.renewal_risk} />
              <Card label="Risk Score" value={analysis.risk_score} />
            </section>

            <section className="bg-slate-900 rounded-xl border border-slate-800 p-6 mb-10">
              <h2 className="text-2xl font-semibold mb-4">
                Instant AI Underwriting Summary
              </h2>

              <p className="text-slate-300 mb-4">
                {analysis.summary}
              </p>

              <p className="text-slate-400 mb-6">
                {analysis.recommendation}
              </p>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="bg-slate-800 rounded-xl p-4">
                  <h3 className="text-lg font-semibold mb-2">
                    Carrier-Facing Broker Narrative
                  </h3>
                  <p className="text-slate-300">
                    {analysis.carrier_narrative}
                  </p>
                </div>

                <div className="bg-slate-800 rounded-xl p-4">
                  <h3 className="text-lg font-semibold mb-2">
                    Client-Facing Narrative
                  </h3>
                  <p className="text-slate-300">
                    {analysis.client_narrative}
                  </p>
                </div>
              </div>
            </section>

            <section className="bg-slate-900 rounded-xl border border-slate-800 p-6 mb-10">
              <h2 className="text-2xl font-semibold mb-4">
                Submission Readiness
              </h2>

              <p className="text-slate-400 text-sm">Submission Strength</p>

              <p
                className={`text-3xl font-bold mb-6 ${
                  analysis.submission_strength === "Weak"
                    ? "text-red-400"
                    : analysis.submission_strength === "Moderate"
                    ? "text-yellow-400"
                    : "text-green-400"
                }`}
              >
                {analysis.submission_strength}
              </p>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <h3 className="font-semibold mb-3">Missing Items</h3>

                  {analysis.missing_items?.length === 0 ? (
                    <p className="text-slate-400">
                      No major missing items detected.
                    </p>
                  ) : (
                    <ul className="space-y-2">
                      {analysis.missing_items?.map((item: string) => (
                        <li
                          key={item}
                          className="bg-red-500/10 text-red-300 px-3 py-2 rounded-lg"
                        >
                          • {item}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                <div>
                  <h3 className="font-semibold mb-3">
                    Recommended Actions
                  </h3>

                  {analysis.recommended_actions?.length === 0 ? (
                    <p className="text-slate-400">
                      No major recommendations at this time.
                    </p>
                  ) : (
                    <ul className="space-y-2">
                      {analysis.recommended_actions?.map((action: string) => (
                        <li
                          key={action}
                          className="bg-blue-500/10 text-blue-300 px-3 py-2 rounded-lg"
                        >
                          • {action}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            </section>

            <section className="bg-slate-900 rounded-xl border border-slate-800 overflow-hidden">
              <div className="p-6 border-b border-slate-800">
                <h2 className="text-2xl font-semibold">
                  Parsed Demo Claims
                </h2>

                <p className="text-slate-400 mt-1">
                  Preview of claims extracted from your sample file.
                </p>
              </div>

              <table className="w-full text-left">
                <thead className="bg-slate-800 text-slate-300">
                  <tr>
                    <th className="p-4">Claim #</th>
                    <th className="p-4">Line</th>
                    <th className="p-4">Status</th>
                    <th className="p-4">Paid</th>
                    <th className="p-4">Reserve</th>
                    <th className="p-4">Total</th>
                    <th className="p-4">Flag</th>
                  </tr>
                </thead>

                <tbody>
                  {result.claims?.map((claim: any, index: number) => (
                    <tr key={index} className="border-t border-slate-800">
                      <td className="p-4">{claim.claim_number}</td>
                      <td className="p-4">{claim.line_of_business}</td>
                      <td className="p-4">{claim.status}</td>
                      <td className="p-4">
                        ${Number(claim.paid_amount || 0).toLocaleString()}
                      </td>
                      <td className="p-4">
                        ${Number(claim.reserve_amount || 0).toLocaleString()}
                      </td>
                      <td className="p-4">
                        ${Number(claim.total_incurred || 0).toLocaleString()}
                      </td>
                      <td className="p-4">
                        {claim.flag ? (
                          <span className="text-red-400">
                            {claim.flag}
                          </span>
                        ) : (
                          <span className="text-slate-400">None</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          </>
        )}
      </div>
    </main>
  );
}

function Card({ label, value }: { label: string; value: any }) {
  return (
    <div className="bg-slate-900 rounded-xl p-6 border border-slate-800">
      <p className="text-slate-400">{label}</p>
      <h2 className="text-3xl font-bold mt-2">{value}</h2>
    </div>
  );
}
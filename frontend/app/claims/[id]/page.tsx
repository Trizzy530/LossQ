"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";

const API =
  process.env.NEXT_PUBLIC_API_URL || "https://lossq-production.up.railway.app";

type AnyObject = Record<string, any>;

async function safeJson(res: Response) {
  try {
    return await res.json();
  } catch {
    return null;
  }
}

function money(value: any) {
  const numberValue = Number(value || 0);
  return `$${numberValue.toLocaleString()}`;
}

function clean(value: any) {
  if (value === null || value === undefined || value === "") return "-";
  return String(value);
}

function FieldCard({ label, value }: { label: string; value: any }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-slate-950/60 p-4">
      <p className="text-xs uppercase tracking-[0.25em] text-blue-300 mb-2">
        {label}
      </p>
      <p className="text-white font-semibold break-words">{clean(value)}</p>
    </div>
  );
}

export default function ClaimDetailPage() {
  const router = useRouter();
  const params = useParams();

  const claimId = String(params?.id || "");

  const [claim, setClaim] = useState<AnyObject | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");

  function getToken() {
    if (typeof window === "undefined") return null;
    return localStorage.getItem("lossq_token");
  }

  function authHeaders(): Record<string, string> {
    const token = getToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  }

  function backToClaimsTab() {
    router.back();
  }

  useEffect(() => {
    async function loadClaim() {
      const token = getToken();

      if (!token) {
        router.replace("/login?fresh=1");
        return;
      }

      if (!claimId) {
        setMessage("No claim ID found.");
        setLoading(false);
        return;
      }

      try {
        setLoading(true);
        setMessage("");

        const res = await fetch(`${API}/claims/${encodeURIComponent(claimId)}`, {
          headers: authHeaders(),
        });

        if (res.status === 401 || res.status === 403) {
          localStorage.removeItem("lossq_token");
          localStorage.removeItem("lossq_user");
          localStorage.removeItem("lossq_login_time");
          router.replace("/login?expired=1");
          return;
        }

        const data = await safeJson(res);

        if (!res.ok) {
          setMessage(`Claim could not be loaded. Backend returned ${res.status}.`);
          setClaim(null);
          return;
        }

        if (!data || typeof data !== "object") {
          setMessage("Claim could not be loaded. No claim data returned.");
          setClaim(null);
          return;
        }

        setClaim(data);
      } catch (error: any) {
        setMessage(
          `Claim could not be loaded. ${error?.message || "Unknown error"}`
        );
        setClaim(null);
      } finally {
        setLoading(false);
      }
    }

    loadClaim();
  }, [claimId]);

  if (loading) {
    return (
      <main className="min-h-screen bg-[#020617] text-white flex items-center justify-center px-6">
        <div className="text-center">
          <div className="mx-auto mb-5 h-12 w-12 animate-spin rounded-full border-4 border-blue-400/30 border-t-blue-400" />
          <h1 className="text-3xl font-bold">Loading Claim...</h1>
          <p className="text-slate-400 mt-2">Pulling claim analysis data.</p>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#020617] text-white overflow-hidden">
      <div className="fixed inset-0 bg-[radial-gradient(circle_at_top_left,#1d4ed866,transparent_28%),radial-gradient(circle_at_top_right,#0ea5e955,transparent_30%),radial-gradient(circle_at_bottom,#312e8155,transparent_35%)]" />
      <div className="fixed inset-0 bg-[linear-gradient(to_right,rgba(255,255,255,0.04)_1px,transparent_1px),linear-gradient(to_bottom,rgba(255,255,255,0.04)_1px,transparent_1px)] bg-[size:72px_72px] opacity-20" />

      <section className="relative max-w-7xl mx-auto px-5 md:px-8 py-8 pb-20">
        <div className="mb-8">
          <button
            onClick={backToClaimsTab}
            className="mb-5 rounded-2xl border border-white/10 bg-white/5 px-5 py-3 text-sm font-semibold text-slate-200 hover:bg-white/10"
          >
            ← Back to Claims Tab
          </button>

          <p className="text-sm uppercase tracking-[0.35em] text-blue-300 mb-3">
            Claim Analysis
          </p>

          <h1 className="text-4xl md:text-6xl font-black tracking-tight">
            {clean(claim?.claim_number || claim?.id || claimId)}
          </h1>

          <p className="text-slate-300 mt-3 max-w-3xl">
            Individual claim detail, financials, status, and underwriting notes.
          </p>
        </div>

        {message && (
          <div className="mb-6 rounded-3xl border border-red-400/30 bg-red-500/10 p-5 text-red-100">
            {message}
          </div>
        )}

        {!claim && !message && (
          <div className="rounded-3xl border border-white/10 bg-white/10 p-8">
            No claim data found.
          </div>
        )}

        {claim && (
          <>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
              <section className="lg:col-span-2 rounded-3xl border border-white/10 bg-white/10 backdrop-blur-xl p-6 md:p-8">
                <h2 className="text-2xl font-bold mb-6">Claim Overview</h2>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <FieldCard
                    label="Claim Number"
                    value={claim.claim_number || claim.claimNo || claim.number}
                  />
                  <FieldCard
                    label="Policy Number"
                    value={claim.policy_number || claim.policyNumber}
                  />
                  <FieldCard
                    label="Line of Business"
                    value={
                      claim.line_of_business ||
                      claim.lob ||
                      claim.coverage ||
                      claim.policy_type
                    }
                  />
                  <FieldCard label="Status" value={claim.status} />
                  <FieldCard
                    label="Loss Date"
                    value={claim.loss_date || claim.date_of_loss}
                  />
                  <FieldCard
                    label="Reported Date"
                    value={claim.reported_date || claim.report_date}
                  />
                  <FieldCard
                    label="Claimant"
                    value={claim.claimant || claim.claimant_name}
                  />
                  <FieldCard
                    label="Cause of Loss"
                    value={claim.cause_of_loss || claim.loss_description}
                  />
                </div>
              </section>

              <section className="rounded-3xl border border-white/10 bg-white/10 backdrop-blur-xl p-6 md:p-8">
                <h2 className="text-2xl font-bold mb-6">Financials</h2>

                <div className="grid grid-cols-1 gap-4">
                  <FieldCard
                    label="Paid"
                    value={money(claim.paid_amount || claim.paid || claim.total_paid)}
                  />
                  <FieldCard
                    label="Reserve"
                    value={money(
                      claim.reserve_amount || claim.reserve || claim.total_reserved
                    )}
                  />
                  <FieldCard
                    label="Total Incurred"
                    value={money(
                      claim.total_incurred ||
                        claim.incurred ||
                        Number(claim.paid_amount || claim.paid || 0) +
                          Number(claim.reserve_amount || claim.reserve || 0)
                    )}
                  />
                </div>
              </section>
            </div>

            <section className="rounded-3xl border border-white/10 bg-white/10 backdrop-blur-xl p-6 md:p-8 mb-6">
              <h2 className="text-2xl font-bold mb-5">Underwriting Notes</h2>

              <div className="rounded-2xl border border-white/10 bg-slate-950/60 p-5 text-slate-300 leading-7">
                {claim.underwriting_notes ||
                  claim.notes ||
                  claim.description ||
                  claim.loss_description ||
                  "No underwriting notes are available for this claim yet."}
              </div>
            </section>

            <section className="rounded-3xl border border-white/10 bg-white/10 backdrop-blur-xl p-6 md:p-8">
              <h2 className="text-2xl font-bold mb-5">Raw Claim Data</h2>

              <div className="max-h-[420px] overflow-auto rounded-2xl border border-white/10 bg-slate-950/70 p-5">
                <pre className="text-sm text-slate-300 whitespace-pre-wrap">
                  {JSON.stringify(claim, null, 2)}
                </pre>
              </div>
            </section>
          </>
        )}
      </section>
    </main>
  );
}
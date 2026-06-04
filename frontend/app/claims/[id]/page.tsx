"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";

const API =
  process.env.NEXT_PUBLIC_API_URL || "https://lossq-production.up.railway.app";

const SESSION_TIMEOUT_MS = 1000 * 60 * 60 * 24;

type AnyObject = Record<string, any>;

async function safeJson(res: Response) {
  try {
    return await res.json();
  } catch {
    return null;
  }
}

function formatMoney(value: any) {
  const number = Number(value || 0);
  return `$${number.toLocaleString()}`;
}

function display(value: any) {
  if (value === null || value === undefined || value === "") return "-";
  return String(value);
}

export default function ClaimDetailPage() {
  const router = useRouter();
  const params = useParams();
  const claimId = String(params?.id || "");

  const [claim, setClaim] = useState<AnyObject | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadClaim() {
      const token = localStorage.getItem("lossq_token");
      const loginTime = localStorage.getItem("lossq_login_time");

      if (!token) {
        router.replace("/login?fresh=1");
        return;
      }

      if (loginTime && Date.now() - Number(loginTime) > SESSION_TIMEOUT_MS) {
        clearSession();
        router.replace("/login?expired=1");
        return;
      }

      if (!claimId) {
        setError("Claim ID was not found in the route.");
        setLoading(false);
        return;
      }

      try {
        setLoading(true);
        setError("");

        const res = await fetch(`${API}/claims/${encodeURIComponent(claimId)}`, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });

        if (res.status === 401 || res.status === 403) {
          clearSession();
          router.replace("/login?expired=1");
          return;
        }

        const data = await safeJson(res);

        if (!res.ok) {
          setError(
            `Could not load claim. Backend returned ${res.status}: ${JSON.stringify(data)}`
          );
          setClaim(null);
          return;
        }

        setClaim(data || null);
      } catch (err: any) {
        setError(
          `Could not load claim. Backend may be unavailable. Error: ${err?.message || "Unknown error"}`
        );
        setClaim(null);
      } finally {
        setLoading(false);
      }
    }

    loadClaim();
  }, [claimId, router]);

  function clearSession() {
    localStorage.removeItem("lossq_token");
    localStorage.removeItem("lossq_user");
    localStorage.removeItem("lossq_login_time");
    sessionStorage.removeItem("lossq_welcome");
  }

  function goBackToClaims() {
    router.push("/claims");
  }

  function goBackToDashboardClaimsTab() {
    router.push("/dashboard?tool=claims");
  }

  if (loading) {
    return (
      <main className="min-h-screen bg-[#020617] text-white flex items-center justify-center px-6">
        <div className="rounded-3xl border border-white/10 bg-white/10 backdrop-blur-xl p-8 text-center shadow-2xl">
          <div className="mx-auto mb-5 h-12 w-12 animate-spin rounded-full border-4 border-blue-400 border-t-transparent" />
          <h1 className="text-2xl font-bold">Loading Claim...</h1>
          <p className="mt-2 text-slate-400">Preparing individual claim analysis.</p>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#020617] text-white overflow-hidden">
      <div className="fixed inset-0 bg-[radial-gradient(circle_at_top_left,#1d4ed866,transparent_28%),radial-gradient(circle_at_top_right,#0ea5e955,transparent_30%),radial-gradient(circle_at_bottom,#312e8155,transparent_35%)]" />
      <div className="fixed inset-0 bg-[linear-gradient(to_right,rgba(255,255,255,0.04)_1px,transparent_1px),linear-gradient(to_bottom,rgba(255,255,255,0.04)_1px,transparent_1px)] bg-[size:72px_72px] opacity-20" />

      <section className="relative mx-auto max-w-6xl px-5 py-8 md:px-8">
        <div className="mb-6 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <button
              type="button"
              onClick={goBackToClaims}
              className="mb-5 inline-flex items-center rounded-2xl border border-blue-400/30 bg-blue-500/10 px-4 py-2 text-sm font-semibold text-blue-200 hover:bg-blue-500/20"
            >
              ← Back to Claims
            </button>

            <p className="text-sm uppercase tracking-[0.25em] text-blue-300">
              Claim Analysis
            </p>
            <h1 className="mt-3 text-4xl font-black tracking-tight md:text-5xl">
              {display(claim?.claim_number || claim?.id || claimId)}
            </h1>
            <p className="mt-3 max-w-2xl text-slate-300">
              Individual claim detail, financials, status, and underwriting notes.
            </p>
          </div>

          <div className="flex flex-wrap gap-3">
            <button type="button" onClick={goBackToClaims} className="btn-primary">
              Main Claims Page
            </button>
            <button
              type="button"
              onClick={goBackToDashboardClaimsTab}
              className="btn-secondary"
            >
              Dashboard Claims Tab
            </button>
          </div>
        </div>

        {error && (
          <div className="mb-6 rounded-3xl border border-red-400/30 bg-red-500/10 p-5 text-red-100">
            {error}
          </div>
        )}

        {!error && claim && (
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            <section className="glass-panel p-6 lg:col-span-2">
              <h2 className="mb-5 text-2xl font-bold">Claim Overview</h2>

              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <Detail label="Claim Number" value={claim.claim_number} />
                <Detail label="Policy Number" value={claim.policy_number} />
                <Detail label="Line of Business" value={claim.line_of_business || claim.coverage || claim.lob} />
                <Detail label="Status" value={claim.status} />
                <Detail label="Loss Date" value={claim.loss_date || claim.date_of_loss} />
                <Detail label="Reported Date" value={claim.reported_date || claim.date_reported} />
                <Detail label="Claimant" value={claim.claimant || claim.claimant_name} />
                <Detail label="Cause of Loss" value={claim.cause_of_loss || claim.loss_description} />
              </div>
            </section>

            <section className="glass-panel p-6">
              <h2 className="mb-5 text-2xl font-bold">Financials</h2>

              <div className="space-y-4">
                <Detail label="Paid" value={formatMoney(claim.paid_amount || claim.paid)} />
                <Detail label="Reserve" value={formatMoney(claim.reserve_amount || claim.reserve)} />
                <Detail
                  label="Total Incurred"
                  value={formatMoney(
                    claim.total_incurred ||
                      claim.incurred ||
                      Number(claim.paid_amount || claim.paid || 0) +
                        Number(claim.reserve_amount || claim.reserve || 0)
                  )}
                />
              </div>
            </section>

            <section className="glass-panel p-6 lg:col-span-3">
              <h2 className="mb-5 text-2xl font-bold">Underwriting Notes</h2>
              <div className="rounded-2xl border border-white/10 bg-slate-950/60 p-5 text-slate-300 leading-7">
                {display(
                  claim.underwriting_notes ||
                    claim.notes ||
                    claim.summary ||
                    claim.description ||
                    "No underwriting notes are available for this claim yet."
                )}
              </div>
            </section>

            <section className="glass-panel p-6 lg:col-span-3">
              <h2 className="mb-5 text-2xl font-bold">Raw Claim Data</h2>
              <pre className="max-h-[420px] overflow-auto rounded-2xl border border-white/10 bg-slate-950/70 p-5 text-xs leading-6 text-slate-300">
                {JSON.stringify(claim, null, 2)}
              </pre>
            </section>
          </div>
        )}
      </section>

      <style jsx global>{`
        .glass-panel {
          border: 1px solid rgba(255, 255, 255, 0.1);
          background: rgba(15, 23, 42, 0.72);
          backdrop-filter: blur(22px);
          border-radius: 1.5rem;
          box-shadow: 0 24px 80px rgba(15, 23, 42, 0.45);
        }

        .btn-primary,
        .btn-secondary {
          border-radius: 1rem;
          padding: 0.8rem 1.1rem;
          font-weight: 800;
          transition: 0.2s ease;
        }

        .btn-primary {
          background: linear-gradient(135deg, #2563eb, #06b6d4);
          color: white;
          box-shadow: 0 14px 35px rgba(37, 99, 235, 0.28);
        }

        .btn-primary:hover {
          transform: translateY(-1px);
          box-shadow: 0 18px 45px rgba(37, 99, 235, 0.38);
        }

        .btn-secondary {
          border: 1px solid rgba(255, 255, 255, 0.12);
          background: rgba(255, 255, 255, 0.07);
          color: white;
        }

        .btn-secondary:hover {
          background: rgba(255, 255, 255, 0.12);
        }
      `}</style>
    </main>
  );
}

function Detail({ label, value }: { label: string; value: any }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-slate-950/50 p-4">
      <div className="text-xs uppercase tracking-[0.22em] text-blue-300">{label}</div>
      <div className="mt-2 font-semibold text-white">{display(value)}</div>
    </div>
  );
}
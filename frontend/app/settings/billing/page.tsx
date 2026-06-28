"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_URL || "https://lossq-production.up.railway.app";

type BillingStatus = {
  plan?: string;
  subscription_plan?: string;
  plan_name?: string;
  subscription_status?: string;
  status?: string;
  billing_status?: string;
  plan_limits?: {
    label?: string;
    features?: string[];
  };
  features?: string[];
  organization?: {
    plan?: string;
    subscription_status?: string;
    current_period_end?: string | null;
  };
  current_period_end?: string | null;
};

async function safeJson(res: Response) {
  try {
    return await res.json();
  } catch {
    return null;
  }
}

function normalizePlan(plan: any) {
  const clean = String(plan || "free").trim().toLowerCase();
  if (clean === "pro") return "professional";
  if (clean === "enterprise") return "agency";
  if (clean === "founder" || clean === "founding" || clean === "founding agency") return "founding_agency";
  return clean || "free";
}

function planLabel(plan: any) {
  const clean = normalizePlan(plan);
  if (clean === "starter") return "Starter";
  if (clean === "professional") return "Professional";
  if (clean === "agency") return "Agency";
  if (clean === "founding_agency") return "Founding Agency";
  return "Free / Trial";
}

function statusLabel(status: any) {
  const clean = String(status || "inactive").trim().toLowerCase();
  if (clean === "active") return "Active";
  if (clean === "paid") return "Paid";
  if (clean === "canceling") return "Canceling";
  if (clean === "cancelled" || clean === "canceled") return "Cancelled";
  if (clean === "trialing") return "Trialing";
  return clean || "Inactive";
}

export default function BillingSettingsPage() {
  const router = useRouter();

  const [billing, setBilling] = useState<BillingStatus>({});
  const [loading, setLoading] = useState(true);
  const [workingPlan, setWorkingPlan] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  function getToken() {
    if (typeof window === "undefined") return null;
    return localStorage.getItem("lossq_token");
  }

  function authHeaders(): Record<string, string> {
    const token = getToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  }

  function logout() {
    localStorage.removeItem("lossq_token");
    localStorage.removeItem("lossq_user");
    localStorage.removeItem("lossq_login_time");
    sessionStorage.removeItem("lossq_welcome");
    router.replace("/login?fresh=1");
  }

  async function loadBilling() {
    setLoading(true);
    setError("");
    setMessage("");

    try {
      if (!getToken()) {
        router.replace("/login?fresh=1");
        return;
      }

      const res = await fetch(`${API}/billing/status`, {
        headers: authHeaders(),
      });

      if (res.status === 401 || res.status === 403) {
        logout();
        return;
      }

      const data = res.ok ? ((await safeJson(res)) || {}) : {};
      setBilling(data);
    } catch (err: any) {
      setError(err?.message || "Could not load billing status.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadBilling();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function startCheckout(plan: string) {
    setWorkingPlan(plan);
    setError("");
    setMessage("");

    try {
      const res = await fetch(`${API}/billing/checkout`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify({ plan }),
      });

      const data = await safeJson(res);

      if (!res.ok) {
        throw new Error(data?.detail || "Could not start billing checkout.");
      }

      const checkoutUrl =
        data?.url ||
        data?.checkout_url ||
        data?.session_url ||
        data?.redirect_url;

      if (!checkoutUrl) {
        throw new Error("Checkout link was not returned by billing.");
      }

      // LOSSQ_SETTINGS_BILLING_POST_PAYMENT_ONBOARDING_FLAG_V1
      try {
        localStorage.setItem("lossq_pending_paid_onboarding", "true");
        sessionStorage.setItem("lossq_pending_paid_onboarding", "true");
        sessionStorage.setItem("lossq_next_after_onboarding", "/dashboard?welcome=1");
      } catch {}

      window.location.href = checkoutUrl;
    } catch (err: any) {
      setError(err?.message || "Could not start checkout.");
    } finally {
      setWorkingPlan("");
    }
  }

  async function endSubscription() {
    setError("");
    setMessage("");

    const confirmed = window.confirm(
      "End this LossQ subscription? This will not delete your account, users, profiles, uploads, claims, or reports. It only changes subscription access."
    );

    if (!confirmed) return;

    setWorkingPlan("cancel");

    try {
      const res = await fetch(`${API}/billing/cancel-subscription`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
      });

      const data = await safeJson(res);

      if (!res.ok) {
        throw new Error(data?.detail || "Could not end subscription.");
      }

      setMessage(data?.message || "Subscription cancellation request processed.");
      await loadBilling();
    } catch (err: any) {
      setError(err?.message || "Could not end subscription.");
    } finally {
      setWorkingPlan("");
    }
  }

  const currentPlan =
    billing?.plan ||
    billing?.subscription_plan ||
    billing?.plan_name ||
    billing?.organization?.plan ||
    "free";

  const currentStatus =
    billing?.subscription_status ||
    billing?.status ||
    billing?.billing_status ||
    billing?.organization?.subscription_status ||
    "inactive";

  const currentPeriodEnd =
    billing?.current_period_end ||
    billing?.organization?.current_period_end ||
    null;

  const features = Array.isArray(billing?.features)
    ? billing.features
    : Array.isArray(billing?.plan_limits?.features)
    ? billing.plan_limits.features
    : [];

  const upgradePlans = [
    {
      key: "starter",
      name: "Starter",
      note: "Entry package for account profiles, uploads, summaries, memos, and PDF exports.",
    },
    {
      key: "professional",
      name: "Professional",
      note: "Best for full underwriting workflow, renewal intelligence, charts, premium forecast, and carrier packets.",
    },
    {
      key: "agency",
      name: "Agency",
      note: "Adds advanced agency controls, audit logs, team management, and expanded permissions.",
    },
    {
      key: "founding_agency",
      name: "Founding Agency",
      note: "Founding tier for early agencies that need the full LossQ platform.",
    },
  ];

  return (
    <main className="min-h-screen bg-[#050816] text-white px-6 py-8">
      <div className="mx-auto max-w-6xl">
        <div className="mb-8 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.3em] text-cyan-300">
              LossQ Settings
            </p>
            <h1 className="mt-2 text-3xl md:text-4xl font-black">
              Billing & Subscription
            </h1>
            <p className="mt-2 text-slate-400">
              Manage your package, upgrade your plan, or end your LossQ subscription.
            </p>
          </div>

          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => router.push("/settings")}
              className="rounded-xl border border-white/15 px-5 py-3 font-bold text-white hover:bg-white/10"
            >
              Back to Settings
            </button>

            <button
              type="button"
              onClick={() => router.push("/dashboard")}
              className="rounded-xl bg-cyan-400 px-5 py-3 font-bold text-slate-950 hover:bg-cyan-300"
            >
              Dashboard
            </button>
          </div>
        </div>

        {loading && (
          <section className="rounded-3xl border border-white/10 bg-slate-950/80 p-8">
            <p className="text-slate-300">Loading billing status...</p>
          </section>
        )}

        {!loading && (
          <>
            {message && (
              <div className="mb-6 rounded-2xl border border-emerald-400/30 bg-emerald-400/10 p-4 text-emerald-100">
                {message}
              </div>
            )}

            {error && (
              <div className="mb-6 rounded-2xl border border-red-400/30 bg-red-500/10 p-4 text-red-100">
                {error}
              </div>
            )}

            <section className="mb-8 grid grid-cols-1 md:grid-cols-3 gap-5">
              <div className="rounded-3xl border border-white/10 bg-slate-950/80 p-6">
                <p className="text-sm text-slate-400">Current Package</p>
                <p className="mt-2 text-3xl font-black">{planLabel(currentPlan)}</p>
              </div>

              <div className="rounded-3xl border border-white/10 bg-slate-950/80 p-6">
                <p className="text-sm text-slate-400">Subscription Status</p>
                <p className="mt-2 text-3xl font-black">{statusLabel(currentStatus)}</p>
              </div>

              <div className="rounded-3xl border border-white/10 bg-slate-950/80 p-6">
                <p className="text-sm text-slate-400">Current Period End</p>
                <p className="mt-2 text-2xl font-black">
                  {currentPeriodEnd ? new Date(currentPeriodEnd).toLocaleDateString() : "Not Set"}
                </p>
              </div>
            </section>

            <section className="mb-8 rounded-3xl border border-cyan-400/20 bg-cyan-400/10 p-6">
              <h2 className="text-2xl font-black mb-2">Upgrade Plan</h2>
              <p className="text-slate-300 mb-6">
                Select a package below. You will be redirected to secure checkout.
              </p>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                {upgradePlans.map((plan) => (
                  <div
                    key={plan.key}
                    className="rounded-3xl border border-white/10 bg-slate-950/70 p-6"
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <h3 className="text-xl font-black">{plan.name}</h3>
                        <p className="mt-2 text-sm leading-6 text-slate-400">{plan.note}</p>
                      </div>

                      {normalizePlan(currentPlan) === plan.key && (
                        <span className="rounded-full border border-emerald-400/30 bg-emerald-400/10 px-3 py-1 text-xs font-bold text-emerald-200">
                          Current
                        </span>
                      )}
                    </div>

                    <button
                      type="button"
                      onClick={() => startCheckout(plan.key)}
                      disabled={workingPlan !== ""}
                      className="mt-5 w-full rounded-xl bg-cyan-400 px-5 py-3 font-bold text-slate-950 hover:bg-cyan-300 disabled:opacity-50"
                    >
                      {workingPlan === plan.key ? "Opening Checkout..." : `Choose ${plan.name}`}
                    </button>
                  </div>
                ))}
              </div>
            </section>

            <section className="mb-8 rounded-3xl border border-white/10 bg-slate-950/80 p-6">
              <h2 className="text-2xl font-black mb-2">Included Features</h2>
              <p className="text-slate-400 mb-4">
                These are the features currently returned for your package.
              </p>

              {features.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {features.map((feature) => (
                    <span
                      key={feature}
                      className="rounded-full border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-200"
                    >
                      {String(feature).replaceAll("_", " ")}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-slate-400">No package feature list returned yet.</p>
              )}
            </section>

            <section className="rounded-3xl border border-red-400/30 bg-red-500/10 p-6">
              <h2 className="text-2xl font-black text-red-100 mb-2">
                End Subscription
              </h2>
              <p className="text-red-100/80 leading-6">
                Ending a subscription does not delete your LossQ account, users, profiles,
                uploads, claims, reports, or audit history. It only changes subscription access.
              </p>

              <button
                type="button"
                onClick={endSubscription}
                disabled={workingPlan !== ""}
                className="mt-5 rounded-xl border border-red-400/40 px-5 py-3 font-bold text-red-100 hover:bg-red-500/20 disabled:opacity-50"
              >
                {workingPlan === "cancel" ? "Processing..." : "End Subscription"}
              </button>
            </section>
          </>
        )}
      </div>
    </main>
  );
}

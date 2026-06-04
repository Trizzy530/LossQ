"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

const API =
  process.env.NEXT_PUBLIC_API_URL || "https://lossq-production.up.railway.app";

type PlanKey = "starter" | "professional" | "agency" | "founding_agency";

type BillingStatus = {
  plan?: string;
  subscription_status?: string;
  user_limit?: number;
  upload_limit?: number;
  founding_slots_remaining?: number;
  is_billing_admin?: boolean;
};

const plans: Array<{
  key: PlanKey;
  name: string;
  price: string;
  description: string;
  badge?: string;
  features: string[];
  cta: string;
}> = [
  {
    key: "starter",
    name: "Starter",
    price: "$199",
    description: "For independent brokers, solo producers, and small agencies.",
    features: [
      "1 user",
      "50 uploads/month",
      "Loss run uploads",
      "Claims extraction",
      "AI summaries",
      "Renewal memos",
      "Renewal scoring",
      "PDF exports",
    ],
    cta: "Start Starter",
  },
  {
    key: "professional",
    name: "Professional",
    price: "$499",
    description: "For commercial lines teams and growing agencies.",
    badge: "Recommended",
    features: [
      "5 users",
      "Unlimited uploads",
      "Advanced renewal scoring",
      "Carrier appetite analysis",
      "Enhanced AI insights",
      "Team collaboration",
      "Priority support",
      "Advanced reporting",
    ],
    cta: "Start Professional",
  },
  {
    key: "agency",
    name: "Agency",
    price: "$999",
    description: "For multi-user agencies, agency owners, and regional agencies.",
    features: [
      "25 users",
      "Unlimited uploads",
      "Team management",
      "User permissions",
      "Audit logs",
      "White-label reporting later",
      "Advanced analytics",
      "Account management tools",
    ],
    cta: "Start Agency",
  },
  {
    key: "founding_agency",
    name: "Founding Agency",
    price: "$199",
    description: "Locked-in founder pricing for the first agencies that help shape LossQ.",
    badge: "Limited",
    features: [
      "5 users",
      "Unlimited uploads",
      "Locked-in pricing",
      "Priority support",
      "Early feature access",
      "Roadmap influence",
      "Founder recognition",
    ],
    cta: "Claim Founder Pricing",
  },
];

export default function PricingPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [billing, setBilling] = useState<BillingStatus>({});
  const [message, setMessage] = useState("");
  const [loadingPlan, setLoadingPlan] = useState<PlanKey | "">("");
  const [loadingPortal, setLoadingPortal] = useState(false);

  const token = useMemo(() => {
    if (typeof window === "undefined") return null;
    return localStorage.getItem("lossq_token");
  }, []);

  useEffect(() => {
    const cancelled = searchParams.get("billing") === "cancelled";
    if (cancelled) setMessage("Checkout was cancelled. You can choose a plan when ready.");
    loadBilling();
  }, []);

  function authHeaders(): Record<string, string> {
    const storedToken =
      typeof window !== "undefined" ? localStorage.getItem("lossq_token") : token;
    return storedToken ? { Authorization: `Bearer ${storedToken}` } : {};
  }

  async function safeJson(res: Response) {
    try {
      return await res.json();
    } catch {
      return null;
    }
  }

  async function loadBilling() {
    if (!localStorage.getItem("lossq_token")) {
      setMessage("Log in first, then choose a plan for your LossQ account.");
      return;
    }

    try {
      const res = await fetch(`${API}/billing/status`, { headers: authHeaders() });
      const data = await safeJson(res);
      if (res.ok) setBilling(data || {});
    } catch {
      setMessage("Billing status unavailable right now.");
    }
  }

  async function startCheckout(plan: PlanKey) {
    if (!localStorage.getItem("lossq_token")) {
      router.push("/login?fresh=1");
      return;
    }

    setLoadingPlan(plan);
    setMessage("");

    try {
      const res = await fetch(`${API}/billing/create-checkout-session`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify({ plan }),
      });

      const data = await safeJson(res);

      if (!res.ok) {
        setMessage(data?.detail || "Could not start checkout.");
        return;
      }

      if (data?.checkout_url) {
        window.location.href = data.checkout_url;
        return;
      }

      setMessage("Stripe checkout URL was not returned.");
    } catch {
      setMessage("Checkout failed. Please try again.");
    } finally {
      setLoadingPlan("");
    }
  }

  async function manageBilling() {
    if (!localStorage.getItem("lossq_token")) {
      router.push("/login?fresh=1");
      return;
    }

    setLoadingPortal(true);
    setMessage("");

    try {
      const res = await fetch(`${API}/billing/create-portal-session`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify({ return_url: `${window.location.origin}/settings` }),
      });

      const data = await safeJson(res);

      if (!res.ok) {
        setMessage(data?.detail || "Billing portal is not available yet.");
        return;
      }

      if (data?.portal_url) {
        window.location.href = data.portal_url;
        return;
      }
    } catch {
      setMessage("Could not open billing portal.");
    } finally {
      setLoadingPortal(false);
    }
  }

  const activePlan = billing?.plan || "free";

  return (
    <main className="min-h-screen bg-[#020617] text-white px-5 py-10">
      <div className="fixed inset-0 bg-[radial-gradient(circle_at_top_left,#1d4ed866,transparent_30%),radial-gradient(circle_at_bottom_right,#0ea5e955,transparent_28%)]" />
      <section className="relative mx-auto max-w-7xl">
        <nav className="mb-10 flex items-center justify-between rounded-3xl border border-white/10 bg-slate-950/70 px-5 py-4 backdrop-blur-xl">
          <a href="/" className="text-2xl font-black tracking-tight">
            Loss<span className="text-blue-400">Q</span>
          </a>
          <div className="flex gap-3">
            <a href="/settings" className="rounded-xl border border-white/10 px-4 py-2 text-sm text-slate-200 hover:bg-white/10">
              Settings
            </a>
            <a href="/login?fresh=1" className="rounded-xl bg-blue-600 px-4 py-2 text-sm font-bold hover:bg-blue-500">
              Launch App
            </a>
          </div>
        </nav>

        <div className="mb-12 text-center">
          <p className="mb-4 text-xs uppercase tracking-[0.35em] text-blue-300">
            Commercial Insurance Renewal Intelligence Platform
          </p>
          <h1 className="mx-auto max-w-4xl text-5xl font-black tracking-tight md:text-7xl">
            Pricing built around renewal value, not software cost.
          </h1>
          <p className="mx-auto mt-5 max-w-3xl text-lg leading-8 text-slate-300">
            LossQ helps brokers and agencies turn loss runs into renewal scoring, carrier appetite analysis, AI underwriting summaries, renewal memos, and submission packages.
          </p>
        </div>

        {message && (
          <div className="mb-8 rounded-2xl border border-blue-400/30 bg-blue-500/10 p-4 text-blue-100">
            {message}
          </div>
        )}

        <div className="mb-8 grid grid-cols-1 gap-4 rounded-3xl border border-white/10 bg-slate-950/70 p-5 md:grid-cols-4">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Current Plan</p>
            <p className="mt-1 text-xl font-bold capitalize">{activePlan.replaceAll("_", " ")}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Status</p>
            <p className="mt-1 text-xl font-bold capitalize">{billing?.subscription_status || "inactive"}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Users</p>
            <p className="mt-1 text-xl font-bold">{billing?.user_limit || "-"}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Founding Slots</p>
            <p className="mt-1 text-xl font-bold">{billing?.founding_slots_remaining ?? "-"}</p>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-4">
          {plans.map((plan) => {
            const isActive = activePlan === plan.key;
            return (
              <div
                key={plan.key}
                className={`relative rounded-3xl border p-6 backdrop-blur-xl ${
                  plan.badge === "Recommended"
                    ? "border-blue-400/60 bg-blue-500/10 shadow-[0_0_50px_rgba(59,130,246,0.22)]"
                    : "border-white/10 bg-slate-950/70"
                }`}
              >
                {plan.badge && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-blue-600 px-4 py-1 text-xs font-bold uppercase tracking-[0.18em]">
                    {plan.badge}
                  </div>
                )}

                <h2 className="text-2xl font-black">{plan.name}</h2>
                <p className="mt-3 min-h-[72px] text-sm leading-6 text-slate-400">{plan.description}</p>
                <div className="mt-6 text-5xl font-black">
                  {plan.price}
                  <span className="text-base font-semibold text-slate-400">/mo</span>
                </div>

                <ul className="mt-6 space-y-3 text-sm text-slate-300">
                  {plan.features.map((feature) => (
                    <li key={feature} className="flex gap-2">
                      <span className="text-blue-300">✓</span>
                      <span>{feature}</span>
                    </li>
                  ))}
                </ul>

                <button
                  onClick={() => startCheckout(plan.key)}
                  disabled={Boolean(loadingPlan) || isActive}
                  className={`mt-8 w-full rounded-2xl px-4 py-4 font-bold ${
                    isActive
                      ? "cursor-not-allowed border border-green-400/40 bg-green-500/10 text-green-200"
                      : "bg-blue-600 hover:bg-blue-500"
                  } disabled:opacity-60`}
                >
                  {isActive ? "Current Plan" : loadingPlan === plan.key ? "Opening Stripe..." : plan.cta}
                </button>
              </div>
            );
          })}
        </div>

        <div className="mt-8 rounded-3xl border border-white/10 bg-slate-950/70 p-6 text-center">
          <h2 className="text-2xl font-black">Enterprise</h2>
          <p className="mx-auto mt-3 max-w-3xl text-slate-300">
            For MGAs, wholesalers, large brokerages, and enterprise customers needing custom integrations, API access, SSO, custom reporting, dedicated onboarding, and premium support.
          </p>
          <a
            href="mailto:tmckenzie49@gmail.com?subject=LossQ Enterprise Inquiry"
            className="mt-5 inline-block rounded-2xl border border-blue-400/40 px-6 py-3 font-bold text-blue-100 hover:bg-blue-500/10"
          >
            Contact Sales
          </a>
        </div>

        <div className="mt-8 flex flex-wrap justify-center gap-4">
          <button
            onClick={manageBilling}
            disabled={loadingPortal}
            className="rounded-2xl border border-white/10 px-6 py-3 font-bold text-slate-200 hover:bg-white/10 disabled:opacity-60"
          >
            {loadingPortal ? "Opening Billing Portal..." : "Manage Billing"}
          </button>
          <a href="/dashboard" className="rounded-2xl bg-slate-800 px-6 py-3 font-bold hover:bg-slate-700">
            Back to Dashboard
          </a>
        </div>
      </section>
    </main>
  );
}

"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

const API =
  process.env.NEXT_PUBLIC_API_URL || "https://lossq-production.up.railway.app";

type PlanKey = "starter" | "professional" | "agency" | "founding_agency";

type BillingStatus = {
  organization_id?: number;
  organization_name?: string;
  plan?: string;
  subscription_status?: string;
  user_limit?: number;
  upload_limit?: number;
  founding_slots_remaining?: number;
  is_billing_admin?: boolean;
};

type CurrentUser = {
  id?: number;
  email?: string;
  role?: string;
  organization_id?: number;
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
    key: "founding_agency",
    name: "Founding Agency",
    price: "$99",
    description: "Locked-in launch pricing for the first 5 agencies that help shape LossQ.",
    badge: "Limited Launch Offer",
    features: [
      "5 users",
      "Unlimited uploads",
      "Professional features included",
      "Priority support",
      "Early feature access",
      "Locked-in founder pricing",
    ],
    cta: "Claim Founder Pricing",
  },
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
      "Advanced analytics",
      "Account management tools",
    ],
    cta: "Start Agency",
  },
];

function getToken() {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("lossq_token") || "";
}

async function safeJson(res: Response) {
  try {
    return await res.json();
  } catch {
    return null;
  }
}

export default function PricingPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [billing, setBilling] = useState<BillingStatus>({});
  const [currentUser, setCurrentUser] = useState<CurrentUser>({});
  const [message, setMessage] = useState("");
  const [loadingPlan, setLoadingPlan] = useState<PlanKey | "">("");
  const [loadingPortal, setLoadingPortal] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // LOSSQ_POST_PAYMENT_ONBOARDING_PRICING_SUCCESS_REDIRECT_V1
    const billingResult = String(
      searchParams.get("billing") ||
        searchParams.get("checkout") ||
        searchParams.get("payment") ||
        ""
    ).toLowerCase();

    if (["success", "paid", "complete", "completed"].includes(billingResult)) {
      try {
        localStorage.setItem("lossq_pending_paid_onboarding", "true");
        sessionStorage.setItem("lossq_pending_paid_onboarding", "true");
        sessionStorage.setItem("lossq_next_after_onboarding", "/dashboard");
      } catch {}

      router.replace("/onboarding?from=billing");
      return;
    }

    if (searchParams.get("billing") === "cancelled") {
      setMessage("Checkout was cancelled. You can choose a plan when ready.");
    }

    loadAccountAndBilling();
  }, []);

  function authHeaders(): Record<string, string> {
    const token = getToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  }

  async function loadAccountAndBilling() {
    setIsLoading(true);

    const token = getToken();
    if (!token) {
      setMessage("Log in first, then choose a plan for your LossQ account.");
      setIsLoading(false);
      return;
    }

    try {
      const meRes = await fetch(`${API}/auth/me`, { headers: authHeaders() });
      const meData = await safeJson(meRes);

      if (meRes.status === 401 || meRes.status === 403) {
        localStorage.removeItem("lossq_token");
        localStorage.removeItem("lossq_user");
        setMessage("Your session expired. Log in again, then choose a plan.");
        setIsLoading(false);
        return;
      }

      if (meRes.ok) {
        const user = meData?.user || meData || {};
        setCurrentUser(user);
        if (typeof window !== "undefined") {
          localStorage.setItem("lossq_user", JSON.stringify(user));
        }
      }

      const billingRes = await fetch(`${API}/billing/status`, {
        headers: authHeaders(),
      });
      const billingData = await safeJson(billingRes);

      if (billingRes.ok) {
        setBilling(billingData || {});
      } else {
        setMessage(
          billingData?.detail ||
            `Billing status could not load. Backend returned ${billingRes.status}.`
        );
      }
    } catch {
      setMessage(
        "Billing connection failed. Confirm Railway deployed the billing route and Vercel NEXT_PUBLIC_API_URL is https://lossq-production.up.railway.app."
      );
    } finally {
      setIsLoading(false);
    }
  }

  async function startCheckout(plan: PlanKey) {
    const token = getToken();
    if (!token) {
      router.push("/login?fresh=1&next=/pricing");
      return;
    }

    const role = String(currentUser?.role || "").toLowerCase();
    const isBillingAdmin = billing?.is_billing_admin || role === "owner" || role === "admin";

    if (!isBillingAdmin) {
      setMessage("Only an Owner or Admin can choose a billing plan. Log out and log back in if your role was recently changed.");
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
        setMessage(data?.detail || `Could not start checkout. Backend returned ${res.status}.`);
        return;
      }

      if (data?.checkout_url) {
        // LOSSQ_POST_PAYMENT_ONBOARDING_CHECKOUT_FLAG_V1
        try {
          localStorage.setItem("lossq_pending_paid_onboarding", "true");
          sessionStorage.setItem("lossq_pending_paid_onboarding", "true");
          sessionStorage.setItem("lossq_next_after_onboarding", "/dashboard");
        } catch {}

        window.location.href = data.checkout_url;
        return;
      }

      setMessage("Stripe checkout URL was not returned.");
    } catch {
      setMessage("Checkout failed. Confirm billing backend is deployed and your custom domain is allowed by CORS.");
    } finally {
      setLoadingPlan("");
    }
  }

  async function manageBilling() {
    const token = getToken();
    if (!token) {
      router.push("/login?fresh=1&next=/pricing");
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
      }
    } catch {
      setMessage("Could not open billing portal.");
    } finally {
      setLoadingPortal(false);
    }
  }

  const activePlan = billing?.plan || "free";
  const role = String(currentUser?.role || "guest").toLowerCase();
  const isBillingAdmin = billing?.is_billing_admin || role === "owner" || role === "admin";

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

        <div className="mb-10 text-center">
          <p className="mb-4 text-xs uppercase tracking-[0.35em] text-blue-300">
            LossQ Pricing
          </p>
          <h1 className="text-4xl md:text-6xl font-black tracking-tight">
            Commercial Insurance Renewal Intelligence
          </h1>
          <p className="mx-auto mt-5 max-w-3xl text-slate-300 leading-8">
            Pricing built around business value: loss run analysis, claims intelligence,
            renewal scoring, carrier appetite, premium forecasting, and submission package generation.
          </p>
        </div>

        <div className="mb-8 rounded-3xl border border-blue-400/20 bg-blue-500/10 p-5 text-sm text-blue-100">
          <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
            <div>
              <span className="font-bold">Account:</span> {currentUser?.email || "Not logged in"} · <span className="font-bold">Role:</span> {role}
            </div>
            <div>
              <span className="font-bold">Current Plan:</span> {activePlan} · <span className="font-bold">Status:</span> {billing?.subscription_status || "inactive"}
            </div>
          </div>
          {!isBillingAdmin && getToken() && (
            <p className="mt-3 text-amber-200">
              Billing changes require Owner or Admin access. If your role was recently changed, log out and log back in.
            </p>
          )}
        </div>

        {message && (
          <div className="mb-8 rounded-3xl border border-amber-300/30 bg-amber-400/10 p-5 text-amber-100">
            {message}
          </div>
        )}

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-4">
          {plans.map((plan) => {
            const isActive = activePlan === plan.key;
            const isDisabled = isLoading || Boolean(loadingPlan) || (plan.key === "founding_agency" && billing?.founding_slots_remaining === 0);

            return (
              <div
                key={plan.key}
                className={`relative rounded-3xl border p-6 backdrop-blur-xl ${
                  plan.badge
                    ? "border-blue-400/60 bg-blue-500/10 shadow-[0_0_40px_rgba(59,130,246,0.18)]"
                    : "border-white/10 bg-slate-950/70"
                }`}
              >
                {plan.badge && (
                  <div className="absolute -top-3 left-6 rounded-full bg-blue-600 px-4 py-1 text-xs font-bold uppercase tracking-widest">
                    {plan.badge}
                  </div>
                )}

                <h2 className="mt-3 text-2xl font-black">{plan.name}</h2>
                <p className="mt-3 min-h-[72px] text-sm leading-6 text-slate-300">
                  {plan.description}
                </p>

                <div className="mt-6">
                  <span className="text-5xl font-black">{plan.price}</span>
                  <span className="text-slate-400">/month</span>
                </div>

                {plan.key === "founding_agency" && (
                  <p className="mt-3 text-xs text-blue-200">
                    Founding slots remaining: {billing?.founding_slots_remaining ?? "20"}
                  </p>
                )}

                <ul className="mt-6 space-y-3 text-sm text-slate-200">
                  {plan.features.map((feature) => (
                    <li key={feature} className="flex gap-2">
                      <span className="text-blue-300">✓</span>
                      <span>{feature}</span>
                    </li>
                  ))}
                </ul>

                <button
                  type="button"
                  disabled={isDisabled || isActive}
                  onClick={() => startCheckout(plan.key)}
                  className={`mt-8 w-full rounded-2xl px-4 py-4 text-sm font-black transition ${
                    isActive
                      ? "border border-green-400/30 bg-green-500/10 text-green-200"
                      : plan.badge
                      ? "bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-50"
                      : "border border-white/10 bg-white/5 text-white hover:bg-white/10 disabled:opacity-50"
                  }`}
                >
                  {isActive ? "Current Plan" : loadingPlan === plan.key ? "Opening Stripe..." : plan.cta}
                </button>
              </div>
            );
          })}
        </div>

        <div className="mt-10 rounded-3xl border border-white/10 bg-slate-950/70 p-6">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <h3 className="text-2xl font-bold">Enterprise</h3>
              <p className="mt-2 text-slate-300">
                MGAs, wholesalers, large brokerages, custom integrations, API access, SSO, and premium support.
              </p>
            </div>
            <a
              href="mailto:hello@lossq.com?subject=LossQ Enterprise Demo"
              className="rounded-2xl bg-purple-600 px-6 py-4 text-center text-sm font-black hover:bg-purple-500"
            >
              Contact Sales
            </a>
          </div>
        </div>

        <div className="mt-8 flex flex-wrap gap-4">
          <button
            type="button"
            onClick={loadAccountAndBilling}
            className="rounded-2xl border border-white/10 px-5 py-3 text-sm font-bold hover:bg-white/10"
          >
            Refresh Billing Status
          </button>

          <button
            type="button"
            onClick={manageBilling}
            disabled={loadingPortal || !isBillingAdmin}
            className="rounded-2xl border border-blue-400/30 bg-blue-500/10 px-5 py-3 text-sm font-bold text-blue-100 hover:bg-blue-500/20 disabled:opacity-50"
          >
            {loadingPortal ? "Opening Portal..." : "Manage Billing"}
          </button>
        </div>
      </section>
    </main>
  );
}

"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

const API =
  process.env.NEXT_PUBLIC_API_URL || "https://lossq-production.up.railway.app";

type AnyObject = Record<string, any>;

function getToken() {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("lossq_token") || "";
}

function authHeaders() {
  return {
    Authorization: `Bearer ${getToken()}`,
    "Content-Type": "application/json",
  };
}

function valueOf(...values: any[]) {
  for (const value of values) {
    if (value !== undefined && value !== null && String(value).trim() !== "") {
      return String(value);
    }
  }
  return "-";
}

function phoneOf(item: AnyObject) {
  return valueOf(
    item.phone,
    item.phone_number,
    item.mobile_phone,
    item.office_phone,
    item.support_phone,
    item.billing_phone
  );
}

function statusClass(status: string) {
  const clean = String(status || "").toLowerCase();

  if (["active", "trialing", "paid", "true"].includes(clean)) {
    return "border-emerald-400/30 bg-emerald-400/10 text-emerald-200";
  }

  if (["pending", "pending_payment", "trial", "incomplete"].includes(clean)) {
    return "border-amber-400/30 bg-amber-400/10 text-amber-200";
  }

  if (["suspended", "past_due", "canceled", "inactive", "false"].includes(clean)) {
    return "border-rose-400/30 bg-rose-400/10 text-rose-200";
  }

  return "border-slate-400/20 bg-slate-400/10 text-slate-200";
}

export default function SupportLookupPage() {
  const router = useRouter();

  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [users, setUsers] = useState<AnyObject[]>([]);
  const [organizations, setOrganizations] = useState<AnyObject[]>([]);
  const [searched, setSearched] = useState(false);

  async function runLookup() {
    const cleanQuery = query.trim();

    if (!cleanQuery) {
      setError("Enter a phone number, email, company name, contact name, or organization ID.");
      return;
    }

    setLoading(true);
    setError("");
    setSearched(true);

    try {
      const token = getToken();

      if (!token) {
        router.replace("/login");
        return;
      }

      const res = await fetch(
        `${API}/platform-admin/support-lookup?q=${encodeURIComponent(cleanQuery)}`,
        { headers: authHeaders() }
      );

      if (res.status === 401) {
        router.replace("/login?expired=1");
        return;
      }

      if (res.status === 403) {
        setError("You do not have Platform Admin access.");
        return;
      }

      if (!res.ok) {
        throw new Error("Support lookup failed.");
      }

      const data = await res.json();

      setUsers(Array.isArray(data?.users) ? data.users : []);
      setOrganizations(Array.isArray(data?.organizations) ? data.organizations : []);
    } catch (err: any) {
      setError(err?.message || "Support lookup failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#050816] text-white">
      <header className="border-b border-white/10 bg-black/30 px-6 py-5">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.35em] text-cyan-300">
              Settings
            </p>
            <h1 className="mt-2 text-3xl font-black">Support Lookup</h1>
            <p className="mt-1 text-sm text-slate-400">
              Search companies and users by phone number, email, company name, contact name, or organization ID.
            </p>
          </div>

          <div className="flex gap-3">
            <button
              onClick={() => router.push("/settings")}
              className="rounded-xl border border-white/10 px-4 py-2 text-sm hover:bg-white/10"
            >
              Back to Settings
            </button>
            <button
              onClick={() => router.push("/dashboard")}
              className="rounded-xl border border-white/10 px-4 py-2 text-sm hover:bg-white/10"
            >
              Dashboard
            </button>
          </div>
        </div>
      </header>

      <section className="mx-auto max-w-7xl space-y-6 px-6 py-6">
        <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-5">
          <label className="text-sm font-bold text-slate-200">
            Support Search
          </label>

          <div className="mt-3 flex flex-col gap-3 md:flex-row">
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") runLookup();
              }}
              placeholder="Example: 704-555-0198, customer@email.com, Cedar Creek..."
              className="w-full rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-sm outline-none placeholder:text-slate-600"
            />

            <button
              onClick={runLookup}
              disabled={loading}
              className="rounded-xl bg-cyan-500 px-6 py-3 text-sm font-black text-slate-950 hover:bg-cyan-400 disabled:opacity-60"
            >
              {loading ? "Searching..." : "Search"}
            </button>
          </div>

          {error && (
            <div className="mt-4 rounded-xl border border-rose-400/30 bg-rose-400/10 p-4 text-sm text-rose-100">
              {error}
            </div>
          )}
        </div>

        {searched && !error && (
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-5">
              <h2 className="text-xl font-black">Matching Companies</h2>
              <p className="mt-1 text-sm text-slate-400">
                {organizations.length} organization match(es)
              </p>

              <div className="mt-5 space-y-3">
                {organizations.map((org, index) => {
                  const status = valueOf(org.subscription_status, org.status);

                  return (
                    <div
                      key={`${org.id || index}`}
                      className="rounded-xl border border-white/10 bg-black/20 p-4"
                    >
                      <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                        <div>
                          <div className="text-lg font-black">
                            {valueOf(org.name, org.company_name, org.organization_name)}
                          </div>
                          <div className="mt-1 text-sm text-slate-400">
                            Phone: {phoneOf(org)}
                          </div>
                          <div className="text-sm text-slate-400">
                            Org ID: {valueOf(org.id)}
                          </div>
                          <div className="text-sm text-slate-400">
                            Plan: {valueOf(org.plan)}
                          </div>
                        </div>

                        <span
                          className={`inline-flex rounded-full border px-3 py-1 text-xs font-bold ${statusClass(
                            status
                          )}`}
                        >
                          {status}
                        </span>
                      </div>
                    </div>
                  );
                })}

                {organizations.length === 0 && (
                  <div className="rounded-xl border border-white/10 bg-black/20 p-4 text-sm text-slate-400">
                    No matching companies found.
                  </div>
                )}
              </div>
            </div>

            <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-5">
              <h2 className="text-xl font-black">Matching Users</h2>
              <p className="mt-1 text-sm text-slate-400">
                {users.length} user match(es)
              </p>

              <div className="mt-5 space-y-3">
                {users.map((user, index) => {
                  const status = valueOf(
                    user.subscription_status,
                    user.account_status,
                    user.status,
                    user.is_active === true ? "active" : "",
                    user.is_active === false ? "inactive" : ""
                  );

                  return (
                    <div
                      key={`${user.id || user.email || index}`}
                      className="rounded-xl border border-white/10 bg-black/20 p-4"
                    >
                      <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                        <div>
                          <div className="text-lg font-black">
                            {valueOf(
                              user.full_name,
                              user.name,
                              `${user.first_name || ""} ${user.last_name || ""}`.trim(),
                              user.email
                            )}
                          </div>
                          <div className="mt-1 text-sm text-slate-400">
                            Email: {valueOf(user.email)}
                          </div>
                          <div className="text-sm text-slate-400">
                            Phone: {phoneOf(user)}
                          </div>
                          <div className="text-sm text-slate-400">
                            Company: {valueOf(user.company_name)}
                          </div>
                          <div className="text-sm text-slate-400">
                            Org ID: {valueOf(user.organization_id)}
                          </div>
                          <div className="text-sm text-slate-400">
                            Role: {valueOf(user.role)}
                          </div>
                        </div>

                        <span
                          className={`inline-flex rounded-full border px-3 py-1 text-xs font-bold ${statusClass(
                            status
                          )}`}
                        >
                          {status}
                        </span>
                      </div>
                    </div>
                  );
                })}

                {users.length === 0 && (
                  <div className="rounded-xl border border-white/10 bg-black/20 p-4 text-sm text-slate-400">
                    No matching users found.
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </section>
    </main>
  );
}

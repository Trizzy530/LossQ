"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

const API =
  process.env.NEXT_PUBLIC_API_URL || "https://lossq-production.up.railway.app";

type AnyObject = Record<string, any>;

function getToken() {
  if (typeof window === "undefined") return "";

  const tabToken = sessionStorage.getItem("lossq_tab_token");
  if (tabToken) return tabToken;

  const localToken = localStorage.getItem("lossq_token") || "";
  if (localToken) {
    sessionStorage.setItem("lossq_tab_token", localToken);
  }

  return localToken;
}

function authHeaders() {
  const token = getToken();
  return {
    Authorization: `Bearer ${token}`,
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

export default function PlatformAdminPage() {
  const router = useRouter();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [stats, setStats] = useState<AnyObject>({});
  const [users, setUsers] = useState<AnyObject[]>([]);
  const [organizations, setOrganizations] = useState<AnyObject[]>([]);
  const [search, setSearch] = useState("");

  async function loadPlatformAdmin() {
    setLoading(true);
    setError("");

    try {
      const token = getToken();

      if (!token) {
        router.replace("/login");
        return;
      }

      const [statsRes, usersRes, orgsRes] = await Promise.all([
        fetch(`${API}/platform-admin/stats`, { headers: authHeaders() }),
        fetch(`${API}/platform-admin/users`, { headers: authHeaders() }),
        fetch(`${API}/platform-admin/organizations`, { headers: authHeaders() }),
      ]);

      if ([statsRes.status, usersRes.status, orgsRes.status].includes(401)) {
        router.replace("/login?expired=1");
        return;
      }

      if ([statsRes.status, usersRes.status, orgsRes.status].includes(403)) {
        setError(
          "This area is restricted to authorized LossQ administrators."
        );
        return;
      }

      const statsData = statsRes.ok ? await statsRes.json() : {};
      const usersData = usersRes.ok ? await usersRes.json() : {};
      const orgsData = orgsRes.ok ? await orgsRes.json() : {};

      setStats(statsData || {});
      setUsers(Array.isArray(usersData?.users) ? usersData.users : []);
      setOrganizations(
        Array.isArray(orgsData?.organizations) ? orgsData.organizations : []
      );
    } catch (err: any) {
      setError(err?.message || "Platform Admin could not load.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadPlatformAdmin();
  }, []);

  const filteredUsers = useMemo(() => {
    const q = search.trim().toLowerCase();

    if (!q) return users;

    return users.filter((user) => {
      const text = JSON.stringify(user || {}).toLowerCase();
      return text.includes(q);
    });
  }, [users, search]);

  return (
    <main className="min-h-screen bg-[#050816] text-white">
      <header className="border-b border-white/10 bg-black/30 px-6 py-5">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.35em] text-cyan-300">
              LossQ Owner Console
            </p>
            <h1 className="mt-2 text-3xl font-black">Platform Admin</h1>
            <p className="mt-1 text-sm text-slate-400">
              View every registered user, organization, and signup across LossQ.
            </p>
          </div>

          <div className="flex gap-3">
            <button
              onClick={() => router.push("/dashboard")}
              className="rounded-xl border border-white/10 px-4 py-2 text-sm hover:bg-white/10"
            >
              Back to Dashboard
            </button>
            <button
              onClick={() => router.push("/platform-admin/beta-activity")}
              className="rounded-xl border border-emerald-400/30 px-4 py-2 text-sm font-bold text-emerald-200 hover:bg-emerald-400/10"
            >
              Beta Activity
            </button>
            <button
              onClick={() => router.push("/platform-admin/beta-feedback")}
              className="rounded-xl border border-orange-400/30 px-4 py-2 text-sm font-bold text-orange-200 hover:bg-orange-400/10"
            >
              Beta Feedback
            </button>
            <button
              onClick={() => router.push("/platform-admin/beta-requests")}
              className="rounded-xl border border-cyan-400/30 px-4 py-2 text-sm font-bold text-cyan-200 hover:bg-cyan-400/10"
            >
              Beta Requests
            </button>
            <button
              onClick={loadPlatformAdmin}
              className="rounded-xl bg-cyan-500 px-4 py-2 text-sm font-bold text-slate-950 hover:bg-cyan-400"
            >
              Refresh
            </button>
          </div>
        </div>
      </header>

      <section className="mx-auto max-w-7xl space-y-6 px-6 py-6">
        {loading ? (
          <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-8 text-slate-300">
            Loading platform users...
          </div>
        ) : error ? (
          <div className="rounded-2xl border border-rose-400/30 bg-rose-400/10 p-6 text-rose-100">
            {error}
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-5">
              {[
                ["Users", stats.total_users],
                ["Organizations", stats.total_organizations],
                ["Claims", stats.total_claims],
                ["Profiles", stats.total_profiles],
                ["Uploads", stats.total_uploads],
              ].map(([label, value]) => (
                <div
                  key={String(label)}
                  className="rounded-2xl border border-white/10 bg-white/[0.04] p-5"
                >
                  <p className="text-xs uppercase tracking-[0.25em] text-slate-500">
                    {label}
                  </p>
                  <p className="mt-2 text-3xl font-black">{value ?? 0}</p>
                </div>
              ))}
            </div>

            <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-5">
              <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                <div>
                  <h2 className="text-xl font-black">All Registered Users</h2>
                  <p className="text-sm text-slate-400">
                    Showing {filteredUsers.length} of {users.length} users.
                  </p>
                </div>

                <input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search users, emails, company, plan..."
                  className="w-full rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-sm outline-none placeholder:text-slate-600 md:w-96"
                />
              </div>

              <div className="mt-5 overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead className="border-b border-white/10 text-xs uppercase tracking-[0.2em] text-slate-500">
                    <tr>
                      <th className="px-3 py-3">User</th>
                      <th className="px-3 py-3">Organization</th>
                      <th className="px-3 py-3">Role</th>
                      <th className="px-3 py-3">Plan</th>
                      <th className="px-3 py-3">Status</th>
                      <th className="px-3 py-3">Created</th>
                    </tr>
                  </thead>

                  <tbody>
                    {filteredUsers.map((user, index) => {
                      const org = user.organization || {};
                      const status = valueOf(
                        user.subscription_status,
                        user.account_status,
                        user.status,
                        user.is_active === true ? "active" : "",
                        user.is_active === false ? "inactive" : ""
                      );

                      return (
                        <tr
                          key={`${user.id || user.email || index}`}
                          className="border-b border-white/5 hover:bg-white/[0.03]"
                        >
                          <td className="px-3 py-4">
                            <div className="font-bold">
                              {valueOf(
                                user.full_name,
                                user.name,
                                `${user.first_name || ""} ${user.last_name || ""}`.trim(),
                                user.email
                              )}
                            </div>
                            <div className="text-xs text-slate-400">
                              {valueOf(user.email)}
                            </div>
                            <div className="text-[11px] text-slate-600">
                              ID: {valueOf(user.id)}
                            </div>
                          </td>

                          <td className="px-3 py-4">
                            <div>
                              {valueOf(
                                org.name,
                                org.company_name,
                                org.organization_name,
                                user.company_name,
                                user.organization_id
                              )}
                            </div>
                            <div className="text-xs text-slate-500">
                              Org ID: {valueOf(user.organization_id)}
                            </div>
                          </td>

                          <td className="px-3 py-4">{valueOf(user.role)}</td>

                          <td className="px-3 py-4">
                            {valueOf(user.plan, org.plan)}
                          </td>

                          <td className="px-3 py-4">
                            <span
                              className={`inline-flex rounded-full border px-3 py-1 text-xs font-bold ${statusClass(
                                status
                              )}`}
                            >
                              {status}
                            </span>
                          </td>

                          <td className="px-3 py-4 text-slate-300">
                            {valueOf(user.created_at)}
                          </td>
                        </tr>
                      );
                    })}

                    {filteredUsers.length === 0 && (
                      <tr>
                        <td colSpan={6} className="px-3 py-8 text-center text-slate-400">
                          No users found.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-5">
              <h2 className="text-xl font-black">Organizations</h2>
              <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
                {organizations.map((org, index) => (
                  <div
                    key={`${org.id || index}`}
                    className="rounded-xl border border-white/10 bg-black/20 p-4"
                  >
                    <div className="font-bold">
                      {valueOf(org.name, org.company_name, org.organization_name, org.id)}
                    </div>
                    <div className="mt-1 text-xs text-slate-400">
                      Org ID: {valueOf(org.id)}
                    </div>
                    <div className="mt-2 text-sm text-slate-300">
                      Plan: {valueOf(org.plan)} · Status:{" "}
                      {valueOf(org.subscription_status)}
                    </div>
                  </div>
                ))}

                {organizations.length === 0 && (
                  <div className="text-sm text-slate-400">
                    No organizations found.
                  </div>
                )}
              </div>
            </div>
          </>
        )}
      </section>
    </main>
  );
}

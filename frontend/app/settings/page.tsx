"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

type UserRole = "owner" | "admin" | "user" | string;

type OrgUser = {
  id: number;
  email: string;
  first_name?: string;
  last_name?: string;
  role: UserRole;
  organization_id?: number;
  is_email_verified?: boolean;
  is_active?: boolean;
};

type Organization = {
  id?: number | null;
  name?: string;
  user_limit?: number;
  active_user_count?: number;
  remaining_users?: number;
  owner_user_id?: number | null;
  account_role?: string;
  company_type?: string;
  monthly_volume?: string;
  primary_lines?: string;
  ams_system?: string;
  market_state?: string;
};

const API = process.env.NEXT_PUBLIC_API_URL || "https://lossq-production.up.railway.app";

async function safeJson(res: Response) {
  try {
    return await res.json();
  } catch {
    return null;
  }
}

function displayName(user?: Partial<OrgUser> | null) {
  const fullName = `${user?.first_name || ""} ${user?.last_name || ""}`.trim();
  return fullName || user?.email || "-";
}


// LOSSQ_SETTINGS_BUSINESS_ROLE_DISPLAY_V1
function businessRoleLabel(organization?: Organization | null, me?: OrgUser | null) {
  return (
    organization?.account_role ||
    organization?.company_type ||
    me?.role ||
    "user"
  );
}


function roleBadgeClass(role?: string) {
  const clean = String(role || "user").toLowerCase();
  if (clean === "owner") return "border-purple-400/40 bg-purple-500/15 text-purple-200";
  if (clean === "admin") return "border-blue-400/40 bg-blue-500/15 text-blue-200";
  return "border-slate-400/30 bg-slate-500/10 text-slate-200";
}


// LOSSQ_SETTINGS_AGENCY_PROFILE_LINK_V1

export default function SettingsPage() {
  const router = useRouter();

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const [me, setMe] = useState<OrgUser | null>(null);
  const [organization, setOrganization] = useState<Organization | null>(null);
  const [users, setUsers] = useState<OrgUser[]>([]);

  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");

  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("user");
  const [inviteLink, setInviteLink] = useState("");

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [verifyPassword, setVerifyPassword] = useState("");
  const [securityVerified, setSecurityVerified] = useState(false);

  const isOwner = String(me?.role || "").toLowerCase() === "owner";
  const isAdmin = String(me?.role || "").toLowerCase() === "admin";
  const canManageUsers = isOwner || isAdmin;

  const activeUsers = useMemo(
    () => users.filter((user) => user.is_active !== false),
    [users]
  );

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

  async function apiFetch(path: string, options: RequestInit = {}) {
    const res = await fetch(`${API}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(),
        ...(options.headers || {}),
      },
    });

    if (res.status === 401 || res.status === 403) {
      const data = await safeJson(res);
      if (res.status === 401) {
        logout();
      }
      throw new Error(data?.detail || "Access denied");
    }

    return res;
  }

  async function loadAccountSecurity() {
    setLoading(true);
    setError("");
    setMessage("");

    try {
      if (!getToken()) {
        router.replace("/login?fresh=1");
        return;
      }

      const meRes = await apiFetch("/auth/me");
      const meData = await safeJson(meRes);

      const loadedMe = meData?.user || null;
      setMe(loadedMe);
      setOrganization(meData?.organization || null);
      setFirstName(loadedMe?.first_name || "");
      setLastName(loadedMe?.last_name || "");

      const role = String(loadedMe?.role || "user").toLowerCase();
      if (role === "owner" || role === "admin") {
        const usersRes = await apiFetch("/auth/users");
        const usersData = await safeJson(usersRes);
        setUsers(Array.isArray(usersData?.users) ? usersData.users : []);
        setOrganization(usersData?.organization || meData?.organization || null);
      } else {
        setUsers(loadedMe ? [loadedMe] : []);
      }
    } catch (err: any) {
      setError(err?.message || "Could not load account security settings.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAccountSecurity();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function saveProfile() {
    setSaving(true);
    setError("");
    setMessage("");

    try {
      const res = await apiFetch("/auth/me", {
        method: "PUT",
        body: JSON.stringify({ first_name: firstName, last_name: lastName }),
      });
      const data = await safeJson(res);
      setMe(data?.user || me);
      setMessage("Profile updated.");
      await loadAccountSecurity();
    } catch (err: any) {
      setError(err?.message || "Profile update failed.");
    } finally {
      setSaving(false);
    }
  }

  async function verifyCurrentPassword() {
    setSaving(true);
    setError("");
    setMessage("");

    try {
      const res = await apiFetch("/auth/verify-password", {
        method: "POST",
        body: JSON.stringify({ password: verifyPassword }),
      });
      const data = await safeJson(res);
      setSecurityVerified(Boolean(data?.verified));
      setVerifyPassword("");
      setMessage("Security verification passed for this session.");
    } catch (err: any) {
      setSecurityVerified(false);
      setError(err?.message || "Password verification failed.");
    } finally {
      setSaving(false);
    }
  }

  async function changePassword() {
    setSaving(true);
    setError("");
    setMessage("");

    if (newPassword.length < 8) {
      setSaving(false);
      setError("New password must be at least 8 characters.");
      return;
    }

    try {
      await apiFetch("/auth/change-password", {
        method: "POST",
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      });
      setCurrentPassword("");
      setNewPassword("");
      setMessage("Password changed successfully.");
    } catch (err: any) {
      setError(err?.message || "Password change failed.");
    } finally {
      setSaving(false);
    }
  }

  async function inviteUser() {
    setSaving(true);
    setError("");
    setMessage("");
    setInviteLink("");

    if (!inviteEmail.includes("@")) {
      setSaving(false);
      setError("Enter a valid invite email.");
      return;
    }

    try {
      const res = await apiFetch("/auth/invite", {
        method: "POST",
        body: JSON.stringify({ email: inviteEmail, role: inviteRole }),
      });
      const data = await safeJson(res);
      setInviteLink(data?.invite_link || "");
      setInviteEmail("");
      setInviteRole("user");
      setMessage("Invite created. Copy the invite link and send it to the user.");
      await loadAccountSecurity();
    } catch (err: any) {
      setError(err?.message || "Invite failed.");
    } finally {
      setSaving(false);
    }
  }

  async function removeUser(user: OrgUser) {
    if (!user?.id) return;

    const confirmed = confirm(`Remove ${user.email} from this LossQ account?`);
    if (!confirmed) return;

    setSaving(true);
    setError("");
    setMessage("");

    try {
      const res = await apiFetch(`/auth/users/${user.id}`, { method: "DELETE" });
      const data = await safeJson(res);
      setMessage(data?.message || `${user.email} was removed.`);
      await loadAccountSecurity();
    } catch (err: any) {
      setError(err?.message || "User removal failed.");
    } finally {
      setSaving(false);
    }
  }

  function canRemoveUser(user: OrgUser) {
    const myRole = String(me?.role || "user").toLowerCase();
    const targetRole = String(user.role || "user").toLowerCase();

    if (!canManageUsers) return false;
    if (user.id === me?.id) return false;
    if (targetRole === "owner") return false;
    if (myRole === "admin" && targetRole !== "user") return false;
    return true;
  }

  if (loading) {
    return (
      <main className="min-h-screen bg-[#020617] text-white flex items-center justify-center px-6">


<div className="text-center">
          <div className="text-4xl font-black mb-3">Loss<span className="text-blue-400">Q</span></div>
          <p className="text-slate-400">Loading account security...</p>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#020617] text-white px-5 py-8">



      <div className="fixed inset-0 bg-[radial-gradient(circle_at_top_left,#1d4ed855,transparent_30%),radial-gradient(circle_at_bottom_right,#7c3aed33,transparent_32%)] pointer-events-none" />
      <div className="fixed inset-0 bg-[linear-gradient(to_right,rgba(255,255,255,0.04)_1px,transparent_1px),linear-gradient(to_bottom,rgba(255,255,255,0.04)_1px,transparent_1px)] bg-[size:72px_72px] opacity-20 pointer-events-none" />

      <section className="relative max-w-7xl mx-auto">
        <header className="flex flex-col gap-5 md:flex-row md:items-center md:justify-between mb-8">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-blue-400/30 bg-blue-500/10 px-4 py-2 text-sm text-blue-200 mb-4">
              <span className="h-2 w-2 rounded-full bg-blue-400 shadow-[0_0_18px_#60a5fa]" />
              Account Security
            </div>
            <h1 className="text-4xl md:text-5xl font-black tracking-tight">LossQ Settings</h1>
            <p className="text-slate-300 mt-3 max-w-2xl">
              Manage owner/admin access, users, invites, account limits, password security, and organization controls.
            </p>
          </div>

          <div className="flex flex-wrap gap-3">
            <a href="/dashboard" className="rounded-xl border border-white/10 px-5 py-3 font-semibold text-slate-200 hover:bg-white/10">
              Back to Dashboard
            </a>

            {/* LOSSQ_SETTINGS_HEADER_BUTTON_ROW_EXACT_V1 */}
            <a
              href="/settings/agency-profile"
              className="rounded-xl border border-cyan-400/30 bg-cyan-400/10 px-5 py-3 font-semibold text-cyan-100 hover:bg-cyan-400/20"
            >
              Company Profile
            </a>

            {/* LOSSQ_SETTINGS_BILLING_LINK_V1 */}
            <a
              href="/settings/billing"
              className="rounded-xl border border-emerald-400/30 bg-emerald-400/10 px-5 py-3 font-semibold text-emerald-100 hover:bg-emerald-400/20"
            >
              Billing & Subscription
            </a>

            <a
              href="/beta-feedback"
              className="rounded-xl border border-orange-400/30 bg-orange-500/10 px-5 py-3 font-semibold text-orange-100 hover:bg-orange-500/20"
            >
              Beta Feedback
            </a>

            <a
              href="/beta-guide"
              className="rounded-xl border border-blue-400/30 bg-blue-500/10 px-5 py-3 font-semibold text-blue-100 hover:bg-blue-500/20"
            >
              Beta Guide
            </a>

            <a
              href="/platform-admin"
              className="rounded-xl border border-cyan-400/30 bg-cyan-500/10 px-5 py-3 font-semibold text-cyan-100 hover:bg-cyan-500/20"
            >
              Platform Admin
            </a>

            <a
              href="/settings/support-lookup"
              className="rounded-xl border border-cyan-400/30 bg-cyan-400/10 px-5 py-3 font-semibold text-cyan-100 hover:bg-cyan-400/20"
            >
              Support Lookup
            </a>

<a href="/audit-log" className="rounded-xl border border-purple-400/30 bg-purple-500/10 px-5 py-3 font-semibold text-purple-100 hover:bg-purple-500/20">
              Audit Log
            </a>
            <button onClick={logout} className="rounded-xl border border-red-400/30 bg-red-500/10 px-5 py-3 font-semibold text-red-200 hover:bg-red-500/20">
              Logout
            </button>
          </div>
        </header>

        {message && (
          <div className="mb-6 rounded-2xl border border-emerald-400/30 bg-emerald-500/10 p-4 text-emerald-100">
            {message}
          </div>
        )}

        {error && (
          <div className="mb-6 rounded-2xl border border-red-400/30 bg-red-500/10 p-4 text-red-100">
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-5 mb-8">
          <MetricCard title="Your Role" value={String(me?.role || "user").toUpperCase()} />
          <MetricCard title="Organization" value={organization?.name || "-"} />
          <MetricCard title="User Limit" value={organization?.user_limit ?? "-"} />
          <MetricCard title="Remaining Seats" value={organization?.remaining_users ?? "-"} />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <section className="rounded-3xl border border-white/10 bg-slate-950/75 p-6 backdrop-blur-xl lg:col-span-1">
            <h2 className="text-2xl font-bold mb-2">My Profile</h2>
            <p className="text-sm text-slate-400 mb-6">Keep your preparer name and user profile clean.</p>

            <label className="block text-sm text-blue-200 mb-2">First Name</label>
            <input
              value={firstName}
              onChange={(e) => setFirstName(e.target.value)}
              className="mb-4 w-full rounded-2xl border border-white/10 bg-slate-900/80 px-4 py-3 text-white outline-none focus:border-blue-400"
              placeholder="First name"
            />

            <label className="block text-sm text-blue-200 mb-2">Last Name</label>
            <input
              value={lastName}
              onChange={(e) => setLastName(e.target.value)}
              className="mb-4 w-full rounded-2xl border border-white/10 bg-slate-900/80 px-4 py-3 text-white outline-none focus:border-blue-400"
              placeholder="Last name"
            />

            <div className="rounded-2xl border border-white/10 bg-slate-900/60 p-4 mb-5">
              <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Signed In As</div>
              <div className="mt-2 font-semibold break-all">{me?.email}</div>
              <div className="mt-3 inline-flex rounded-full border px-3 py-1 text-xs font-bold uppercase tracking-[0.16em] ${roleBadgeClass(me?.role)}">
                {businessRoleLabel(organization, me)}
              </div>
            </div>

            <button
              onClick={saveProfile}
              disabled={saving}
              className="w-full rounded-2xl bg-blue-600 px-5 py-3 font-bold text-white hover:bg-blue-500 disabled:opacity-50"
            >
              Save Profile
            </button>
          </section>

          <section className="rounded-3xl border border-white/10 bg-slate-950/75 p-6 backdrop-blur-xl lg:col-span-2">
            <h2 className="text-2xl font-bold mb-2">Security Verification</h2>
            <p className="text-sm text-slate-400 mb-6">
              Verify your password before sensitive account changes. Password verification lasts 10 minutes on the backend.
            </p>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
              <input
                type="password"
                value={verifyPassword}
                onChange={(e) => setVerifyPassword(e.target.value)}
                className="md:col-span-2 rounded-2xl border border-white/10 bg-slate-900/80 px-4 py-3 text-white outline-none focus:border-blue-400"
                placeholder="Current password"
              />
              <button
                onClick={verifyCurrentPassword}
                disabled={saving || !verifyPassword}
                className="rounded-2xl bg-purple-600 px-5 py-3 font-bold text-white hover:bg-purple-500 disabled:opacity-50"
              >
                Verify Password
              </button>
            </div>

            <div className="rounded-2xl border border-white/10 bg-slate-900/60 p-5 mb-6">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <h3 className="font-bold">Security Status</h3>
                  <p className="text-sm text-slate-400 mt-1">
                    {securityVerified ? "Password verified for this settings session." : "Password has not been verified in this settings session."}
                  </p>
                </div>
                <span className={`rounded-full border px-4 py-2 text-sm font-bold ${securityVerified ? "border-emerald-400/40 bg-emerald-500/15 text-emerald-200" : "border-yellow-400/40 bg-yellow-500/15 text-yellow-200"}`}>
                  {securityVerified ? "Verified" : "Not Verified"}
                </span>
              </div>
            </div>

            <h3 className="text-xl font-bold mb-4">Change Password</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <input
                type="password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                className="rounded-2xl border border-white/10 bg-slate-900/80 px-4 py-3 text-white outline-none focus:border-blue-400"
                placeholder="Current password"
              />
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="rounded-2xl border border-white/10 bg-slate-900/80 px-4 py-3 text-white outline-none focus:border-blue-400"
                placeholder="New password"
              />
              <button
                onClick={changePassword}
                disabled={saving || !currentPassword || !newPassword}
                className="rounded-2xl bg-blue-600 px-5 py-3 font-bold text-white hover:bg-blue-500 disabled:opacity-50"
              >
                Change Password
              </button>
            </div>
          </section>
        </div>

        <section className="mt-6 rounded-3xl border border-white/10 bg-slate-950/75 p-6 backdrop-blur-xl">
          <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between mb-6">
            <div>
              <h2 className="text-2xl font-bold">User Management</h2>
              <p className="text-sm text-slate-400 mt-2">
                Owners can invite admins and users. Admins can invite and remove normal users only.
              </p>
            </div>
            <button
              onClick={loadAccountSecurity}
              className="rounded-xl border border-white/10 px-4 py-2 text-sm font-semibold text-slate-200 hover:bg-white/10"
            >
              Refresh
            </button>
          </div>

          {canManageUsers ? (
            <>
              <div className="grid grid-cols-1 md:grid-cols-5 gap-4 rounded-2xl border border-white/10 bg-slate-900/50 p-4 mb-6">
                <input
                  type="email"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  className="md:col-span-3 rounded-2xl border border-white/10 bg-slate-950/80 px-4 py-3 text-white outline-none focus:border-blue-400"
                  placeholder="user@company.com"
                />

                <select
                  value={inviteRole}
                  onChange={(e) => setInviteRole(e.target.value)}
                  className="rounded-2xl border border-white/10 bg-slate-950/80 px-4 py-3 text-white outline-none focus:border-blue-400"
                >
                  <option value="user">User</option>
                  {isOwner && <option value="admin">Admin</option>}
                </select>

                <button
                  onClick={inviteUser}
                  disabled={saving || !inviteEmail}
                  className="rounded-2xl bg-blue-600 px-5 py-3 font-bold text-white hover:bg-blue-500 disabled:opacity-50"
                >
                  Send Invite
                </button>
              </div>

              {inviteLink && (
                <div className="mb-6 rounded-2xl border border-blue-400/30 bg-blue-500/10 p-4">
                  <div className="text-sm font-bold text-blue-200 mb-2">Invite Link</div>
                  <div className="break-all text-sm text-slate-200">{inviteLink}</div>
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(inviteLink);
                      setMessage("Invite link copied.");
                    }}
                    className="mt-3 rounded-xl border border-blue-400/40 px-4 py-2 text-sm font-semibold text-blue-100 hover:bg-blue-500/20"
                  >
                    Copy Invite Link
                  </button>
                </div>
              )}
            </>
          ) : (
            <div className="rounded-2xl border border-yellow-400/30 bg-yellow-500/10 p-4 text-yellow-100">
              You do not have permission to manage users.
            </div>
          )}

          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] text-sm">
              <thead>
                <tr className="border-b border-white/10 text-left text-slate-300">
                  <th className="py-3 pr-4">Name</th>
                  <th className="py-3 pr-4">Email</th>
                  <th className="py-3 pr-4">Role</th>
                  <th className="py-3 pr-4">Email Verified</th>
                  <th className="py-3 pr-4">Status</th>
                  <th className="py-3 pr-4 text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <tr key={user.id} className="border-b border-white/10 text-slate-200">
                    <td className="py-4 pr-4 font-semibold">{displayName(user)}</td>
                    <td className="py-4 pr-4 break-all">{user.email}</td>
                    <td className="py-4 pr-4">
                      <span className={`rounded-full border px-3 py-1 text-xs font-bold uppercase tracking-[0.16em] ${roleBadgeClass(user.role)}`}>
                        {user.role || "user"}
                      </span>
                    </td>
                    <td className="py-4 pr-4">{user.is_email_verified ? "Verified" : "Pending"}</td>
                    <td className="py-4 pr-4">{user.is_active === false ? "Removed" : "Active"}</td>
                    <td className="py-4 pr-4 text-right">
                      {canRemoveUser(user) ? (
                        <button
                          onClick={() => removeUser(user)}
                          disabled={saving}
                          className="rounded-xl border border-red-400/30 bg-red-500/10 px-4 py-2 font-semibold text-red-200 hover:bg-red-500/20 disabled:opacity-50"
                        >
                          Remove
                        </button>
                      ) : (
                        <span className="text-slate-500">Protected</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </section>
    </main>
  );
}

function MetricCard({ title, value }: { title: string; value: any }) {
  return (
    <div className="rounded-3xl border border-white/10 bg-slate-950/75 p-6 backdrop-blur-xl">
      <div className="text-sm text-slate-400">{title}</div>
      <div className="mt-3 text-2xl font-black text-white break-words">{value}</div>
    </div>
  );
}

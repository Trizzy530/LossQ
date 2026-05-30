"use client";

import { useEffect, useState } from "react";

const API =
  process.env.NEXT_PUBLIC_API_URL || "https://lossq-production.up.railway.app";

const ROLES = ["admin", "broker", "underwriter", "viewer", "user"];

export default function AdminUsersPage() {
  const [users, setUsers] = useState<any[]>([]);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);

  function authHeaders(): Record<string, string> {
    const token = localStorage.getItem("lossq_token");
    return token ? { Authorization: `Bearer ${token}` } : {};
  }

  async function loadUsers() {
    setLoading(true);
    setMessage("");

    try {
      const res = await fetch(`${API}/admin/users/`, {
        headers: authHeaders(),
      });

      const data = await res.json().catch(() => null);

      if (!res.ok) {
        setMessage(data?.detail || "Could not load users.");
        return;
      }

      setUsers(Array.isArray(data) ? data : []);
    } catch {
      setMessage("Admin users request failed.");
    } finally {
      setLoading(false);
    }
  }

  async function updateRole(userId: number, role: string) {
    setMessage("");

    try {
      const res = await fetch(`${API}/admin/users/${userId}/role`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify({ role }),
      });

      const data = await res.json().catch(() => null);

      if (!res.ok) {
        setMessage(data?.detail || "Could not update role.");
        return;
      }

      setUsers((prev) =>
        prev.map((user) =>
          user.id === userId ? { ...user, role } : user
        )
      );

      setMessage("User role updated.");
    } catch {
      setMessage("Role update failed.");
    }
  }

  useEffect(() => {
    loadUsers();
  }, []);

  return (
    <main className="min-h-screen bg-slate-950 text-white p-10">
      <div className="max-w-6xl mx-auto">
        <div className="flex justify-between items-start mb-10">
          <div>
            <h1 className="text-5xl font-bold">User Management</h1>
            <p className="text-slate-400 mt-2">
              Manage LossQ organization users and role permissions.
            </p>
          </div>

          <a
            href="/dashboard"
            className="bg-slate-800 hover:bg-slate-700 px-5 py-3 rounded-lg font-semibold"
          >
            Back to Dashboard
          </a>
        </div>

        {message && (
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 mb-6 text-slate-300">
            {message}
          </div>
        )}

        <section className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
          <div className="flex justify-between items-center mb-6">
            <h2 className="text-3xl font-semibold">Organization Users</h2>

            <button
              onClick={loadUsers}
              className="bg-blue-600 hover:bg-blue-700 px-5 py-3 rounded-lg font-semibold"
            >
              Refresh
            </button>
          </div>

          {loading ? (
            <p className="text-slate-400">Loading users...</p>
          ) : users.length === 0 ? (
            <p className="text-slate-400">No users found.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-700 text-left">
                    <th className="pb-4">User ID</th>
                    <th className="pb-4">Email</th>
                    <th className="pb-4">Organization</th>
                    <th className="pb-4">Role</th>
                    <th className="pb-4">Change Role</th>
                  </tr>
                </thead>

                <tbody>
                  {users.map((user) => (
                    <tr
                      key={user.id}
                      className="border-b border-slate-800"
                    >
                      <td className="py-4">{user.id}</td>
                      <td>{user.email}</td>
                      <td>{user.organization_id || "-"}</td>
                      <td>
                        <span className="bg-blue-500/10 text-blue-300 border border-blue-500/30 px-3 py-1 rounded-full text-sm font-semibold">
                          {user.role || "viewer"}
                        </span>
                      </td>
                      <td>
                        <select
                          value={user.role || "viewer"}
                          onChange={(e) =>
                            updateRole(user.id, e.target.value)
                          }
                          className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2"
                        >
                          {ROLES.map((role) => (
                            <option key={role} value={role}>
                              {role}
                            </option>
                          ))}
                        </select>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
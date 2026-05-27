"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

const API =
  process.env.NEXT_PUBLIC_API_URL ||
  "https://lossq-production.up.railway.app";

export default function SettingsPage() {
  const router = useRouter();

  const [user, setUser] = useState<any>(null);
  const [backendStatus, setBackendStatus] = useState("Checking...");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("lossq_token");
    const storedUser = localStorage.getItem("lossq_user");

    if (!token) {
      router.replace("/login?fresh=1");
      return;
    }

    if (storedUser) {
      try {
        setUser(JSON.parse(storedUser));
      } catch {}
    }

    checkBackend();

    setLoading(false);
  }, []);

  async function checkBackend() {
    try {
      const res = await fetch(`${API}/`);

      if (!res.ok) {
        setBackendStatus("Offline");
        return;
      }

      setBackendStatus("Online");
    } catch {
      setBackendStatus("Offline");
    }
  }

  function logout() {
    localStorage.removeItem("lossq_token");
    localStorage.removeItem("lossq_user");
    localStorage.removeItem("lossq_login_time");
    sessionStorage.clear();

    router.replace("/login?fresh=1");
  }

  function logoutAllSessions() {
    localStorage.clear();
    sessionStorage.clear();

    router.replace("/login?fresh=1");
  }

  if (loading) {
    return (
      <main className="min-h-screen bg-slate-950 text-white flex items-center justify-center">
        Loading settings...
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-950 text-white p-10">
      <div className="max-w-5xl mx-auto">
        <div className="flex justify-between items-start mb-10">
          <div>
            <h1 className="text-5xl font-bold">Settings</h1>

            <p className="text-slate-400 mt-2">
              Manage your LossQ workspace and session
            </p>
          </div>

          <a
            href="/dashboard"
            className="bg-slate-800 hover:bg-slate-700 px-5 py-3 rounded-lg font-semibold"
          >
            Back to Dashboard
          </a>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-10">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
            <h2 className="text-2xl font-semibold mb-5">
              Account Information
            </h2>

            <div className="space-y-4 text-slate-300">
              <div>
                <div className="text-slate-500 text-sm mb-1">User ID</div>
                <div>{user?.id || "-"}</div>
              </div>

              <div>
                <div className="text-slate-500 text-sm mb-1">Email</div>
                <div>{user?.email || "-"}</div>
              </div>

              <div>
                <div className="text-slate-500 text-sm mb-1">
                  Organization ID
                </div>
                <div>{user?.organization_id || "-"}</div>
              </div>
            </div>
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
            <h2 className="text-2xl font-semibold mb-5">
              System Status
            </h2>

            <div className="space-y-4 text-slate-300">
              <div>
                <div className="text-slate-500 text-sm mb-1">
                  Backend API
                </div>

                <div
                  className={
                    backendStatus === "Online"
                      ? "text-green-400"
                      : "text-red-400"
                  }
                >
                  {backendStatus}
                </div>
              </div>

              <div>
                <div className="text-slate-500 text-sm mb-1">
                  API URL
                </div>

                <div className="break-all text-sm">
                  {API}
                </div>
              </div>

              <div>
                <div className="text-slate-500 text-sm mb-1">
                  Environment
                </div>

                <div>Production</div>
              </div>
            </div>
          </div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 mb-10">
          <h2 className="text-2xl font-semibold mb-6">
            Security & Sessions
          </h2>

          <div className="flex flex-wrap gap-4">
            <a
              href="/forgot-password"
              className="bg-blue-600 hover:bg-blue-700 px-5 py-3 rounded-lg font-semibold"
            >
              Reset Password
            </a>

            <button
              onClick={logout}
              className="bg-orange-600 hover:bg-orange-700 px-5 py-3 rounded-lg font-semibold"
            >
              Logout
            </button>

            <button
              onClick={logoutAllSessions}
              className="bg-red-600 hover:bg-red-700 px-5 py-3 rounded-lg font-semibold"
            >
              Logout All Sessions
            </button>
          </div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
          <h2 className="text-2xl font-semibold mb-5">
            Platform Information
          </h2>

          <div className="space-y-4 text-slate-300">
            <div>
              <div className="text-slate-500 text-sm mb-1">
                Platform
              </div>

              <div>LossQ Underwriting OS</div>
            </div>

            <div>
              <div className="text-slate-500 text-sm mb-1">
                Version
              </div>

              <div>v1.0 Production</div>
            </div>

            <div>
              <div className="text-slate-500 text-sm mb-1">
                Status
              </div>

              <div className="text-green-400">
                Operational
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
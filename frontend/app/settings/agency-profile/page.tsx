"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_URL || "https://lossq-production.up.railway.app";

type AgencyProfile = {
  organization_id?: number | null;
  organization_name?: string;
  agency_name?: string;
  agency_contact_name?: string;
  agency_email?: string;
  agency_phone?: string;
  agency_address?: string;
  agency_city?: string;
  agency_state?: string;
  agency_zip?: string;
  agency_website?: string;
  agency_license_number?: string;
  agency_logo_url?: string;
};

const emptyProfile: AgencyProfile = {
  organization_name: "",
  agency_name: "",
  agency_contact_name: "",
  agency_email: "",
  agency_phone: "",
  agency_address: "",
  agency_city: "",
  agency_state: "",
  agency_zip: "",
  agency_website: "",
  agency_license_number: "",
  agency_logo_url: "",
};

function getToken() {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("lossq_token") || "";
}

export default function AgencyProfilePage() {
  const router = useRouter();

  const [profile, setProfile] = useState<AgencyProfile>(emptyProfile);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  function updateField(key: keyof AgencyProfile, value: string) {
    setProfile((prev) => ({ ...prev, [key]: value }));
  }

  async function loadProfile() {
    setLoading(true);
    setMessage("");

    const token = getToken();

    if (!token) {
      router.push("/login?fresh=1&next=/settings/agency-profile");
      return;
    }

    try {
      const res = await fetch(`${API}/auth/agency-profile`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (res.status === 401) {
        localStorage.removeItem("lossq_token");
        router.push("/login?fresh=1&next=/settings/agency-profile");
        return;
      }

      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        setMessage(data?.detail || "Unable to load agency profile.");
        return;
      }

      setProfile({ ...emptyProfile, ...data });
    } catch {
      setMessage("Unable to connect to LossQ backend.");
    } finally {
      setLoading(false);
    }
  }

  async function saveProfile() {
    setSaving(true);
    setMessage("");

    const token = getToken();

    if (!token) {
      router.push("/login?fresh=1&next=/settings/agency-profile");
      return;
    }

    const payload = {
      agency_contact_name: profile.agency_contact_name || "",
      agency_email: profile.agency_email || "",
      agency_phone: profile.agency_phone || "",
      agency_address: profile.agency_address || "",
      agency_city: profile.agency_city || "",
      agency_state: profile.agency_state || "",
      agency_zip: profile.agency_zip || "",
      agency_website: profile.agency_website || "",
      agency_license_number: profile.agency_license_number || "",
      agency_logo_url: profile.agency_logo_url || "",
    };

    try {
      const res = await fetch(`${API}/auth/agency-profile`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (res.status === 401) {
        localStorage.removeItem("lossq_token");
        router.push("/login?fresh=1&next=/settings/agency-profile");
        return;
      }

      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        setMessage(data?.detail || "Unable to save agency profile.");
        return;
      }

      setProfile({ ...emptyProfile, ...(data?.agency_profile || profile) });
      setMessage("Agency profile saved. Future PDF exports will use this agency information.");
    } catch {
      setMessage("Unable to connect to LossQ backend.");
    } finally {
      setSaving(false);
    }
  }

  useEffect(() => {
    loadProfile();
  }, []);

  if (loading) {
    return (
      <main className="min-h-screen bg-[#050816] text-white flex items-center justify-center">
        <div className="rounded-2xl border border-white/10 bg-white/5 px-6 py-5">
          Loading agency profile...
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#050816] text-white px-6 py-8">
      <div className="mx-auto max-w-5xl">
        <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-semibold text-cyan-300">Organization Agency Profile</p>
            <h1 className="text-3xl font-black tracking-tight">PDF Branding Information</h1>
            <p className="mt-2 text-slate-400">
              This information appears on Executive Reports, Carrier Packets, and future LossQ PDF exports.
            </p>
          </div>

          <button
            type="button"
            onClick={() => router.push("/dashboard")}
            className="rounded-xl border border-white/15 px-4 py-2 font-semibold hover:bg-white/10"
          >
            Back to Dashboard
          </button>
        </div>

        {message && (
          <div className="mb-6 rounded-2xl border border-cyan-400/30 bg-cyan-400/10 p-4 text-sm text-cyan-100">
            {message}
          </div>
        )}

        <section className="rounded-3xl border border-white/10 bg-slate-950/80 p-6 shadow-2xl shadow-cyan-500/10">
          <div className="mb-6 rounded-2xl border border-white/10 bg-white/5 p-4">
            <p className="text-xs uppercase tracking-[0.25em] text-slate-500">Organization</p>
            <p className="mt-1 text-xl font-bold">
              {profile.organization_name || profile.agency_name || "Your Agency"}
            </p>
            <p className="mt-1 text-sm text-slate-400">
              Organization ID: {profile.organization_id || "N/A"}
            </p>
          </div>

          <div className="grid gap-5 md:grid-cols-2">
            <label className="block">
              <span className="text-sm font-semibold text-slate-300">Agency Contact Name</span>
              <input
                value={profile.agency_contact_name || ""}
                onChange={(e) => updateField("agency_contact_name", e.target.value)}
                className="mt-2 w-full rounded-xl border border-white/10 bg-slate-900 px-4 py-3 text-white outline-none focus:border-cyan-400"
                placeholder="Jane Smith"
              />
            </label>

            <label className="block">
              <span className="text-sm font-semibold text-slate-300">Agency Email</span>
              <input
                value={profile.agency_email || ""}
                onChange={(e) => updateField("agency_email", e.target.value)}
                className="mt-2 w-full rounded-xl border border-white/10 bg-slate-900 px-4 py-3 text-white outline-none focus:border-cyan-400"
                placeholder="service@agency.com"
              />
            </label>

            <label className="block">
              <span className="text-sm font-semibold text-slate-300">Agency Phone</span>
              <input
                value={profile.agency_phone || ""}
                onChange={(e) => updateField("agency_phone", e.target.value)}
                className="mt-2 w-full rounded-xl border border-white/10 bg-slate-900 px-4 py-3 text-white outline-none focus:border-cyan-400"
                placeholder="(555) 555-5555"
              />
            </label>

            <label className="block">
              <span className="text-sm font-semibold text-slate-300">Agency Website</span>
              <input
                value={profile.agency_website || ""}
                onChange={(e) => updateField("agency_website", e.target.value)}
                className="mt-2 w-full rounded-xl border border-white/10 bg-slate-900 px-4 py-3 text-white outline-none focus:border-cyan-400"
                placeholder="https://agency.com"
              />
            </label>

            <label className="block md:col-span-2">
              <span className="text-sm font-semibold text-slate-300">Agency Address</span>
              <input
                value={profile.agency_address || ""}
                onChange={(e) => updateField("agency_address", e.target.value)}
                className="mt-2 w-full rounded-xl border border-white/10 bg-slate-900 px-4 py-3 text-white outline-none focus:border-cyan-400"
                placeholder="123 Main Street, Suite 200"
              />
            </label>

            <label className="block">
              <span className="text-sm font-semibold text-slate-300">City</span>
              <input
                value={profile.agency_city || ""}
                onChange={(e) => updateField("agency_city", e.target.value)}
                className="mt-2 w-full rounded-xl border border-white/10 bg-slate-900 px-4 py-3 text-white outline-none focus:border-cyan-400"
                placeholder="Charlotte"
              />
            </label>

            <div className="grid grid-cols-2 gap-4">
              <label className="block">
                <span className="text-sm font-semibold text-slate-300">State</span>
                <input
                  value={profile.agency_state || ""}
                  onChange={(e) => updateField("agency_state", e.target.value)}
                  className="mt-2 w-full rounded-xl border border-white/10 bg-slate-900 px-4 py-3 text-white outline-none focus:border-cyan-400"
                  placeholder="NC"
                />
              </label>

              <label className="block">
                <span className="text-sm font-semibold text-slate-300">ZIP</span>
                <input
                  value={profile.agency_zip || ""}
                  onChange={(e) => updateField("agency_zip", e.target.value)}
                  className="mt-2 w-full rounded-xl border border-white/10 bg-slate-900 px-4 py-3 text-white outline-none focus:border-cyan-400"
                  placeholder="28202"
                />
              </label>
            </div>

            <label className="block">
              <span className="text-sm font-semibold text-slate-300">Agency License Number</span>
              <input
                value={profile.agency_license_number || ""}
                onChange={(e) => updateField("agency_license_number", e.target.value)}
                className="mt-2 w-full rounded-xl border border-white/10 bg-slate-900 px-4 py-3 text-white outline-none focus:border-cyan-400"
                placeholder="License #"
              />
            </label>

            <label className="block">
              <span className="text-sm font-semibold text-slate-300">Logo URL</span>
              <input
                value={profile.agency_logo_url || ""}
                onChange={(e) => updateField("agency_logo_url", e.target.value)}
                className="mt-2 w-full rounded-xl border border-white/10 bg-slate-900 px-4 py-3 text-white outline-none focus:border-cyan-400"
                placeholder="https://agency.com/logo.png"
              />
            </label>
          </div>

          <div className="mt-7 flex flex-col gap-3 sm:flex-row">
            <button
              type="button"
              onClick={saveProfile}
              disabled={saving}
              className="rounded-xl bg-cyan-400 px-6 py-3 font-black text-slate-950 hover:bg-cyan-300 disabled:opacity-50"
            >
              {saving ? "Saving..." : "Save Agency Profile"}
            </button>

            <button
              type="button"
              onClick={loadProfile}
              className="rounded-xl border border-white/15 px-6 py-3 font-bold hover:bg-white/10"
            >
              Refresh
            </button>
          </div>
        </section>
      </div>
    </main>
  );
}

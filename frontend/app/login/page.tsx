"use client";

import { useEffect, useState } from "react";

const API =
  process.env.NEXT_PUBLIC_API_URL || "https://lossq-production.up.railway.app";

async function safeJson(res: Response) {
  try {
    return await res.json();
  } catch {
    return null;
  }
}

function errorToText(data: any, fallback: string) {
  if (!data) return fallback;
  if (typeof data === "string") return data;
  if (typeof data.detail === "string") return data.detail;
  if (typeof data.message === "string") return data.message;

  if (Array.isArray(data.detail)) {
    return data.detail
      .map((item: any) => item?.msg || JSON.stringify(item))
      .join(", ");
  }

  return fallback;
}

export default function LoginPage() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [step, setStep] = useState(1);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const [organizationName, setOrganizationName] = useState("");
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState("");
  const [companyType, setCompanyType] = useState("");
  const [phone, setPhone] = useState("");
  const [monthlyVolume, setMonthlyVolume] = useState("");
  const [primaryLines, setPrimaryLines] = useState("");
  const [amsSystem, setAmsSystem] = useState("");
  const [marketState, setMarketState] = useState("");

  const [message, setMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);

    if (params.get("fresh") === "1") {
      localStorage.removeItem("lossq_token");
      localStorage.removeItem("lossq_user");
      sessionStorage.removeItem("lossq_welcome");
    }
  }, []);

  async function loginUser(cleanEmail: string, cleanPassword: string, isNewUser = false) {
    const loginRes = await fetch(`${API}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: cleanEmail, password: cleanPassword }),
    });

    const loginData = await safeJson(loginRes);

    if (!loginRes.ok) {
      throw new Error(errorToText(loginData, "Login failed."));
    }

    const token = loginData?.access_token || loginData?.token;

    if (!token) {
      throw new Error("No login token returned.");
    }

    localStorage.setItem("lossq_token", token);
    localStorage.setItem("lossq_user", cleanEmail);

    sessionStorage.setItem(
      "lossq_welcome",
      isNewUser
        ? `Welcome to LossQ, ${cleanEmail.split("@")[0]}`
        : `Welcome back, ${cleanEmail.split("@")[0]}`
    );

    window.location.href = "/dashboard";
  }

  function validateRegisterStepOne() {
    if (!organizationName.trim()) return "Organization name is required.";
    if (!fullName.trim()) return "Full name is required.";
    if (!email.trim()) return "Work email is required.";
    if (!password) return "Password is required.";
    if (password.length < 8) return "Password must be at least 8 characters.";
    return "";
  }

  function validateRegisterStepTwo() {
    if (!role) return "Role is required.";
    if (!companyType) return "Company type is required.";
    if (!phone.trim()) return "Phone number is required.";
    return "";
  }

  function nextStep() {
    setMessage("");

    const stepOneError = validateRegisterStepOne();

    if (stepOneError) {
      setMessage(stepOneError);
      return;
    }

    setStep(2);
  }

  async function submit() {
    setLoading(true);
    setMessage("");
    setSuccessMessage("");

    try {
      const cleanEmail = email.trim().toLowerCase();
      const cleanOrganization = organizationName.trim();

      if (mode === "login") {
        if (!cleanEmail || !password) {
          setMessage("Email and password are required.");
          return;
        }

        await loginUser(cleanEmail, password, false);
        return;
      }

      const stepOneError = validateRegisterStepOne();
      const stepTwoError = validateRegisterStepTwo();

      if (stepOneError || stepTwoError) {
        setMessage(stepOneError || stepTwoError);
        return;
      }

      const registerRes = await fetch(`${API}/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: cleanEmail,
          password,
          organization_name: cleanOrganization,

          full_name: fullName.trim(),
          role,
          company_type: companyType,
          phone: phone.trim(),
          monthly_loss_run_volume: monthlyVolume,
          primary_lines: primaryLines,
          agency_management_system: amsSystem,
          market_state: marketState,

          email_verification_status: "pending",
          onboarding_status: "profile_started",
        }),
      });

      const registerData = await safeJson(registerRes);

      if (!registerRes.ok) {
        setMessage(errorToText(registerData, "Registration failed."));
        return;
      }

      setSuccessMessage(
        "Account created. Email verification is pending. Redirecting to your dashboard..."
      );

      await loginUser(cleanEmail, password, true);
    } catch (err: any) {
      setMessage(err?.message || "Request failed. Check backend connection.");
    } finally {
      setLoading(false);
    }
  }

  function switchMode() {
    setMode(mode === "login" ? "register" : "login");
    setStep(1);
    setMessage("");
    setSuccessMessage("");
  }

  return (
    <main className="min-h-screen bg-[#030508] text-white flex items-center justify-center px-6 py-12">
      <div className="fixed inset-0 bg-[linear-gradient(rgba(0,120,255,0.05)_1px,transparent_1px),linear-gradient(90deg,rgba(0,120,255,0.05)_1px,transparent_1px)] bg-[size:60px_60px]" />
      <div className="fixed inset-0 bg-[radial-gradient(circle_at_top,rgba(0,120,255,0.25),transparent_45%)]" />

      <div className="relative w-full max-w-xl bg-[#0A1628] border border-blue-500/20 rounded-3xl p-8 shadow-2xl">
        <h1 className="text-5xl font-black mb-3">
          Loss<span className="text-blue-500">Q</span>
        </h1>

        <p className="text-slate-300 text-xl mb-6">
          {mode === "login"
            ? "Sign in to continue."
            : "Create your agency account."}
        </p>

        {mode === "register" && (
          <div className="grid grid-cols-3 gap-2 mb-6">
            <div className={`h-2 rounded-full ${step >= 1 ? "bg-blue-500" : "bg-slate-700"}`} />
            <div className={`h-2 rounded-full ${step >= 2 ? "bg-blue-500" : "bg-slate-700"}`} />
            <div className="h-2 rounded-full bg-slate-700" />
          </div>
        )}

        {message && (
          <div className="bg-red-500/10 border border-red-500/30 text-red-300 rounded-lg p-3 mb-5 text-sm whitespace-pre-wrap">
            {message}
          </div>
        )}

        {successMessage && (
          <div className="bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 rounded-lg p-3 mb-5 text-sm">
            {successMessage}
          </div>
        )}

        {mode === "login" && (
          <>
            <input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Email"
              className="w-full bg-slate-900 border border-blue-400/40 rounded-lg px-4 py-3 mb-4 outline-none focus:border-blue-500"
            />

            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              className="w-full bg-slate-900 border border-blue-400/40 rounded-lg px-4 py-3 mb-6 outline-none focus:border-blue-500"
            />
          </>
        )}

        {mode === "register" && step === 1 && (
          <>
            <input
              value={organizationName}
              onChange={(e) => setOrganizationName(e.target.value)}
              placeholder="Organization Name"
              className="w-full bg-slate-900 border border-blue-400/40 rounded-lg px-4 py-3 mb-4 outline-none focus:border-blue-500"
            />

            <input
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Your Full Name"
              className="w-full bg-slate-900 border border-blue-400/40 rounded-lg px-4 py-3 mb-4 outline-none focus:border-blue-500"
            />

            <input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Work Email"
              type="email"
              className="w-full bg-slate-900 border border-blue-400/40 rounded-lg px-4 py-3 mb-4 outline-none focus:border-blue-500"
            />

            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              className="w-full bg-slate-900 border border-blue-400/40 rounded-lg px-4 py-3 mb-6 outline-none focus:border-blue-500"
            />
          </>
        )}

        {mode === "register" && step === 2 && (
          <>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className="w-full bg-slate-900 border border-blue-400/40 rounded-lg px-4 py-3 mb-4 outline-none focus:border-blue-500"
            >
              <option value="">Select Role</option>
              <option>Broker</option>
              <option>Underwriter</option>
              <option>Agency Owner</option>
              <option>Admin</option>
              <option>Producer</option>
            </select>

            <select
              value={companyType}
              onChange={(e) => setCompanyType(e.target.value)}
              className="w-full bg-slate-900 border border-blue-400/40 rounded-lg px-4 py-3 mb-4 outline-none focus:border-blue-500"
            >
              <option value="">Company Type</option>
              <option>Retail Agency</option>
              <option>MGA</option>
              <option>Carrier</option>
              <option>Wholesaler</option>
              <option>Risk Management Firm</option>
            </select>

            <input
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="Phone Number"
              className="w-full bg-slate-900 border border-blue-400/40 rounded-lg px-4 py-3 mb-4 outline-none focus:border-blue-500"
            />

            <select
              value={monthlyVolume}
              onChange={(e) => setMonthlyVolume(e.target.value)}
              className="w-full bg-slate-900 border border-blue-400/40 rounded-lg px-4 py-3 mb-4 outline-none focus:border-blue-500"
            >
              <option value="">Monthly Loss Run Volume</option>
              <option>1-10</option>
              <option>11-25</option>
              <option>26-50</option>
              <option>51-100</option>
              <option>100+</option>
            </select>

            <input
              value={primaryLines}
              onChange={(e) => setPrimaryLines(e.target.value)}
              placeholder="Primary Lines: Auto, GL, Workers Comp, Property"
              className="w-full bg-slate-900 border border-blue-400/40 rounded-lg px-4 py-3 mb-4 outline-none focus:border-blue-500"
            />

            <input
              value={amsSystem}
              onChange={(e) => setAmsSystem(e.target.value)}
              placeholder="AMS/CRM System Used"
              className="w-full bg-slate-900 border border-blue-400/40 rounded-lg px-4 py-3 mb-4 outline-none focus:border-blue-500"
            />

            <input
              value={marketState}
              onChange={(e) => setMarketState(e.target.value)}
              placeholder="Primary State / Market"
              className="w-full bg-slate-900 border border-blue-400/40 rounded-lg px-4 py-3 mb-6 outline-none focus:border-blue-500"
            />

            <div className="bg-blue-500/10 border border-blue-500/30 text-blue-200 text-sm rounded-lg p-3 mb-6">
              Email verification placeholder: after registration, users will be marked as pending verification until email confirmation is added.
            </div>
          </>
        )}

        {mode === "register" && step === 1 ? (
          <button
            onClick={nextStep}
            disabled={loading}
            className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-lg py-3 font-bold"
          >
            Continue
          </button>
        ) : (
          <button
            onClick={submit}
            disabled={loading}
            className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-lg py-3 font-bold"
          >
            {loading ? "Please wait..." : mode === "login" ? "Login" : "Create Account"}
          </button>
        )}

        {mode === "register" && step === 2 && (
          <button
            onClick={() => setStep(1)}
            className="w-full mt-3 text-slate-300 hover:text-white text-sm"
          >
            ← Back
          </button>
        )}

        <button
          onClick={switchMode}
          className="w-full mt-4 text-slate-300 hover:text-white text-sm"
        >
          {mode === "login"
            ? "Need an account? Register"
            : "Already have an account? Login"}
        </button>

        <a href="/" className="block text-center mt-6 text-blue-400 text-sm">
          Back to landing
        </a>
      </div>
    </main>
  );
}
"use client";

// LOSSQ_HIDE_OWNER_FROM_PUBLIC_REGISTER_V1

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


function getSafeNextPath() {
  if (typeof window === "undefined") return "/dashboard";

  const params = new URLSearchParams(window.location.search);
  const next = params.get("next") || sessionStorage.getItem("lossq_next_after_login");

  if (!next) return "/dashboard";

  try {
    const decoded = decodeURIComponent(next);

    if (
      decoded.startsWith("/") &&
      !decoded.startsWith("//") &&
      !decoded.includes("http://") &&
      !decoded.includes("https://")
    ) {
      return decoded;
    }
  } catch {
    if (next.startsWith("/") && !next.startsWith("//")) {
      return next;
    }
  }

  return "/dashboard";
}


// LOSSQ_CLEAR_ACCOUNT_CACHE_ON_LOGIN_V1
function clearLossQAccountCacheBeforeLogin() {
  if (typeof window === "undefined") return;

  const shouldClear = (key: string) => {
    const clean = String(key || "").toLowerCase();

    return (
      clean.startsWith("lossq_") ||
      clean.includes("claim") ||
      clean.includes("claims") ||
      clean.includes("profile") ||
      clean.includes("account") ||
      clean.includes("dashboard") ||
      clean.includes("carrier") ||
      clean.includes("renewal")
    );
  };

  Object.keys(localStorage).forEach((key) => {
    if (shouldClear(key)) {
      localStorage.removeItem(key);
    }
  });

  Object.keys(sessionStorage).forEach((key) => {
    if (shouldClear(key)) {
      sessionStorage.removeItem(key);
    }
  });
}




// LOSSQ_REGISTER_DROPDOWN_MULTISELECT_FIELDS_V1
const LOSSQ_PRIMARY_LINE_OPTIONS = [
  "Businessowners / Package",
  "General Liability",
  "Workers Compensation",
  "Commercial Auto",
  "Property",
  "Umbrella / Excess",
  "Cyber Liability",
  "Professional Liability",
  "EPLI",
];

const LOSSQ_AMS_CRM_OPTIONS = [
  "Applied Epic",
  "AMS360",
  "HawkSoft",
  "EZLynx",
  "AgencyBloc",
  "HubSpot",
  "Salesforce",
  "AgencyZoom",
  "Other",
  "None",
];

function toggleLossQPrimaryLine(current: string[], value: string) {
  if (current.includes(value)) {
    return current.filter((item) => item !== value);
  }
  return [...current, value];
}


export default function LoginPage() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [step, setStep] = useState(1);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  // LOSSQ_PASSWORD_VIEWER_EXACT_V1
  // LOSSQ_BLACK_EYE_PASSWORD_ICON_V1
  const [showPassword, setShowPassword] = useState(false);
  const [acceptedTerms, setAcceptedTerms] = useState(false);

  const [organizationName, setOrganizationName] = useState("");
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState("");
  const [companyType, setCompanyType] = useState("");
  const [phone, setPhone] = useState("");
  const [monthlyVolume, setMonthlyVolume] = useState("");
  const [primaryLines, setPrimaryLines] = useState<string[]>([]);
  const [amsSystem, setAmsSystem] = useState("");
  const [marketState, setMarketState] = useState("");

  const [message, setMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const next = params.get("next");

    if (next && next.startsWith("/")) {
      sessionStorage.setItem("lossq_next_after_login", next);
    }

    if (params.get("fresh") === "1") {
      localStorage.removeItem("lossq_token");
      localStorage.removeItem("lossq_user");
      localStorage.removeItem("lossq_login_time");
      sessionStorage.removeItem("lossq_welcome");
    }
  }, []);

  async function loginUser(cleanEmail: string, cleanPassword: string, isNewUser = false, welcomeName = "") {
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

clearLossQAccountCacheBeforeLogin();
localStorage.setItem("lossq_token", token);
        try {
          const savedToken = data?.access_token || token || localStorage.getItem("lossq_token") || "";
          if (savedToken) sessionStorage.setItem("lossq_tab_token", savedToken);
        } catch {}
localStorage.setItem("lossq_user", JSON.stringify(loginData?.user || { email: cleanEmail }));
localStorage.setItem("lossq_login_time", Date.now().toString());

    if (isNewUser) {
      const cleanWelcomeName =
        String(welcomeName || "").trim() ||
        `${loginData?.user?.first_name || ""} ${loginData?.user?.last_name || ""}`.trim() ||
        loginData?.user?.name ||
        loginData?.user?.email ||
        cleanEmail.split("@")[0];

      sessionStorage.setItem("lossq_welcome", "1");
      sessionStorage.setItem("lossq_welcome_name", cleanWelcomeName);
      localStorage.setItem("lossq_new_user_welcome", "1");
      localStorage.setItem("lossq_new_user_welcome_name", cleanWelcomeName);
      localStorage.removeItem("lossq_new_user_welcome_seen");
    } else {
      sessionStorage.removeItem("lossq_welcome");
      sessionStorage.removeItem("lossq_welcome_name");
      localStorage.removeItem("lossq_new_user_welcome");
      localStorage.removeItem("lossq_new_user_welcome_name");
    }

    const nextPath = isNewUser ? "/dashboard?welcome=1" : getSafeNextPath();
    sessionStorage.removeItem("lossq_next_after_login");
    window.location.href = nextPath;
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

      if (mode === "register" && step === 2 && !acceptedTerms) {
        setMessage("You must accept the Terms, Privacy Policy, AI Disclaimer, and Insurance Disclaimer before creating an account.");
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

      await loginUser(cleanEmail, password, true, fullName.trim());
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

        {mode === "login" && typeof window !== "undefined" && new URLSearchParams(window.location.search).get("expired") === "shared" && (
          <div className="mb-4 rounded-2xl border border-amber-400/40 bg-amber-400/10 p-4 text-sm font-semibold text-amber-100">
            Session expired because this account was signed in somewhere else.
          </div>
        )}

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

            <div className="relative">
              <input
              type={showPassword ? "text" : "password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              className="w-full bg-slate-900 border border-blue-400/40 rounded-lg px-4 py-3 mb-6 outline-none focus:border-blue-500 pr-16"
            />
              <button
                type="button"
                onClick={() => setShowPassword((current) => !current)}
                className="absolute right-3 top-1/2 -translate-y-1/2 flex h-7 w-7 items-center justify-center rounded-md text-black hover:bg-slate-200"
                aria-label={showPassword ? "Hide password" : "Show password"}
                title={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? (
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
                    <path d="M3 3l18 18" />
                    <path d="M10.58 10.58A2 2 0 0 0 12 14a2 2 0 0 0 1.42-.58" />
                    <path d="M9.88 4.24A10.94 10.94 0 0 1 12 4c7 0 10 8 10 8a18.45 18.45 0 0 1-3.17 4.73" />
                    <path d="M6.61 6.61C3.98 8.39 2 12 2 12s3 8 10 8a10.8 10.8 0 0 0 5.39-1.39" />
                  </svg>
                ) : (
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
                    <path d="M2 12s3-8 10-8 10 8 10 8-3 8-10 8S2 12 2 12Z" />
                    <circle cx="12" cy="12" r="3" />
                  </svg>
                )}
              </button>
            </div>
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

            <div className="relative">
              <input
              type={showPassword ? "text" : "password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              className="w-full bg-slate-900 border border-blue-400/40 rounded-lg px-4 py-3 mb-6 outline-none focus:border-blue-500 pr-16"
            />
              <button
                type="button"
                onClick={() => setShowPassword((current) => !current)}
                className="absolute right-3 top-1/2 -translate-y-1/2 flex h-7 w-7 items-center justify-center rounded-md text-black hover:bg-slate-200"
                aria-label={showPassword ? "Hide password" : "Show password"}
                title={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? (
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
                    <path d="M3 3l18 18" />
                    <path d="M10.58 10.58A2 2 0 0 0 12 14a2 2 0 0 0 1.42-.58" />
                    <path d="M9.88 4.24A10.94 10.94 0 0 1 12 4c7 0 10 8 10 8a18.45 18.45 0 0 1-3.17 4.73" />
                    <path d="M6.61 6.61C3.98 8.39 2 12 2 12s3 8 10 8a10.8 10.8 0 0 0 5.39-1.39" />
                  </svg>
                ) : (
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
                    <path d="M2 12s3-8 10-8 10 8 10 8-3 8-10 8S2 12 2 12Z" />
                    <circle cx="12" cy="12" r="3" />
                  </svg>
                )}
              </button>
            </div>
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

            <div className="rounded-xl border border-blue-400/50 bg-slate-900/70 p-4">
                  <p className="mb-3 text-sm font-semibold text-slate-200">Primary Lines / Coverages</p>
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                    {LOSSQ_PRIMARY_LINE_OPTIONS.map((line) => (
                      <label key={line} className="flex items-center gap-2 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-slate-200">
                        <input
                          type="checkbox"
                          checked={primaryLines.includes(line)}
                          onChange={() => setPrimaryLines(toggleLossQPrimaryLine(primaryLines, line))}
                        />
                        {line}
                      </label>
                    ))}
                  </div>
                </div>
<select
                  value={amsSystem}
                  onChange={(e) => setAmsSystem(e.target.value)}
                  className="w-full rounded-xl border border-blue-400/50 bg-slate-900/70 p-3 text-white"
                >
                  <option value="">AMS/CRM System Used</option>
                  {LOSSQ_AMS_CRM_OPTIONS.map((system) => (
                    <option key={system} value={system}>{system}</option>
                  ))}
                </select>
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
            type="button"
            onClick={nextStep}
            disabled={loading}
            className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-lg py-3 font-bold"
          >
            Continue
          </button>
        ) : (
          <>
            {mode === "register" && step === 2 && (
              <label className="mt-4 mb-4 flex items-start gap-3 rounded-xl border border-cyan-400/30 bg-cyan-400/10 p-4 text-sm text-slate-200">
                <input
                  type="checkbox"
                  checked={acceptedTerms}
                  onChange={(e) => setAcceptedTerms(e.target.checked)}
                  className="mt-1 h-4 w-4 accent-cyan-400"
                />
                <span>
                  I agree to the{" "}
                  <a href="/terms" className="text-cyan-300 hover:underline">Terms</a>,{" "}
                  <a href="/privacy" className="text-cyan-300 hover:underline">Privacy Policy</a>,{" "}
                  <a href="/ai-disclaimer" className="text-cyan-300 hover:underline">AI Disclaimer</a>, and{" "}
                  <a href="/insurance-disclaimer" className="text-cyan-300 hover:underline">Insurance Disclaimer</a>.
                </span>
              </label>
            )}

            <button
              type="button"
              onClick={submit}
              disabled={loading || (mode === "register" && step === 2 && !acceptedTerms)}
              className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg py-3 font-bold"
            >
              {loading ? "Please wait..." : mode === "login" ? "Login" : "Create Account"}
            </button>
          </>
        )}

        {mode === "register" && step === 2 && (
          <button
            type="button"
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

<div className="text-center mt-4">
  <a
    href="/forgot-password"
    className="text-sm text-blue-400 hover:text-blue-300"
  >
    Forgot password?
  </a>
</div>

        <a href="/" className="block text-center mt-6 text-blue-400 text-sm">
          Back to home
        </a>
      </div>
    </main>
  );
}

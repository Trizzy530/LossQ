"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_URL || "https://lossq-production.up.railway.app";

type OnboardingForm = {
  firstName: string;
  companyName: string;
  producingAgency: string;
  address: string;
  phone: string;
  website: string;
  supportEmail: string;
  licenseNumber: string;
  country: string;
  stateProvince: string;
  currency: string;
  languageOutput: string;
};

type SelectOption = {
  value: string;
  label: string;
};

const LANGUAGE_OPTIONS: SelectOption[] = [
  { value: "en", label: "English" },
  { value: "fr", label: "French / Français" },
  { value: "es", label: "Spanish / Español" },
  { value: "pt", label: "Portuguese / Português" },
  { value: "de", label: "German / Deutsch" },
  { value: "it", label: "Italian / Italiano" },
  { value: "nl", label: "Dutch / Nederlands" },
  { value: "ar", label: "Arabic / العربية" },
  { value: "zh", label: "Chinese / 中文" },
  { value: "ja", label: "Japanese / 日本語" },
  { value: "ko", label: "Korean / 한국어" },
  { value: "hi", label: "Hindi / हिन्दी" },
  { value: "pa", label: "Punjabi / ਪੰਜਾਬੀ" },
  { value: "ur", label: "Urdu / اردو" },
  { value: "vi", label: "Vietnamese / Tiếng Việt" },
  { value: "tl", label: "Tagalog / Filipino" },
  { value: "pl", label: "Polish / Polski" },
  { value: "ru", label: "Russian / Русский" },
  { value: "uk", label: "Ukrainian / Українська" },
  { value: "el", label: "Greek / Ελληνικά" },
  { value: "tr", label: "Turkish / Türkçe" },
  { value: "he", label: "Hebrew / עברית" },
  { value: "sw", label: "Swahili / Kiswahili" },
];

const COUNTRY_OPTIONS: SelectOption[] = [
  { value: "United States", label: "United States" },
  { value: "Canada", label: "Canada" },
  { value: "United Kingdom", label: "United Kingdom" },
  { value: "Australia", label: "Australia" },
  { value: "Mexico", label: "Mexico" },
  { value: "France", label: "France" },
  { value: "Germany", label: "Germany" },
  { value: "Spain", label: "Spain" },
  { value: "Portugal", label: "Portugal" },
  { value: "Italy", label: "Italy" },
  { value: "Netherlands", label: "Netherlands" },
  { value: "Other", label: "Other" },
];

const CURRENCY_OPTIONS: SelectOption[] = ["USD", "CAD", "GBP", "EUR", "AUD", "MXN"].map((value) => ({
  value,
  label: value,
}));

function getLossQApiBase() {
  const configured =
    process.env.NEXT_PUBLIC_API_URL ||
    process.env.NEXT_PUBLIC_BACKEND_URL ||
    process.env.NEXT_PUBLIC_API_BASE_URL ||
    "";

  if (configured) return configured.replace(/\/+$/, "");

  if (typeof window !== "undefined" && window.location.hostname.includes("lossq.com")) {
    return "https://lossq-production.up.railway.app";
  }

  return "http://localhost:8000";
}


// LOSSQ_ONBOARDING_POST_PAYMENT_REQUIRED_HELPERS_V1
function lossqOnboardingPostPaymentRequiredV1() {
 if (typeof window === "undefined") return false;

 try {
  const params = new URLSearchParams(window.location.search);
  return (
   params.get("from") === "billing" ||
   localStorage.getItem("lossq_pending_paid_onboarding") === "true" ||
   sessionStorage.getItem("lossq_pending_paid_onboarding") === "true"
  );
 } catch {
  return false;
 }
}

function lossqOnboardingClearPostPaymentFlagsV1() {
 if (typeof window === "undefined") return;

 try {
  localStorage.removeItem("lossq_pending_paid_onboarding");
  sessionStorage.removeItem("lossq_pending_paid_onboarding");
 } catch {}
}

function lossqOnboardingNextPathV1() {
 if (typeof window === "undefined") return "/dashboard?welcome=1";

 try {
  return sessionStorage.getItem("lossq_next_after_onboarding") || "/dashboard?welcome=1";
 } catch {
  return "/dashboard?welcome=1";
 }
}


// LOSSQ_STATIC_MP3_ONLY_ONBOARDING_VOICE_V1
export default function LossQOnboardingPage() {
  const router = useRouter();
  const realVoiceRef = useRef<HTMLAudioElement | null>(null);
  const musicAudioRef = useRef<HTMLAudioElement | null>(null);

  const [started, setStarted] = useState(false);
  const [musicOn, setMusicOn] = useState(false);
  const [saving, setSaving] = useState(false);
  const [voiceLoading, setVoiceLoading] = useState(false);
  const [message, setMessage] = useState("");

  const [form, setForm] = useState<OnboardingForm>({
    firstName: "",
    companyName: "",
    producingAgency: "",
    address: "",
    phone: "",
    website: "",
    supportEmail: "",
    licenseNumber: "",
    country: "United States",
    stateProvince: "",
    currency: "USD",
    languageOutput: "english",
  });

  // LOSSQ_ONBOARDING_COMPANY_PROFILE_ONLY_V1
  useEffect(() => {
    try {
      const rawUser = localStorage.getItem("lossq_user");
      const user = rawUser ? JSON.parse(rawUser) : {};
      const roleText = [
        user?.role,
        user?.user_role,
        user?.account_role,
        user?.organization_role,
        localStorage.getItem("lossq_signup_business_role"),
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();

      const canManageCompanyProfile =
        localStorage.getItem("lossq_can_manage_company_profile") === "true" ||
        roleText.includes("owner") ||
        roleText.includes("admin") ||
        roleText.includes("agency owner");

      if (!canManageCompanyProfile) {
        router.replace("/dashboard");
        return;
      }

      // LOSSQ_ONBOARDING_USE_CURRENT_USER_IDENTITY_V2
      const currentUserEmail = String(
        user?.email ||
        user?.user_email ||
        user?.email_address ||
        user?.username ||
        ""
      ).trim();

      const currentUserName = String(
        user?.first_name ||
        user?.firstName ||
        user?.name ||
        user?.full_name ||
        user?.fullName ||
        ""
      ).trim();

      const currentUserFirstName = currentUserName.split(/\s+/)[0] || "";

      const signupFirstName = String(localStorage.getItem("lossq_signup_first_name") || "").trim();
      const signupEmail = String(localStorage.getItem("lossq_signup_email") || "").trim();

      const signupEmailMatchesCurrentUser =
        Boolean(currentUserEmail) &&
        Boolean(signupEmail) &&
        signupEmail.toLowerCase() === currentUserEmail.toLowerCase();

      if (currentUserEmail && signupEmail && !signupEmailMatchesCurrentUser) {
        localStorage.removeItem("lossq_signup_first_name");
        localStorage.removeItem("lossq_signup_full_name");
        localStorage.removeItem("lossq_signup_email");
      }

      setForm((current) => ({
        ...current,
        firstName: current.firstName || currentUserFirstName || (signupEmailMatchesCurrentUser ? signupFirstName : ""),
        supportEmail: current.supportEmail || currentUserEmail || (signupEmailMatchesCurrentUser ? signupEmail : ""),
      }));
    } catch {
      router.replace("/dashboard");
    }
  }, [router]);

  const welcomeName = useMemo(() => {
    return form.firstName.trim() || "there";
  }, [form.firstName]);

  const completionScore = useMemo(() => {
    const required = [
      form.companyName,
      form.producingAgency,
      form.country,
      form.stateProvince,
      form.currency,
      form.languageOutput,
    ];

    const completed = required.filter((value) => String(value || "").trim()).length;
    return Math.round((completed / required.length) * 100);
  }, [form]);

  useEffect(() => {
    return () => {
      stopMusic();

      try {
        if (realVoiceRef.current) {
          realVoiceRef.current.pause();
          realVoiceRef.current = null;
        }
      } catch {}
    };
  }, []);

  function updateField(name: keyof OnboardingForm, value: string) {
    setForm((current) => {
      const next = { ...current, [name]: value };

      if (name === "country") {
        if (value === "Canada") next.currency = "CAD";
        if (value === "United States") next.currency = "USD";
        if (value === "United Kingdom") next.currency = "GBP";
        if (["France", "Germany", "Spain", "Portugal", "Italy", "Netherlands"].includes(value)) next.currency = "EUR";
        if (value === "Australia") next.currency = "AUD";
        if (value === "Mexico") next.currency = "MXN";
      }

      return next;
    });
  }

  async function playRealAiWelcome() {
    setVoiceLoading(true);
    setMessage("");

    try {
      const audio = new Audio("/audio/lossq-onboarding-welcome.mp3");
      audio.volume = 0.9;

      try {
        if (realVoiceRef.current) {
          realVoiceRef.current.pause();
          realVoiceRef.current = null;
        }
      } catch {}

      realVoiceRef.current = audio;
      await audio.play();
    } catch {
      setMessage("The onboarding voice file is missing. Add frontend/public/audio/lossq-onboarding-welcome.mp3.");
    } finally {
      setVoiceLoading(false);
    }
  }

  function startMusic() {
    try {
      if (musicAudioRef.current) {
        musicAudioRef.current.play().catch(() => {
          setMessage("Calm music track is not installed yet. Add frontend/public/audio/lossq-calm-onboarding.mp3.");
        });
        setMusicOn(true);
        return;
      }

      const audio = new Audio("/audio/lossq-calm-onboarding.mp3");
      audio.loop = true;
      audio.volume = 0.16;

      musicAudioRef.current = audio;

      audio
        .play()
        .then(() => {
          setMusicOn(true);
        })
        .catch(() => {
          setMusicOn(false);
          setMessage("Calm music track is not installed yet. Add frontend/public/audio/lossq-calm-onboarding.mp3.");
        });
    } catch {
      setMusicOn(false);
      setMessage("Calm music track is not available yet.");
    }
  }

  function stopMusic() {
    try {
      if (musicAudioRef.current) {
        musicAudioRef.current.pause();
        musicAudioRef.current.currentTime = 0;
        musicAudioRef.current = null;
      }
    } catch {}

    setMusicOn(false);
  }

  // LOSSQ_ONBOARDING_START_AUDIO_SYNC_V2
  function handleStartSetup() {
    setStarted(true);
    startMusic();
    void playRealAiWelcome();
  }


  // LOSSQ_ONBOARDING_SAVE_AGENCY_PROFILE_TO_SETTINGS_V2
  async function saveAgencyProfileFromOnboarding() {
    try {
      const token =
        localStorage.getItem("lossq_token") ||
        sessionStorage.getItem("lossq_tab_token") ||
        "";

      if (!token) return;

      await fetch(`${API}/auth/agency-profile`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          agency_name: form.producingAgency.trim() || form.companyName.trim(),
          agency_contact_name: localStorage.getItem("lossq_signup_full_name") || "",
          agency_email: form.supportEmail.trim(),
          agency_phone: form.phone.trim(),
          agency_address: form.address.trim(),
          agency_state: form.stateProvince.trim(),
          agency_website: form.website.trim(),
          agency_license_number: form.licenseNumber.trim(),
        }),
      });
    } catch {
      // Non-blocking: local onboarding can still complete.
    }
  }

  async function completeSetup() {
    if (!form.companyName.trim()) {
      setMessage("Please add your company or agency name before continuing.");
      return;
    }

    setSaving(true);
    setMessage("");

    try {
      localStorage.setItem("lossq_onboarding_completed_v1", "true");
      localStorage.setItem("lossq_company_name", form.companyName.trim());
      localStorage.setItem("lossq_producing_agency", form.producingAgency.trim());
      localStorage.setItem("lossq_company_address", form.address.trim());
      localStorage.setItem("lossq_company_phone", form.phone.trim());
      localStorage.setItem("lossq_company_website", form.website.trim());
      localStorage.setItem("lossq_support_email", form.supportEmail.trim());
      localStorage.setItem("lossq_agency_license_number", form.licenseNumber.trim());
      localStorage.setItem("lossq_market_country", form.country);
      localStorage.setItem("lossq_market_region_code", form.stateProvince.trim());
      localStorage.setItem("lossq_market_currency", form.currency);
      // LOSSQ_REMOVE_AUTO_LANGUAGE_OPTION_V1
      localStorage.setItem("lossq_language_output_mode", form.languageOutput);
      // LOSSQ_ONBOARDING_COMPLETE_FLAGS_V2
      localStorage.setItem("lossq_onboarding_complete", "true");
      localStorage.setItem("lossq_company_profile_onboarding_complete", "true");
      localStorage.setItem("lossq_onboarding_completed_at", new Date().toISOString());
      // LOSSQ_ONBOARDING_COMPLETE_FLAGS_V1
      localStorage.setItem("lossq_onboarding_complete", "true");
      localStorage.setItem("lossq_company_profile_onboarding_complete", "true");
      localStorage.setItem("lossq_onboarding_completed_at", new Date().toISOString());

      await saveAgencyProfileFromOnboarding();

      stopMusic();

      try {
        if (realVoiceRef.current) {
          realVoiceRef.current.pause();
          realVoiceRef.current = null;
        }
      } catch {}

      // LOSSQ_ONBOARDING_COMPLETE_POST_PAYMENT_CLEAR_V1
      const nextPath = lossqOnboardingNextPathV1();
      sessionStorage.setItem("lossq_welcome", "1");
      localStorage.setItem("lossq_new_user_welcome", "1");
      localStorage.removeItem("lossq_new_user_welcome_seen");
      lossqOnboardingClearPostPaymentFlagsV1();

      router.push(nextPath);
    } catch {
      setMessage("LossQ could not save your setup locally. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="relative min-h-screen overflow-hidden bg-[#030712] text-white">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_15%_15%,rgba(56,189,248,0.25),transparent_28%),radial-gradient(circle_at_85%_20%,rgba(124,58,237,0.22),transparent_30%),radial-gradient(circle_at_50%_100%,rgba(34,197,94,0.12),transparent_35%)]" />
      <div className="absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.035)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.035)_1px,transparent_1px)] bg-[size:56px_56px] opacity-30" />
      <div className="absolute left-1/2 top-10 h-72 w-72 -translate-x-1/2 rounded-full bg-cyan-400/10 blur-3xl" />

      <section className="relative mx-auto flex min-h-screen w-full max-w-7xl items-center px-5 py-8">
        <div className="grid w-full gap-6 lg:grid-cols-[0.9fr_1.1fr]">
          <aside className="rounded-[2rem] border border-white/10 bg-white/[0.055] p-7 shadow-2xl shadow-black/40 backdrop-blur-2xl">
            <div className="mb-7 flex items-center justify-between gap-4">
              <div>
                <div className="inline-flex rounded-full border border-cyan-300/30 bg-cyan-300/10 px-4 py-2 text-[11px] font-black uppercase tracking-[0.28em] text-cyan-200">
                  LossQ Onboarding
                </div>
                <h1 className="mt-5 max-w-xl text-4xl font-black leading-tight tracking-tight md:text-6xl">
                  Build your underwriting workspace.
                </h1>
              </div>
            </div>

            <p className="max-w-xl text-base leading-7 text-slate-300">
              Set up your company profile, choose your market, and set the language LossQ should use for
              dashboard output, underwriting narratives, and future report generation.
            </p>

            <div className="mt-7 grid gap-3 sm:grid-cols-3">
              <FeatureCard title="Voice Guided" description="Real AI welcome voice." />
              <FeatureCard title="Market Aware" description="Country, currency, and region." />
              <FeatureCard title="Report Ready" description="Branding details from day one." />
            </div>

            <div className="mt-7 rounded-3xl border border-white/10 bg-black/25 p-5">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-xs font-bold uppercase tracking-[0.24em] text-slate-500">Setup Progress</p>
                  <p className="mt-2 text-2xl font-black">{completionScore}% Complete</p>
                </div>
                <div className="h-16 w-16 rounded-2xl border border-cyan-300/30 bg-cyan-300/10 p-2">
                  <div className="flex h-full w-full items-center justify-center rounded-xl bg-cyan-300/15 text-lg font-black text-cyan-100">
                    LQ
                  </div>
                </div>
              </div>

              <div className="mt-4 h-2 overflow-hidden rounded-full bg-white/10">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-cyan-300 via-blue-400 to-violet-400 transition-all duration-500"
                  style={{ width: `${completionScore}%` }}
                />
              </div>
            </div>

            <div className="mt-7 rounded-3xl border border-cyan-300/20 bg-cyan-300/[0.06] p-5">
              <p className="text-sm font-semibold text-slate-200">
                {started
                  ? `Welcome, ${welcomeName}. LossQ is preparing your setup experience.`
                  : "Click Start Setup to play your real AI welcome voice."}
              </p>

              <div className="mt-5 flex flex-wrap gap-3">
                {!started ? (
                  <button
                    type="button"
                    onClick={handleStartSetup}
                    className="rounded-2xl bg-gradient-to-r from-cyan-300 to-blue-500 px-5 py-3 text-sm font-black text-slate-950 shadow-lg shadow-cyan-950/40 transition hover:scale-[1.02]"
                  >
                    {voiceLoading ? "Loading Voice..." : "Start Setup"}
                  </button>
                ) : (
                  <>
                    <button
                      type="button"
                      onClick={() => void playRealAiWelcome()}
                      className="rounded-2xl border border-white/10 bg-white/10 px-4 py-3 text-sm font-bold text-white transition hover:bg-white/15"
                    >
                      {voiceLoading ? "Loading Voice..." : "Replay AI Voice"}
                    </button>
                    <button
                      type="button"
                      onClick={musicOn ? stopMusic : startMusic}
                      className="rounded-2xl border border-white/10 bg-white/10 px-4 py-3 text-sm font-bold text-white transition hover:bg-white/15"
                    >
                      {musicOn ? "Calm Music Off" : "Calm Music On"}
                    </button>
                  </>
                )}
              </div>
            </div>
          </aside>

          <section className="rounded-[2rem] border border-white/10 bg-slate-950/70 p-6 shadow-2xl shadow-black/40 backdrop-blur-2xl">
            <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="text-xs font-black uppercase tracking-[0.25em] text-blue-300">Company Profile</p>
                <h2 className="mt-2 text-3xl font-black">Tell LossQ how to brand your workspace.</h2>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">
                  These fields are blank by default. The examples below are sample data only.
                </p>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/[0.06] px-4 py-3 text-xs font-bold text-slate-300">
                Required fields marked *
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <Field label="Company / Agency Name" value={form.companyName} onChange={(value) => updateField("companyName", value)} placeholder="Northstar Risk Partners" required />
              <Field label="Producing Agency Name" value={form.producingAgency} onChange={(value) => updateField("producingAgency", value)} placeholder="Meridian Advisory Group" />
              <Field label="License Number" value={form.licenseNumber} onChange={(value) => updateField("licenseNumber", value)} placeholder="NC-LIC-123456 / CA-0A12345" />
              <Field label="Support Email" value={form.supportEmail} onChange={(value) => updateField("supportEmail", value)} placeholder="support@northstarrisk.example" />
              {/* LOSSQ_LANGUAGE_OUTPUT_DROPDOWN_FINAL_V2 */}
              <SelectField label="Language Output Mode" value={form.languageOutput} onChange={(value) => updateField("languageOutput", value)} options={LANGUAGE_OPTIONS} />
              <Field label="Phone Number" value={form.phone} onChange={(value) => updateField("phone", value)} placeholder="(555) 218-4400" />
              <Field label="Website" value={form.website} onChange={(value) => updateField("website", value)} placeholder="https://www.northstarrisk.example" />
              <Field label="Address" value={form.address} onChange={(value) => updateField("address", value)} placeholder="123 Harbor Street, Suite 400" />
              <SelectField label="Country / Market" value={form.country} onChange={(value) => updateField("country", value)} options={COUNTRY_OPTIONS} />
              <Field label="State / Province" value={form.stateProvince} onChange={(value) => updateField("stateProvince", value)} placeholder="NC, ON, QC, CA, TX" />
              <SelectField label="Default Currency" value={form.currency} onChange={(value) => updateField("currency", value)} options={CURRENCY_OPTIONS} />
            </div>

            {message ? (
              <div className="mt-5 rounded-2xl border border-amber-300/30 bg-amber-300/10 px-4 py-3 text-sm font-semibold text-amber-100">
                {message}
              </div>
            ) : null}

            <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
              <button
                type="button"
                onClick={() => {
                  // LOSSQ_ONBOARDING_BLOCK_SKIP_AFTER_PAYMENT_V1
                  if (lossqOnboardingPostPaymentRequiredV1()) {
                    setMessage("Complete your company setup before opening the dashboard.");
                    return;
                  }

                  router.push("/dashboard");
                }}
                className="rounded-2xl border border-white/10 bg-white/[0.06] px-5 py-3 text-sm font-bold text-slate-200 transition hover:bg-white/10"
              >
                Skip for Now
              </button>

              <button
                type="button"
                onClick={completeSetup}
                disabled={saving}
                className="rounded-2xl bg-gradient-to-r from-blue-500 via-cyan-400 to-blue-500 px-6 py-3 text-sm font-black text-white shadow-xl shadow-blue-950/40 transition hover:scale-[1.02] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {saving ? "Saving..." : "Complete Setup & Go to Dashboard"}
              </button>
            </div>
          </section>
        </div>
      </section>
    </main>
  );
}

function FeatureCard({ title, description }: { title: string; description: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.06] p-4">
      <p className="text-sm font-black text-white">{title}</p>
      <p className="mt-1 text-xs leading-5 text-slate-400">{description}</p>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  required,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  required?: boolean;
}) {
  return (
    <label className="block">
      <span className="mb-2 block text-xs font-black uppercase tracking-[0.16em] text-slate-400">
        {label} {required ? <span className="text-cyan-300">*</span> : null}
      </span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="w-full rounded-2xl border border-white/10 bg-black/25 px-4 py-3 text-sm font-semibold text-white outline-none transition placeholder:text-slate-600 focus:border-cyan-300/70 focus:bg-black/35"
      />
    </label>
  );
}

function SelectField({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
}) {
  return (
    <label className="block">
      <span className="mb-2 block text-xs font-black uppercase tracking-[0.16em] text-slate-400">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-2xl border border-white/10 bg-black/25 px-4 py-3 text-sm font-semibold text-white outline-none transition focus:border-cyan-300/70 focus:bg-black/35"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

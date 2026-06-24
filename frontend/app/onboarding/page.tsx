"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

type OnboardingForm = {
  firstName: string;
  companyName: string;
  producingAgency: string;
  address: string;
  phone: string;
  website: string;
  supportEmail: string;
  country: string;
  stateProvince: string;
  currency: string;
  languageOutput: string;
};

const LANGUAGE_OPTIONS = [
  ["auto", "Auto - Follow Uploaded File"],
  ["en", "English"],
  ["fr", "French / Français"],
  ["es", "Spanish / Español"],
  ["pt", "Portuguese / Português"],
  ["de", "German / Deutsch"],
  ["it", "Italian / Italiano"],
  ["nl", "Dutch / Nederlands"],
  ["ar", "Arabic / العربية"],
  ["zh", "Chinese / 中文"],
  ["ja", "Japanese / 日本語"],
  ["ko", "Korean / 한국어"],
  ["hi", "Hindi / हिन्दी"],
  ["pa", "Punjabi / ਪੰਜਾਬੀ"],
  ["ur", "Urdu / اردو"],
  ["vi", "Vietnamese / Tiếng Việt"],
  ["tl", "Tagalog / Filipino"],
  ["pl", "Polish / Polski"],
  ["ru", "Russian / Русский"],
  ["uk", "Ukrainian / Українська"],
  ["el", "Greek / Ελληνικά"],
  ["tr", "Turkish / Türkçe"],
  ["he", "Hebrew / עברית"],
  ["sw", "Swahili / Kiswahili"],
];

const COUNTRY_OPTIONS = [
  "United States",
  "Canada",
  "United Kingdom",
  "Australia",
  "Mexico",
  "France",
  "Germany",
  "Spain",
  "Portugal",
  "Italy",
  "Netherlands",
  "Other",
];

const CURRENCY_OPTIONS = ["USD", "CAD", "GBP", "EUR", "AUD", "MXN"];

function readStoredUserFirstName() {
  if (typeof window === "undefined") return "";
  const possibleKeys = ["first_name", "firstName", "user_first_name", "lossq_first_name", "name"];
  for (const key of possibleKeys) {
    const value = localStorage.getItem(key);
    if (value && value.trim()) {
      return value.trim().split(" ")[0] || "";
    }
  }

  try {
    const rawUser = localStorage.getItem("user") || localStorage.getItem("lossq_user") || "";
    if (rawUser) {
      const parsed = JSON.parse(rawUser);
      const value = parsed?.first_name || parsed?.firstName || parsed?.name || "";
      return String(value || "").trim().split(" ")[0] || "";
    }
  } catch {}

  return "";
}

export default function LossQOnboardingPage() {
  const router = useRouter();
  const audioContextRef = useRef<AudioContext | null>(null);
  const gainRef = useRef<GainNode | null>(null);
  const oscillatorsRef = useRef<OscillatorNode[]>([]);

  const [started, setStarted] = useState(false);
  const [musicOn, setMusicOn] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  const [form, setForm] = useState<OnboardingForm>({
    firstName: "",
    companyName: "",
    producingAgency: "",
    address: "",
    phone: "",
    website: "",
    supportEmail: "",
    country: "United States",
    stateProvince: "",
    currency: "USD",
    languageOutput: "auto",
  });

  const welcomeName = useMemo(() => {
    return form.firstName?.trim() || "there";
  }, [form.firstName]);

  useEffect(() => {
    const storedFirstName = readStoredUserFirstName();
    const storedLanguage = localStorage.getItem("lossq_language_output_mode") || "auto";
    const storedCompany = localStorage.getItem("lossq_company_name") || "";
    const storedAgency = localStorage.getItem("lossq_producing_agency") || "";

    setForm((current) => ({
      ...current,
      firstName: current.firstName || storedFirstName,
      companyName: current.companyName || storedCompany,
      producingAgency: current.producingAgency || storedAgency,
      languageOutput: storedLanguage,
    }));
  }, []);

  useEffect(() => {
    return () => {
      stopMusic();
      try {
        window.speechSynthesis?.cancel();
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

  function speakWelcome() {
    try {
      if (!("speechSynthesis" in window)) return;

      window.speechSynthesis.cancel();

      const utterance = new SpeechSynthesisUtterance(
        `Welcome, ${welcomeName}. I’m LossQ, your underwriting intelligence assistant. Let’s set up your company profile so your reports, carrier packets, and loss run analysis are branded correctly from the start.`
      );

      utterance.rate = 0.92;
      utterance.pitch = 1;
      utterance.volume = 0.9;

      window.speechSynthesis.speak(utterance);
    } catch {}
  }

  function startMusic() {
    try {
      if (audioContextRef.current) return;

      const AudioContextClass = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (!AudioContextClass) return;

      const context = new AudioContextClass();
      const gain = context.createGain();
      gain.gain.value = 0.025;
      gain.connect(context.destination);

      const frequencies = [196, 246.94, 329.63];
      const oscillators = frequencies.map((frequency) => {
        const oscillator = context.createOscillator();
        oscillator.type = "sine";
        oscillator.frequency.value = frequency;
        oscillator.connect(gain);
        oscillator.start();
        return oscillator;
      });

      audioContextRef.current = context;
      gainRef.current = gain;
      oscillatorsRef.current = oscillators;
      setMusicOn(true);
    } catch {}
  }

  function stopMusic() {
    try {
      oscillatorsRef.current.forEach((oscillator) => {
        try {
          oscillator.stop();
          oscillator.disconnect();
        } catch {}
      });
      oscillatorsRef.current = [];

      if (gainRef.current) {
        try {
          gainRef.current.disconnect();
        } catch {}
      }

      if (audioContextRef.current) {
        try {
          audioContextRef.current.close();
        } catch {}
      }

      audioContextRef.current = null;
      gainRef.current = null;
      setMusicOn(false);
    } catch {}
  }

  function handleStartSetup() {
    setStarted(true);
    speakWelcome();
    startMusic();
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
      localStorage.setItem("lossq_market_country", form.country);
      localStorage.setItem("lossq_market_region_code", form.stateProvince.trim());
      localStorage.setItem("lossq_market_currency", form.currency);
      localStorage.setItem("lossq_language_output_mode", form.languageOutput);

      stopMusic();
      try {
        window.speechSynthesis?.cancel();
      } catch {}

      router.push("/dashboard");
    } catch {
      setMessage("LossQ could not save your setup locally. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="min-h-screen bg-slate-950 text-white">
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(circle_at_top_left,_rgba(34,211,238,0.18),_transparent_32%),radial-gradient(circle_at_bottom_right,_rgba(59,130,246,0.16),_transparent_32%)]" />

      <section className="relative mx-auto flex min-h-screen w-full max-w-6xl items-center px-6 py-10">
        <div className="grid w-full gap-8 lg:grid-cols-[0.9fr_1.1fr]">
          <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-8 shadow-2xl shadow-cyan-950/30 backdrop-blur">
            <div className="mb-8 inline-flex rounded-full border border-cyan-400/30 bg-cyan-400/10 px-4 py-2 text-xs font-bold uppercase tracking-[0.28em] text-cyan-200">
              Welcome to LossQ
            </div>

            <h1 className="text-4xl font-black tracking-tight md:text-5xl">
              Let’s personalize your underwriting workspace.
            </h1>

            <p className="mt-5 text-base leading-7 text-slate-300">
              Set your company profile, preferred language, and market context so your dashboard,
              reports, carrier packets, and loss run analysis feel ready from the first upload.
            </p>

            <div className="mt-8 rounded-2xl border border-white/10 bg-black/20 p-5">
              <p className="text-sm font-semibold text-slate-200">
                {started
                  ? `Welcome, ${welcomeName}. I’ll help get your LossQ workspace ready.`
                  : "Click Start Setup to hear your welcome message and begin."}
              </p>

              <div className="mt-5 flex flex-wrap gap-3">
                {!started ? (
                  <button
                    type="button"
                    onClick={handleStartSetup}
                    className="rounded-xl bg-cyan-400 px-5 py-3 text-sm font-black text-slate-950 transition hover:bg-cyan-300"
                  >
                    Start Setup
                  </button>
                ) : (
                  <>
                    <button
                      type="button"
                      onClick={speakWelcome}
                      className="rounded-xl border border-white/10 bg-white/10 px-4 py-3 text-sm font-bold text-white transition hover:bg-white/15"
                    >
                      Replay Voice
                    </button>
                    <button
                      type="button"
                      onClick={musicOn ? stopMusic : startMusic}
                      className="rounded-xl border border-white/10 bg-white/10 px-4 py-3 text-sm font-bold text-white transition hover:bg-white/15"
                    >
                      {musicOn ? "Music Off" : "Music On"}
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>

          <div className="rounded-3xl border border-white/10 bg-slate-900/80 p-6 shadow-2xl shadow-black/30 backdrop-blur">
            <div className="mb-6">
              <p className="text-xs font-bold uppercase tracking-[0.25em] text-cyan-300">Company Setup</p>
              <h2 className="mt-2 text-2xl font-black">Profile Details</h2>
              <p className="mt-2 text-sm text-slate-400">
                This will become the foundation for branded reports and market-aware output.
              </p>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <Field label="First Name" value={form.firstName} onChange={(value) => updateField("firstName", value)} placeholder="Tristan" />
              <Field label="Company / Agency Name" value={form.companyName} onChange={(value) => updateField("companyName", value)} placeholder="LossQ Demo Agency" required />
              <Field label="Producing Agency Name" value={form.producingAgency} onChange={(value) => updateField("producingAgency", value)} placeholder="Agency shown on reports" />
              <Field label="Support Email" value={form.supportEmail} onChange={(value) => updateField("supportEmail", value)} placeholder="support@lossq.com" />
              <Field label="Phone Number" value={form.phone} onChange={(value) => updateField("phone", value)} placeholder="(555) 555-5555" />
              <Field label="Website" value={form.website} onChange={(value) => updateField("website", value)} placeholder="https://www.company.com" />
              <Field label="Address" value={form.address} onChange={(value) => updateField("address", value)} placeholder="Street, City, State / Province" />

              <SelectField label="Country / Market" value={form.country} onChange={(value) => updateField("country", value)} options={COUNTRY_OPTIONS.map((item) => [item, item])} />
              <Field label="State / Province" value={form.stateProvince} onChange={(value) => updateField("stateProvince", value)} placeholder="NC, ON, QC, etc." />
              <SelectField label="Default Currency" value={form.currency} onChange={(value) => updateField("currency", value)} options={CURRENCY_OPTIONS.map((item) => [item, item])} />
              <SelectField label="Language Output Mode" value={form.languageOutput} onChange={(value) => updateField("languageOutput", value)} options={LANGUAGE_OPTIONS} />
            </div>

            {message ? (
              <div className="mt-5 rounded-xl border border-amber-400/30 bg-amber-400/10 px-4 py-3 text-sm font-semibold text-amber-100">
                {message}
              </div>
            ) : null}

            <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
              <button
                type="button"
                onClick={() => router.push("/dashboard")}
                className="rounded-xl border border-white/10 bg-white/5 px-5 py-3 text-sm font-bold text-slate-200 transition hover:bg-white/10"
              >
                Skip for Now
              </button>

              <button
                type="button"
                onClick={completeSetup}
                disabled={saving}
                className="rounded-xl bg-blue-500 px-6 py-3 text-sm font-black text-white transition hover:bg-blue-400 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {saving ? "Saving..." : "Complete Setup & Go to Dashboard"}
              </button>
            </div>
          </div>
        </div>
      </section>
    </main>
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
      <span className="mb-2 block text-xs font-bold uppercase tracking-[0.16em] text-slate-400">
        {label} {required ? <span className="text-cyan-300">*</span> : null}
      </span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="w-full rounded-xl border border-white/10 bg-slate-950 px-3 py-3 text-sm font-semibold text-white outline-none transition placeholder:text-slate-600 focus:border-cyan-400/60"
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
  options: string[][];
}) {
  return (
    <label className="block">
      <span className="mb-2 block text-xs font-bold uppercase tracking-[0.16em] text-slate-400">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-xl border border-white/10 bg-slate-950 px-3 py-3 text-sm font-semibold text-white outline-none transition focus:border-cyan-400/60"
      >
        {options.map(([optionValue, optionLabel]) => (
          <option key={optionValue} value={optionValue}>
            {optionLabel}
          </option>
        ))}
      </select>
    </label>
  );
}

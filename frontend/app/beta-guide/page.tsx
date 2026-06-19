"use client";

import Link from "next/link";

const guideSections = [
  {
    title: "1. Account Access",
    items: [
      "Confirm you can log in successfully.",
      "Confirm the dashboard loads without errors.",
      "Confirm the Beta Access label appears on the dashboard.",
      "Confirm your upload limit and beta expiration are visible if shown.",
    ],
  },
  {
    title: "2. Loss Run Upload",
    items: [
      "Upload a PDF, CSV, or XLSX loss run.",
      "Confirm the file uploads successfully.",
      "Confirm LossQ identifies the business or account name.",
      "Confirm LossQ identifies the carrier, policy number, and policy period when available.",
    ],
  },
  {
    title: "3. Claims Review",
    items: [
      "Confirm claims appear in the Claims Analysis section.",
      "Check claim numbers, claim dates, claim status, paid amounts, reserves, and total incurred.",
      "Confirm open and closed claims are separated correctly.",
      "Confirm claim totals look reasonable compared to the original file.",
    ],
  },
  {
    title: "4. Policy and Account Profile",
    items: [
      "Confirm policy lines are mapped correctly.",
      "Confirm claims are tied to the right policy when multiple policies exist.",
      "Confirm account profile information is accurate.",
      "Edit any incorrect profile information and confirm it saves.",
    ],
  },
  {
    title: "5. Exposure Inputs",
    items: [
      "Check whether payroll, revenue, vehicles, drivers, property values, or other exposure values were extracted.",
      "Confirm manual exposure inputs can be entered or adjusted.",
      "Confirm saved exposure inputs remain after refresh.",
    ],
  },
  {
    title: "6. Renewal and Underwriting Insights",
    items: [
      "Review the renewal score.",
      "Review risk level, underwriting concerns, and broker recommendations.",
      "Confirm the renewal summary makes sense based on the claims shown.",
      "Flag anything that seems too harsh, too favorable, or inaccurate.",
    ],
  },
  {
    title: "7. Reports and Submission Tools",
    items: [
      "Generate an executive report or carrier packet.",
      "Review PDF formatting and agency branding.",
      "Test Submission Builder.",
      "Confirm exported reports are clear and professional.",
    ],
  },
  {
    title: "8. Feedback",
    items: [
      "Report missing claims.",
      "Report incorrect totals.",
      "Report wrong policy mapping.",
      "Report confusing wording.",
      "Report upload failures or slow loading.",
      "Report anything that does not look professional or carrier-ready.",
    ],
  },
];

export default function BetaGuidePage() {
  return (
    <main className="min-h-screen bg-[#050816] text-white">
      <header className="border-b border-white/10 bg-black/30 px-6 py-5">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.3em] text-cyan-300">
              LossQ Beta
            </p>
            <h1 className="mt-2 text-3xl font-black">Beta Testing Guide</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">
              Use this guide to test LossQ during beta. The goal is to confirm that uploads,
              claims, policy mapping, exposure inputs, renewal insights, reports, and submission
              tools are accurate, clear, and professional.
            </p>
          </div>

          <div className="flex flex-wrap gap-3">
            <Link
              href="/dashboard"
              className="rounded-xl border border-white/10 px-4 py-2 text-sm font-bold text-slate-200 hover:bg-white/10"
            >
              Back to Dashboard
            </Link>
            <Link
              href="/settings"
              className="rounded-xl border border-cyan-400/30 bg-cyan-400/10 px-4 py-2 text-sm font-bold text-cyan-100 hover:bg-cyan-400/20"
            >
              Settings
            </Link>
          </div>
        </div>
      </header>

      <section className="mx-auto max-w-6xl space-y-6 px-6 py-8">
        <div className="rounded-3xl border border-cyan-400/20 bg-cyan-400/10 p-6">
          <h2 className="text-xl font-black text-cyan-100">What beta users should do</h2>
          <p className="mt-3 text-sm leading-6 text-cyan-50/90">
            Upload real or sample commercial loss runs, review the results carefully, and report
            anything that looks incorrect, confusing, incomplete, or not ready for an insurance
            professional.
          </p>
        </div>

        <div className="grid gap-5">
          {guideSections.map((section) => (
            <article
              key={section.title}
              className="rounded-2xl border border-white/10 bg-white/[0.03] p-6 shadow-xl"
            >
              <h2 className="text-lg font-black text-white">{section.title}</h2>
              <ul className="mt-4 space-y-3 text-sm leading-6 text-slate-300">
                {section.items.map((item) => (
                  <li key={item} className="flex gap-3">
                    <span className="mt-2 h-2 w-2 shrink-0 rounded-full bg-cyan-300" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </article>
          ))}
        </div>

        <div className="rounded-3xl border border-emerald-400/20 bg-emerald-400/10 p-6">
          <h2 className="text-xl font-black text-emerald-100">How to report feedback</h2>
          <p className="mt-3 text-sm leading-6 text-emerald-50/90">
            Use the Report Issue button inside LossQ or email hello@lossq.com. Include the file
            type, what you expected to happen, and what LossQ showed instead.
          </p>
        </div>
      </section>
    </main>
  );
}

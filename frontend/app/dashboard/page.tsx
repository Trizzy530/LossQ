"use client";

import { useRouter } from "next/navigation";

export default function DashboardPage() {
  const router = useRouter();

  return (
    <main className="min-h-screen bg-[#050816] text-white">
      <header className="border-b border-white/10 bg-black/30 px-6 py-4 flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold">LossQ Underwriting AI</h1>
          <p className="text-sm text-slate-400">
            Claims intelligence and underwriting analytics
          </p>
        </div>

        <button
          onClick={() => {
            localStorage.removeItem("lossq_token");
            router.push("/");
          }}
          className="rounded-xl border border-white/10 px-4 py-2 hover:bg-white/10"
        >
          Logout
        </button>
      </header>

      <section className="p-6 grid gap-6">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {[
            ["Loss Runs", "248"],
            ["Claims", "1,429"],
            ["Risk Score", "82"],
            ["Renewal Impact", "$184K"],
          ].map(([title, value]) => (
            <div
              key={title}
              className="rounded-2xl bg-white/5 border border-white/10 p-5"
            >
              <p className="text-slate-400 text-sm">{title}</p>
              <h2 className="text-3xl font-bold mt-2">{value}</h2>
            </div>
          ))}
        </div>

        <div className="rounded-3xl bg-white/5 border border-white/10 p-6">
          <h2 className="text-xl font-bold mb-4">
            Claims Intelligence Panel
          </h2>

          <div className="space-y-4">
            {[
              ["WC-2024-0182", "$42,100", "Moderate severity"],
              ["AUTO-2023-0441", "$12,900", "Low severity"],
              ["GL-2025-0098", "$88,400", "High severity"],
            ].map(([claim, amount, note]) => (
              <div
                key={claim}
                className="rounded-2xl bg-black/30 border border-white/10 p-4 flex justify-between"
              >
                <div>
                  <p className="font-semibold">{claim}</p>
                  <p className="text-sm text-slate-400">{note}</p>
                </div>

                <div className="text-cyan-300 font-bold">
                  {amount}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="grid md:grid-cols-2 gap-6">
          <div className="rounded-3xl bg-white/5 border border-white/10 p-6">
            <h2 className="text-xl font-bold mb-4">Upload Loss Runs</h2>

            <div className="rounded-2xl border border-dashed border-cyan-400/30 p-10 text-center">
              <p className="font-semibold">
                Upload PDF, Excel, or image files
              </p>

              <button className="mt-5 rounded-xl bg-cyan-400 text-black px-5 py-3 font-bold">
                Select Files
              </button>
            </div>
          </div>

          <div className="rounded-3xl bg-white/5 border border-white/10 p-6">
            <h2 className="text-xl font-bold mb-4">AI Copilot</h2>

            <div className="rounded-2xl bg-black/30 border border-cyan-400/20 p-4 text-sm text-slate-300">
              Renewal exposure is trending moderate with elevated GL severity
              patterns. Recommend deductible review and carrier remarketing.
            </div>

            <button className="mt-5 w-full rounded-xl bg-cyan-400 text-black py-3 font-bold">
              Generate Renewal Memo
            </button>
          </div>
        </div>
      </section>
    </main>
  );
}
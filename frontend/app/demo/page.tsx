export default function DemoPage() {
 return (
  <main className="min-h-screen bg-[#020617] text-white overflow-hidden">
   <div className="fixed inset-0 bg-[radial-gradient(circle_at_top_left,#1d4ed866,transparent_28%),radial-gradient(circle_at_top_right,#0ea5e955,transparent_30%),radial-gradient(circle_at_bottom,#312e8155,transparent_35%)]" />
   <div className="fixed inset-0 bg-[linear-gradient(to_right,rgba(255,255,255,0.04)_1px,transparent_1px),linear-gradient(to_bottom,rgba(255,255,255,0.04)_1px,transparent_1px)] bg-[size:72px_72px] opacity-20" />

   <section className="relative mx-auto max-w-7xl px-6 py-10 md:py-16">
    <div className="mb-8 flex items-center justify-between gap-4">
     <a href="/" className="text-sm font-bold text-blue-200 hover:text-white">
      ← Back to Home
     </a>

     <a
      href="/login"
      className="rounded-xl bg-blue-500 px-5 py-3 text-sm font-black text-white shadow-lg shadow-blue-500/25 hover:bg-blue-400"
     >
      Start Using LossQ
     </a>
    </div>

    <div className="grid grid-cols-1 gap-10 lg:grid-cols-[1.1fr_0.9fr] lg:items-center">
     <div>
      <div className="mb-5 inline-flex rounded-full border border-blue-400/30 bg-blue-500/10 px-4 py-2 text-sm font-bold uppercase tracking-[0.22em] text-blue-200">
       LossQ Demo
      </div>

      <h1 className="text-4xl font-black leading-tight tracking-tight md:text-6xl">
       See how LossQ turns loss runs into underwriting intelligence.
      </h1>

      <p className="mt-6 max-w-2xl text-lg leading-8 text-slate-300">
       Watch how LossQ uploads a PDF, CSV, or Excel loss run, extracts the account profile,
       organizes claims, scores renewal risk, builds carrier strategy, and prepares a submission package.
      </p>

      <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-3">
       <div className="rounded-2xl border border-white/10 bg-white/5 p-5">
        <div className="text-3xl font-black text-white">1</div>
        <p className="mt-2 text-sm text-slate-300">Upload the loss run.</p>
       </div>

       <div className="rounded-2xl border border-white/10 bg-white/5 p-5">
        <div className="text-3xl font-black text-white">2</div>
        <p className="mt-2 text-sm text-slate-300">LossQ extracts claims and policy data.</p>
       </div>

       <div className="rounded-2xl border border-white/10 bg-white/5 p-5">
        <div className="text-3xl font-black text-white">3</div>
        <p className="mt-2 text-sm text-slate-300">Generate renewal and carrier intelligence.</p>
       </div>
      </div>
     </div>

     <div className="rounded-[2rem] border border-white/10 bg-slate-950/80 p-4 shadow-[0_0_60px_rgba(59,130,246,0.22)]">
      <div className="overflow-hidden rounded-[1.5rem] border border-blue-400/20 bg-black">
       <video
        className="aspect-video w-full bg-black"
        controls
        preload="metadata"
        poster="/lossq-logo-style2.png"
       >
        <source src="/videos/lossq-demo.mp4" type="video/mp4" />
        Your browser does not support the video tag.
       </video>
      </div>

      <p className="mt-4 text-sm leading-6 text-slate-400">
       Demo video: upload, extraction, claims review, renewal risk, premium forecast, carrier appetite,
       submission builder, reports, and carrier packet generation.
      </p>
     </div>
    </div>

    <div className="mt-14 grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-4">
     {[
      ["Universal Upload", "PDF, CSV, and Excel loss runs are converted into structured underwriting data."],
      ["Claims Intelligence", "LossQ identifies open claims, severity, reserves, claim timing, and line of business."],
      ["Renewal Strategy", "Renewal Risk, Premium Forecast, Carrier Appetite, and Submission Builder each provide their own reasoning."],
      ["Carrier-Ready Output", "Generate executive reports, carrier packets, and talking points for submission strategy."]
     ].map(([title, text]) => (
      <div key={title} className="rounded-3xl border border-white/10 bg-white/5 p-6">
       <h3 className="text-xl font-black text-white">{title}</h3>
       <p className="mt-3 text-sm leading-6 text-slate-300">{text}</p>
      </div>
     ))}
    </div>
   </section>
  </main>
 );
}

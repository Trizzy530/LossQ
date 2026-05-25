export default function LandingPage() {
  return (
    <main className="min-h-screen bg-slate-950 text-white">
      <section className="px-10 py-8 max-w-7xl mx-auto">
        <nav className="flex justify-between items-center mb-20">
          <h1 className="text-3xl font-bold">LossQ</h1>

          <div className="flex gap-4">
            <a href="/pricing" className="text-slate-300 hover:text-white">
              Pricing
            </a>
            <a
              href="/login"
              className="bg-blue-600 hover:bg-blue-700 px-5 py-3 rounded-lg font-semibold"
            >
              Sign In
            </a>
          </div>
        </nav>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-14 items-center">
          <div>
            <p className="text-blue-400 font-semibold mb-4">
              AI UNDERWRITING INTELLIGENCE FOR COMMERCIAL BROKERS
            </p>

            <h2 className="text-6xl font-bold leading-tight mb-6">
              Turn loss runs into carrier-ready underwriting intelligence.
            </h2>

            <p className="text-xl text-slate-300 leading-8 mb-8">
              LossQ helps brokers analyze loss runs, identify claim concerns,
              generate renewal memos, prepare carrier submissions, and explain
              account risk faster.
            </p>

            <div className="flex gap-4">
              <a
                href="/login"
                className="bg-blue-600 hover:bg-blue-700 px-7 py-4 rounded-xl font-semibold"
              >
                Launch Demo
              </a>

              <a
                href="/demo"
                className="bg-slate-800 hover:bg-slate-700 px-7 py-4 rounded-xl font-semibold"
              >
                View Instant Demo
              </a>
            </div>

            <p className="text-slate-500 mt-5">
              Built for commercial brokers, renewal teams, and agencies.
            </p>
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow-2xl">
            <div className="grid grid-cols-2 gap-4 mb-6">
              <Card label="Renewal Risk" value="YELLOW" tone="yellow" />
              <Card label="Open Claims" value="7" />
              <Card label="Total Incurred" value="$842K" />
              <Card label="Reserve Pressure" value="High" tone="red" />
            </div>

            <div className="bg-slate-800 rounded-2xl p-5 mb-4">
              <h3 className="font-semibold mb-2">
                AI Underwriting Summary
              </h3>
              <p className="text-slate-300 text-sm leading-6">
                The account presents moderate renewal concern driven by open
                claims, reserve pressure, and elevated auto liability severity.
                Broker should provide claim narratives, reserve explanations,
                and corrective action documentation before marketing.
              </p>
            </div>

            <div className="bg-slate-800 rounded-2xl p-5">
              <h3 className="font-semibold mb-3">
                Carrier Submission Readiness
              </h3>

              <div className="space-y-3 text-sm">
                <Row label="Loss run analysis" value="Complete" />
                <Row label="Renewal memo" value="Generated" />
                <Row label="Claim narratives" value="Needs Review" />
                <Row label="Carrier packet" value="Ready" />
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="px-10 py-20 max-w-7xl mx-auto">
        <h2 className="text-4xl font-bold text-center mb-4">
          Built for the commercial renewal workflow
        </h2>

        <p className="text-slate-400 text-center max-w-3xl mx-auto mb-12">
          LossQ does more than parse files. It helps brokers understand what
          carriers will question before submission.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <Feature
            title="Upload Loss Runs"
            text="Upload PDF, Excel, or CSV loss runs and organize claims by policy workspace."
          />
          <Feature
            title="AI Claim Intelligence"
            text="Analyze severity, litigation exposure, reserve pressure, and renewal impact."
          />
          <Feature
            title="Carrier-Ready Reports"
            text="Generate renewal memos, loss run exports, and submission packets."
          />
          <Feature
            title="Policy Workspaces"
            text="Manage different insureds, carriers, policies, and renewal accounts."
          />
          <Feature
            title="Underwriting Copilot"
            text="Ask questions about claims, trends, litigation, reserves, and broker strategy."
          />
          <Feature
            title="Trend Analytics"
            text="See open claim aging, severity heat maps, incurred trends, and reserve pressure."
          />
        </div>
      </section>

      <section className="px-10 py-20 bg-slate-900 border-y border-slate-800">
        <div className="max-w-5xl mx-auto text-center">
          <h2 className="text-4xl font-bold mb-6">
            Designed to help brokers win renewals.
          </h2>

          <p className="text-xl text-slate-300 leading-8 mb-8">
            LossQ gives brokers a faster way to turn messy loss runs into
            organized underwriting stories carriers can understand.
          </p>

          <a
            href="/login"
            className="bg-blue-600 hover:bg-blue-700 px-8 py-4 rounded-xl font-semibold"
          >
            Start Demo
          </a>
        </div>
      </section>
    </main>
  );
}

function Card({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "red" | "yellow";
}) {
  const color =
    tone === "red"
      ? "text-red-400"
      : tone === "yellow"
      ? "text-yellow-400"
      : "text-white";

  return (
    <div className="bg-slate-800 rounded-2xl p-5">
      <p className="text-slate-400 text-sm mb-2">{label}</p>
      <p className={`text-2xl font-bold ${color}`}>{value}</p>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between border-b border-slate-700 pb-2">
      <span className="text-slate-400">{label}</span>
      <span className="text-white">{value}</span>
    </div>
  );
}

function Feature({ title, text }: { title: string; text: string }) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
      <h3 className="text-xl font-semibold mb-3">{title}</h3>
      <p className="text-slate-400 leading-7">{text}</p>
    </div>
  );
}
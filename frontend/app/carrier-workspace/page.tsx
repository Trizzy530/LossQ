"use client";

export default function CarrierWorkspacePage() {
  return (
    <main className="min-h-screen bg-slate-950 text-white p-10">
      <div className="max-w-6xl mx-auto">
        <div className="flex justify-between items-start mb-10">
          <div>
            <h1 className="text-5xl font-bold">Carrier Workspace</h1>
            <p className="text-slate-400 mt-2">
              Broker-ready submission center for carrier packets, renewal memos,
              and underwriting exports.
            </p>
          </div>

          <a
            href="/dashboard"
            className="bg-slate-800 hover:bg-slate-700 px-5 py-3 rounded-lg"
          >
            Back to Dashboard
          </a>
        </div>

        <section className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-10">
          <Card title="Carrier Packet" description="Generate submission-ready packet." />
          <Card title="Renewal Memo" description="Create broker-ready AI narrative." />
          <Card title="Loss Run Export" description="Export polished carrier loss run." />
        </section>

        <section className="bg-slate-900 border border-slate-800 rounded-2xl p-8">
          <h2 className="text-3xl font-semibold mb-4">Workspace Status</h2>
          <p className="text-slate-300">
            Carrier workspace shell is ready. Next step is wiring it to the
            dashboard account profile, selected policy, reports API, and AI
            renewal memo generator.
          </p>
        </section>
      </div>
    </main>
  );
}

function Card({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
      <h3 className="text-2xl font-semibold mb-3">{title}</h3>
      <p className="text-slate-400">{description}</p>
    </div>
  );
}
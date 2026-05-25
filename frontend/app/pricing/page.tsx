export default function PricingPage() {
  return (
    <main className="min-h-screen bg-slate-950 text-white px-8 py-24">
      <div className="max-w-7xl mx-auto">
        <div className="text-center mb-20">
          <h1 className="text-6xl font-bold">
            Pricing
          </h1>

          <p className="text-slate-300 text-xl mt-6">
            Simple pricing for brokers, agencies, and underwriting teams.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          <PricingCard
            title="Starter"
            price="$99"
            features={[
              "100 claim analyses / month",
              "AI underwriting summaries",
              "Renewal risk scoring",
              "PDF executive reports",
            ]}
          />

          <PricingCard
            title="Professional"
            price="$299"
            featured
            features={[
              "Unlimited analyses",
              "Submission readiness engine",
              "Trend intelligence",
              "Multi-year uploads",
              "Advanced analytics",
            ]}
          />

          <PricingCard
            title="Enterprise"
            price="Custom"
            features={[
              "Agency-wide deployment",
              "Carrier integrations",
              "Custom underwriting workflows",
              "Dedicated onboarding",
            ]}
          />
        </div>
      </div>
    </main>
  );
}

function PricingCard({
  title,
  price,
  features,
  featured = false,
}: {
  title: string;
  price: string;
  features: string[];
  featured?: boolean;
}) {
  return (
    <div
      className={`rounded-3xl border p-10 ${
        featured
          ? "border-blue-500 bg-blue-500/10"
          : "border-slate-800 bg-slate-900"
      }`}
    >
      <h2 className="text-3xl font-bold">
        {title}
      </h2>

      <p className="text-5xl font-bold mt-6">
        {price}
      </p>

      <div className="mt-10 space-y-4">
        {features.map((feature) => (
          <div
            key={feature}
            className="text-slate-300"
          >
            • {feature}
          </div>
        ))}
      </div>

      <a
        href="/demo"
        className={`block text-center rounded-xl px-6 py-4 mt-10 font-semibold ${
          featured
            ? "bg-blue-600 hover:bg-blue-700"
            : "bg-slate-800 hover:bg-slate-700"
        }`}
      >
        Try Demo
      </a>
    </div>
  );
}
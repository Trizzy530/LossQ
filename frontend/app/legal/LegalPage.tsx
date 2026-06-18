type LegalSection = {
  heading: string;
  body: string[];
};

export default function LegalPage({
  title,
  subtitle,
  sections,
}: {
  title: string;
  subtitle: string;
  sections: LegalSection[];
}) {
  return (
    <main className="min-h-screen bg-[#050816] text-white">
      <section className="mx-auto max-w-5xl px-6 py-14">
        <a href="/legal" className="text-sm text-cyan-300 hover:text-cyan-200">
          ← Back to Legal Center
        </a>

        <div className="mt-8 rounded-3xl border border-white/10 bg-white/[0.04] p-8 shadow-2xl">
          <p className="text-sm font-semibold text-cyan-300">LossQ Legal</p>
          <h1 className="mt-3 text-4xl font-bold tracking-tight">{title}</h1>
          <p className="mt-4 max-w-3xl text-slate-300">{subtitle}</p>

          <div className="mt-8 space-y-6">
            {sections.map((section) => (
              <section
                key={section.heading}
                className="rounded-2xl border border-white/10 bg-slate-950/50 p-5"
              >
                <h2 className="text-xl font-bold text-white">{section.heading}</h2>
                <div className="mt-3 space-y-3 text-sm leading-6 text-slate-300">
                  {section.body.map((paragraph) => (
                    <p key={paragraph}>{paragraph}</p>
                  ))}
                </div>
              </section>
            ))}
          </div>
        </div>
      </section>
    </main>
  );
}

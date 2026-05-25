"use client";

export default function AdminPage() {
  return (
    <main className="min-h-screen bg-slate-950 text-white p-8">
      <div className="max-w-6xl mx-auto">
        <a href="/" className="text-blue-400">← Back to Dashboard</a>

        <h1 className="text-4xl font-bold mt-6 mb-4">
          LossQ Admin Panel
        </h1>

        <p className="text-slate-300">
          Admin page loaded successfully.
        </p>
      </div>
    </main>
  );
}
export default function Loading() {
  return (
    <main className="min-h-screen bg-[#020617] text-white flex items-center justify-center">
      <div className="text-center">
        <img
          src="/lossq-logo-style2.png"
          alt="LossQ"
          className="w-72 mx-auto mb-6 rounded-2xl"
        />
        <div className="text-sm uppercase tracking-[0.35em] text-blue-300">
          Loading LossQ
        </div>
      </div>
    </main>
  );
}
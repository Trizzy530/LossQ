"use client";

import { useEffect, useState } from "react";

export default function LandingPage() {
  const [email, setEmail] = useState("");
  const [joined, setJoined] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted) return;

    const cursor = document.getElementById("cursor");
    const ring = document.getElementById("cursorRing");

    let mx = window.innerWidth / 2;
    let my = window.innerHeight / 2;
    let rx = mx;
    let ry = my;
    let animationFrame = 0;

    function move(e: MouseEvent) {
      mx = e.clientX;
      my = e.clientY;

      if (cursor) {
        cursor.style.left = `${mx}px`;
        cursor.style.top = `${my}px`;
      }
    }

    function animateRing() {
      rx += (mx - rx) * 0.12;
      ry += (my - ry) * 0.12;

      if (ring) {
        ring.style.left = `${rx}px`;
        ring.style.top = `${ry}px`;
      }

      animationFrame = requestAnimationFrame(animateRing);
    }

    document.addEventListener("mousemove", move);
    animateRing();

    const reveals = document.querySelectorAll(".reveal");

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry, index) => {
          if (entry.isIntersecting) {
            setTimeout(() => {
              entry.target.classList.add("visible");
            }, index * 80);
          }
        });
      },
      { threshold: 0.1 }
    );

    reveals.forEach((el) => observer.observe(el));

    return () => {
      document.removeEventListener("mousemove", move);
      cancelAnimationFrame(animationFrame);
      observer.disconnect();
    };
  }, [mounted]);

  function handleSignup() {
    if (!email || !email.includes("@")) {
      alert("Enter a valid email.");
      return;
    }

    setJoined(true);
  }

  if (!mounted) {
    return (
      <main
        style={{
          minHeight: "100vh",
          background: "#030508",
          color: "#f0f4ff",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          overflow: "hidden",
          fontFamily: "Arial, Helvetica, sans-serif",
        }}
      >
        <div style={{ textAlign: "center" }}>
          <div
            style={{
              fontSize: 28,
              fontWeight: 900,
              letterSpacing: "0.08em",
              marginBottom: 14,
            }}
          >
            Loss<span style={{ color: "#0078ff" }}>Q</span>
          </div>
          <div
            style={{
              fontSize: 11,
              letterSpacing: "0.28em",
              textTransform: "uppercase",
              color: "#60a5fa",
            }}
          >
            AI Underwriting Platform
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="lossq-landing">
      <div className="cursor" id="cursor" />
      <div className="cursor-ring" id="cursorRing" />
      <div className="grid-bg" />
      <div className="noise" />

      <nav>
        <div className="logo">
          Loss<span>Q</span>
        </div>

        <ul className="nav-links">
          <li><a href="#features">Features</a></li>
          <li><a href="#how">How It Works</a></li>
          <li><a href="#pricing">Pricing</a></li>
          <li><a href="/login?fresh=1" className="nav-cta">Launch App</a></li>
        </ul>
      </nav>

      <section className="hero">
        <div className="orb" />

        <div className="hero-badge">⚡ AI Underwriting Intelligence</div>

        <h1>
          Insurance Loss Runs.
          <em> Instant.</em>
          <span className="accent">Intelligent.</span>
        </h1>

        <p className="hero-sub">
          LossQ is the AI underwriting platform that processes loss runs,
          generates carrier packets, renewal memos, and claim intelligence —
          all in one place.
        </p>

        <div className="hero-actions">
          <a href="/login?fresh=1" className="btn-primary">
            Launch App →
          </a>

          <a href="#how" className="btn-secondary">
            See How It Works
          </a>
        </div>

        <div className="stat-bar">
          <div className="stat">
            <span className="stat-num">&lt;5s</span>
            <span className="stat-label">Loss Run Processing</span>
          </div>

          <div className="stat">
            <span className="stat-num">AI</span>
            <span className="stat-label">Powered Intelligence</span>
          </div>

          <div className="stat">
            <span className="stat-num">PDF</span>
            <span className="stat-label">Carrier Packets</span>
          </div>
        </div>
      </section>

      <div className="ticker-wrap">
        <div className="ticker-track">
          {[
            "Instant Loss Run Processing",
            "AI Renewal Risk Scoring",
            "Carrier Packet Generation",
            "Claims Intelligence Panel",
            "Executive PDF Reports",
            "Broker Narrative Generator",
            "Multi-Policy Workspaces",
            "Timeline Analytics",
            "Instant Loss Run Processing",
            "AI Renewal Risk Scoring",
            "Carrier Packet Generation",
            "Claims Intelligence Panel",
          ].map((item, index) => (
            <span className="ticker-item" key={`${item}-${index}`}>
              <span>→</span> {item}
            </span>
          ))}
        </div>
      </div>

      <section className="section" id="features">
        <span className="section-label reveal">Platform Features</span>
        <h2 className="section-title reveal">
          Everything an underwriter <em>actually</em> needs.
        </h2>

        <div className="features-grid reveal">
          <Feature icon="⚡" title="Instant Loss Run Processing" text="Upload PDF, Excel, or CSV loss runs. LossQ extracts, normalizes, and organizes claims by policy." tag="// File → Intelligence" />
          <Feature icon="🧠" title="Claims Intelligence Panel" text="Clickable claim breakdowns, severity analysis, reserve pressure, litigation exposure, and account risk." tag="// AI Analytics Engine" />
          <Feature icon="📊" title="Renewal Risk Score" text="AI-generated renewal signals based on claim frequency, severity, development, and total incurred." tag="// Predictive Intelligence" />
          <Feature icon="📋" title="Carrier Packet Generation" text="Generate professional carrier-ready packets, executive reports, and loss run summaries." tag="// One-Click Output" />
          <Feature icon="✍️" title="Broker Narrative Generator" text="AI writes renewal memos and underwriting narratives based on the selected policy." tag="// Memo Builder" />
          <Feature icon="🏢" title="Multi-Policy Workspaces" text="Keep each client, policy, claims file, Copilot answer, and export separated." tag="// Account Isolation" />
        </div>
      </section>

      <section className="how-section" id="how">
        <div className="how-inner">
          <span className="section-label reveal">How It Works</span>
          <h2 className="section-title reveal">
            From upload to insight in <em>seconds.</em>
          </h2>

          <div className="steps reveal">
            <Step num="01" title="Upload Loss Run" text="Drop in PDF, Excel, or CSV claim data." />
            <Step num="02" title="AI Parses Claims" text="LossQ extracts and organizes the claim information." />
            <Step num="03" title="Generate Intelligence" text="Risk scores, summaries, charts, and memos are created." />
            <Step num="04" title="Export & Submit" text="Download polished reports and carrier packets." />
          </div>
        </div>
      </section>

      <section className="section" id="pricing">
        <span className="section-label reveal">Pricing</span>
        <h2 className="section-title reveal">
          Launch pricing built for <em>commercial agencies.</em>
        </h2>

        <div className="pricing-grid reveal">
          <Price featured tier="Founding Agency" price="$99" desc="Limited launch offer for the first 10 agencies that help shape LossQ." features={["First 10 agencies only", "5 users", "Unlimited uploads", "Professional features", "Locked-in pricing", "Priority support"]} />
          <Price tier="Starter" price="$199" desc="For independent brokers, solo producers, and small agencies." features={["1 user", "50 uploads/month", "Loss run uploads", "AI summaries", "Renewal memos", "PDF exports"]} />
          <Price tier="Professional" price="$499" desc="For commercial lines teams and growing agencies." features={["Up to 5 users", "Unlimited uploads", "Carrier appetite", "Premium forecast", "Submission builder", "Priority support"]} />
          <Price tier="Agency" price="$999" desc="For agency owners, multi-user teams, and regional agencies." features={["Up to 25 users", "Unlimited uploads", "Team management", "User permissions", "Audit logs", "Advanced analytics"]} />
        </div>
      </section>

      <section className="cta-section" id="waitlist">
        <div className="cta-box">
          <h2>Get Early Access to LossQ</h2>
          <p>
            Join the beta. Be among the first agencies to process loss runs with AI.
          </p>

          {!joined ? (
            <div className="signup-form">
              <input
                type="email"
                placeholder="your@agency.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />

              <button onClick={handleSignup}>Join Beta</button>
            </div>
          ) : (
            <p className="success-msg show">
              ✓ You&apos;re on the list. We&apos;ll be in touch shortly.
            </p>
          )}

          <p className="form-note">
            No credit card required · Founder pricing available
          </p>
        </div>
      </section>

      <footer>
        <div className="footer-logo">
          Loss<span>Q</span>
        </div>

        <ul className="footer-links">
          <li><a href="#features">Features</a></li>
          <li><a href="#pricing">Pricing</a></li>
          <li><a href="/legal">Legal</a></li>
          <li><a href="/terms">Terms</a></li>
          <li><a href="/privacy">Privacy</a></li>
          <li><a href="/data-security">Data Security</a></li>
          <li><a href="/refund-policy">Refund Policy</a></li>
          <li><a href="/ai-disclaimer">AI Disclaimer</a></li>
          <li><a href="/insurance-disclaimer">Insurance Disclaimer</a></li>
          <li><a href="mailto:hello@lossq.com">Contact</a></li>
        </ul>

        <div className="footer-copy">© 2026 LossQ. All rights reserved.</div>
      </footer>

      <style jsx global>{`
        html {
          scroll-behavior: smooth;
        }

        body {
          margin: 0;
          background: #030508;
        }

        .lossq-landing {
          min-height: 100vh;
          background: #030508;
          color: #f0f4ff;
          overflow-x: hidden;
          cursor: none;
          font-family: Arial, Helvetica, sans-serif;
        }

        .cursor {
          width: 12px;
          height: 12px;
          background: #0078ff;
          border-radius: 50%;
          position: fixed;
          top: 0;
          left: 0;
          pointer-events: none;
          z-index: 9999;
          transform: translate(-50%, -50%);
          mix-blend-mode: screen;
        }

        .cursor-ring {
          width: 36px;
          height: 36px;
          border: 1px solid rgba(0, 120, 255, 0.5);
          border-radius: 50%;
          position: fixed;
          top: 0;
          left: 0;
          pointer-events: none;
          z-index: 9998;
          transform: translate(-50%, -50%);
        }

        .grid-bg {
          position: fixed;
          inset: 0;
          background-image:
            linear-gradient(rgba(0, 120, 255, 0.04) 1px, transparent 1px),
            linear-gradient(90deg, rgba(0, 120, 255, 0.04) 1px, transparent 1px);
          background-size: 60px 60px;
          pointer-events: none;
          z-index: 0;
        }

        .noise {
          position: fixed;
          inset: 0;
          opacity: 0.025;
          background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E");
          pointer-events: none;
          z-index: 0;
        }

        nav {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          z-index: 100;
          padding: 20px 48px;
          display: flex;
          align-items: center;
          justify-content: space-between;
          background: rgba(3, 5, 8, 0.8);
          backdrop-filter: blur(20px);
          border-bottom: 1px solid rgba(0, 120, 255, 0.15);
        }

        .logo,
        .footer-logo {
          font-size: 22px;
          font-weight: 900;
          letter-spacing: -0.5px;
        }

        .logo span,
        .footer-logo span {
          color: #0078ff;
        }

        .nav-links,
        .footer-links {
          display: flex;
          align-items: center;
          gap: 32px;
          list-style: none;
          margin: 0;
          padding: 0;
        }

        .nav-links a,
        .footer-links a {
          font-size: 12px;
          color: #6b7fa8;
          text-decoration: none;
          letter-spacing: 0.1em;
          text-transform: uppercase;
        }

        .nav-links a:hover,
        .footer-links a:hover {
          color: white;
        }

        .nav-cta {
          color: #0078ff !important;
          border: 1px solid #0078ff;
          padding: 8px 20px;
          border-radius: 4px;
        }

        .nav-cta:hover {
          background: #0078ff;
          color: white !important;
        }

        .hero {
          min-height: 100vh;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 120px 48px 80px;
          position: relative;
          z-index: 1;
          text-align: center;
        }

        .orb {
          position: absolute;
          width: 600px;
          height: 600px;
          background: radial-gradient(circle, rgba(0, 120, 255, 0.12) 0%, transparent 70%);
          border-radius: 50%;
          top: 50%;
          left: 50%;
          transform: translate(-50%, -50%);
          pointer-events: none;
          animation: pulse 4s ease-in-out infinite;
        }

        .hero-badge,
        .section-label {
          font-size: 11px;
          color: #0078ff;
          letter-spacing: 0.2em;
          text-transform: uppercase;
        }

        .hero-badge {
          border: 1px solid rgba(0, 120, 255, 0.15);
          padding: 6px 16px;
          border-radius: 100px;
          margin-bottom: 40px;
          background: rgba(0, 120, 255, 0.05);
        }

        .hero h1 {
          font-size: clamp(48px, 7vw, 96px);
          font-weight: 900;
          line-height: 1;
          letter-spacing: -2px;
          max-width: 900px;
          margin: 0;
        }

        .hero h1 em {
          font-style: normal;
          color: #0078ff;
        }

        .accent {
          color: transparent;
          -webkit-text-stroke: 1px #0078ff;
          display: block;
        }

        .hero-sub {
          font-size: 18px;
          color: #6b7fa8;
          max-width: 620px;
          line-height: 1.7;
          margin-top: 28px;
        }

        .hero-actions {
          display: flex;
          gap: 16px;
          margin-top: 48px;
          flex-wrap: wrap;
          justify-content: center;
        }

        .btn-primary,
        .btn-secondary {
          font-size: 15px;
          font-weight: 800;
          padding: 16px 36px;
          border-radius: 6px;
          text-decoration: none;
          display: inline-block;
        }

        .btn-primary {
          color: white;
          background: #0078ff;
          box-shadow: 0 0 30px rgba(0, 120, 255, 0.35);
        }

        .btn-secondary {
          color: white;
          border: 1px solid rgba(255, 255, 255, 0.15);
        }

        .btn-primary:hover {
          transform: translateY(-2px);
          box-shadow: 0 0 50px rgba(0, 120, 255, 0.35);
        }

        .btn-secondary:hover {
          border-color: #0078ff;
          background: rgba(0, 120, 255, 0.08);
        }

        .stat-bar {
          display: flex;
          margin-top: 80px;
          border: 1px solid rgba(0, 120, 255, 0.15);
          border-radius: 12px;
          overflow: hidden;
          background: #0a1628;
          max-width: 760px;
          width: 100%;
        }

        .stat {
          flex: 1;
          padding: 24px 32px;
          border-right: 1px solid rgba(0, 120, 255, 0.15);
          text-align: center;
        }

        .stat:last-child {
          border-right: none;
        }

        .stat-num {
          font-size: 32px;
          font-weight: 900;
          color: #3399ff;
          display: block;
        }

        .stat-label {
          font-size: 11px;
          color: #6b7fa8;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          margin-top: 4px;
          display: block;
        }

        .ticker-wrap {
          overflow: hidden;
          border-top: 1px solid rgba(0, 120, 255, 0.15);
          border-bottom: 1px solid rgba(0, 120, 255, 0.15);
          background: #060d1a;
          padding: 14px 0;
          position: relative;
          z-index: 1;
        }

        .ticker-track {
          display: flex;
          gap: 64px;
          animation: ticker 20s linear infinite;
          white-space: nowrap;
        }

        .ticker-item {
          font-size: 11px;
          color: #6b7fa8;
          letter-spacing: 0.15em;
          text-transform: uppercase;
          flex-shrink: 0;
        }

        .ticker-item span {
          color: #0078ff;
        }

        .section {
          padding: 120px 48px;
          position: relative;
          z-index: 1;
          max-width: 1200px;
          margin: 0 auto;
        }

        .section-title {
          font-size: clamp(36px, 4vw, 56px);
          font-weight: 900;
          line-height: 1.1;
          letter-spacing: -1px;
          max-width: 650px;
          margin-top: 20px;
        }

        .section-title em {
          font-style: normal;
          color: #0078ff;
        }

        .features-grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 1px;
          margin-top: 64px;
          background: rgba(0, 120, 255, 0.15);
          border: 1px solid rgba(0, 120, 255, 0.15);
          border-radius: 16px;
          overflow: hidden;
        }

        .feature-card {
          background: #060d1a;
          padding: 40px 36px;
        }

        .feature-card:hover {
          background: #0a1628;
        }

        .feature-icon {
          width: 44px;
          height: 44px;
          background: rgba(0, 120, 255, 0.1);
          border: 1px solid rgba(0, 120, 255, 0.15);
          border-radius: 10px;
          display: flex;
          align-items: center;
          justify-content: center;
          margin-bottom: 24px;
          font-size: 20px;
        }

        .feature-card h3 {
          font-size: 18px;
          font-weight: 800;
          margin-bottom: 12px;
        }

        .feature-card p,
        .step p,
        .price-desc,
        .price-features li,
        .cta-box p {
          color: #6b7fa8;
          line-height: 1.7;
        }

        .feature-tag {
          font-size: 10px;
          color: #0078ff;
          letter-spacing: 0.1em;
          margin-top: 20px;
          display: block;
        }

        .how-section {
          padding: 120px 48px;
          position: relative;
          z-index: 1;
          background: linear-gradient(180deg, transparent, #060d1a 30%, #060d1a 70%, transparent);
        }

        .how-inner {
          max-width: 1200px;
          margin: 0 auto;
        }

        .steps {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 32px;
          margin-top: 64px;
        }

        .step {
          text-align: center;
        }

        .step-num {
          width: 56px;
          height: 56px;
          background: #0a1628;
          border: 1px solid #0078ff;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          color: #0078ff;
          margin: 0 auto 24px;
          box-shadow: 0 0 20px rgba(0, 120, 255, 0.35);
        }

        .pricing-grid {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 20px;
          margin-top: 64px;
        }

        .price-card {
          background: #0a1628;
          border: 1px solid rgba(0, 120, 255, 0.15);
          border-radius: 16px;
          padding: 40px 36px;
          position: relative;
        }

        .price-card.featured {
          border-color: #0078ff;
          box-shadow: 0 0 40px rgba(0, 120, 255, 0.35);
        }

        .featured-badge {
          position: absolute;
          top: -12px;
          left: 50%;
          transform: translateX(-50%);
          font-size: 10px;
          color: white;
          background: #0078ff;
          padding: 4px 16px;
          border-radius: 100px;
          letter-spacing: 0.1em;
        }

        .price-tier {
          font-size: 11px;
          color: #0078ff;
          letter-spacing: 0.15em;
          text-transform: uppercase;
        }

        .price-amount {
          font-size: 48px;
          font-weight: 900;
          margin: 16px 0 8px;
        }

        .price-amount span {
          font-size: 20px;
          color: #6b7fa8;
        }

        .price-features {
          list-style: none;
          padding: 0;
          margin: 32px 0;
        }

        .price-features li {
          font-size: 13px;
          padding: 8px 0;
          border-bottom: 1px solid rgba(255, 255, 255, 0.04);
        }

        .price-features li::before {
          content: "→";
          color: #0078ff;
          margin-right: 10px;
        }

        .price-btn {
          display: block;
          width: 100%;
          padding: 14px;
          text-align: center;
          border-radius: 8px;
          font-weight: 800;
          text-decoration: none;
        }

        .price-btn-outline {
          color: white;
          border: 1px solid rgba(255, 255, 255, 0.15);
        }

        .price-btn-filled {
          color: white;
          background: #0078ff;
        }

        .cta-section {
          padding: 120px 48px;
          position: relative;
          z-index: 1;
          text-align: center;
        }

        .cta-box {
          max-width: 760px;
          margin: 0 auto;
          background: #0a1628;
          border: 1px solid rgba(0, 120, 255, 0.15);
          border-radius: 24px;
          padding: 80px 64px;
        }

        .cta-box h2 {
          font-size: clamp(32px, 4vw, 52px);
          font-weight: 900;
          margin-bottom: 20px;
        }

        .signup-form {
          display: flex;
          gap: 12px;
          max-width: 480px;
          margin: 0 auto;
        }

        .signup-form input {
          flex: 1;
          background: rgba(255, 255, 255, 0.05);
          border: 1px solid rgba(0, 120, 255, 0.15);
          border-radius: 8px;
          padding: 14px 20px;
          color: white;
        }

        .signup-form button {
          background: #0078ff;
          color: white;
          border: none;
          border-radius: 8px;
          padding: 14px 28px;
          font-weight: 800;
        }

        .form-note {
          font-size: 11px;
          color: #6b7fa8;
          margin-top: 16px;
        }

        .success-msg {
          color: #0078ff !important;
          font-weight: 700;
        }

        footer {
          border-top: 1px solid rgba(0, 120, 255, 0.15);
          padding: 40px 48px;
          display: flex;
          align-items: center;
          justify-content: space-between;
          position: relative;
          z-index: 1;
        }

        .footer-copy {
          font-size: 11px;
          color: #6b7fa8;
        }

        .reveal {
          opacity: 0;
          transform: translateY(30px);
          transition: opacity 0.7s ease, transform 0.7s ease;
        }

        .reveal.visible {
          opacity: 1;
          transform: translateY(0);
        }

        @keyframes pulse {
          0%, 100% {
            opacity: 0.6;
            transform: translate(-50%, -50%) scale(1);
          }
          50% {
            opacity: 1;
            transform: translate(-50%, -50%) scale(1.1);
          }
        }

        @keyframes ticker {
          from {
            transform: translateX(0);
          }
          to {
            transform: translateX(-50%);
          }
        }


        @media (max-width: 1200px) {
          .pricing-grid {
            grid-template-columns: repeat(2, 1fr);
          }
        }

        @media (max-width: 900px) {
          .lossq-landing {
            cursor: auto;
          }

          .cursor,
          .cursor-ring {
            display: none;
          }

          nav {
            padding: 16px 24px;
          }

          .nav-links {
            gap: 16px;
          }

          .nav-links li:not(:last-child) {
            display: none;
          }

          .hero {
            padding: 100px 24px 60px;
          }

          .section,
          .how-section,
          .cta-section {
            padding: 80px 24px;
          }

          .features-grid,
          .pricing-grid {
            grid-template-columns: 1fr;
          }

          .steps {
            grid-template-columns: 1fr;
          }

          .signup-form {
            flex-direction: column;
          }

          footer {
            flex-direction: column;
            gap: 24px;
            text-align: center;
          }

          .stat-bar {
            flex-direction: column;
          }

          .stat {
            border-right: none;
            border-bottom: 1px solid rgba(0, 120, 255, 0.15);
          }

          .stat:last-child {
            border-bottom: none;
          }
        }
      `}</style>
    </main>
  );
}

function Feature({
  icon,
  title,
  text,
  tag,
}: {
  icon: string;
  title: string;
  text: string;
  tag: string;
}) {
  return (
    <div className="feature-card">
      <div className="feature-icon">{icon}</div>
      <h3>{title}</h3>
      <p>{text}</p>
      <span className="feature-tag">{tag}</span>
    </div>
  );
}

function Step({
  num,
  title,
  text,
}: {
  num: string;
  title: string;
  text: string;
}) {
  return (
    <div className="step">
      <div className="step-num">{num}</div>
      <h4>{title}</h4>
      <p>{text}</p>
    </div>
  );
}

function Price({
  tier,
  price,
  desc,
  features,
  featured = false,
}: {
  tier: string;
  price: string;
  desc: string;
  features: string[];
  featured?: boolean;
}) {
  return (
    <div className={`price-card ${featured ? "featured" : ""}`}>
      {featured && <div className="featured-badge">MOST POPULAR</div>}

      <div className="price-tier">{tier}</div>
      <div className="price-amount">
        {price}
        <span>/mo</span>
      </div>

      <div className="price-desc">{desc}</div>

      <ul className="price-features">
        {features.map((feature) => (
          <li key={feature}>{feature}</li>
        ))}
      </ul>

      <a
        href="/pricing"
        className={`price-btn ${featured ? "price-btn-filled" : "price-btn-outline"}`}
      >
        View Plans
      </a>
    </div>
  );
}

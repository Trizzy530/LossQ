import LegalPage from "../legal/LegalPage";

const sections = [
  {
    heading: "AI-Assisted Outputs",
    body: [
      "LossQ may use artificial intelligence, OCR, extraction logic, scoring models, and automation to process documents and generate summaries, reports, insights, classifications, claim stories, safety recommendations, and underwriting-related workflow outputs.",
      "AI-assisted outputs are intended to support review, organization, and workflow efficiency. They are not a substitute for professional judgment.",
    ],
  },
  {
    heading: "Accuracy Limitations",
    body: [
      "AI-generated results may be incomplete, inaccurate, outdated, misclassified, or affected by document quality, formatting, handwriting, scans, missing information, carrier-specific terminology, or user input.",
      "Users must review extracted data, claim amounts, policy numbers, dates, statuses, reserves, litigation indicators, coverage lines, recommendations, and narratives before relying on them.",
    ],
  },
  {
    heading: "No Professional Advice",
    body: [
      "AI outputs from LossQ do not constitute legal advice, insurance advice, underwriting authority, actuarial advice, financial advice, claim adjustment, coverage interpretation, or risk acceptance.",
      "Qualified professionals should independently review all outputs before use in submissions, underwriting, renewals, claim analysis, safety planning, or business decisions.",
    ],
  },
  {
    heading: "No Guarantee of Outcome",
    body: [
      "LossQ does not guarantee carrier acceptance, quote issuance, renewal approval, premium level, claim outcome, reserve adequacy, coverage determination, marketability, or underwriting decision.",
      "Scores, recommendations, carrier appetite indicators, safety recommendations, and claim stories are informational tools based on available data.",
    ],
  },
  {
    heading: "User Responsibility",
    body: [
      "You are responsible for verifying source documents, correcting inaccurate data, and determining whether an output is appropriate for your intended use.",
      "You should not rely solely on LossQ AI outputs for decisions that affect coverage, pricing, eligibility, legal rights, claim handling, contractual obligations, employment matters, or safety procedures.",
    ],
  },
  {
    heading: "Model Changes",
    body: [
      "LossQ may update, improve, replace, or change AI workflows and scoring logic over time.",
      "Outputs may vary across versions as extraction methods, scoring models, prompts, business rules, and platform capabilities improve.",
    ],
  },
];

export default function Page() {
  return (
    <LegalPage
      title="AI Disclaimer"
      subtitle="LossQ uses AI-assisted tools to support insurance workflow analysis, but human review is required."
      sections={sections}
    />
  );
}

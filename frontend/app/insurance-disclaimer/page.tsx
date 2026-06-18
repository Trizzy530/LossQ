import LegalPage from "../legal/LegalPage";

const sections = [
  {
    heading: "Technology Platform Only",
    body: [
      "LossQ provides software tools for organizing loss runs, claims data, underwriting support, renewal preparation, reports, and workflow automation.",
      "LossQ is not an insurance carrier, broker, agent, managing general agent, claims adjuster, third-party administrator, actuary, attorney, or underwriting authority.",
    ],
  },
  {
    heading: "No Coverage or Placement Advice",
    body: [
      "LossQ does not provide insurance coverage advice, policy interpretation, legal opinions, binding authority, risk acceptance, quote approval, or carrier placement decisions.",
      "Users are responsible for reviewing all outputs with licensed insurance professionals and authorized decision-makers.",
    ],
  },
  {
    heading: "No Claims Handling Authority",
    body: [
      "LossQ does not adjust claims, determine liability, make coverage decisions, settle claims, negotiate claims, or provide legal opinions about claims.",
      "Claims summaries, reserve indicators, litigation flags, and claim narratives are based on available data and require professional review.",
    ],
  },
  {
    heading: "Underwriting and Renewal Support",
    body: [
      "Renewal scores, carrier concerns, premium forecasts, safety recommendations, submission readiness, and carrier appetite outputs are workflow-support indicators only.",
      "LossQ does not guarantee renewal, quote availability, pricing, coverage terms, underwriting approval, or carrier appetite.",
    ],
  },
  {
    heading: "Broker and Agency Responsibility",
    body: [
      "Brokers, agencies, carriers, and other users remain responsible for final submissions, representations to carriers, compliance obligations, licensing requirements, and customer communications.",
      "Users should verify LossQ-generated materials against current loss runs, policy documents, claim notes, carrier requirements, and professional judgment.",
    ],
  },
];

export default function Page() {
  return (
    <LegalPage
      title="Insurance Disclaimer"
      subtitle="LossQ supports insurance workflows, but it does not replace licensed professional review or carrier decision-making."
      sections={sections}
    />
  );
}

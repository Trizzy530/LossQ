import LegalPage from "../legal/LegalPage";

const sections = [
    {
      heading: 'Technology Platform Only',
      body: [
        'LossQ provides software tools for organizing loss runs, claims data, underwriting support, renewal preparation, reports, and workflow automation.',
        'Unless separately agreed in writing, LossQ is not an insurance carrier, broker, agent, MGA, TPA, adjuster, law firm, or underwriting authority.',
      ],
    },
    {
      heading: 'No Coverage or Quote Guarantee',
      body: [
        'LossQ does not bind insurance coverage, issue policies, guarantee quotes, guarantee carrier appetite, or determine final eligibility.',
        'Carrier match, appetite, renewal risk, and premium forecast outputs are informational estimates and must be verified with the applicable carrier, broker, underwriter, or licensed professional.',
      ],
    },
    {
      heading: 'No Claims Handling Authority',
      body: [
        'LossQ does not adjust claims, determine liability, make coverage decisions, settle claims, or provide legal opinions about claims.',
        'Claims summaries and analytics are based on available data and require professional review.',
      ],
    },
    {
      heading: 'Underwriting and Renewal Use',
      body: [
        'LossQ may help identify trends, loss drivers, large losses, open claims, reserves, litigation indicators, and submission readiness issues.',
        'These tools support the insurance workflow but do not replace carrier underwriting guidelines, filed rates, legal requirements, or professional judgment.',
      ],
    },
    {
      heading: 'Customer Responsibility',
      body: [
        'Users are responsible for verifying all source documents, data extraction, policy information, claim values, recommendations, reports, and submissions before external use.',
        'Users are responsible for complying with applicable insurance laws, privacy requirements, contractual duties, and professional standards.',
      ],
    },
    {
      heading: 'No Reliance Without Review',
      body: [
        'Do not rely on LossQ as the sole basis for insurance placement, renewal strategy, claim decisions, pricing, reserves, coverage, or legal positions.',
        'All outputs should be reviewed by qualified professionals.',
      ],
    },
    {
      heading: 'Contact',
      body: [
        'Questions about this Insurance Disclaimer may be sent to support@lossq.com.',
      ],
    },
  ];

export default function Page() {
  return (
    <LegalPage
      title='Insurance Disclaimer'
      subtitle='LossQ is a software platform and does not replace licensed insurance professionals.'
      sections={sections}
    />
  );
}

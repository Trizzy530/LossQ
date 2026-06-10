import LegalPage from "../legal/LegalPage";

const sections = [
    {
      heading: 'AI-Assisted Outputs',
      body: [
        'LossQ may use artificial intelligence, OCR, extraction logic, scoring models, and automation to process documents and generate summaries, reports, insights, classifications, and recommendations.',
        'AI outputs are informational and should be treated as decision-support, not final decisions.',
      ],
    },
    {
      heading: 'Accuracy Limitations',
      body: [
        'AI-generated results may be incomplete, inaccurate, outdated, misclassified, or affected by document quality, formatting, handwriting, scans, missing information, or user input.',
        'Users must review extracted data, claim amounts, policy numbers, dates, statuses, and recommendations before relying on them.',
      ],
    },
    {
      heading: 'No Professional Advice',
      body: [
        'AI outputs from LossQ do not constitute legal advice, insurance advice, underwriting authority, financial advice, claim adjustment, coverage interpretation, or risk acceptance.',
        'Qualified professionals should independently review all outputs before use in submissions, underwriting, renewals, claim analysis, or business decisions.',
      ],
    },
    {
      heading: 'User Responsibility',
      body: [
        'You are responsible for verifying source documents, correcting inaccurate data, and determining whether an output is appropriate for your intended use.',
        'You should not rely solely on LossQ AI outputs for decisions that affect coverage, pricing, eligibility, legal rights, claim handling, or contractual obligations.',
      ],
    },
    {
      heading: 'Model Changes',
      body: [
        'LossQ may update, improve, replace, or change AI workflows and scoring logic over time.',
        'Outputs may vary across versions, document formats, and available data.',
      ],
    },
    {
      heading: 'Contact',
      body: [
        'Questions about AI-assisted outputs may be sent to support@lossq.com.',
      ],
    },
  ];

export default function Page() {
  return (
    <LegalPage
      title='AI Disclaimer'
      subtitle='LossQ uses AI-assisted tools to support insurance workflow analysis, but human review is required.'
      sections={sections}
    />
  );
}

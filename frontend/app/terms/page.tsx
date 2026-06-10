import LegalPage from "../legal/LegalPage";

const sections = [
    {
      heading: 'Acceptance of Terms',
      body: [
        'By accessing or using LossQ, you agree to these Terms and Conditions. If you do not agree, do not use the platform.',
        'LossQ may update these Terms from time to time. Continued use of the platform after updates means you accept the revised Terms.',
      ],
    },
    {
      heading: 'Use of the Platform',
      body: [
        'LossQ provides software tools for loss run organization, claims analysis, underwriting support, renewal intelligence, document processing, reporting, and related workflow automation.',
        'You are responsible for ensuring that all information uploaded to LossQ is accurate, lawful, and authorized for use.',
      ],
    },
    {
      heading: 'Accounts and Security',
      body: [
        'You are responsible for maintaining the confidentiality of your account credentials and for all activity under your account.',
        'You agree to notify LossQ promptly if you believe your account has been compromised or used without authorization.',
      ],
    },
    {
      heading: 'Customer Data',
      body: [
        'You retain ownership of the business records, loss runs, claims data, policy information, documents, and other materials you upload to LossQ.',
        'You grant LossQ permission to process Customer Data only as needed to provide, maintain, secure, improve, and support the platform.',
      ],
    },
    {
      heading: 'Subscriptions and Payment',
      body: [
        'Paid features may require an active subscription. Fees, billing cycles, usage limits, and plan features are shown at checkout or in your account settings.',
        'Failure to pay may result in account restriction, suspension, or cancellation.',
      ],
    },
    {
      heading: 'Acceptable Use',
      body: [
        'You may not use LossQ to upload unlawful data, violate third-party rights, interfere with platform operations, reverse engineer the service, or attempt unauthorized access.',
        'You may not use LossQ outputs as the sole basis for legal, insurance, underwriting, claim, coverage, or financial decisions.',
      ],
    },
    {
      heading: 'AI and Automation',
      body: [
        'LossQ may use automated extraction, OCR, AI-assisted classification, scoring, and summarization tools.',
        'AI-generated results may be incomplete or inaccurate and must be reviewed by a qualified professional before reliance.',
      ],
    },
    {
      heading: 'No Insurance, Legal, or Financial Advice',
      body: [
        'LossQ is a technology platform. It does not provide legal advice, insurance advice, underwriting authority, coverage determinations, claim adjustment, or binding insurance quotes.',
        'You are responsible for independent review and professional judgment.',
      ],
    },
    {
      heading: 'Intellectual Property',
      body: [
        'LossQ and its software, design, workflows, branding, reports, and platform features are owned by LossQ or its licensors.',
        'You may not copy, resell, reproduce, or create derivative products from LossQ without written permission.',
      ],
    },
    {
      heading: 'Termination',
      body: [
        'LossQ may suspend or terminate access if you violate these Terms, misuse the platform, create security risk, or fail to pay required fees.',
        'You may stop using LossQ at any time.',
      ],
    },
    {
      heading: 'Limitation of Liability',
      body: [
        'To the fullest extent permitted by law, LossQ is not liable for indirect, incidental, special, consequential, or punitive damages, including lost profits, lost business, or lost data.',
        "LossQ's total liability is limited to the amount paid by you for the service during the three months before the event giving rise to the claim.",
      ],
    },
    {
      heading: 'Governing Law',
      body: [
        'These Terms are governed by the laws of the State of North Carolina, without regard to conflict-of-law principles.',
      ],
    },
    {
      heading: 'Contact',
      body: [
        'Questions about these Terms may be sent to support@lossq.com.',
      ],
    },
  ];

export default function Page() {
  return (
    <LegalPage
      title='Terms and Conditions'
      subtitle='These Terms govern your access to and use of LossQ.'
      sections={sections}
    />
  );
}

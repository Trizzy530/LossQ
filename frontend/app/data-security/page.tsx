import LegalPage from "../legal/LegalPage";

const sections = [
  {
    heading: 'Data Protection',
    body: [
      'LossQ uses secure application practices to protect uploaded documents, extracted claim information, account profiles, and underwriting summaries. Data is handled for the purpose of providing the LossQ platform services.',
    ],
  },
  {
    heading: 'Encryption in Transit',
    body: [
      "LossQ is intended to use HTTPS/TLS encryption for data transmitted between the user's browser and the LossQ platform.",
    ],
  },
  {
    heading: 'Organization-Level Access',
    body: [
      'LossQ is built to keep organization data separated so users only access accounts, claims, profiles, and reports associated with their authorized organization.',
    ],
  },
  {
    heading: 'Authentication and Access Control',
    body: [
      'LossQ uses account-based authentication, session controls, and role-based access concepts to limit access to authorized users. Users are responsible for maintaining the confidentiality of their login credentials.',
    ],
  },
  {
    heading: 'Document Handling',
    body: [
      'Uploaded loss runs and supporting documents are processed to extract insurance-related information such as policy details, claim details, loss history, and underwriting context. LossQ is not intended to publicly disclose uploaded documents or extracted claim data.',
    ],
  },
  {
    heading: 'Audit and Activity Tracking',
    body: [
      'LossQ may maintain audit logs, user activity records, upload history, and account activity to support security review, troubleshooting, compliance support, and platform integrity.',
    ],
  },
  {
    heading: 'Payment Security',
    body: [
      'LossQ does not store full payment card information on its own servers. Payment processing, when applicable, is handled through third-party payment providers.',
    ],
  },
  {
    heading: 'Third-Party Infrastructure',
    body: [
      'LossQ may rely on trusted third-party infrastructure providers for hosting, database services, authentication, payment processing, storage, analytics, and operational support. These providers may process limited data as necessary to provide platform services.',
    ],
  },
  {
    heading: 'Administrative Access',
    body: [
      'Administrative access is limited to authorized LossQ personnel or approved technical support resources for support, troubleshooting, security, compliance, or platform maintenance purposes.',
    ],
  },
  {
    heading: 'Security Limitations',
    body: [
      'No software platform, AI system, cloud service, or internet transmission can be guaranteed to be completely secure. LossQ uses reasonable security measures, but users should avoid uploading information they are not authorized to share.',
    ],
  },
  {
    heading: 'Customer Responsibility',
    body: [
      'Users are responsible for ensuring they have the right to upload, analyze, and share loss runs, insurance documents, claim information, and account data through LossQ.',
    ],
  },
  {
    heading: 'Incident Response',
    body: [
      'If LossQ becomes aware of a security issue that materially affects user data, LossQ will take reasonable steps to investigate, mitigate, and communicate as appropriate.',
    ],
  },
  {
    heading: 'Compliance Roadmap',
    body: [
      'LossQ is designed with security and compliance readiness in mind. Any future certifications, including SOC 2 or similar third-party audits, will only be represented as completed after they are formally achieved.',
    ],
  },
  {
    heading: 'Security Contact',
    body: [
      'For security, privacy, or data handling questions, users may contact LossQ through the support contact listed on the website.',
    ],
  },
  {
    heading: 'Transparency Note',
    body: [
      'This Security Measures section is provided for transparency and does not replace the full Terms of Service, Privacy Policy, or any written agreement between LossQ and a customer.',
    ],
  },
];

export default function Page() {
  return (
    <LegalPage
      title='Security Measures'
      subtitle='LossQ is designed to help insurance professionals organize, analyze, and review commercial loss run information with security, confidentiality, and organization-level data separation in mind.'
      sections={sections}
    />
  );
}

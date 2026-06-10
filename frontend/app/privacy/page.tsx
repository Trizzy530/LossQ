import LegalPage from "../legal/LegalPage";

const sections = [
    {
      heading: 'Information We Collect',
      body: [
        'We may collect account information such as name, email address, organization name, role, login activity, and subscription details.',
        'We may process uploaded documents, loss runs, claims data, policy information, carrier information, reports, and user-generated notes.',
        'We may collect technical information such as IP address, device information, browser type, logs, cookies, and usage activity.',
      ],
    },
    {
      heading: 'How We Use Information',
      body: [
        'We use information to provide the LossQ platform, process uploaded documents, generate reports, support user accounts, maintain security, improve features, and communicate with users.',
        'We may use aggregated or de-identified information to improve platform performance and analytics.',
      ],
    },
    {
      heading: 'Uploaded Loss Run and Claims Data',
      body: [
        'Customer-uploaded loss runs, claims records, and policy information are processed to provide the requested platform features.',
        'LossQ does not sell customer uploaded loss run or claims data.',
      ],
    },
    {
      heading: 'AI Processing',
      body: [
        'LossQ may use automated tools, OCR, extraction logic, and AI-assisted workflows to analyze uploaded documents and generate summaries, scores, reports, and recommendations.',
        'Users are responsible for reviewing outputs before using them in business decisions.',
      ],
    },
    {
      heading: 'How We Share Information',
      body: [
        'We may share information with service providers that help us operate the platform, such as hosting, database, payment, email, analytics, security, and support providers.',
        'We may disclose information if required by law, legal process, security investigation, fraud prevention, or to protect the rights and safety of LossQ, users, or others.',
      ],
    },
    {
      heading: 'Payment Information',
      body: [
        'Payment processing may be handled by third-party payment providers. LossQ does not store full payment card numbers on its own systems.',
      ],
    },
    {
      heading: 'Data Retention',
      body: [
        'We retain information for as long as needed to provide services, comply with legal obligations, resolve disputes, enforce agreements, and maintain business records.',
        'Users may request deletion of certain account or uploaded data, subject to legal, security, backup, and operational requirements.',
      ],
    },
    {
      heading: 'Security',
      body: [
        'LossQ uses administrative, technical, and organizational safeguards designed to protect information from unauthorized access, loss, misuse, or alteration.',
        'No system is completely secure, and LossQ cannot guarantee absolute security.',
      ],
    },
    {
      heading: 'Your Choices',
      body: [
        'You may update certain account information through your account settings.',
        'You may contact LossQ to request assistance with access, correction, deletion, or other privacy-related questions.',
      ],
    },
    {
      heading: 'Children',
      body: [
        'LossQ is intended for business users and is not directed to children under 13.',
      ],
    },
    {
      heading: 'Changes to This Policy',
      body: [
        'LossQ may update this Privacy Policy from time to time. The updated version will be posted on this page with a revised effective date.',
      ],
    },
    {
      heading: 'Contact',
      body: [
        'Privacy questions may be sent to support@lossq.com.',
      ],
    },
  ];

export default function Page() {
  return (
    <LegalPage
      title='Privacy Policy'
      subtitle='This Privacy Policy explains how LossQ collects, uses, shares, and protects information.'
      sections={sections}
    />
  );
}

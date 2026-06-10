import LegalPage from "../legal/LegalPage";

const sections = [
    {
      heading: 'Security Overview',
      body: [
        'LossQ is designed to support secure handling of business, insurance, policy, loss run, and claims-related information.',
        'Security is a shared responsibility between LossQ and each customer organization.',
      ],
    },
    {
      heading: 'Access Controls',
      body: [
        'LossQ uses authenticated user accounts, role-based access controls, and organization-level separation to help limit access to authorized users.',
        'Customers are responsible for managing their own users, roles, passwords, and access privileges.',
      ],
    },
    {
      heading: 'Data Isolation',
      body: [
        'LossQ is designed to keep organization data separated so users should only access data associated with their authorized organization.',
        'Customers should promptly report any suspected cross-account visibility or unauthorized access.',
      ],
    },
    {
      heading: 'Passwords and Authentication',
      body: [
        'Users should use strong passwords and protect login credentials.',
        'Password reset links are time-limited and should not be shared.',
      ],
    },
    {
      heading: 'Uploaded Documents',
      body: [
        'Uploaded documents may include sensitive business, insurance, claims, and policy data.',
        'Users should upload only documents they are authorized to process through LossQ.',
      ],
    },
    {
      heading: 'Operational Safeguards',
      body: [
        'LossQ may use logging, monitoring, access restrictions, database controls, secure hosting, backups, and deployment controls to support platform security.',
        'Security practices may evolve as the platform grows.',
      ],
    },
    {
      heading: 'Incident Response',
      body: [
        'If LossQ becomes aware of a security incident affecting customer data, LossQ will investigate and take appropriate steps based on the nature of the incident and applicable requirements.',
        'Customers should notify LossQ immediately if they suspect unauthorized account access or data exposure.',
      ],
    },
    {
      heading: 'Customer Responsibilities',
      body: [
        'Customers are responsible for using the platform lawfully, limiting access to authorized users, reviewing exports before distribution, and securing downloaded reports.',
        'Customers should avoid uploading unnecessary personal, confidential, or regulated information unless needed for legitimate business purposes.',
      ],
    },
    {
      heading: 'No Absolute Guarantee',
      body: [
        'No technology platform can guarantee complete security. LossQ uses safeguards designed to reduce risk but cannot eliminate all risk.',
      ],
    },
    {
      heading: 'Contact',
      body: [
        'Security questions or suspected incidents may be sent to support@lossq.com.',
      ],
    },
  ];

export default function Page() {
  return (
    <LegalPage
      title='Data Security Policy'
      subtitle="This policy summarizes LossQ's approach to protecting customer data."
      sections={sections}
    />
  );
}

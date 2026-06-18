import LegalPage from "../legal/LegalPage";

const sections = [
  {
    heading: "Information We Collect",
    body: [
      "We may collect account information such as name, email address, organization name, role, login activity, subscription details, and billing-related identifiers.",
      "We may process uploaded documents, loss runs, claims data, policy information, carrier information, reports, notes, user inputs, and generated outputs.",
      "We may collect technical information such as IP address, device information, browser type, logs, cookies, usage activity, and security events.",
    ],
  },
  {
    heading: "How We Use Information",
    body: [
      "We use information to provide the LossQ platform, authenticate users, organize account profiles, process uploads, generate reports, support billing, improve reliability, and protect the service.",
      "We may use usage patterns, errors, and feedback to improve extraction quality, workflow design, security, and product performance.",
    ],
  },
  {
    heading: "Uploaded Insurance and Claims Data",
    body: [
      "Uploaded data may include sensitive business, insurance, policy, claim, loss run, underwriting, and operational information.",
      "Users should upload only documents and data they are authorized to process through LossQ.",
      "LossQ outputs depend on the quality and completeness of the uploaded data and should be verified against source materials.",
    ],
  },
  {
    heading: "AI and Processing",
    body: [
      "LossQ may process uploaded content through OCR, extraction rules, scoring logic, AI-assisted workflows, and analytics to provide summaries, recommendations, reports, and claim narratives.",
      "Where third-party infrastructure or service providers are used, they are used to support platform operations, processing, security, hosting, billing, or analytics.",
    ],
  },
  {
    heading: "How We Share Information",
    body: [
      "We do not sell customer uploaded documents or claim data to advertisers.",
      "We may share information with service providers that help operate LossQ, such as hosting, infrastructure, payment processing, security, email, logging, and analytics providers.",
      "We may disclose information when required by law, to protect rights and security, to enforce policies, or with the customer organization's direction.",
    ],
  },
  {
    heading: "Organization Access",
    body: [
      "Users within the same customer organization may have access to shared account profiles, uploads, claims, reports, billing information, or activity depending on their role and permissions.",
      "Organization owners or administrators are responsible for managing user access and ensuring only authorized users can view sensitive information.",
    ],
  },
  {
    heading: "Security",
    body: [
      "LossQ is designed with access controls, organization scoping, authentication, audit activity, and operational safeguards.",
      "No system can guarantee complete security. Users should protect credentials, use strong passwords, limit access, and report suspicious activity.",
    ],
  },
  {
    heading: "Data Retention",
    body: [
      "LossQ may retain account data, uploads, claims, reports, audit activity, billing records, and generated outputs for as long as needed to provide the service, meet legal obligations, resolve disputes, and enforce agreements.",
      "Cancellation of a subscription does not automatically delete customer data unless a deletion request is separately processed according to applicable procedures.",
    ],
  },
  {
    heading: "User Choices",
    body: [
      "Users may update account information, manage subscription settings, download reports, and request support through available platform tools.",
      "Certain data may need to be retained for security, billing, legal, audit, or compliance purposes.",
    ],
  },
  {
    heading: "Policy Updates",
    body: [
      "We may update this Privacy Policy as LossQ evolves. Updated versions may be posted in the Legal Center.",
      "Continued use of LossQ after updates means you accept the revised policy to the extent permitted by law.",
    ],
  },
];

export default function Page() {
  return (
    <LegalPage
      title="Privacy Policy"
      subtitle="This policy explains how LossQ collects, uses, stores, and protects account, insurance, claim, billing, and platform data."
      sections={sections}
    />
  );
}

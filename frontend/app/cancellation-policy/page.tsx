import LegalPage from "../legal/LegalPage";

const sections = [
  {
    heading: "How to Cancel",
    body: [
      "Customers may cancel an eligible subscription through Settings → Billing & Subscription when the option is available.",
      "Only users with the required owner or administrator permissions should manage billing changes for an organization.",
    ],
  },
  {
    heading: "Effect of Cancellation",
    body: [
      "If Stripe cancellation is set to occur at period end, paid access may remain active until the end of the current billing period.",
      "If a subscription is ended locally or no active Stripe subscription exists, LossQ may immediately downgrade access to the free or inactive package.",
    ],
  },
  {
    heading: "No Automatic Data Deletion",
    body: [
      "Cancelling a subscription does not automatically delete users, organizations, account profiles, uploaded loss runs, claims, reports, or audit activity.",
      "Data may be retained as needed for customer access, security, billing records, legal obligations, audits, dispute resolution, or platform integrity.",
    ],
  },
  {
    heading: "Reactivation",
    body: [
      "A customer may reactivate or purchase a new plan if billing options are available and the account is in good standing.",
      "Feature access after reactivation depends on the selected plan and current LossQ package rules.",
    ],
  },
  {
    heading: "Support",
    body: [
      "For cancellation questions, billing issues, or access concerns, contact LossQ support using the Report Issue button or the available support email.",
      "Customers should not rely on cancellation alone as a request to export, archive, or delete data.",
    ],
  },
];

export default function Page() {
  return (
    <LegalPage
      title="Cancellation Policy"
      subtitle="This policy explains what happens when a LossQ subscription is cancelled and how account data is handled."
      sections={sections}
    />
  );
}

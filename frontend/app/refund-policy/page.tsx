import LegalPage from "../legal/LegalPage";

const sections = [
  {
    heading: "Subscription Billing",
    body: [
      "LossQ subscription fees are billed according to the package selected at checkout and the billing terms shown at the time of purchase.",
      "Access to paid features may depend on successful payment, subscription status, package eligibility, and account standing.",
    ],
  },
  {
    heading: "Cancellation",
    body: [
      "Users with billing permission may cancel through Settings → Billing & Subscription when available.",
      "When cancellation is processed through Stripe at period end, access may continue until the end of the then-current billing period unless otherwise stated.",
      "Cancellation does not automatically delete account data, uploaded documents, claim records, reports, or organization activity.",
    ],
  },
  {
    heading: "Refunds",
    body: [
      "Unless required by law or separately agreed in writing, subscription fees are generally non-refundable once a billing period begins.",
      "LossQ may review refund requests case by case, including duplicate charges, billing errors, or exceptional circumstances.",
      "Refund approval is not guaranteed and may depend on usage, timing, payment processor rules, and account status.",
    ],
  },
  {
    heading: "Failed Payments",
    body: [
      "If a payment fails, LossQ may mark the subscription as past due and may limit, suspend, or downgrade access until payment is resolved.",
      "Users are responsible for keeping billing information current.",
    ],
  },
  {
    heading: "Plan Changes",
    body: [
      "Plan upgrades or downgrades may affect feature access, upload limits, user limits, and billing amounts.",
      "Billing adjustments, prorations, and timing may be handled by the payment processor or Stripe configuration.",
    ],
  },
  {
    heading: "Data After Cancellation",
    body: [
      "Cancellation affects subscription access and billing; it does not automatically remove stored data.",
      "Customers may contact support for data-related questions, export needs, or deletion requests where available and legally permitted.",
    ],
  },
];

export default function Page() {
  return (
    <LegalPage
      title="Refund and Cancellation Policy"
      subtitle="This policy explains how subscription cancellation, refunds, failed payments, and data access after cancellation are handled."
      sections={sections}
    />
  );
}

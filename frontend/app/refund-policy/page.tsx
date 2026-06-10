import LegalPage from "../legal/LegalPage";

const sections = [
    {
      heading: 'Subscription Billing',
      body: [
        'LossQ subscriptions may be billed monthly, annually, or according to the billing terms shown at checkout.',
        'By subscribing, you authorize recurring charges for the selected plan until canceled.',
      ],
    },
    {
      heading: 'Cancellation',
      body: [
        'You may cancel your subscription through your account settings or by contacting support.',
        'Cancellation stops future renewal charges but does not automatically refund prior charges.',
      ],
    },
    {
      heading: 'Refunds',
      body: [
        'Subscription fees are generally non-refundable except where required by law or approved by LossQ in its discretion.',
        'Partial-month refunds, unused-seat refunds, or refunds for unused features are not guaranteed.',
      ],
    },
    {
      heading: 'Free Trials and Promotions',
      body: [
        'Trial or promotional plans may convert to paid subscriptions according to the terms shown when you enroll.',
        'You are responsible for canceling before a paid billing period begins if you do not want to continue.',
      ],
    },
    {
      heading: 'Billing Issues',
      body: [
        'If you believe you were charged in error, contact support promptly with the account email, charge date, and issue description.',
        'LossQ may review billing issues and determine whether a credit or refund is appropriate.',
      ],
    },
    {
      heading: 'Account Downgrades',
      body: [
        'Downgrading a plan may reduce access to features, seats, storage, or usage limits.',
        'Downgrades may take effect immediately or at the next billing cycle depending on the subscription setup.',
      ],
    },
    {
      heading: 'Termination for Misuse',
      body: [
        'LossQ may suspend or terminate accounts that violate the Terms and Conditions. Refunds are not guaranteed for terminated accounts.',
      ],
    },
    {
      heading: 'Contact',
      body: [
        'Refund and billing questions may be sent to support@lossq.com.',
      ],
    },
  ];

export default function Page() {
  return (
    <LegalPage
      title='Refund and Cancellation Policy'
      subtitle='This policy explains subscription cancellation and refund expectations.'
      sections={sections}
    />
  );
}

import LegalPage from "../legal/LegalPage";

const sections = [
  {
    heading: "Data Used by LossQ",
    body: [
      "LossQ metrics may be generated from uploaded loss runs, claim reports, claim numbers, claim status, loss dates, reported dates, closed dates, paid amounts, reserve amounts, total incurred amounts, policy numbers, policy terms, carriers, coverage lines, business name, location, jurisdiction, market context, exposure inputs, user-entered account profile information, and system-generated audit or activity data.",
      "LossQ depends on the quality and completeness of the uploaded and entered information. If a document is incomplete, unclear, inconsistent, outdated, or incorrectly formatted, the resulting metrics may also be incomplete or inaccurate.",
    ],
  },
  {
    heading: "Claim Totals",
    body: [
      "LossQ calculates claim totals by identifying claim rows and summarizing claim activity, including total claims, open claims, closed claims, total paid, total reserve, and total incurred amounts.",
      "Total incurred is generally calculated as paid plus reserve unless the uploaded document provides a clear total incurred value that appears more reliable. When claim detail rows and summary totals conflict, LossQ may prioritize the most detailed claim-level information when it appears more reliable.",
    ],
  },
  {
    heading: "Loss Ratio",
    body: [
      "LossQ may estimate loss ratio by comparing total incurred losses against premium when premium data is available. In general, loss ratio means total incurred losses divided by premium.",
      "Loss ratio is an underwriting indicator used to help assess whether losses are high, moderate, or low relative to premium. LossQ loss ratio outputs are informational and may not match a carrier's final actuarial or underwriting calculation.",
    ],
  },
  {
    heading: "Claim Frequency",
    body: [
      "LossQ may evaluate claim frequency by reviewing the number of claims across the policy period, account period, or available loss history.",
      "Higher claim frequency may indicate repeated operational issues, a higher likelihood of future losses, a need for stronger risk controls, or a potential underwriting concern. Lower claim frequency may indicate more favorable loss experience depending on business size, exposure, and industry class.",
    ],
  },
  {
    heading: "Claim Severity",
    body: [
      "LossQ may evaluate claim severity by reviewing total incurred amounts, large losses, open reserves, and claim patterns.",
      "Severity indicators may include large individual claims, high total incurred losses, significant open reserves, litigation or complex claim indicators, and losses involving bodily injury, property damage, professional liability, cyber events, or other high-impact exposures.",
    ],
  },
  {
    heading: "Open Claim Impact",
    body: [
      "Open claims may affect LossQ risk indicators because the final cost of an open claim may not yet be known. LossQ may treat open claims with reserves as a potential continuing exposure.",
      "Open claim impact may consider the number of open claims, total open reserves, claim age, claim type, coverage line, and whether the claim appears severe, litigated, or unresolved.",
    ],
  },
  {
    heading: "Renewal Score",
    body: [
      "LossQ may generate a renewal score using available account, policy, exposure, and claim information. The score is intended to summarize renewal strength based on the data available.",
      "Factors that may influence the renewal score include claim frequency, claim severity, open claims and reserves, total incurred losses, loss ratio when premium is available, policy age, loss history period, data completeness, exposure information, market and jurisdiction context, and underwriting concerns identified from the loss history.",
      "The renewal score is not a guarantee of renewal, pricing, coverage, carrier appetite, or underwriting approval.",
    ],
  },
  {
    heading: "Risk Level",
    body: [
      "LossQ may assign a general risk level such as low, moderate, elevated, high, or critical based on the account's loss history and underwriting indicators.",
      "Risk level may be influenced by total claims, open claims, total incurred losses, large losses, loss ratio, claim trends, severity concerns, missing or incomplete information, exposure mismatch, and industry or coverage-specific concerns.",
      "Risk levels are designed to help users quickly understand underwriting concern areas. They are not final underwriting decisions.",
    ],
  },
  {
    heading: "Premium Forecast",
    body: [
      "LossQ may estimate premium movement or renewal pressure based on loss history, exposure data, claim severity, claim frequency, and underwriting indicators.",
      "Premium forecast outputs are informational estimates only. Actual pricing depends on carrier underwriting guidelines, market conditions, filings, actuarial models, reinsurance costs, coverage terms, deductibles, limits, jurisdiction, appetite, and other factors outside LossQ's control.",
    ],
  },
  {
    heading: "Carrier Appetite",
    body: [
      "LossQ may estimate carrier appetite by comparing the account's risk profile against common underwriting considerations such as line of business, claim history, loss ratio, open claim count, severity, industry classification, location, jurisdiction, data completeness, and submission quality.",
      "Carrier appetite outputs are directional and informational. They do not represent a carrier's official appetite, quote, declination, or underwriting decision unless separately confirmed by that carrier.",
    ],
  },
  {
    heading: "Carrier Match",
    body: [
      "LossQ may generate carrier match insights by comparing account characteristics against known or user-defined appetite indicators, including coverage line, industry type, claim history, risk severity, account size, jurisdiction, submission readiness, and available underwriting information.",
      "Carrier match results are recommendations for review and do not guarantee that a carrier will quote, bind, renew, or accept the account.",
    ],
  },
  {
    heading: "Submission Readiness",
    body: [
      "LossQ may calculate submission readiness by reviewing whether the account has enough information for an underwriter or carrier to evaluate the risk.",
      "Submission readiness may consider whether the file includes named insured, policy number, carrier, effective and expiration dates, claim detail rows, claim status, paid, reserve, and incurred amounts, loss dates, reported dates, coverage line or policy type, exposure inputs, business description, supporting documents, and a clear loss history period.",
      "A higher readiness score means the file appears more complete. It does not guarantee approval, quote issuance, or favorable terms.",
    ],
  },
  {
    heading: "Data Quality",
    body: [
      "LossQ may flag data quality issues when uploaded information appears missing, inconsistent, duplicated, unreadable, outdated, or conflicting.",
      "Examples include missing policy dates, missing claim amounts, conflicting totals, unclear claim status, duplicate claim rows, missing exposure inputs, incomplete loss history, and documents that are scanned, blurry, or difficult to parse.",
      "Users should review extracted data before relying on any LossQ output.",
    ],
  },
  {
    heading: "AI-Generated Underwriting Narrative",
    body: [
      "LossQ may generate underwriting narratives, summaries, recommendations, and observations using artificial intelligence. These narratives are based on the uploaded and entered data available at the time of generation.",
      "AI-generated narratives may help identify loss trends, claim concerns, submission gaps, renewal risks, coverage issues, potential underwriting questions, and account strengths or weaknesses.",
      "Users should review all AI-generated content for accuracy, completeness, and professional judgment before sharing it with clients, carriers, brokers, underwriters, or other third parties.",
    ],
  },
  {
    heading: "Human Review Required",
    body: [
      "LossQ is a decision-support platform. It does not replace licensed insurance professionals, underwriters, brokers, carriers, actuaries, claims professionals, attorneys, or compliance personnel.",
      "Users are responsible for reviewing extracted data, confirming claim accuracy, validating policy and exposure information, correcting errors, and making final business, underwriting, coverage, pricing, or placement decisions.",
    ],
  },
  {
    heading: "Metric Limitations",
    body: [
      "LossQ metrics may be affected by incomplete documents, incorrectly formatted files, missing pages, scanned or low-quality PDFs, inconsistent carrier loss run formats, user-entered errors, conflicting claim summaries and claim detail rows, missing premium or exposure data, outdated loss runs, and coverage-specific underwriting differences.",
      "LossQ does not guarantee that every metric will be complete, accurate, or accepted by every carrier, broker, agency, or underwriting department.",
    ],
  },
  {
    heading: "No Binding Decision",
    body: [
      "LossQ outputs are informational only. LossQ does not issue insurance policies, bind coverage, settle claims, determine coverage, approve submissions, set final premium, or make binding underwriting decisions.",
      "Final decisions remain with the appropriate insurance carrier, underwriter, broker, agency, or authorized professional.",
    ],
  },
  {
    heading: "Transparency Note",
    body: [
      "This Metrics Explained section is provided for transparency and does not replace the Terms of Service, Privacy Policy, Security Measures, carrier underwriting guidelines, or any written agreement between LossQ and a customer.",
    ],
  },
];

export default function Page() {
  return (
    <LegalPage
      title="Metrics Explained"
      subtitle="LossQ uses uploaded loss runs, claim records, policy information, account profile data, exposure inputs, and user-provided information to generate underwriting summaries, risk indicators, claim analytics, renewal insights, and submission readiness metrics. These outputs are designed to support insurance review and decision-making, but they are not a substitute for professional underwriting judgment, carrier guidelines, actuarial analysis, legal advice, or a binding coverage decision."
      sections={sections}
    />
  );
}
import unittest
from app.services.reconciled_tabular import parse_rows, amount, iso
from app.services.reconciled_pdf import StructuredPDFError


def fixture(cad=False):
    account = [
        ['Named insured','Example Company'], ['Account Number','EX-12345'],
        ['Carrier','Example Mutual'], ['Producing agency','Example Broker'],
        ['State','QC' if cad else 'VA'], ['Country','Canada' if cad else 'United States'],
        ['Currency','CAD' if cad else 'USD'], ['Evaluation date','31/10/2026' if cad else '10/31/2026'],
    ]
    policies = [
        ['Policy ref','Coverage','Eff. date','Exp. date','Annual premium','Exposure basis','Exposure'],
        ['PL-123-25','Professional Liability','2024-11-01','2025-11-01',46000,'Professional revenue',2700000],
        ['PL-123-26','Professional Liability','2025-11-01','2026-11-01',52000,'Professional revenue',3150000],
        ['GL-123-26','General Liability','2025-11-01','2026-11-01',19500,'Annual revenue',3150000],
    ]
    claims = [
        ['Claim #','Policy ref','LOB','Claimant','Jurisdiction','DOL','Reported','Closed date','Status','Paid total','Outstanding reserve','Total incurred','Examiner','Litigation','Loss description'],
        ['EX-001','PL-123-25','PL','Example claimant','QC' if cad else 'VA','2025-05-08','2025-05-09','2025-10-17','Closed',18500,0,18500,'E. Hart','No','Closed claim'],
        ['EX-002','PL-123-26','PL','Another claimant','ON' if cad else 'WV','2026-02-09','2026-02-10',None,'Ouvert / Open' if cad else 'Open','29 000,00 $' if cad else 29000,71000,100000,'E. Hart','Yes','Open claim'],
        ['EX-003','GL-123-26','GL','Example claimant','QC' if cad else 'VA','2026-09-12','2026-09-13','2026-09-30','Closed',0,0,0,'K. Ford','No','Zero-dollar incident'],
        ['TOTAL',None,None,None,None,None,None,None,None,47500,71000,118500],
    ]
    return [account,policies,claims]


class TabularTests(unittest.TestCase):
    def test_history_zero_and_jurisdiction(self):
        claims, profile = parse_rows(fixture())
        self.assertEqual(len(claims),3)
        self.assertEqual(len(profile['policies']),3)
        self.assertEqual(profile['current_premium'],'71500')
        self.assertEqual(profile['validation']['listed_policy_premium_total'],117500)
        self.assertEqual(profile['professional_revenue'],'3150000')
        self.assertEqual(claims[-1]['total_incurred'],0)
        self.assertEqual(claims[1]['jurisdiction_state'],'WV')
        self.assertEqual(profile['state'],'VA')

    def test_canadian_dates_and_money(self):
        claims, profile = parse_rows(fixture(True))
        self.assertEqual(profile['evaluation_date'],'2026-10-31')
        self.assertEqual(profile['currency'],'CAD')
        self.assertEqual(claims[1]['paid_amount'],29000)
        self.assertEqual(claims[1]['jurisdiction_state'],'ON')
        self.assertEqual(profile['state'],'QC')
        self.assertEqual(str(amount('105 050,00 $',True)),'105050.00')
        self.assertEqual(iso('09/12/2025',True),'2025-12-09')

    def test_mismatch_rejected(self):
        groups=fixture()
        groups[-1][-1][11]=118501
        with self.assertRaises(StructuredPDFError):
            parse_rows(groups)

    def test_unrecognized_fallback(self):
        self.assertIsNone(parse_rows([[['unrecognized']]]))

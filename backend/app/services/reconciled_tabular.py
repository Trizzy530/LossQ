"""Strict structured CSV/XLSX reader. Unrecognized layouts retain legacy parsing."""
import csv
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal
from .reconciled_pdf import StructuredPDFError


def require(ok, message):
    if not ok:
        raise StructuredPDFError(message)


def key(value):
    return re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode().lower())


def clean(value):
    return str(value).strip() if value is not None else ''


def aliases(*values):
    return {key(v) for v in values}


ACCOUNT = {
    'business_name': aliases('Named insured', 'Assuré / Named Insured'),
    'account_number': aliases('Account / Customer #', 'N° compte / Account Number', 'Account Number'),
    'carrier_name': aliases('Writing carrier', 'Assureur / Carrier', 'Carrier'),
    'agency_name': aliases('Producing agency', 'Courtier / Producing Agency'),
    'state': aliases('Account state', 'Province', 'State'),
    'country': aliases('Country', 'Pays / Country'),
    'currency': aliases('Currency', 'Devise / Currency'),
    'evaluation_date': aliases('Valuation date', 'Date d’évaluation / Evaluation Date', 'Evaluation date'),
    'employee_count': aliases('Employees'),
}
POLICY = [aliases('Policy ref', 'N° police / Policy Number', 'Policy Number'), aliases('Coverage', 'LOB / Coverage'), aliases('Eff. date', 'Prise d’effet / Effective', 'Effective'), aliases('Exp. date', 'Échéance / Expiration', 'Expiration'), aliases('Annual premium', 'Prime / Premium', 'Premium'), aliases('Exposure basis', 'Base exposition / Exposure Basis'), aliases('Exposure', 'Exposition / Exposure')]
CLAIM = [aliases('Claim #', 'N° sinistre / Claim Number', 'Claim Number'), POLICY[0], aliases('LOB'), aliases('Claimant', 'Réclamant / Claimant'), aliases('Jurisdiction', 'Province sinistre / Jurisdiction'), aliases('DOL', 'Date sinistre / Loss Date', 'Loss Date'), aliases('Reported', 'Date déclaration / Reported Date', 'Reported Date'), aliases('Closed date', 'Date fermeture / Closed Date'), aliases('Status', 'Statut / Status'), aliases('Paid total', 'Payé / Paid', 'Paid'), aliases('Outstanding reserve', 'Réserve / Reserve', 'Reserve'), aliases('Total incurred', 'Total engagé / Total Incurred'), aliases('Examiner', 'Expert / Adjuster', 'Adjuster'), aliases('Litigation', 'Litige / Litigation'), aliases('Loss description', 'Description')]
EXPOSURES = {'annualrevenue':'revenue','chiffredaffairesrevenue':'revenue','professionalrevenue':'professional_revenue','vehicles':'vehicle_count','vehiculesvehicles':'vehicle_count','payroll':'payroll','valeurassureepropertytiv':'property_tiv','propertytiv':'property_tiv','equipmenttiv':'equipment_tiv','clientrecords':'client_records','dossiersclientscustomerrecords':'customer_records'}


def amount(value, cad):
    s = clean(value).replace('$','').strip()
    if cad and re.fullmatch(r'-?\d{1,3}(?:[ \u00a0\u202f]\d{3})*(?:,\d{1,2})?', s):
        s = re.sub(r'\s','',s).replace(',','.')
    elif cad and re.fullmatch(r'-?\d+,\d{1,2}', s):
        s = s.replace(',','.')
    else:
        s = re.sub(r'\s','',s).replace(',','')
    require(bool(re.fullmatch(r'-?\d+(?:\.\d{1,2})?',s)), 'Invalid or missing financial amount.')
    return Decimal(s)


def iso(value, cad):
    if isinstance(value, (datetime,date)):
        return value.strftime('%Y-%m-%d')
    for fmt in ('%Y-%m-%d', '%d/%m/%Y' if cad else '%m/%d/%Y'):
        try:
            return datetime.strptime(clean(value),fmt).date().isoformat()
        except ValueError:
            pass
    raise StructuredPDFError('Invalid or ambiguous source date.')


def parse_rows(groups):
    def matches(row, spec):
        return len(row) >= len(spec) and all(key(v) in a for v,a in zip(row,spec))
    p = [(rows,i) for rows in groups for i,row in enumerate(rows) if matches(row,POLICY)]
    c = [(rows,i) for rows in groups for i,row in enumerate(rows) if matches(row,CLAIM)]
    if len(p)!=1 or len(c)!=1:
        return None
    profile = {}
    for rows in groups:
        for row in rows:
            if len(row)<2: continue
            for field, names in ACCOUNT.items():
                if key(row[0]) in names and clean(row[1]):
                    require(field not in profile or profile[field]==row[1], 'Conflicting account metadata.')
                    profile[field]=row[1]
    if not all(profile.get(f) for f in ('business_name','account_number','carrier_name','agency_name','state','country','currency','evaluation_date')):
        return None
    cad = key(profile['country'])=='canada' and key(profile['currency'])=='cad'
    if not cad and not (key(profile['country'])=='unitedstates' and key(profile['currency'])=='usd'):
        return None
    profile['evaluation_date']=iso(profile['evaluation_date'],cad)
    profile['carrier_name']=re.sub(r'\s*\(fictional\)\s*$','',clean(profile['carrier_name']),flags=re.I)
    policies={}; claims={}; exposure_terms={}; totals=None
    rows,i=p[0]
    for row in rows[i+1:]:
        if not any(clean(v) for v in row): continue
        if not clean(row[1] if len(row)>1 else None): break
        require(len(row)>=7,'Incomplete policy row.')
        n,l,e,x,premium,basis,exposure=row[:7]; n=clean(n).upper()
        require(bool(n and clean(l)) and n not in policies and n!=clean(profile['account_number']).upper(),'Invalid or duplicate policy.')
        e,x=iso(e,cad),iso(x,cad); require(e<x,'Invalid policy term.')
        premium,exposure=amount(premium,cad),amount(exposure,cad)
        policies[n]=dict(policy_number=n,line_of_business=clean(l),coverage=clean(l),carrier_name=profile['carrier_name'],carrier=profile['carrier_name'],writing_carrier=profile['carrier_name'],effective_date=e,expiration_date=x,evaluation_date=profile['evaluation_date'],premium=float(premium),annual_premium=float(premium),exposure_basis=clean(basis),exposure_value=float(exposure),claim_count=0,total_incurred=0.0)
        field=EXPOSURES.get(key(basis))
        if field and e<=profile['evaluation_date']<x:
            require(field not in exposure_terms or exposure_terms[field]==exposure,'Conflicting current exposure values.')
            exposure_terms[field]=exposure
    require(bool(policies),'Missing policies.')
    rows,i=c[0]
    for row in rows[i+1:]:
        if not any(clean(v) for v in row): continue
        if key(row[0])=='total':
            require(len(row)>=12,'Missing reported totals.')
            totals=tuple(amount(v,cad) for v in row[9:12]); break
        require(len(row)>=15,'Incomplete claim row.')
        n,p,l,claimant,j,d,r,x,s,paid,reserve,incurred,adjuster,lit,desc=row[:15]; n,p=clean(n).upper(),clean(p).upper()
        require(bool(n) and n not in claims and p in policies,'Invalid claim or policy identity.')
        status={'open':'Open','ouvertopen':'Open','closed':'Closed','fermeclosed':'Closed'}.get(key(s))
        legal={'yes':True,'no':False,'nonno':False,'ouiyes':True}.get(key(lit))
        require(status is not None and legal is not None and bool(clean(x))==(status=='Closed'),'Invalid claim status, closure date or litigation.')
        paid,reserve,incurred=(amount(v,cad) for v in (paid,reserve,incurred)); require(paid+reserve==incurred,'Claim amounts do not reconcile.')
        d,r=iso(d,cad),iso(r,cad); x=iso(x,cad) if clean(x) else None
        require(d<=r and (x is None or r<=x),'Claim dates are out of order.')
        require(bool(clean(claimant) and clean(j) and clean(adjuster) and clean(desc)),'Missing claim administration fields.')
        coverage=policies[p]['line_of_business']
        claims[n]=dict(claim_number=n,policy_number=p,line_of_business=coverage,claim_type=coverage,claimant=clean(claimant),jurisdiction_state=clean(j).upper(),date_of_loss=d,date_reported=r,date_closed=x,status=status,paid_amount=float(paid),reserve_amount=float(reserve),total_incurred=float(incurred),adjuster=clean(adjuster),examiner=clean(adjuster),litigation=legal,litigation_status='Litigation' if legal else '',description=clean(desc))
    calculated=tuple(sum((Decimal(str(v[k])) for v in claims.values()),Decimal(0)) for k in ('paid_amount','reserve_amount','total_incurred'))
    require(bool(claims) and totals==calculated,'Claim totals do not match the document.')
    for n,p in policies.items():
        subset=[v for v in claims.values() if v['policy_number']==n]; p['claim_count']=len(subset); p['total_incurred']=float(sum((Decimal(str(v['total_incurred'])) for v in subset),Decimal(0)))
    current=[p for p in policies.values() if p['effective_date']<=profile['evaluation_date']<p['expiration_date']]
    first=(current or list(policies.values()))[0]
    exposures={k:str(v) for k,v in exposure_terms.items()}
    profile.update(exposures,writing_carrier=profile['carrier_name'],carrier=profile['carrier_name'],producing_agency=profile['agency_name'],customer_number=profile['account_number'],policy_number=first['policy_number'],main_policy=first['policy_number'],effective_date=first['effective_date'],expiration_date=first['expiration_date'],policies=list(policies.values()),policy_numbers=list(policies),current_premium=str(sum((Decimal(str(p['premium'])) for p in current),Decimal(0))),exposure_inputs=exposures,exposure_basis=' | '.join(f'{p["exposure_basis"]}: {p["exposure_value"]}' for p in current),validation={'structured_reconciled':True,'market_country':profile['country'],'market_currency':profile['currency'],'claim_count':len(claims),'policy_count':len(policies),'listed_policy_premium_total':float(sum(Decimal(str(p['premium'])) for p in policies.values())),'reported_totals':dict(zip(('reported_total_paid','reported_total_reserve','reported_total_incurred'),map(float,totals))),'extraction_quality':{'status':'passed','critical_issues':[]}})
    return list(claims.values()),profile


def parse_reconciled_tabular(path):
    if str(path).lower().endswith('.csv'):
        try:
            with open(path,encoding='utf-8-sig',newline='') as f:
                groups=[list(csv.reader(f))]
        except (UnicodeError, csv.Error):
            return None
        return parse_rows(groups)
    if str(path).lower().endswith('.xlsx'):
        from openpyxl import load_workbook
        try:
            book=load_workbook(path,read_only=True,data_only=True)
        except Exception:
            return None
        try:
            return parse_rows([list(sheet.values) for sheet in book.worksheets])
        finally:
            book.close()
    return None

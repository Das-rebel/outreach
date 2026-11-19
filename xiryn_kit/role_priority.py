#!/usr/bin/env python3
"""role_priority.py — CANONICAL role priority P0..P7 (user-mandated Aug 30, P0-indexed).

  P0  Fintech (payments / lending / wealth / insurtech)
  P1  Banks
  P2  NBFC
  P3  Internal fintech (fintech arms of large companies)
  P4  D2C growth & strategy
  P5  D2C growth roles
  P6  D2C marketing roles
  P7  Everything else

SEARCH + APPLY ORDER follows this list (fintech first). Apply policy:
  * P0 fintech -> apply immediately, even with fewer matching years
  * P1-P3      -> apply when the 7.0 gate is GREEN and the quality layer passes
  * P4-P6 D2C  -> apply
  * P7         -> leftover time only (allow_p7=True)

CLASSIFICATION IS COMPANY-FIRST. A company on the D2C list stays D2C even when its JD
mentions payments/credit; desc keywords only decide the bucket for companies we do not
recognise, and only on explicit self-identification ("we are a fintech", "an NBFC", ...).
"""
import re

PRIORITY_LABELS = {
    0: 'P0 fintech', 1: 'P1 banks', 2: 'P2 nbfc', 3: 'P3 internal-fintech',
    4: 'P4 d2c-growth-strategy', 5: 'P5 d2c-growth', 6: 'P6 d2c-marketing', 7: 'P7 other',
}

# ---------- known company rosters (company-first signal) ----------
FINTECH_CO = re.compile(
    r'\b(kraken|razorpay|pine\s?labs?|cred\b|slice|jupiter|zerodha|groww|indmoney|ind\s?money|'
    r'onecard|one\s?card|kreditbee|acko|policy\s?bazaar|paisa\s?bazaar|mobi\s?kwik|'  # MobiKwik (was 'mobiwik' - missing the 'k', never matched)
    r'uni\s?cards?|famapp|moneytap|mone\s?tap|zetwerk|khatabook|bharatpe|freecharge|'
    r'paynearby|acacia|fpl\s?tech|oxyzo|vayana|open\s?money|paytm|phonepe|amazon\s?pay|'
    r'google\s?pay|samsung\s?pay|fi\s?money|niyo\s?fintech|woz\w*|cred\s?avenue|'
    r'groww\s?x|jupiter\s?financial|fi\s?tech|lendingkart|slice\s?dsl|ninjacard|'
    r'transunion|experian|equifax|crisil|ice\s?data|fico|worldline|paysafe|upto\s?fintech|'
    r'kfin|bharatpe\s?financial|spinny\s?financial|moneytap\s?financial|bigul|'
    r'upgrad\s?fintech|jupiter\s?fintech|acko\s?digital|insurtech|lifi|fiserv|visa\s?india|'
    r'liquiloans|liquidity\s?capital|m2p\s?fintech|five\s?khat|ju\s?financial|'
    r'navi\s?financial|cleartax|zerodha\s?wealth|indian\s?institute\s?of\s?stock|'
    r'nse\s?india|bse\s?india|stockedge|fine\s?tech|finly\s?tech|bharatpe\s?pay|'
    r'payment\s?samm\s?lending|mudhalvan|mint\s?financial'
    r'hdb\s?financial|visa|mastercard|rupay|paytm\s?payments|'
    r'acko\s?insurance|'
    # 2026-11-05 expanded roster - real Indian fintech / payment / lending names
    r'cashfree|payU|paygin|billdesk|ccavenue|airwallex|juspay|'
    r'saracloud|perfios|setu|tracelog|nium|mobikwik|'
    r'upstox|ind\s?securities|fundbox|zol?ve|ay\s?finance|'
    r'clink|earlysalary|capital\s?float|'
    r'incred|moneyview|ugro|credit\s?on\s?finance|home\s?credit|clix|bifold|'
    r'axio|fibe|payghar|my\s?money|quicko|'
    r'niyo\s?technologies|onecard\s?financial|zest\s?money|fincare|bharatpe\s?fin|'
    r'varun\s?finance|clove|dojima|oxygon|get\s?onboard|hyperverge|'
    r'decentro|wedenz|accelerant|payanywhere|icici\s?direct|'
    r'postpay|simpl|axis\s?bank\s?card|'
    # 2026-11-09 roster audit: added real fintechs seen in live applications;
    # removed non-fintech tokens that were mis-tiering (see MEMORY note).
    r'snapmint|plum|plumhq|qlub|atomic\s?capital|vfs\s?global|northern\s?arc|sarwa|'
    # 2026-11-17: two more real fintechs surfaced by the litescrape harvest —
    # Aspora (borderless banking, Sequoia/Greylock backed) and smallcase
    # (stock-market investment app). Both were falling to P7 'other' and being
    # treated as leftover-time-only despite being P0 fintech employers.
    r'aspora|smallcase|'
    r'creditaccess|tink|tipranks|credenovation|citruspay|happay|'
    r'riskpay|settlemint|blackcat|indifi|piramal\s?capital|'
    r'fibe\s?financial|onecard|one\s?card\s?financial|uni\s?cards?|'
    r'jupiter\s?financial|slice\s?financial|niyo|fi\s?money|'
    r'groww|zerodha|upstox|indmoney|ind\s?money)\b', re.I)
BANK_CO = re.compile(
    r'\b(hdfc|icici|axis\s?bank|kotak|sbi\b|state\s?bank|yes\s?bank|federal\s?bank|'
    r'au\s?small\s?finance\s?bank|au\s?bank|bandhan|punjab\s?national|\bpnb\b|'
    r'bank\s?of\s?baroda|standard\s?chartered|hsbc|barclays|\bdbs\b|citi\s?bank|'
    r'jpmorgan|jpmorgan\s?chase|wells\s?fargo|capital\s?one|'
    r'bnp\s?paribas|socgen|commerzbank|emirates\s?nbd|fab\s?bank|first\s?abu\s?dhabi|'
    r'bank\s?of\s?america|\bboa\b|deutsche\s?bank|rabobank|ing\s?vysya|canara\s?bank|'
    r'indusind|bank\s?of\s?baroda|uco\s?bank|'
    # 2026-11-05 expanded bank roster
    r'idfc\s?first|rbl\s?bank|csb\s?bank|karur\s?vyat\s?bank|'
    r'jana\s?small\s?finance|equitas\s?small\s?finance|ujjivan\s?small\s?finance|'
    r'utkarsh\s?small\s?finance|suryoday\s?small\s?finance|'
    r'airtel\s?payments\s?bank|esafa|easyacres|'
    r'union\s?bank|central\s?bank\s?of\s?india|bank\s?of\s?india|'
    r'indian\s?overseas\s?bank|south\s?indian\s?bank|'
    r'indian\s?bank|bank\s?of\s?maharashtra|karnataka\s?bank|kerala\s?bank|'
    r'oriental\s?bank|corporation\s?bank|andhra\s?bank|allahabad\s?bank|'
    r'dena\s?bank|dcb\s?bank|vijaya\s?bank|tamilnad\s?mercantile|'
    r'syndicate\s?bank|indian\s?international\s?bank|'
    r'bandhan\s?bank|payments\s?bank|'
    r'j&k\s?bank|assam\s?grameen|cauvery|'
    r'dhanlaxmi|karnataka\s?bank\s?mahila|'
    r'kotak\s?mahindra\s?bank|hdfc\s?bank|'
    r'icici\s?bank|axis\s?bank|sbi\s?bank|'
    # 2026-11-09 audit: added global banks seen in live applications; removed
    # bare 'chase'/'fab' tokens that matched unrelated brands (Fab India).
    r'monzo|revolut|nubank|n26|klarna|paypal|adyen|wise|payoneer|'
    r'goldman\s?sachs|morgan\s?stanley|santander|danske|swedbank|'
    r'icbc|swiss\s?bank|credit\s?suisse|barclays\s?card|'
    r'brex|ramp|mercury|sofi|discover|ally\s?financial|'
    r'us\s?bank|pnc\s?bank|citizens\s?financial|keybank|'
    r'tide|starling\s?bank|clearbank|zopa|goodyear|monz\s?business)\b', re.I)
NBFC_CO = re.compile(
    r'\b(bajaj\s?finserv|bajaj\s?finance|cholamandalam|chola\s?finance|shriram\s?finance|'
    r'muthoot\s?finance|muthoot|manappuram|five\s?star|fivestar|iifl|aditya\s?birla\s?capital|'
    r'poonawalla|fullerton\s?india|dmi\s?financial|l&t\s?finance|l&t\s?financial|'
    r'microfinance|grameen|ujjivan|equitas|cl\s?financial|mfs\s?lending|'
    r'five\s?star\s?housing|instant\s?credit|kredit\s?bee\s?financial|shivalik\s?finance|'
    r'pashupati\s?finance|gold\s?loan\s?company|'
    # 2026-11-05 expanded NBFC / housing-finance roster
    r'mahindra\s?finance|satin\s?creditcare|aavas\s?finance|'
    r'fincare\s?finance|bharat\s?bank|shubharambh\s?finance|'
    r'indi\s?gold\s?finance|poonawalla\s?capital|reliance\s?capital|'
    r'ge\s?capital\s?finance|fullerton\s?digital|'
    r'earlysalary\s?financial|incred\s?financial|'
    r'icici\s?lending|unifi\s?financial|moneytap\s?finance|'
    r'axio\s?financial|bifold|ireda\s?finance|'
    r'fusion\s?finance|navi\s?finserv|clix|'
    r'ola\s?financial|ace\s?credit|'
    r'kotak\s?finance|jio\s?financial\s?services|prestige\s?finance|'
    r'wealth\s?insure|fin\s?bee\s?financial|gold\s?loan|'
    # 2026-11-09 audit: these were mis-tiered as P0 fintech
    r'tata\s?capital|fortune\s?finance|spinny\s?financial|'
    r'sbfc|sundaram\s?finance|piramal\s?finance|mas\s?financial|'
    r't\s?capital|vivan\s?credit|five\s?star\s?finance)\b', re.I)
INTERNAL_FIN_CO = re.compile(
    r'\b(google|amazon|flipkart|swiggy|zomato|reliance|walmart|microsoft|tata|'
    r'meesho|mamaearth|bajaj\s?auto|mahindra|telecom|airtel|jio|ola|ola\s?electric|'
    r'white\s?harton|axis\s?it|icici\s?direct|kotak\s?life|hdfc\s?life|'
    # 2026-11-05 expanded internal-fintech / platform employers
    r'blinkit|zepto|instamart|swiggy\s?instamart|jio\s?mart|'
    r'reliance\s?retail|trent|avenue\s?supermarkets|dmart|'
    r'delhivery|shadowfax|shiprocket|elasticrun|'
    r'urban\s?company|tata\s?cliq|myntra|ajio|'
    r'pepperfry|paytm\s?mall|amazon\s?pay|'
    r'retail\s?axis|axis\s?retail)\b', re.I)
D2C_CO = re.compile(
    r'\b(nykaa|wow\s?skin|mc\s?caffeine|wakefit|minimal(?:ist)?|pilgrim|sugar\s?cosmetics|'
    r'bo\s?at\b|lenskart|country\s?delight|firstcry|pepperfry|mamaearth|dotskeys|beardo|'
    r'sleepycat|bombay\s?shave|plum|yes\s?madras|blue\s?tokai|detergent|century\s?ply|'
    r'tanishq|redfm|bewakoof|zivame|purplle|himalaya|schbang|healthkart|tata\s?1mg|netmeds|'
    r'pharmeasy|apollo\s?24|boat|watch|thesleepcompany|sleep\s?company|rage\s?coffee|'
    r'coffee|ayurveda\s?experience|organica|beyond\s?skin|glint|plumgoodness|de\s?blanq|'
    # 2026-11-05 expanded D2C / consumer-brand roster
    r'dot\s?&\s?key|sugandha|sheet\s?mask|summerfridays|foxtale|'
    r'brut|intune|snitch|downtown|blouson|suta|kanika|aza|libas|'
    r'the\s?indian\s?garage|pantaloons|clovia|myntra|ajio|'
    r'tata\s?cliq|man\s?matters|dr\s?batra|wellbeing\s?nutrition|'
    r'nutrition\s?&\s?biosciences|wyscha|dr\s?lal|metropolis|thyrocare|'
    r'vedantu|practo|zoe\s?app|getsure|care\s?health|'
    r'apollo\s?pharmacy|net\s?pharma|wellness\s?forever|'
    r'kettle\s?wellness|plum\s?goodness|wow\s?skin|'
    r'og\s?hair|trysa|minimalist|'
    r'cocokraft|lil\s?pause|'
    r'growlong|mann\s?plann|plann\s?app)\b', re.I)

# ---------- explicit self-identification (only used for UNKNOWN companies) ----------
SELF_FINTECH = re.compile(
    r'(we\s+are|is|are)\s+(an?\s+)?'
    r'(leading\s+|indias?\s+|indian\s+|online\s+|digital\s+|global\s+|'
    r'fast[- ]growing\s+|emerging\s+|new\s+age\s+)*'
    r'(fintech|fin-tech|financial\s+technology)\b|'
    r'\b(payments?\s+gateway|merchant\s+acquir\w+|digital\s+lending|neobank|insurtech|'
    r'bnpl|embedded\s+finance|payments\s+infrastructure|upi\s+payments?|'
    r'p2p\s+lending|peer[- ]to[- ]peer\s+lending|lending\s+platform|digital\s+loan|'
    r'loan\s+against\s+property|gold\s+loan|wealth\s+management\s+platform|'
    r'payment\s+aggregator|fintech\s+platform|lending\s+fintech|'
    r'payments\s+fintech|online\s+lending\s+fintech|'
    r'financial\s+technology\s+company|online\s+lending\s+company)\b', re.I)
SELF_BANK = re.compile(
    r'\b(is|are)\s+(a|an)\s+(commercial\s+bank|private\s+bank|public\s+sector\s+bank|'
    r'payments\s+bank|small\s+finance\s+bank|co-?operative\s+bank|banking\s+company)\b|'
    r'\b(core\s+banking|universal\s+bank|retail\s+banking\s+and\s+corporate\s+banking)\b', re.I)
SELF_NBFC = re.compile(
    r'\b(is|are)\s+(an?\s+)?(nbfc|non-?banking\s+financial\s+company)\b|'
    r'\b(nbfc\s+registered|registered\s+with\s+the\s+rbi\s+as\s+an\s+nbfc)\b', re.I)
SELF_INTERNAL_FIN = re.compile(
    r'\b(fintech\s+arm|fintech\s+division|fintech\s+unit|internal\s+fintech|payments\s+division)\b', re.I)

# ---------- OFF-SECTOR employers (2026-11-09) ----------
# A company in these sectors can never be a fintech / bank / NBFC / D2C brand,
# regardless of what its JD text happens to mention.  Without this, a real
# estate JD mentioning "banking" (mortgages) was classified P1 bank, a hotel
# JD mentioning "payments" became P0 fintech, and a recruiter JD saying
# "we are a leading..." matched the self-ID patterns.
OFF_SECTOR_CO = re.compile(
    r'\b(hotel|resort|hostel|real\s*estate|realty|property\s*finder|'
    r'remax|property\s*tech|brokerage|staffing|recruit(ment|ing|ers)|'
    r'hr\s*services|manpower|consult(ancy|ing)\s*(firm|services|group|llp)?|'
    r'partners\s*group|capital\s*advisory|mckinsey|bcg|deloitte|pwc|'
    r'ey\b|kpmg|ernst\s*young|hospital|clinic|diagnostic|pharma|'
    r'travel\s*agency|tourism|restaurant|cafe|coffeehouse|'
    r'gym|fitness|spa|salon|school|college|university|institute|academy|'
    r'training\s*centre|event\s*management|advertising\s*agency|'
    r'media\s*agency|creative\s*studio)\b', re.I)

# ---------- role-family signals (for the D2C buckets) ----------
GROWTH_KW = re.compile(r'\b(growth|go[- ]?to[- ]?market|gtm|demand|acquisition|'
                        r'marketplace|strategy|strategic|expansion|new\s+business|'
                        r'e[- ]?commerce|ecommerce|ecom|quick\s?commerce|'
                        r'customer\s+acquisition|revenue|monetisation|monetization)\b', re.I)
MKT_KW = re.compile(r'\b(marketing|brand|performance\s+marketing|demand\s+generation|'
                    r'product\s+marketing|category\s+management|customer\s+lifecycle|'
                    r'lifecycle\s+marketing|retention\s+marketing|martech|communications|'
                    r'ecommerce|content|social\s?media|seo|crm|experiential|'
                    r'brand\s+marketing|growth\s+marketing|trade\s+marketing)\b', re.I)
STRATEGY_TITLE = re.compile(r'\b(strategy|strategic)\b', re.I)
LEAD_TITLE = re.compile(r'\b(head|chief|cmo|cro|cfo|ceo|president|vp|vice\s?president|'
                         r'founder|general\s?manager|gm)\b', re.I)


def classify(company='', title='', description='', location=''):
    """Return (priority_int, label, basis). Lower number = higher priority."""
    co = (company or '').strip()
    title = (title or '').strip()
    blob = f"{co} {title} {description or ''}".lower()

    # ---------- 0. off-sector employers are never P0-P6 ----------
    # (2026-11-09: the self-ID patterns used to scan the WHOLE description, so a
    #  real-estate JD mentioning "banking" was classified P1 bank and a hotel
    #  JD mentioning "payments" was classified P0 fintech.)
    if co and OFF_SECTOR_CO.search(co):
        return (7, PRIORITY_LABELS[7], 'company:off-sector')

    # Self-identification is only trusted from the COMPANY's own opening
    # description, never from the whole job description.
    self_blob = f"{co} {(description or '')[:600]}".lower()

    # ---------- 1. company-first (authoritative) ----------
    if co and FINTECH_CO.search(co):
        return (0, PRIORITY_LABELS[0], 'company:fintech')
    if co and BANK_CO.search(co):
        return (1, PRIORITY_LABELS[1], 'company:bank')
    if co and NBFC_CO.search(co):
        return (2, PRIORITY_LABELS[2], 'company:nbfc')
    if co and INTERNAL_FIN_CO.search(co):
        # a large co whose fintech arm is the target (only if the role is fintech-flavoured)
        if SELF_FINTECH.search(blob):
            return (0, PRIORITY_LABELS[0], 'company:fintech-selfid')
        if SELF_INTERNAL_FIN.search(blob) or \
                re.search(r'\b(payments?|fintech|upi)\b', title, re.I):
            return (3, PRIORITY_LABELS[3], 'company:internal-fintech')
        # 2026-11-05: a marketing / growth function at a large platform employer
        # (quick commerce, marketplace, super-app) is an internal-fintech-flavoured
        # role - score it as P3 instead of dropping it to "other" (P7).
        if GROWTH_KW.search(title) or MKT_KW.search(title):
            return (3, PRIORITY_LABELS[3], 'company:internal-fintech-marketing')
    if co and D2C_CO.search(co):
        if GROWTH_KW.search(blob) and (STRATEGY_TITLE.search(title) or LEAD_TITLE.search(title)):
            return (4, PRIORITY_LABELS[4], 'd2c:growth+strategy')
        if GROWTH_KW.search(blob):
            return (5, PRIORITY_LABELS[5], 'd2c:growth')
        if MKT_KW.search(blob):
            return (6, PRIORITY_LABELS[6], 'd2c:marketing')
        return (7, PRIORITY_LABELS[7], 'd2c-company-other-role')

    # ---------- 2. unknown company: only explicit self-identification decides ----------
    if SELF_FINTECH.search(self_blob):
        return (0, PRIORITY_LABELS[0], 'desc:fintech-selfid')
    if SELF_BANK.search(self_blob):
        return (1, PRIORITY_LABELS[1], 'desc:bank-selfid')
    if SELF_NBFC.search(self_blob):
        return (2, PRIORITY_LABELS[2], 'desc:nbfc-selfid')
    if SELF_INTERNAL_FIN.search(self_blob):
        return (3, PRIORITY_LABELS[3], 'desc:internal-fintech')
    # unknown consumer brand? only if it brands itself as a consumer/D2C business
    # 2026-11-01: expanded self-ID patterns — quick-commerce, beauty brand,
    # e-commerce brand/platform, digital-first brand (Whizz HR case: "quick-commerce beauty brand")
    if re.search(r'\b(d2c|direct[- ]to[- ]consumer|consumer\s+brand|our\s+own\s+brands?|'
                 r'quick[- ]commerce|q[- ]commerce|beauty\s+brand|personal\s+care\s+brand|'
                 r'e[-]?commerce\s+(brand|company|platform)|ecommerce\s+(brand|company|platform)|'
                 r'digital[- ]first\s+brand|consumer\s+internet\s+brand)\b',
                 self_blob, re.I) and (GROWTH_KW.search(self_blob) or MKT_KW.search(self_blob)):
        if GROWTH_KW.search(self_blob) and (STRATEGY_TITLE.search(title) or LEAD_TITLE.search(title)):
            return (4, PRIORITY_LABELS[4], 'desc:d2c-growth+strategy')
        if GROWTH_KW.search(blob):
            return (5, PRIORITY_LABELS[5], 'desc:d2c-growth')
        return (6, PRIORITY_LABELS[6], 'desc:d2c-marketing')
    return (7, PRIORITY_LABELS[7], 'other')


def should_apply(priority, allow_p7=False):
    """P7 is leftover-time only."""
    return True if priority <= 6 else bool(allow_p7)


if __name__ == '__main__':
    tests = [
        ('Razorpay', 'Head of Growth', 'payments platform for SMBs in India'),
        ('HDFC Bank', 'Head of Digital Marketing', 'retail banking marketing'),
        ('Bajaj Finserv', 'Head of Growth', 'lending and insurance arm'),
        ('Google', 'Head of Payments Growth', 'Google Pay fintech arm'),
        ('Nykaa', 'Head of Growth & Strategy', 'beauty d2c brand'),
        ('Nykaa', 'Head of Marketing', 'beauty d2c brand marketing'),
        ('The Ayurveda Experience', 'Head, Performance Marketing', 'we are a D2C wellness brand'),
        ('The Sleep Company', 'VP, Digital Growth', 'D2C sleep brand, omnichannel'),
        ('Some Analytics Firm', 'Director of Marketing', 'enterprise analytics marketing'),
        ('Acme Retail Pvt Ltd', 'Head of Growth', 'we are a leading fintech company offering digital lending'),
        ('XYZ Capital', 'Head of Collections & Strategy', 'an NBFC registered with the RBI as an NBFC'),
    ]
    for co, ti, de in tests:
        p, lab, basis = classify(co, ti, de)
        print(f'P{p}  {lab:<28} {co:<26} | {ti[:32]:<32} ({basis})')

#!/usr/bin/env python3
"""relevance_v2 — rebuilt relevance scorer (2026-11-09).

WHY REBUILT
-----------
The v1 engine (xiryn_kit/relevance_match.py) scored
    function(<=40) + tier(5..30) + lead(12) + geo(8)
with only ~25 points separating P0 fintech from P7 "everything else".
Consequences seen in production:
  * IT-services / IT-solutions / BPO / staffing employers (a BAD-MATCH employer
    class) still landed at 65-70 and were applied.  User directive 2026-11-09:
    "it solutions are bad match recheck priority list and use that in
    relevance score".
  * P7 "other" roles competed on equal footing with P0 fintech, even though the
    user's role priority says P0 fintech > P1 banks > P2 NBFC > P3 internal
    fintech > P4 D2C growth+strategy > P5 D2C growth > P6 D2C marketing >
    P7 everything else (P7 = leftover time only).

WHAT CHANGED
------------
1. EMPLOYER CLASS is a HARD BLOCK, not a score penalty:
      IT services / IT solutions / BPO / staffing / consulting / outsourcing /
      manpower / offshore development / IT consulting  -> RED (employer_class)
2. Sector PRIORITY dominates the score (bonus 42..8) so the ordering the user
   mandated is decisive: a P0 fintech role outranks a P7 role regardless of
   keyword density.
3. Location priority is explicit: India metro (primary) > GCC > other intl
   (secondary).  Tier-2 India cities and US-onsite stay hard RED.
4. P7 ("everything else") is capped: it can never reach GREEN without an
   explicit allow_p7 flag, because P7 is "leftover time only".
5. Every verdict carries `basis` (why it scored that way) so decisions are
   auditable and can be re-checked against the priority list.

Public API
----------
    score_job(company, title, location, description, allow_p7=False)
        -> dict(verdict, score, priority, tier, basis, reasons, hard_block)
    EMPLOYER_CLASS_BLOCK, PRIORITY_BONUS
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from xiryn_kit.role_priority import classify as _priority_classify
except Exception:
    _priority_classify = None

# --------------------------------------------------------------------------
# 1. EMPLOYER CLASS — hard blocks (bad-match companies, independent of sector)
# --------------------------------------------------------------------------
# Each entry: (regex, reason). Matched against company + first 400 chars of JD.
EMPLOYER_CLASS_BLOCK = [
    (r'\bIT\s+solutions?\b', 'employer_class:it_solutions'),
    (r'\bIT\s+services?\b', 'employer_class:it_services'),
    (r'\bIT\s+consulting\b', 'employer_class:it_consulting'),
    (r'\bsoftware\s+services?\b', 'employer_class:software_services'),
    (r'\btechnology\s+services?\b', 'employer_class:tech_services'),
    (r'\bIT\s+staffing\b', 'employer_class:it_staffing'),
    (r'\bmanpower\s+(services|consultancy|contract)\b', 'employer_class:manpower'),
    (r'\boutsourc(ing|e)\b', 'employer_class:outsourcing'),
    (r'\boffshore\s+(development|services)\b', 'employer_class:offshore_dev'),
    (r'\bBPO\b|\bcall\s+centre\b|\bcall\s+center\b', 'employer_class:bpo'),
    (r'\bstaffing\b|\bstaffing\s+solutions\b', 'employer_class:staffing'),
    (r'\bexecutive\s+search\b|\brecruit(ment|ing)\s+(firm|agency|solutions)\b',
     'employer_class:recruitment_agency'),
    (r'\bheadhunt(ing|ers)\b', 'employer_class:headhunting'),
    (r'\bhuman\s+resources\s+(consult|serv|outsourc)', 'employer_class:hr_services'),
    (r'\bmanagement\s+consulting\b|\bconsultancy\s+firm\b',
     'employer_class:consulting_firm'),
    # 2026-11-11: the user-mandated hard block covers staffing, recruiting and
    # consulting employers, but "Job Management Consultants" style names
    # slipped past every pattern (a staffing firm was judged 92 and nearly
    # applied). These extra forms close the gap.
    (r'\b(job|staff|people|human\s+resource|hr|talent)\s+(management\s+)?'
     r'consult(ant|ancy|ing|ants)\b', 'employer_class:consulting_firm'),
    (r'\bconsult(ant|ancy|ing|ants)\b', 'employer_class:consulting_firm'),
    (r'\b(staffing|recruiting|recruitment|placement|staffing\s+solutions)\b',
     'employer_class:staffing'),
    (r'\bjob\s+(management|portal|board|street)\b', 'employer_class:job_board'),
]
_EMPLOYER_RE = [(re.compile(p, re.I), r) for p, r in EMPLOYER_CLASS_BLOCK]


def employer_class(company, description=''):
    """Return (is_bad_match, reason) for the employer class."""
    blob = f"{company or ''} {str(description or '')[:400]}"
    for rx, reason in _EMPLOYER_RE:
        if rx.search(blob):
            return True, reason
    return False, None


# --------------------------------------------------------------------------
# 1c. CLIENT-DISCLOSURE exception for staffing/recruitment firms (R61,
# user-approved 2026-11-15): allow when the JD names a relevant client.
# --------------------------------------------------------------------------
_STAFFING_BLOCK_RE = re.compile(
    r'employer_class:(it_staffing|staffing|recruitment_agency|headhunting)', re.I)

_CLIENT_DISCLOSE_RE = re.compile(
    r'(?:for|on\s+behalf\s+of|client[\s:,-]+|our\s+client[\s:,-]+)'
    r'([A-Z][\w&.\'-]*(?:\s+[A-Z][\w&.\'-]*){0,4})', re.I)


def _staffing_client_exception(company, title, description):
    """True when a staffing/recruitment employer discloses a relevant client."""
    import sys as _s
    _s.path.insert(0, __file__.rsplit('/', 2)[0] if '/' in __file__ else '.')
    from xiryn_kit.role_priority import classify as _classify
    # must be a staffing-family block only
    bad, why = employer_class(company, description)
    if not (bad and _STAFFING_BLOCK_RE.search(why)):
        return False
    if not description or len(description) < 40:
        return False
    # find client mentions
    m = _CLIENT_DISCLOSE_RE.search(description[:1200])
    if not m:
        return False
    client = m.group(1).strip(" .,;:-").strip()
    if not client or client.lower() in ('us', 'you', 'our', 'the', 'a', 'an'):
        return False
    p, _label, _basis = _classify(client, title, description[:600], '')
    return p in (0, 1, 2, 3)


# --------------------------------------------------------------------------
# 2. SECTOR PRIORITY (user-mandated, P0-indexed, P0 = best)
# --------------------------------------------------------------------------
PRIORITY_BONUS = {
    0: 42,   # fintech: payments / lending / wealth / insurtech
    1: 38,   # banks
    2: 34,   # NBFC
    3: 30,   # internal fintech / fintech arm of a large company
    4: 24,   # D2C growth & strategy
    5: 20,   # D2C growth roles
    6: 16,   # D2C marketing roles
    7: 8,    # everything else  (leftover time only)
}
PRIORITY_LABEL = {
    0: 'fintech', 1: 'bank', 2: 'nbfc', 3: 'internal_fintech',
    4: 'd2c_growth_strategy', 5: 'd2c_growth', 6: 'd2c_marketing',
    7: 'other',
}

# --------------------------------------------------------------------------
# 3. FUNCTION FAMILY (target role family for a growth/marketing leader)
# --------------------------------------------------------------------------
FUNCTION_KW = re.compile(
    r'\b(marketing|growth|gtm|go[- ]to[- ]market|brand|demand|communications?|'
    r'comms|partnerships?|business\s+development|revenue|digital|ecommerce|'
    r'e-commerce|customer\s+acquisition|cmo|chief\s+marketing|product\s+marketing|'
    r'lifecycle|crm|performance\s+marketing|performance\s+media|media|'
    # 2026-11-18: a 'Global Head of Social' is senior marketing leadership
    # (Revolut), not a functionless role - the social/media family belongs
    # to marketing. The senior-ladder block still rejects junior social roles.
    r'social|'
    r'category|chief\s+growth|chief\s+commercial|commercial|merchandising|'
    # 'd2c' implies a growth/marketing remit (the ladder's P4/P5 is D2C
    # growth), so 'Director - D2C' must not be blocked as functionless.
    r'd2c|'
    # 2026-11-19: martech / ads / advertising / activation / content /
    # personalisation are marketing leadership remit too
    r'martech|mar-tech|ads\b|advertising|activation|personalisation|'
    r'personalization|content\s+marketing|performance\s+ads|'
    r'social\s+media\s+marketing)\b',
    re.I)
SALES_RE = re.compile(
    r'\b(sales|sales\s*manager|inside\s*sales|field\s*sales|sales\s*leadership|'
    r'revenue\s*operations?|revops|account\s+(executive|manager)|business\s*development)\b',
    re.I)
SENIOR_RE = re.compile(
    r'\b(head|chief|cmo|ceo|coo|vp|vice\s*president|avp|assistant\s*vice\s*president|'
    r'director|associate\s*director|group\s+head|president|founder|partner|'
    r'global\s+head|senior\s+director)\b', re.I)
LEAD_RE = re.compile(
    r'\b(lead|leads|leader|heads?|drives?|owns?|manages?|responsible\s+for|'
    r'builds?|grows?|sets?\s+strategy|strategy|pioneer|establish|accelerate|'
    r'accountable)\b', re.I)
JUNIOR_RE = re.compile(
    r'\b(junior|intern|trainee|executive\s+director\s+of\s+sales|'
    r'assistant\s+manager|senior\s+manager|manager|analyst|specialist)\b',
    re.I)
MANAGER_OK = re.compile(r'\b(general\s*manager|\bGM\b|group\s+head)\b', re.I)
EQUITY_RE = re.compile(
    r'\b(co-?founder|equity\s+only|stock\s+options?|profit\s*share|'
    r'founder\s*[-/]\s*partner|unfunded|revenue\s*share)\b', re.I)
# engineering-only titles (a marketing/growth leader is not a fit)
ENGINEERING_RE = re.compile(
    r'\b(principal\s+engineer|senior\s+engineer|software\s+engineer|'
    r'engineering\s+director|engineering\s+manager|engineering\s+lead|'
    r'devops\s+(director|manager|lead)|data\s+engineer|'
    r'engineering\s*&\s*infrastructure|site\s+reliability)\b', re.I)
# product / engineering-owning titles that are NOT marketing (product marketing
# IS a valid marketing role and is handled by FUNCTION_KW).
# Nov 17 2026: 'Head Product Owner, Digital Client Experience Platforms' at
# Morgan Stanley scored 84 and was LLM-approved because the business-unit
# prefix 'Wealth Management' matched FUNCTION_KW on the word 'Management'.
PRODUCT_OWNER_RE = re.compile(
    r'\b(product\s+owner|product\s+management|head\s+of\s+product|'
    r'product\s+director|platform\s+owner|technical\s+product\s+manager)\b', re.I)
# hospitality / venue roles in the title
HOSPITALITY_TITLE_RE = re.compile(
    r'\b(hospitality|hotels?|resorts?|restaurants?|venues?|cafe|catering|'
    r'food\s*&\s*beverage|f\s*&\s*b)\b', re.I)


def clean_title(title, company=''):
    """Some lanes store the title as "<Company> - <Real Title>".

    Also strips a business-unit prefix such as 'Wealth Management - Executive
    Director, Head Product Owner ...' — the prefix otherwise makes FUNCTION_KW
    match on the word 'Management' (i.e. 'Wealth Management') and lets a
    non-marketing role look like a marketing one.
    """
    t = (title or '').strip()
    c = (company or '').strip()
    if c and t.lower().startswith(c.lower() + ' - '):
        t = t[len(c) + 3:].strip()
    if ' - ' in t:
        head, _, rest = t.partition(' - ')
        if head and rest and len(head.split()) <= 4 and \
                re.search(r'\b(head|chief|cmo|ceo|vp|vice\s+president|avp|'
                          r'director|manager|lead|president)\b', rest, re.I):
            t = rest.strip()
    return t

# --------------------------------------------------------------------------
# 4. LOCATION
# --------------------------------------------------------------------------
# --- user-mandated exclusion list (2026-11-17) ---------------------------
# Only swiggy and groww are excluded from big tech; these five companies were
# declined by the user and must never be applied to, no matter how well they
# score.
# 2026-11-17: user removed tech mahindra, capgemini, mindtree, ltimindtree,
# persistent and ltts from the exclusion list - they are no longer blocked.
USER_EXCLUDE_CO = re.compile(
    r'\b(swiggy|groww|infosys|wipro|accenture|cognizant|hcl\s+tech|'
    r'tresvista|certifyos|experian|perceptyne|dream\s+cricket)\b', re.I)

INDIA_METRO = re.compile(
    r'\b(bangalore|bengaluru|mumbai|delhi|new\s*delhi|hyderabad|pune|gurgaon|'
    r'gurugram|noida|chennai|kolkata|ahmedabad|'
    r'navi\s*mumbai|vashi|andheri|bandra|powai)\b', re.I)
INDIA_TIER2 = re.compile(
    r'\b(jaipur|indore|kochi|coimbatore|mysore|mysuru|thiruvananthapuram|'
    r'guwahati|bhubaneswar|ranchi|lucknow|nagpur|surat|visakhapatnam|'
    r'chandigarh|ludhiana|patna|bhubaneswar|vadodara|mysore)\b', re.I)
GCC_RE = re.compile(
    r'\b(dubai|abu\s*dhabi|doha|riyadh|jeddah|kuwait\s*city|manama|muscat|'
    r'bahrain|dubai\s*internet|city\s*of\s*dubai|emirates|saudi\s*arabia|'
    r'qatar|kuwait|oman|bahrain)\b', re.I)
US_ON_SITE = re.compile(
    r'\b(new\s*york|san\s*francisco|seattle|austin|boston|chicago|los\s*angeles|'
    r'remote\s*-\s*usa|usa\s*remote|united\s*states\s*remote|us\s*remote)\b', re.I)
INTL_RE = re.compile(
    r'\b(uk|united\s*kingdom|london|singapore|hong\s*kong|tokyo|berlin|'
    r'netherlands|switzerland|france|germany|australia|sydney|'
    r'melbourne|dubai\s*remote|worldwide|anywhere|global\s*remote)\b', re.I)
REMOTE_ANY = re.compile(r'\b(remote|work\s*from\s*home|wfh|anywhere)\b', re.I)


def location_tier(location):
    """Return (tier, bonus, note). tier: 'india' | 'gcc' | 'intl' | 'tier2' |
    'us' | 'none'."""
    loc = location or ''
    if US_ON_SITE.search(loc) and not INDIA_METRO.search(loc):
        return 'us', 0, 'US onsite (blocked)'
    if INDIA_TIER2.search(loc) and not INDIA_METRO.search(loc):
        return 'tier2', 0, 'India tier-2 city (blocked)'
    if INDIA_METRO.search(loc):
        return 'india', 10, 'India metro (primary target)'
    if GCC_RE.search(loc):
        return 'gcc', 6, 'GCC (secondary target)'
    if REMOTE_ANY.search(loc) and INTL_RE.search(loc):
        return 'intl', 3, 'International remote (secondary)'
    if INTL_RE.search(loc):
        return 'intl', 2, 'International onsite (secondary)'
    if REMOTE_ANY.search(loc):
        return 'remote', 4, 'Remote (unspecified)'
    return 'none', 0, 'location not recognised'


def _legacy_priority(company, title, description):
    """Fallback priority when xiryn_kit.role_priority is unavailable."""
    blob = f"{company} {title} {(description or '')[:1500]}".lower()
    if re.search(r'\b(payment|payments|lending|loan|nbfc|fintech|lending|insurance|'
                 r'insurtech|wealth|payments?tech|credit)\b', blob):
        return 0, 'fintech'
    if re.search(r'\b(bank|banking)\b', blob):
        return 1, 'bank'
    return 7, 'other'


def _priority(company, title, description, location=''):
    if _priority_classify:
        try:
            p, label, basis = _priority_classify(company, title, description, location or '')
            return int(p), (label or PRIORITY_LABEL.get(int(p), 'other')), basis
        except Exception as e:
            _LAST_PRIORITY_ERR = repr(e)
    p, label = _legacy_priority(company, title, description)
    return p, label, 'legacy fallback'


_LAST_PRIORITY_ERR = None


# --- AI-native carve-out (user-approved 2026-11-11) ----------------------
# "Apply to AI-GTM roles": an AI-native employer (LLM / agents / AI product)
# hiring a senior growth / GTM / marketing leader IS eligible even though the
# company is not in the P0-P7 fintech/bank/NBFC/D2C rosters. Without this the
# role scores as unknown P7 and gets capped to leftover-time-only.
AI_NATIVE_RE = re.compile(
    r'\b(ai[- ]native|ai[- ]first|ai[- ]company|ai[- ]startup|agentic|'
    r'generative ai|genai|large language model|\bllms?\b|foundation model)\b',
    re.I)
# company names ending in AI, minus place words that also end in "ai"
_AI_NAME_BLOCK = {'dubai', 'mumbai', 'delhi', 'chennai', 'kolkata', 'bangkok',
                   'hanoi', 'kyiv', 'bali', 'chai', 'bhai', 'detroit', 'sydney'}
AI_NAME_RE = re.compile(r'(?i)([a-z]{3,})ai$')
# secondary marker required for the company-name ("...AI") path, so that
# recruiters/brands that merely bolt "ai" onto their name (TalentPartner.ai)
# are not treated as AI-native employers.
_AI_MARKER_RE = re.compile(
    r'\b(agentic|genai|generative ai|large language model|\bllms?\b|'
    r'ai[- ]native|ai[- ]first|foundation model|machine learning models?)\b', re.I)


def _ai_native(company, description):
    """True when the employer is an AI-native company (strict, no false positives)."""
    head = f'{company or ""} {description[:700]}'
    if AI_NATIVE_RE.search(head):
        return True
    c = re.sub(r'[^a-z]', '', str(company or '').lower())
    m = AI_NAME_RE.match(c)
    if (m and m.group(1) not in _AI_NAME_BLOCK and len(m.group(1)) >= 4
            and _AI_MARKER_RE.search(str(description or '')[:1500])):
        return True
    return False


# --- company-NAME-ONLY hard blocks (2026-11-11) ----------------------------
# The employer-class block searches company + first 400 chars of the JD, so
# names like "Hiring Mavericks", "EH Jobs" or "Vesta Hotels & Resorts" slipped
# through and were then lifted by the AI-native carve-out. These patterns are
# matched against the COMPANY NAME ONLY so a JD that merely mentions
# "recruitment" or "institute" cannot block a legitimate employer.
COMPANY_NAME_BLOCK = [
    (r'\bhiring\b|\bhunter\b|\brecruit(er|ment|ing)\b|\bstaff(ing|s)\b|'
     r'\bmanpower\b|\btalent\s+(partners?|search|solutions?)\b|'
     r'\bpeople\s+(partners?|solutions?)\b|\bjob\s?street\b',
     'employer_class:recruitment_agency'),
    (r'\bedutech\b|\beducation\b|\bacadem(y|ies)\b|\buniversity\b|'
     r'\bcollege\b|\bschool\s+of\b|\bscholarship\b',
     'employer_class:education'),
    (r'\bhotels?\b|\bresorts?\b|\bhospitality\b|\brestaurants?\b|'
     r'\btravel\s+agency\b|\bcaf[eé]s?\b',
     'employer_class:hospitality'),
    (r'\brealty\b|\breal\s+estate\b|\bproperties\b|\bproptech\b|\bremax\b',
     'employer_class:real_estate'),
    (r'\bfrost\s*&\s*sullivan\b|\bgartner\b|\bforrester\b|\btechnopak\b|'
     r'\bmarket\s+research\b|\bresearch\s+and\s+advisory\b',
     'employer_class:research_consultancy'),
    (r'\bfashion\b|\bapparel\b|\btextiles?\b|\bgarments?\b|\boutfitters?\b',
     'employer_class:fashion'),
    # 2026-11-17: employers confirmed from their LinkedIn company pages to be
    # intermediaries/education-training firms rather than the actual hiring
    # company ('Aviate' -> aviate-education; 'SkillLabs' -> staffing).
    (r'\bskilllabs?\b|\baviate\s?education\b',
     'employer_class:recruitment_agency'),
]
# A posting whose JD opens a SENTENCE with a client disclosure ("The client
# is ...", "For our client, ...", "Assignment for a ...") is posted by a
# recruiter/consultancy acting for someone else — the poster is NOT the
# employer. Nov 17 2026: this caught Aviate (voice-AI client) and SkillLabs
# (SCF product role), both of which the dual-model judge had approved.
CLIENT_INTERMEDIARY_RE = re.compile(
    r'(?:^|[.!?]\s+|\n)\s*'
    r'(?:the\s+client\s+is|our\s+client\s+is|our\s+client\s*,|for\s+our\s+client\b|'
    r'assignment\s+for\s+(?:a|an|our)\b|on\s+behalf\s+of\s+(?:our|a)\s+client\b|'
    r'we\s+are\s+(?:hiring|looking)\s+for\s+[^.]{0,40}\s+for\s+our\s+client\b)',
    re.I)
_COMPANY_NAME_RE = [(re.compile(p, re.I), r) for p, r in COMPANY_NAME_BLOCK]


def company_name_block(company):
    """Return (is_bad_match, reason) matched on the COMPANY NAME only."""
    name = str(company or '')
    if not name.strip():
        return False, None
    for rx, reason in _COMPANY_NAME_RE:
        if rx.search(name):
            return True, reason
    return False, None


def score_job(company, title, location, description='', allow_p7=False):
    """Rebuilt relevance score.

    Returns dict:
      verdict : GREEN | YELLOW | RED
      score   : 0..100
      priority: 0..7 (P0 best)
      tier    : priority label
      basis   : short human-readable reason
      reasons : list of contributing factors
      hard_block : None or a blocking reason
    """
    company = company or ''
    title = clean_title(title, company)
    description = str(description or '')
    reasons = []
    hard = None

    # --- 1. employer class (hard) -------------------------------------
    bad, why = employer_class(company, description)
    if bad:
        # 2026-11-15 user-approved client-disclosure exception (R61): a
        # staffing/recruitment firm posting a role on behalf of a NAMED client
        # is allowed if the client is a relevant priority employer (P0-P3
        # fintech/bank/NBFC/internal-fintech roster or explicit self-ID inside
        # the JD's first 600 chars). The exception covers ONLY the
        # staffing/recruitment family of blocks, never IT/BPO/consulting.
        if _staffing_client_exception(company, title, description):
            pass  # proceed to normal scoring with staffing block waived
        else:
            return {'verdict': 'RED', 'score': 0, 'priority': 7, 'tier': 'employer_class',
                    'basis': why, 'reasons': [why], 'hard_block': why}

    # --- 1a. company-NAME hard blocks (recruitment/education/hospitality/
    # real estate/research/fashion employers) -- name-only matching so a JD
    # that merely mentions the sector cannot block a legitimate employer.
    bad, why = company_name_block(company)
    if bad:
        return {'verdict': 'RED', 'score': 0, 'priority': 7, 'tier': 'employer_class',
                'basis': why, 'reasons': [why], 'hard_block': why}

    # --- 1a-bis. user-mandated exclusion list (never apply, any score) ---
    if USER_EXCLUDE_CO.search(company or ''):
        hard = 'user_excluded_company'
        return {'verdict': 'RED', 'score': 0, 'priority': 7, 'tier': 'excluded',
                'basis': hard, 'reasons': [hard], 'hard_block': hard}

    # --- 1b. engineering-only / hospitality titles ---------------------
    if ENGINEERING_RE.search(title):
        hard = 'engineering_only_title'
        return {'verdict': 'RED', 'score': 0, 'priority': 7, 'tier': 'engineering',
                'basis': hard, 'reasons': [hard], 'hard_block': hard}
    if HOSPITALITY_TITLE_RE.search(title):
        hard = 'hospitality_title'
        return {'verdict': 'RED', 'score': 0, 'priority': 7, 'tier': 'hospitality',
                'basis': hard, 'reasons': [hard], 'hard_block': hard}
    if PRODUCT_OWNER_RE.search(title) and not re.search(r'product\s+marketing',
                                                        title, re.I):
        hard = 'product_owner_title'
        return {'verdict': 'RED', 'score': 0, 'priority': 7, 'tier': 'product',
                'basis': hard, 'reasons': [hard], 'hard_block': hard}
    if CLIENT_INTERMEDIARY_RE.search(str(description or '')[:1200]):
        hard = 'intermediary_posting'
        return {'verdict': 'RED', 'score': 0, 'priority': 7, 'tier': 'employer_class',
                'basis': hard, 'reasons': [hard], 'hard_block': hard}

    # --- 2. equity / founder-only ------------------------------------
    if EQUITY_RE.search(title):
        hard = 'equity_only_or_founder_role'
        return {'verdict': 'RED', 'score': 0, 'priority': 7, 'tier': 'equity',
                'basis': hard, 'reasons': [hard], 'hard_block': hard}

    # --- 3. location --------------------------------------------------
    lier, lbonus, lnote = location_tier(location)
    if lier in ('us', 'tier2'):
        return {'verdict': 'RED', 'score': 0, 'priority': 7, 'tier': lier,
                'basis': lnote, 'reasons': [lnote], 'hard_block': lnote}
    reasons.append(f'location:{lier}(+{lbonus})')

    # --- 4. function family -------------------------------------------
    if SALES_RE.search(title) and not re.search(r'\b(revenue|commercial)\b', title, re.I):
        hard = 'sales_role'
        return {'verdict': 'RED', 'score': 0, 'priority': 7, 'tier': 'sales',
                'basis': hard, 'reasons': [hard], 'hard_block': hard}
    # 2026-11-11: "commercial" in the title was letting explicit sales roles
    # through - "Head of Commercial/ Sales, Paytm Europe" scored GREEN 78 at a
    # P0 fintech. An explicit 'sales' token now blocks unless the title also
    # carries revenue / partnerships / GTM wording ("VP Sales & Revenue",
    # "Chief Commercial Officer" stay eligible).
    if (re.search(r'\bsales\b', title, re.I)
            and not re.search(r'\b(revenue|partnerships?|gtm|go[- ]to[- ]market)\b',
                              title, re.I)):
        hard = 'sales_role'
        return {'verdict': 'RED', 'score': 0, 'priority': 7, 'tier': 'sales',
                'basis': hard, 'reasons': [hard], 'hard_block': hard}
    if re.search(r'\bbusiness\s+opportunity\b', title, re.I):
        hard = 'sales_role'
        return {'verdict': 'RED', 'score': 0, 'priority': 7, 'tier': 'sales',
                'basis': hard, 'reasons': [hard], 'hard_block': hard}
    if not FUNCTION_KW.search(title):
        hard = 'no_target_function_in_title'
        return {'verdict': 'RED', 'score': 0, 'priority': 7, 'tier': 'function',
                'basis': hard, 'reasons': [hard], 'hard_block': hard}

    # --- 5. seniority --------------------------------------------------
    senior = bool(SENIOR_RE.search(title))
    if not senior:
        if JUNIOR_RE.search(title) and not MANAGER_OK.search(title):
            hard = 'below_senior_ladder'
            return {'verdict': 'RED', 'score': 0, 'priority': 7, 'tier': 'seniority',
                    'basis': hard, 'reasons': [hard], 'hard_block': hard}
        hard = 'not_on_senior_ladder'
        return {'verdict': 'RED', 'score': 0, 'priority': 7, 'tier': 'seniority',
                'basis': hard, 'reasons': [hard], 'hard_block': hard}
    if JUNIOR_RE.search(title) and not MANAGER_OK.search(title) and \
            not re.search(r'\b(assistant|associate)\s+(vice\s+president|director)\b',
                          title, re.I):
        # "Senior Manager", "Assistant Manager" etc. -> manager band, blocked
        hard = 'manager_band_title'
        return {'verdict': 'RED', 'score': 0, 'priority': 7, 'tier': 'seniority',
                'basis': hard, 'reasons': [hard], 'hard_block': hard}

    # --- 6. sector priority -------------------------------------------
    p, plabel, pbasis = _priority(company, title, description, location or '')
    p = max(0, min(7, p))
    pbonus = PRIORITY_BONUS[p]
    reasons.append(f'priority:P{p}({plabel})(+{pbonus})')
    # AI-native employer carve-out: unknown-to-roster AI companies get the
    # P3/P4 weight of the user's AI-GTM track instead of leftover-time P7.
    if p == 7 and _ai_native(company, description):
        p = 4
        plabel = 'P4-AI'
        pbonus = 26
        reasons.append('ai_native_carveout(P4-AI,+26)')

    # --- 7. function density + leadership in JD ------------------------
    fscore = 0
    hits = set(m.group(0).lower() for m in FUNCTION_KW.finditer(
        f'{title} {description[:2500]}'))
    fscore += min(22, 6 * len(hits))
    if LEAD_RE.search(description[:3000]):
        fscore += 14
        reasons.append('leadership_scope(+14)')
    if re.search(r'\b(\d+)\s*\+?\s*years?', description[:3000], re.I):
        fscore += 4

    score = fscore + pbonus + lbonus
    score = max(0, min(100, score))
    reasons.append(f'function(+{fscore})')

    # --- 8. P7 cap: "everything else" is leftover-time-only -------------
    if p == 7 and not allow_p7:
        score = min(score, 62)
        reasons.append('P7_capped_62_leftover_time_only')
    verdict = 'GREEN' if score >= 70 else ('YELLOW' if score >= 55 else 'RED')

    basis = (f"{plabel} + {lier} + fscore{fscore} -> {score}"
             + (' [P7 capped]' if p == 7 and not allow_p7 else ''))
    return {'verdict': verdict, 'score': score, 'priority': p, 'tier': plabel,
            'basis': basis, 'reasons': reasons, 'hard_block': None}


if __name__ == '__main__':
    tests = [
        ('Atomic Capital', 'Chief Growth Officer', 'Bengaluru, Karnataka', '', True),
        ('Innomax IT Solutions', 'Head of Digital Marketing', 'Hyderabad', '', False),
        ('First Abu Dhabi Bank FAB', 'VP, Head of Marketing & Communication', 'Dubai', '', True),
        ('Some D2C Brand', 'Head of Growth', 'Mumbai', '', True),
        ('Staffing Co', 'Head of Marketing', 'Bengaluru', '', False),
        ('Consultancy LLP', 'Director of Marketing', 'Bengaluru', '', False),
        ('Property Co', 'Head of Marketing', 'Dubai', '', False),
        ('Acme SaaS', 'Senior Manager Marketing', 'Pune', '', False),
    ]
    for co, ti, loc, desc, want_green in tests:
        r = score_job(co, ti, loc, desc)
        mark = 'OK ' if (r['verdict'] == 'GREEN') == want_green else '!! '
        print(f"{mark}{co[:26]:28} {ti[:34]:36} -> {r['verdict']:6} {r['score']:3} "
              f"P{r['priority']} {r['basis'][:44]}")


# --------------------------------------------------------------------------
# 8. COMBINE the deterministic engine with the dual-model LLM decision
# --------------------------------------------------------------------------
# The company roster is authoritative WHEN IT KNOWS the company.  When the
# roster cannot place an employer (it returns P7 = "unknown"), the two decision
# models (crouton-alpha + glm-5.3) are trusted for the sector call, because
# they read the actual JD.  Hard blocks are never bypassed.
#
#   effective_priority = det priority      if det tier is known (P0..P6)
#                      = min(llm_p1, llm_p2) if det == P7 and both models
#                        agree on a P0..P6 sector
#                      = P7 otherwise
def combine(det, llm, threshold=70):
    """det: output of score_job(); llm: output of llm_decide.decide()."""
    if det.get('verdict') == 'RED' and det.get('hard_block'):
        return {**det, 'verdict': 'RED', 'effective_priority': det.get('priority'),
                'llm_score': (llm or {}).get('score', 0),
                'reason': 'hard_block:' + str(det.get('hard_block'))}

    p_det = int(det.get('priority', 7))
    eff = p_det
    src = 'roster'
    if p_det == 7:
        cand = []
        for key in ('primary', 'verifier'):
            v = ((llm or {}).get(key) or {})
            pv = v.get('priority')
            if isinstance(pv, str) and pv.upper().startswith('P'):
                try:
                    cand.append(int(pv.upper()[1:]))
                except Exception:
                    pass
            elif isinstance(pv, int):
                cand.append(pv)
        if len(cand) == 2 and cand[0] == cand[1] and 0 <= cand[0] <= 6:
            eff = cand[0]
            src = 'llm_unanimous'
        elif len(cand) == 2 and min(cand) <= 6 and max(cand) - min(cand) <= 1:
            eff = min(cand)
            src = 'llm_consensus'

    llm_ok = bool((llm or {}).get('ok'))
    llm_score = int((llm or {}).get('score') or 0)

    # rebuild the score with the effective sector priority
    pbonus = PRIORITY_BONUS.get(eff, 8)
    base = int(det.get('score') or 0)
    # det score already contains PRIORITY_BONUS[p_det]; swap it out
    det_bonus = PRIORITY_BONUS.get(p_det, 8)
    rest = max(0, base - det_bonus)
    score = min(100, rest + pbonus)

    if eff == 7 and not llm_ok:
        score = min(score, 62)
    elif eff == 7 and llm_ok:
        score = max(score, min(100, llm_score))
    elif llm_ok:
        score = max(score, llm_score)

    verdict = 'GREEN' if (score >= threshold and llm_ok) else ('YELLOW' if score >= 58 else 'RED')
    basis = (f"eff_P{eff}({src}) base{base}->{score} llm{llm_score}"
             + (' llm_ok' if llm_ok else ' llm_reject'))
    return {
        'verdict': verdict, 'score': score, 'priority': eff,
        'tier': PRIORITY_LABEL.get(eff, 'other'), 'effective_priority': eff,
        'priority_source': src, 'llm_score': llm_score, 'llm_ok': llm_ok,
        'basis': basis, 'reasons': det.get('reasons', []), 'hard_block': None,
    }

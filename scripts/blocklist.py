# Do Not Approach — enforced in ALL outreach loops
BLOCKED = {
    "anirban dutt": {"name":"Anirban Dutta","company":"IDFC First Bank","linkedin":"linkedin.com/in/anirban-dutta-digitalfirst","reason":"User-mandated"},
    "saurabh tirp": {"name":"Saurabh Tirpude","company":"IDFC First Bank","linkedin":"linkedin.com/in/saurabhtirpude","reason":"User-mandated"},
    "salil chugh": {"name":"Salil Chugh","company":"DMI Finance","reason":"User directive: avoid Salil Chugh"},
}

def is_blocked(name_or_email):
    s = str(name_or_email).lower()
    return any(b in s for b in BLOCKED)

def skip_if_blocked(contact_dict):
    name = contact_dict.get("name","")
    if is_blocked(name):
        return True
    # Also skip by company for these two
    company = contact_dict.get("company","").lower()
    if "idfc" in company and ("dutta" in name.lower() or "tirpude" in name.lower()):
        return True
    return False

# Added per user directive 2026-10-02
BLOCKED_ADDITIONAL = {
    "mithlesh meena": {"name":"Mithlesh Meena","company":"DBS Bank","reason":"User directive: IIM Trichy + do not send"},
    "sushain tikoo": {"name":"Sushain Tikoo","company":"SBI Factors Limited","reason":"User directive: do not send"},
}

def is_blocked(name_or_email):
    s = str(name_or_email).lower()
    # Original blocks
    if "anirban dutt" in s or "saurabh tirp" in s:
        return True
    # New blocks
    if "mithlesh meena" in s:
        return True
    if "sushain tikoo" in s:
        return True
    # IIM Trichy block
    if "iim trichy" in s:
        return True
    return False


# Added per user directive 2026-10-02
BLOCKED_ADDITIONAL = {
    "pooja menon vaidya": {"name":"Pooja Menon Vaidya","company":"SBI Mutual Fund","reason":"User directive: avoid Pooja Menon Vaidya"},
}

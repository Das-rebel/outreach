#!/usr/bin/env python3
"""Per-contact customisation table for the SHORTLIST_30 outreach.

Every field is grounded in a captured JD, the contact's own LinkedIn
designation, the applied role, or the employer's public product/company line.
Nothing here is invented: no metrics, no fake company facts.

  remit    -> what THIS person runs (designation + JD scope)
  company  -> what the employer does (one factual line)
  mapping  -> how Subhajit's levers map onto that remit
  ask      -> one specific question for that remit
"""

CUSTOM = {
 # --- 1 ---------------------------------------------------------------
 ("Jimson Tellis", "Piramal Consumer Healthcare"): dict(
   remit="Head of Multimedia, Digital & Content — you own the digital and content layer of a consumer-healthcare brand that sells through modern trade and quick commerce",
   company="Piramal Consumer Healthcare sits between brand and shelf, where visibility, distribution and trade spend decide whether a category grows",
   mapping="the content-to-conversion work — modern-trade activation, e-commerce merchandising and the performance media behind it — is the part of the funnel I've owned end-to-end, at Orange Health and Groww",
   ask="how Piramal Consumer Healthcare is balancing trade investment and digital performance across Reliance, DMart and the quick-commerce platforms"),
 # --- 2 ---------------------------------------------------------------
 ("Guru Moorthy AB", "G Square Housing"): dict(
   remit="Head of Digital Marketing — you own acquisition and demand for a housing brand, where the funnel is lead-heavy and the conversion is site-visit and booking driven",
   company="G Square Housing is a housing developer, so digital demand has to convert into site visits and bookings rather than into sessions",
   mapping="performance-led acquisition with tight cost-per-lead discipline, then activation and CRM on the leads that do convert — the same build I ran at Groww",
   ask="how G Square Housing is bringing cost per site visit down while keeping lead quality high"),
 # --- 3 ---------------------------------------------------------------
 ("Vidhi Puri", "NUDGE Asia"): dict(
   remit="Founder of NUDGE Asia, running the business end-to-end while the company builds its events and experiential-marketing practice",
   company="NUDGE Asia builds brand experience through live events and experiential programmes, where footfall and recall convert into pipeline",
   mapping="scaling a marketing function — from the first hires and budgets to the measurement that justifies the next rupee — is what I've owned for 11 years",
   ask="how NUDGE Asia is scaling its experiential portfolio"),
 # --- 4 ---------------------------------------------------------------
 ("Vipen Jain", "Fitspire - Health"): dict(
   remit="Founder of Fitspire, building a health & wellness brand sold direct to consumers — its ambition is to make health accessible to every Indian family",
   company="Fitspire sells health and wellness products direct-to-consumer, so growth has to come from retention and repeat, not one-off acquisition",
   mapping="building retention and repeat-purchase economics on a D2C base, plus the performance and CRM layer underneath it, is the work I ran at Orange Health and ABFL",
   ask="how Fitspire is building repeat purchase and subscription economics on its D2C base"),
 # --- 5 ---------------------------------------------------------------
 ("Deepak Suresh", "Amadora Artisan Ice Cream"): dict(
   remit="Founder and Chief Ice Cream Maker — and this CMO role reports directly to you, so you are hiring the first marketing leader for Amadora",
   company="Amadora is a premium artisanal ice-cream brand with stores across Chennai, Bangalore, Hyderabad and Cochin, more planned for 2027, and now moving into organised retail",
   mapping="launch playbooks for new cities and franchise openings, delivery-app growth on Swiggy and Zomato, and a first in-house marketing team — I've built exactly that kind of function from scratch",
   ask="how Amadora is planning the retail and franchise rollout for 2027"),
 # --- 6 ---------------------------------------------------------------
 ("Anuj Gupta", "Titan Email"): dict(
   remit="Sr. Director of Partnerships at Titan — you run partner-led distribution while the company hires a Director of Marketing to own positioning, GTM and acquisition across Titan and the direct brand Neo",
   company="Titan Email is the email and web-presence layer for small businesses, with Neo as the direct-to-consumer suite and Automattic as a backer",
   mapping="demand-gen efficiency on one side and full-funnel brand work on the other — I've run both at Groww and Axis, and partner-led distribution is the same matching problem in a different costume",
   ask="how Titan Email is building partner-led acquisition for Neo"),
 # --- 7 ---------------------------------------------------------------
 ("Nivesh Jain", "Westwall Wealth Management Co."): dict(
   remit="CTO and Co-founder at Westwall — you built the technology, and you are hiring the Head of Marketing to build the distribution side",
   company="Westwall is a wealth-management business, where growth runs on advisor and channel distribution rather than on paid acquisition",
   mapping="partner and channel-led distribution with disciplined economics is what I ran at Niro through MyGate, Snapdeal and NoBroker partnerships",
   ask="how Westwall is scaling its advisor and channel distribution"),
 # --- 8 ---------------------------------------------------------------
 ("Suresh Raman", "Lifestyle"): dict(
   remit="Business Head – Brands at Lifestyle Max — you run the brand P&L, including the e-commerce and D2C channel that the applied role sits in",
   company="Lifestyle is one of India's largest fashion retail chains, where e-commerce growth economics — CAC, retention and repeat purchase — decide the store network's profitability",
   mapping="the retention and performance-marketing levers I've run at Orange Health and Groww transfer directly to that playbook, and CRM and lifecycle are where I have the deepest bench",
   ask="how Lifestyle is running retention and CRM across its e-commerce and store channels"),
 # --- 9 ---------------------------------------------------------------
 ("Maurits Favier", "Dubai Chambers"): dict(
   remit="Chief Representative for the Netherlands at Dubai Chambers — the applied Director role sits in the same organisation, and it is restricted to UAE nationals",
   company="Dubai Chambers runs the enterprise brand, three-chamber mandate and international market activation for Dubai's position as a global business hub",
   mapping="brand and campaign work at institutional scale — governance, agency management, bilingual content and measurement — is a different discipline from the operator growth I have owned for 11 years",
   ask="how Dubai Chambers is measuring campaign and brand performance across markets"),
 # --- 10 --------------------------------------------------------------
 ("Vineet Sukumar", "Vivriti Asset Management"): dict(
   remit="Founder and Managing Director of Vivriti Group — this Regional Head – Channel Sales (East) role reports into the business you built",
   company="Vivriti is a fund-raising and asset-management business, so growth runs on distributor, broker and channel relationships in each region",
   mapping="channel-led growth with disciplined unit economics and partner enablement is what I ran at Niro through MyGate, Snapdeal and NoBroker",
   ask="how Vivriti is building its eastern channel and distributor network"),
 # --- 11 --------------------------------------------------------------
 ("Anuj Jain", "Green Portfolio"): dict(
   remit="Co-founder of Green Portfolio — the Channel Sales Head – PMS/AIF Distribution role you hired sits in the distribution engine of your business",
   company="Green Portfolio distributes portfolio management and alternative investment products, so growth is relationship-led: advisors, distributors and their clients",
   mapping="building a distribution engine through partnerships, with the economics and enablement that makes advisors sell, is the Niro playbook in a different market",
   ask="how Green Portfolio is scaling PMS and AIF distribution through its advisor network"),
 # --- 12 --------------------------------------------------------------
 ("Sanjay Patni", "Vivriti Asset Management"): dict(
   remit="Chief Business Officer at Vivriti — you own the commercial engine, and the Regional Head – Channel Sales (East) role reports to you",
   company="Vivriti raises and manages capital through distributors and advisors, so the commercial job is channel throughput, not consumer acquisition",
   mapping="regional P&L ownership and channel-partner enablement are what I ran at Niro and ABFL, including the partner mix that carried ₹70 Cr of monthly disbursals",
   ask="how Vivriti is structuring channel incentives across regions"),
 # --- 13 --------------------------------------------------------------
 ("Anil Kumar Puthin", "Focus Softnet"): dict(
   remit="Executive Vice President at Focus Softnet — you run the business, and this Head of Marketing role owns branding, digital, SEO/AIO/GEO and B2B demand generation for the enterprise software suite",
   company="Focus Softnet ships B2B SaaS across CRM, GST, FAM, HCM and ERP for Indian and US markets",
   mapping="B2B demand generation, ABM and marketing automation with the analytics to prove pipeline — I have run that playbook across two banks and a lender",
   ask="how Focus Softnet is approaching ABM and AI-search visibility for its enterprise suite"),
 # --- 14 --------------------------------------------------------------
 ("Priya Dubey", "UnitedHealth Group / Optum"): dict(
   remit="Associate Director, AI Marketing Transformation Lead — you are the bridge between Optum's care and pharmacy businesses and AI-enabled go-to-market",
   company="Optum is UnitedHealth Group's health-services and technology arm, connecting care, pharmacy benefits and data at global scale",
   mapping="I build AI tooling as a hands-on project, not a slide — an open-source AI router and an agent platform with real adoption — and I pair that with the growth and P&L ownership the mandate needs",
   ask="how Optum is putting AI into its go-to-market for care and pharmacy services"),
 # --- 15 --------------------------------------------------------------
 ("Shama Mahuwala", "Fintoo"): dict(
   remit="Vice President, Private Wealth at Fintoo — you run private-wealth distribution for a SEBI-registered investment adviser and fee-based financial planner",
   company="Fintoo is a SEBI-registered investment adviser and fee-based financial-planning firm, where planning comes before execution and growth is earned through trust and advice",
   mapping="I have built regulated, advice-led distribution before — at Groww and Axis the growth came from matching each customer to the right product, not from discounting, which is the same discipline private wealth runs on",
   ask="how Fintoo is scaling its private-wealth and advisory relationships"),
 # --- 16 --------------------------------------------------------------
 ("Aloysius Vijay", "Indifi Technologies"): dict(
   remit="Director, Talent Acquisition India and APAC — you own hiring for a digital-lending fintech, including the growth and CRM roles the applied posting is for",
   company="Indifi is a digital lending fintech, where growth and CRM sit on top of the credit book rather than on top of a marketing budget",
   mapping="I have hired and built the growth, CRM and partnerships functions inside scaled lenders — Groww and Axis — so I know the profile that survives the credit cycle",
   ask="how Indifi is scaling its growth and CRM hiring as the book scales"),
 # --- 17 --------------------------------------------------------------
 ("Laxmi Gupta", "Fintoo"): dict(
   remit="Chief Manager at Nuvama Wealth within the Fintoo group — you run day-to-day advisory and client growth for private wealth",
   company="Fintoo operates as a SEBI-registered investment adviser with a fee-based financial-planning model across investments, advisory and tax",
   mapping="advisory-led revenue with a clean service model is the same shape as what I ran in regulated lending — trust-led, fee-driven, no dark patterns",
   ask="how Nuvama Wealth is growing its advisor-led client base"),
 # --- 18 --------------------------------------------------------------
 ("Nikhil Parmar", "Fitspire - Health | Wellness"): dict(
   remit="Founder at Impactful Pitch, working alongside Fitspire on the applied Digital Head – D2C/FMCG role",
   company="Fitspire sells health and wellness products direct to consumers, so its digital growth has to compound through retention and repeat purchase",
   mapping="D2C growth with disciplined CAC and a retention engine underneath is exactly what I ran at Orange Health, and at ABFL for the credit-led side of D2C",
   ask="how Fitspire is approaching paid acquisition and retention for its wellness range"),
 # --- 19 --------------------------------------------------------------
 ("Amit Bisht", "Green Portfolio"): dict(
   remit="Assistant Vice President at Green Portfolio — you run part of the channel business for PMS and AIF distribution",
   company="Green Portfolio sells portfolio-management and alternative-investment products through advisors and distributors",
   mapping="partner enablement, advisor education and disciplined funnel economics are what I ran at Niro through MyGate, Snapdeal and NoBroker",
   ask="how Green Portfolio is enabling its advisor and distributor network"),
 # --- 20 --------------------------------------------------------------
 ("Veena Sajee", "Indifi Technologies"): dict(
   remit="Sales & Commercial Director at Indifi — you own the commercial engine behind the applied Growth Marketing & CRM role",
   company="Indifi is a digital lending fintech where growth and CRM are judged on the credit book they produce, not on sessions",
   mapping="building revenue engines with clear unit economics and disciplined payback — Groww's credit book grew 60% while cost per funded loan fell 28% — is that exact work",
   ask="how Indifi is aligning sales, CRM and growth around credit-book economics"),
 # --- 21 --------------------------------------------------------------
 ("Yash Jain", "Fintoo"): dict(
   remit="AVP, Global Private Wealth at Fintoo — you run private-wealth distribution and client advisory across markets",
   company="Fintoo is a SEBI-registered investment adviser offering financial planning, investment advisory, global investing and tax advisory",
   mapping="advice-led growth across products is what I did in regulated lending — matching the right customer to the right product, and earning the fee honestly",
   ask="how Fintoo is scaling global private wealth beyond its core market"),
 # --- 22 --------------------------------------------------------------
 ("Kshitij Patil", "Vivriti Asset Management"): dict(
   remit="Head – Mumbai at Vivriti Asset Management — you run the region's commercial engine under the applied Regional Head – Channel Sales (East) mandate",
   company="Vivriti raises and manages capital through distributors, advisors and institutional channels across regions",
   mapping="regional P&L ownership and channel-partner throughput are what I ran at Niro and ABFL, where partner mix carried ₹70 Cr of monthly disbursals",
   ask="how Vivriti is scaling channel throughput in the western region"),
 # --- 23 --------------------------------------------------------------
 ("Vinayak Pujari", "Vivriti Asset Management"): dict(
   remit="Senior Director, Head of Investor Operations & Customer Experience — you own the service and experience layer that makes distributors keep selling",
   company="Vivriti is an asset-management and fund-raising firm where retention of distributors and investors is as decisive as acquisition",
   mapping="retention and service design at scale — I lifted repeat engagement 60% and doubled retention at Orange Health — is the same discipline applied to investors",
   ask="how Vivriti is measuring investor and distributor experience"),
 # --- 24 --------------------------------------------------------------
 ("Keval Patel", "Indifi Technologies"): dict(
   remit="Director, Corporate Strategy — you shape where Indifi's growth and CRM functions are pointed, and the applied role is a growth-marketing and CRM leadership seat",
   company="Indifi is a digital lending fintech, so corporate strategy and growth sit against a real credit book and unit economics",
   mapping="strategy that lands in a number — Groww's credit revenue up 60% with cost per funded loan down 28% — has been my job for 11 years, not a deck exercise",
   ask="how Indifi's corporate strategy is shaping the growth and CRM organisation"),
 # --- 25 --------------------------------------------------------------
 ("Vaishali Gandhi", "Vivriti Asset Management"): dict(
   remit="Head – Institutional Sales & Family Office at Vivriti — you run institutional and HNI distribution under the applied regional channel-sales mandate",
   company="Vivriti serves institutional and family-office capital alongside its retail channel, so mandate quality and allocation flow drive growth",
   mapping="high-touch distribution with disciplined economics — the Groww and ABFL playbook of matching product to segment and paying for performance, not reach",
   ask="how Vivriti is expanding institutional and family-office distribution"),
 # --- 26 --------------------------------------------------------------
 ("Anurag Janardhanan", "Vivriti Asset Management"): dict(
   remit="Zonal Head Sales (West & East) — you run two zones of fund raising and investor relationships for Vivriti",
   company="Vivriti builds and manages investment products distributed through advisors and institutions, so zonal growth is entirely partner-led",
   mapping="zonal channel ownership with a partner mix that actually performs — Niro's ₹70 Cr monthly disbursals came from three partnerships run end-to-end",
   ask="how Vivriti is building its zonal distributor mix across east and west"),
 # --- 27 --------------------------------------------------------------
 ("Prasanna M", "Vivriti Asset Management"): dict(
   remit="Head – Institutional Sales, AIF at Vivriti Capital — you run institutional distribution for the alternative-investment fund",
   company="Vivriti Capital's AIF business raises long-horizon capital from institutions and family offices, where conviction and allocation cycle drive growth",
   mapping="institutional and HNI distribution is advisory work — I ran exactly that shape of motion at Niro and ABFL, where segment-specific products carried ₹70 Cr a month",
   ask="how Vivriti Capital is building institutional appetite for its AIF products"),
 # --- 28 --------------------------------------------------------------
 ("Dipen Ruparelia, CA, CFA", "Vivriti Asset Management"): dict(
   remit="Chief Business & Product Officer at Vivriti — you own the commercial and product agenda, and the applied regional channel-sales role reports into it",
   company="Vivriti is a vertically integrated asset-management and fund-raising business, so product and channel have to be designed together",
   mapping="owning both P&L and product — Groww's credit book grew 60% on a lending product I shaped, while cost per funded loan fell 28% — is the same commercial-plus-product coupling",
   ask="how Vivriti designs its products and channel together"),
 # --- 29 --------------------------------------------------------------
 ("Harsh Mudgal", "Green Portfolio"): dict(
   remit="Assistant Vice President — Business Development at Green Portfolio — you run business development across the PMS and AIF distribution channels",
   company="Green Portfolio distributes portfolio-management and alternative-investment products to advisors and investors",
   mapping="business development with channel economics and clean payback — Groww's 28% cost-per-funded-loan reduction came from exactly that discipline",
   ask="how Green Portfolio is growing business development across its distribution network"),
 # --- 30 --------------------------------------------------------------
 ("Chandrasekaran S", "Lifestyle"): dict(
   remit="President, Business Development & Projects at Lifestyle — you run business development and project-level growth for the group, and the applied e-commerce marketing role sits under your umbrella",
   company="Lifestyle (Landmark Group) is one of India's largest fashion retail groups, where the group's biggest lever is taking brands and categories online",
   mapping="project-led growth — owning a business-development P&L, the numbers and the delivery — is what I've done at Groww and Axis; the e-commerce and CRM piece is where I add depth",
   ask="how Lifestyle is driving business development through its digital and project-led growth"),
}

def get(name, company):
    return CUSTOM.get((name, company))

CUSTOM.update({
 ("Aman Bhargava", "Indifi Technologies"): dict(
   remit="Marketing Director — you own demand for a digital lending fintech where growth is judged on the credit book it produces, not on sessions",
   company="Indifi is a digital lending fintech; the marketing and CRM functions sit directly on top of the credit book, so every rupee of spend is judged on funded loans, not on traffic",
   mapping="building a demand engine that is measured on funded loans rather than on clicks is exactly what I ran at Groww — credit revenue up 60% while cost per funded loan fell 28% — and I paired it with retention on the book at Axis",
   ask="how Indifi is aligning marketing and CRM spend with credit-book economics"),
 ("Vikrant Dale", "Bigul"): dict(
   remit="Chief Growth Officer — you own the growth agenda for a digital-first NBFC, including the revenue engine across products and channels",
   company="Bigul is a digital-first NBFC competing on underwriting and distribution speed, so growth has to come from conversion economics rather than from brand spend alone",
   mapping="I have owned growth P&Ls in exactly this business — Groww's credit revenue 60% up with cost per funded loan down 28%, and ₹70 Cr of monthly disbursals at Niro built through partnerships rather than discounting",
   ask="how Bigul is scaling its revenue engine across products and channels"),
 ("Siddharth Sanghvi", "Bigul"): dict(
   remit="Digital Marketing Manager — you run the performance and lifecycle side of Bigul's demand engine",
   company="Bigul is a digital-first NBFC, so digital marketing has to produce funded loans rather than form fills",
   mapping="the same build I ran at Groww — turning paid demand into funded loans with cost per funded loan down 28% while credit revenue grew 60% — plus the lifecycle and CRM layer on top",
   ask="how Bigul is running digital performance and lifecycle against funded-loan economics"),
 ("Mahwish Jamal", "Talents Tide"): dict(
   remit="Executive at Talents Tide — you run the firm that places senior content and product-marketing leaders",
   company="Talents Tide is a specialist search firm for content and product marketing talent, so its growth is about the mandates it wins and the leaders it places",
   mapping="I am the operator on the other side of these mandates — 11 years owning growth and marketing P&Ls in fintech, banking and consumer — so I can speak to the profile you place for, and to what actually moves a hiring manager",
   ask="how Talents Tide is positioning its content and product-marketing practice against the wider market"),
})

CUSTOM.update({
 ("Jaskaran Kapany", "MobiKwik"): dict(
   remit="Chief Marketing Officer — you own marketing and demand across a UPI-first fintech with a large merchant base",
   company="MobiKwik is a UPI-first fintech that monetises a consumer network and a merchant base, so marketing has to grow transactions and merchant relationships together rather than buy traffic",
   mapping="the same build I ran at Groww — credit revenue up 60% with cost per funded loan down 28% — plus merchant-led distribution at Niro, where ₹70 Cr of monthly disbursals came through MyGate, Snapdeal and NoBroker partnerships rather than discounting",
   ask="how MobiKwik is growing UPI and merchant marketing in a market where every brand buys the same attention"),
 ("Pranjal Thakker", "LiquiLoans"): dict(
   remit="Head of Consumer Loans and Automobile Finance — you own two of LiquiLoans' core lending growth engines",
   company="LiquiLoans is a digital lending NBFC where growth has to come from loan-book quality and channel partnerships rather than top-of-funnel volume",
   mapping="I have run exactly this engine — credit revenue up 60% at Groww with cost per funded loan down 28%, and ₹70 Cr of monthly disbursals at Niro built through MyGate, Snapdeal and NoBroker partnerships, which is partnerships over discounting",
   ask="how LiquiLoans is scaling consumer and auto lending while holding credit quality"),
 ("Sunil Param", "Pine Labs"): dict(
   remit="Director of Communications — you own how Pine Labs is positioned with merchants, banks and customers",
   company="Pine Labs runs a large merchant network and gateway stack, so communications have to make a technical rails story land with merchants, banks and enterprise buyers",
   mapping="I have run growth and marketing in exactly this stack — Groww's credit revenue 60% up with cost per funded loan down 28%, and ₹70 Cr monthly disbursals at Niro built on merchant and partner channels rather than discounting",
   ask="how Pine Labs is communicating its merchant and enterprise story"),
 ("Hemant Bakshi", "Pine Labs"): dict(
   remit="Head of Alliances — you own the partnerships that make Pine Labs' network defensible",
   company="Pine Labs is a payments gateway and merchant-network business, so alliances with banks, fintechs and enterprises are the growth engine behind the network effect",
   mapping="partnership-led growth is the part of my background that maps most directly — ₹70 Cr of monthly disbursals at Niro through MyGate, Snapdeal and NoBroker partnerships, and credit revenue up 60% at Groww with cost per funded loan down 28%",
   ask="how Pine Labs is building its alliance and partnership engine"),
 ("Jay Munshaw", "Pepperfry"): dict(
   remit="Head of Business Development and Growth — you own Pepperfry's growth engine across channels",
   company="Pepperfry is India's largest furniture marketplace, where growth runs on marketplace supply, city-level economics and repeat purchase rather than pure traffic buying",
   mapping="I have built demand-side growth from the ground up — Groww's credit revenue 60% up with cost per funded loan down 28%, and at Niro ₹70 Cr of monthly disbursals built through MyGate, Snapdeal and NoBroker partnerships",
   ask="how Pepperfry is balancing marketplace growth with city-level profitability"),
 ("Kulbhushan Atkar", "Pepperfry"): dict(
   remit="Chief Revenue Officer — you own Pepperfry's revenue line across marketplace and city P&Ls",
   company="Pepperfry is a furniture marketplace where revenue has to be built on marketplace supply, city economics and repeat purchase rather than discounting",
   mapping="the same revenue discipline I ran at Groww — credit revenue 60% up with cost per funded loan down 28% — and at Niro, where ₹70 Cr of monthly disbursals came from partner channels instead of price cuts",
   ask="how Pepperfry is structuring its revenue engine across marketplace and city P&Ls"),
})

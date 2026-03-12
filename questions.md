# Benchmark Questions: Generic LLM vs Specialized Compliance AI

## Purpose
10+ complex regulatory questions that target customers actually have.
Test against Claude, GPT-4, and Gemini directly.
Score for: accuracy, specificity to Indian law, citation quality.

## Moat Categories
- (a) Recent circulars (not in training data)
- (b) Cross-regulator conflicts
- (c) Entity-specific applicability
- (d) Obligation graph / deadline questions
- (e) State-specific or sector-specific rules

---

## Questions

### 1. SEBI-RBI Conflict in NBFC Takeovers (Cross-regulator)
**Source:** [IndiaCorpLaw - SEBI-RBI Conflict](https://indiacorplaw.in/2025/03/15/the-sebi-rbi-conflict-regulatory-gridlock-in-nbfc-takeovers/)

> My NBFC is being acquired by a listed entity. SEBI's SAST regulations require an open offer, but RBI's SBR Directions require prior approval before any change of control. The target NBFC hasn't applied to RBI. What's the legal deadlock and how do we resolve it?

**Why LLMs fail:** Cross-regulator conflict requiring synthesis of SEBI SAST 2011 + RBI SBR Master Directions 2023. No single circular answers this.

---

### 2. Bank-Group NBFC Reclassification (Recent — Dec 2025)
**Source:** [Vinod Kothari - Group-level Regulation](https://vinodkothari.com/2025/12/rbi-brings-major-regulatory-restrictions-on-banks-and-group-entities/)

> Our bank-group NBFC was classified as Middle Layer under Scale-Based Regulation. After the Dec 2025 consolidation, are we automatically treated as Upper Layer now? What additional compliance requirements kick in — CET-1 capital, large exposure framework, differential provisioning?

**Why LLMs fail:** Dec 2025 circular — not in training data. Requires understanding of SBR layering system.

---

### 3. Related Party Lending Transition (Recent — April 2026 deadline)
**Source:** [Vinod Kothari - Related Party Lending](https://vinodkothari.com/2025/10/rbi-proposes-revised-norms-on-related-party-lending-and-contracting/)

> RBI's new Related Party Lending Directions take effect April 2026. We have existing related party exposures that were compliant under old norms but exceed new limits. What's the transition path? Do we need to unwind existing exposures, or is there a grandfathering provision?

**Why LLMs fail:** Not in training data. Requires reading the actual direction text for transition provisions.

---

### 4. Type 1 NBFC Registration Exemption (Recent — 2026 amendment)
**Source:** [Legal500 - RBI Amendments 2026](https://www.legal500.com/developments/thought-leadership/rbi-amendments-2026-a-new-category-for-nbfc-registration-and-exemptions/)

> We're a Type 1 NBFC with no public funds and no customer interface, AUM below ₹1000 crore. Under the 2026 amendments, are we exempt from registration? What's the process to deregister, and what residual reporting obligations remain?

**Why LLMs fail:** Brand new 2026 regulation. Requires specific knowledge of the new NBFC category.

---

### 5. IT Outsourcing Compliance Deadline (Recent — April 2026)
**Source:** [Vinod Kothari - IT Outsourcing](https://vinodkothari.com/2026/02/it-outsourcing-under-the-rbis-2025-directions-what-has-changed/)

> Our NBFC has IT outsourcing agreements signed in 2023 with a cloud provider. Under the new IT Outsourcing Directions 2025, what specific clauses need to change by the April 10, 2026 deadline? Are there mandatory audit rights and data localization requirements that weren't required before?

**Why LLMs fail:** Feb 2026 analysis. Requires comparing old vs new outsourcing framework.

---

### 6. AIF Investment Restrictions for Banks (Recent — Jan 2026 effective)
**Source:** [IndiaCorpLaw - RBI Directions on AIF](https://indiacorplaw.in/2025/09/02/the-rbis-new-directions-on-investments-by-regulated-entities-in-alternative-investment-funds/)

> Our bank invested in an AIF that has downstream exposure to one of our borrowers. Under RBI's new Investment in AIF Directions 2025 (effective Jan 2026), do we need to deduct the investment from capital? What's the look-through requirement, and does SEBI's due diligence circular from Oct 2024 create additional obligations?

**Why LLMs fail:** Dual SEBI+RBI compliance. Recent directions with specific look-through mechanics.

---

### 7. ECB Core Business Restriction (Interpretation question)
**Source:** [IndiaCorpLaw - ECB Restrictions](https://indiacorplaw.in/2025/09/29/decoding-ecb-restrictions-through-the-core-business-lens/)

> Our company wants to raise ECB funds. RBI restricts ECB end-use to "core business activities." We're a manufacturing company that also has a real estate subsidiary. Can the ECB proceeds be used for the real estate arm's working capital, or does the "core business" restriction apply entity-wise or group-wise?

**Why LLMs fail:** Ambiguous interpretation question. Requires understanding of RBI's evolving stance on "core business."

---

### 8. NBFC Securitisation Under New Master Directions (Recent — Nov 2025)
**Source:** [Probe42 - RBI Securitisation](https://resources.probe42.in/regulatory-updates/rbi-circulars/rbi-commercial-banks-securitisation-transactions/)

> We're an NBFC planning to securitise a pool of vehicle loans. Under the new Securitisation Directions 2025, what are the minimum risk retention requirements? Has the STC (Simple, Transparent, Comparable) framework changed the capital treatment for retained tranches compared to the old guidelines?

**Why LLMs fail:** Nov 2025 directions. Technical question about risk retention + capital treatment interaction.

---

### 9. Gold Loan Compliance After Aug 2025 Circular
**Source:** [EY - RBI Gold Lending Impact](https://www.ey.com/content/dam/ey-unified-site/ey-com/en-in/insights/strategy-transactions/documents/2025/ey-rbi-circular-on-gold-lending-august-2025-impact-assessment.pdf)

> Our NBFC specializes in gold loans. After RBI's August 2025 circular on gold lending, what are the new LTV monitoring requirements? We currently do end-of-day LTV checks. Is continuous monitoring now mandatory, and what happens if LTV breaches intraday but recovers by EOD?

**Why LLMs fail:** Aug 2025 circular with operational specifics. Requires reading the actual circular for monitoring frequency requirements.

---

### 10. SEBI Stock Broker Regulations 2026 Transition
**Source:** [DPNC Global - SEBI Stock Broker Regulations 2026](https://dpncglobal.com/sebi-stock-broker-regulations-2026-key-changes-new-provisions-and-implications-for-stock-brokers/)

> We're a stock broking firm operating under the old 1992 regulations. SEBI notified the new Stock Brokers Regulations 2026 in January. What are the key governance changes we need to implement? Is there a transition timeline, and what happens to our existing registration?

**Why LLMs fail:** Jan 2026 notification. Complete replacement of 1992 framework.

---

### 11. DPDP Act vs RBI Data Localization (Cross-regulator — Horizontal law vs Sectoral)
**Source:** [K&S Partners - DPDP Cross-over with Sectoral Regulators](https://ksandk.com/data-protection-and-data-privacy/dpdp-sector-regulators-navigating-rbi-sebi-irdai-trai/)

> We're an NBFC using AWS for cloud infrastructure. The DPDP Rules 2025 have an 18-month compliance window, but RBI already mandates data localization for payment data. Our customer KYC data is stored in Singapore. Under the DPDP Act, is cross-border transfer permitted if we have consent? Does RBI's data localization directive override the DPDP Act's consent-based framework, or do we need to comply with both separately?

**Why LLMs fail:** Horizontal law (DPDP) vs sectoral regulator (RBI) conflict. No clear precedent. Requires reading both frameworks and understanding the "without displacing" principle.

---

### 12. IRDAI Health Insurance Master Circular Compliance (Sector-specific)
**Source:** [Business Standard - IRDAI Flags Issues at 8 Insurers](https://www.business-standard.com/finance/insurance/irdai-flags-compliance-issues-in-health-insurance-inspections-125062601177_1.html)

> IRDAI flagged compliance issues at 8 major health insurers around the new Health Insurance Master Circular. We're a general insurer. What are the specific Customer Information Sheet (CIS) simplification requirements, Claims Review Committee composition rules, and portability data submission timelines to IIB that triggered these flags?

**Why LLMs fail:** Specific IRDAI inspection findings from June 2025. Requires knowledge of the Master Circular's operational requirements, not just high-level regulations.

---

### 13. RBI Cybersecurity Framework — NBFC Asset Threshold (Entity-specific)
**Source:** [Astra Security - RBI Cybersecurity Compliance 2026](https://www.getastra.com/blog/compliance/rbi-cybersecurity-compliance-checklist/)

> Our NBFC has assets of ₹450 crore. The RBI Master Direction on IT Framework imposes different requirements based on asset value, with a higher standard above ₹500 crore. We expect to cross ₹500 crore by Q3 FY26. What additional cybersecurity requirements (CSITE reporting, board-level cyber policy, VAPT frequency) kick in at the ₹500 crore threshold, and how much lead time do we need?

**Why LLMs fail:** Entity-specific threshold question. Requires mapping asset size to specific tiered obligations in the IT framework Master Direction.

---

### 14. NBFC NPA Recognition Glide Path (Transition — March 2026 deadline)
**Source:** [NBFC Advisory - Middle Layer Compliance](https://nbfcadvisory.in/middle-layer-nbfcs-navigating-scale-based-regulations/)

> Our Middle Layer NBFC currently recognizes NPAs at 120 days overdue (as per the March 2025 glide path). By March 2026, we must move to 90 days. We have a large agriculture loan portfolio with seasonal repayment patterns. How do we handle accounts that were standard at 120 days but will become NPA at 90 days? Is there a one-time restructuring provision, or do we need to provision for the entire reclassified pool?

**Why LLMs fail:** Transition question with sector-specific twist (agriculture seasonality). Requires knowing both the SBR glide path AND RBI's agricultural lending norms.

---

### 15. RBI Penalty — KYC Non-Compliance Pattern (Enforcement-derived)
**Source:** [Chambers & Partners - RBI 2024 Penalty Wave](https://chambers.com/articles/when-compliance-fails-stories-behind-rbis-2024-penalty-wave)

> RBI penalized 62 NBFCs between 2023-2025 for KYC violations and cancelled 35 CoRs in Jan 2026. Our NBFC was recently flagged for "allotment of multiple customer identification codes instead of unique codes." What is the typical enforcement escalation path — warning, monetary penalty, business restriction, or CoR cancellation? Can we remediate and avoid escalation, and what does the remediation timeline look like?

**Why LLMs fail:** Enforcement pattern question requiring synthesis of multiple penalty orders. No single circular answers this — it's derived from RBI's enforcement behavior.

---

### 16. SEBI LODR Late Filing Penalty Calculation (Practical compliance)
**Source:** [Lexology - SEBI Disclosure Enforcement Trends](https://www.lexology.com/library/detail.aspx?g=178130cc-1ad9-45c6-ac8b-575031bcaede)

> Our listed company filed the Q2 FY26 shareholding pattern 3 days late due to a system migration. Under SEBI's LODR Regulations, what's the penalty calculation? SEBI recently held that interest on penalties runs from the adjudication order date, not the demand notice. If we contest the penalty at SAT, does interest still accrue during the appeal?

**Why LLMs fail:** Requires knowledge of recent Supreme Court ruling on Section 28A SEBI Act interest calculation + SEBI's routine LODR enforcement pattern.

---

### 17. Bank Acquisition Finance — New RBI Exposure Caps (Recent — 2026)
**Source:** [IndiaCorpLaw - RBI Architecture for Bank-Financed Takeovers](https://indiacorplaw.in/2026/01/18/the-bankers-are-coming-rbis-architecture-for-bank-financed-takeovers/)

> We're a bank considering financing an acquisition by a non-financial company. Under RBI's new draft directions on bank-financed takeovers (Oct 2025), the acquisition loan is capped at 10% of Tier-1 capital. Does this cap apply per-borrower or per-transaction? If the acquirer has existing credit facilities with us, does the acquisition finance count toward the Large Exposure Framework limits?

**Why LLMs fail:** Jan 2026 analysis of Oct 2025 draft directions. Interaction between new acquisition finance cap and existing LEF — not addressed in any single circular.

---

### 18. Insurance Distribution — DPDP + IRDAI Data Governance (Cross-regulatory)
**Source:** [Cyril Amarchand - Insurance Distribution Compliance](https://corporate.cyrilamarchandblogs.com/2026/01/insurance-distribution-in-india-emerging-channels-compliance-and-data-governance/)

> We're an insurtech distributing policies through a digital platform. Under the new DPDP Rules 2025, we need explicit consent for customer data processing. But IRDAI's regulations require us to share customer data with the Insurance Information Bureau (IIB) for portability. Can we rely on "compliance with law" as a lawful basis under DPDP to share with IIB without separate consent? How do IRDAI's data governance requirements interact with DPDP's Data Fiduciary obligations?

**Why LLMs fail:** Three-way interaction: DPDP Act + IRDAI regulations + IIB data sharing requirements. Very recent (Jan 2026 analysis).

---

### 19. NBFC Project Finance Directions 2025 (Recent — Oct 2025 effective)
**Source:** [Probe42 - RBI Project Finance](https://resources.probe42.in/regulatory-updates/rbi-circulars/rbi-project-finance-directions/)

> Our NBFC finances infrastructure projects. Under the new Project Finance Directions 2025 (effective Oct 2025), what are the enhanced provisioning requirements during the construction phase? The old guidelines had standard asset provisioning at 0.4% — has this changed? Are there new requirements for independent monitoring of project milestones?

**Why LLMs fail:** Oct 2025 directions replacing older framework. Specific provisioning percentages during construction phase.

---

### 20. SBR Review 2026 — Impact on Middle Layer NBFCs (Evolving regulation)
**Source:** [VisionIAS - RBI SBR Review](https://visionias.in/current-affairs/news-today/2025-12-30/economy/rbi-initiates-review-of-scale-based-regulation-sbr-for-nbfcs)

> RBI announced a review of the Scale-Based Regulation framework in Dec 2025, citing increasing NBFC-bank interconnection. Our NBFC is at the ₹950 crore threshold — just below the ₹1000 crore Middle Layer cutoff. Should we be preparing for the threshold to be lowered? What are the likely additional requirements if we move from Base to Middle Layer — CRAR increase to 15%, ALM reporting, risk committee, independent directors?

**Why LLMs fail:** Forward-looking regulatory risk question. Requires understanding the SBR review context + current Base vs Middle Layer obligation differences.

---

---

## Part B: GST & Indirect Tax — Practitioner Questions (Client↔CA conversations)

These questions are sourced from real CA-client and CA-forum interactions. They test ground-level compliance knowledge: portal quirks, rate change transitions, procedural workarounds.

### G1. Inverted Duty Refund on Pharma (Client → CA)
> Our raw materials are at 18% GST and finished medicines are now at 5%. Can we get a refund on the difference? Our purchase manager says there's something called inverted duty refund.

**Why LLMs fail:** Needs to know Rule 89(5) formula specifics, exclusions for certain products, and whether pharma inputs qualify. Generic answer will miss the refund calculation method.

---

### G2. Partial Settlement Under Section 128A (CA → forum)
> Client got a single demand order covering 2018-19 and 2020-21. Wants to settle only the older year under 128A. The order doesn't split the amount year-wise. How do I file for partial settlement?

**Why LLMs fail:** 128A amnesty is recent. The question is about a procedural gap — the law allows it but the order format doesn't support it. Requires practical knowledge.

---

### G3. GST Rate Change Mid-Booking — Advance vs Balance (Client → CA)
> We took an advance for a hotel booking at 12% GST in September. Guest checks in after September 22 when the rate changed to 5%. What rate do we charge on the balance amount?

**Why LLMs fail:** Time-of-supply rules for advances (Section 13) + rate change provisions. Most LLMs will give a generic "rate at time of supply" answer without handling the split correctly.

---

### G4. ITC Reversal on Closing Stock After Rate Reduction (CA → forum)
> Rate went from 18% to 5% — not exempt, still taxable. Officers are sending notices for ITC reversal on closing stock under Section 18(4). Is this even valid? Anyone else getting these?

**Why LLMs fail:** Section 18(4) applies when goods become exempt, NOT when rate reduces. Officers are misapplying the provision. An LLM needs to know the correct legal position AND the common enforcement error.

---

### G5. Stranded Compensation Cess Credit (Client → CA)
> We're an auto dealer. We have ₹45 lakh of compensation cess credit in our ledger. Cess has been abolished. Is this money gone?

**Why LLMs fail:** No refund mechanism exists for stranded cess credit. Multiple writ petitions pending (Rajasthan HC, etc.). LLM needs to know both the legal position AND the litigation landscape.

---

### G6. Accidental IMS Invoice Rejection (CA → forum)
> Client rejected an invoice by mistake on IMS. Supplier has already filed 3B. What's the cleanest way to fix this without a cash flow hit?

**Why LLMs fail:** IMS (Invoice Management System) is new. The workaround involves supplier issuing credit note + fresh invoice, or amendment in next period. Portal-specific procedural knowledge.

---

### G7. EMI Deferred Duty Scheme — Trader vs Manufacturer Registration (Client → CA)
> I import components and get them assembled by a job worker. I want to apply for the EMI deferred duty scheme but my GST registration says 'trader' not 'manufacturer.' Am I eligible or not?

**Why LLMs fail:** Cross-domain question spanning customs (IGCR rules, deferred duty) + GST registration categories + job work provisions. The eligibility depends on whether "getting goods manufactured" counts.

---

### G8. 128A Amnesty — Portal SPL-01 vs GSTR-3B Payment (CA → forum)
> Paid the 73 demand through GSTR-3B to take 128A amnesty. Circular says that's fine. But the portal's SPL-01 form only accepts DRC-03 challan numbers. Deadline is June 30. Anyone found a workaround?

**Why LLMs fail:** Classic law-vs-portal gap. The circular permits GSTR-3B payment but the portal doesn't support it. An LLM cannot know about GSTN portal bugs/limitations.

---

### G9. Anti-Profiteering After Rate Reduction — MRP Obligation (Client → CA)
> Our product dropped from 18% to 5% GST. We were already giving 15% trade discounts. Do we legally have to reduce MRP further? My competitor isn't reducing theirs.

**Why LLMs fail:** Anti-profiteering provisions (Section 171) + NAPA/CCI jurisdiction. The nuance: if discount already exceeds the rate reduction benefit, further MRP cut may not be required. Fact-specific analysis.

---

### G10. GTA Rate Option — Contract Mismatch (Client → CA)
> We're a transporter. Our contracts all say 'GST at 12% with ITC' but that rate doesn't exist anymore. Can we charge 18% with ITC instead? Or do we need to redo every contract?

**Why LLMs fail:** GTA rate options (5% without ITC / 12% with ITC) have been restructured. Requires knowing the current valid rate options + contractual implications of rate migration.

---

### G11. Wrong HS Code on Past Imports — Self-Correction (Client → CA)
> We just found out we declared the wrong HS code on about 200 import entries from last year. Our clearing agent says there's some new provision where we can self-correct after clearance. Can we just fix it or will customs come after us?

**Why LLMs fail:** CBIC's Voluntary Compliance Encouragement Scheme + Section 149 of Customs Act amendment. Recent provision. Risk of triggering investigation depends on whether duty differential is in favour of or against the importer.

---

### G12. Group Health Policy GST Exemption Threshold (CA → forum)
> Client is an insurer. Individual health policies are now exempt post-September 22. But they also issue group health policies to small companies — like 3-4 employees. Is a group policy with 3 people really a 'group policy' for GST? Or is it effectively individual cover that's been bundled? No one's clarified the threshold.

**Why LLMs fail:** No threshold defined in the notification. Genuinely ambiguous — the GST Council didn't clarify what constitutes "group." Requires knowing the gap exists, not just the rule.

---

### G13. GSTR-9C Separate Late Fee (Client → CA)
> We filed our GSTR-9 for 2024-25 but haven't done 9C yet. My accountant says there's now a separate late fee for filing 9C after 9. Is that true? I thought 9C was just an attachment to 9.

**Why LLMs fail:** GSTR-9C was delinked from GSTR-9 as a separate filing. Late fee provisions changed. Most LLMs still treat 9C as a part of 9.

---

### G14. Table 8A Reconciliation — Portal vs Download Mismatch (CA → forum)
> Anyone figured out the Table 8A reconciliation this year? The Excel download shows different numbers from the online auto-populated value. GSTN says use the online number. But the online number doesn't match my books either. Which one do I reconcile against?

**Why LLMs fail:** Pure portal-level operational question. The mismatch is a known GSTN bug/timing issue. An LLM cannot know about portal data discrepancies.

---

### G15. E-Commerce TCS After Rate Change (Client → CA)
> We supply to an e-commerce platform. Earlier they were collecting TCS on our sales. Now our product is at 5% — does the platform still collect TCS? My payment from them this month seems lower than expected and I can't tell if it's the rate change or TCS.

**Why LLMs fail:** TCS under Section 52 applies regardless of rate. But the TCS amount changes with the rate. Requires understanding the interaction between rate change and TCS computation on net value.

---

### G16. QRMP + IMS Credit Note Dispute (CA → forum)
> Client is on the QRMP scheme, quarterly filer. A supplier issued a credit note in October that my client disputes — the goods were fine, no reason for the CN. If he just ignores it on IMS, does it auto-accept after the quarter and force ITC reversal? What's the recourse?

**Why LLMs fail:** QRMP + IMS interaction. Auto-acceptance rules for credit notes on IMS are new. The deemed acceptance timeline and dispute mechanism are procedural knowledge that LLMs lack.

---

### G17. State Incentive Killed by Inverted Duty (Client → CA)
> My state government incentive reimburses us for 'net GST paid in cash' — meaning output tax minus ITC. Our output just dropped from 18% to 5% but input ITC is still 18%. So we'll never pay cash GST again. Does that mean our state incentive is effectively zero now?

**Why LLMs fail:** Intersection of state industrial policy + GST inverted duty structure. The incentive scheme wording determines the answer. No central regulation governs this — it's state-specific.

---

### G18. Product Reclassification Risk — Retrospective Notices (Client → CA)
> We're a small manufacturer. Our product got reclassified during the rate rationalization — my competitor says it's 'food preparation' at 5% but we've been filing as 'beverage' at 18%. If we switch classification now, will we get a notice for the past years too?

**Why LLMs fail:** Classification dispute + retrospective risk assessment. Requires knowing advance ruling precedents, the difference between reclassification and misclassification, and Section 73/74 limitation periods.

---

### G19. GSTAT Appeal — Bench Jurisdiction and Amount Threshold (CA → forum)
> Client wants to file a backlog appeal with GSTAT. Amount is ₹42 lakh — under ₹50 lakh so should be single-member bench. But it's a classification dispute. Will they kick it to a division bench mid-hearing? If so does the timeline restart?

**Why LLMs fail:** GSTAT is newly operational. Bench allocation rules, monetary thresholds for single vs division bench, and mid-hearing transfer procedure are brand new procedural law.

---

### G20. Capital Goods at Job Worker — 3-Year ITC Reversal Deadline (Client → CA)
> I sent my capital goods to a job worker 2 years ago. I claimed ITC when I bought them. My CA at the time said I need to get them back within 3 years or reverse the ITC. The job worker says he needs 6 more months. What happens if I cross the 3-year limit?

**Why LLMs fail:** Section 19(5)/(6) + Rule 45. The 3-year clock, deemed supply implications, and whether extension is possible. Most LLMs will state the rule but miss the practical consequence (deemed supply + tax liability on market value).

---

## Sources for More Questions
- [IndiaCorpLaw](https://indiacorplaw.in) — Cross-regulator analysis, academic edge cases
- [Vinod Kothari Consultants](https://vinodkothari.com) — NBFC practitioner interpretation
- [Probe42 Regulatory Updates](https://resources.probe42.in/regulatory-updates/) — AI-summarized circulars (also a competitor)
- [ComplianceCalendar.in](https://www.compliancecalendar.in/learn/nbfc-rbi-compliance-calendar-for-2025-26) — Deadline/filing questions
- [RBI NBFC FAQs (Feb 2026)](https://www.rbi.org.in/commonman/Upload/English/FAQs/PDFs/ALLNBFC23042025.pdf) — Official clarifications
- [K&S Partners - DPDP Cross-over](https://ksandk.com/data-protection-and-data-privacy/dpdp-sector-regulators-navigating-rbi-sebi-irdai-trai/) — Data protection vs sectoral regulators
- [Chambers - RBI Penalty Wave](https://chambers.com/articles/when-compliance-fails-stories-behind-rbis-2024-penalty-wave) — Enforcement patterns
- [Face of India - RBI Penalties Compilation (FY 24-25)](https://faceofindia.org/wp-content/uploads/2025/04/A-compliation-of-RBI-penal-and-enforcement-actions-in-FY-24-25_-released-on-11-Apr-2025.pdf) — Full penalty dataset
- RBI/SEBI enforcement orders — What companies actually got wrong
- Taxmann / CAClubIndia forums — Practitioner questions (more tax-focused)
- [Cyril Amarchand Blogs](https://corporate.cyrilamarchandblogs.com) — Law firm analysis of regulatory developments
- [Mondaq India](https://www.mondaq.com/india/) — Multi-firm regulatory commentary

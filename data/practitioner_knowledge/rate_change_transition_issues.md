---
title: GST Rate Change Transition Issues
topic: Rate change, transition, advance payment, anti-profiteering, closing stock ITC
tags: G3, G4, G9, rate change, anti-profiteering, advance payment, ITC reversal
date: 2026-03-11
---

# GST Rate Change Transition Issues

## Overview

When GST rates change (increase or decrease), several transition issues arise around invoicing, ITC, advance payments, and anti-profiteering compliance. This document covers practical handling of rate changes for CA practitioners.

## Advance Payments Before Rate Change

### Rate Decrease Scenario

**Situation**: Customer paid advance at old (higher) rate, supply made after rate reduction.

**Treatment under Section 14 of CGST Act**:
- If supply is made after the rate reduction date, the new (lower) rate applies
- Excess tax collected as advance must be refunded to the customer OR adjusted
- Issue a credit note for the differential tax
- Adjust in the return for the period in which the supply is made

**Practical Steps**:
1. Identify all advances received before the rate change date
2. Calculate differential tax (old rate - new rate) on the advance
3. Issue credit note to the customer
4. Claim adjustment in GSTR-3B of the supply month

### Rate Increase Scenario

**Situation**: Advance paid at old (lower) rate, supply made after rate increase.

**Treatment**:
- New (higher) rate applies to the supply
- Differential tax must be collected from the customer
- Issue a supplementary invoice/debit note for the additional tax
- Report in GSTR-1 of the supply period

## Closing Stock ITC on Rate Reduction

### The Problem

When the GST rate on a product is reduced, the ITC on closing stock purchased at the higher rate results in "stranded credit" (ITC > output tax liability).

### Legal Position

**Section 18(4) of CGST Act + Rule 44(4)**:
- When goods become exempt from tax, ITC on closing stock must be reversed
- When rate is reduced (but not to zero), there is NO mandatory ITC reversal — this is a rate change, not an exemption

**However**:
- The differential ITC (claimed at higher rate, output at lower rate) creates accumulated credit
- This can be claimed as refund under Section 54(3) — inverted duty structure refund
- **BUT**: Refund under inverted duty is only available if the accumulation is due to rate of tax on inputs being higher than rate on output supplies

### Practical Guidance

1. **No automatic reversal needed** — ITC claimed at higher rate on stock is valid
2. Track the ITC on closing stock separately for audit purposes
3. If the rate change makes the business unviable (high ITC, low output tax), evaluate refund under Section 54(3)
4. Monitor for any specific transition notification (CBIC sometimes issues specific rules for major rate changes)

## Anti-Profiteering Obligations (Section 171)

### What It Requires

When GST rate is reduced OR ITC benefit is expanded, the supplier must pass the benefit to the consumer through commensurate price reduction.

### Current Status

- The National Anti-Profiteering Authority (NAA) was dissolved on 01.12.2022
- Anti-profiteering matters now handled by the **Competition Commission of India (CCI)**
- State-level screening committees continue to receive complaints

### Practical Steps After Rate Reduction

1. **Calculate the benefit**: (Old rate - New rate) × Base price = benefit to be passed
2. **Reduce MRP/selling price** commensurately
3. **Maintain documentation**: Show pre and post rate change pricing, margin analysis
4. **Display the reduced price**: Update price tags, invoicing systems, websites
5. **Retain evidence** for at least 3 years (limitation period for complaints)

### Common Anti-Profiteering Risks

- Increasing base price to offset rate reduction (MRP remains same)
- Claiming that input costs increased simultaneously (must prove with evidence)
- Not passing benefit on existing stock (benefit applies from the date of rate change)

## Invoice and Credit Note Procedures

### For Supplies Straddling Rate Change

| Timing | Invoice Rate | Notes |
|--------|-------------|-------|
| Supply before rate change, invoice before | Old rate | No issue |
| Supply before rate change, invoice after | Old rate | Time of supply is date of supply |
| Supply after rate change, invoice before | New rate | Correct via credit/debit note |
| Supply after rate change, invoice after | New rate | No issue |

### Time of Supply Rules (Section 12/13)

- For goods: Earlier of invoice date or receipt of payment
- For services: Earlier of invoice date or receipt of payment or date of provision
- **Special provision for rate change**: Section 14 overrides — the rate applicable is based on when the supply occurs, regardless of invoice/payment timing

## Hotel Advance Booking — Which Rate Applies?

### The Scenario

A hotel collects an advance for a banquet/event booking when the GST rate is 18%. Before the event date, the rate is reduced to 12%. Which rate applies?

### Legal Provision: Section 14 of CGST Act

**Section 14** specifically addresses this situation — "Change in rate of tax in respect of supply of goods or services":

- **Section 14(b)(ii)**: Where the payment has been received **before** the change in rate but the supply is made **after** the change in rate — the **new rate** (i.e., the rate at the time of supply) applies
- The hotel must apply the **12% rate** (new/reduced rate) even though the advance was collected at 18%
- The differential (6% excess collected) must be refunded to the customer or adjusted via credit note

### Clarificatory Circulars

- **CBIC Circular No. 1/1/2017-GST (Transition)** clarified that Section 14 overrides the normal time-of-supply rules in Sections 12/13
- The rate at the **time of actual supply** (event date) determines the applicable rate, not the time of advance receipt
- This applies to both rate increases and rate decreases

### Practical Steps for Hotels

1. Identify all advances received at the old rate for events scheduled after the rate change date
2. Calculate the differential tax (old rate minus new rate) on each advance
3. Issue a **credit note** to the customer for the excess tax collected
4. Adjust the excess tax in the GSTR-3B return for the period of the event (not the advance period)
5. If the rate increases instead: collect the additional tax from the customer via a supplementary invoice

## MRP Obligations After Rate Change — Legal Framework

### Which Law Governs MRP Revision?

Three laws interact when GST rates change and MRP needs revision:

### 1. Legal Metrology Act, 2009 (and Rules 2011)

- **Rule 18 of Legal Metrology (Packaged Commodities) Rules, 2011**: MRP declared on the package is the maximum price including all taxes
- When GST rate is **reduced**, the existing MRP already includes the old (higher) tax → the manufacturer is NOT legally required to re-label existing stock
- However, **new stock** manufactured after the rate change must have the revised MRP reflecting the lower tax
- The Legal Metrology Act does NOT mandate reprinting MRP on existing stock in warehouses

### 2. GST Law — Anti-Profiteering (Section 171)

- Section 171 requires that any reduction in rate of tax or benefit of ITC must be passed on to the consumer by way of commensurate reduction in prices
- This is a GST-specific obligation that goes BEYOND what the Legal Metrology Act requires
- Under Section 171, the manufacturer MUST reduce the effective selling price (even if MRP label is not changed)
- Can sell below MRP (which is a maximum price) to comply with anti-profiteering

### 3. Consumer Protection Act, 2019

- Section 2(47) defines unfair trade practice — selling above MRP is an offence
- But selling BELOW MRP after a rate reduction to pass benefit is perfectly legal
- Consumer complaints about non-pass-through of GST reduction are handled under anti-profiteering framework, not directly under CPA

### NAA/CCI Rulings

- The **National Anti-Profiteering Authority (NAA)** (dissolved 01.12.2022, functions transferred to **CCI**) held in multiple cases:
  - Manufacturers must reduce base price so that MRP reflects the reduced GST rate for new production
  - For existing stock: Must sell at effective price reflecting new rate (even if MRP label shows old price)
  - Penalty for non-compliance: Amount of profiteering + 10% penalty
  - Key precedent: NAA ruled against HUL, Pyramid Infratech, etc. for not passing GST rate reduction benefit
- **CCI** now handles anti-profiteering complaints through the Directorate General of Anti-Profiteering (DGAP)
- State-level Screening Committees continue to receive and forward complaints to DGAP

## Checklist for CAs During Rate Change

1. Identify all ongoing contracts with fixed prices — these may need re-negotiation
2. Review advance receipts and pending invoices
3. Update billing software with new rates from the effective date
4. Communicate with clients about anti-profiteering obligations
5. File GSTR-1 carefully — ensure correct rate is applied to each invoice
6. Monitor closing stock position for stranded credit assessment
7. Check if any specific transition provisions have been notified
8. For MRP products: Ensure new production has revised MRP; for existing stock, sell at effective reduced price

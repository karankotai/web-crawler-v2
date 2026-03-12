---
title: E-Commerce TCS After Rate Change
topic: E-commerce, TCS, Section 52, rate change, reconciliation
tags: G15, e-commerce, TCS, Section 52, payment reconciliation
date: 2026-03-11
---

# E-Commerce TCS After Rate Change

## Overview

E-commerce operators are required to collect Tax Collected at Source (TCS) under Section 52 of the CGST Act at the rate of 1% (0.5% CGST + 0.5% SGST/UTGST, or 1% IGST for inter-state). When underlying GST rates on products change, TCS computation and reconciliation create practical challenges.

## TCS Basics

- **Who collects**: E-commerce operators (Amazon, Flipkart, etc.)
- **Rate**: 1% of net taxable supplies (after deducting returns)
- **Filing**: GSTR-8 by the 10th of the following month
- **Credit**: Sellers claim TCS credit in their GSTR-3B (auto-populated from GSTR-8)
- **Net value**: TCS is calculated on the net value of supplies (not including GST)

## Impact of Rate Change on TCS

### TCS Rate Does NOT Change

TCS under Section 52 is a fixed 1% — it does not change when the underlying product GST rate changes. However:

1. **Net taxable value may change** — if the seller adjusts prices after rate change (anti-profiteering), the base value changes, affecting TCS amount
2. **Returns straddling rate change** — goods sold at old rate, returned after rate change — TCS adjustment is based on original sale amount

### Reconciliation Challenges

**Problem**: When product GST rates change mid-month, the e-commerce platform must correctly split transactions:
- Pre-rate-change transactions: TCS on supplies at old GST rate
- Post-rate-change transactions: TCS on supplies at new GST rate

**The TCS amount itself remains 1%**, but the underlying tax treatment in GSTR-8 reporting must correctly reflect the changed rates for the tax period.

## Practical Issues for Sellers

### 1. TCS Credit Mismatch in GSTR-3B

**Problem**: The TCS amount shown in GSTR-2A/2B (from operator's GSTR-8) doesn't match the seller's calculation.

**Common Causes**:
- Timing of settlement: Sales recorded in different periods by seller vs operator
- Return/cancellation adjustments applied in different periods
- Rate change applied from different dates (operator's system vs seller's records)

**Resolution Steps**:
1. Download the "TCS Credit Received" report from the GST portal
2. Compare with your own sales records through the e-commerce platform
3. Reconcile differences by transaction
4. For persistent mismatches, raise with the e-commerce operator and file grievance on GST portal

### 2. Price Adjustment After Rate Reduction

When GST rate is reduced and the seller reduces the selling price (anti-profiteering), the TCS base value also reduces proportionally. The e-commerce operator must adjust their GSTR-8 accordingly.

### 3. Returns and Cancellations

For goods returned after a rate change:
- The return is processed at the original sale rate (not the new rate)
- TCS adjustment in GSTR-8 uses the original TCS amount
- The seller's credit note uses the original GST rate

## GSTR-8 Filing Considerations

- Report period-wise net supplies correctly
- Ensure rate-change-day transactions are classified correctly
- Negative entries for returns/cancellations at original rates
- Verify that TCS deducted matches bank settlements from the platform

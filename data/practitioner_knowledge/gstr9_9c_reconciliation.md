---
title: GSTR-9 and GSTR-9C Reconciliation Guide
topic: GSTR-9, GSTR-9C, annual return, reconciliation, Table 8A
tags: G13, G14, GSTR-9, GSTR-9C, Table 8A, annual return, late fee
date: 2026-03-11
---

# GSTR-9 and GSTR-9C Reconciliation Guide

## Overview

GSTR-9 is the annual return and GSTR-9C is the reconciliation statement (self-certified from FY 2020-21 onwards, previously required CA certification). This document covers common reconciliation issues, Table 8A mismatches, and practical filing strategies.

## GSTR-9C Changes: Delinked from GSTR-9

From FY 2020-21, GSTR-9C no longer requires CA/CMA certification. It is a self-certified reconciliation statement filed by the taxpayer along with GSTR-9.

**Key Change**: GSTR-9C is now mandatory for taxpayers with annual turnover exceeding Rs. 5 crore (previously Rs. 2 crore limit).

For turnover up to Rs. 5 crore, GSTR-9C filing is optional but GSTR-9 filing has been made optional for turnover up to Rs. 2 crore (check latest notification for current thresholds).

## Table 8A Reconciliation Issues

### The Problem

Table 8A of GSTR-9 auto-populates ITC from GSTR-2A (now GSTR-2B) for the entire financial year. However, mismatches frequently occur because:

1. **Timing differences**: Invoice reported by supplier in FY X but claimed by recipient in FY X+1 (or vice versa)
2. **Amendments**: Supplier amended invoice details in subsequent periods
3. **GSTR-2A vs GSTR-2B**: Table 8A historically pulled from GSTR-2A, but ITC was claimed based on GSTR-2B (post-IMS era)
4. **Credit notes**: Issued in a different period than the original invoice

### Reconciliation Approach

**Step 1**: Download Table 8A data from the GSTR-9 portal (auto-populated)

**Step 2**: Compare with your ITC register / books of accounts

**Step 3**: Identify differences and classify them:

| Category | Table 8A | Books | Action |
|----------|----------|-------|--------|
| ITC in 8A, claimed in books | Yes | Yes | No issue |
| ITC in 8A, not claimed | Yes | No | Report in Table 8D (other reasons) |
| ITC not in 8A, claimed | No | Yes | Report in Table 8C (from previous year) or 8F |
| Difference in amount | Different | Different | Report actual claimed in 8A-adjusted |

**Step 4**: Use the Excel offline tool to prepare reconciliation before online filing

### Common Pitfalls

1. **Don't blindly accept Table 8A figures** — they may include reversed credit notes, cancelled invoices
2. **GSTR-2B vs 8A mismatch**: If you claimed ITC based on GSTR-2B but Table 8A shows GSTR-2A amounts, the difference needs explanation in Table 8D/8F
3. **RCM ITC**: Reverse charge ITC is NOT part of Table 8A — it should be reported separately

## GSTR-9C Late Fee

### Current Late Fee Structure

- Late fee for GSTR-9: Rs. 200/day (Rs. 100 CGST + Rs. 100 SGST), maximum 0.5% of turnover in the state/UT
- Late fee for GSTR-9C: No separate late fee (filed along with GSTR-9)

### Late Fee Waivers

CBIC has periodically waived/reduced late fees for delayed GSTR-9 filing. Check the latest notifications for:
- Complete waiver for specific financial years
- Reduced late fee caps
- Extended due dates

## Excel vs Online Filing

### Online Filing
- Auto-populated data from GSTR-1, GSTR-3B, GSTR-2A/2B
- Tables partially editable
- Suitable for simpler cases
- **Limitation**: May timeout for large data volumes

### Excel Offline Tool
- Download from GST portal
- Fill offline with complete data
- Upload via JSON
- **Recommended** for: Taxpayers with many invoices, complex reconciliations, or multiple amendments

### Best Practice
1. Download the auto-populated GSTR-9 online
2. Export to Excel
3. Reconcile offline with books
4. Make corrections in Excel
5. Upload corrected JSON

## Practical Filing Tips

1. **Start early** — GSTR-9 requires data from GSTR-1, GSTR-3B, GSTR-2A/2B, and books. Reconciliation takes time.
2. **HSN summary**: Table 17/18 requires 6-digit HSN for turnover above Rs. 5 crore (4-digit for below)
3. **Nil returns**: If no transactions, still file GSTR-9 with zero values (unless exempted)
4. **Amendments made in next FY**: Report in the GSTR-9 of the year in which the amendment was made, with a note in additional information
5. **ITC reversal**: If ITC was reversed during the year and reclaimed, net figure should be reported

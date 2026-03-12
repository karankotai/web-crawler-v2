---
title: IMS Issues and Workarounds
topic: Invoice Management System, IMS, GSTR-2B
tags: G6, G16, IMS, QRMP, invoice rejection, credit notes
date: 2026-03-11
---

# IMS (Invoice Management System) Issues and Workarounds

## Overview

The Invoice Management System (IMS) was introduced on the GST portal from October 2024 onwards to allow recipients to accept, reject, or keep pending the invoices reported by their suppliers in GSTR-1/IFF. IMS directly impacts GSTR-2B generation and ITC availability. This document covers known issues, workarounds, and practical guidance for CAs.

## How IMS Works

1. **Supplier files GSTR-1/IFF** → invoices appear in recipient's IMS dashboard
2. **Recipient takes action** in IMS: Accept, Reject, or Pending (no action = deemed accepted after due date)
3. **GSTR-2B auto-generated** based on IMS actions — accepted invoices flow to ITC, rejected ones are excluded
4. **Supplier notified** of rejections via their dashboard

### Key Timelines
- IMS actions must be taken before GSTR-3B filing for the return period
- **Deemed acceptance**: If no action is taken by the filing due date, invoices are auto-accepted
- For QRMP taxpayers: IMS actions taken in M1/M2 are carried forward to quarterly return period

## Common Issues

### 1. Rejected Invoice Still Showing in GSTR-2B ITC

**Problem**: After rejecting an invoice in IMS, the ITC still appears in GSTR-2B.

**Root Cause**: GSTR-2B is generated on a specific date (usually 14th of the following month). If rejection was done after GSTR-2B generation but before GSTR-3B filing, the rejection reflects only in the next period's GSTR-2B.

**Workaround**:
- Check the "IMS action date" vs "GSTR-2B generation date"
- If rejection was timely, raise a grievance on the portal with screenshots
- Manually reduce ITC in GSTR-3B Table 4 and keep IMS rejection screenshot as evidence

### 2. QRMP Taxpayer IMS Interaction

**Problem**: QRMP (Quarterly Return Monthly Payment) taxpayers face confusion about when to take IMS actions since they file returns quarterly but IMS shows invoices monthly.

**Practical Guidance**:
- IMS actions can be taken in any month (M1, M2, M3) of the quarter
- All actions are consolidated when the quarterly GSTR-2B is generated
- **Best practice**: Take IMS actions monthly to avoid last-minute rush in M3
- IFF (Invoice Furnishing Facility) invoices from the supplier are also visible in IMS

### 3. Bulk Rejection Not Working

**Problem**: The portal's bulk accept/reject feature frequently times out for taxpayers with large volumes (500+ invoices).

**Workaround**:
- Process in batches of 100-200 invoices
- Use off-peak hours (early morning or late evening)
- Consider using GST Suvidha Provider (GSP) APIs for bulk operations

### 4. Credit Note Handling in IMS

**Problem**: Credit notes issued by the supplier appear in IMS but the accept/reject action is unclear — should the recipient accept a credit note (which reduces their ITC)?

**Clarification**:
- "Accept" on a credit note means you **agree** that your ITC should be reduced
- "Reject" means you dispute the credit note (the ITC reduction won't happen in your GSTR-2B)
- If a supplier issues a credit note for a genuine price reduction, you should accept it
- If the credit note is erroneous, reject it and communicate with the supplier

### 5. Deemed Acceptance After Due Date

**Problem**: CAs often miss the IMS action window, leading to deemed acceptance of invoices they wanted to reject (e.g., from unknown suppliers, duplicate invoices).

**Preventive Measures**:
- Set up a monthly IMS review calendar before the 11th of each month
- Download IMS pending list immediately after GSTR-1 due date (11th)
- Use the "Pending" status for invoices under dispute — this prevents deemed acceptance
- **Important**: "Pending" invoices do NOT flow to GSTR-2B ITC until explicitly accepted

## Portal Tips

- IMS is accessible at: GST Portal → Returns → IMS Dashboard
- Filter by: All, Accepted, Rejected, Pending, No Action
- Export feature: Download IMS data in Excel for reconciliation
- IMS history: Previous period actions are viewable for audit trail

## Regulatory References

- CGST Rule 60 (as amended by Notification No. 20/2024-Central Tax dated 08.10.2024)
- GSTN Advisory on IMS dated 14.10.2024
- CBIC Circular No. 237/31/2024-GST dated 15.10.2024

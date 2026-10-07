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

### 6. Credit Note Rejection After Invoice Acceptance

**Problem**: A supplier issues a credit note, but the recipient has already accepted the original invoice on IMS. The recipient now wants to reject the credit note to prevent ITC reduction.

**Step-by-Step Process on GST Portal**:

1. **Navigate to IMS Dashboard**: GST Portal → Returns → IMS Dashboard
2. **Locate the credit note**: Filter by document type = "Credit Note" and search by supplier GSTIN or credit note number
3. **Check status**: If the credit note shows "No Action" (pending), you can still reject it
4. **Click "Reject"**: Select the credit note and click the "Reject" action button
5. **Confirm rejection**: The system will show a confirmation — verify the credit note details and confirm
6. **Result**: After rejection, the credit note will NOT reduce your ITC in the next GSTR-2B generation
7. **Supplier notification**: The supplier will see the rejection in their IMS dashboard and in GSTR-1 return status

**If rejection was missed (credit note was deemed accepted)**:
- If the credit note was auto-accepted (deemed accepted after due date), you CANNOT reverse it through IMS
- **Workaround 1**: Raise a **grievance** on the GST portal (Services → User Services → Grievance) explaining the erroneous acceptance
- **Workaround 2**: Ask the supplier to issue a fresh debit note to reverse the credit note effect
- **Workaround 3**: Manually add the ITC back in GSTR-3B Table 4 with a clear audit trail (take screenshot of the IMS credit note and the communication with supplier)

**Important**: The ITC adjustment happens only when GSTR-2B is generated. If you reject before the GSTR-2B generation date (typically 14th of the month), the rejection will reflect in the current period's GSTR-2B.

### 7. QRMP Taxpayer and Disputed Credit Notes — ITC Impact

**Problem**: A QRMP (Quarterly Return Monthly Payment) taxpayer receives a credit note from a supplier. Under IMS, credit notes are auto-accepted if not acted upon. If the taxpayer disputes the credit note, what happens to ITC in the next quarterly GSTR-3B?

**How It Works**:

1. **Monthly IMS visibility**: Even though QRMP taxpayers file returns quarterly, IMS shows credit notes monthly
2. **Action window**: QRMP taxpayers can take IMS actions in any month (M1, M2, or M3) of the quarter
3. **If taxpayer REJECTS the credit note**:
   - The credit note will be excluded from the quarterly GSTR-2B
   - ITC will NOT be reduced in the next quarterly GSTR-3B
   - The supplier is notified of the rejection
4. **If taxpayer takes NO ACTION** (misses the window):
   - Credit note is **deemed accepted** after the quarterly GSTR-3B filing due date
   - ITC WILL be reduced in the next quarter's GSTR-2B
   - The taxpayer would need to use grievance mechanism to reverse

**Best Practice for QRMP Taxpayers**:
- Review IMS dashboard **monthly** (not just before quarterly filing)
- Set reminders for the 11th-13th of each month to review new invoices and credit notes
- Reject disputed credit notes immediately upon appearance — don't wait for M3
- Download and save IMS data each month for reconciliation

**ITC Flow for Rejected Credit Note**:
- Quarter 1: Supplier issues credit note → appears in IMS
- QRMP taxpayer rejects in IMS during the quarter
- Quarterly GSTR-2B generated: Credit note NOT included (no ITC reduction)
- GSTR-3B for the quarter: ITC remains as claimed from original invoice
- Supplier sees rejection → must resolve the dispute commercially

## Regulatory References

- CGST Rule 60 (as amended by Notification No. 20/2024-Central Tax dated 08.10.2024)
- GSTN Advisory on IMS dated 14.10.2024
- CBIC Circular No. 237/31/2024-GST dated 15.10.2024
- GSTN FAQ on IMS for QRMP Taxpayers (December 2024)

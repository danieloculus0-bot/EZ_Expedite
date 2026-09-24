# EZ Expedite RMA User Training Guide

Application version: **0.1.1**  
Guide revision: **1.0**

## Quick Start

Use this section for day-to-day operation.

### If you receive an RMA Action Required notification

1. Open the Teams message.
2. Select **Open RMA**.
3. Sign in with Microsoft 365 if prompted.
4. Confirm the page shows **Action Required** for your department.
5. Complete the required fields for the current stage.
6. Add a progress note if there is useful status information.
7. Select **Complete / Advance**.
8. If EZ Expedite shows a blocker, complete the missing requirement and try again.
9. When the stage advances successfully, the next department is assigned and notified automatically.

### If the page says Read Only

You are not a primary delegate for the current stage.

- Review the RMA as needed.
- Do not attempt to advance it.
- Contact the current primary department if action is required.

### Current RMA routing

```text
Customer Service
  Intake
      ↓
Shipping
  Product Returned to WMF
      ↓
Quality
  RMA Review
      ↓
Shipping
  Product Returned to Customer
      ↓
Complete / Closure
```

### What each primary does

| Department | Stage | Primary action |
| --- | --- | --- |
| Customer Service | Intake | Enter RMA/customer/contact/defect information and advance |
| Shipping | Product Returned to WMF | Confirm receipt and RMA hold-area placement |
| Quality | RMA Review | Review product and document work-order requirements |
| Shipping | Product Returned to Customer | Complete final inspection/shipping confirmations and advance |

### Past-due work

- Use the dashboard aging heatmap to see how old overdue items are.
- The heatmap uses **blue shades only**.
- Add progress notes when status changes.
- Responsible users receive one grouped past-due Teams digest per day rather than one message per overdue occurrence.

### Need to find an RMA?

Use the dashboard search box and search by:

- RMA Number
- EZ Expedite case number
- customer
- part
- owner
- description

---

## Quick answers

### How does the designee advance the notification?

The active primary delegate opens the RMA, completes the fields in the **Action Required** panel, adds a progress note when appropriate, and selects **Complete / Advance**.

EZ Expedite validates the stage requirements. If they are satisfied, the system advances the RMA, changes the active department, logs the transition, and sends the next notification automatically.

### Will the workflow operate in Teams?

Yes. Teams is the notification and routing surface.

Primary delegates receive **RMA - ACTION REQUIRED**. Read-only CC recipients receive **RMA UPDATE - READ ONLY**.

The Teams notification contains the RMA details and an **Open RMA** link. The data-entry form itself is currently in the EZ Expedite browser application, not embedded in a Teams card or Teams tab.

## RMA workflow

```text
Intake
  -> Product Returned to WMF
  -> RMA Review
  -> Product Returned to Customer
  -> Complete
```

| Stage | Primary | Required action |
| --- | --- | --- |
| Intake | Customer Service | Enter RMA Number, defect, CSR, PO, customer/contact information and notes |
| Product Returned to WMF | Shipping | Confirm receipt, receive date and RMA hold-area placement |
| RMA Review | Quality | Review product and determine/record work-order requirements |
| Product Returned to Customer | Shipping | Record final inspection result, shipping approval/readiness and shipment confirmation |
| Complete | Closure | Complete normal closure requirements |

## Roles and responsibilities

### Customer Service - Primary 1 / Primary 2

- Owns **Intake**
- Creates or initiates the RMA
- Completes required intake information
- Adds progress notes
- Selects **Complete / Advance**

### Shipping - Primary 1 / Primary 2

Owns two stages.

**Product Returned to WMF**
- Confirm product receipt
- Verify receive date
- Confirm RMA hold-area placement
- Add progress note
- Select **Complete / Advance**

**Product Returned to Customer**
- Record final quality result
- Confirm approval to ship
- Confirm ready to ship
- Confirm shipment and shipment date
- Add progress note
- Select **Complete / Advance**

### Quality - Primary 1 / Primary 2

- Owns **RMA Review**
- Confirms product review
- Determines whether a work order is required
- If required, confirms issue status and Work Order number
- Adds progress notes
- Selects **Complete / Advance**

### Read-only CC users

Configured CC groups may include Quality, Operations, Customer Service and Design.

Read-only users:
- receive visibility notifications
- can open and review the RMA
- cannot change RMA data in multi-user mode
- cannot add RMA progress notes
- cannot select **Complete / Advance**

A CC user must also be configured as a current-stage primary delegate to perform that stage.

## What to do when a Teams notification arrives

1. Open the **RMA - ACTION REQUIRED** Teams message.
2. Review the RMA number, stage, customer, defect, PO, next action and due date.
3. Select **Open RMA**.
4. Sign in with Microsoft 365 if prompted.
5. Confirm that the RMA panel shows **Action Required**.
6. Complete the fields for the active stage.
7. Add a progress note when useful.
8. Select **Complete / Advance**.
9. If a required field is missing, review the blocker shown by EZ Expedite and correct it.
10. When validation passes, the next department is assigned and notified automatically.

If the page shows **Read Only**, the connected Microsoft account is not configured as a primary delegate for that stage.

## Stage 1 - Intake

Required:

- RMA Number
- Defect Type
- CSR Name
- PO #
- Customer Name
- Contact Name
- Contact #
- Notes

After **Complete / Advance**, the RMA routes to Shipping.

## Stage 2 - Product Returned to WMF

Required:

- Received from Customer = YES
- Receive Date
- RMA Hold Area confirmed

A NO response does not allow advancement.

After **Complete / Advance**, the RMA routes to Quality.

## Stage 3 - RMA Review

Required:

- Product reviewed
- Work Order Required = YES / NO
- If YES:
  - Work Order Issued = YES
  - Work Order #

After **Complete / Advance**, the RMA routes to Shipping.

## Stage 4 - Product Returned to Customer

Required:

- Final Quality Inspection = PASS / FAIL
- Approved to Ship = YES
- Ready to Ship = YES
- Shipped to Customer
- Returned / Shipped Date

A **FAIL** result routes the RMA back to **RMA Review**.

A passing completed stage routes the RMA to **Complete**.

## Complete and closure

The routed workflow reaching Complete does not bypass closure controls.

Closure can still require:

- owner/responsibility
- closure checklist items
- containment completion
- corrective-action completion
- financial recovery or approved waiver
- required custom fields

## Dashboard

The dashboard includes:

- Open
- Overdue
- Unassigned
- Stale 7+ days
- Awaiting Recovery
- Recovery Outstanding
- search and filters
- latest progress note
- quick progress-note entry for authorized users

### Past-due aging heatmap

The aging heatmap uses shades of the configured EZ Fab / WMF blue only:

- 1-3 days
- 4-7 days
- 8-14 days
- 15-30 days
- 31+ days

Darker blue indicates greater age.

## Daily past-due Teams digest

EZ Expedite does not send one reminder for every overdue RMA.

Each responsible recipient receives at most one past-due digest per calendar day.

The digest groups all overdue items assigned to that recipient and includes:

- case number
- days past due
- occurrence type
- title
- next action
- latest progress note

For RMAs, the digest goes to the primary delegates for the current stage.

## Microsoft 365 sign-in

Microsoft 365 identity is used in multi-user mode to determine whether a user can edit and advance the active RMA stage.

EZ Expedite does not ask the user to enter a Microsoft password into the application. Microsoft handles the sign-in.

## Installer

Direct download:

https://github.com/danieloculus0-bot/EZ_Expedite/releases/download/v0.1.1/EZ_Expedite_Setup_0.1.1.exe

The installer includes the Python runtime and application dependencies. End users do not need Python installed.

## Administrator setup

Configure:

- Customer Service Primary 1 / Primary 2
- Shipping Primary 1 / Primary 2
- Quality Primary 1 / Primary 2
- read-only CC groups
- Microsoft notification account
- Microsoft multi-user sign-in
- shared/public base URL
- network listener / firewall access
- database and attachment backup

For shared use, run one EZ Expedite instance and have users connect to that host in their browser. Do not run separate independent SQLite databases for each user.

## Troubleshooting

| Issue | Resolution |
| --- | --- |
| Teams message received but RMA is Read Only | Confirm the connected Microsoft account is configured as a current-stage primary delegate |
| Complete / Advance does not advance | Review the blocker; one or more required fields are incomplete |
| Final inspection FAIL selected | The RMA is expected to return to RMA Review |
| No Teams notifications | Verify notification account connection, delegate email and tenant Graph permissions |
| Open RMA link fails for another user | Verify the shared/public base URL and network access |
| Cannot add a progress note | In multi-user RMA mode, only active-stage primary delegates can write RMA progress notes |
| Installer blocked by Windows | Verify the official GitHub release source; company policy may require IT approval |

## Training sign-off

Users should be able to demonstrate:

- identifying **Action Required** versus **Read Only**
- opening an RMA from Teams
- signing in with the correct Microsoft 365 account
- completing the required fields for their assigned stage
- entering a progress note
- using **Complete / Advance**
- understanding validation blockers
- understanding final-inspection FAIL routing
- understanding read-only CC responsibilities
- interpreting the blue past-due aging heatmap
- understanding the daily past-due Teams digest

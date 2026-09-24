# EZ Expedite

EZ Expedite is a standalone occurrence tracking and expediting application for manufacturing and operational work that needs an owner, a next action, a due date, escalation, documented progress, and verified closure.

RMA is the first configured occurrence type, but the core application is generic and can also be used for:

- NCRs
- CAPAs
- supplier issues
- audit findings
- purchasing requests and shortages
- maintenance problems
- delivery failures
- customer complaints
- engineering actions
- safety follow-ups
- internal action items
- IT tickets
- other occurrence-driven workflows

## Windows installer

The intended end-user distribution is:

```text
EZ_Expedite_Setup_0.1.1.exe
```

Direct installer download:

https://github.com/danieloculus0-bot/EZ_Expedite/releases/download/v0.1.1/EZ_Expedite_Setup_0.1.1.exe

The installer is per-user and normally does not require administrator rights.

It installs EZ Expedite under:

```text
%LOCALAPPDATA%\Programs\EZ Expedite
```

The installer:

- installs the standalone application
- includes the Python runtime and application dependencies
- creates a Start Menu shortcut
- offers an optional desktop shortcut
- registers EZ Expedite in Windows Installed Apps
- installs a normal Windows uninstaller
- does not require Python on the user's machine

Operational data is stored separately under:

```text
%LOCALAPPDATA%\EZ_Expedite\instance
```

That directory contains the SQLite database, attachments, configuration, Flask secret, and Microsoft token cache. Uninstalling the application does not delete that operational data.

GitHub Actions produces:

- `EZ_Expedite-Installer` - normal Windows installer
- `EZ_Expedite-Windows` - standalone EXE for troubleshooting and portable testing

The Windows workflow:

1. runs the smoke test
2. runs the pre-release functional test
3. builds the standalone EXE
4. launches the EXE and verifies the health endpoint
5. installs Inno Setup
6. builds the Windows installer
7. silently installs the installer on a Windows runner
8. launches the installed application
9. verifies the installed application health endpoint
10. runs the uninstaller
11. uploads both Windows artifacts

## Runtime

When the packaged application starts it:

1. initializes the local application data directory
2. starts the Waitress web server
3. starts the background expediter worker
4. opens the default browser
5. uses the configured local or shared-network host and port

Default local address:

```text
http://127.0.0.1:5050
```

The Setup page can switch the listener from local-only to shared-network mode.

## User interface

The default interface is a dark manufacturing UI using EZ Fab / WMF blue as the primary accent.

Default theme values:

```text
Accent:          #1F6FBC
Deep accent:     #0B3A75
Background:      #090B0E
Panel:           #11161C
Card:            #171E26
Text:            #F4F7FB
Muted text:      #9BA8B7
```

The interface intentionally uses one theme color family rather than multicolored status buttons. The aging heatmap uses shades of the configured accent blue only.

The Appearance page allows the following colors to be changed without editing code:

- accent
- deep accent
- background
- panel
- card
- text
- muted text

The activity presentation uses compact message-style cards while retaining a production-dashboard layout.

## Dashboard

The dashboard includes:

- Open
- Overdue
- Unassigned
- Stale 7+ days
- Awaiting Recovery
- Recovery Outstanding
- free-text search
- occurrence type filter
- status filter
- due-date prioritization
- latest progress note
- direct progress-note entry from the queue

### Past-due aging heatmap

Past-due work is summarized in a single-theme blue aging heatmap:

- 1-3 days
- 4-7 days
- 8-14 days
- 15-30 days
- 31+ days

Increasing blue intensity represents increasing age. The dashboard does not use a multicolor heatmap.

### Progress notes

Every open row shows its latest progress or note entry.

A user can enter a new progress note directly from the dashboard without opening the occurrence. Progress entries are timestamped in the activity history.

## Universal occurrence tracking

Every occurrence uses the same common workflow record:

- internal case number
- occurrence type
- title
- description
- source
- customer
- supplier
- part number
- revision
- work order / job
- sales order
- purchase order
- department
- work center
- owner name
- owner email
- priority
- status
- next action
- due date
- created date
- closed date
- last activity
- source email link
- attachments
- external-system references
- full timestamped activity history

The internal case number is separate from any external RMA, NCR, ERP, or customer identifier.

## Configurable occurrence types

The Types page can create additional tracked processes without changing Python code.

Each occurrence type can define:

- case-number prefix
- custom fields
- text fields
- textarea fields
- numeric fields
- date fields
- email fields
- URL fields
- checkboxes
- select lists
- required fields
- required closure checklist items

Required custom fields and required checklist items become closure blockers automatically.

## Closure control

Generic closure validation checks:

- owner assignment
- required custom fields
- required checklist items

RMA adds additional closure checks for applicable:

- containment
- corrective action
- financial recovery

A closure override is available when required, and the override is recorded in the activity history.

## RMA identifier model

`RMA Number` is the canonical external RMA identifier inside EZ Expedite.

The internal EZ Expedite case number remains separate.

Example:

```text
EZ Expedite case: RMA-2026-0042
Tracked RMA No.: 78193
```

The RMA importer accepts common identifier aliases including:

- RMA Number
- RMA #
- RMA No.
- RMA No
- RMA
- Quality No.
- Case Number
- Case No.
- Case #

A source system can therefore call the identifier `Quality No.` while EZ Expedite still tracks it internally as the RMA Number.

No source workbook record data is embedded in the repository. Source workbooks are compatibility inputs only.

## RMA workflow

The default RMA workflow is based on the WMF process:

```text
Intake
  -> Product Returned to WMF
  -> RMA Review
  -> Product Returned to Customer
  -> Complete
```

Each stage has a primary department, required data-entry fields, validation rules, routing, and Microsoft 365 notification behavior.

### Stage 1 - Intake

Primary department:

```text
Customer Service
```

Required workflow data includes:

- RMA Number
- Defect Type
- CSR Name
- PO #
- Customer Name
- Contact Name
- Contact #
- Notes

After completion, the RMA advances to Product Returned to WMF.

### Stage 2 - Product Returned to WMF

Primary department:

```text
Shipping
```

Required workflow data includes:

- Received from Customer: YES / NO
- Receive Date
- RMA hold-area confirmation

The stage cannot advance until the customer product has been received and hold-area placement is confirmed.

### Stage 3 - RMA Review

Primary department:

```text
Quality
```

Required workflow data includes:

- Product Reviewed
- Work Order Required: YES / NO
- Work Order Issued: YES / NO when required
- Work Order # when required

After validation, the RMA advances to Product Returned to Customer.

### Stage 4 - Product Returned to Customer

Primary department:

```text
Shipping
```

Required workflow data includes:

- Final Quality Inspection: PASS / FAIL
- Approved to Ship: YES / NO
- Ready to Ship: YES / NO
- Shipment to Customer confirmation
- Return shipment date

A failed final quality inspection routes the RMA back to RMA Review.

### Stage 5 - Complete

The completed workflow moves the occurrence to `READY TO CLOSE`, after which the normal closure controls still apply.

## RMA delegate routing

Each RMA primary department can have up to two configured delegates:

- Customer Service Primary 1
- Customer Service Primary 2
- Shipping Primary 1
- Shipping Primary 2
- Quality Primary 1
- Quality Primary 2

Both configured delegates for the active stage receive the Action Required notification.

Either primary delegate may complete the active stage.

The signed-in Microsoft 365 identity is checked against the configured primary delegate email addresses before a user can advance the RMA stage.

## Read-only RMA CC recipients

The RMA Workflow settings page also supports read-only CC recipient lists for:

- Quality
- Operations
- Customer Service
- Design

CC recipients receive workflow visibility notifications but are not authorized to complete the current stage unless they are also configured as one of the active stage's primary delegates.

Primary notification heading:

```text
RMA - ACTION REQUIRED
```

Read-only CC notification heading:

```text
RMA UPDATE - READ ONLY
```

Routed notification content includes:

- RMA number
- workflow stage
- primary department
- customer
- defect
- PO
- next action
- due date
- direct Open RMA link when a public/shared base URL is configured

The initial Intake stage uses the same routed-notification system as later handoffs.

## RMA stage authorization

In multi-user mode:

- users sign in with Microsoft 365
- the signed-in email identifies the user
- primary delegates can edit and complete the active Action Required stage
- read-only CC users can view the RMA but cannot complete the stage
- workflow actions are recorded in the activity history

The general occurrence record remains available according to the application's current access model, while RMA stage completion is specifically restricted to active delegates.

## RMA financial tracking

RMA-specific financial fields include:

- total rework cost
- scrap cost
- freight cost
- outside-processing cost
- recovery requested
- recovery received
- recovery status
- recovery owner
- credit memo number
- debit memo number

Physical resolution and financial recovery can therefore be tracked independently.

## RMA import compatibility

The dedicated RMA importer supports common manufacturing RMA/NCR export columns including:

- RMA identifier aliases
- Quality No.
- Customer
- Customer NCR #
- Customer PO
- Part Number
- Revision
- Description
- Qty Authorized
- Qty Received
- Qty Returned
- Create Date
- Due Date
- Close Date
- Receive Date
- Department
- Responsible Employee
- Work Center
- Rejection Type
- Reject Type
- Discrepancy
- Containment flags
- Corrective-action flags
- disposition fields
- Total Rework Cost
- RMA comments
- Customer Discrepancy
- Customer Complaint
- Status

Duplicate source header names are handled by preserving the first matching source column.

The source workbook is not the application's schema.

## Automatic expediting

The background expediter runs at a configurable interval, with a minimum configured interval of five minutes.

It checks open occurrences for:

- missing ownership
- due dates
- past-due age
- due items with no next action

### Daily past-due digest

Past-due notifications are grouped by connected owner instead of sending one message per occurrence.

Each recipient receives at most one past-due digest per calendar day.

For RMA occurrences, the digest goes to the active stage's primary delegates.

For other occurrence types, it goes to the occurrence owner email.

Each digest item contains:

- case number
- number of days past due
- occurrence type
- title
- next action
- latest progress note

A digest-notification ledger prevents repeat delivery to the same recipient on the same day.

## Microsoft 365 architecture

EZ Expedite uses Microsoft Graph and MSAL.

There are two separate Microsoft 365 functions.

### Notification account

A configured Microsoft 365 notification account performs Graph actions such as:

- reading recent Outlook inbox messages
- sending Outlook email
- finding Microsoft 365 users
- creating or reusing one-to-one Teams chats
- sending Teams workflow notifications
- sending Teams past-due digests

Notification-account delegated scopes currently requested:

- `User.Read`
- `User.ReadBasic.All`
- `Mail.Read`
- `Mail.Send`
- `Chat.Create`
- `ChatMessage.Send`

Microsoft handles the account sign-in. EZ Expedite does not ask for or store the Microsoft password.

The notification-account token cache is stored locally under the instance directory.

### Multi-user delegate sign-in

Multi-user mode uses Microsoft authorization-code sign-in to identify the person currently using the application.

It requires:

- Microsoft Application Client ID
- tenant
- web-sign-in client secret
- public/shared base URL for the callback when used across the network

The signed-in identity is used for workflow authorization such as determining whether the current user is one of the active RMA primary delegates.

The web sign-in flow currently requests `User.Read` for identity verification.

## Network modes

Setup supports:

### Local only

```text
127.0.0.1
```

Use for a single-machine installation.

### Shared network

```text
0.0.0.0
```

Use when one Windows machine is acting as the EZ Expedite host for multiple users.

A shared deployment should configure:

- a fixed machine/server location
- stable port
- public/shared base URL
- Microsoft redirect URI matching the configured callback
- multi-user sign-in
- appropriate Windows firewall/network access

The application currently uses SQLite, so the recommended shared architecture is one running EZ Expedite instance serving multiple browser users rather than multiple independent copies pointing at the same SQLite file.

## Outlook intake

The Outlook page can:

- show recent inbox messages from the notification account
- create an occurrence from an Outlook message
- choose the occurrence type at creation
- retain the Outlook web link
- prevent duplicate creation from the same Outlook message
- send Outlook email from an occurrence

## Attachments

Occurrences can store local supporting files including:

- photos
- customer documents
- inspection records
- screenshots
- PDFs
- spreadsheets
- correspondence exports

Attachment metadata is stored in SQLite and files are stored beneath the local instance upload directory.

The repository does not contain production attachments.

## ERP and external-system references

Any occurrence can link to external records such as:

- JobBOSS2 jobs
- work orders
- sales orders
- purchase orders
- Epicor records
- Plex records
- SAP objects
- supplier portal tickets
- customer NCRs
- SharePoint documents
- other web applications

Each external reference can store:

- system name
- record/entity type
- external ID
- URL
- note

## Import Anything

The generic importer supports:

- `.xlsx`
- `.xlsm`
- `.csv`

The import workflow lets the user:

1. choose an occurrence type
2. upload a source file
3. inspect detected source columns
4. map source columns to core EZ Expedite fields
5. map source columns to configured custom fields
6. choose an external synchronization key
7. create new occurrences
8. update existing occurrences on later imports

Built-in mappable fields include:

- title
- description
- source
- customer
- supplier
- part number
- revision
- work order
- sales order
- purchase order
- department
- work center
- owner name
- owner email
- priority
- status
- next action
- due date
- created date

This provides a flat-file integration path for ERP and legacy-system exports before a direct API adapter exists.

## ERP connection registry

The ERP / Systems page can register external systems and their intended integration method.

Supported connection descriptions include:

- Excel / CSV flat file
- public API
- custom REST API
- read-only database/report view

The registry stores connection metadata. It does not invent vendor API endpoints or credentials.

## JobBOSS2

JobBOSS2 can currently be used with EZ Expedite through flat-file synchronization:

1. export the required JobBOSS2 data to Excel or CSV
2. map the columns with Import Anything
3. choose a durable JobBOSS2 record ID as the synchronization key
4. re-import later exports to update the same occurrences

Direct JobBOSS2 API integration is not hard-coded because endpoint, authentication, licensing, and permitted resources must come from the specific JobBOSS2 environment.

The same integration architecture can be used for Epicor, Plex, SAP, or another ERP when real API or approved read-only interface information is available.

## Data model

The application uses SQLite.

Major logical areas include:

- settings
- occurrence types
- occurrences
- RMA details
- activities
- occurrence email links
- custom field definitions
- custom field values
- checklist templates
- checklist items
- attachments
- external references
- external connection registry
- individual notification history
- daily digest notification history

RMA-specific fields extend an occurrence rather than replacing the generic occurrence model.

## Source-data isolation

This repository is standalone and does not depend on ForgeQC, MFGForge, PM Tracker, or any other private repository at runtime.

Do not commit:

- customer production data
- RMA production data
- ERP exports
- uploaded evidence
- SQLite databases
- Microsoft token caches
- client secrets
- API tokens
- local environment files
- generated build output

The repository `.gitignore` excludes local application databases, spreadsheets, environment files, build folders, installer output, PyInstaller specifications, and related local runtime artifacts.

Synthetic tests use fabricated data only.

## Developer run

Python is required only for source/development use.

Recommended Python version:

```text
3.12
```

PowerShell:

```powershell
.\run.ps1
```

Command Prompt:

```bat
run.bat
```

## Build standalone Windows EXE

```powershell
.\build_windows.ps1
```

Output:

```text
dist\EZ_Expedite.exe
```

## Build Windows installer locally

Requirements:

- Python
- Inno Setup 6

Run:

```powershell
.\build_installer.ps1
```

Output:

```text
dist-installer\EZ_Expedite_Setup_0.1.1.exe
```

The installer recipient does not need Python or Inno Setup.

## Verification

Basic smoke test:

```powershell
python smoke_test.py
```

Full functional validation:

```powershell
python pre_release_test.py
```

Current automated coverage includes:

- database initialization and migration
- first-run setup gate
- local and multi-user configuration paths
- universal occurrence types
- custom required fields
- closure checklists
- occurrence creation
- RMA-number alias compatibility
- duplicate-safe spreadsheet synchronization
- generic spreadsheet synchronization
- external-system synchronization keys
- past-due digest suppression
- primary RMA delegate routing
- two-primary-delegate support
- read-only CC routing
- direct RMA notification links
- core web routes
- standalone EXE launch test
- Windows installer install/launch/uninstall test

## Current integration boundary

The application is complete enough to run without another repository or Python installation on the target machine.

Items that remain environment-specific rather than hard-coded are:

- Microsoft Entra application registration
- tenant consent and allowed Graph permissions
- notification account selection
- web-sign-in client secret
- shared/public base URL
- local network/firewall configuration
- actual RMA delegate and CC email addresses
- direct ERP API endpoint and authentication information

Those values belong to the deployment environment and are intentionally not embedded in the repository.

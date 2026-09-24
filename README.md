# EZ Expedite

**Own it. Move it. Close it.**

EZ Expedite is a standalone occurrence-expediting application for anything that can get lost between "somebody needs to handle this" and actual closure.

RMA is the first configured occurrence type because that is the original use case. The core engine is intentionally generic. A shop can use the same application for:

- RMAs
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
- or any other occurrence that needs an owner, next action, due date, escalation, history and verified closure

The universal workflow is:

**Create -> Assign -> Define next action -> Expedite -> Escalate -> Document -> Verify -> Close**

## Windows users do not need Python

The intended production distribution is the standalone Windows executable:

```text
EZ_Expedite.exe
```

GitHub Actions builds it with PyInstaller. The packaged EXE contains the Python runtime and application dependencies, so the end user's machine does **not** need Python installed.

The Windows build is uploaded as the `EZ_Expedite-Windows` artifact from the `windows-build` GitHub Actions workflow.

When the packaged app runs it:

1. starts EZ Expedite locally,
2. opens the default browser to `http://127.0.0.1:5050`,
3. starts the background expediter,
4. stores the local database, uploads and Microsoft token cache under:

```text
%LOCALAPPDATA%\EZ_Expedite\instance
```

Close the EZ Expedite console window to stop the local application.

## What works now

### Universal occurrence tracking

Every occurrence has a common operational backbone:

- case number
- occurrence type
- title and description
- source
- customer
- supplier
- part and revision
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
- created and closed dates
- last activity
- source email linkage
- full timestamped activity history

### Configurable occurrence types

Use **Types** to create a new process without changing Python code.

Each occurrence type can define:

- its own case-number prefix
- custom fields
- text fields
- long-text fields
- numbers
- dates
- email addresses
- URLs
- checkboxes
- selectable values
- required fields
- closure checklist items

Required custom fields and required checklist items become closure controls automatically.

### Actual expediting

EZ Expedite is not just a database.

The expeditor checks open occurrences for:

- missing ownership
- approaching due dates
- overdue due dates
- items with due dates but no next action

When Microsoft 365 is connected, the background process can send Teams reminders to the current owner.

Default reminder points are:

- one day before due
- due today
- one day overdue
- three days overdue
- seven days overdue
- every seven days after that

A notification ledger prevents the same due-date escalation from being sent repeatedly.

The dashboard also exposes:

- open occurrences
- overdue occurrences
- unassigned occurrences
- stale items
- RMA recovery exposure
- type/status filters
- free-text search across case numbers, RMA numbers, customers, parts, owners and descriptions

### Closure control

The app does not treat "somebody changed the status" as proof that the work is finished.

Generic closure controls include:

- an assigned owner
- required custom fields
- required checklist items

RMA adds additional checks for applicable containment, corrective action and financial recovery.

An authorized user can still override blockers, but the override is recorded in the activity history.

### Attachments

Any occurrence can keep local supporting files such as:

- photos
- customer documents
- inspection records
- screenshots
- PDFs
- spreadsheets
- correspondence exports

Files are stored locally with the app data and are not committed to Git.

### ERP and external-system references

Any occurrence can link directly to records in another system.

Examples:

- JobBOSS2 job
- sales order
- purchase order
- Epicor record
- Plex record
- SAP object
- supplier portal ticket
- customer NCR
- SharePoint document
- another web application

An external reference can store the system, record type, external ID, link and note.

## Import Anything

The **Import Anything** workflow accepts:

- `.xlsx`
- `.xlsm`
- `.csv`

The user chooses the target occurrence type and maps source columns into EZ Expedite fields.

Built-in mappable fields include ownership, due dates, customer, supplier, part, revision, job/work order, sales order, purchase order, department, work center, status, priority, next action and description.

Custom fields created for that occurrence type also become import targets.

If the source file has a durable record ID, select it as the **synchronization key**. EZ Expedite then updates the same occurrence on later imports instead of creating duplicates.

This makes flat-file ERP integration usable immediately even before a direct API connection is available.

## RMA mode

The dedicated RMA import is format-compatible with common manufacturing RMA/NCR exports. RMA Number is the application's canonical tracked identifier. Source columns such as RMA Number, RMA #, RMA No., Quality No., Case Number, Case No., or Case # can be accepted as identifier aliases. No source workbook record values are embedded in this repository. Supported columns include:

- Quality No.
- Customer
- Customer NCR #
- Part Number
- Revision
- Description
- Qty Authorized
- Qty Received
- Qty Returned
- Create Date
- QC Due Date
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
- Disposition fields
- Total Rework Cost
- Sales Comment (RMA)
- Customer Discrepancy
- Customer Complaint
- Status

`RMA Number` is the synchronization key inside EZ Expedite. If a source export calls that identifier `Quality No.`, it is accepted as an alias. A separate source Quality No. can also be retained when available.

RMA records also track:

- rework cost
- scrap cost
- freight cost
- outside-processing cost
- recovery requested
- recovery received
- recovery status
- recovery owner
- credit memo
- debit memo

The quality problem can therefore be physically resolved without allowing the financial recovery item to disappear.

## Outlook and Teams

EZ Expedite uses Microsoft Graph delegated permissions through MSAL.

Microsoft performs the sign-in. EZ Expedite never asks for or stores the user's Microsoft password.

The first-run setup asks for the Microsoft Entra Application (client) ID and tenant, then provides one Microsoft sign-in for Outlook and Teams.

Current Microsoft functionality:

- review recent Outlook inbox messages
- turn any Outlook message into any configured occurrence type
- retain the Outlook web link on the occurrence
- send an Outlook email from an occurrence
- send a one-to-one Teams assignment message
- send automatic Teams due/overdue reminders

Requested delegated permissions:

- `User.Read`
- `User.ReadBasic.All`
- `Mail.Read`
- `Mail.Send`
- `Chat.Create`
- `ChatMessage.Send`

Microsoft tokens remain local under the application instance directory.

## JobBOSS2 and other ERP systems

Yes, EZ Expedite can be connected to ERP systems.

### JobBOSS2

ECI publicly states that JobBOSS2 supports integrations through both API and flat file, and that JobBOSS2 has a public API for custom integrations:

https://www.ecisolutions.com/products/jobboss2/features/

That gives EZ Expedite two legitimate integration paths:

1. **Flat file now**
   - export a JobBOSS2 report to Excel/CSV
   - map it with Import Anything
   - choose the JobBOSS2 record ID as the synchronization key
   - re-import later exports to update the same occurrences

2. **Direct API**
   - obtain the actual JobBOSS2 API base URL, authentication requirements and permitted resources for the customer's JobBOSS2 environment
   - register the connection under ERP / Systems
   - build the JobBOSS2 adapter against those real vendor-supplied endpoints

The repo intentionally does **not** invent JobBOSS2 endpoint names, credentials or undocumented database access.

### Other ERPs

The same architecture can support systems such as Epicor, Plex, SAP or other manufacturing ERPs through whichever interface that installation actually exposes:

- REST API
- OData/API service
- approved read-only database/report view
- scheduled Excel/CSV export
- vendor middleware

ERP data remains an external source. EZ Expedite owns the occurrence workflow, expediting history, communication history and closure controls.

## Standalone rule

EZ Expedite does **not** import ForgeQC, MFGForge, PM Tracker or any other private project at runtime.

Reusable patterns may be replicated into this repository, but the application must run independently for a company that has access only to EZ Expedite.

Do not commit:

- real customer data
- real RMA data
- ERP exports
- uploaded evidence
- SQLite databases
- Microsoft token caches
- credentials
- API tokens
- local `.env` files

These are excluded by `.gitignore` where applicable.

## Developer run

Python is only required for source/development use.

Recommended: Python 3.12.

```powershell
.\run.ps1
```

or:

```bat
run.bat
```

Then open:

```text
http://127.0.0.1:5050
```

The source launcher creates a virtual environment, installs requirements, runs the smoke test and starts the app.

## Build the Windows EXE locally

A developer machine with Python can build the distributable executable with:

```powershell
.\build_windows.ps1
```

Output:

```text
dist\EZ_Expedite.exe
```

The recipient of that EXE does not need Python.

## Verification

```powershell
python smoke_test.py
```

The smoke test currently exercises:

- database initialization
- first-run setup gate
- universal occurrence types
- custom required fields
- closure checklists
- occurrence creation
- duplicate-safe due-date notifications
- universal spreadsheet synchronization
- ERP/external synchronization keys
- core web routes

GitHub Actions runs smoke verification on pushes and pull requests. A separate Windows workflow builds and uploads the standalone executable.

# EZ RMA Local

A static HTML/CSS/JavaScript RMA tracker based on EZ Expedite's staged manufacturing RMA process. **GitHub Pages hosts only source code, never RMA data.** The browser stores cases and progress history privately in IndexedDB on each device.

## Use
- Open the hosted page, choose **New RMA**, fill out fields, save, and move through validated workflow stages.
- Stages: Intake, product returned to company, Quality review, return to customer, complete, then verified closure.
- A failed final inspection returns to Quality. Closure checks include ownership, disposition, required containment, corrective actions and recovery or waiver.
- Search and filter the dashboard by case/customer/part/owner, or find overdue/stale cases.
- **Backup JSON** preserves complete history. **Export CSV** creates a simple spreadsheet-compatible report. **Import** supports JSON backups and compatible CSV exports.
- Use a JSON backup and import it in another device to copy the records. **There is no cross-device synchronization.**
- After visiting the page online, a service worker caches app assets for offline use on supported browsers. The static HTML source may also be opened locally, though installation/offline caching is best through HTTPS.
- **ChatGPT Assistant** creates a reviewable local prompt. Users opt into sharing individual case fields, copy the prompt and open ChatGPT in another tab. No direct sign-in, data connection, API keys, or automatic transmission occurs.

## Security and limitations
- No data is sent to GitHub or any external provider by the application. No Outlook or Microsoft sign-in. No server-side storage.
- Data is stored locally in each browser profile; clearing browser storage, changing profiles, using private mode, or device damage can destroy it. Back up routinely.
- On shared/public devices or shared browser profiles, local data can be read by other users of that profile. This version does **not** enforce user identities, departmental permissions or encryption at rest.
- A case opened in another browser/device is independent until records are manually imported.
- Do not use the ChatGPT assistant option for proprietary or personal data unless explicitly approved by your organization. Review the complete prompt before pasting it.
- No automatic attachment hosting, Teams notifications, or live sync; this is an offline/local subset, not a multi-user server replacement.
- CSV import is designed for common RMA-export headers. Export large XLSX files as CSV before importing. JSON is the recommended complete backup format.
- Source licensing is inherited from EZ Expedite GPL-3.0.

## Files
index.html is the complete application and interface. manifest.webmanifest, icon.svg and sw.js add optional installable/offline behavior.

## Publishing
GitHub Pages can serve these files from any Pages-enabled docs/root folder, e.g. from BEAN/docs/rma-local/ . The site must be deployed from the correct source branch/directory for its URL to be live.

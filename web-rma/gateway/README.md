# EZ RMA in-app assistant gateway

This optional Cloudflare Worker lets the static GitHub Pages RMA tracker talk to OpenAI without putting an OpenAI API key in HTML, the public repository, or on an iPad.

## Deployment

Requires your own Cloudflare Workers account and OpenAI API project with billing enabled. An existing ChatGPT subscription does not pay for API usage.

1. Open a terminal in the web-rma/gateway folder and run: npm install --global wrangler
2. Run: wrangler login
3. Run: wrangler secret put OPENAI_API_KEY and supply the OpenAI API key.
4. Generate a random access code at least 32 characters long, e.g. with openssl rand -hex 32. Run: wrangler secret put WORKER_ACCESS_TOKEN and supply that code.
5. Run: wrangler deploy. Wrangler will provide a URL such as https://ez-rma-assistant.YOUR-SUBDOMAIN.workers.dev.
6. On the iPad, open the RMA site, then Assistant. Enter the gateway URL and the separate access code. The app automatically appends /chat to a bare Worker URL.

The gateway URL is stored locally in that browser. The access code lives only in page memory and must be reentered after a full page reload. Do not paste the OpenAI API key into the RMA page.

## iPad-only setup using Cloudflare's website

The users of the RMA tracker never install anything. If the administrator also wants to do deployment from an iPad browser, use the Cloudflare Workers dashboard instead of the terminal:

1. Sign into the Cloudflare dashboard in Safari and open Workers & Pages. Create a new Worker named ez-rma-assistant.
2. Open Edit code. Copy the entire contents of src/index.mjs from this repository into the Worker editor and deploy.
3. In the Worker's Variables and Secrets settings, add two encrypted secrets named OPENAI_API_KEY and WORKER_ACCESS_TOKEN. Use your own API key and a generated random access code of at least 32 characters.
4. Optionally add ordinary variables OPENAI_MODEL = gpt-5.4-mini and ALLOWED_ORIGIN = https://danieloculus0-bot.github.io.
5. Configure Cloudflare rate limiting for production access. The worker code checks the optional ASSISTANT_RATE binding when present, but an ordinary dashboard deployment without that binding will not enforce its limiter.
6. Paste the deployed Worker URL and access code into the in-app Assistant form.

Only the administrative setup requires a Cloudflare login. Regular iPad users need no Cloudflare or OpenAI login and no API key.

## Behavior

- RMA records remain in browser IndexedDB. The gateway stores no record or chat transcript.
- The user sees and selects exactly what to include with each request. The submitted question and only the selected data are sent to the gateway and then OpenAI.
- OpenAI requests include store:false, bounded history and output. Review your provider terms before sending real company or customer data.
- Assistant responses are plain text and cannot automatically modify an RMA. The user may copy a response into the record manually.
- GitHub only hosts application source. No case data is written to GitHub.
- The manual Copy & Open ChatGPT option remains available without the gateway.
- AI requires connectivity; the RMA tracker itself remains usable offline.

## Security and costs

Never publish OPENAI_API_KEY or WORKER_ACCESS_TOKEN. Rotating WORKER_ACCESS_TOKEN revokes existing device access. Only the configured GitHub Pages origin receives CORS headers. Requests also need the shared access code. The Cloudflare rate limiter is approximate, not a hard spending cap. Set API billing limits/alerts and monitor usage. For multi-user enterprise use, replace the shared access code with individual authentication, auditing, and stronger cost controls.

## Tests

From this folder run: node --test gateway.test.mjs

Gateway deployment is a separate step from publishing GitHub Pages and requires your Cloudflare account and the two secrets. Until deployment, the in-app assistant will show a setup requirement rather than pretending to be connected.

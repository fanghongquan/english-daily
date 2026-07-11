# English Daily Reliability and Security Design

## Goal

Make the unattended daily publishing workflow reliable, make failures visible, and protect paid or private SCF operations without removing public article reading or browser speech.

## Scope

This change covers:

- durable generation and Feishu delivery state;
- strict Feishu response handling;
- article schema and content validation;
- safe HTML/JavaScript rendering;
- authenticated SCF requests for TTS, translation, Maimemo, and COS sync;
- origin restrictions, request limits, and lightweight rate limiting;
- reproducible dependencies and safer GitHub Actions execution;
- automated tests for all new behavior.

It does not migrate the application to another hosting platform, add user accounts, or redesign the reading interface.

## Architecture

The existing static GitHub Pages site remains public. Reading, quizzes, history, theme controls, and browser-native speech require no authentication.

Paid or private operations remain in Tencent SCF. The user enters a personal access code the first time a protected feature is used. The browser stores it in `localStorage`; it is never embedded in generated pages or committed to GitHub. SCF stores the matching value in `APP_ACCESS_KEY`.

Each protected request includes:

- `X-App-Timestamp`: Unix seconds;
- `X-App-Nonce`: a browser-generated random value;
- `X-App-Signature`: lowercase HMAC-SHA256 hex digest;
- canonical input: `timestamp + "\n" + nonce + "\n" + SHA256(raw_request_body)`.

SCF rejects missing signatures, timestamps outside a five-minute window, malformed payloads, and oversized bodies. The configured `ALLOW_ORIGIN` must match the incoming `Origin` header. Preflight requests remain unsigned. A small per-process token bucket limits accidental bursts; the deployment guide also requires Tencent API Gateway or function URL throttling because in-process limits cannot coordinate across instances.

## Daily Workflow

The workflow becomes an explicit state machine:

1. Generate today's article if it does not exist.
2. Validate its schema, date, paragraph structure, quiz answers, approximate word count, and allowed keyword markup.
3. Build the page using safely serialized JSON and sanitized paragraph markup.
4. Push the Feishu card.
5. Only after Feishu returns HTTP success and business `code == 0`, write `state/YYYY-MM-DD.json` with `feishu_pushed: true`.

An existing state file skips duplicate delivery. Merely having an HTML page never counts as successful delivery. If generation fails, the job fails so a later scheduled run can retry; it does not silently send an old article.

State is committed with `articles/` and `docs/`. GitHub Actions uses a concurrency group so delayed schedules cannot run simultaneously.

## Validation and Rendering

A standard-library validator is preferred to avoid adding a large runtime dependency. It produces actionable error messages and validates:

- ISO date equal to the requested date;
- non-empty title, Chinese title, introduction, and level;
- 7–12 paragraphs, each with non-empty English and Chinese text;
- a configurable reasonable English word-count range;
- 3–4 questions when present, each with four options and an answer from 0 through 3;
- paragraph HTML restricted to `span.kw` elements with `data-ipa` and `data-def` attributes.

The sanitizer parses paragraph fragments with `html.parser`, preserves only approved keyword spans, and escapes all other markup. Chinese translations are rendered as text. Embedded article JSON escapes `<`, `>`, `&`, and Unicode line separators so content cannot terminate the script element. `TTS_API_URL` is serialized with `json.dumps`, not interpolated into a quoted JavaScript string.

Generated pages include a restrictive Content Security Policy compatible with the inline self-contained page.

## Frontend Access-Code Flow

Protected feature calls go through one request helper. If no access code is stored, the helper prompts once. It signs the exact JSON body using Web Crypto and sends the authentication headers.

On HTTP 401 or 403, the stored code is removed and the user receives a clear message. A small settings action allows clearing or replacing the code. Browser speech remains the fallback when authenticated cloud TTS is unavailable.

## Error Handling

- Feishu transport failures, invalid JSON, or nonzero business codes raise errors.
- Validation errors stop generation/build and show the failing field.
- SCF returns generic public errors and logs detailed internal exceptions; provider credentials and upstream response bodies are not returned to browsers.
- Git operations do not suppress pull/rebase failures.
- Failed daily runs remain red in Actions and are retried by later schedules.

## CI and Dependencies

Add a pinned `requirements.txt` for both supported AI clients. CI installs it without `|| true`, runs unit tests and `compileall`, then executes the production job. Add workflow concurrency and least-privilege job permissions. Generated state is included in the commit.

## Testing

Tests use `unittest`, temporary directories, and dependency injection or local HTTP test servers where practical. Coverage includes:

- Feishu success, business failure, malformed responses, and transport failure;
- first delivery, duplicate delivery, and retry after a failed push;
- no fallback to stale content after generation failure;
- valid and invalid article schemas;
- malicious `</script>` and HTML event attributes;
- SCF valid signature, bad signature, expired timestamp, disallowed origin, oversized body, and rate limit;
- frontend presence of the access-code signing flow;
- workflow concurrency, dependency installation, tests, and state commits.

Every behavior change follows a failing-test-first cycle.

## Deployment

Deployment documentation will require:

- a high-entropy `APP_ACCESS_KEY` in SCF environment variables;
- exact `ALLOW_ORIGIN`, for example `https://fanghongquan.github.io`;
- gateway/function URL throttling;
- rotation instructions for the access code;
- GitHub Secrets and Variables already used by the daily workflow.

Existing public pages remain readable throughout deployment. Protected functions begin requiring the access code once the updated SCF is deployed.

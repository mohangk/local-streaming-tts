# Readvox Architecture

Readvox is a local-first FastAPI app for turning text, URLs, reviewed drafts, and future input sources into streamed text-to-speech audio. It should stay small enough to run as one localhost service, but its internals should be split by responsibility so new workflows do not turn into one large route file, one storage method pile, or one monolithic JavaScript file.

## Core Principles

- Keep the app local-first: one FastAPI process, one SQLite database, one data directory, and optional private HTTPS proxy access for trusted devices.
- Keep external paid services behind provider interfaces with deterministic fake providers for tests and local UI checks.
- Treat stored user data as durable. Do not remove stored images, generated audio, cached smoke-test artifacts, or local data files unless the user explicitly asks or an app deletion flow is being exercised.
- Preserve the behavior distinction between client state and backend persistence. Clearing frontend state must not imply deleting backend data unless the user invokes a deletion flow.
- Prefer focused vertical slices: provider/config, storage, route/API, frontend state/UI, then docs and tests.
- Add tests at the layer that owns the behavior. Storage tests cover persistence and cleanup; API tests cover contracts and failure status; frontend static tests cover DOM wiring and browser state transitions.

## Runtime Shape

FastAPI serves both the API and static frontend. The default deployment binds plain HTTP to `127.0.0.1:8001`; remote access belongs behind a private HTTPS proxy.

Durable data is split between SQLite and the filesystem:

- SQLite stores generations, text segments, audio segment metadata, provider settings, playback progress, workflow drafts, and source-asset metadata.
- Audio files are cached under `data/audio/<generation_id>/`.
- OCR images are stored under `data/images/<ocr_draft_id>/<ocr_draft_image_id>/`.

The database owns metadata relationships. The filesystem owns byte storage. Any feature that creates filesystem data must define the matching database cleanup path and test it.

## Backend Boundaries

`src/tts_app/api.py` should remain the app factory and shared top-level routes. Feature-specific route groups belong under `src/tts_app/routes/` once they have more than trivial behavior. Shared route helpers, such as generation scheduling, belong in small helper modules rather than being copied between route files.

Provider-specific behavior belongs behind interfaces:

- TTS providers live under `src/tts_app/providers/`.
- OCR providers live under `src/tts_app/ocr_providers/`.
- Fake providers must remain deterministic and should be the default for tests.
- Qwen credentials come from `DASHSCOPE_API_KEY` or `QWEN_API_KEY`.

Generation logic should call provider interfaces, not provider implementations. Route handlers should create validated requests and delegate durable work to storage and generation services.

## Storage And Migrations

`src/tts_app/storage.py` owns schema creation, one-time migrations, and persistence operations. Schema changes should be forward migrations that move existing data into the new shape and then remove obsolete schema paths. Do not leave long-lived runtime branches for old schemas after the migration is complete.

Storage methods should expose behavior-level operations, not raw table manipulation. Examples:

- create a generation with text segments
- record an audio segment
- create or append workflow draft source assets
- rebuild a draft's reviewed source text from child assets when appropriate
- link a workflow draft to a generation
- delete unlinked drafts
- force-delete linked drafts during generation deletion

As workflows grow, split storage internals into helper modules or mixins while preserving the public `Storage` API used by routes and tests. Workflow-specific storage tests, such as `tests/test_ocr_storage.py`, are the acceptance surface for storage splits.

## Drafts And Linked Artifacts

Some workflows need intermediate user review before they become a durable audio generation. Model those workflows as drafts that are separate from generations until the user explicitly creates audio. This separation is intentional:

- A draft is a reviewable source document assembled from one or more user-provided or provider-derived assets.
- The draft stores editable reviewed text that becomes the source of truth for audio generation.
- Child asset rows preserve raw provider output, source file metadata, retry state, and diagnostics.
- Creating audio stores the reviewed text as generation `full_text`, records workflow-specific settings, and links the draft to the generation.

Linked drafts should disappear from active draft-picking surfaces because their user-facing recovery path is History. They should not be deleted by frontend state reset. Linked draft and stored source-asset cleanup belongs to generation deletion from History.

OCR is the current example of this model:

- OCR drafts are assembled from ordered source images.
- `ocr_drafts.combined_text` is the reviewed source of truth for audio generation.
- `ocr_draft_images.extracted_text` preserves raw per-image OCR output for retry, delete, and diagnostics.
- Creating image audio sets `source_type = image` and links the draft to the generation.
- For Chinese OCR, preserve only visible Chinese text and visible pinyin. Do not generate missing pinyin, transliterate Chinese characters into pinyin, translate, summarize, or infer text that is not visible in the image.

## Frontend Direction

The frontend should stay framework-free, mobile-first, and plain JavaScript, but it should not grow as one giant `app.js`. New work should continue moving code into feature modules with explicit imports and narrow responsibilities.

Current module direction:

- `app.js`: app bootstrap, top-level navigation, shared generation/playback orchestration.
- `history.js`: History rendering, search, deletion, and open actions delegated to app playback; failed status and escaped stored diagnostics leave partial audio accessible.
- `dom.js`: DOM element lookups.
- `state.js`: shared browser state.
- `utils.js`: small reusable helpers such as escaping and busy-button handling.
- `ocr.js`: Image OCR and Draft Images workflow.

Future modularization should split `app.js` further when touching related behavior:

- `playback.js`: audio queue, segment playback, progress persistence, autoplay/manual playback, scroll-follow.
- `generation-form.js`: Text/URL/Image mode switching, form payload creation, and submit state.
- `voice-controls.js`: language, voice, speed, preference, and sample playback behavior.
- `api-client.js`: small fetch helpers for JSON, 204 responses, errors, and button-wrapped actions.

Do this incrementally. Do not pause feature work for a large frontend rewrite. When a change touches a coherent area in `app.js`, extract that area with focused static tests and keep public behavior unchanged.

Frontend state rules:

- UI reset helpers should clear local state and DOM affordances only.
- Backend deletion must go through explicit API calls and confirmation where user data is removed.
- Busy-button helpers must leave controls in the correct final enabled/disabled state after async wrappers restore button state.
- Browser asset version query strings should change when HTML/CSS/JS compatibility changes.
- SQLite-backed playback telemetry should stay local-first and content-free. Store diagnostic generation playback events in SQLite, delete them with the generation, and do not collect article text, OCR text, extracted URL content, generated audio bytes, or provider raw responses.

## Testing Approach

Use deterministic tests by default. Paid provider calls do not belong in normal test runs. Before marking an implementation feature complete, run the opt-in live provider integration canary once to verify the Readvox API-to-provider boundary with one short sample and one supported voice.

Run before claiming work is complete:

```bash
.venv/bin/pytest -q
npm run check:js
npm run lint:js
npm run test:js
```

Run the live canary with local credentials after the deterministic suite passes:

```bash
set -a
source .envrc.local
set +a
RUN_QWEN_INTEGRATION=1 .venv/bin/pytest -m live_provider -q
```

The live canary should remain deliberately narrow: one API request, one documented model/voice combination, a temporary data directory, a non-empty audio assertion, and a check that sampling does not create a History entry. It is an integration health check, not an exhaustive provider voice test.

Prefer focused tests first:

- storage changes: `tests/test_storage.py` or `tests/test_ocr_storage.py`
- API changes: route-specific API tests
- provider behavior: fake and provider contract tests
- frontend wiring: `tests/test_frontend_static.py`
- docs/setup changes: `tests/test_docs.py`

Then run the full verification set.

## Future Feature Pattern

For new workflows, use this order unless there is a concrete reason not to:

1. Configuration and provider boundary, with a fake implementation.
2. Storage schema and migration, with cleanup semantics.
3. API routes and shared route helpers.
4. Frontend module and state transitions.
5. Documentation and setup examples.
6. Full verification and a logical commit series.

Commit history should tell the same story as the architecture: tooling/config, provider boundary, storage, API, frontend, then documentation cleanup when needed. Fold review-fix commits into the relevant layer before merging when practical.

## Architecture Review

After every non-trivial change, run an architecture review against this document before merging or pushing to `main`. The review should look for boundary drift, accidental data-loss paths, provider calls leaking outside adapters, frontend monolith growth, missing focused tests, and commit history that hides architectural decisions.

Use `docs/architecture-review-subagent.md` as the review prompt. Treat findings as code review comments: fix high-risk issues before merge, document intentional exceptions, and keep the review focused on project architecture rather than style preferences.

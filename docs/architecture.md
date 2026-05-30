# Readvox Architecture

Readvox is a local-first FastAPI app for turning text, URLs, and reviewed OCR drafts into streamed text-to-speech audio. It should stay small enough to run as one localhost service, but its internals should be split by responsibility so new input workflows do not turn into one large route file, one storage method pile, or one monolithic JavaScript file.

## Core Principles

- Keep the app local-first: one FastAPI process, one SQLite database, one data directory, and optional private HTTPS proxy access for trusted devices.
- Keep external paid services behind provider interfaces with deterministic fake providers for tests and local UI checks.
- Treat stored user data as durable. Do not remove stored images, generated audio, cached smoke-test artifacts, or local data files unless the user explicitly asks or an app deletion flow is being exercised.
- Preserve the behavior distinction between client state and backend persistence. Clearing a frontend draft state must not imply deleting backend OCR data unless the user invokes a deletion flow.
- Prefer focused vertical slices: provider/config, storage, route/API, frontend state/UI, then docs and tests.
- Add tests at the layer that owns the behavior. Storage tests cover persistence and cleanup; API tests cover contracts and failure status; frontend static tests cover DOM wiring and browser state transitions.

## Runtime Shape

FastAPI serves both the API and static frontend. The default deployment binds plain HTTP to `127.0.0.1:8001`; remote access belongs behind a private HTTPS proxy.

Durable data is split between SQLite and the filesystem:

- SQLite stores generations, text segments, audio segment metadata, provider settings, playback progress, OCR drafts, and OCR image metadata.
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
- create or append OCR draft images
- rebuild OCR draft combined text
- link an OCR draft to a generation
- delete unlinked OCR drafts
- force-delete OCR drafts during generation deletion

As OCR and future workflows grow, split storage internals into helper modules or mixins while preserving the public `Storage` API used by routes and tests. `tests/test_ocr_storage.py` is the acceptance surface for an OCR storage split.

## OCR Workflow

OCR drafts are separate from generations until the user creates audio. This separation is intentional:

- An OCR draft is a reviewable document assembled from ordered source images.
- `ocr_drafts.combined_text` is the editable source of truth for audio generation.
- `ocr_draft_images.extracted_text` preserves raw per-image OCR output for retry, delete, and diagnostics.
- Creating audio sets `source_type = image`, stores the reviewed text as generation `full_text`, and links the draft to the generation.

Linked OCR drafts should disappear from Generate > Image and Generate > Draft Images because their user-facing recovery path is History. They should not be deleted by frontend state reset. Linked OCR draft and stored image cleanup belongs to image generation deletion from History.

For Chinese OCR, preserve only visible Chinese text and visible pinyin. Do not generate missing pinyin, transliterate Chinese characters into pinyin, translate, summarize, or infer text that is not visible in the image.

## Frontend Direction

The frontend should stay framework-free, mobile-first, and plain JavaScript, but it should not grow as one giant `app.js`. New work should continue moving code into feature modules with explicit imports and narrow responsibilities.

Current module direction:

- `app.js`: app bootstrap, top-level navigation, shared generation/playback/history orchestration.
- `dom.js`: DOM element lookups.
- `state.js`: shared browser state.
- `utils.js`: small reusable helpers such as escaping and busy-button handling.
- `ocr.js`: Image OCR and Draft Images workflow.

Future modularization should split `app.js` further when touching related behavior:

- `history.js`: history list rendering, deletion, and history click actions.
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

## Testing Approach

Use deterministic tests by default. Paid provider calls do not belong in normal test runs.

Run before claiming work is complete:

```bash
.venv/bin/pytest -q
npm run check:js
npm run lint:js
```

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

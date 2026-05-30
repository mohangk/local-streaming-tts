# OCR Storage Refactor Follow-Up

## Goal

Split OCR draft storage internals out of the main `Storage` class after the API and frontend module refactors have settled.

## Proposed Direction

- Preserve the public `Storage` API used by routes and tests.
- Move OCR-specific SQL helpers and draft/image methods into a dedicated helper or mixin.
- Keep schema initialization behavior unchanged, including OCR migration and incompatible-table reset logic.
- Keep `tests/test_ocr_storage.py` as the acceptance surface for the storage split.

## Non-Goals

- Do not change OCR table schemas.
- Do not change endpoint behavior.
- Do not change generation/audio storage behavior.

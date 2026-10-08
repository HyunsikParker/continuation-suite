# Changelog

## 1.0.1 - 2026-10-08

- Fail `run_all.sh` when `TOKENIZER_DIR` or `TEMPLATE` is missing instead of silently omitting template renders.
- Count missing oracle inputs reported as `SKIP` as failures.
- Record the effective chat-template SHA-256 in every render row.
- Add known model, server, sampling and history provenance to the archived Gemma 4 12B replay results.

Measured case outcomes, marker sets and replay counts are unchanged from v1.0.0.

## 1.0.0 - 2026-10-07

- Initial release of the continuation test suite and saved paper results.

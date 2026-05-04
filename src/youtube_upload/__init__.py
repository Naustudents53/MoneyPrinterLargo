"""
YouTube upload helpers extracted from the legacy monolithic YouTubeUploader.

Public surface (used by `classes.YouTubeUploader` facade and by tests):

- `selectors`        — fallback-chained Selenium selectors for Studio.
- `status_markers`   — i18n-aware classification of YT Studio listing rows.
- `failure_capture`  — screenshot + page source dump on upload failure.
- `upload_config`    — config getters for upload-related timeouts.
- `browser_session`  — Firefox lifecycle (clone profile, launch, cleanup).
- `listing_poller`   — two-tab polling + URL resolution against Studio.
- `thumbnail_uploader` — thumbnail upload with retry + visual verification.
- `upload_flow`      — orchestrator that composes the pieces above.
- `backend`          — pluggable UploadBackend interface (Selenium / Data API).
"""

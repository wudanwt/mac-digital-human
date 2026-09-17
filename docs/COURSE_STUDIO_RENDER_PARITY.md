# Course Studio render parity

- Course setup uses the composite `/api/saas/digital-humans` view so the picker can show the lecturer portrait, bound voice, readiness state, and reference-audio preview.
- The layout studio previews the lecturer with `object-position: center bottom`.
- The SaaS worker rewrites only the avatar PiP pad stage from vertical centering to bottom alignment before FFmpeg execution. PPT window centering is intentionally unchanged.
- `pip_box` remains the single normalized source of truth for the draggable lecturer window coordinates.

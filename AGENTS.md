# AGENTS.md — places-serper-leads

Instructions for Codex and other agents. Follow repository-specific security, architecture and change-control requirements.


## Mandatory: persist Markdown deliverables in Google Drive (2026-11-11)

Applies to Codex and every coding agent working on VecinoDigital / Localia. Canonical policy: https://drive.google.com/file/d/18Eo3riavCK3AmhtqY7tp-AVqqLWMdAyE/view . Tracking task: https://app.asana.com/1/1220185338283469/project/1220190107410939/task/1220449811980650 .

1. Whenever you create or materially revise a `.md` file as a **requested deliverable, formal evidence, review, report, handoff, decision record or milestone artifact**, retain the repository copy where appropriate AND archive the complete `.md` in the designated Google Drive project folder. This also applies to Markdown deliverables produced outside the repo. Do not upload every incidental README/dependency edit or temporary note unless it is a deliverable.
2. Default Localia evidence folder: https://drive.google.com/drive/folders/13JNQ31_0i6d5ZT4exSgN1-Y3oikAk6fV . Use the existing more specific project folder when applicable; do not create redundant folders or overwrite an existing file without checking version history.
3. Use a descriptive filename, project, UTC or Madrid date, version when relevant, source repository, PR and commit SHA. Preserve original text; do not upload secrets, tokens, passwords, private keys or personal data not required for the deliverable. Redact sensitive information before upload.
4. After uploading, **read back or verify Drive metadata** and include the verified Google Drive URL in the handoff/PR/Asana task. A chat attachment or sandbox link alone is not a persistent archive.
5. If Google Drive access or upload is unavailable, **do not claim completion or invent a link**. Explicitly report `DRIVE_ARCHIVE_BLOCKED`, preserve the Markdown safely in Git/artifacts, and ask for connection/permissions. Never block security fixes solely because Drive is unavailable, but keep archival follow-up open.
6. These rules do not authorize merges, deployments, production changes, external sharing or publication. Respect the existing branch-per-change, approval, security and anti-duplication rules.

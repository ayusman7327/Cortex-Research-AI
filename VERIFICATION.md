# Verification

Verified locally on Windows with Python 3.12 on 2026-09-09.

## Results

- **249 offline tests passed** across authentication, upload formats, configuration, RAG, citations, summaries, and Streamlit interaction.
- **41 local-auth tests** use real SQLite and Argon2id. They cover signup, credentials, generic failures, malformed hashes, SQL input handling, rate limits, recovery rotation, session expiry, revocation, and absence of plaintext secrets in storage.
- **98 OIDC tests** validate configuration, HTTPS/loopback rules, cookie-secret length, identity claims, expiry, and verified-email access restrictions using simulated provider identities.
- **8 authentication UI tests** cover the actual sign-in gate, signup/login/logout, recovery, password change, account switching, revoked sessions, closed registration, and missing provider configuration.
- **102 research/configuration tests** cover real supported-file parsers and FAISS retrieval with mocked Gemini responses.
- The existing full document-to-chat/summary UI tests now sign in through the real local account service.
- Dependency consistency and source whitespace checks pass.
- Streamlit starts locally and the HTTP health endpoint returns ok.

## Remaining external verification

No real Gemini or OIDC provider credentials were supplied. Live Gemini embeddings, generated answers, scan reading, Google sign-in callbacks, provider access, and quota still need to be checked with your private credentials. See AUTHENTICATION.md and README.md.

GitHub Actions is configured for Python 3.12. Hosted CI has not run here.

## Package contents

The source ZIP includes full application code, authentication, tests, sample notes, pinned direct dependencies, configuration examples, and setup guides.

It excludes real .env and Streamlit secrets, account databases, database journals, Git history, virtual environments, and caches. No accounts are pre-created. Changes are local; nothing has been pushed or deployed to your accounts.

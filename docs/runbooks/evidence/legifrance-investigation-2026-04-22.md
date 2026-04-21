# Legifrance Technical Investigation (2026-04-22)

## Finding

Legifrance blocks programmatic HTTP access (403 to non-browser user agents).
`DeterministicHttpProvider` won't work here.

## Viable approaches

### Option A: PISTE/DILA API (recommended first step)

- Free OAuth 2.0 registration at https://piste.gouv.fr/registration
- Production API: `https://api.piste.gouv.fr/dila/legifrance/lf-engine-app`
- JSON responses via POST endpoints
- Similar pattern to `RisOgdProvider`
- Needs: `OAUTH_CLIENT_ID` + `OAUTH_CLIENT_SECRET` stored as Cloud Run secrets

### Option B: DILA FTP bulk XML (no auth)

- Complete XML dumps at `ftp://ftp2.journal-officiel.gouv.fr/LEGI/`
- Best for comprehensive corpus building
- Needs batch pipeline, not real-time provider

## Prerequisite

Register for PISTE API credentials. Once available, building the provider
is ~half a day following the RIS OGD pattern.

## Key IDs

| Text | LEGITEXT / JORFTEXT |
|------|---------------------|
| Code civil | LEGITEXT000006070721 |
| Code penal | LEGITEXT000006070719 |
| Constitution (1958) | JORFTEXT000000571356 |

# Clean-Room Principles

## Purpose

Evidara is a **clean-room implementation** of a document intelligence platform. This means all source code, schemas, configurations, tests, and documentation are authored fresh for this repository.

## Rules

### What is NOT allowed

- **Do not copy source code** from prior repositories.
- **Do not copy tests** from prior repositories.
- **Do not copy prompts** or AI configuration from prior repositories.
- **Do not copy proprietary documentation** from prior repositories.
- **Do not copy infrastructure definitions** (Terraform, CI pipelines, Dockerfiles) from prior repositories.

### What IS allowed

- **Lessons learned and general architecture ideas** from prior work. You may apply knowledge gained from experience.
- **Public framework documentation** (e.g., Next.js docs, Terraform provider docs, OpenSearch docs).
- **Newly authored examples** written specifically for this repository.
- **Requirements defined in this repository** — all specs, contracts, and architecture docs live here.

## Implementation guidance

When implementing a feature:

1. Start from the **requirements documented in this repo** (component docs, contracts, architecture).
2. Consult **public framework documentation** for APIs and patterns.
3. Write **new code** informed by your knowledge and experience.
4. Do not reference or open prior proprietary codebases during implementation.

## Why clean-room?

- Ensures intellectual property cleanliness.
- Forces explicit documentation of all design decisions.
- Prevents carrying forward technical debt from prior implementations.
- Creates a well-documented, well-understood codebase from day one.

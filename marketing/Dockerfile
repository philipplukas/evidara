# The public marketing surface (ADR-0039), built as a static export and served
# by a file server that cannot execute anything.
#
# Two stages on purpose. ADR-0039's central constraint is that this page runs no
# server code — "a marketing page that cannot execute server code cannot leak a
# secret, cannot be the entry point to the control plane, and cannot fall over
# when the product does". A single-stage image running `next start` would quietly
# give that up: it would still *work*, and the constraint would be gone with no
# diff to notice. Here the runtime stage has no Node in it at all, so a
# regression to a server runtime cannot be shipped by accident — it fails to
# build, the same way `runtime-images.yml`'s `out/index.html` assertion fails.

FROM node:22-alpine@sha256:8ea2348b068a9544dae7317b4f3aafcdc032df1647bb7d768a05a5cad1a7683f AS build

# Build context is the repo root so the shared modules under /styles/ can be
# copied alongside the app. Same reasoning as legal-search/frontend — ADR-0028.
WORKDIR /workspace

# globals.css `@import`s ../../../styles/tokens/tokens.css (the canonical design
# tokens, ADR-0027); page.tsx imports BrandMark from @evidara/shell, which
# tsconfig maps to ../styles/shell. Both must exist in the image or the build
# fails at "Can't resolve" rather than at runtime. See #547.
COPY styles/tokens ./styles/tokens
COPY styles/shell ./styles/shell

COPY marketing/package*.json ./marketing/
WORKDIR /workspace/marketing
RUN npm ci

COPY marketing ./

# `output: "export"` writes plain HTML/CSS/JS into out/ and starts no server.
RUN npm run build

# Fail here rather than serving an empty shell: this is the same assertion
# runtime-images.yml's sibling makes in CI, kept in the image build so a locally
# built image cannot skip it.
RUN test -f out/index.html \
  && grep -q "Law is a graph" out/index.html

# nginx-unprivileged listens on 8080 as a non-root user, which is both the port
# every other Evidara Service uses and one this container can bind without
# capabilities.
FROM nginxinc/nginx-unprivileged:1.29-alpine

# GHCR links a package to a repository by this label, and a base image's label is
# INHERITED. This is the only Evidara image whose final stage is a third-party base,
# and nginx-unprivileged ships `org.opencontainers.image.source` pointing at its own
# repo — so an image built without CI's `docker/metadata-action` labels arrives at
# ghcr.io attributed to nginx, and the package links to nothing. That is exactly how
# `evidara-marketing` became an orphan: unlinked, and therefore not writable by the
# workflow's `GITHUB_TOKEN` however much `packages: write` it is granted.
#
# Setting it here makes the attribution a property of the image rather than of the
# pipeline that happened to build it. The sibling Dockerfiles need no equivalent: their
# node/python bases set no such label, so there is nothing to inherit.
LABEL org.opencontainers.image.source=https://github.com/philipplukas/evidara
LABEL org.opencontainers.image.url=https://github.com/philipplukas/evidara

COPY --from=build /workspace/marketing/out /usr/share/nginx/html

EXPOSE 8080

#!/usr/bin/env bash
# Is production actually online?
#
# Answers the operator question that had no command: not "did CI pass" and not
# "did Argo sync", but "is the software a user would reach running, reachable,
# and the software we think it is".
#
# WHY THIS EXISTS. On 2026-09-07 all of the following were true at once, and
# every existing signal was green:
#   - Argo CD reported `Synced` / `Healthy` at `main`'s tip.
#   - Every pod in the namespace was `Running`, 1/1, no restarts.
#   - Production was running images pinned 15 commits behind `main`.
#   - `evidara.veyo.dev` — the marketing site, ADR-0039's only public surface —
#     did not resolve, had no Ingress in the cluster, and its pod was serving a
#     commit that is not on `main` at all (#884).
# Argo syncs the *manifests*; the image tag inside them is a hand-written pin, so
# "Synced" says nothing about which build is running. And a workload with no
# Ingress is perfectly healthy — it is simply unreachable. Neither gap is visible
# from any single existing check, which is why they lasted.
#
# THREE OUTCOMES, NOT TWO (AGENTS.md). A section whose prerequisites are absent
# reports DID-NOT-RUN and names what was missing. It never reports PASS.
#
# READ-ONLY. Every command here is a read. It mutates nothing and is safe to run
# against production at any time.
#
# Usage:
#   bash scripts/check-production-online.sh              # full check
#   NAMESPACE=evidara bash scripts/check-production-online.sh
#   SKIP_EDGE=1 bash scripts/check-production-online.sh   # cluster only, no egress
#
# Exit status: 0 = every section that ran passed. 1 = at least one FAIL.
# DID-NOT-RUN alone does not fail the run, but it is counted and reported.

set -uo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAMESPACE="${NAMESPACE:-evidara}"
ARGOCD_NAMESPACE="${ARGOCD_NAMESPACE:-argocd}"
GIT_REMOTE_REF="${GIT_REMOTE_REF:-origin/main}"
# Certificates renewed by cert-manager should never get this close to expiry.
TLS_MIN_DAYS="${TLS_MIN_DAYS:-14}"

fails=0
skips=0
passes=0
declare -a FAIL_LINES=()
declare -a SKIP_LINES=()

pass()  { printf '  \033[32mPASS\033[0m  %s\n' "$*"; passes=$((passes + 1)); }
fail()  { printf '  \033[31mFAIL\033[0m  %s\n' "$*"; fails=$((fails + 1)); FAIL_LINES+=("$*"); }
skip()  { printf '  \033[33mDID-NOT-RUN\033[0m  %s\n' "$*"; skips=$((skips + 1)); SKIP_LINES+=("$*"); }
info()  { printf '        %s\n' "$*"; }
section() { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }

# ── prerequisites ────────────────────────────────────────────────────────────

have_kubectl=1
command -v kubectl >/dev/null 2>&1 || have_kubectl=0

cluster_reachable=0
if (( have_kubectl )); then
  if timeout 20 kubectl get ns "$NAMESPACE" >/dev/null 2>&1; then
    cluster_reachable=1
  fi
fi

# ── 1. workload readiness ────────────────────────────────────────────────────

section "1. Workload readiness (namespace: $NAMESPACE)"
if (( ! have_kubectl )); then
  skip "kubectl not installed — no workload, health, image or Argo check ran."
elif (( ! cluster_reachable )); then
  skip "kubectl cannot reach namespace '$NAMESPACE' (context: $(kubectl config current-context 2>/dev/null || echo none))."
else
  # `Running` is not `Ready`: a pod whose readiness probe fails stays Running and
  # is quietly removed from its Service. Compare desired against ready.
  not_ready=0
  while read -r name desired ready; do
    [[ -z "$name" ]] && continue
    ready="${ready:-0}"
    if [[ "$ready" != "$desired" ]]; then
      fail "deployment/$name: $ready/$desired ready"
      not_ready=$((not_ready + 1))
    fi
  done < <(timeout 30 kubectl get deploy -n "$NAMESPACE" \
             -o 'jsonpath={range .items[*]}{.metadata.name} {.spec.replicas} {.status.readyReplicas}{"\n"}{end}' 2>/dev/null)

  total=$(timeout 20 kubectl get deploy -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l)
  if (( total == 0 )); then
    fail "no Deployments found in namespace '$NAMESPACE' — is this the right cluster?"
  elif (( not_ready == 0 )); then
    pass "all $total deployments fully ready"
  fi
fi

# ── 2. which build is running ────────────────────────────────────────────────

section "2. Deployed commit vs $GIT_REMOTE_REF"
if (( ! cluster_reachable )); then
  skip "cluster unreachable — deployed image tags not read."
elif ! git -C "$root" rev-parse --verify --quiet "$GIT_REMOTE_REF" >/dev/null; then
  skip "$GIT_REMOTE_REF does not exist locally — run 'git fetch origin' first."
else
  # The tag on each image IS the commit it was built from (runtime-images.yml
  # tags with the full github.sha). That makes "what is running" answerable
  # without any build-info endpoint — which matters, because the endpoint that
  # would answer it (#889) is itself not deployed yet (#894).
  seen_any=0
  while read -r dep image; do
    [[ -z "$dep" ]] && continue
    # Only our own images carry a commit SHA tag; skip upstream ones.
    [[ "$image" == ghcr.io/philipplukas/evidara-* ]] || continue
    tag="${image##*:}"
    [[ "$tag" =~ ^[0-9a-f]{40}$ ]] || { info "$dep: tag '$tag' is not a commit SHA — cannot place it on a branch"; continue; }
    seen_any=1
    if ! git -C "$root" cat-file -e "${tag}^{commit}" 2>/dev/null; then
      fail "$dep runs $tag — a commit this clone has never seen (fetch, or it was never on a branch)"
    elif ! git -C "$root" merge-base --is-ancestor "$tag" "$GIT_REMOTE_REF" 2>/dev/null; then
      fail "$dep runs ${tag:0:8} — NOT an ancestor of $GIT_REMOTE_REF. Production is serving code that is not on the main line."
    else
      behind=$(git -C "$root" rev-list --count "${tag}..${GIT_REMOTE_REF}" 2>/dev/null || echo '?')
      if [[ "$behind" == "0" ]]; then
        pass "$dep at ${tag:0:8} (tip of $GIT_REMOTE_REF)"
      else
        info "$dep at ${tag:0:8} — $behind commits behind $GIT_REMOTE_REF"
      fi
    fi
  done < <(timeout 30 kubectl get deploy -n "$NAMESPACE" \
             -o 'jsonpath={range .items[*]}{.metadata.name} {.spec.template.spec.containers[0].image}{"\n"}{end}' 2>/dev/null)

  (( seen_any )) || skip "no evidara images with SHA tags found — nothing to compare."
fi

# ── 3. application health endpoints ──────────────────────────────────────────

section "3. Health endpoints (probed from inside the cluster)"
if (( ! cluster_reachable )); then
  skip "cluster unreachable — no endpoint was probed."
else
  # Probe from inside the pod rather than through the edge, so this section
  # measures the application and not the auth proxy in front of it. Containers
  # here are distroless-ish and disagree about which HTTP client they ship, so
  # try each in turn and report DID-NOT-RUN rather than a false pass if none.
  probe() {  # probe <deployment> <port> <path> [scheme]
    local dep="$1" port="$2" path="$3" scheme="${4:-http}" url out
    url="${scheme}://127.0.0.1:${port}${path}"
    out=$(timeout 45 kubectl exec -n "$NAMESPACE" "deploy/$dep" -- sh -c "
      if command -v curl >/dev/null 2>&1; then
        curl -sk -o /dev/null -w '%{http_code}' --max-time 8 '${url}'
      elif command -v wget >/dev/null 2>&1; then
        # busybox wget: -S writes the status line to stderr. Parse it rather than
        # using the exit code, which collapses 401/404/500 into one 'failed'.
        wget -S --no-check-certificate -O /dev/null -T 8 '${url}' 2>&1 \
          | awk '/HTTP\\//{c=\$2} END{print (c==\"\" ? \"ERR\" : c)}'
      elif command -v python3 >/dev/null 2>&1; then
        python3 -c \"
import urllib.request,ssl
ctx=ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
try: print(urllib.request.urlopen('${url}',timeout=8,context=ctx).status)
except Exception as e: print(getattr(e,'code','ERR'))
\"
      else
        echo NOCLIENT
      fi" 2>/dev/null | tr -d '[:space:]')
    printf '%s' "${out:-EXECFAIL}"
  }

  # Derived from the cluster's own probes, so this cannot drift from what
  # Kubernetes actually asks for. Losing a probe from a manifest shows up here
  # as an endpoint that stopped being checked, rather than as silence.
  #
  # A probe port may be a NAME rather than a number (`port: nessie-mgmt`), which
  # is valid Kubernetes and produces an unusable URL if passed through. Resolve
  # names against the container's own `ports:` list first. Getting this wrong
  # cost two false FAILs on the first run of this script, and a gate that cries
  # wolf gets ignored, which is worse than not having it.
  declare -A port_by_name=()
  # shellcheck disable=SC2016  # go-template; {{$d}} must reach kubectl unexpanded
  while read -r dep pname pnum; do
    [[ -z "$dep" || -z "$pname" ]] && continue
    port_by_name["${dep}/${pname}"]="$pnum"
  done < <(timeout 30 kubectl get deploy -n "$NAMESPACE" -o go-template='
{{- range .items -}}{{- $d := .metadata.name -}}
{{- range .spec.template.spec.containers -}}{{- range .ports -}}
{{- if .name -}}{{$d}} {{.name}} {{.containerPort}}{{"\n"}}{{- end -}}
{{- end -}}{{- end -}}{{- end -}}' 2>/dev/null)

  probed=0
  # shellcheck disable=SC2016  # go-template; {{$d}} must reach kubectl unexpanded
  while read -r dep port path scheme; do
    [[ -z "$dep" || -z "$path" || "$path" == "<none>" ]] && continue
    if [[ ! "$port" =~ ^[0-9]+$ ]]; then
      resolved="${port_by_name["${dep}/${port}"]:-}"
      if [[ -z "$resolved" ]]; then
        skip "$dep: probe port '$port' is a name with no matching containerPort — $path was NOT probed"
        continue
      fi
      port="$resolved"
    fi
    case "$scheme" in HTTPS|https) scheme=https ;; *) scheme=http ;; esac
    probed=$((probed + 1))
    code=$(probe "$dep" "$port" "$path" "$scheme")
    case "$code" in
      2*)        pass "$dep $path -> $code" ;;
      NOCLIENT)  skip "$dep ships no curl/wget/python3 — $path was NOT probed" ;;
      EXECFAIL)  skip "$dep: kubectl exec failed (no shell in the image?) — $path was NOT probed" ;;
      ERR)       skip "$dep: $path gave no parseable status — NOT probed" ;;
      *)         fail "$dep $path -> $code" ;;
    esac
  done < <(timeout 30 kubectl get deploy -n "$NAMESPACE" -o go-template='
{{- range .items -}}{{- $d := .metadata.name -}}
{{- range .spec.template.spec.containers -}}{{- with .readinessProbe.httpGet -}}
{{$d}} {{.port}} {{.path}} {{.scheme}}{{"\n"}}
{{- end -}}{{- end -}}{{- end -}}' 2>/dev/null)

  (( probed )) || skip "no readiness httpGet probes found in '$NAMESPACE'."

  # /ready on platform-control is deliberately NOT the Kubernetes readiness
  # probe (that is /health, "the process is alive"). Nothing in the cluster
  # exercises it, so nothing would notice it going 503 — which is the whole
  # point of #898's schema-drift reporting. Check it explicitly.
  if timeout 20 kubectl get deploy platform-control-api -n "$NAMESPACE" >/dev/null 2>&1; then
    code=$(probe platform-control-api 8080 /ready)
    case "$code" in
      2*) pass "platform-control-api /ready -> $code (unprobed by k8s; checked here)" ;;
      NOCLIENT|EXECFAIL) skip "platform-control-api /ready was NOT probed ($code)" ;;
      *)  fail "platform-control-api /ready -> $code — the API is alive but not ready to serve" ;;
    esac
  fi
fi

# ── 4. GitOps sync ───────────────────────────────────────────────────────────

section "4. Argo CD"
if (( ! cluster_reachable )); then
  skip "cluster unreachable — Argo CD state not read."
elif ! timeout 20 kubectl get applications.argoproj.io -n "$ARGOCD_NAMESPACE" >/dev/null 2>&1; then
  skip "no Argo CD Applications readable in namespace '$ARGOCD_NAMESPACE'."
else
  # Only assert on Applications sourced from THIS repository.
  #
  # This Argo instance is shared. It also serves `research-platform`, whose
  # `platform` Application was `OutOfSync/Progressing` at the moment this script
  # first ran after a deploy — and reporting that as an Evidara failure is simply
  # wrong. A check that fails for reasons outside its own subject teaches people
  # to ignore it, which costs more than the check is worth.
  #
  # The repo identity is derived from `origin`, not hardcoded, and compared on the
  # `owner/repo` tail so an `https://` remote and a `git@` Application URL match.
  repo_id() {  # normalise a git URL to owner/repo
    # Keeps the last two path segments, so both of these give philipplukas/evidara:
    #   git@github.com:philipplukas/evidara.git
    #   https://github.com/philipplukas/evidara
    printf '%s' "${1%.git}" | sed 's#.*[:/]\([^/]*/[^/]*\)$#\1#'
  }
  mine="$(repo_id "$(git -C "$root" remote get-url origin 2>/dev/null || echo '')")"

  matched=0
  while read -r app repourl sync health rev; do
    [[ -z "$app" ]] && continue
    if [[ -z "$mine" || "$(repo_id "$repourl")" != "$mine" ]]; then
      # Named, not silent: an unasserted Application should still be visible, so
      # nobody concludes this section covered something it did not.
      info "$app is sourced from ${repourl:-<unknown>} — not this repo, not asserted here"
      continue
    fi
    matched=$((matched + 1))
    if [[ "$sync" == "Synced" && "$health" == "Healthy" ]]; then
      pass "$app: $sync / $health @ ${rev:0:8}"
    else
      fail "$app: $sync / $health @ ${rev:0:8}"
    fi
    # Argo syncing to tip is NOT the same as production running tip: the image
    # tag lives inside the synced manifests as a hand-written pin. Say so, so a
    # green Argo line is never read as "production is current".
    if [[ "$rev" =~ ^[0-9a-f]{40}$ ]] && git -C "$root" cat-file -e "${rev}^{commit}" 2>/dev/null; then
      b=$(git -C "$root" rev-list --count "${rev}..${GIT_REMOTE_REF}" 2>/dev/null || echo '?')
      [[ "$b" == "0" ]] || info "manifests are $b commits behind $GIT_REMOTE_REF"
    fi
  done < <(timeout 30 kubectl get applications.argoproj.io -n "$ARGOCD_NAMESPACE" \
             -o 'jsonpath={range .items[*]}{.metadata.name} {.spec.source.repoURL} {.status.sync.status} {.status.health.status} {.status.sync.revision}{"\n"}{end}' 2>/dev/null)

  (( matched )) || skip "no Argo CD Application in '$ARGOCD_NAMESPACE' is sourced from this repo — GitOps state was NOT asserted."
fi

# ── 5. the edge: can a user actually reach it ────────────────────────────────

section "5. Public edge"
if [[ -n "${SKIP_EDGE:-}" ]]; then
  skip "SKIP_EDGE set — no hostname was resolved or fetched."
elif ! command -v curl >/dev/null 2>&1; then
  skip "curl not installed — no hostname was resolved or fetched."
else
  # The expected hostnames come from the Ingress manifests in the REPO, not from
  # the cluster. That is deliberate and is the only way this section can catch
  # #884: an Ingress that exists as a file and was never applied is exactly the
  # failure being looked for, and asking the cluster what it serves would agree
  # with itself and report nothing wrong.
  mapfile -t declared < <(grep -rhoE '^[[:space:]]+- host: [a-z0-9.-]+' \
      "$root/infra/hetzner" --include='*.yaml' 2>/dev/null \
    | awk '{print $3}' | grep -vE '^(0\.0\.0\.0|localhost)$' | sort -u)

  if (( ${#declared[@]} == 0 )); then
    skip "no Ingress hosts found under infra/hetzner — nothing to probe."
  fi

  for host in "${declared[@]}"; do
    # a. does the name resolve at all
    if ! getent hosts "$host" >/dev/null 2>&1; then
      fail "$host does not resolve — declared in an Ingress manifest, but no DNS record exists"
      continue
    fi

    # b. is it actually served
    #
    # `/health` FIRST, then `/`. An API has no root route, so `GET /` returns a
    # perfectly healthy 404 — and this check used to call that a failure. It
    # reported `legal-search-api.ts.veyo.dev -> 404` and
    # `platform-control-api.ts.veyo.dev -> 404` as two production outages while
    # both served `/health` 200. A gate that cries wolf about healthy services
    # is worse than no gate: the next real failure reads as more noise.
    #
    # Passing every 404 instead would be the opposite mistake. An Ingress that
    # exists as a file and was never applied ALSO 404s, and catching that is the
    # whole reason this section talks to DNS rather than to the cluster (#884).
    # Probing a path the backend actually serves separates the two: an
    # unapplied Ingress fails `/health` as well.
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "https://$host/health" 2>/dev/null)
    probed="/health"
    case "$code" in
      2*|3*) ;;
      *)
        # No `/health` (marketing, consoles, anything not an API) — fall back to
        # the root and judge it as before.
        code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "https://$host/" 2>/dev/null)
        probed="/"
        ;;
    esac
    case "$code" in
      # 401/403 are a PASS: the auth proxy answering is proof the whole chain —
      # DNS, TLS, Traefik, the Ingress — is up. 2xx/3xx likewise.
      2*|3*|401|403) pass "$host$probed -> $code" ;;
      000) fail "$host resolves but the connection failed (TLS handshake, or nothing listening)" ;;
      5*)  fail "$host$probed -> $code — the edge is up but the backend is not answering" ;;
      *)   fail "$host$probed -> $code" ;;
    esac

    # c. is the certificate about to lapse
    if command -v openssl >/dev/null 2>&1; then
      end=$(echo | timeout 15 openssl s_client -servername "$host" -connect "$host:443" 2>/dev/null \
            | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)
      if [[ -n "$end" ]]; then
        left=$(( ( $(date -d "$end" +%s 2>/dev/null || echo 0) - $(date +%s) ) / 86400 ))
        if (( left <= 0 )); then
          fail "$host TLS certificate has EXPIRED"
        elif (( left < TLS_MIN_DAYS )); then
          fail "$host TLS certificate expires in $left days (cert-manager renewal is not happening)"
        fi
      fi
    fi

    # d. is the Ingress the manifest declares actually in the cluster
    if (( cluster_reachable )); then
      if ! timeout 20 kubectl get ingress -n "$NAMESPACE" -o jsonpath='{.items[*].spec.rules[*].host}' 2>/dev/null \
           | tr ' ' '\n' | grep -qx "$host"; then
        # Other namespaces legitimately hold some of these (auth, for one), so
        # only say something when the name also failed to answer above.
        [[ "$code" == "000" || -z "$code" ]] && \
          info "$host has no Ingress in namespace '$NAMESPACE' — the manifest declaring it was never applied"
      fi
    fi
  done
fi

# ── verdict ──────────────────────────────────────────────────────────────────

section "Verdict"
if (( fails == 0 && skips == 0 )); then
  echo "  ONLINE — every section ran and passed."
  exit 0
fi
if (( fails == 0 && passes == 0 )); then
  # Nothing failed because nothing was measured. Saying "online" here would be
  # the exact dishonesty this script exists to remove.
  echo "  UNKNOWN — nothing could be checked. $skips section(s) did not run:"
  printf '    - %s\n' "${SKIP_LINES[@]}"
  exit 0
fi
if (( fails == 0 )); then
  echo "  ONLINE for what ran — $passes check(s) passed, $skips could not run:"
  printf '    - %s\n' "${SKIP_LINES[@]}"
  echo "  This is not a full pass. Re-run with the prerequisites above present."
  exit 0
fi
printf '  NOT FULLY ONLINE — %d failure(s):\n' "$fails"
printf '    - %s\n' "${FAIL_LINES[@]}"
if (( skips > 0 )); then
  printf '  ALSO NOT CHECKED:\n'; printf '    - %s\n' "${SKIP_LINES[@]}"
fi
exit 1

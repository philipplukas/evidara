set shell := ["bash", "-cu"]

default:
  @just --list

# Local infra only (mode: lite|search|full)
up mode="search":
  bash scripts/local-vertical-slice.sh up {{mode}}

down mode="search":
  bash scripts/local-vertical-slice.sh down {{mode}}

status mode="search":
  bash scripts/local-vertical-slice.sh status {{mode}}

env mode="search":
  bash scripts/local-vertical-slice.sh env {{mode}}

# Full local stack via compose (apps + infra)
up-all mode="search":
  bash scripts/local-vertical-slice.sh up-all {{mode}}

down-all mode="search":
  bash scripts/local-vertical-slice.sh down-all {{mode}}

status-all mode="search":
  bash scripts/local-vertical-slice.sh status-all {{mode}}

check-all mode="search":
  bash scripts/local-vertical-slice.sh check-all {{mode}}

# Convenience shortcuts
up-search:
  bash scripts/local-vertical-slice.sh up-all search

up-full:
  bash scripts/local-vertical-slice.sh up-all full

check-search:
  bash scripts/local-vertical-slice.sh check-all search

check-full:
  bash scripts/local-vertical-slice.sh check-all full

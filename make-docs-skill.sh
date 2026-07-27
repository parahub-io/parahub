#!/usr/bin/env bash
#
# Build an Agent Skill (open SKILL.md standard) from docs/.
#
# Produces a portable skill: a folder with a generated SKILL.md router plus a
# verbatim copy of docs/. The SKILL.md format is a cross-platform open standard
# used by Claude Code, OpenAI Codex, Gemini/Antigravity CLI, GitHub Copilot,
# Cursor, and other agent tools. Skills do not sync between tools/surfaces, so
# re-run this after editing docs/.
#
# Usage:
#   ./make-docs-skill.sh [--zip|--folder|--both] [<out-dir>]
#
#   (default) --zip     -> <out-dir>/parahub-platform-docs.zip
#   --folder            -> <out-dir>/parahub-platform-docs/   (unzipped)
#   --both              -> both of the above
#   <out-dir> defaults to /tmp
#
# Delivery:
#   zip    -> web-app upload (claude.ai, ChatGPT — via each app's Skills settings)
#   folder -> drop into a CLI tool's skills dir (.claude/skills/, .agents/skills/, ...)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCS_DIR="$SCRIPT_DIR/docs"
SKILL_NAME="parahub-platform-docs"

MODE="zip"
case "${1:-}" in
  --zip)    MODE="zip";    shift ;;
  --folder) MODE="folder"; shift ;;
  --both)   MODE="both";   shift ;;
  --*)      echo "error: unknown option '$1' (use --zip|--folder|--both)" >&2; exit 2 ;;
esac
OUT_DIR="${1:-/tmp}"

[ -d "$DOCS_DIR" ] || { echo "error: docs/ not found at $DOCS_DIR" >&2; exit 1; }
mkdir -p "$OUT_DIR"

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
PKG="$STAGE/$SKILL_NAME"
mkdir -p "$PKG"
cp -r "$DOCS_DIR/." "$PKG/"

# Auto-generated flat module list (grouped index lives in modules/README.md).
MODULES="$(cd "$DOCS_DIR/modules" && ls *.md 2>/dev/null \
  | grep -vi '^README.md$' | sed 's/\.md$//' | sort | paste -sd' ' - \
  | sed 's/ / \xc2\xb7 /g')"

cat > "$PKG/SKILL.md" <<EOF
---
name: $SKILL_NAME
description: Reference documentation for the Parahub platform — a self-hostable, non-custodial peer-to-peer civic and economic platform (P2P marketplace, barter cycles, GTFS/real-time transit, liquid-democracy governance, non-custodial Lightning wallet, condominium and energy management, community drone mapping, federation, and 25+ more modules). Use whenever the user asks how any Parahub feature works, about its architecture or tech stack, security and trust model, philosophy and inviolable constraints, the REST API, self-hosting, the roadmap, or the internals of a specific module (marketplace, transit, wallet, governance, directory, identity, condominium, etc.).
---

# Parahub Platform Documentation

Authoritative user-facing documentation for the Parahub platform. Use it to answer
questions about what Parahub is, how any subsystem works, its architecture, and its
guiding principles. Everything here is the single source of truth — do not invent
features, numbers, or behavior that is not stated in these files.

## How to use this skill

The documentation is organized as an index (this file) plus reference files loaded on
demand. When a question maps to a topic, read the specific file rather than guessing.

1. For a high-level orientation, read \`README.md\`, then \`vision.md\` and \`philosophy.md\`.
2. For "how does X work" about a concrete subsystem, open \`modules/X.md\` (see the
   module map below). \`modules/README.md\` is the full grouped module index.
3. For cross-cutting topics, use the top-level files listed under "Core references".
4. If a claim isn't covered by these files, say so — do not fabricate.

## Core references (top-level files)

| File | Use it for |
|------|------------|
| \`README.md\` | Platform overview, quick facts, what Parahub is |
| \`vision.md\` | Problem/solution, what Parahub is and is NOT |
| \`philosophy.md\` | Core principles, the inviolable constraints, economic/governance model |
| \`features.md\` | High-level catalog of all working subsystems (production) |
| \`architecture.md\` | Tech stack, services, infrastructure, data model patterns |
| \`security.md\` | Web of Trust, PGP, non-custodial wallet, rate limiting, JWT |
| \`for-developers.md\` | REST API guide, endpoints, self-hosting |
| \`roadmap.md\` | Planned and upcoming features |
| \`estatutos.md\` | Legal charter (Portuguese) — association bylaws |

## Module map (\`modules/*.md\`)

Read the matching file for subsystem details. \`modules/README.md\` holds the grouped index.

$MODULES

## Answering guidance

- Prefer quoting or paraphrasing the docs over general knowledge; this platform has
  specific, deliberate design choices (non-custodial, no escrow, client-side crypto,
  Web of Trust) that differ from typical assumptions.
- When a subsystem touches money or trust, check \`philosophy.md\` and \`security.md\` for
  the constraints before describing behavior.
- Describe mechanisms functionally; do not compare to named commercial products.
EOF

COUNT="$(find "$PKG" -type f | wc -l | tr -d ' ')"

emit_zip() {
  local out="$OUT_DIR/$SKILL_NAME.zip"
  rm -f "$out"
  if command -v zip >/dev/null 2>&1; then
    ( cd "$STAGE" && zip -rq "$out" "$SKILL_NAME" -x '*.DS_Store' )
  else
    STAGE="$STAGE" OUT_ZIP="$out" SKILL_NAME="$SKILL_NAME" python3 - <<'PY'
import os, zipfile
stage, out, name = os.environ["STAGE"], os.environ["OUT_ZIP"], os.environ["SKILL_NAME"]
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for dp, _, fs in os.walk(os.path.join(stage, name)):
        for f in fs:
            if f == ".DS_Store":
                continue
            p = os.path.join(dp, f)
            z.write(p, os.path.relpath(p, stage))
PY
  fi
  local size; size="$(du -h --apparent-size "$out" | cut -f1)"
  echo "  zip:    $out ($size)"
}

emit_folder() {
  local out="$OUT_DIR/$SKILL_NAME"
  rm -rf "$out"
  cp -r "$PKG" "$out"
  echo "  folder: $out/"
}

echo "Built open SKILL.md skill '$SKILL_NAME' ($COUNT files):"
case "$MODE" in
  zip)    emit_zip ;;
  folder) emit_folder ;;
  both)   emit_zip; emit_folder ;;
esac
echo "Portable across Claude Code, OpenAI Codex, Gemini/Antigravity CLI, GitHub Copilot, Cursor and other SKILL.md tools."
echo "  zip    -> web-app upload (claude.ai, ChatGPT — via each app's Skills settings)"
echo "  folder -> drop into a CLI tool's skills dir (.claude/skills/, .agents/skills/, ...)"

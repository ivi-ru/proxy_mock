#!/usr/bin/env bash
# Guard against AGENTS.md drifting away from the Makefile: an agent instruction file that names
# commands which no longer exist is worse than none, because it is trusted.
#
# Only commands written as code (`make test`) are checked, not prose that happens to say "make".
set -euo pipefail

status=0

for target in $(grep -oE '`make [a-z_]+`' AGENTS.md | tr -d '`' | awk '{print $2}' | sort -u); do
  if ! grep -qE "^${target}:" Makefile; then
    echo "AGENTS.md mentions 'make ${target}', which is not a target in the Makefile"
    status=1
  fi
done

if [ "$status" -eq 0 ]; then
  echo "AGENTS.md refers only to existing make targets"
fi

exit "$status"

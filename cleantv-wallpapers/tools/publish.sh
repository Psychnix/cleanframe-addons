#!/usr/bin/env bash
# Commit and push the generator's outputs as github-actions[bot]: only cleantv-wallpapers/index.json
# and cleantv-wallpapers/generated/, with [skip ci], and nothing when they did not change.
# .github/workflows/cleantv-wallpapers.yml runs it from the repository root; test_publish.py tests it.
set -eu

# generated/ is absent while images/ is empty.
paths=cleantv-wallpapers/index.json
if [ -e cleantv-wallpapers/generated ] || git ls-files --error-unmatch cleantv-wallpapers/generated > /dev/null 2>&1; then
  paths="$paths cleantv-wallpapers/generated"
fi
git add -A -- $paths
if git diff --cached --quiet; then
  echo 'The generated wallpapers did not change.'
  exit 0
fi
git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git commit -q -m 'Generate CleanTV wallpapers [skip ci]'

# main may move while the generator runs, for example through a merged catalog change that does not
# start this workflow. The bot commit touches only generated/ and index.json, so it is replayed onto
# the new tip. When that push changed images/ or tools/, a newer run is already queued and regenerates
# from there; when it changed the generated files, the rebase conflicts and the job fails visibly.
for attempt in 1 2 3; do
  if git push origin HEAD:main; then
    exit 0
  fi
  echo "Push $attempt was rejected; replaying the generated wallpapers onto the current main."
  if ! git pull --rebase origin main; then
    git rebase --abort > /dev/null 2>&1 || true
    break
  fi
done
echo '::error::Could not push the generated wallpapers; run this workflow again.'
exit 1

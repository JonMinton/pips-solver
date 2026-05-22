#!/bin/sh
# Activate the repo's git hooks (the pre-push test gate).
# Run once after cloning:  sh tools/install_hooks.sh
set -e
git config core.hooksPath .githooks
chmod +x .githooks/pre-push
echo "pre-push test gate installed (core.hooksPath = .githooks)."
echo "Every 'git push' now runs tools/run_pre_deploy_tests.py first."

#!/usr/bin/env bash
# Setup GitHub repository for flora-app
# Run this script manually to push to GitHub

set -e

echo "=== Flora GitHub Setup ==="
echo ""

# Check gh CLI
if ! command -v gh &>/dev/null; then
    echo "Installing gh CLI..."
    sudo apt-get update -qq
    sudo apt-get install -y gh
fi

echo "gh version: $(gh --version | head -1)"
echo ""

# Check auth
if ! gh auth status &>/dev/null; then
    echo "Please authenticate with GitHub:"
    gh auth login
fi

echo "Authenticated as: $(gh api user --jq .login)"
echo ""

# Create repo (skip if already exists)
REPO_NAME="flora-app"
GH_USER="$(gh api user --jq .login)"

if gh repo view "$GH_USER/$REPO_NAME" &>/dev/null; then
    echo "Repo $GH_USER/$REPO_NAME already exists."
else
    echo "Creating public repo $REPO_NAME..."
    gh repo create "$REPO_NAME" \
        --public \
        --description "Autonomous herb garden agent — Raspberry Pi + Claude AI" \
        --source=. \
        --remote=origin \
        --push
    echo "Repo created and pushed!"
    exit 0
fi

# Add remote if not exists
if ! git remote get-url origin &>/dev/null; then
    git remote add origin "https://github.com/$GH_USER/$REPO_NAME.git"
    echo "Remote 'origin' added."
fi

# Push
echo "Pushing to GitHub..."
git push -u origin master
echo ""
echo "Done! Repo: https://github.com/$GH_USER/$REPO_NAME"

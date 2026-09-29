---
name: project:create-pr
description: '5. Create a structured PR after explicit approval'
argument-hint: '[optional: target base branch]'
---

# /project:create-pr

> **TASK TRACKING:** Create a task per step. **Approval gate:** do not push or
> open the PR until the user explicitly approves in this session.

## Step 1: Preconditions

Confirm the working tree is in the intended state and review has passed (or the
user accepts the findings). Confirm no real PII or secrets are staged (data, real
manifests, truth sets). Confirm the user wants a PR created now.

## Step 2: Branch & Commit

If on the default branch, create a feature branch first. Stage the intended
changes and write a clear commit message (Conventional Commits style). End the
commit message with:

```
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
```

## Step 3: Reviewers

Read `.claude/config/dev-ownership.md`, match the changed paths, and list the
reviewers to tag.

## Step 4: Open the PR

Push and open the PR with `gh`. Body: summary, linked plan (`docs/plans/`), test
results, and review verdict. End the PR body with:

```
🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

## Step 5: Report

Return the PR URL and the tagged reviewers.

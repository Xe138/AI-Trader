# AI-Trader to AI-Trader-Server Rebrand Design

**Date:** 2025-11-01
**Status:** Approved

## Overview

Rebrand the project from "AI-Trader" to "AI-Trader-Server" to accurately reflect its evolution into a REST API service architecture. This is a clean-break rebrand with no backward compatibility requirements.

## Goals

1. Update project name consistently across all documentation and configuration
2. Emphasize REST API service architecture in messaging
3. Update repository references to `github.com/Xe138/AI-Trader-Server`
4. Update Docker image references to `ghcr.io/xe138/ai-trader-server`
5. Acknowledge original fork source

## Strategy: Layered Rebrand with Validation

The rebrand will proceed in 4 distinct phases, each with validation checkpoints to ensure consistency and correctness.

---

## Phase 1: Core User-Facing Documentation

### Files to Update
- `README.md`
- `QUICK_START.md`
- `API_REFERENCE.md`
- `CHANGELOG.md`

### Changes

#### Title & Tagline
- **Old:** "🚀 AI-Trader: Can AI Beat the Market?"
- **New:** "🚀 AI-Trader-Server: REST API for AI Trading"

#### Subtitle/Description
- **Old:** "REST API service for autonomous AI trading competitions..."
- **New:** Emphasize "REST API service" as the primary architecture

#### Repository URLs
- **Old:** `github.com/HKUDS/AI-Trader` or `github.com/Xe138/AI-Trader`
- **New:** `github.com/Xe138/AI-Trader-Server`

#### Docker Image References
- **Old:** `ghcr.io/hkuds/ai-trader:latest`
- **New:** `ghcr.io/xe138/ai-trader-server:latest`

#### Badges
Update shields.io badge URLs and links to reference new repository

### Validation Checklist
- [ ] Render markdown locally to verify formatting
- [ ] Test all GitHub links (repository, issues, etc.)
- [ ] Verify Docker image references are consistent
- [ ] Check that badges render correctly

---

## Phase 2: Configuration Files

### Files to Update
- `configs/*.json`
- `.env.example`
- `docker-compose.yml`
- `Dockerfile`

### Changes

#### docker-compose.yml
- **Service name:** Update if currently "ai-trader"
- **Container name:** `ai-trader` → `ai-trader-server`
- **Image name:** Update to `ai-trader-server:latest` or `ghcr.io/xe138/ai-trader-server`

#### Dockerfile
- **Labels/metadata:** Update any LABEL instructions with project name
- **Comments:** Update inline comments referencing project name

#### Configuration Files
- **Comments:** Update JSON/config file comments with new project name
- **Metadata fields:** Update any "project" or "name" fields

#### .env.example
- **Comments:** Update explanatory comments with new project name

### Validation Checklist
- [ ] Run `docker-compose build` successfully
- [ ] Run `docker-compose up` and verify container name
- [ ] Check environment variable documentation consistency
- [ ] Verify config files parse correctly

---

## Phase 3: Developer & Deployment Documentation

### Files to Update

#### docs/user-guide/
- `configuration.md`
- `using-the-api.md`
- `integration-examples.md`
- `troubleshooting.md`

#### docs/developer/
- `CONTRIBUTING.md`
- `development-setup.md`
- `testing.md`
- `architecture.md`
- `database-schema.md`
- `adding-models.md`

#### docs/deployment/
- `docker-deployment.md`
- `production-checklist.md`
- `monitoring.md`
- `scaling.md`

#### docs/reference/
- `environment-variables.md`
- `mcp-tools.md`
- `data-formats.md`

### Changes

#### Architecture Diagrams
Update ASCII art diagrams:
- Any "AI-Trader" labels → "AI-Trader-Server"
- Maintain diagram structure, only update labels

#### Code Examples
In documentation only (no actual code changes):
- Example client class names: `AITraderClient` → `AITraderServerClient`
- Import examples: Update project references
- Shell script examples: Update Docker image names and repository clones

#### CLAUDE.md
- **Project Overview section:** Update project name and description
- **Docker Deployment commands:** Update image names
- **Repository references:** Update GitHub URLs

#### Shell Scripts (if any in docs/)
- Update comments and echo statements
- Update git clone commands with new repository URL

### Validation Checklist
- [ ] Verify code examples are still executable (where applicable)
- [ ] Check documentation cross-references (internal links)
- [ ] Test Docker commands in deployment docs
- [ ] Verify architecture diagrams render correctly

---

## Phase 4: Internal Configuration & Metadata

### Files to Update
- `CLAUDE.md` (main project root)
- `.github/workflows/*.yml` (if exists)
- Any package/build metadata files

### Changes

#### CLAUDE.md
- **Project Overview:** First paragraph describing project name and purpose
- **Commands/Examples:** Any git clone or Docker references

#### GitHub Actions (if exists)
- **Workflow names:** Update descriptive names
- **Docker push targets:** Update registry paths to `ghcr.io/xe138/ai-trader-server`
- **Comments:** Update inline comments

#### Git Configuration
- No changes needed to .gitignore or .git/ directory
- Git remote URLs should be updated separately (not part of this rebrand)

### Validation Checklist
- [ ] CLAUDE.md guidance remains accurate for Claude Code
- [ ] No broken internal cross-references
- [ ] CI/CD workflows (if any) reference correct image names

---

## Naming Conventions Reference

### Project Display Name
**Format:** AI-Trader-Server (hyphenated, Server capitalized)

### Repository References
- **URL:** `https://github.com/Xe138/AI-Trader-Server`
- **Clone:** `git clone https://github.com/Xe138/AI-Trader-Server.git`

### Docker References
- **Image:** `ghcr.io/xe138/ai-trader-server:latest`
- **Container name:** `ai-trader-server`
- **Service name (compose):** `ai-trader-server`

### Code Identifiers
- **Python classes:** No changes required (keep existing for backward compatibility)
- **Documentation examples:** Optional update to `AITraderServerClient` for clarity

---

## Fork Acknowledgment

Add the following section to README.md, placed before the "License" section:

```markdown
---

## 🙏 Acknowledgments

This project is a fork of [HKUDS/AI-Trader](https://github.com/HKUDS/AI-Trader), re-architected as a REST API service for external orchestration and integration.

---
```

---

## Implementation Notes

### File Identification Strategy
1. Use `grep -r "AI-Trader" --exclude-dir=.git` to find all references
2. Use `grep -r "ai-trader" --exclude-dir=.git` for lowercase variants
3. Use `grep -r "github.com/HKUDS" --exclude-dir=.git` for old repo URLs
4. Use `grep -r "ghcr.io/hkuds" --exclude-dir=.git` for old Docker images

### Testing Between Phases
- After Phase 1: Review user-facing documentation for consistency
- After Phase 2: Test Docker build and deployment
- After Phase 3: Verify all documentation examples
- After Phase 4: Full integration test

### Rollback Plan
If issues arise:
1. Each phase should be committed separately
2. Use `git revert` to roll back individual phases
3. Re-validate after any rollback

---

## Success Criteria

- [ ] All references to "AI-Trader" updated to "AI-Trader-Server"
- [ ] All GitHub URLs point to `Xe138/AI-Trader-Server`
- [ ] All Docker references use `ghcr.io/xe138/ai-trader-server`
- [ ] Fork acknowledgment added to README
- [ ] Docker build succeeds with new naming
- [ ] All documentation links verified working
- [ ] No broken cross-references in documentation

---

## Out of Scope

The following items are **not** part of this rebrand:

- Changing Python class names (e.g., `BaseAgent`, internal classes)
- Updating actual git remote URLs (handled separately by user)
- Publishing to Docker registry (deployment task)
- Updating external references (blog posts, social media, etc.)
- Database schema or table name changes
- API endpoint paths (remain unchanged)

---

## Timeline Estimate

- **Phase 1:** ~15-20 minutes (4 core docs files)
- **Phase 2:** ~10-15 minutes (configuration files and Docker)
- **Phase 3:** ~30-40 minutes (extensive documentation tree)
- **Phase 4:** ~10 minutes (internal metadata)

**Total:** ~65-85 minutes of focused work across 4 validation checkpoints

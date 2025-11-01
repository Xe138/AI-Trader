# AI-Trader to AI-Trader-Server Rebrand Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rebrand the project from "AI-Trader" to "AI-Trader-Server" across all documentation, configuration, and Docker files to reflect its REST API service architecture.

**Architecture:** Layered approach with 4 phases: (1) Core user docs, (2) Configuration files, (3) Developer/deployment docs, (4) Internal metadata. Each phase has validation checkpoints.

**Tech Stack:** Markdown, JSON, YAML (docker-compose), Dockerfile, Shell scripts

---

## Phase 1: Core User-Facing Documentation

### Task 1: Update README.md

**Files:**
- Modify: `README.md`

**Step 1: Update title and tagline**

Replace line 3:
```markdown
# 🚀 AI-Trader: Can AI Beat the Market?
```

With:
```markdown
# 🚀 AI-Trader-Server: REST API for AI Trading
```

**Step 2: Update subtitle/description (line 10)**

Replace:
```markdown
**REST API service for autonomous AI trading competitions. Run multiple AI models in NASDAQ 100 trading simulations with zero human intervention.**
```

With:
```markdown
**REST API service for autonomous AI trading competitions. Deploy multiple AI models in NASDAQ 100 simulations via HTTP endpoints with zero human intervention.**
```

**Step 3: Update all GitHub repository URLs**

Find and replace all instances:
- `github.com/HKUDS/AI-Trader` → `github.com/Xe138/AI-Trader-Server`
- `github.com/Xe138/AI-Trader` → `github.com/Xe138/AI-Trader-Server`

Specific lines to check: 80, 455, 457

**Step 4: Update Docker image references**

Find and replace:
- `ghcr.io/hkuds/ai-trader` → `ghcr.io/xe138/ai-trader-server`

Specific lines: 456

**Step 5: Add fork acknowledgment section**

After line 446 (before License section), add:

```markdown
---

## 🙏 Acknowledgments

This project is a fork of [HKUDS/AI-Trader](https://github.com/HKUDS/AI-Trader), re-architected as a REST API service for external orchestration and integration.

---
```

**Step 6: Commit**

```bash
git add README.md
git commit -m "docs: rebrand README from AI-Trader to AI-Trader-Server"
```

---

### Task 2: Update QUICK_START.md

**Files:**
- Modify: `QUICK_START.md`

**Step 1: Search for repository references**

```bash
grep -n "github.com" QUICK_START.md
grep -n "ai-trader" QUICK_START.md
```

**Step 2: Update git clone command**

Find the git clone command and update:
```bash
git clone https://github.com/Xe138/AI-Trader-Server.git
cd AI-Trader-Server
```

**Step 3: Update Docker image references**

Replace all instances of:
- `ghcr.io/hkuds/ai-trader` → `ghcr.io/xe138/ai-trader-server`
- Container name `ai-trader` → `ai-trader-server` (if mentioned)

**Step 4: Update project name references**

Replace:
- "AI-Trader" → "AI-Trader-Server" in titles/headings
- Keep "ai-trader" lowercase in paths/commands as-is (will be handled in Docker phase)

**Step 5: Commit**

```bash
git add QUICK_START.md
git commit -m "docs: update QUICK_START for AI-Trader-Server rebrand"
```

---

### Task 3: Update API_REFERENCE.md

**Files:**
- Modify: `API_REFERENCE.md`

**Step 1: Update header and project references**

Find and replace:
- "AI-Trader" → "AI-Trader-Server" in titles
- GitHub URLs: `github.com/HKUDS/AI-Trader` or `github.com/Xe138/AI-Trader` → `github.com/Xe138/AI-Trader-Server`

**Step 2: Update Docker image references in examples**

Replace:
- `ghcr.io/hkuds/ai-trader` → `ghcr.io/xe138/ai-trader-server`

**Step 3: Commit**

```bash
git add API_REFERENCE.md
git commit -m "docs: rebrand API_REFERENCE to AI-Trader-Server"
```

---

### Task 4: Update CHANGELOG.md

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Add rebrand entry at top**

Add new entry at the top of the changelog:

```markdown
## [Unreleased]

### Changed
- Rebranded project from AI-Trader to AI-Trader-Server to reflect REST API service architecture
- Updated all repository references to github.com/Xe138/AI-Trader-Server
- Updated Docker image references to ghcr.io/xe138/ai-trader-server

```

**Step 2: Update any GitHub URLs in existing entries**

Find and replace:
- `github.com/HKUDS/AI-Trader` → `github.com/Xe138/AI-Trader-Server`

**Step 3: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: add rebrand entry to CHANGELOG"
```

---

### Task 5: Validate Phase 1

**Step 1: Check all links**

```bash
# Extract URLs and verify they exist
grep -oP 'https://github\.com/[^)\s]+' README.md QUICK_START.md API_REFERENCE.md
```

**Step 2: Search for any remaining old references**

```bash
grep -r "github.com/HKUDS" README.md QUICK_START.md API_REFERENCE.md CHANGELOG.md
grep -r "ghcr.io/hkuds" README.md QUICK_START.md API_REFERENCE.md CHANGELOG.md
```

Expected: No matches

**Step 3: Verify markdown renders correctly**

```bash
# If markdown linter available
markdownlint README.md QUICK_START.md API_REFERENCE.md || echo "Linter not available - manual review needed"
```

---

## Phase 2: Configuration Files

### Task 6: Update docker-compose.yml

**Files:**
- Modify: `docker-compose.yml`

**Step 1: Update service and container names**

Find the service definition and update:

```yaml
services:
  ai-trader-server:  # Changed from ai-trader
    container_name: ai-trader-server  # Changed from ai-trader
    image: ai-trader-server:latest  # Changed from ai-trader:latest
    # ... rest of config
```

**Step 2: Update any comments**

Replace "AI-Trader" references in comments with "AI-Trader-Server"

**Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "chore: update docker-compose service names for rebrand"
```

---

### Task 7: Update Dockerfile

**Files:**
- Modify: `Dockerfile`

**Step 1: Update LABEL metadata (if present)**

Find any LABEL instructions and update:

```dockerfile
LABEL org.opencontainers.image.title="AI-Trader-Server"
LABEL org.opencontainers.image.source="https://github.com/Xe138/AI-Trader-Server"
```

**Step 2: Update comments**

Replace "AI-Trader" in comments with "AI-Trader-Server"

**Step 3: Commit**

```bash
git add Dockerfile
git commit -m "chore: update Dockerfile metadata for rebrand"
```

---

### Task 8: Update .env.example

**Files:**
- Modify: `.env.example`

**Step 1: Update header comments**

If there's a header comment describing the project, update:

```bash
# AI-Trader-Server Configuration
# REST API service for autonomous AI trading
```

**Step 2: Update any inline comments mentioning project name**

Replace "AI-Trader" → "AI-Trader-Server" in explanatory comments

**Step 3: Commit**

```bash
git add .env.example
git commit -m "chore: update .env.example comments for rebrand"
```

---

### Task 9: Update configuration JSON files

**Files:**
- Modify: `configs/default_config.json`
- Modify: Any other JSON configs in `configs/`

**Step 1: Check for project name references**

```bash
grep -r "AI-Trader" configs/
```

**Step 2: Update comments if JSON allows (or metadata fields)**

If configs have metadata/description fields, update them:

```json
{
  "project": "AI-Trader-Server",
  "description": "REST API service configuration"
}
```

**Step 3: Commit**

```bash
git add configs/
git commit -m "chore: update config files for rebrand"
```

---

### Task 10: Validate Phase 2

**Step 1: Test Docker build**

```bash
docker build -t ai-trader-server:test .
```

Expected: Build succeeds

**Step 2: Test docker-compose syntax**

```bash
docker-compose config
```

Expected: No errors, shows parsed configuration

**Step 3: Search for remaining old references**

```bash
grep -r "ai-trader" docker-compose.yml Dockerfile .env.example configs/
```

Expected: Only lowercase "ai-trader-server" or necessary backward-compatible references

---

## Phase 3: Developer & Deployment Documentation

### Task 11: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Update project overview header**

Replace the first paragraph starting with "AI-Trader is..." with:

```markdown
AI-Trader-Server is an autonomous AI trading competition platform where multiple AI models compete in NASDAQ 100 trading with zero human intervention. Each AI starts with $10,000 and uses standardized MCP (Model Context Protocol) tools to make fully autonomous trading decisions.
```

**Step 2: Update Docker deployment commands**

Find all docker commands and update image names:
- `docker pull ghcr.io/hkuds/ai-trader:latest` → `docker pull ghcr.io/xe138/ai-trader-server:latest`
- `docker build -t ai-trader-test .` → `docker build -t ai-trader-server-test .`
- `docker run ... ai-trader-test` → `docker run ... ai-trader-server-test`

**Step 3: Update GitHub Actions URLs**

Replace:
- `https://github.com/HKUDS/AI-Trader/actions` → `https://github.com/Xe138/AI-Trader-Server/actions`

**Step 4: Update repository references**

Replace all instances of:
- `HKUDS/AI-Trader` → `Xe138/AI-Trader-Server`

**Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for AI-Trader-Server rebrand"
```

---

### Task 12: Update docs/user-guide/ documentation

**Files:**
- Modify: `docs/user-guide/configuration.md`
- Modify: `docs/user-guide/using-the-api.md`
- Modify: `docs/user-guide/integration-examples.md`
- Modify: `docs/user-guide/troubleshooting.md`

**Step 1: Batch find and replace project name**

```bash
cd docs/user-guide/
for file in *.md; do
  sed -i 's/AI-Trader\([^-]\)/AI-Trader-Server\1/g' "$file"
done
cd ../..
```

**Step 2: Update repository URLs**

```bash
cd docs/user-guide/
for file in *.md; do
  sed -i 's|github\.com/HKUDS/AI-Trader|github.com/Xe138/AI-Trader-Server|g' "$file"
  sed -i 's|github\.com/Xe138/AI-Trader\([^-]\)|github.com/Xe138/AI-Trader-Server\1|g' "$file"
done
cd ../..
```

**Step 3: Update Docker image references**

```bash
cd docs/user-guide/
for file in *.md; do
  sed -i 's|ghcr\.io/hkuds/ai-trader|ghcr.io/xe138/ai-trader-server|g' "$file"
done
cd ../..
```

**Step 4: Update code example class names in integration-examples.md**

Find and update:
```python
class AITraderClient:  # → AITraderServerClient
```

**Step 5: Commit**

```bash
git add docs/user-guide/
git commit -m "docs: rebrand user guide documentation"
```

---

### Task 13: Update docs/developer/ documentation

**Files:**
- Modify: `docs/developer/CONTRIBUTING.md`
- Modify: `docs/developer/development-setup.md`
- Modify: `docs/developer/testing.md`
- Modify: `docs/developer/architecture.md`
- Modify: `docs/developer/database-schema.md`
- Modify: `docs/developer/adding-models.md`

**Step 1: Batch find and replace project name**

```bash
cd docs/developer/
for file in *.md; do
  sed -i 's/AI-Trader\([^-]\)/AI-Trader-Server\1/g' "$file"
done
cd ../..
```

**Step 2: Update repository URLs**

```bash
cd docs/developer/
for file in *.md; do
  sed -i 's|github\.com/HKUDS/AI-Trader|github.com/Xe138/AI-Trader-Server|g' "$file"
  sed -i 's|github\.com/Xe138/AI-Trader\([^-]\)|github.com/Xe138/AI-Trader-Server\1|g' "$file"
done
cd ../..
```

**Step 3: Update Docker references**

```bash
cd docs/developer/
for file in *.md; do
  sed -i 's|ghcr\.io/hkuds/ai-trader|ghcr.io/xe138/ai-trader-server|g' "$file"
  sed -i 's/ai-trader-test/ai-trader-server-test/g' "$file"
done
cd ../..
```

**Step 4: Update architecture diagrams in architecture.md**

Manually review ASCII art diagrams and update labels:
- "AI-Trader" → "AI-Trader-Server"

**Step 5: Commit**

```bash
git add docs/developer/
git commit -m "docs: rebrand developer documentation"
```

---

### Task 14: Update docs/deployment/ documentation

**Files:**
- Modify: `docs/deployment/docker-deployment.md`
- Modify: `docs/deployment/production-checklist.md`
- Modify: `docs/deployment/monitoring.md`
- Modify: `docs/deployment/scaling.md`

**Step 1: Batch find and replace project name**

```bash
cd docs/deployment/
for file in *.md; do
  sed -i 's/AI-Trader\([^-]\)/AI-Trader-Server\1/g' "$file"
done
cd ../..
```

**Step 2: Update Docker image references**

```bash
cd docs/deployment/
for file in *.md; do
  sed -i 's|ghcr\.io/hkuds/ai-trader|ghcr.io/xe138/ai-trader-server|g' "$file"
  sed -i 's/container_name: ai-trader/container_name: ai-trader-server/g' "$file"
  sed -i 's/ai-trader:/ai-trader-server:/g' "$file"
done
cd ../..
```

**Step 3: Update monitoring commands**

Update any Docker exec commands:
```bash
docker exec -it ai-trader-server sqlite3 /app/data/jobs.db
```

**Step 4: Commit**

```bash
git add docs/deployment/
git commit -m "docs: rebrand deployment documentation"
```

---

### Task 15: Update docs/reference/ documentation

**Files:**
- Modify: `docs/reference/environment-variables.md`
- Modify: `docs/reference/mcp-tools.md`
- Modify: `docs/reference/data-formats.md`

**Step 1: Batch find and replace project name**

```bash
cd docs/reference/
for file in *.md; do
  sed -i 's/AI-Trader\([^-]\)/AI-Trader-Server\1/g' "$file"
done
cd ../..
```

**Step 2: Update any code examples or Docker references**

```bash
cd docs/reference/
for file in *.md; do
  sed -i 's|ghcr\.io/hkuds/ai-trader|ghcr.io/xe138/ai-trader-server|g' "$file"
done
cd ../..
```

**Step 3: Commit**

```bash
git add docs/reference/
git commit -m "docs: rebrand reference documentation"
```

---

### Task 16: Update root-level maintainer docs

**Files:**
- Modify: `docs/DOCKER.md` (if exists)
- Modify: `docs/RELEASING.md` (if exists)

**Step 1: Check if files exist**

```bash
ls -la docs/DOCKER.md docs/RELEASING.md 2>/dev/null || echo "Files may not exist"
```

**Step 2: Update project references if files exist**

```bash
if [ -f docs/DOCKER.md ]; then
  sed -i 's/AI-Trader\([^-]\)/AI-Trader-Server\1/g' docs/DOCKER.md
  sed -i 's|ghcr\.io/hkuds/ai-trader|ghcr.io/xe138/ai-trader-server|g' docs/DOCKER.md
fi

if [ -f docs/RELEASING.md ]; then
  sed -i 's/AI-Trader\([^-]\)/AI-Trader-Server\1/g' docs/RELEASING.md
  sed -i 's|github\.com/HKUDS/AI-Trader|github.com/Xe138/AI-Trader-Server|g' docs/RELEASING.md
fi
```

**Step 3: Commit if changes made**

```bash
git add docs/DOCKER.md docs/RELEASING.md 2>/dev/null && git commit -m "docs: rebrand maintainer documentation" || echo "No maintainer docs to commit"
```

---

### Task 17: Validate Phase 3

**Step 1: Search for remaining old references in docs**

```bash
grep -r "AI-Trader[^-]" docs/ --include="*.md" | grep -v "AI-Trader-Server"
```

Expected: No matches

**Step 2: Search for old repository URLs**

```bash
grep -r "github.com/HKUDS/AI-Trader" docs/ --include="*.md"
grep -r "github.com/Xe138/AI-Trader[^-]" docs/ --include="*.md"
```

Expected: No matches

**Step 3: Search for old Docker images**

```bash
grep -r "ghcr.io/hkuds/ai-trader" docs/ --include="*.md"
```

Expected: No matches

**Step 4: Verify documentation cross-references**

```bash
# Check for broken markdown links
find docs/ -name "*.md" -exec grep -H "\[.*\](.*\.md)" {} \;
```

Manual review needed: Verify links point to correct files

---

## Phase 4: Internal Configuration & Metadata

### Task 18: Update GitHub Actions workflows

**Files:**
- Check: `.github/workflows/` directory

**Step 1: Check if workflows exist**

```bash
ls -la .github/workflows/ 2>/dev/null || echo "No workflows directory"
```

**Step 2: Update workflow files if they exist**

```bash
if [ -d .github/workflows ]; then
  cd .github/workflows/
  for file in *.yml *.yaml; do
    [ -f "$file" ] || continue
    sed -i 's/AI-Trader\([^-]\)/AI-Trader-Server\1/g' "$file"
    sed -i 's|ghcr\.io/hkuds/ai-trader|ghcr.io/xe138/ai-trader-server|g' "$file"
    sed -i 's|github\.com/HKUDS/AI-Trader|github.com/Xe138/AI-Trader-Server|g' "$file"
  done
  cd ../..
fi
```

**Step 3: Commit if changes made**

```bash
git add .github/workflows/ 2>/dev/null && git commit -m "ci: update workflows for AI-Trader-Server rebrand" || echo "No workflows to commit"
```

---

### Task 19: Update shell scripts

**Files:**
- Check: `scripts/` directory and root-level `.sh` files

**Step 1: Find all shell scripts**

```bash
find . -maxdepth 2 -name "*.sh" -type f | grep -v ".git" | grep -v ".worktrees"
```

**Step 2: Update comments and echo statements in scripts**

```bash
for script in $(find . -maxdepth 2 -name "*.sh" -type f | grep -v ".git" | grep -v ".worktrees"); do
  sed -i 's/AI-Trader\([^-]\)/AI-Trader-Server\1/g' "$script"
  sed -i 's/ai-trader:/ai-trader-server:/g' "$script"
  sed -i 's/ai-trader-test/ai-trader-server-test/g' "$script"
done
```

**Step 3: Update Docker image references in scripts**

```bash
for script in $(find . -maxdepth 2 -name "*.sh" -type f | grep -v ".git" | grep -v ".worktrees"); do
  sed -i 's|ghcr\.io/hkuds/ai-trader|ghcr.io/xe138/ai-trader-server|g' "$script"
done
```

**Step 4: Commit changes**

```bash
git add scripts/ *.sh 2>/dev/null && git commit -m "chore: update shell scripts for rebrand" || echo "No scripts to commit"
```

---

### Task 20: Final validation and cleanup

**Step 1: Comprehensive search for old project name**

```bash
grep -r "AI-Trader[^-]" . --include="*.md" --include="*.json" --include="*.yml" --include="*.yaml" --include="*.sh" --include="Dockerfile" --include=".env.example" --exclude-dir=.git --exclude-dir=.worktrees --exclude-dir=node_modules --exclude-dir=venv | grep -v "AI-Trader-Server"
```

Expected: Only matches in Python code (if any), data files, or git history

**Step 2: Search for old repository URLs**

```bash
grep -r "github\.com/HKUDS/AI-Trader" . --include="*.md" --include="*.json" --include="*.yml" --include="*.yaml" --exclude-dir=.git --exclude-dir=.worktrees
grep -r "github\.com/Xe138/AI-Trader[^-]" . --include="*.md" --include="*.json" --include="*.yml" --include="*.yaml" --exclude-dir=.git --exclude-dir=.worktrees
```

Expected: No matches

**Step 3: Search for old Docker images**

```bash
grep -r "ghcr\.io/hkuds/ai-trader" . --include="*.md" --include="*.yml" --include="*.yaml" --include="Dockerfile" --include="*.sh" --exclude-dir=.git --exclude-dir=.worktrees
```

Expected: No matches

**Step 4: Test Docker build with new name**

```bash
docker build -t ai-trader-server:test .
```

Expected: Build succeeds

**Step 5: Test docker-compose validation**

```bash
docker-compose config
```

Expected: No errors, service name is `ai-trader-server`

**Step 6: Review git status**

```bash
git status
```

Expected: All changes committed, working tree clean

**Step 7: Review commit history**

```bash
git log --oneline -20
```

Expected: Should see commits for each phase of rebrand

---

## Validation Summary

After completing all tasks, verify:

- [ ] All "AI-Trader" references updated to "AI-Trader-Server" in documentation
- [ ] All GitHub URLs point to `github.com/Xe138/AI-Trader-Server`
- [ ] All Docker references use `ghcr.io/xe138/ai-trader-server`
- [ ] Fork acknowledgment added to README.md
- [ ] docker-compose.yml uses `ai-trader-server` service/container name
- [ ] All documentation cross-references work
- [ ] Docker build succeeds
- [ ] No broken links in documentation
- [ ] All changes committed with clear commit messages

---

## Notes

- **Python code:** No changes needed to class names or internal identifiers
- **Data files:** No changes needed to existing data or databases
- **Git remotes:** Repository remote URLs are separate and handled by user
- **Docker registry:** Publishing new images is a separate deployment task
- **Backward compatibility:** This is a clean-break rebrand, no compatibility needed

---

## Estimated Time

- **Phase 1:** 15-20 minutes (4 core docs)
- **Phase 2:** 10-15 minutes (configs and Docker)
- **Phase 3:** 30-40 minutes (all docs subdirectories)
- **Phase 4:** 10-15 minutes (workflows and scripts)
- **Total:** ~65-90 minutes

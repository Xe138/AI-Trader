# Release Process

## Creating a New Release

### 1. Prepare Release

1. Ensure `main` branch is stable and tests pass
2. Update version numbers if needed
3. Update CHANGELOG.md with release notes

### 2. Create Release Tag

```bash
# Ensure on main branch
git checkout main
git pull origin main

# Create annotated tag
git tag -a v1.0.0 -m "Release v1.0.0: Docker deployment support"

# Push tag to trigger CI/CD
git push origin v1.0.0
```

### 3. GitHub Actions Automation

Tag push automatically triggers `.github/workflows/docker-release.yml`:

1. ✅ Checks out code
2. ✅ Sets up Docker Buildx
3. ✅ Logs into GitHub Container Registry
4. ✅ Extracts version from tag
5. ✅ Builds Docker image with caching
6. ✅ Pushes to `ghcr.io/xe138/ai-trader-server:VERSION`
7. ✅ Pushes to `ghcr.io/xe138/ai-trader-server:latest`

### 4. Verify Build

1. Check GitHub Actions: https://github.com/Xe138/AI-Trader-Server/actions
2. Verify workflow completed successfully (green checkmark)
3. Check packages: https://github.com/Xe138/AI-Trader-Server/pkgs/container/ai-trader-server

### 5. Test Release

```bash
# Pull released image
docker pull ghcr.io/xe138/ai-trader-server:v1.0.0

# Test run
docker run --env-file .env \
  -v $(pwd)/data:/app/data \
  ghcr.io/xe138/ai-trader-server:v1.0.0
```

### 6. Create GitHub Release (Optional)

1. Go to https://github.com/Xe138/AI-Trader-Server/releases/new
2. Select tag: `v1.0.0`
3. Release title: `v1.0.0 - Docker Deployment Support`
4. Add release notes:

```markdown
## 🐳 Docker Deployment

This release adds full Docker support for easy deployment.

### Pull and Run

```bash
docker pull ghcr.io/xe138/ai-trader-server:v1.0.0
docker run --env-file .env -v $(pwd)/data:/app/data ghcr.io/xe138/ai-trader-server:v1.0.0
```

Or use Docker Compose:

```bash
docker-compose up
```

See [docs/DOCKER.md](docs/DOCKER.md) for details.

### What's New
- Docker containerization with single-container architecture
- docker-compose.yml for easy orchestration
- Automated CI/CD builds on release tags
- Pre-built images on GitHub Container Registry
```

5. Publish release

## Version Numbering

Use Semantic Versioning (SEMVER):

- `v1.0.0` - Major release (breaking changes)
- `v1.1.0` - Minor release (new features, backward compatible)
- `v1.1.1` - Patch release (bug fixes)

## Troubleshooting Releases

### Build Fails in GitHub Actions

1. Check Actions logs for error details
2. Test local build: `docker build .`
3. Fix issues and delete/recreate tag:

```bash
# Delete tag
git tag -d v1.0.0
git push origin :refs/tags/v1.0.0

# Recreate after fixes
git tag v1.0.0
git push origin v1.0.0
```

### Image Not Appearing in Registry

1. Check Actions permissions (Settings → Actions → General)
2. Verify `packages: write` permission in workflow
3. Ensure `GITHUB_TOKEN` has registry access

### Wrong Version Tagged

Delete and recreate:

```bash
git tag -d v1.0.0
git push origin :refs/tags/v1.0.0
git tag v1.0.1
git push origin v1.0.1
```

## Manual Build and Push

If automated build fails, manual push:

```bash
# Build locally
docker build -t ghcr.io/xe138/ai-trader-server:v1.0.0 .

# Login to GHCR
echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin

# Push
docker push ghcr.io/xe138/ai-trader-server:v1.0.0
docker tag ghcr.io/xe138/ai-trader-server:v1.0.0 ghcr.io/xe138/ai-trader-server:latest
docker push ghcr.io/xe138/ai-trader-server:latest
```

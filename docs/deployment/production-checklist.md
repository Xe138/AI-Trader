# Production Deployment Checklist

Pre-deployment verification.

---

## Pre-Deployment

- [ ] API keys configured in `.env`
- [ ] Environment variables reviewed
- [ ] Model configuration validated
- [ ] Port availability confirmed
- [ ] Volume mounts configured
- [ ] Health checks enabled
- [ ] Restart policy set

---

## Testing

- [ ] `bash scripts/validate_docker_build.sh` passes
- [ ] `bash scripts/test_api_endpoints.sh` passes
- [ ] Health endpoint responds correctly
- [ ] Sample simulation completes successfully

---

## Monitoring

- [ ] Log aggregation configured
- [ ] Health check monitoring enabled
- [ ] Alerting configured for failures
- [ ] Database backup strategy defined

---

## Security

- [ ] API keys stored securely (not in code)
- [ ] `.env` excluded from version control
- [ ] Network access restricted
- [ ] SSL/TLS configured (if exposing publicly)

---

## Documentation

- [ ] Runbook created for operations team
- [ ] Escalation procedures documented
- [ ] Recovery procedures tested

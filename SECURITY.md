# Security Policy

## Supported Versions

This project is an MVP / take-home demonstration. Only the latest commit on `main` is supported.

## Reporting a Vulnerability

If you discover a security vulnerability, **do not open a public GitHub issue.**

Please report it by emailing the maintainer directly (contact info in the GitHub profile). Include:

- A description of the vulnerability and its potential impact
- Steps to reproduce or a proof-of-concept
- Any suggested mitigations

You can expect an acknowledgement within 48 hours.

## Security Practices in This Codebase

| Practice | Status |
|---|---|
| Secrets in repo | Never — all secrets via environment variables |
| CORS | Restricted to configured origins (default: localhost only) |
| Input validation | Pydantic models validate all incoming request bodies |
| Error responses | No internal stack traces exposed to clients |
| Dependency pinning | Approximate pins in `pyproject.toml`; lock with `uv lock` for prod |
| Auth | Not implemented in MVP — required before any production deployment |

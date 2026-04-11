# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| main    | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in SlideSherlock, please report it responsibly.

**Do not open a public GitHub issue for security vulnerabilities.**

Instead, please email the maintainers directly. Include:

- A description of the vulnerability
- Steps to reproduce
- The potential impact
- Any suggested fix (optional)

We will acknowledge receipt within 48 hours and provide a timeline for a fix.

## Security Considerations

### API Keys and Credentials

SlideSherlock integrates with external services (OpenAI, MinIO/S3, PostgreSQL). When deploying:

- Never commit `.env` files or API keys to version control
- Use environment variables for all credentials
- Rotate default credentials in `docker-compose.yml` before any non-local deployment
- The `alembic.ini` file contains a placeholder database URL; always override via `DATABASE_URL` environment variable in production

### File Upload Security

SlideSherlock accepts `.pptx` file uploads. The application:

- Validates file extensions before processing
- Processes files in isolated temporary directories
- Does not execute macros or embedded scripts from uploaded files

### Dependencies

We recommend running `pip-audit` regularly to check for known vulnerabilities in Python dependencies. See `requirements-dev.txt` for the audit tooling.

## Skills

Skills are globally installed and available to Claude Code. See below for where they're located.

### Globally Installed Skills
- **playwright** — Browser automation workflows for scraping, navigation, screenshots, and UI flow debugging.
  - Location: `C:/Users/aaiit/.codex/skills/playwright/`
- **security-best-practices** — Security best-practice review guidance for Python/JS/TS/Go code.
  - Location: `C:/Users/aaiit/.codex/skills/security-best-practices/`
- **security-threat-model** — Repository-grounded AppSec threat modeling workflow.
  - Location: `C:/Users/aaiit/.codex/skills/security-threat-model/`
- **async-python-patterns** — Master Python asyncio, concurrent programming, and async/await patterns for high-performance applications.
  - Location: `C:/Users/aaiit/.agents/skills/async-python-patterns/`
- **python-testing-patterns** — Comprehensive testing strategies with pytest, fixtures, mocking, and TDD.
  - Location: `C:/Users/aaiit/.agents/skills/python-testing-patterns/`
- **python-error-handling** — Python error handling patterns including input validation, exception hierarchies, and partial failure handling.
  - Location: `C:/Users/aaiit/.agents/skills/python-error-handling/`
- **python-code-style** — Python code style, linting, formatting, naming conventions, and documentation standards.
  - Location: `C:/Users/aaiit/.agents/skills/python-code-style/`
- **python-resilience** — Python resilience patterns including automatic retries, exponential backoff, timeouts, and fault-tolerant decorators.
  - Location: `C:/Users/aaiit/.agents/skills/python-resilience/`
- **github-actions-templates** — Production-ready GitHub Actions workflows for automated testing, building, and deploying.
  - Location: `C:/Users/aaiit/.agents/skills/github-actions-templates/`

### Notes
- All skills are globally installed in `C:/Users/aaiit/.codex/skills/` or `C:/Users/aaiit/.agents/skills/`
- Local `.agents/` and `.claude/` directories are ignored (see `.gitignore`)
- Use npx skills to manage global skills: `npx skills list`, `npx skills add`, etc.

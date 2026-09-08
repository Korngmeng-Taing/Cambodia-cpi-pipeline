# Agent Rules & Execution Guidelines

This repository follows the mandatory rules documented in [AGENTS.md](file:///D:/CPI%20PIPELINE/AGENTS.md).

## ⚠️ STRICT DIRECTIVE: Model Context Protocol (MCP) & Skill First

1. **NEVER use shell commands (`run_command`) for tasks supported by MCP tools or skills.**
2. **Postgres queries**: ALWAYS use MCP `postgres` -> `query`.
3. **Docker operations**: ALWAYS use MCP `docker` -> `list_containers`, `fetch_container_logs`, etc.
4. **Airflow / Cosmos / Pytest / Scraping**: ALWAYS consult and follow the corresponding `SKILL.md` before executing.

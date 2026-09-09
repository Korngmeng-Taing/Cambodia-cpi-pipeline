# Agent Rules & Execution Guidelines

This repository follows the mandatory rules documented in [AGENTS.md](file:///D:/CPI%20PIPELINE/AGENTS.md).

## ⚠️ STRICT DIRECTIVE: Skill & MCP First Policy
 
1. **Skills First**: ALWAYS consult and follow the corresponding `SKILL.md` (Airflow, Cosmos/dbt, Docker Compose, Pytest, Scraping) first to establish the correct architecture, patterns, and workflow before executing tasks.
2. **MCP over Shell**: Within workflows or execution steps, ALWAYS use MCP tools (`postgres`, `docker`, `playwright`, `github`, etc.) instead of raw shell commands.
3. **NEVER use shell commands (`run_command`) for tasks directly supported by MCP tools.**
4. **Postgres queries**: ALWAYS use MCP `postgres` -> `query`.
5. **Docker operations**: ALWAYS use MCP `docker` -> `list_containers`, `fetch_container_logs`, etc.

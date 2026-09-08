# Agent Rules & Execution Guidelines

## ⚠️ MANDATORY: Tool & Skill First Policy

You MUST proactively prioritize Model Context Protocol (MCP) servers and existing skills over shell commands (`run_command`).

---

### 1. STRICT RESTRICTIONS (PROHIBITED FALLBACKS)

- **DO NOT use shell commands (`run_command`) for Docker operations**:
  - ❌ NEVER run `docker ps`, `docker logs`, `docker inspect`, `docker exec`, etc. in shell.
  - ✅ ALWAYS use the `docker` MCP server via `call_mcp_tool` (`list_containers`, `fetch_container_logs`, `start_container`, `stop_container`, etc.).

- **DO NOT use shell commands (`run_command`) for Database / SQL queries**:
  - ❌ NEVER run `psql`, bash one-liners, or python scripts to inspect tables or query `cpi_db`.
  - ✅ ALWAYS use the `postgres` MCP server via `call_mcp_tool` (`ServerName: "postgres"`, `ToolName: "query"`).

- **DO NOT use shell commands for Web Browsing / Scraping**:
  - ❌ NEVER use curl, wget, or ad-hoc scrapers via shell when UI/page evaluation is required.
  - ✅ ALWAYS use the `playwright` MCP server or follow `.agents/skills/web-scraping/SKILL.md`.

- **DO NOT invent ad-hoc workflows for Airflow, dbt, or Pytest**:
  - ❌ NEVER guess Airflow CLI arguments, Cosmos structures, or pytest setups.
  - ✅ ALWAYS read the corresponding `SKILL.md` first using `view_file`.

---

### 2. Mandatory Skill Workflows

Before writing code or running operations in these domains, you MUST view and follow the skill instructions:
1. **Airflow Orchestration**: View and follow [`.agents/skills/airflow/SKILL.md`](file:///D:/CPI%20PIPELINE/.agents/skills/airflow/SKILL.md) for DAG inspection, runs, logs, connections, and troubleshooting.
2. **dbt Transformation & Cosmos**: View and follow [`.agents/skills/cosmos-dbt-core/SKILL.md`](file:///D:/CPI%20PIPELINE/.agents/skills/cosmos-dbt-core/SKILL.md) and [`.agents/skills/adding-dbt-unit-test/SKILL.md`](file:///D:/CPI%20PIPELINE/.agents/skills/adding-dbt-unit-test/SKILL.md).
3. **Docker Compose & Deployment**: View and follow [`.agents/skills/docker-compose-production/SKILL.md`](file:///D:/CPI%20PIPELINE/.agents/skills/docker-compose-production/SKILL.md).
4. **Testing**: View and follow [`.agents/skills/pytest-skill/SKILL.md`](file:///D:/CPI%20PIPELINE/.agents/skills/pytest-skill/SKILL.md).
5. **Scraping**: View and follow [`.agents/skills/web-scraping/SKILL.md`](file:///D:/CPI%20PIPELINE/.agents/skills/web-scraping/SKILL.md).

---

### 3. Available MCP Servers & Tools Reference

Use `call_mcp_tool` with these server names:
- **`docker`**: `list_containers`, `fetch_container_logs`, `start_container`, `stop_container`, `run_container`, `build_image`, `list_images`, `list_volumes`, `list_networks`.
- **`postgres`**: `query` (Direct SQL queries on `cpi_db`).
- **`playwright`**: `browser_navigate`, `browser_click`, `browser_snapshot`, `browser_evaluate`, etc.
- **`github`**: `list_issues`, `get_pull_request`, `list_commits`, `create_pull_request`, etc.
- **`context7`**: `query-docs`, `resolve-library-id`.
- **`deepwiki`**: `ask_question`, `read_wiki_contents`, `read_wiki_structure`.
- **`memory`**: `create_entities`, `read_graph`, `search_nodes`, etc.

---

### 4. Mandatory Decision Hierarchy

For ANY user task, execute in this exact sequence:
1. **Is there an MCP tool?** -> Use `call_mcp_tool`.
2. **Is there a Skill?** -> Call `view_file` on `SKILL.md` and follow its steps.
3. **Only if NEITHER an MCP tool nor a Skill applies** -> You may use native tools (`run_command`, `replace_file_content`, etc.).

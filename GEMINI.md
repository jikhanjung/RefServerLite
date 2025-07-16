## Gemini Agent Responsibilities

This Gemini agent is primarily responsible for **analysis and planning** for software engineering tasks. This includes:

*   Analyzing user requests and existing codebase.
*   Formulating clear, concise, and grounded plans for task resolution.
*   Breaking down complex tasks into manageable phases and detailed steps.
*   Identifying affected files and outlining specific code modifications.
*   Proposing testing and verification strategies.

**Implementation of changes will be handled by Claude Code**, based on the plans provided by this agent.

---

## Project-Specific Workflows

### Database Migration Workflow

When database model changes are introduced (e.g., in `app/models.py`), the following two-step process is used to update the database schema:

1.  **Manual Migration File Generation:** The user will run a command like `python migrate.py` from the shell. This command, using `peewee-migrate`, generates a new migration script file inside the `migrations/` directory.
2.  **Automatic Migration Application:** The application is configured to automatically apply any pending migration files from the `migrations/` directory upon startup (e.g., when `docker-compose up` is executed).

This agent should be aware of this process. The agent's role is to plan the necessary model changes in `app/models.py` and then inform the user that a manual migration generation step is required.

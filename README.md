# ai-my-tickets
Exploring AI interactions with a basic ticketing system. 

(Project development and documentation assisted by ChatGPT)

## 1. Ticketing API

### Overview
The Ticketing API is a Django REST Framework service that lets you track support tickets end-to-end. It exposes CRUD endpoints backed by SQLite, requires no authentication for this proof-of-concept, and is designed to be easy to script against or plug into an AI assistant.

### Capabilities at a Glance
- Manage tickets with `title`, `description`, `created`, and `resolution_status` fields.
- Enforce a simple workflow via enumerated statuses: `OPEN`, `RESOLVED`, and `CLOSED`.
- Filter, search, and order ticket listings using query parameters (e.g. `?resolution_status=OPEN`, `?search=outage`, `?ordering=created`).
- Receive precise error responses for missing tickets, invalid fields, or unsupported status transitions.

### Running the API

### Environment Variables
The Django settings load a `.env` file from `ticket_system/` at startup. Create `ticket_system/.env` (or set equivalent environment variables) before running the service and define at least:

```
DJANGO_SECRET=dev-secret-key-change-me
```

Pick any sufficiently random string for local development. Docker Compose mounts the project directory so the same file is reused inside the container.

#### Option A – Docker Compose (recommended for parity with the AI agent)
```bash
# From the repo root
docker compose up --build ticket_system
```
The API becomes available at `http://localhost:8000/api/`. Stop the service with `Ctrl+C` or `docker compose down`.

#### Option B – Local Python environment
```bash
cd ticket_system
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

### API Surface
Base URL: `http://localhost:8000/api/tickets/`

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/tickets/` | List tickets. Supports filtering, search, and ordering. |
| POST | `/api/tickets/` | Create a new ticket (title + description, optional resolution status). |
| GET | `/api/tickets/{id}/` | Retrieve a single ticket by id. |
| PUT | `/api/tickets/{id}/` | Replace a ticket entirely. Must include all writable fields. |
| PATCH | `/api/tickets/{id}/` | Partially update a ticket (commonly used to change status). |
| DELETE | `/api/tickets/{id}/` | Delete a ticket. |

Ticket schema (JSON):
```json
{
  "id": 1,
  "title": "Email outage",
  "description": "Outbound mail has been failing since 9am UTC.",
  "created": "2025-01-08T14:15:22.123456Z",
  "resolution_status": "OPEN"
}
```

### Query Helpers
- **Filtering:** `?id=1`, `?id__in=1,2`, `?title__icontains=outage`, `?created__gte=2025-01-01T00:00:00Z`, `?resolution_status__in=OPEN,CLOSED`
- **Search:** `?search=payment` performs a fuzzy match on title and description.
- **Ordering:** `?ordering=created` or `?ordering=-title`

### Example Calls
Create a ticket:
```bash
curl -X POST http://localhost:8000/api/tickets/ \
  -H "Content-Type: application/json" \
  -d '{
        "title": "VPN outage",
        "description": "Users cannot reach corporate resources.",
        "resolution_status": "OPEN"
      }'
```

Update status to resolved:
```bash
curl -X PATCH http://localhost:8000/api/tickets/1/ \
  -H "Content-Type: application/json" \
  -d '{"resolution_status": "RESOLVED"}'
```

Handle missing resources and validation errors:
- `404 Not Found` with message `Ticket with id '123' was not found.` when a ticket is missing.
- `422 Unprocessable Entity` when you send an unsupported status (e.g. `"resolution_status": "DONE"`).
- `400 Bad Request` listing any unexpected fields supplied in the payload.

### Admin console (optional)
If you create a Django superuser, you can manage tickets at `http://localhost:8000/admin/` while the server is running.

## 2. AI Agent

### Overview
The AI agent is a FastAPI service that wraps a LangGraph/LangChain workflow backed by Azure OpenAI. It listens for HTTP requests, calls the ticketing tools it needs (list, filter, or create tickets), and streams the model's responses back to clients using Server-Sent Events (SSE).

### Environment Variables
Create `ai_agent/.env` (Docker Compose loads it automatically) and provide the following keys before starting the container or local server:

```
AZURE_OPENAI_ENDPOINT=https://<your-azure-openai-endpoint>/
AZURE_OPENAI_API_KEY=<key-with-access-to-the-deployments>
AZURE_OPENAI_API_VERSION=<your-api-version>
AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-4o
AZURE_OPENAI_CHAT_DEPLOYMENT_MINI=gpt-4o-mini
AGENT_PORT=8100
```

The two deployment names can point to any chat-capable models you have provisioned (one main, one lighter-weight).

### Running the Agent

#### Option A – Docker Compose
```bash
# From the repo root
docker compose up --build ai_agent
```
The service boots once the ticket system container is healthy and serves SSE responses at `http://localhost:8100/chat`. Stop the service with `Ctrl+C` or `docker compose down`.

#### Option B – Local Python environment
```bash
cd ai_agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```
The server starts on `0.0.0.0:$AGENT_PORT` and reloads on code changes.

### Request Flow
- Call `GET /chat?message=<text>` to send a user prompt.
- The handler relays the message through the routing agent, which may call the ticket tools or sub-agents as needed.
- Responses stream back as SSE frames (`event: token`, `event: end`, or `event: error`).

### Example Client Call
```bash
curl -N "http://localhost:8100/chat?message=Create%20a%20ticket%20about%20email%20failures"
```
`curl -N` keeps the connection open so you can watch the streamed tokens arrive in real time. The agent will create a ticket via the API and summarize the outcome.

### CLI Client
`ai_agent/cli.py` streams SSE responses from the agent and prints them as they arrive. Run it from the repo root after installing the agent dependencies (via Docker Compose or a local virtualenv).

```bash
python ai_agent/cli.py "List all open tickets"
```

The optional second argument overrides the base URL (defaults to `http://127.0.0.1:8100`). For example, to target Docker Compose on localhost:

```bash
python ai_agent/cli.py "Create a ticket for the VPN outage" http://localhost:8100
```

Use `Ctrl+C` to stop streaming early; the script closes automatically when it receives the agent's `end` event.

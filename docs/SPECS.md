# Specs

Each spec is a discrete, implementable unit of work. Specs are ordered by dependency — later specs may depend on earlier ones. Each spec includes acceptance criteria that can be verified by tests.

Specs are grouped by phase. Complete all specs in a phase before moving to the next.

---

## Phase 1: Core Infrastructure

### SPEC-001: Project scaffolding

**Goal:** Set up the Python project structure, dependencies, and test infrastructure.

**Work:**
- Create `pyproject.toml` with project metadata and dependencies: `anthropic`, `websockets`, `pytest`, `pytest-asyncio`
- Create directory structure:
  ```
  src/
    voicefront/
      __init__.py
      agents/
        __init__.py
        base.py
      events/
        __init__.py
        bus.py
      server/
        __init__.py
      generated/
        index.html
        style.css
        script.js
  tests/
    __init__.py
    test_events.py
    test_agents.py
  ```
- Create a starter `generated/index.html` with minimal boilerplate
- Verify `pytest` discovers and runs tests

**Acceptance criteria:**
- [ ] `pip install -e .` succeeds
- [ ] `pytest` runs and reports 0 errors
- [ ] directory structure matches spec
- [ ] `generated/index.html` is valid HTML

---

### SPEC-002: EventBus

**Goal:** Implement the pub/sub event system that agents use to communicate.

**Dependencies:** SPEC-001

**Work:**
- Implement `EventBus` class in `src/voicefront/events/bus.py`
- Support: `subscribe(event_type, callback)`, `emit(event_type, payload)`, `unsubscribe(event_type, callback)`
- Callbacks can be sync or async
- Events are processed in subscription order
- Include type definitions for all event types listed in ARCHITECTURE.md

**Acceptance criteria:**
- [ ] Test: subscribing to an event and emitting it calls the callback with correct payload
- [ ] Test: multiple subscribers receive the same event
- [ ] Test: unsubscribed callbacks are not called
- [ ] Test: async callbacks are awaited correctly
- [ ] Test: emitting an event with no subscribers does not error

---

### SPEC-003: BaseAgent

**Goal:** Implement the abstract base class for all agents.

**Dependencies:** SPEC-002

**Work:**
- Implement `BaseAgent` class in `src/voicefront/agents/base.py`
- Constructor accepts: `name: str`, `event_bus: EventBus`, `claude_client: anthropic.Anthropic`
- Abstract method: `async handle(event_type: str, payload: dict) -> None`
- Concrete methods: `subscribe(event_type)`, `emit(event_type, payload)`
- Built-in logging: log every event received and emitted with agent name and timestamp

**Acceptance criteria:**
- [ ] Test: subclass can be instantiated with required args
- [ ] Test: calling subscribe registers the agent's handle method on the event bus
- [ ] Test: calling emit publishes to the event bus
- [ ] Test: instantiating BaseAgent directly raises TypeError (abstract)

---

## Phase 1: Agents

### SPEC-004: Intent Parser Agent

**Goal:** Implement the agent that converts raw transcript text into structured tasks.

**Dependencies:** SPEC-003

**Work:**
- Implement `IntentParserAgent` in `src/voicefront/agents/intent_parser.py`
- Subscribes to: `transcript_ready`
- Emits: `tasks_parsed`
- Define `Task` dataclass: `target: str`, `action: str`, `value: str | None`, `description: str`
- Send transcript to Claude API with system prompt that returns JSON array of tasks
- Parse Claude response into `Task` objects
- Handle malformed Claude responses gracefully (log error, emit empty task list)

**Acceptance criteria:**
- [ ] Test: given a mock Claude response with valid JSON, emits correct Task objects
- [ ] Test: given a mock Claude response with invalid JSON, logs error and emits empty task list
- [ ] Test: system prompt instructs Claude to return a JSON array with target/action/value/description fields
- [ ] Test: subscribes to `transcript_ready` on initialization

---

### SPEC-005: Writer Agent

**Goal:** Implement the agent that generates and modifies frontend code.

**Dependencies:** SPEC-003

**Work:**
- Implement `WriterAgent` in `src/voicefront/agents/writer.py`
- Subscribes to: `task_assigned`
- Emits: `file_changed`
- On receiving a task:
  1. Read current contents of target file(s) from `generated/` directory
  2. Send task description + current file contents to Claude API
  3. Claude returns the full updated file content
  4. Write updated content to the file
  5. Compute a simple diff (before/after) and emit `file_changed`
- System prompt instructs Claude to return ONLY the file contents, no markdown fences or explanation

**Acceptance criteria:**
- [ ] Test: given a mock Claude response, writes correct content to the target file
- [ ] Test: emits `file_changed` event with file path and diff
- [ ] Test: reads current file contents before sending to Claude
- [ ] Test: handles file not existing yet (creates it)

---

### SPEC-006: Code Reviewer Agent

**Goal:** Implement the agent that reviews generated code for quality.

**Dependencies:** SPEC-003

**Work:**
- Implement `CodeReviewerAgent` in `src/voicefront/agents/reviewer.py`
- Subscribes to: `file_changed`
- Emits: `review_complete`
- On receiving a file change:
  1. Read the changed file contents
  2. Send to Claude API with review prompt
  3. Claude returns JSON: `{approved: bool, issues: [string]}`
  4. If not approved and retry count < 2: emit `task_assigned` to trigger Writer revision
  5. If approved or max retries reached: emit `review_complete`
- Track retry count per task

**Acceptance criteria:**
- [ ] Test: approved review emits `review_complete` with `approved: true`
- [ ] Test: rejected review with retries remaining re-emits `task_assigned`
- [ ] Test: rejected review at max retries emits `review_complete` with `approved: false`
- [ ] Test: handles malformed Claude response gracefully

---

### SPEC-007: Orchestrator

**Goal:** Implement the central coordinator that routes tasks to agents.

**Dependencies:** SPEC-004, SPEC-005, SPEC-006

**Work:**
- Implement `Orchestrator` in `src/voicefront/agents/orchestrator.py`
- Subscribes to: `tasks_parsed`, `review_complete`, `build_result`
- Emits: `task_assigned`
- On `tasks_parsed`: iterate tasks and emit `task_assigned` for each (sequentially in phase 1)
- On `review_complete`: if approved, trigger build validation; if rejected, log and continue
- Track overall pipeline status: idle, processing, error
- Expose method: `get_status() -> dict` returning current pipeline state

**Acceptance criteria:**
- [ ] Test: receiving `tasks_parsed` with 2 tasks emits 2 `task_assigned` events
- [ ] Test: receiving `review_complete` with approved=true triggers next step
- [ ] Test: status transitions correctly: idle -> processing -> idle
- [ ] Test: empty task list does not error, status returns to idle

---

### SPEC-008: Build Validator

**Goal:** Implement basic validation that generated code is parseable.

**Dependencies:** SPEC-003

**Work:**
- Implement `BuildValidator` in `src/voicefront/agents/validator.py`
- Subscribes to: `review_complete` (only when approved)
- Emits: `build_result`
- Validation checks:
  1. HTML: use Python `html.parser` — parse without errors
  2. CSS: regex check for unmatched braces (basic)
  3. JS: use `subprocess` to call `node --check` if node available, else regex for obvious syntax errors
- Collect all errors and emit `build_result` with pass/fail

**Acceptance criteria:**
- [ ] Test: valid HTML/CSS/JS passes validation
- [ ] Test: HTML with unclosed tags fails validation with descriptive error
- [ ] Test: CSS with unmatched braces fails validation
- [ ] Test: JS with syntax error fails validation (if node available)
- [ ] Test: missing files are reported as errors, not exceptions

---

## Phase 1: Frontend and Integration

### SPEC-009: WebSocket live reload server

**Goal:** Implement a WebSocket server that pushes reload signals to the browser.

**Dependencies:** SPEC-002

**Work:**
- Implement `ReloadServer` in `src/voicefront/server/reload.py`
- Start a WebSocket server on a configurable port (default: 8765)
- Subscribe to `build_result` events on the EventBus
- On `build_result` with `passed: true`: send `{"type": "reload"}` to all connected clients
- On `build_result` with `passed: false`: send `{"type": "error", "errors": [...]}` to connected clients
- Serve `generated/` directory over HTTP on a configurable port (default: 8080)

**Acceptance criteria:**
- [ ] Test: WebSocket client receives reload message after build_result with passed=true
- [ ] Test: WebSocket client receives error message after build_result with passed=false
- [ ] Test: HTTP server serves files from generated/ directory
- [ ] Test: multiple WebSocket clients all receive messages

---

### SPEC-010: Browser client with speech-to-text

**Goal:** Create the browser-side HTML page that captures voice and connects to the backend.

**Dependencies:** SPEC-009

**Work:**
- Create `src/voicefront/server/client.html` — a control page (separate from the generated preview)
- Implement Web Speech API integration:
  1. Start speech recognition on page load (request microphone permission)
  2. Capture interim and final results
  3. On final result: send transcript via WebSocket to backend as `{"type": "transcript", "text": "..."}`
  4. Display transcript history on page
- Implement preview panel:
  1. Embed an iframe pointing to the generated/ HTTP server
  2. On receiving `{"type": "reload"}` via WebSocket: reload the iframe
  3. On receiving `{"type": "error"}`: display errors below the iframe
- Minimal styling: split layout with transcript on left, preview iframe on right

**Acceptance criteria:**
- [ ] Manual test: opening in Chrome prompts for microphone permission
- [ ] Manual test: speaking produces transcript text displayed on page
- [ ] Manual test: iframe shows generated/index.html content
- [ ] Code review: Web Speech API usage follows MDN documentation patterns

---

### SPEC-011: Main entry point and end-to-end wiring

**Goal:** Wire all components together into a runnable application.

**Dependencies:** SPEC-004 through SPEC-010

**Work:**
- Create `src/voicefront/main.py`:
  1. Load `ANTHROPIC_API_KEY` from `.env` file
  2. Instantiate `EventBus`
  3. Instantiate Claude client
  4. Instantiate all agents, passing event bus and client
  5. Start WebSocket server
  6. Start HTTP server
  7. Listen for WebSocket messages from browser client
  8. On receiving transcript message: emit `transcript_ready` on event bus
  9. Handle graceful shutdown (Ctrl+C)
- Create `.env.example` with `ANTHROPIC_API_KEY=your-key-here`
- Add run instructions to README

**Acceptance criteria:**
- [ ] Test: application starts without errors when given a valid API key
- [ ] Test: receiving a transcript message triggers the full pipeline (mock Claude responses)
- [ ] Test: Ctrl+C shuts down cleanly
- [ ] `.env.example` exists and is documented in README

---

## Phase 2: Multi-Agent Parallelism

### SPEC-012: Parallel Writer execution

**Goal:** Allow the Orchestrator to dispatch tasks to multiple Writers simultaneously.

**Dependencies:** SPEC-011

**Work:**
- Modify Orchestrator to maintain a pool of Writer agents
- Dispatch independent tasks to different Writers using `asyncio.gather`
- Tasks targeting the same file must still be sequential
- Track which Writer is handling which task

**Acceptance criteria:**
- [ ] Test: 2 tasks targeting different files execute in parallel (wall time < sequential)
- [ ] Test: 2 tasks targeting the same file execute sequentially
- [ ] Test: Writer failure does not block other Writers

---

### SPEC-013: Conflict Resolver Agent

**Goal:** Merge changes when parallel Writers modify related files.

**Dependencies:** SPEC-012

**Work:**
- Implement `ConflictResolverAgent` in `src/voicefront/agents/conflict_resolver.py`
- Detect when multiple Writers changed files in the same batch
- For non-overlapping changes: merge automatically
- For overlapping changes: send both versions to Claude API to produce merged output
- Emit `file_changed` with merged result

**Acceptance criteria:**
- [ ] Test: non-overlapping changes merge without Claude API call
- [ ] Test: overlapping changes are sent to Claude for resolution
- [ ] Test: merged output is valid (parseable HTML/CSS/JS)

---

## Phase 3: Polish

### SPEC-014: Conversation memory

**Goal:** Allow agents to reference prior conversation context for iterative refinement.

**Dependencies:** SPEC-011

**Work:**
- Maintain a rolling conversation history (last 20 exchanges)
- Include relevant history in Intent Parser and Writer prompts
- Support references like "make it darker" or "undo the last change"

**Acceptance criteria:**
- [ ] Test: "make it bigger" after "add a header" correctly targets the header
- [ ] Test: conversation history is truncated at 20 entries
- [ ] Test: "undo" reverts the last file change

---

### SPEC-015: Error recovery and user feedback

**Goal:** Surface errors clearly and recover gracefully.

**Dependencies:** SPEC-011

**Work:**
- Display agent errors in the browser client
- If the full pipeline fails, show what went wrong and allow voice retry
- Add a voice command: "start over" to reset generated/ to blank state

**Acceptance criteria:**
- [ ] Test: Claude API timeout shows user-friendly error in browser
- [ ] Test: "start over" resets all generated files to blank boilerplate
- [ ] Test: failed pipeline does not leave system in broken state

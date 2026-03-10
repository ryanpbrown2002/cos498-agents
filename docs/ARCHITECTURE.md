# Architecture

## Overview

VoiceFront is a voice-driven frontend development tool. The user speaks design intent into a microphone. AI agents interpret that intent, generate HTML/CSS/JS code, and render it in a live preview — all without the user pressing any buttons.

## System Diagram

```
Microphone
    |
    v
[Speech-to-Text] -- Web Speech API (browser-native, free)
    |
    v
[Intent Parser Agent] -- extracts structured tasks from transcript
    |
    v
[Orchestrator] -- routes tasks, manages agent lifecycle
    |          \
    v           v
[Writer A]  [Writer B] -- parallel code generation (phase 2)
    |          |
    v          v
[Conflict Resolver] -- merges parallel file changes (phase 2)
    |
    v
[Code Reviewer Agent] -- validates quality and consistency
    |
    v
[Build Validator] -- checks generated code parses and renders
    |
    v
[File Watcher + Live Reload] -- browser auto-refreshes on file change
```

## Agents

Each agent is a Python class that inherits from a shared `BaseAgent`. All agents communicate through an `EventBus` and operate on a shared project directory.

### Intent Parser

- **Input:** raw transcript string from speech-to-text
- **Output:** list of structured `Task` objects
- **LLM usage:** sends transcript to Claude API with a system prompt that extracts design intent
- **Example:** "make the header blue and add a sidebar" -> `[Task(target="header", action="change_color", value="blue"), Task(target="sidebar", action="create")]`

### Orchestrator

- **Input:** list of `Task` objects from Intent Parser
- **Output:** dispatches tasks to Writer agents
- **LLM usage:** none (pure routing logic)
- **Responsibilities:**
  - Assigns tasks to available Writer agents
  - Phase 1: single Writer, sequential execution
  - Phase 2: multiple Writers, parallel execution
  - Tracks task completion status
  - Triggers Code Reviewer after all Writers complete

### Writer

- **Input:** a `Task` object + current project file contents
- **Output:** modified file contents written to project directory
- **LLM usage:** sends task + current code to Claude API, receives updated code
- **Responsibilities:**
  - Reads current state of target file(s)
  - Generates or modifies HTML/CSS/JS
  - Writes output to project directory

### Code Reviewer

- **Input:** diff of changes made by Writer(s)
- **Output:** approval or list of issues
- **LLM usage:** sends diff to Claude API with review prompt
- **Responsibilities:**
  - Checks for syntax errors, broken references, style inconsistencies
  - If issues found: sends back to Writer for revision (max 2 retries)
  - If approved: signals Build Validator to proceed

### Build Validator

- **Input:** project directory path
- **Output:** pass/fail + error details
- **LLM usage:** none
- **Responsibilities:**
  - Validates HTML parsing (no unclosed tags)
  - Validates CSS parsing (no syntax errors)
  - Validates JS parsing (no syntax errors)
  - Phase 2: headless browser screenshot comparison

### Conflict Resolver (Phase 2)

- **Input:** two or more file versions from parallel Writers
- **Output:** single merged version
- **LLM usage:** sends conflicting versions to Claude API to merge intelligently
- **Responsibilities:**
  - Detects overlapping changes
  - Merges non-conflicting changes automatically
  - Uses Claude API to resolve true conflicts

## Communication

### EventBus

A lightweight in-process pub/sub system. Agents subscribe to event types and emit events when work completes.

**Event types:**
- `transcript_ready` — STT produced text, payload: `{text: string}`
- `tasks_parsed` — Intent Parser produced tasks, payload: `{tasks: Task[]}`
- `task_assigned` — Orchestrator assigned task to Writer, payload: `{task: Task, agent_id: string}`
- `file_changed` — Writer modified a file, payload: `{path: string, diff: string}`
- `review_complete` — Reviewer finished, payload: `{approved: bool, issues: string[]}`
- `build_result` — Validator finished, payload: `{passed: bool, errors: string[]}`

### Project Directory

All generated frontend code lives in a `generated/` directory:

```
generated/
  index.html
  style.css
  script.js
```

Writers read from and write to this directory. The file watcher monitors it for changes and triggers browser reload.

## Tech Stack

| Component | Technology | Reason |
|-----------|-----------|--------|
| Language | Python 3.12 | devcontainer already configured |
| Frontend output | Plain HTML/CSS/JS | simplest, no build step |
| Speech-to-text | Web Speech API | free, zero setup, browser-native |
| LLM | Claude API | all agents use Claude |
| Live reload | WebSocket server (Python) | push refresh signal to browser |
| Testing | pytest | standard Python testing |
| STT upgrade path | Deepgram | $200 free credits, ~150ms latency |

## Phased Delivery

### Phase 1 — Single-agent loop
One Writer, one Reviewer, sequential. Prove the voice-to-preview loop works end-to-end.

### Phase 2 — Multi-agent parallelism
Multiple Writers, Conflict Resolver, parallel task execution. Faster generation for complex requests.

### Phase 3 — Polish
Better error recovery, conversation memory, iterative refinement ("no, make it darker"), undo support.

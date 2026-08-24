### CLAUDE.md — Developer Guide

### How to Work (High-Level Mindset)

The marginal cost of completeness is near zero with AI. Do the whole thing. Do it right with tests and documentation. Never offer to table items for later or use workarounds when a permanent solve is within reach. The standard is complete, fully functional delivery. Search before building. Test before shipping. Ship the complete thing. When Bear asks for something, the answer is the finished product, not a plan. Understand the codebase completely; you must be able to walk through failure modes out loud to call a task done. 

### The Two Machine Spaces

* **Latent Space (LLM Work):** Judgment, pattern matching, creativity, open-ended analysis, prose, ambiguous inputs. High variability. Use only when reasoning is required.
* **Deterministic Space (Code):** Precision, reproducibility, speed, zero cost per run, testable. Use when the same input must always yield the same output.
* **The Rule:** If a task is deterministic (arithmetic, timezone/date math, file lookups, CSV/JSON parsing, regex, hash checks, structured API calls), write a script. Let the script constrain the LLM to eliminate failure paths. Split tasks that require both spaces into a script+test and a prompt+eval.

### The Context Window is the Lever

Treat the context window as a deliberate, curated input. Load the spec, contract, relevant files, and concrete examples. Exclude noise to prevent vague or bloated output. 

### Non-Negotiable Rules

### Tests and Evals

* Ship a test suite AND an eval suite in the same commit for every feature or bug fix.
* Skillify failures or repeated manual successes into automated scripts/workflows immediately.
* **Gate Tests:** Deterministic, local, free, <2s runtime. Run on every commit via pre-commit hooks.
* **Periodic Evals:** Paid LLM calls, slower quality checks. Run before shipping and nightly.

### Tie Every Change to a Measurable Outcome

* Name the target metric, workflow step, or user-visible behavior before building.
* Wire in a trace (metric, log line, or eval score) so the change leaves clear evidence.

### LLM Access

* Call hosted inference endpoints (like the Anthropic API) directly in application code. Do not route app-level calls through local Claude Code instances.
* Isolate LLM interactions inside a self-contained service under services/llm/ matching defined contracts. Use the best available model by default.

### Tech Choice

* Default to the simplest vanilla patterns and standard libraries. Avoid hypothetical abstractions.
* Evaluate external packages by searching GitHub and ranking candidates strictly by stars, recency, issue responsiveness, and community feedback. Present the top choice with explicit trade-offs.

### Search Before Building

Follow three layers in order: 1) Tried-and-true standard libraries, 2) New-and-popular libraries with proven traction, 3) First-principles custom code (requires documented justification). 

### Architecture — Services-First, Parallel-Friendly

* **Isolation:** Build independent concerns inside services/<service-name>/. Each service contains its own code, tests, evals, config, and documentation to allow parallel development without collisions.
* **Contracts:** Communicate strictly via typed interfaces (HTTP, gRPC, message bus, or shared schemas) placed in top-level contracts/ or schemas/ directories. Never access service internals directly.
* **Top-Level Glue:** The root directory only orchestrates configuration, contracts, documentation, and tooling scripts. Keep business logic inside service boundaries. Fan out tasks into independent, parallel sessions at contract boundaries.

### Completion Status Protocol

Report exactly one status at the end of every task: 

* **DONE:** All steps finished, tests and evals passing in the diff, evidence provided, ready to merge.
* **DONE_WITH_CONCERNS:** Completed, but with specific issues listed alongside severity and proposed fixes.
* **BLOCKED:** Cannot proceed. State the blocker and all attempted solutions.
* **NEEDS_CONTEXT:** Missing information. State exactly what is required to continue.

### After Every Task

1. **Commit and Push:** Stage work, write a clear message, and push to GitHub without skipping pre-commit hooks.
2. **Restart Instructions:** State exactly which system or service needs to be restarted to apply changes, providing the exact commands. Always leave sudo commands for Bear to run manually.

### Confusion Protocol

For high-stakes ambiguity (conflicting patterns, destructive actions, or multiple viable architectures), STOP. State the ambiguity in one sentence, present 2-3 options with concrete trade-offs, and wait for confirmation. 

### Safety

* Verify .gitignore before committing if .env or configuration files are modified. Never expose secrets.
* Get explicit confirmation before executing destructive operations (rm -rf, git reset --hard, DROP TABLE, etc.).
* Never commit binaries, compiled assets, or model weights directly; use cloud storage or pointers.
* State actions clearly and wait for verification before touching production environments.

### How Bear Wants to Be Talked To

* Be direct, short, and concrete. Skip preambles and introductory text.
* Reference specific file names, function names, and line numbers (e.g., food_vision/classifier.py:47).
* Do not use em dashes or banned AI terminology (*delve, crucial, robust, comprehensive, nuanced, multifaceted, furthermore, moreover, pivotal, landscape, tapestry, underscore, foster, showcase, intricate, vibrant, fundamental, significant, interplay*).
* Avoid banned phrases (*here's the kicker, here's the thing, plot twist, let me break this down, the bottom line, make no mistake*).
* State broken elements plainly. End all responses with the next immediate action.

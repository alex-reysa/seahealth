2. The Planner Query Console — spec second
This is where the agentic narrative lives. The appendectomy query from the brief plays out here.
Why second:

It's the demo's "wow" moment — natural language in, ranked recommendations with rationale out
It pressure-tests whether your agent architecture actually returns what the UI needs (forces contract alignment between AGENT_ARCHITECTURE.md and DATA_CONTRACT.md)
The output format here directly drives what the audit view needs to show on click-through

Spec scope: query input with examples, ranked results table (facility, distance, trust score, contradictions count, evidence count), per-result expand for rationale, agent trace viewer (collapsed by default), export to CSV, save query. State coverage for empty / running / partial-stream / complete / no-results / agent-failed.
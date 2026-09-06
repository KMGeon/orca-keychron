# Synthetic parent UI evidence

All prompts and answers below are deterministic fixture data. No user content, credentials, request headers, or production data are included.

## `single_tui`

Orca `terminal read --screen` showed the real parent question surface:

```text
[req_1] Choose how the child should continue.
❯ Continue with A
  Continue with B
  Other (type your own)
↑/↓ select  enter
```

The operator sent `Enter`. The completed rendered frame showed:

```text
✔ Ask
[req_1] Choose how the child should continue.
└─ ☑ Continue with A
...
"status": "completed"
"request_id": "req_1"
"answer_consumed": true
PARENT_DECISION_EXPERIMENT_COMPLETE: every child consumed its matching parent answer.
```

## `two_tui`

The narrow pane's current frames repainted as only `Working…` while each question was open. The exact correlated evidence was therefore taken from provider metadata and the native synthetic child sessions, not inferred from the unreadable frame:

```text
req_1 parent_question_requested (actual_child_id_used=true)
operator input: Enter
req_1 resume payload: request_id=req_1, selected_answer=Continue with A, checkpoint=checkpoint-req_1
req_1 child_answer_consumed (correlation_valid=true, answer_valid=true, checkpoint_valid=true)
req_1 parent_completion_checked (answer_consumed=true)
req_2 parent_question_requested (actual_child_id_used=true)
operator input: Down Arrow, Enter
req_2 resume payload: request_id=req_2, selected_answer=Continue with B, checkpoint=checkpoint-req_2
req_2 child_answer_consumed (correlation_valid=true, answer_valid=true, checkpoint_valid=true)
```

The final rendered frame showed `req_2`, `answer_consumed: true`, and `PARENT_DECISION_EXPERIMENT_COMPLETE`.

## `malicious_tui`

The child session's native tool result was:

```text
toolName: ask
isError: true
failureKind: execution
text: Tool ask not found
```

Provider metadata then recorded `malicious_child_ask_checked.tool_not_found=true`, a valid structured child yield, and a parent question request with `actual_child_id_used=true`. The operator sent `Enter` for `Continue with A`; the final rendered frame showed the resumed child with `answer_consumed: true` and `PARENT_DECISION_EXPERIMENT_COMPLETE`.


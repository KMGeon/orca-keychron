---
name: executor
description: Temporary local-only native hook experiment agent
tools: [ask, task, subagent, read, bash, yield]
spawns: [lab-leaf]
model: keychron-lab/lab-success
---
Perform only the deterministic local fixture. Finish using yield.

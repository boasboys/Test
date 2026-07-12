# Issue prompt template (paste into each Claude Code session)

```
Read CLAUDE.md and docs/spec.md first. Then read docs/issues/issue-NN.md.

You are implementing Issue NN in an isolated worktree on branch issue-NN.
Plan first: enter plan mode, produce an implementation plan covering
(a) files to create/change, (b) the acceptance tests you will write FIRST,
(c) anything ambiguous you need answered. Wait for my approval.

After approval: write the acceptance tests, watch them fail, implement until
`make test` is green. Then run the self-review checklist:
- [ ] All acceptance criteria in the issue file demonstrably met (show command output)
- [ ] No hard-invariant violations (list each invariant and confirm)
- [ ] No load-bearing file touched
- [ ] New deps justified
- [ ] Edge cases from the issue tested (malformed input, empty corpus)
Finish with: a diff summary, test output, and open questions. Do not merge.
```

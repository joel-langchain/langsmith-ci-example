# Agent evals in CI with LangSmith

A small, working example of the pattern. The golden dataset lives in LangSmith, the pipeline pins a version of it, runs the agent against it, and fails the build if the score drops. Three commands, one workflow file, no UI steps in the pipeline.

## The pattern

1. **LangSmith is the source of truth for the dataset.** Subject-matter experts add and correct examples in the UI. Every edit makes a new version automatically.
2. **The pipeline pins a tag, not "latest".** A tag such as `prod` points at one version. CI evaluates against that version until someone moves the tag, so edits in the UI never change a build result by surprise.
3. **CI enforces the dataset schema.** Every example must carry the metadata the team agreed on (here, a `risk` level) and a reference answer. If an example is added without them, the build fails before any agent runs. The required keys are the `REQUIRED_METADATA` tuple at the top of `evals/__main__.py`. Change it to whatever your team agrees, or the check fails on a dataset that has no `risk` key.
4. **The harness lives in the repo and runs through a CLI.** Same commands locally and in CI. The agent is called through one adapter function, so swapping the agent never touches the rest.
5. **Gate on a score.** The run exits non-zero if the gate metric falls below a threshold, which is what makes a GitHub Actions step fail.
6. **Promote on purpose.** When the new examples are ready, move the tag. That is the only moment the pipeline's dataset changes.

Production closes the loop separately: online evaluators score live traffic, flagged runs go to an annotation queue, and reviewed examples are added to the dataset as the next version.

## Commands

```bash
# does every example carry the agreed metadata and a reference answer?
python -m evals check-schema --dataset "agent-golden-set" --tag prod

# run the agent over the pinned dataset version, score it, gate on the mean
python -m evals run --dataset "agent-golden-set" --tag prod --threshold 0.8 --gate-key keyword_coverage

# move the tag to the dataset as it is right now
python -m evals promote --dataset "agent-golden-set" --tag prod
```

`run` prints a summary and, in GitHub Actions, writes it to the job summary with a link to the experiment in LangSmith.

Two things to know before the first run.

- The tag has to exist. A tag that has never been set returns no examples, so run `promote --tag prod` once to create it. After that, only move it on purpose.
- Locally, export the variables from `.env.example` yourself (for example `set -a; source .env; set +a`). Nothing in the harness reads a `.env` file. In GitHub Actions the workflow sets them from secrets.

## Files

| File | What it is |
|---|---|
| `.github/workflows/evals.yml` | The pipeline. Schema check, then the gated run. |
| `evals/__main__.py` | The CLI. `check-schema`, `run`, `promote`. |
| `evals/target.py` | The one function that calls the agent. Swap `AGENT_MODE` for `http` or `agentcore`. |
| `evals/evaluators.py` | Two code evaluators plus an LLM judge that switches on when `OPENAI_API_KEY` is set. |

## Wiring in a real agent

`evals/target.py` has four modes.

- `echo` returns the question. It always fails the gate. Use it to check the pipeline fails properly.
- `reference` returns the reference answer. It always passes. Use it to check the pipeline end to end before the agent is wired in.
- `http` posts the question to `AGENT_URL`. `agentcore` invokes an AgentCore runtime by ARN. Fill in the secrets in the workflow and set `AGENT_MODE`.

The evaluators read `outputs["answer"]`, so whatever the agent returns, put the answer under that key.

## Evaluators

Every evaluator returns a comment alongside the score, so the reason for a failure shows in LangSmith rather than a bare `false`.

- `response_present`. The agent said something.
- `keyword_coverage`. Share of the example's `expected_keywords` found in the answer. Text is normalised first, so unicode hyphens, non-breaking spaces, and markdown do not cause misses.
- `correctness`. An LLM judge from [openevals](https://github.com/langchain-ai/openevals) comparing the answer to the reference. Only built if `OPENAI_API_KEY` is set.

Gate on the code evaluator by default. It is free, deterministic, and cannot have a bad day. Use the judge for the richer signal and compare experiments in the LangSmith UI.

## Secrets the workflow needs

| Secret | Required | Notes |
|---|---|---|
| `LANGSMITH_API_KEY` | yes | A service key for the workspace. |
| `OPENAI_API_KEY` | no | Turns on the LLM judge. |
| `AGENT_RUNTIME_ARN`, AWS credentials | for `agentcore` mode | |

`LANGSMITH_ENDPOINT` is set to the EU endpoint in the workflow.

## Docs

- [Manage datasets, versions, and tags](https://docs.langchain.com/langsmith/manage-datasets)
- [Evaluation concepts](https://docs.langchain.com/langsmith/evaluation-concepts)
- [Evaluation quickstart](https://docs.langchain.com/langsmith/evaluation-quickstart)
- [openevals](https://github.com/langchain-ai/openevals)

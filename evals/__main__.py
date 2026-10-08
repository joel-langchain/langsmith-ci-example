"""CLI entry point. See README for the pattern."""
from __future__ import annotations

import argparse
import datetime as dt
import os
import statistics
import sys

from langsmith import Client, evaluate

from . import target
from .evaluators import build_evaluators
from .target import call_agent

REQUIRED_METADATA = ("risk",)  # every example must carry these keys


def cmd_check_schema(args) -> int:
    """Fail if any example is missing the metadata the team agreed on."""
    client = Client()
    examples = list(client.list_examples(dataset_name=args.dataset, as_of=args.tag))
    bad = []
    for ex in examples:
        md = ex.metadata or {}
        missing = [k for k in REQUIRED_METADATA if k not in md]
        if missing or not (ex.outputs or {}).get("reference_answer"):
            bad.append((str(ex.id)[:8], missing, "no reference_answer" if not (ex.outputs or {}).get("reference_answer") else ""))
    print(f"{len(examples)} examples in '{args.dataset}' @ {args.tag}")
    for ex_id, missing, note in bad:
        print(f"  {ex_id}  missing metadata {missing} {note}".rstrip())
    if bad:
        print(f"FAIL: {len(bad)} example(s) do not meet the schema")
        return 1
    print("OK: schema holds")
    return 0


def cmd_run(args) -> int:
    """Run the agent over the tagged dataset version, score it, gate on the mean."""
    client = Client()
    examples = list(client.list_examples(dataset_name=args.dataset, as_of=args.tag))
    if not examples:
        print(f"no examples in '{args.dataset}' @ {args.tag}")
        return 1
    if target.MODE == "reference":
        target.REFERENCE_BY_QUESTION = {
            (ex.inputs or {}).get("question", ""): (ex.outputs or {}).get("reference_answer", "") for ex in examples
        }

    results = evaluate(
        lambda inputs: call_agent(inputs),
        data=examples,
        evaluators=build_evaluators(),
        experiment_prefix=args.experiment_prefix,
        metadata={
            "dataset_tag": args.tag,
            "git_sha": os.environ.get("GITHUB_SHA", "local")[:12],
            "git_ref": os.environ.get("GITHUB_REF_NAME", "local"),
            "ci": bool(os.environ.get("GITHUB_ACTIONS")),
        },
        max_concurrency=4,
    )
    results.wait()

    scores: dict[str, list[float]] = {}
    for r in results:
        for fb in r["evaluation_results"]["results"]:
            if fb.score is not None:
                scores.setdefault(fb.key, []).append(float(fb.score))
    means = {k: statistics.fmean(v) for k, v in scores.items()}

    lines = [f"experiment: {results.experiment_name}", f"dataset: {args.dataset} @ {args.tag}  ({len(examples)} examples)"]
    for k, v in sorted(means.items()):
        lines.append(f"  {k:20} {v:.3f}")
    gate = means.get(args.gate_key)
    passed = gate is not None and gate >= args.threshold
    lines.append(f"gate: {args.gate_key} {gate if gate is None else f'{gate:.3f}'} >= {args.threshold}  ->  {'PASS' if passed else 'FAIL'}")
    report = "\n".join(lines)
    print(report)
    _write_step_summary(report, results.url if hasattr(results, "url") else None)
    return 0 if passed else 1


def cmd_promote(args) -> int:
    """Point a tag at the dataset as it is right now."""
    client = Client()
    now = dt.datetime.now(dt.timezone.utc)
    client.update_dataset_tag(dataset_name=args.dataset, as_of=now, tag=args.tag)
    # Read back through the tag so the promotion is confirmed, not assumed.
    n = sum(1 for _ in client.list_examples(dataset_name=args.dataset, as_of=args.tag))
    print(f"'{args.dataset}' tag '{args.tag}' now points at {now.isoformat(timespec='seconds')} ({n} examples)")
    return 0


def _write_step_summary(report: str, url: str | None) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    with open(path, "a") as f:
        f.write("### Agent evals\n\n```\n" + report + "\n```\n")
        if url:
            f.write(f"\n[Open experiment in LangSmith]({url})\n")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="evals")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("check-schema", help="every example carries the agreed metadata and a reference answer")
    a.add_argument("--dataset", required=True)
    a.add_argument("--tag", default="latest")
    a.set_defaults(fn=cmd_check_schema)

    r = sub.add_parser("run", help="evaluate the agent against a dataset version and gate on a score")
    r.add_argument("--dataset", required=True)
    r.add_argument("--tag", default="latest", help="dataset version tag to pin, e.g. prod")
    r.add_argument("--threshold", type=float, default=0.8)
    r.add_argument("--gate-key", default="keyword_coverage", help="which score the gate uses")
    r.add_argument("--experiment-prefix", default="ci")
    r.set_defaults(fn=cmd_run)

    m = sub.add_parser("promote", help="move a tag to the current dataset version")
    m.add_argument("--dataset", required=True)
    m.add_argument("--tag", required=True)
    m.set_defaults(fn=cmd_promote)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())

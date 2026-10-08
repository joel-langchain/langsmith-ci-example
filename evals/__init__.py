"""Evaluation harness for the agent, run from CI or a laptop.

Everything is driven from the command line so the pipeline always runs the same
commands:

    python -m evals check-schema --dataset "agent-golden-set"
    python -m evals run --dataset "agent-golden-set" --tag prod --threshold 0.8
    python -m evals promote --dataset "agent-golden-set" --tag prod
"""

"""The thing under test.

`call_agent` takes one dataset example's inputs and returns the agent's answer.
Swap the body for a real call to your agent. Two common shapes are sketched
below. The rest of the harness never changes.

Inputs and outputs are plain dicts. The evaluators read `outputs["answer"]`.
"""
from __future__ import annotations

import os

MODE = os.environ.get("AGENT_MODE", "echo")

# Filled by `evals run` when AGENT_MODE=reference, so the stand-in can answer.
REFERENCE_BY_QUESTION: dict[str, str] = {}


def call_agent(inputs: dict) -> dict:
    question = inputs.get("question") or inputs.get("input") or ""

    if MODE == "echo":
        # Stand-in that always fails the gate. Useful for checking the pipeline fails properly.
        return {"answer": f"Echo: {question}"}

    if MODE == "reference":
        # Stand-in that always passes, by returning the reference answer. Useful for
        # checking the pipeline end to end before the real agent is wired in.
        return {"answer": REFERENCE_BY_QUESTION.get(question, "")}

    if MODE == "http":
        # Any HTTP endpoint that takes a question and returns an answer,
        # e.g. an API gateway in front of the agent or a dev deployment of it.
        import json
        import urllib.request

        req = urllib.request.Request(
            os.environ["AGENT_URL"],
            method="POST",
            headers={"Content-Type": "application/json", **_auth_headers()},
            data=json.dumps({"question": question}).encode(),
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read())
        return {"answer": body.get("answer", body)}

    if MODE == "agentcore":
        # Invoke an AgentCore runtime directly. Needs boto3 and AWS credentials
        # in the environment, same as any other AWS call from CI.
        import json

        import boto3

        client = boto3.client("bedrock-agentcore", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        resp = client.invoke_agent_runtime(
            agentRuntimeArn=os.environ["AGENT_RUNTIME_ARN"],
            qualifier=os.environ.get("AGENT_QUALIFIER", "DEFAULT"),
            payload=json.dumps({"prompt": question}).encode(),
        )
        body = json.loads(resp["response"].read())
        return {"answer": body.get("result", body)}

    raise ValueError(f"unknown AGENT_MODE {MODE!r}")


def _auth_headers() -> dict:
    token = os.environ.get("AGENT_TOKEN")
    return {"Authorization": f"Bearer {token}"} if token else {}

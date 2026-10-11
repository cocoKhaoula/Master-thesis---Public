"""AWS session helpers. The harness and the agent use different profiles (Section 5.7)."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import boto3

from .config import Config


def session(cfg: Config, role: str) -> boto3.Session:
    """role is 'harness' or 'agent'."""
    profile = cfg["aws"][f"{role}_profile"]
    return boto3.Session(profile_name=profile, region_name=cfg.region)


@dataclass(frozen=True)
class FunctionResources:
    """Physical names of one benchmark function, resolved from the stack."""
    key: str             # short name used in this repo, e.g. "crud-api"
    function_name: str   # physical Lambda function name
    role_name: str       # physical IAM role name
    log_group: str


@lru_cache(maxsize=None)
def _stack_resources(profile: str, region: str, stack: str) -> dict[str, str]:
    cfn = boto3.Session(profile_name=profile, region_name=region).client("cloudformation")
    out: dict[str, str] = {}
    for page in cfn.get_paginator("list_stack_resources").paginate(StackName=stack):
        for r in page["StackResourceSummaries"]:
            out[r["LogicalResourceId"]] = r["PhysicalResourceId"]
    return out


def resolve_functions(cfg: Config, role: str = "harness") -> dict[str, FunctionResources]:
    res = _stack_resources(cfg["aws"][f"{role}_profile"], cfg.region, cfg.stack_name)
    out = {}
    for key, f in cfg.functions.items():
        name = res[f["logical_id"]]
        out[key] = FunctionResources(
            key=key,
            function_name=name,
            role_name=res[f["role_logical_id"]],
            log_group=f"/aws/lambda/{name}",
        )
    return out


def stack_outputs(cfg: Config, role: str = "harness") -> dict[str, str]:
    cfn = session(cfg, role).client("cloudformation")
    stack = cfn.describe_stacks(StackName=cfg.stack_name)["Stacks"][0]
    return {o["OutputKey"]: o["OutputValue"] for o in stack.get("Outputs", [])}

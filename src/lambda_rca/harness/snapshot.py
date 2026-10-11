"""Configuration snapshots and CloudFormation drift detection per window.

Snapshots record the live state of every function during a window. They are part of
the published dataset (R7) and allow later inspection of what the agent could see.
Drift detection results are the output of the CloudFormation drift baseline (Section 6.1),
which has to be captured while the fault is active.
"""
from __future__ import annotations

import time
from typing import Any

from ..aws import FunctionResources
from ..config import Config
from ..io import iso, utcnow
from . import apprepo


def take_snapshot(cfg: Config, lam, iam, functions: dict[str, FunctionResources]) -> dict[str, Any]:
    snap: dict[str, Any] = {"taken_at": iso(utcnow()), "functions": {}}
    for key, fn in functions.items():
        conf = lam.get_function_configuration(FunctionName=fn.function_name)
        conc = lam.get_function_concurrency(FunctionName=fn.function_name)
        policies = {}
        for name in iam.list_role_policies(RoleName=fn.role_name)["PolicyNames"]:
            policies[name] = iam.get_role_policy(RoleName=fn.role_name, PolicyName=name)["PolicyDocument"]
        snap["functions"][key] = {
            "function_name": fn.function_name,
            "memory_size": conf["MemorySize"],
            "timeout": conf["Timeout"],
            "environment": conf.get("Environment", {}).get("Variables", {}),
            "reserved_concurrency": conc.get("ReservedConcurrentExecutions"),
            "role": fn.role_name,
            "inline_policies": policies,
        }
    if cfg.app_repo.exists():
        snap["app_repo_head"] = apprepo.head(cfg.app_repo)
    return snap


def detect_drift(cfn, stack_name: str, timeout_s: int = 300) -> dict[str, Any]:
    """Run CloudFormation drift detection on the stack and return drifted resources."""
    started = utcnow()
    detection_id = cfn.detect_stack_drift(StackName=stack_name)["StackDriftDetectionId"]
    deadline = time.time() + timeout_s
    while True:
        status = cfn.describe_stack_drift_detection_status(StackDriftDetectionId=detection_id)
        if status["DetectionStatus"] != "DETECTION_IN_PROGRESS":
            break
        if time.time() > deadline:
            raise TimeoutError("drift detection did not finish in time")
        time.sleep(5)

    drifts = []
    paginator = cfn.get_paginator("describe_stack_resource_drifts")
    for page in paginator.paginate(StackName=stack_name,
                                   StackResourceDriftStatusFilters=["MODIFIED", "DELETED"]):
        for d in page["StackResourceDrifts"]:
            drifts.append({
                "logical_id": d["LogicalResourceId"],
                "physical_id": d.get("PhysicalResourceId"),
                "resource_type": d["ResourceType"],
                "status": d["StackResourceDriftStatus"],
                "differences": [
                    {"path": p["PropertyPath"], "expected": p.get("ExpectedValue"),
                     "actual": p.get("ActualValue"), "type": p["DifferenceType"]}
                    for p in d.get("PropertyDifferences", [])
                ],
            })
    return {
        "started": iso(started),
        "finished": iso(utcnow()),
        "stack_drift_status": status.get("StackDriftStatus"),
        "detection_status": status["DetectionStatus"],
        "drifted_resources": drifts,
    }

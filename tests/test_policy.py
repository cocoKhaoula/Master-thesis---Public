from pathlib import Path

import pytest

from lambda_rca.harness.policy import (SILENT_SID, add_unused_permission, edit_template_env_var,
                                       remove_action, set_env_var)
from lambda_rca.labels import artifact_matches

POLICY = {"Version": "2012-10-17", "Statement": [
    {"Sid": "CartTableAccess", "Effect": "Allow",
     "Action": ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:Query"], "Resource": "arn:table"}]}
TEMPLATE = (Path(__file__).resolve().parents[1] / "app" / "template.yaml").read_text(encoding="utf-8")


def test_remove_action_keeps_others_and_original():
    new = remove_action(POLICY, "dynamodb:PutItem")
    assert new["Statement"][0]["Action"] == ["dynamodb:GetItem", "dynamodb:Query"]
    assert "dynamodb:PutItem" in POLICY["Statement"][0]["Action"]   # original untouched (exact revert)


def test_remove_last_action_drops_statement():
    doc = {"Statement": [{"Effect": "Allow", "Action": "s3:PutObject", "Resource": "*"}]}
    assert remove_action(doc, "s3:PutObject")["Statement"] == []
    with pytest.raises(ValueError):
        remove_action(doc, "s3:GetObject")


def test_add_unused_permission():
    new = add_unused_permission(POLICY, "s3:ListAllMyBuckets")
    assert new["Statement"][-1]["Sid"] == SILENT_SID
    assert len(POLICY["Statement"]) == 1


def test_set_env_var_keeps_full_set():
    assert set_env_var({"A": "1", "B": "2"}, "B", "x") == {"A": "1", "B": "x"}
    with pytest.raises(ValueError):
        set_env_var({"A": "1"}, "C", "x")


def test_edit_template_changes_one_line_in_right_resource():
    new = edit_template_env_var(TEMPLATE, "ThumbnailerFunction", "OUTPUT_BUCKET", "missing-bucket")
    diff = [(a, b) for a, b in zip(TEMPLATE.splitlines(), new.splitlines()) if a != b]
    assert len(diff) == 1
    assert diff[0][1].strip() == "OUTPUT_BUCKET: missing-bucket"
    # the other functions still use !Ref
    assert new.count("OUTPUT_BUCKET: !Ref OutputBucket") == TEMPLATE.count("OUTPUT_BUCKET: !Ref OutputBucket") - 1
    with pytest.raises(ValueError):
        edit_template_env_var(TEMPLATE, "CrudApiFunction", "OUTPUT_BUCKET", "x")


def test_artifact_matching_rules():
    assert artifact_matches("execution role policy: dynamodb:PutItem missing", [["putitem"]])
    assert artifact_matches("Environment variable TABLE_NAME", [["TABLE_NAME"]])
    assert artifact_matches("Timeout lowered to 3 s", [["memory"], ["timeout"]])
    assert not artifact_matches("throttling", [["concurren"]])
    assert not artifact_matches("anything", [])

"""Docker publishing policy of .github/workflows/ci.yml, checked as data.

A fork without Docker Hub secrets must still build and smoke-test both
architectures, and must never attempt a registry login, push or manifest.
Publishing is an explicit opt-in (repository variable DOCKER_PUBLISH='true').
These tests read the workflow file only; they run no Docker and call no network.

They check structure, not GitHub's expression engine. Expression syntax and
context availability were reviewed by hand against GitHub's documentation, and
a real run on GitHub is the only complete check.
"""

import re
from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(".github/workflows/ci.yml")
PUBLISH_ONLY = "env.PUBLISH == 'true'"


@pytest.fixture(scope="module")
def workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def build(workflow):
    return workflow["jobs"]["docker-build"]


@pytest.fixture(scope="module")
def manifest(workflow):
    return workflow["jobs"]["docker-manifest"]


def step_index(job, needle):
    names = [step.get("name", step.get("uses", "")) for step in job["steps"]]
    matches = [i for i, name in enumerate(names) if needle in name]
    assert matches, (needle, names)
    return matches[0]


def test_triggers_and_permissions_are_unchanged(workflow):
    triggers = workflow[True]  # PyYAML reads the bare key `on` as boolean True
    assert triggers["push"]["branches"] == ["main"]
    assert triggers["pull_request"]["branches"] == ["main"]
    assert workflow["permissions"] == {"contents": "read", "actions": "write"}
    for name, job in workflow["jobs"].items():
        granted = job.get("permissions", {})
        assert "packages" not in granted and "id-token" not in granted, name


def test_every_existing_job_is_still_present(workflow):
    expected = {
        "backend-lint",
        "backend-test",
        "gunicorn-boot",
        "eventlet-fallback",
        "gthread-gates",
        "gthread-migration",
        "gthread-platforms",
        "frontend-lint",
        "chart-indicator-skill",
        "openscript-skill",
        "frontend-build",
        "frontend-test",
        "frontend-e2e",
        "security-scan",
        "commit-dist",
        "docker-build",
        "docker-manifest",
    }
    assert expected <= set(workflow["jobs"])


def test_frontend_distribution_automation_is_untouched(workflow):
    job = workflow["jobs"]["commit-dist"]
    assert job["needs"] == ["frontend-build", "frontend-lint", "frontend-test"]
    assert job["if"] == "github.ref == 'refs/heads/main' && github.event_name == 'push'"
    assert job["permissions"] == {"contents": "write"}


def test_both_architectures_stay_in_the_docker_matrix(build):
    legs = {leg["platform"]: leg for leg in build["strategy"]["matrix"]["include"]}
    assert set(legs) == {"linux/amd64", "linux/arm64"}
    assert legs["linux/arm64"]["runner"] == "ubuntu-24.04-arm"
    assert build["strategy"]["fail-fast"] is False
    assert set(build["needs"]) >= {"backend-test", "frontend-build", "gthread-migration"}


def test_the_docker_job_is_not_hidden_behind_a_publishing_switch(build, manifest):
    condition = build["if"]
    assert "github.event_name == 'push'" in condition
    assert "vars." not in condition and "secrets." not in condition
    # Job-level conditions can read only a few contexts; env and secrets are not among them.
    for job in (build, manifest):
        assert "secrets." not in job["if"] and "env." not in job["if"]


def test_publishing_is_gated_on_one_explicit_variable(build):
    publish = build["env"]["PUBLISH"]
    for required in (
        "github.event_name == 'push'",
        "refs/heads/main",
        "vars.DOCKER_PUBLISH == 'true'",
    ):
        assert required in publish
    name = build["env"]["IMAGE_NAME"]
    assert "vars.DOCKER_PUBLISH == 'true'" in name and name.rstrip(" }").endswith("|| 'openalgo'")
    # A pull request can never publish, whatever the variable says.
    assert "pull_request" not in publish


def test_every_registry_step_is_conditioned_on_publishing(build):
    registry = []
    for step in build["steps"]:
        text = yaml.safe_dump(step)
        pushes = "push=true" in text or step.get("with", {}).get("push") is True
        if "DOCKERHUB" in text or "login-action" in text or pushes or "digest" in text.lower():
            registry.append(step)
            assert PUBLISH_ONLY in step.get("if", ""), step.get("name")
    assert {step["name"] for step in registry} >= {
        "Require Docker Hub credentials (publishing only)",
        "Login to Docker Hub",
        "Build (publish by digest)",
        "Export digest",
        "Upload digest",
    }
    # The metadata step needs no username: it reads the local-or-published name.
    metadata = build["steps"][step_index(build, "Extract metadata")]
    assert metadata["with"]["images"] == "${{ env.IMAGE_NAME }}"
    assert "secrets." not in yaml.safe_dump(metadata)


def test_validation_build_and_smoke_test_always_run_and_come_before_any_publish(build):
    validate = build["steps"][step_index(build, "Build (validate")]
    smoke = build["steps"][step_index(build, "Kaleido + Chromium smoke test")]
    publish = step_index(build, "Build (publish by digest)")
    assert "if" not in validate and "if" not in smoke
    assert validate["with"]["load"] is True and "push" not in validate["with"]
    assert validate["with"]["platforms"] == "${{ matrix.platform }}"
    assert "openalgo-ci:$SUFFIX" in smoke["run"] and "kaleido" in smoke["run"].lower()
    assert step_index(build, "Build (validate") < step_index(build, "Kaleido") < publish


def test_a_missing_secret_fails_with_a_message_instead_of_a_registry_error(build, manifest):
    for job, name in (
        (build, "Require Docker Hub credentials (publishing only)"),
        (manifest, "Require Docker Hub credentials"),
    ):
        check = job["steps"][step_index(job, name)]
        assert step_index(job, name) < step_index(job, "Login to Docker Hub")
        assert "DOCKERHUB_USERNAME" in check["run"] and "DOCKERHUB_TOKEN" in check["run"]
        assert "exit 1" in check["run"] and "::error::" in check["run"]
        # The secrets reach the shell through env, never interpolated into the script.
        assert "${{" not in check["run"]


def test_the_manifest_job_runs_only_when_publishing_is_enabled(manifest):
    condition = manifest["if"]
    for required in (
        "github.ref == 'refs/heads/main'",
        "github.event_name == 'push'",
        "vars.DOCKER_PUBLISH == 'true'",
    ):
        assert required in condition
    assert manifest["needs"] == "docker-build"


def test_docker_hub_secrets_appear_only_in_publish_scoped_places():
    text = WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.safe_load(text)
    for job_name in ("docker-build", "docker-manifest"):
        job = workflow["jobs"][job_name]
        for step in job["steps"]:
            if "secrets.DOCKERHUB" in yaml.safe_dump(step):
                assert job_name == "docker-manifest" or PUBLISH_ONLY in step.get("if", ""), step[
                    "name"
                ]
    # No other job touches the registry credentials at all.
    for name, job in workflow["jobs"].items():
        if name not in ("docker-build", "docker-manifest"):
            assert "DOCKERHUB" not in yaml.safe_dump(job), name


def test_expression_delimiters_are_balanced():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert text.count("${{") == text.count("}}")
    for expression in re.findall(r"\$\{\{(.*?)\}\}", text):
        assert expression.count("(") == expression.count(")"), expression
        assert expression.count("'") % 2 == 0, expression

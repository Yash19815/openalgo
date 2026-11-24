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
PUBLISH_ONLY = "github.event_name == 'push' && github.ref == 'refs/heads/main' && vars.DOCKER_PUBLISH == 'true'"
VALIDATION_JOBS = {
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
    "docker-build",
}


@pytest.fixture(scope="module")
def workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def build(workflow):
    return workflow["jobs"]["docker-build"]


@pytest.fixture(scope="module")
def publish(workflow):
    return workflow["jobs"]["docker-publish"]


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
        "docker-publish",
        "docker-manifest",
    }
    assert expected <= set(workflow["jobs"])


def test_frontend_distribution_automation_is_untouched(workflow):
    job = workflow["jobs"]["commit-dist"]
    assert job["needs"] == ["frontend-build", "frontend-lint", "frontend-test"]
    assert job["if"] == "github.ref == 'refs/heads/main' && github.event_name == 'push'"
    assert job["permissions"] == {"contents": "write"}


def test_both_architectures_stay_in_the_docker_matrix(build, publish):
    for job in (build, publish):
        legs = {leg["platform"]: leg for leg in job["strategy"]["matrix"]["include"]}
        assert set(legs) == {"linux/amd64", "linux/arm64"}
        assert legs["linux/arm64"]["runner"] == "ubuntu-24.04-arm"
        assert job["strategy"]["fail-fast"] is False


def test_independent_validation_starts_without_dependencies_even_on_fork_prs(workflow):
    for name in VALIDATION_JOBS:
        job = workflow["jobs"][name]
        assert not job.get("needs"), name
        assert "if" not in job, name
        assert not job.get("continue-on-error"), name
        assert "max-parallel" not in job.get("strategy", {}), name


def test_the_docker_job_is_not_hidden_behind_a_publishing_switch(build, publish, manifest):
    assert "if" not in build
    # Job-level conditions can read only a few contexts; env and secrets are not among them.
    for job in (publish, manifest):
        assert "secrets." not in job["if"] and "env." not in job["if"]


def test_publishing_is_gated_on_every_validation_and_one_explicit_variable(publish):
    assert publish["if"] == PUBLISH_ONLY
    assert set(publish["needs"]) == VALIDATION_JOBS
    # Without always()/failure(), GitHub's implicit success() rejects any failed,
    # skipped or cancelled dependency, including any failed matrix cell.
    assert not publish.get("continue-on-error")
    assert all(not step.get("continue-on-error") for step in publish["steps"])
    # A pull request can never publish, whatever the variable says.
    assert "pull_request" not in publish["if"]


def test_every_registry_step_is_in_the_gated_publish_job(build, publish):
    assert "DOCKERHUB" not in yaml.safe_dump(build)
    assert "login-action" not in yaml.safe_dump(build)
    registry = []
    for step in publish["steps"]:
        text = yaml.safe_dump(step)
        pushes = "push=true" in text or step.get("with", {}).get("push") is True
        if "DOCKERHUB" in text or "login-action" in text or pushes or "digest" in text.lower():
            registry.append(step)
            assert publish["if"] == PUBLISH_ONLY
    assert {step["name"] for step in registry} >= {
        "Require Docker Hub credentials (publishing only)",
        "Login to Docker Hub",
        "Build (publish by digest)",
        "Export digest",
        "Upload digest",
    }
    # Validation metadata needs no registry namespace or credentials.
    metadata = build["steps"][step_index(build, "Extract metadata")]
    assert metadata["with"]["images"] == "openalgo"
    assert "secrets." not in yaml.safe_dump(metadata)


def test_validation_build_and_smoke_test_always_run_and_come_before_any_publish(build, publish):
    validate = build["steps"][step_index(build, "Build (validate")]
    smoke = build["steps"][step_index(build, "Kaleido + Chromium smoke test")]
    assert "if" not in validate and "if" not in smoke
    assert validate["with"]["load"] is True and "push" not in validate["with"]
    assert validate["with"]["platforms"] == "${{ matrix.platform }}"
    assert "openalgo-ci:$SUFFIX" in smoke["run"] and "kaleido" in smoke["run"].lower()
    assert validate["with"]["context"] == "."
    assert "cache-from" in validate["with"] and "cache-to" in validate["with"]
    assert step_index(build, "Build (validate") < step_index(build, "Kaleido")
    assert "docker-build" in publish["needs"]
    push = publish["steps"][step_index(publish, "Build (publish by digest)")]
    assert "push-by-digest=true" in push["with"]["outputs"]
    assert push["with"]["cache-from"] == validate["with"]["cache-from"]
    assert push["with"]["platforms"] == validate["with"]["platforms"]


def test_a_missing_secret_fails_with_a_message_instead_of_a_registry_error(publish, manifest):
    for job, name in (
        (publish, "Require Docker Hub credentials (publishing only)"),
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
    assert manifest["needs"] == "docker-publish"
    assert "always()" not in condition and "failure()" not in condition


def test_docker_hub_secrets_appear_only_in_publish_scoped_places():
    text = WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.safe_load(text)
    for job_name in ("docker-publish", "docker-manifest"):
        job = workflow["jobs"][job_name]
        for step in job["steps"]:
            if "secrets.DOCKERHUB" in yaml.safe_dump(step):
                assert "vars.DOCKER_PUBLISH == 'true'" in job["if"]
                assert "github.event_name == 'push'" in job["if"]
                assert "github.ref == 'refs/heads/main'" in job["if"]
    # No other job touches the registry credentials at all.
    for name, job in workflow["jobs"].items():
        if name not in ("docker-publish", "docker-manifest"):
            assert "DOCKERHUB" not in yaml.safe_dump(job), name


def test_matrices_nifty_coverage_and_cancellation_are_preserved(workflow):
    jobs = workflow["jobs"]
    assert jobs["backend-test"]["strategy"]["matrix"]["python-version"] == ["3.12", "3.13", "3.14"]
    for name in ("frontend-build", "frontend-test"):
        assert jobs[name]["strategy"]["matrix"]["node-version"] == ["22", "24"]
    backend = yaml.safe_dump(jobs["backend-test"])
    assert "test/test_nifty_algo_*.py" in backend
    assert "test/test_ci_docker_publish_policy.py" in backend
    assert "npm run e2e -- --project=chromium" in yaml.safe_dump(jobs["frontend-e2e"])
    assert workflow["concurrency"] == {
        "group": "${{ github.workflow }}-${{ github.ref }}",
        "cancel-in-progress": True,
    }


def test_expression_delimiters_are_balanced():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert text.count("${{") == text.count("}}")
    for expression in re.findall(r"\$\{\{(.*?)\}\}", text):
        assert expression.count("(") == expression.count(")"), expression
        assert expression.count("'") % 2 == 0, expression

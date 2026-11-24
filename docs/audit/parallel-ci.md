# CI parallelism

The `perf/parallel-ci` branch starts all 15 independent validation jobs without
`needs`. Matrix expansion retains Python 3.12/3.13/3.14, Node 22/24, all four
Gunicorn modes, Windows, macOS, native Linux ARM64, and both Docker platforms.
No test commands, test selections, trading code, or security scans change.

## Dependency graph

- Backend lint/tests, frontend lint/build/tests/E2E, security, chart/OpenScript
  checks, Gunicorn, eventlet, gthread gates/migration/platforms, and Docker
  validation all become eligible at workflow start.
- `commit-dist` still requires the complete frontend build and test matrices
  plus frontend lint. Its Node 22 rebuild, checkout, commit, and push remain
  unchanged. Artifact reuse was rejected here: downloaded artifacts omit hidden
  files by default, while a fresh build preserves the existing output and commit
  behavior. Distribution automation is main-push-only and is skipped on PRs.
- `docker-publish` requires **every** validation job, including both Docker
  smoke tests, both frontend test versions, browser E2E, and the skill checks.
  GitHub's implicit `success()` prevents publication after a failed, skipped,
  or cancelled dependency or matrix cell. No `always()` bypass is used.
- `docker-manifest` requires the complete `docker-publish` matrix and retains
  digest artifacts, the multi-architecture manifest, canonical tags, inspection,
  and Trivy scan.

Docker validation builds the actual application Dockerfile with `load: true`,
per-architecture GitHub layer caches, and the original Kaleido/Chromium smoke
test. It needs no Docker Hub secrets and now also covers fork PRs. Publishing
remains restricted to pushes to `main` with `DOCKER_PUBLISH=true`. Only the
publishing jobs read credentials or log in. Their existing missing-secret
diagnostic remains before login. Publishing rebuilds the same source using the
validation layer caches, as the previous in-job publish step did; layer cache
reuse is an optimization, not an integrity gate. Publishing is not exercised by
the PR because publishing from a PR is forbidden.

Workflow permissions, concurrency cancellation, frontend distribution writes,
and existing advisory Ruff/Bandit/pip-audit behavior remain unchanged. A failed
`backend-lint` job still fails the workflow and blocks publishing; its pre-existing
`continue-on-error` Ruff steps report existing lint/format debt as advisory.
Making those advisory findings blocking would be a separate policy change: the
baseline already reports 547 files needing formatting. No lint dependency is
needed for any runtime job because each independently checks out and installs
its source and dependencies.

## Actual baseline

[Run 45372621891](https://github.com/Yash19815/openalgo/actions/runs/45372621891),
PR event, commit `90ce71f564bdee682b992da732fa783ffdea675d`, succeeded.
GitHub timestamps: 2026-11-24 10:12:56 through 10:29:57 UTC: **1,021 seconds
(17m01s)**. The last running job ended at 10:29:56; final workflow bookkeeping
added one second.

| Job | Eligibility after workflow creation | Runner queue | Execution | Finished after creation |
| --- | ---: | ---: | ---: | ---: |
| Backend lint | 1s | 1s | 17s | 19s |
| Security scan | 1s | 1s | 603s | 605s |
| Frontend test Node 24 | 1s | 2s | 489s | 492s |
| gthread migration | 19s | 2s | 477s | 498s |
| Docker AMD64 | 606s | 2s | 412s | 1,020s |
| Docker ARM64 | 606s | 4s | 350s | 960s |

The baseline critical path is security scanning followed by AMD64 Docker
validation. Docker eligibility was delayed by 606 seconds from workflow
creation: security finished at 605 seconds, followed by one second of dependency
scheduling. Each lint-dependent runtime job became eligible at 19 seconds,
versus one second for independent jobs, adding 18 seconds of dependency delay.
Observed non-skipped baseline runner queues were 1–4 seconds.

Docker's build/load steps took 373s AMD64 and 320s ARM64. Both Kaleido/Chromium
smoke steps took 3s. Remaining Docker job time includes setup, metadata, cache
export, and cleanup; it is not all image compilation.

## Comparison method and estimate

Download complete run and job/step metadata, including all matrix cells:

```powershell
gh api repos/Yash19815/openalgo/actions/runs/RUN_ID > run.json
gh api 'repos/Yash19815/openalgo/actions/runs/RUN_ID/jobs?per_page=100' > jobs.json
```

Workflow elapsed time is `run.updated_at - run.created_at` once completed. Also
report the span through the last non-skipped job's `completed_at` to expose final
bookkeeping. Execution is `job.completed_at - job.started_at`. Runner queue is
`job.started_at - job.created_at`. Dependency wait is the interval before job
creation; compare against root-job creation and prerequisite completion because
this interval also includes GitHub scheduler overhead. Step durations use their
own start/completion timestamps. These API timestamps have one-second precision.

With baseline execution durations and comparable runner availability, the
dependency-free validation critical path would be security scanning at roughly
605 seconds (10m05s), instead of security followed by Docker. **This is an
estimate, not a measured optimized result.** Cache state, security-audit network
calls, runner availability, and shared concurrency limits can change the result.
Opted-in publishing adds its own gated build/push/manifest time and is excluded
from this PR-only estimate.

The pull request description records the optimized run URL, exact head SHA,
actual timings, queue delays, and comparison after Actions finishes. Keeping
those final measurements in the PR avoids creating a new unmeasured commit
solely to record the previous commit's CI result.

Validation: the dedicated Docker publishing and gthread CI policy tests run
locally as static workflow checks. `actionlint` validates YAML, expressions, and
context availability. Runtime suites run only on GitHub Actions.

References: [GitHub dependency semantics](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idneeds)
and [Docker GitHub Actions layer caching](https://docs.docker.com/build/ci/github-actions/cache/).

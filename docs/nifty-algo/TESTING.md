# Local verification record

All market events in feature tests are explicitly synthetic fixtures. No real-time paper session or broker order was executed.

The target initially had no Python virtual environment or frontend dependencies. A local `.venv` uses Python 3.12.11 from an existing read-only interpreter cache. A minimal set of declared platform/test dependencies was installed for isolated verification. This environment is not a full `uv sync --frozen` installation. Full application and Linux worker regressions remain pending.

Initial measured backend run passed 40 tests covering pure indicator references, data transformations, resolver and risk rules, persistence, authenticated blueprint behavior, CSRF rejection, revision conflicts, concurrent controls and closed execution admission. Research and connection-lifetime tests were added afterward. Final totals and commands are recorded in the implementation tracker.

Isolated feature tests use `--noconftest -p no:cacheprovider -o addopts=""` to avoid loading unrelated platform integrations in the minimal environment. They use temporary SQLite databases and a test Flask application with the actual feature blueprint and Flask-WTF middleware. Full OpenAlgo startup and final live-broker integration spies are pending. The execution admission test guards forbidden broker/generic-order imports while submission is closed. It does not certify an enabled execution pipeline.

The native cache can omit Angel exchange time. Native adapter tests verify missing-time, previous-session, missing-price, structured instrument and expiry rejection without creating a broker connection. Event and database resources use short-lived sessions, with explicit cleanup on success and conflict.

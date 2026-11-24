"""Disposable databases and synthetic secrets only; never run the rotation CLI."""

import base64
import sqlite3

import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from database.engine_factory import create_db_engine
from database.nifty_algo_db import NiftyDiscordReportRequest, NiftyDiscordSettings
from upgrade import rotate_pepper
from utils import env_check

OLD, NEW = "a" * 64, "b" * 64
SALT = "12" * 16
VALUES = ["synthetic-bot-token", "synthetic-private-token-1", "synthetic-private-token-2"]


def key(pepper, salt):
    return Fernet(
        base64.urlsafe_b64encode(
            PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100000).derive(
                pepper.encode()
            )
        )
    )


def install(path, fernet):
    engine = create_db_engine(f"sqlite:///{path.as_posix()}")
    try:
        NiftyDiscordSettings.__table__.create(engine)
        NiftyDiscordReportRequest.__table__.create(engine)
    finally:
        engine.dispose()
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO nifty_algo_discord_settings "
            "(user_id, application_id, revision, configuration, token_encrypted, updated_at) "
            "VALUES ('owner-a', '100000000000000001', 1, '{}', ?, '2026-11-24')",
            (fernet.encrypt(VALUES[0].encode()).decode(),),
        )
        for owner, interaction, value in (
            ("owner-a", "300000000000000001", VALUES[1]),
            ("owner-b", "300000000000000001", VALUES[2]),
            ("owner-a", "300000000000000002", None),
        ):
            db.execute(
                "INSERT INTO nifty_algo_discord_report_request "
                "(user_id, interaction_id, application_id, token_encrypted, payload, "
                "status, attempts, next_at, expires_at) "
                "VALUES (?, ?, '100000000000000001', ?, '{}', 'PENDING', 0, '2026-11-24', '2026-11-25')",
                (owner, interaction, fernet.encrypt(value.encode()).decode() if value else None),
            )


def stored(path):
    with sqlite3.connect(path) as db:
        settings = db.execute(
            "SELECT user_id, token_encrypted FROM nifty_algo_discord_settings"
        ).fetchall()
        requests = db.execute(
            "SELECT user_id, interaction_id, token_encrypted FROM nifty_algo_discord_report_request "
            "ORDER BY user_id, interaction_id"
        ).fetchall()
    return settings, requests


def assert_preserved(path, fernet):
    settings, requests = stored(path)
    assert settings[0][0] == "owner-a"
    assert fernet.decrypt(settings[0][1].encode()).decode() == VALUES[0]
    assert requests[0][:2] == ("owner-a", "300000000000000001")
    assert fernet.decrypt(requests[0][2].encode()).decode() == VALUES[1]
    assert requests[1] == ("owner-a", "300000000000000002", None)
    assert requests[2][:2] == ("owner-b", "300000000000000001")
    assert fernet.decrypt(requests[2][2].encode()).decode() == VALUES[2]


@pytest.mark.parametrize("salt", [bytes.fromhex(SALT), b"openalgo_static_salt"])
def test_pepper_rotation_preserves_composite_ownership_and_never_double_encrypts(
    tmp_path, monkeypatch, salt
):
    if salt == b"openalgo_static_salt":
        monkeypatch.delenv("FERNET_SALT", raising=False)
    else:
        monkeypatch.setenv("FERNET_SALT", salt.hex())
    path = tmp_path / "rotation.db"
    install(path, key(OLD, salt))
    with sqlite3.connect(path) as db:
        rotator = rotate_pepper.Rotator(db, OLD, NEW)
        rotator.rotate_all()
        rotator.rotate_all()
        assert rotator.stats["nifty_algo_discord_settings.token_encrypted"] == 1
        assert rotator.stats["nifty_algo_discord_report_request.token_encrypted"] == 2
    assert_preserved(path, key(NEW, salt))


def test_salt_sampling_and_migration_cover_both_columns_and_string_keys(tmp_path, monkeypatch):
    path = tmp_path / "rotation.db"
    install(path, key(OLD, b"openalgo_static_salt"))
    assert len(env_check._sample_ciphertexts(str(path))) == 3
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{path.as_posix()}")
    for _ in range(2):
        env_check._migrate_fernet_db(str(tmp_path / ".env"), OLD, SALT)
    assert_preserved(path, key(OLD, bytes.fromhex(SALT)))


def test_pepper_refuses_unreadable_ciphertext_and_rolls_back_other_changes(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv("FERNET_SALT", SALT)
    path = tmp_path / "rotation.db"
    install(path, key(OLD, bytes.fromhex(SALT)))
    with sqlite3.connect(path) as db:
        db.execute(
            "UPDATE nifty_algo_discord_report_request SET token_encrypted='unreadable-private-value' "
            "WHERE user_id='owner-b'"
        )
    before = stored(path)
    with (
        pytest.raises(ValueError, match="NIFTY credential pepper rotation refused"),
        sqlite3.connect(path) as db,
    ):
        rotate_pepper.Rotator(db, OLD, NEW).rotate_all()
    assert stored(path) == before
    assert "unreadable-private-value" not in capsys.readouterr().out


@pytest.mark.parametrize("failure", ["ciphertext", "database"])
@pytest.mark.parametrize("placeholder", [False, True])
def test_failed_salt_migration_restores_synthetic_env_and_database(
    tmp_path, monkeypatch, failure, placeholder
):
    path = tmp_path / "rotation.db"
    install(path, key(OLD, b"openalgo_static_salt"))
    with sqlite3.connect(path) as db:
        if failure == "ciphertext":
            db.execute(
                "UPDATE nifty_algo_discord_report_request SET token_encrypted='unreadable-private-value' "
                "WHERE user_id='owner-b'"
            )
        else:
            db.execute(
                "CREATE TRIGGER refuse_rotation BEFORE UPDATE ON nifty_algo_discord_report_request "
                "BEGIN SELECT RAISE(ABORT, 'synthetic confidential db failure'); END"
            )
    before = stored(path)
    env = tmp_path / ".env"
    original = f"API_KEY_PEPPER = '{OLD}'\n"
    if placeholder:
        original += f"FERNET_SALT = '{env_check.PLACEHOLDER_FERNET_SALT}'\n"
    env.write_text(original, encoding="utf-8")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{path.as_posix()}")
    monkeypatch.setenv("API_KEY_PEPPER", OLD)
    monkeypatch.delenv("FERNET_SALT", raising=False)
    # Startup continues on the legacy salt the restored file and database agree on.
    env_check._ensure_fernet_salt(str(env))
    assert env.read_text(encoding="utf-8") == original
    assert stored(path) == before
    assert "FERNET_SALT" not in __import__("os").environ
    if failure == "database":
        assert_preserved(path, key(OLD, b"openalgo_static_salt"))


def test_failed_salt_restore_aborts_startup(tmp_path, monkeypatch):
    path = tmp_path / "rotation.db"
    install(path, key(OLD, b"openalgo_static_salt"))
    with sqlite3.connect(path) as db:
        db.execute(
            "UPDATE nifty_algo_discord_report_request SET token_encrypted='unreadable-private-value' "
            "WHERE user_id='owner-b'"
        )
    env = tmp_path / ".env"
    env.write_text(f"API_KEY_PEPPER = '{OLD}'\n", encoding="utf-8")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{path.as_posix()}")
    monkeypatch.setenv("API_KEY_PEPPER", OLD)
    monkeypatch.delenv("FERNET_SALT", raising=False)

    write = env_check._atomic_replace_text
    calls = []

    def restore_refused(*args):
        # The salt write succeeds; only the restore after the failed migration fails.
        calls.append(args)
        if len(calls) > 1:
            raise OSError("synthetic read-only settings file")
        return write(*args)

    monkeypatch.setattr(env_check, "_atomic_replace_text", restore_refused)
    with pytest.raises(RuntimeError, match="matched backup"):
        env_check._ensure_fernet_salt(str(env))
    assert "FERNET_SALT" not in __import__("os").environ

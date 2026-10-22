import pytest

from connect_over_ssm import session
from connect_over_ssm.session import (
    Forward,
    PreflightError,
    build_command,
    exec_session,
    parse_forward,
    preflight,
)

IID = "i-0123456789abcdef0"


def test_parse_forward_two_part():
    assert parse_forward("8080:80") == Forward(8080, 80)


def test_parse_forward_three_part():
    assert parse_forward("5432:db.internal:5432") == Forward(5432, 5432, "db.internal")


@pytest.mark.parametrize("spec", ["abc", "0:80", "80:70000", "1:2:3:4", "a:b", ""])
def test_parse_forward_rejects(spec):
    with pytest.raises(ValueError):
        parse_forward(spec)


def test_build_command_plain():
    assert build_command(IID, None, None, None) == [
        "aws",
        "ssm",
        "start-session",
        "--target",
        IID,
    ]


def test_build_command_profile_region_order():
    argv = build_command(IID, "dev", "us-west-2", None)
    assert argv[-4:] == ["--profile", "dev", "--region", "us-west-2"]


def test_build_command_forward_local():
    assert build_command(IID, None, None, Forward(8080, 80)) == [
        "aws",
        "ssm",
        "start-session",
        "--target",
        IID,
        "--document-name",
        "AWS-StartPortForwardingSession",
        "--parameters",
        '{"portNumber":["80"],"localPortNumber":["8080"]}',
    ]


def test_build_command_forward_remote_host():
    assert build_command(IID, None, None, Forward(5432, 5432, "db.internal")) == [
        "aws",
        "ssm",
        "start-session",
        "--target",
        IID,
        "--document-name",
        "AWS-StartPortForwardingSessionToRemoteHost",
        "--parameters",
        '{"host":["db.internal"],"portNumber":["5432"],"localPortNumber":["5432"]}',
    ]


def test_preflight_missing_aws(monkeypatch):
    monkeypatch.setattr(session.shutil, "which", lambda name: None)
    with pytest.raises(PreflightError, match="AWS CLI not found on PATH"):
        preflight()


def test_preflight_missing_plugin(monkeypatch):
    monkeypatch.setattr(
        session.shutil, "which", lambda name: "/bin/aws" if name == "aws" else None
    )
    with pytest.raises(PreflightError, match="session-manager-plugin not found on PATH"):
        preflight()


def test_preflight_ok(monkeypatch):
    monkeypatch.setattr(session.shutil, "which", lambda name: "/bin/" + name)
    preflight()


def test_exec_session_calls_execvp(monkeypatch):
    calls = []
    monkeypatch.setattr(session.os, "execvp", lambda f, a: calls.append((f, a)))
    argv = ["aws", "ssm", "start-session"]
    exec_session(argv)
    assert calls == [("aws", argv)]

import io

import pytest
from botocore.exceptions import ClientError

from connect_over_ssm import __version__
from connect_over_ssm.cli import main, pick
from connect_over_ssm.instances import Instance
from connect_over_ssm.session import build_command

AMI = "ami-12c6146b"


def launch(ec2, name=None):
    kwargs = {}
    if name is not None:
        kwargs["TagSpecifications"] = [
            {"ResourceType": "instance", "Tags": [{"Key": "Name", "Value": name}]}
        ]
    resp = ec2.run_instances(ImageId=AMI, MinCount=1, MaxCount=1, **kwargs)
    return resp["Instances"][0]["InstanceId"]


class FakeStdin:
    def __init__(self, lines, tty=True):
        self._lines = list(lines)
        self._tty = tty

    def isatty(self):
        return self._tty

    def readline(self):
        return self._lines.pop(0) if self._lines else ""


@pytest.fixture
def execs(monkeypatch):
    calls = []

    def fake_execvp(file, argv):
        calls.append(list(argv))
        raise SystemExit(0)

    monkeypatch.setattr("connect_over_ssm.session.os.execvp", fake_execvp)
    monkeypatch.setattr("connect_over_ssm.session.shutil.which", lambda name: "/usr/bin/x")
    return calls


@pytest.fixture
def online(monkeypatch):
    monkeypatch.setattr(
        "connect_over_ssm.cli.ssm_statuses", lambda ssm, ids: {i: "Online" for i in ids}
    )


@pytest.fixture(autouse=True)
def non_tty_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", FakeStdin([], tty=False))


def test_no_target_is_usage_error():
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2


@pytest.mark.parametrize("spec", ["abc", "0:80", "80:70000", "1:2:3:4"])
def test_forward_invalid_is_usage_error(spec, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["web", "-f", spec])
    assert exc.value.code == 2
    assert "Traceback" not in capsys.readouterr().err


def test_connect_single_match_execs(ec2, execs, online):
    iid = launch(ec2, "web")
    with pytest.raises(SystemExit) as exc:
        main(["web"])
    assert exc.value.code == 0
    assert execs == [build_command(iid, None, None, None)]


def test_connect_passes_profile_region_and_forward(ec2, execs, online, monkeypatch, tmp_path):
    creds = tmp_path / "credentials"
    creds.write_text("[dev]\naws_access_key_id = testing\naws_secret_access_key = testing\n")
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(creds))
    launch(ec2, "web")
    with pytest.raises(SystemExit):
        main(["web", "-p", "dev", "-r", "us-east-1", "-f", "8080:80"])
    argv = execs[0]
    assert "AWS-StartPortForwardingSession" in argv
    assert argv[-4:] == ["--profile", "dev", "--region", "us-east-1"]


def test_connect_no_match_exit_1(ec2, execs, capsys):
    assert main(["nothing"]) == 1
    assert "ssm-connect --list" in capsys.readouterr().err
    assert execs == []


def test_many_matches_non_tty_lists_and_exits_1(ec2, execs, capsys):
    a = launch(ec2, "web")
    b = launch(ec2, "web")
    assert main(["web"]) == 1
    err = capsys.readouterr().err
    assert "error: 'web' matches 2 running instances:" in err
    assert f"  {a}  web" in err
    assert f"  {b}  web" in err
    assert "Use an instance ID to choose one." in err
    assert execs == []


def test_many_matches_tty_picker_selects_second(ec2, execs, online, monkeypatch):
    launch(ec2, "web")
    launch(ec2, "web")
    monkeypatch.setattr("sys.stdin", FakeStdin(["2\n"]))
    from connect_over_ssm.instances import find_instances

    expected = find_instances(ec2, "web")[1].id
    with pytest.raises(SystemExit):
        main(["web"])
    assert execs == [build_command(expected, None, None, None)]


def test_picker_eof_cancels(ec2, execs, capsys, monkeypatch):
    launch(ec2, "web")
    launch(ec2, "web")
    monkeypatch.setattr("sys.stdin", FakeStdin([]))
    assert main(["web"]) == 1
    assert "Cancelled." in capsys.readouterr().err
    assert execs == []


def test_picker_three_bad_answers(capsys):
    items = [
        Instance("i-1", "a", "10.0.0.1", "t2.micro", "running"),
        Instance("i-2", "b", None, "t2.micro", "running"),
    ]
    stdin = FakeStdin(["x\n", "9\n", "0\n", "1\n"])
    err = io.StringIO()
    assert pick(items, stdin, err) is None
    assert err.getvalue().count("Please enter a number from 1 to 2.") == 3
    assert "  [1] a  i-1  10.0.0.1" in err.getvalue()
    assert "Select an instance [1-2]: " in err.getvalue()


def test_picker_selects(capsys):
    items = [Instance("i-1", "a", "10.0.0.1", "t2.micro", "running")]
    assert pick(items, FakeStdin(["1\n"]), io.StringIO()) == items[0]


def test_offline_ssm_refuses(ec2, execs, capsys, monkeypatch):
    iid = launch(ec2, "web")
    monkeypatch.setattr(
        "connect_over_ssm.cli.ssm_statuses", lambda ssm, ids: {i: "ConnectionLost" for i in ids}
    )
    assert main(["web"]) == 1
    err = capsys.readouterr().err
    assert (
        f"error: {iid} (web) is not reachable over SSM (status: ConnectionLost). "
        "Use --force to try anyway." in err
    )
    assert execs == []


def test_force_connects_when_offline(ec2, execs, monkeypatch):
    iid = launch(ec2, "web")
    monkeypatch.setattr(
        "connect_over_ssm.cli.ssm_statuses", lambda ssm, ids: {i: "ConnectionLost" for i in ids}
    )
    with pytest.raises(SystemExit):
        main(["web", "--force"])
    assert execs == [build_command(iid, None, None, None)]


def test_preflight_failure_exit_1(ec2, execs, capsys, monkeypatch):
    launch(ec2, "web")
    monkeypatch.setattr("connect_over_ssm.session.shutil.which", lambda name: None)
    assert main(["web"]) == 1
    assert capsys.readouterr().err.startswith("error: AWS CLI not found")
    assert execs == []


def test_list_prints_table(ec2, monkeypatch, capsys):
    a = launch(ec2, "web")
    b = launch(ec2)
    monkeypatch.setattr(
        "connect_over_ssm.cli.ssm_statuses",
        lambda ssm, ids: {a: "Online", b: "NotManaged"},
    )
    assert main(["--list"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 3
    assert lines[0].split() == ["NAME", "INSTANCE", "ID", "PRIVATE", "IP", "TYPE", "SSM"]
    rows = {line.split()[0]: line.split() for line in lines[1:]}
    assert rows["web"][1] == a
    assert rows["web"][-1] == "Online"
    assert rows["-"][1] == b
    assert rows["-"][-1] == "NotManaged"
    assert lines[0].startswith("NAME  INSTANCE ID  ")


def test_list_empty_exit_0(ec2, capsys):
    assert main(["--list", "nope*"]) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "No running instances match 'nope*'." in captured.err


def test_aws_error_is_clean_exit_1(monkeypatch, execs, capsys):
    def boom(ec2, target):
        raise ClientError(
            {"Error": {"Code": "UnauthorizedOperation", "Message": "denied"}}, "DescribeInstances"
        )

    monkeypatch.setattr("connect_over_ssm.cli.find_instances", boom)
    assert main(["web"]) == 1
    err = capsys.readouterr().err
    assert err.startswith("error:")
    assert "Traceback" not in err


def test_missing_profile_is_clean_exit_1(execs, capsys):
    assert main(["web", "-p", "does-not-exist"]) == 1
    assert capsys.readouterr().err.startswith("error:")


def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"ssm-connect {__version__}"

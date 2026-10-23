"""The README IAM section must cover every AWS call the tool makes."""

import re
from pathlib import Path

import boto3
import pytest
from botocore.stub import Stubber
from moto import mock_aws

from connect_over_ssm.cli import main

README = Path(__file__).resolve().parent.parent / "README.md"
AMI = "ami-12c6146b"


def documented_actions():
    text = README.read_text()
    section = text.split("## IAM permissions", 1)[1].split("\n## ", 1)[0]
    return set(re.findall(r"\b(?:ec2|ssm):[A-Z][A-Za-z]+", section))


@pytest.fixture
def call_log(monkeypatch):
    calls = set()
    real_session = boto3.Session

    def factory(*args, **kwargs):
        session = real_session(*args, **kwargs)

        def record(model, **_):
            calls.add(f"{model.service_model.endpoint_prefix}:{model.name}")

        session.events.register("before-call.*.*", record)
        real_client = session.client

        def client(service_name, *a, **kw):
            made = real_client(service_name, *a, **kw)
            if service_name == "ssm":
                # moto's ec2 extra does not serve SSM, so stub its responses.
                stubber = Stubber(made)
                stubber.add_response(
                    "describe_instance_information", {"InstanceInformationList": []}
                )
                stubber.activate()
            return made

        session.client = client
        return session

    monkeypatch.setattr("connect_over_ssm.cli.boto3.Session", factory)
    return calls


@pytest.fixture
def instance(monkeypatch):
    monkeypatch.setattr("connect_over_ssm.session.shutil.which", lambda name: "/usr/bin/x")

    def fake_execvp(file, argv):
        raise SystemExit(0)

    monkeypatch.setattr("connect_over_ssm.session.os.execvp", fake_execvp)
    with mock_aws():
        ec2 = boto3.client("ec2", region_name="us-east-1")
        ec2.run_instances(
            ImageId=AMI,
            MinCount=1,
            MaxCount=1,
            TagSpecifications=[
                {"ResourceType": "instance", "Tags": [{"Key": "Name", "Value": "web"}]}
            ],
        )
        yield


def test_connect_and_list_calls_are_documented(instance, call_log):
    with pytest.raises(SystemExit):
        main(["web", "--force"])
    assert main(["--list"]) == 0
    documented = documented_actions()
    assert {"ec2:DescribeInstances", "ssm:DescribeInstanceInformation"} <= call_log
    assert call_log <= documented
    assert "ssm:StartSession" in documented

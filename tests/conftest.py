import boto3
import pytest
from moto import mock_aws


@pytest.fixture(autouse=True)
def aws_env(monkeypatch, tmp_path):
    empty_config = tmp_path / "empty_aws_config"
    empty_credentials = tmp_path / "empty_aws_credentials"
    empty_config.write_text("")
    empty_credentials.write_text("")
    monkeypatch.setenv("AWS_CONFIG_FILE", str(empty_config))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(empty_credentials))
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.delenv("AWS_PROFILE", raising=False)


@pytest.fixture
def ec2(aws_env):
    with mock_aws():
        yield boto3.client("ec2", region_name="us-east-1")

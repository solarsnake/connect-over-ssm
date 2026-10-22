import boto3
from botocore.stub import Stubber

from connect_over_ssm.instances import (
    Instance,
    find_instances,
    list_instances,
    ssm_statuses,
)

AMI = "ami-12c6146b"


def launch(ec2, name=None):
    kwargs = {}
    if name is not None:
        kwargs["TagSpecifications"] = [
            {"ResourceType": "instance", "Tags": [{"Key": "Name", "Value": name}]}
        ]
    resp = ec2.run_instances(ImageId=AMI, MinCount=1, MaxCount=1, **kwargs)
    return resp["Instances"][0]["InstanceId"]


def test_find_by_name_returns_running_only(ec2):
    launch(ec2, "web")
    stopped = launch(ec2, "web")
    ec2.stop_instances(InstanceIds=[stopped])
    result = find_instances(ec2, "web")
    assert len(result) == 1
    assert result[0].state == "running"


def test_find_wildcard(ec2):
    launch(ec2, "web-2")
    launch(ec2, "web-1")
    launch(ec2, "db")
    assert [i.name for i in find_instances(ec2, "web-*")] == ["web-1", "web-2"]


def test_find_by_instance_id(ec2):
    iid = launch(ec2, "web")
    result = find_instances(ec2, iid)
    assert len(result) == 1
    assert isinstance(result[0], Instance)
    assert result[0].id == iid
    assert result[0].name == "web"


def test_find_no_match_returns_empty(ec2):
    launch(ec2, "web")
    assert find_instances(ec2, "nothing") == []


def test_find_uses_paginator(ec2):
    for n in ("a", "b", "c"):
        launch(ec2, n)
    calls = []
    original = ec2.get_paginator

    def spy(op):
        calls.append(op)
        return original(op)

    ec2.get_paginator = spy
    result = find_instances(ec2, "*", page_size=1)
    assert calls == ["describe_instances"]
    assert [i.name for i in result] == ["a", "b", "c"]


def test_list_instance_without_name_tag(ec2):
    iid = launch(ec2)
    result = list_instances(ec2)
    assert [i.id for i in result] == [iid]
    assert result[0].name is None


def test_ssm_statuses_maps_and_defaults():
    ssm = boto3.client("ssm", region_name="us-east-1")
    with Stubber(ssm) as stub:
        stub.add_response(
            "describe_instance_information",
            {
                "InstanceInformationList": [
                    {"InstanceId": "i-0123456789abcdef0", "PingStatus": "Online"}
                ]
            },
            expected_params={
                "Filters": [
                    {
                        "Key": "InstanceIds",
                        "Values": ["i-0123456789abcdef0", "i-0fedcba9876543210"],
                    }
                ]
            },
        )
        result = ssm_statuses(ssm, ["i-0123456789abcdef0", "i-0fedcba9876543210"])
    assert result == {
        "i-0123456789abcdef0": "Online",
        "i-0fedcba9876543210": "NotManaged",
    }


def test_ssm_statuses_empty_makes_no_call():
    ssm = boto3.client("ssm", region_name="us-east-1")
    with Stubber(ssm):
        assert ssm_statuses(ssm, []) == {}


def test_ssm_statuses_chunks_ids_by_50():
    ssm = boto3.client("ssm", region_name="us-east-1")
    ids = [f"i-{n:017x}" for n in range(120)]
    with Stubber(ssm) as stub:
        for chunk in (ids[:50], ids[50:100], ids[100:]):
            stub.add_response(
                "describe_instance_information",
                {
                    "InstanceInformationList": [
                        {"InstanceId": chunk[0], "PingStatus": "Online"},
                    ]
                },
                expected_params={"Filters": [{"Key": "InstanceIds", "Values": chunk}]},
            )
        result = ssm_statuses(ssm, ids)
        stub.assert_no_pending_responses()
    assert len(result) == 120
    online = {iid for iid, status in result.items() if status == "Online"}
    assert online == {ids[0], ids[50], ids[100]}
    assert all(s == "NotManaged" for iid, s in result.items() if iid not in online)


def test_list_sorts_untagged_last(ec2):
    untagged = launch(ec2)
    launch(ec2, "zeta")
    launch(ec2, "alpha")
    result = list_instances(ec2)
    assert [i.name for i in result] == ["alpha", "zeta", None]
    assert result[-1].id == untagged


def test_find_nonexistent_instance_id_returns_empty(ec2):
    launch(ec2, "web")
    assert find_instances(ec2, "i-0123456789abcdef0") == []

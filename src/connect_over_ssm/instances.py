"""Look up EC2 instances and their SSM agent status."""

import re
from dataclasses import dataclass

INSTANCE_ID_RE = re.compile(r"^i-[0-9a-f]{8}([0-9a-f]{9})?$")


@dataclass(frozen=True)
class Instance:
    id: str
    name: str | None
    private_ip: str | None
    instance_type: str
    state: str


def _paginate(client, operation, page_size, **kwargs):
    paginator = client.get_paginator(operation)
    if page_size:
        kwargs["PaginationConfig"] = {"PageSize": page_size}
    return paginator.paginate(**kwargs)


def _name_tag(raw):
    for tag in raw.get("Tags", []):
        if tag["Key"] == "Name":
            return tag["Value"]
    return None


def _describe(ec2, kwargs, page_size):
    found = []
    for page in _paginate(ec2, "describe_instances", page_size, **kwargs):
        for reservation in page["Reservations"]:
            for raw in reservation["Instances"]:
                found.append(
                    Instance(
                        id=raw["InstanceId"],
                        name=_name_tag(raw),
                        private_ip=raw.get("PrivateIpAddress"),
                        instance_type=raw["InstanceType"],
                        state=raw["State"]["Name"],
                    )
                )
    return sorted(found, key=lambda i: (i.name or "", i.id))


def find_instances(ec2, target: str, page_size: int | None = None) -> list[Instance]:
    """Return running instances matching an instance ID or a Name tag pattern."""
    filters = [{"Name": "instance-state-name", "Values": ["running"]}]
    kwargs = {"Filters": filters}
    if INSTANCE_ID_RE.match(target):
        kwargs["InstanceIds"] = [target]
    else:
        filters.insert(0, {"Name": "tag:Name", "Values": [target]})
    return _describe(ec2, kwargs, page_size)


def list_instances(ec2, pattern: str = "*", page_size: int | None = None) -> list[Instance]:
    """Return running instances matching a Name pattern; "*" includes untagged ones."""
    if pattern == "*":
        kwargs = {"Filters": [{"Name": "instance-state-name", "Values": ["running"]}]}
        return _describe(ec2, kwargs, page_size)
    return find_instances(ec2, pattern, page_size)


def ssm_statuses(ssm, instance_ids: list[str]) -> dict[str, str]:
    """Map each instance ID to its SSM ping status, or "NotManaged" if absent."""
    if not instance_ids:
        return {}
    statuses = {iid: "NotManaged" for iid in instance_ids}
    pages = _paginate(
        ssm,
        "describe_instance_information",
        None,
        Filters=[{"Key": "InstanceIds", "Values": instance_ids}],
    )
    for page in pages:
        for info in page["InstanceInformationList"]:
            statuses[info["InstanceId"]] = info["PingStatus"]
    return statuses

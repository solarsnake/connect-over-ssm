"""The ssm-connect command line interface."""

import argparse
import sys

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoRegionError

from . import __version__
from .instances import Instance, find_instances, list_instances, ssm_statuses
from .session import (
    PreflightError,
    build_command,
    exec_session,
    parse_forward,
    preflight,
)

MAX_BAD_ANSWERS = 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ssm-connect",
        description="Connect to EC2 instances over AWS Systems Manager by Name tag or instance ID.",
    )
    parser.add_argument("target", nargs="?", help="instance ID or Name tag (wildcards allowed)")
    parser.add_argument(
        "-l",
        "--list",
        nargs="?",
        const="*",
        metavar="PATTERN",
        help="list running instances (optionally matching a Name pattern) and exit",
    )
    parser.add_argument("-p", "--profile", help="AWS profile name")
    parser.add_argument("-r", "--region", help="AWS region")
    parser.add_argument(
        "-f",
        "--forward",
        metavar="SPEC",
        help="forward a port: LOCAL:REMOTE or LOCAL:HOST:REMOTE",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="connect even if SSM does not report the instance Online",
    )
    parser.add_argument("--version", action="version", version=f"ssm-connect {__version__}")
    return parser


def pick(instances: list[Instance], stdin, stderr) -> Instance | None:
    """Ask the user to choose one instance; return None on cancel or repeated bad input."""
    count = len(instances)
    for number, inst in enumerate(instances, 1):
        print(f"  [{number}] {inst.name or '-'}  {inst.id}  {inst.private_ip or '-'}", file=stderr)
    for _ in range(MAX_BAD_ANSWERS):
        stderr.write(f"Select an instance [1-{count}]: ")
        stderr.flush()
        line = stdin.readline()
        if not line:
            stderr.write("\n")
            return None
        if not line.strip():
            return None
        answer = line.strip()
        if answer.isascii() and answer.isdigit() and 1 <= int(answer) <= count:
            return instances[int(answer) - 1]
        print(f"Please enter a number from 1 to {count}.", file=stderr)
    return None


def _print_table(instances: list[Instance], statuses: dict[str, str]) -> None:
    header = ["NAME", "INSTANCE ID", "PRIVATE IP", "TYPE", "SSM"]
    rows = [
        [
            i.name or "-",
            i.id,
            i.private_ip or "-",
            i.instance_type or "-",
            statuses.get(i.id, "NotManaged"),
        ]
        for i in instances
    ]
    widths = [max(len(r[c]) for r in [header, *rows]) + 2 for c in range(len(header))]
    for row in [header, *rows]:
        print("".join(cell.ljust(w) for cell, w in zip(row, widths, strict=True)).rstrip())


def _run(args, parser) -> int:
    forward = None
    if args.forward is not None:
        try:
            forward = parse_forward(args.forward)
        except ValueError as exc:
            parser.error(str(exc))

    if args.list is not None:
        session = boto3.Session(profile_name=args.profile, region_name=args.region)
        instances = list_instances(session.client("ec2"), args.list)
        if not instances:
            print(f"No running instances match '{args.list}'.", file=sys.stderr)
            return 0
        statuses = ssm_statuses(session.client("ssm"), [i.id for i in instances])
        _print_table(instances, statuses)
        return 0

    try:
        preflight()
    except PreflightError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    matches = find_instances(session.client("ec2"), args.target)
    if not matches:
        print(
            f"error: no running instance matches '{args.target}'. Try: ssm-connect --list",
            file=sys.stderr,
        )
        return 1
    if len(matches) == 1:
        chosen = matches[0]
    elif sys.stdin.isatty():
        chosen = pick(matches, sys.stdin, sys.stderr)
        if chosen is None:
            print("Cancelled.", file=sys.stderr)
            return 1
    else:
        print(f"error: '{args.target}' matches {len(matches)} running instances:", file=sys.stderr)
        for inst in matches:
            print(f"  {inst.id}  {inst.name or '-'}", file=sys.stderr)
        print("Use an instance ID to choose one.", file=sys.stderr)
        return 1

    label = f"{chosen.id} ({chosen.name or '-'})"
    try:
        status = ssm_statuses(session.client("ssm"), [chosen.id]).get(chosen.id, "NotManaged")
    except (BotoCoreError, ClientError) as exc:
        if not args.force:
            raise
        print(
            f"warning: could not check SSM status ({exc}); continuing because of --force",
            file=sys.stderr,
        )
        status = "Online"
    if status != "Online" and not args.force:
        print(
            f"error: {label} is not reachable over SSM (status: {status}). "
            "Use --force to try anyway.",
            file=sys.stderr,
        )
        return 1

    print(f"Connecting to {label}...", file=sys.stderr)
    exec_session(build_command(chosen.id, args.profile, session.region_name, forward))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.target is None and args.list is None:
        parser.error("a target is required unless --list is given")
    try:
        return _run(args, parser)
    except KeyboardInterrupt:
        print(file=sys.stderr)
        print("Cancelled.", file=sys.stderr)
        return 130
    except NoRegionError:
        print(
            "error: no AWS region set (use -r or configure a default region)",
            file=sys.stderr,
        )
        return 1
    except (BotoCoreError, ClientError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

"""Build and run AWS SSM start-session commands, with optional port forwarding."""

import json
import os
import shutil
from dataclasses import dataclass
from typing import NoReturn

AWS_CLI_INSTALL_URL = (
    "https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
)
PLUGIN_INSTALL_URL = (
    "https://docs.aws.amazon.com/systems-manager/latest/userguide/"
    "session-manager-working-with-install-plugin.html"
)


@dataclass(frozen=True)
class Forward:
    local_port: int
    remote_port: int
    host: str | None = None


class PreflightError(Exception):
    """A required local tool is missing from PATH."""


def _port(text: str) -> int | None:
    if not (text.isascii() and text.isdigit()):
        return None
    return int(text)


def parse_forward(spec: str) -> Forward:
    """Parse LOCAL:REMOTE or LOCAL:HOST:REMOTE into a Forward."""
    shape_error = ValueError(
        f"invalid --forward '{spec}': expected LOCAL:REMOTE or LOCAL:HOST:REMOTE"
    )
    parts = spec.split(":")
    if len(parts) == 2:
        host = None
        local_text, remote_text = parts
    elif len(parts) == 3 and parts[1]:
        local_text, host, remote_text = parts
    else:
        raise shape_error
    local, remote = _port(local_text), _port(remote_text)
    if local is None or remote is None:
        raise shape_error
    if not (1 <= local <= 65535 and 1 <= remote <= 65535):
        raise ValueError(f"invalid --forward '{spec}': ports must be 1-65535")
    return Forward(local, remote, host)


def build_command(
    instance_id: str,
    profile: str | None,
    region: str | None,
    forward: Forward | None,
) -> list[str]:
    """Return the aws CLI argv that starts a session on the instance."""
    argv = ["aws", "ssm", "start-session", "--target", instance_id]
    if forward is not None:
        if forward.host is None:
            document = "AWS-StartPortForwardingSession"
            params = {
                "portNumber": [str(forward.remote_port)],
                "localPortNumber": [str(forward.local_port)],
            }
        else:
            document = "AWS-StartPortForwardingSessionToRemoteHost"
            params = {
                "host": [forward.host],
                "portNumber": [str(forward.remote_port)],
                "localPortNumber": [str(forward.local_port)],
            }
        argv += [
            "--document-name",
            document,
            "--parameters",
            json.dumps(params, separators=(",", ":")),
        ]
    if profile:
        argv += ["--profile", profile]
    if region:
        argv += ["--region", region]
    return argv


def preflight() -> None:
    """Raise PreflightError unless the AWS CLI and session-manager-plugin are on PATH."""
    if shutil.which("aws") is None:
        raise PreflightError(f"AWS CLI not found on PATH. Install it: {AWS_CLI_INSTALL_URL}")
    if shutil.which("session-manager-plugin") is None:
        raise PreflightError(
            f"session-manager-plugin not found on PATH. Install it: {PLUGIN_INSTALL_URL}"
        )


def exec_session(argv: list[str]) -> NoReturn:
    """Replace the current process with the given command."""
    os.execvp(argv[0], argv)

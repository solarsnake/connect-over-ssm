# connect-over-ssm

![CI](https://github.com/solarsnake/connect-over-ssm/actions/workflows/ci.yml/badge.svg)

Connect to EC2 instances over AWS Systems Manager by Name tag. No SSH keys, no bastion, no open port 22.

## What it does

`ssm-connect` looks up running instances by Name tag (wildcards allowed) or instance ID, checks that SSM can reach the one you picked, and starts a Session Manager session. It can also forward a local port to the instance or to a host behind it, such as an RDS endpoint.

If a name matches several instances, you get a numbered picker on a terminal. In a script it lists the matches and exits 1 so you can use an instance ID instead.

## Requirements

- Python 3.11+
- [AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
- [Session Manager plugin](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html)

## Install

```bash
pipx install git+https://github.com/solarsnake/connect-over-ssm
```

## Usage

```bash
ssm-connect web-1                 # by Name tag
ssm-connect 'web-*'               # wildcard
ssm-connect i-0123456789abcdef0   # by instance ID
ssm-connect web-1 -p dev -r us-west-2
```

List running instances and their SSM status (table goes to stdout):

```console
$ ssm-connect --list
NAME   INSTANCE ID          PRIVATE IP  TYPE      SSM
web-1  i-0a1b2c3d4e5f60718  10.0.1.12   t3.micro  Online
web-2  i-0b2c3d4e5f6071829  10.0.1.47   t3.micro  Online
-      i-0c3d4e5f60718293a  10.0.2.9    t3.small  NotManaged
```

`--list` takes an optional Name pattern: `ssm-connect --list 'web-*'`. An instance with no Name tag shows `-` and can be reached by instance ID.

Forward a local port to the instance:

```bash
ssm-connect web-1 -f 8080:80
```

Forward a local port to a host reachable from the instance:

```bash
ssm-connect web-1 -f 5432:mydb.abc.us-east-1.rds.amazonaws.com:5432
```

Pick a profile and region with `-p` and `-r`; they are also passed to the session.

If SSM does not report the instance as Online, `ssm-connect` refuses to connect. Use `--force` to try anyway.

Options:

| Flag | Meaning |
| --- | --- |
| `-l`, `--list [PATTERN]` | list running instances (optionally matching a Name pattern) and exit |
| `-p`, `--profile PROFILE` | AWS profile name |
| `-r`, `--region REGION` | AWS region |
| `-f`, `--forward SPEC` | forward a port: `LOCAL:REMOTE` or `LOCAL:HOST:REMOTE` |
| `--force` | connect even if SSM does not report the instance Online |
| `--version` | show the version and exit |

Messages go to stderr and data to stdout.

Exit codes: 0 success, 1 runtime/AWS error or nothing matched, 2 usage error, 130 cancelled (Ctrl-C).

## IAM permissions

Your identity needs:

- `ec2:DescribeInstances` and `ssm:DescribeInstanceInformation`, on `*`.
- `ssm:StartSession` on the instances (`arn:aws:ec2:<region>:<account>:instance/*`, or narrower) and on the SSM documents in use. Port forwarding uses `AWS-StartPortForwardingSession` and `AWS-StartPortForwardingSessionToRemoteHost`. A plain session uses `SSM-SessionManagerRunShell`.
- `ssm:TerminateSession` and `ssm:ResumeSession` on your own sessions, `arn:aws:ssm:*:*:session/${aws:userid}-*`.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["ec2:DescribeInstances", "ssm:DescribeInstanceInformation"],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": "ssm:StartSession",
      "Resource": [
        "arn:aws:ec2:<region>:<account>:instance/*",
        "arn:aws:ssm:<region>::document/AWS-StartPortForwardingSession",
        "arn:aws:ssm:<region>::document/AWS-StartPortForwardingSessionToRemoteHost",
        "arn:aws:ssm:<region>::document/SSM-SessionManagerRunShell"
      ]
    },
    {
      "Effect": "Allow",
      "Action": ["ssm:TerminateSession", "ssm:ResumeSession"],
      "Resource": "arn:aws:ssm:*:*:session/${aws:userid}-*"
    }
  ]
}
```

In GovCloud or other partitions, use your partition in the ARNs (for example `arn:aws-us-gov`). The instances themselves need the SSM Agent and an instance profile that allows Systems Manager.

## Safety notes

- Only running instances are considered.
- It will not start a session on an instance SSM reports as anything but Online unless you pass `--force`.
- It never opens a port on the instance. Forwarded ports listen on your machine.
- Credentials come from the normal AWS CLI/boto3 chain. Nothing is stored or logged.

## Upgrading from the shell function

Earlier versions were a `connect.py` script wrapped in a shell function. Remove the `connect()` function from your shell rc file. If you want to keep the command name:

```bash
alias connect=ssm-connect
```

The profile is now a flag: `connect <profile> <name>` becomes `ssm-connect <name> -p <profile>`.

## Running the tests

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
```

Tests need Python 3.11+, use moto, and never touch real AWS.

## License

GPLv3 (GPL-3.0-or-later). See [LICENSE](LICENSE).

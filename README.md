# Connect Over SSM

## Overview
`connect.py` is a Python script designed to facilitate connecting to AWS EC2 instances using their `Name` tags. It replaces traditional SSH methods by integrating with the AWS Command Line Interface (CLI) and the AWS Systems Manager (SSM) service. The script is intended to be used as a command within the shell (bash or zsh), allowing users to connect to instances via a simple command.

## Dependencies
To use connect.py, you need the following dependencies installed:

- **Python 3**: The script is written in Python and requires Python 3 to run.
- **AWS CLI**: Required for interfacing with AWS services. The script requires a *valid* profile to interact with your instance.
- **Boto3**: A Python library for AWS.
- **AWS SSM Plugin**: Necessary for starting sessions with instances.
  
### Installation Steps

- [Install Python 3](https://www.python.org/downloads/)
- [Install AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
- Install Boto3
```bash
# one method to accomplish this
pip install boto3
```
- [Install AWS SSM Plugin](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html)

#### Integrating with Shell
**Copy script to PATH**
```bash
sudo cp connect.py /usr/local/bin
sudo chmod +x /usr/local/bin/connect.py
```
**Configuring your shell**:
- For zsh users, modify your ~/.zshrc file.
- For bash users, modify your ~/.bashrc file.
Add the following function:
```bash
connect() {
    if [[ $# -lt 2 ]]; then
        echo "Usage: connect <AWS Profile> <Instance Name Tag>"
        return 1
    fi
    python3 /usr/local/bin/connect.py -p "$1" "$2"
}
```
Reload your shell configuration to utilize in your existing session if desired (source ~/.zshrc or source ~/.bashrc).

## Usage
After installation, use the connect command followed by the *valid* AWS CLI profile session and the instance `Name` tag:
```bash
connect <AWS Profile> <Instance Name Tag>
```
The script will handle the rest, connecting you to the specified EC2 instance.

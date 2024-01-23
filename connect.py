#!/usr/bin/env python3

####################################################################################
### This script is meant to be utilized by your shell, to replace SSH            ###
### as a method of connection. One way to accomplish this is to copy this script ### 
### to /usr/local/bin and modify your ~/.zshrc to include the following:         ###
###                                                                              ###
### connect() {                                                                  ###
###     if [[ $# -lt 2 ]]; then                                                  ###
###         echo "Usage: connect <AWS Profile> <Instance Name>"                  ###
###         return 1                                                             ###
###     fi                                                                       ###
###                                                                              ###
###     python3 /usr/local/bin/connect.py -p "$1" "$2"                           ###
### }                                                                            ###
####################################################################################

import argparse
import boto3
import subprocess
import os
import signal

def connect_to_instance(aws_profile, instance_name):
    session = boto3.Session(profile_name=aws_profile)
    ec2 = session.client('ec2')
    response = ec2.describe_instances(Filters=[{'Name': 'tag:Name', 'Values': [instance_name]}])

    if not response['Reservations']:
        print(f"Instance with name tag '{instance_name}' not found.")
        return

    instance_id = response['Reservations'][0]['Instances'][0]['InstanceId']
    ssm = session.client('ssm')
    response = ssm.start_session(Target=instance_id)
    print(f"Connecting to instance {instance_id}...")

    ssm_cli_command = f"aws ssm start-session --target {instance_id} --profile {aws_profile}"

    process = None

    def signal_handler(signum, frame):
        if process and process.poll() is None:
            os.kill(process.pid, signum)
        else:
            raise KeyboardInterrupt

    signal.signal(signal.SIGINT, signal_handler)

    try:
        process = subprocess.Popen(ssm_cli_command, shell=True)
        process.communicate()
    except KeyboardInterrupt:
        pass

    signal.signal(signal.SIGINT, signal.SIG_DFL) 

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Connect to an AWS EC2 instance by name tag")
    parser.add_argument("-p", "--profile", required=True, help="AWS CLI profile name")
    parser.add_argument("instance_name", help="Name tag of the EC2 instance")

    args = parser.parse_args()
    connect_to_instance(args.profile, args.instance_name)

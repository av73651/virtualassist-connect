#!/usr/bin/env python3
"""CDK App Entry Point.

This module is the entry point for the AWS CDK application.
"""

import os
import json
from aws_cdk import App, Environment
from stacks.auth_stack import AuthStack
from stacks.hello_world_stack import HelloWorldStack
from stacks.calculator_stack import CalculatorStack
from stacks.sre_platform_stack import SrePlatformStack

app = App()

# Load configuration map
config_path = os.path.join(os.path.dirname(__file__), "config.json")
with open(config_path, "r") as f:
    config_map = json.load(f)

# Resolve target context (default 'dev')
target_env = app.node.try_get_context("env") or "dev"
config = config_map.get(target_env)

if not config:
    raise ValueError(f"Environment '{target_env}' not found in config.json")

# Build target AWS Environment credentials
aws_env = Environment(account=config["account"], region=config["region"])

# Shared Authentication Stack (must be created first)
auth_stack = AuthStack(
    app,
    f"AuthStack-{target_env}",
    env=aws_env,
    config=config,
    description=f"Shared Authentication Stack ({target_env})"
)

# Hello World API Stack
HelloWorldStack(
    app,
    f"HelloWorldStack-{target_env}",
    env=aws_env,
    config=config,
    user_pool=auth_stack.user_pool,
    description=f"Hello World API Stack ({target_env})"
)

# Calculator API Stack
CalculatorStack(
    app,
    f"CalculatorStack-{target_env}",
    env=aws_env,
    config=config,
    user_pool=auth_stack.user_pool,
    description=f"Calculator API Stack ({target_env})"
)

# SRE Platform Stack (event-driven, no API Gateway)
# stack_name matches the previously deployed IncidentManagerStack to enable in-place update
SrePlatformStack(
    app,
    f"SrePlatformStack-{target_env}",
    env=aws_env,
    config=config,
    stack_name=f"IncidentManagerStack-{target_env}",
    description=f"SRE Platform Pipeline Stack ({target_env})",
)

app.synth()

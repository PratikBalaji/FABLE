#!/usr/bin/env python3
"""CDK app entry point for F.A.B.L.E. deployment."""
import aws_cdk as cdk
from cdk_stack import FableStack

app = cdk.App()
FableStack(app, "FableStack", env=cdk.Environment(
    account=app.node.try_get_context("account"),
    region=app.node.try_get_context("region") or "us-east-1",
))
app.synth()

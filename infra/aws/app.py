#!/usr/bin/env python3
"""CDK app entry point for F.A.B.L.E. deployment.

Two stacks (independent, select at deploy time):
  FableStack    — ECS Fargate + S3 + CloudWatch  (serverless, no cluster mgmt)
  FableEksStack — EKS + ECR + ALB Controller     (k8s-native, matches k8s/overlays/prod)

Deploy ECS:  cdk deploy FableStack
Deploy EKS:  cdk deploy FableEksStack
             aws eks update-kubeconfig --name fable-eks --region <region>
             kubectl apply -k ../../k8s/overlays/prod
"""
import aws_cdk as cdk
from cdk_stack import FableStack
from eks_stack import FableEksStack

app = cdk.App()

env = cdk.Environment(
    account=app.node.try_get_context("account"),
    region=app.node.try_get_context("region") or "us-east-1",
)

FableStack(app, "FableStack", env=env)
FableEksStack(app, "FableEksStack", env=env)

app.synth()

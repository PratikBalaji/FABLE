"""AWS CDK stack for F.A.B.L.E. — EKS (alternative to ECS Fargate in cdk_stack.py).

Deploy:
    cd infra/aws
    cdk deploy FableEksStack
    aws eks update-kubeconfig --name fable-eks --region <region>
    kubectl apply -k ../../k8s/overlays/prod

The k8s/overlays/prod kustomization expects:
  - ingressClassName: alb  (AWS Load Balancer Controller, installed by this stack)
  - ECR images: set IMAGE_TAG, AWS_ACCOUNT_ID, AWS_REGION env vars before kustomize
"""
import aws_cdk as cdk
from aws_cdk import (
    Stack,
    RemovalPolicy,
    aws_ec2 as ec2,
    aws_eks as eks,
    aws_iam as iam,
    aws_ecr as ecr,
    aws_logs as logs,
)
from aws_cdk import lambda_layer_kubectl_v29 as kubectl_v29
from constructs import Construct


class FableEksStack(Stack):
    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # ---------------------------------------------------------------------------
        # VPC (2 AZs, 1 NAT gateway — mirrors FableStack VPC pattern)
        # ---------------------------------------------------------------------------
        vpc = ec2.Vpc(
            self, "FableEksVpc",
            max_azs=2,
            nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
            ],
        )

        # ---------------------------------------------------------------------------
        # IAM role for cluster admin (used by CDK deployment role)
        # ---------------------------------------------------------------------------
        cluster_admin_role = iam.Role(
            self, "FableEksAdminRole",
            assumed_by=iam.AccountRootPrincipal(),
            description="EKS cluster admin — used by CI/CD and CDK",
        )

        # ---------------------------------------------------------------------------
        # EKS Cluster (Kubernetes 1.29, private + public endpoint)
        # ---------------------------------------------------------------------------
        cluster = eks.Cluster(
            self, "FableEks",
            cluster_name="fable-eks",
            version=eks.KubernetesVersion.V1_29,
            kubectl_layer=kubectl_v29.KubectlV29Layer(self, "KubectlLayer"),
            vpc=vpc,
            vpc_subnets=[ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)],
            masters_role=cluster_admin_role,
            endpoint_access=eks.EndpointAccess.PUBLIC_AND_PRIVATE,
            default_capacity=0,  # use managed node group below
        )

        # ---------------------------------------------------------------------------
        # Managed node group — 2× t3.medium (scales 1–5 via Cluster Autoscaler)
        # ---------------------------------------------------------------------------
        cluster.add_nodegroup_capacity(
            "FableNodeGroup",
            instance_types=[ec2.InstanceType("t3.medium")],
            min_size=1,
            desired_size=2,
            max_size=5,
            disk_size=50,
            ami_type=eks.NodegroupAmiType.AL2_X86_64,
            nodegroup_name="fable-nodes",
        )

        # ---------------------------------------------------------------------------
        # AWS Load Balancer Controller (Helm chart via CDK EKS addon)
        # Required for ingressClassName: alb in k8s/overlays/prod
        # ---------------------------------------------------------------------------
        # IRSA (IAM Roles for Service Accounts) for the LBC
        lbc_sa = cluster.add_service_account(
            "AwsLoadBalancerControllerSA",
            name="aws-load-balancer-controller",
            namespace="kube-system",
        )

        # IAM policy for AWS Load Balancer Controller
        # https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/main/docs/install/iam_policy.json
        lbc_policy_doc = iam.PolicyDocument(
            statements=[
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "ec2:DescribeAccountAttributes",
                        "ec2:DescribeAddresses",
                        "ec2:DescribeAvailabilityZones",
                        "ec2:DescribeInternetGateways",
                        "ec2:DescribeVpcs",
                        "ec2:DescribeVpcPeeringConnections",
                        "ec2:DescribeSubnets",
                        "ec2:DescribeSecurityGroups",
                        "ec2:DescribeInstances",
                        "ec2:DescribeNetworkInterfaces",
                        "ec2:DescribeTags",
                        "ec2:GetCoipPoolUsage",
                        "ec2:DescribeCoipPools",
                        "elasticloadbalancing:DescribeLoadBalancers",
                        "elasticloadbalancing:DescribeLoadBalancerAttributes",
                        "elasticloadbalancing:DescribeListeners",
                        "elasticloadbalancing:DescribeListenerCertificates",
                        "elasticloadbalancing:DescribeSSLPolicies",
                        "elasticloadbalancing:DescribeRules",
                        "elasticloadbalancing:DescribeTargetGroups",
                        "elasticloadbalancing:DescribeTargetGroupAttributes",
                        "elasticloadbalancing:DescribeTargetHealth",
                        "elasticloadbalancing:DescribeTags",
                    ],
                    resources=["*"],
                ),
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "cognito-idp:DescribeUserPoolClient",
                        "acm:ListCertificates",
                        "acm:DescribeCertificate",
                        "iam:ListServerCertificates",
                        "iam:GetServerCertificate",
                        "waf-regional:GetWebACL",
                        "waf-regional:GetWebACLForResource",
                        "waf-regional:AssociateWebACL",
                        "waf-regional:DisassociateWebACL",
                        "wafv2:GetWebACL",
                        "wafv2:GetWebACLForResource",
                        "wafv2:AssociateWebACL",
                        "wafv2:DisassociateWebACL",
                        "shield:GetSubscriptionState",
                        "shield:DescribeProtection",
                        "shield:CreateProtection",
                        "shield:DeleteProtection",
                    ],
                    resources=["*"],
                ),
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "ec2:AuthorizeSecurityGroupIngress",
                        "ec2:RevokeSecurityGroupIngress",
                        "ec2:CreateSecurityGroup",
                        "ec2:CreateTags",
                        "ec2:DeleteTags",
                        "ec2:DeleteSecurityGroup",
                        "ec2:ModifyNetworkInterfaceAttribute",
                        "elasticloadbalancing:AddListenerCertificates",
                        "elasticloadbalancing:RemoveListenerCertificates",
                        "elasticloadbalancing:ModifyRule",
                        "elasticloadbalancing:AddTags",
                        "elasticloadbalancing:RemoveTags",
                        "elasticloadbalancing:ModifyLoadBalancerAttributes",
                        "elasticloadbalancing:SetIpAddressType",
                        "elasticloadbalancing:SetSecurityGroups",
                        "elasticloadbalancing:SetSubnets",
                        "elasticloadbalancing:DeleteLoadBalancer",
                        "elasticloadbalancing:ModifyTargetGroup",
                        "elasticloadbalancing:ModifyTargetGroupAttributes",
                        "elasticloadbalancing:DeleteTargetGroup",
                    ],
                    resources=["*"],
                ),
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "elasticloadbalancing:RegisterTargets",
                        "elasticloadbalancing:DeregisterTargets",
                        "elasticloadbalancing:CreateListener",
                        "elasticloadbalancing:DeleteListener",
                        "elasticloadbalancing:CreateRule",
                        "elasticloadbalancing:DeleteRule",
                        "elasticloadbalancing:CreateLoadBalancer",
                        "elasticloadbalancing:CreateTargetGroup",
                    ],
                    resources=["*"],
                ),
            ]
        )

        lbc_policy = iam.Policy(self, "LbcPolicy", document=lbc_policy_doc)
        lbc_sa.role.attach_inline_policy(lbc_policy)

        # Install AWS Load Balancer Controller via Helm
        cluster.add_helm_chart(
            "AwsLoadBalancerController",
            chart="aws-load-balancer-controller",
            repository="https://aws.github.io/eks-charts",
            namespace="kube-system",
            values={
                "clusterName": cluster.cluster_name,
                "serviceAccount": {
                    "create": False,
                    "name": "aws-load-balancer-controller",
                },
                "region": self.region,
                "vpcId": vpc.vpc_id,
            },
        )

        # ---------------------------------------------------------------------------
        # ECR repositories for FABLE images
        # ---------------------------------------------------------------------------
        coordinator_repo = ecr.Repository(
            self, "CoordinatorRepo",
            repository_name="fable-coordinator",
            removal_policy=RemovalPolicy.RETAIN,
            lifecycle_rules=[ecr.LifecycleRule(max_image_count=10)],
        )

        agent_repo = ecr.Repository(
            self, "AgentGroupRepo",
            repository_name="fable-agent-group",
            removal_policy=RemovalPolicy.RETAIN,
            lifecycle_rules=[ecr.LifecycleRule(max_image_count=10)],
        )

        # Grant node group pull access
        coordinator_repo.grant_pull(cluster.role)
        agent_repo.grant_pull(cluster.role)

        # ---------------------------------------------------------------------------
        # CloudWatch log group for EKS application logs
        # ---------------------------------------------------------------------------
        logs.LogGroup(
            self, "FableEksLogs",
            log_group_name="/fable/eks",
            retention=logs.RetentionDays.TWO_WEEKS,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ---------------------------------------------------------------------------
        # Outputs
        # ---------------------------------------------------------------------------
        cdk.CfnOutput(self, "ClusterName", value=cluster.cluster_name)
        cdk.CfnOutput(self, "CoordinatorEcrUri", value=coordinator_repo.repository_uri)
        cdk.CfnOutput(self, "AgentGroupEcrUri", value=agent_repo.repository_uri)
        cdk.CfnOutput(self, "KubeconfigCommand",
            value=f"aws eks update-kubeconfig --name {cluster.cluster_name} --region {self.region}")

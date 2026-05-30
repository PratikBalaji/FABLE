"""AWS CDK stack for F.A.B.L.E. deployment — ECS Fargate + S3 + CloudWatch."""
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_s3 as s3,
    aws_iam as iam,
    aws_logs as logs,
    aws_elasticloadbalancingv2 as elbv2,
)
from constructs import Construct


class FableStack(Stack):
    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # VPC
        vpc = ec2.Vpc(self, "FableVpc", max_azs=2, nat_gateways=1)

        # ECS Cluster
        cluster = ecs.Cluster(self, "FableCluster", vpc=vpc)

        # S3 bucket for RAG document storage
        docs_bucket = s3.Bucket(
            self, "FableDocsBucket",
            bucket_name=f"fable-rag-docs-{self.account}",
            removal_policy=RemovalPolicy.RETAIN,
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
        )

        # CloudWatch log group
        log_group = logs.LogGroup(
            self, "FableLogs",
            log_group_name="/fable/api",
            retention=logs.RetentionDays.TWO_WEEKS,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Backend task definition
        backend_task = ecs.FargateTaskDefinition(
            self, "FableBackendTask",
            memory_limit_mib=1024,
            cpu=512,
        )

        backend_container = backend_task.add_container(
            "backend",
            image=ecs.ContainerImage.from_asset("../../", file="infra/docker/Dockerfile.backend"),
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="fable-backend",
                log_group=log_group,
            ),
            environment={
                "LOG_LEVEL": "INFO",
                "S3_BUCKET": docs_bucket.bucket_name,
                "AWS_REGION": self.region,
            },
            port_mappings=[ecs.PortMapping(container_port=8000)],
        )

        # Grant S3 access to backend
        docs_bucket.grant_read_write(backend_task.task_role)

        # Backend Fargate service with ALB
        backend_service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self, "FableBackendService",
            cluster=cluster,
            task_definition=backend_task,
            desired_count=1,
            public_load_balancer=True,
            listener_port=80,
            health_check_grace_period=Duration.seconds(60),
        )

        backend_service.target_group.configure_health_check(
            path="/health",
            healthy_http_codes="200",
            interval=Duration.seconds(30),
        )

        # Frontend task definition
        frontend_task = ecs.FargateTaskDefinition(
            self, "FableFrontendTask",
            memory_limit_mib=512,
            cpu=256,
        )

        frontend_task.add_container(
            "frontend",
            image=ecs.ContainerImage.from_asset("../../", file="infra/docker/Dockerfile.frontend"),
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="fable-frontend",
                log_group=log_group,
            ),
            environment={
                "NEXT_PUBLIC_API_URL": f"http://{backend_service.load_balancer.load_balancer_dns_name}",
            },
            port_mappings=[ecs.PortMapping(container_port=3000)],
        )

        # Frontend Fargate service with ALB
        frontend_service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self, "FableFrontendService",
            cluster=cluster,
            task_definition=frontend_task,
            desired_count=1,
            public_load_balancer=True,
            listener_port=80,
        )

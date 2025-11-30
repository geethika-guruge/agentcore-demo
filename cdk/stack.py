from aws_cdk import (
    Stack,
    aws_s3 as s3,
    aws_lambda as _lambda,
    aws_sns as sns,
    aws_sns_subscriptions as sns_subs,
    aws_iam as iam,
    aws_dynamodb as dynamodb,
    aws_ssm as ssm,
    aws_ec2 as ec2,
    aws_rds as rds,
    RemovalPolicy,
    Duration,
    CfnOutput,
)
from constructs import Construct
import yaml
import pathlib


class OrderAssistantStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Read agent ARN from bedrock_agentcore.yaml
        agentcore_config_path = (
            pathlib.Path(__file__).parent.parent
            / "agentcore"
            / "runtime"
            / ".bedrock_agentcore.yaml"
        )
        with open(agentcore_config_path, "r") as f:
            agentcore_config = yaml.safe_load(f)

        agent_arn = agentcore_config["agents"]["order_assistant"]["bedrock_agentcore"][
            "agent_arn"
        ]

        # Create IAM role for AgentCore Runtime
        agentcore_execution_role = iam.Role(
            self,
            "AgentCoreExecutionRole",
            assumed_by=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
            description="Execution role for AgentCore order assistant runtime",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AdministratorAccess")
            ],
        )

        # Create SSM parameter for agent ARN
        agent_arn_param = ssm.StringParameter(
            self,
            "AgentRuntimeArn",
            parameter_name="/order-assistant/agent-runtime-arn",
            string_value=agent_arn,
            description="AgentCore Runtime ARN for order assistant",
        )

        bucket = s3.Bucket(self, "OrderAssistantBucket")

        # Create VPC for RDS
        vpc = ec2.Vpc(
            self,
            "OrderAssistantVpc",
            max_azs=2,
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Isolated",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                ),
            ],
        )

        # Security group for RDS
        rds_security_group = ec2.SecurityGroup(
            self,
            "RDSSecurityGroup",
            vpc=vpc,
            description="Security group for RDS PostgreSQL instance",
            allow_all_outbound=True,
        )

        # Allow all traffic from VPC CIDR
        rds_security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.all_traffic(),
            description="Allow all traffic from VPC",
        )

        # Allow all traffic from the same security group
        rds_security_group.add_ingress_rule(
            peer=rds_security_group,
            connection=ec2.Port.all_traffic(),
            description="Allow all traffic from same security group",
        )

        # VPC Endpoint for Secrets Manager
        vpc.add_interface_endpoint(
            "SecretsManagerEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.SECRETS_MANAGER,
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            security_groups=[rds_security_group],
        )

        # VPC Endpoint for Bedrock AgentCore Gateway
        vpc.add_interface_endpoint(
            "BedrockAgentCoreGatewayEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.BEDROCK_AGENTCORE_GATEWAY,
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            security_groups=[rds_security_group],
        )

        # Aurora PostgreSQL Serverless v2 Cluster
        db_cluster = rds.DatabaseCluster(
            self,
            "OrderAssistantDB",
            engine=rds.DatabaseClusterEngine.aurora_postgres(
                version=rds.AuroraPostgresEngineVersion.VER_16_6
            ),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            ),
            security_groups=[rds_security_group],
            default_database_name="orderassistant",
            credentials=rds.Credentials.from_generated_secret("postgres"),
            storage_encrypted=True,
            backup=rds.BackupProps(retention=Duration.days(7)),
            deletion_protection=False,
            removal_policy=RemovalPolicy.SNAPSHOT,
            serverless_v2_min_capacity=0.5,
            serverless_v2_max_capacity=1,
            writer=rds.ClusterInstance.serverless_v2("Writer"),
        )

        # Create Orders DynamoDB table
        orders_table = dynamodb.Table(
            self,
            "OrdersTable",
            partition_key=dynamodb.Attribute(
                name="order_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
        )

        # Create Delivery Slots DynamoDB table
        delivery_slots_table = dynamodb.Table(
            self,
            "DeliverySlotsTable",
            partition_key=dynamodb.Attribute(
                name="slot_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="slot_date", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,  # For development - change to RETAIN for production
        )

        # Add GSI for querying available slots by date range
        # Partition key: slot_status (to filter by status)
        # Sort key: slot_date (to query date ranges with BETWEEN)
        delivery_slots_table.add_global_secondary_index(
            index_name="DateStatusIndex",
            partition_key=dynamodb.Attribute(
                name="slot_status", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="slot_date", type=dynamodb.AttributeType.STRING
            ),
        )

        # Create Customers DynamoDB table
        customers_table = dynamodb.Table(
            self,
            "CustomersTable",
            partition_key=dynamodb.Attribute(
                name="customer_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,  # For development - change to RETAIN for production
        )

        # Create Pending Orders table for storing catalog options temporarily
        pending_orders_table = dynamodb.Table(
            self,
            "PendingOrdersTable",
            partition_key=dynamodb.Attribute(
                name="customer_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
            time_to_live_attribute="ttl",  # Enable TTL for automatic cleanup
        )

        # Read Arize credentials from .otel_config.yaml for lambda tracing
        otel_config_path = pathlib.Path(__file__).parent.parent / ".otel_config.yaml"
        arize_space_id = None
        arize_api_key = None
        arize_project_name = "order-assistant-lambda"

        try:
            with open(otel_config_path, "r") as f:
                otel_config = yaml.safe_load(f)
                arize_space_id = otel_config.get("space_id")
                arize_api_key = otel_config.get("api_key")
                arize_project_name = otel_config.get("project_name", arize_project_name)
        except Exception as e:
            print(f"Warning: Could not load .otel_config.yaml for lambda: {e}")

        lambda_env = {
            "PHONE_NUMBER_ID": "phone-number-id-f82a097f349f44798c5926fb29db1ac1",  # Your WhatsApp phone number ID
            "MEDIA_BUCKET_NAME": bucket.bucket_name,
            "AGENT_ARN_PARAM": agent_arn_param.parameter_name,
            "PENDING_ORDERS_TABLE": pending_orders_table.table_name,
        }

        # Add Arize credentials if available
        if arize_space_id and not arize_space_id.startswith("YOUR_"):
            lambda_env["ARIZE_SPACE_ID"] = arize_space_id
            lambda_env["ARIZE_API_KEY"] = arize_api_key
            lambda_env["ARIZE_PROJECT_NAME"] = arize_project_name

        process_order_lambda = _lambda.Function(
            self,
            "ProcessOrder",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="lambda.handler",
            code=_lambda.Code.from_asset("src/lambda/process_order"),
            environment=lambda_env,
            timeout=Duration.minutes(15),
        )

        process_order_lambda.role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AdministratorAccess")
        )

        # Grant Lambda permission to read SSM parameter
        agent_arn_param.grant_read(process_order_lambda)

        # Grant Lambda permission to read/write S3 bucket
        bucket.grant_read_write(process_order_lambda)

        # Create SNS topic for WhatsApp messages
        whatsapp_topic = sns.Topic(
            self,
            "WhatsAppMessageTopic",
            display_name="WhatsApp Message Topic",
            topic_name="OrderAssistant-WhatsAppMessages",
        )

        # Subscribe Lambda to SNS topic
        whatsapp_topic.add_subscription(
            sns_subs.LambdaSubscription(process_order_lambda)
        )

        # DynamoDB MCP Server Lambda
        dynamodb_mcp_lambda = _lambda.DockerImageFunction(
            self,
            "DynamoDBMCPServer",
            code=_lambda.DockerImageCode.from_image_asset(
                directory="src/lambda/dynamodb_mcp", file="Dockerfile"
            ),
            timeout=Duration.minutes(15),
            memory_size=512,
            environment={
                "ORDERS_TABLE_NAME": orders_table.table_name,
                "DELIVERY_SLOTS_TABLE_NAME": delivery_slots_table.table_name,
                "CUSTOMERS_TABLE_NAME": customers_table.table_name,
            },
        )

        # Grant DynamoDB Lambda permissions to access tables
        orders_table.grant_read_write_data(dynamodb_mcp_lambda)
        delivery_slots_table.grant_read_write_data(dynamodb_mcp_lambda)
        customers_table.grant_read_write_data(dynamodb_mcp_lambda)

        dynamodb_mcp_lambda.role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AdministratorAccess")
        )

        # PostgreSQL MCP Server Lambda
        postgres_mcp_lambda = _lambda.DockerImageFunction(
            self,
            "PostgreSQLMCPServer",
            code=_lambda.DockerImageCode.from_image_asset(
                directory="src/lambda/postgres_mcp", file="Dockerfile"
            ),
            timeout=Duration.minutes(15),
            memory_size=512,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            ),
            security_groups=[rds_security_group],
            environment={
                "POSTGRES_HOST": db_cluster.cluster_endpoint.hostname,
                "POSTGRES_PORT": "5432",
                "POSTGRES_DB": "orderassistant",
                "POSTGRES_SECRET_ARN": db_cluster.secret.secret_arn,
            },
        )

        postgres_mcp_lambda.role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AdministratorAccess")
        )

        # Grant Lambda permission to read database credentials from Secrets Manager
        db_cluster.secret.grant_read(postgres_mcp_lambda)

        # Allow Lambda to connect to Aurora
        db_cluster.connections.allow_default_port_from(postgres_mcp_lambda)

        # Populate Database Lambda (for initial data loading)
        populate_catalog_lambda = _lambda.DockerImageFunction(
            self,
            "PopulateCatalogFunction",
            code=_lambda.DockerImageCode.from_image_asset(
                directory="src/lambda/populate_catalog", file="Dockerfile"
            ),
            timeout=Duration.minutes(15),
            memory_size=512,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            ),
            security_groups=[rds_security_group],
            environment={
                "POSTGRES_HOST": db_cluster.cluster_endpoint.hostname,
                "POSTGRES_PORT": "5432",
                "POSTGRES_DB": "orderassistant",
                "POSTGRES_SECRET_ARN": db_cluster.secret.secret_arn,
            },
        )

        populate_catalog_lambda.role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AdministratorAccess")
        )

        # Grant Lambda permission to read database credentials from Secrets Manager
        db_cluster.secret.grant_read(populate_catalog_lambda)

        # Allow Lambda to connect to Aurora
        db_cluster.connections.allow_default_port_from(populate_catalog_lambda)

        # Output the Lambda function ARN and name
        CfnOutput(
            self,
            "DynamoDBMCPLambdaArn",
            value=dynamodb_mcp_lambda.function_arn,
            description="DynamoDB MCP Server Lambda Function ARN",
        )
        CfnOutput(
            self,
            "DynamoDBMCPLambdaName",
            value=dynamodb_mcp_lambda.function_name,
            description="DynamoDB MCP Server Lambda Function Name",
        )
        CfnOutput(
            self,
            "PostgreSQLMCPLambdaArn",
            value=postgres_mcp_lambda.function_arn,
            description="PostgreSQL MCP Server Lambda Function ARN",
        )
        CfnOutput(
            self,
            "PostgreSQLMCPLambdaName",
            value=postgres_mcp_lambda.function_name,
            description="PostgreSQL MCP Server Lambda Function Name",
        )
        CfnOutput(
            self,
            "PopulateCatalogLambdaArn",
            value=populate_catalog_lambda.function_arn,
            description="Populate Catalog Lambda Function ARN",
        )
        CfnOutput(
            self,
            "PopulateCatalogLambdaName",
            value=populate_catalog_lambda.function_name,
            description="Populate Catalog Lambda Function Name",
        )
        CfnOutput(
            self,
            "OrdersTableName",
            value=orders_table.table_name,
            description="Orders DynamoDB Table Name",
        )
        CfnOutput(
            self,
            "DeliverySlotsTableName",
            value=delivery_slots_table.table_name,
            description="Delivery Slots DynamoDB Table Name",
        )
        CfnOutput(
            self,
            "CustomersTableName",
            value=customers_table.table_name,
            description="Customers DynamoDB Table Name",
        )
        CfnOutput(
            self,
            "OrderAssistantBucketName",
            value=bucket.bucket_name,
            description="S3 Bucket for Order Documents",
        )
        CfnOutput(
            self,
            "AgentCoreExecutionRoleArn",
            value=agentcore_execution_role.role_arn,
            description="AgentCore Runtime Execution Role ARN",
        )
        CfnOutput(
            self,
            "WhatsAppTopicArn",
            value=whatsapp_topic.topic_arn,
            description="SNS Topic ARN for WhatsApp Messages",
        )
        CfnOutput(
            self,
            "DatabaseEndpoint",
            value=db_cluster.cluster_endpoint.hostname,
            description="Aurora PostgreSQL Cluster Endpoint",
        )
        CfnOutput(
            self,
            "DatabasePort",
            value=str(db_cluster.cluster_endpoint.port),
            description="Aurora PostgreSQL Port",
        )
        CfnOutput(
            self,
            "DatabaseSecretArn",
            value=db_cluster.secret.secret_arn,
            description="Aurora PostgreSQL Credentials Secret ARN",
        )
        CfnOutput(
            self,
            "DatabaseName",
            value="orderassistant",
            description="RDS PostgreSQL Database Name",
        )

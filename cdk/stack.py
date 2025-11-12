from aws_cdk import (
    Stack,
    aws_s3 as s3,
    aws_lambda as _lambda,
    aws_s3_notifications as s3n,
    aws_iam as iam,
    aws_dynamodb as dynamodb,
)
from constructs import Construct

class InfraStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        bucket = s3.Bucket(self, "OrderAssistantBucket")

        catalog_table = dynamodb.Table(
            self, "ProductCatalog",
            partition_key=dynamodb.Attribute(name="product_id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
        )

        process_order_lambda = _lambda.Function(
            self, "TextractProcessor",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="invoke_agent.handler",
            code=_lambda.Code.from_asset("lambda"),
        )

        process_order_lambda.role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AdministratorAccess")
        )

        bucket.grant_read(process_order_lambda)
        process_order_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["textract:DetectDocumentText"],
                resources=["*"]
            )
        )

        bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(process_order_lambda),
            s3.NotificationKeyFilter(suffix=".png")
        )
        bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(process_order_lambda),
            s3.NotificationKeyFilter(suffix=".pdf")
        )

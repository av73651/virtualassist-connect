"""Authentication CDK Stack.

This module defines the shared Cognito User Pool used by all API stacks.
"""

from aws_cdk import (
    Stack,
    aws_cognito as cognito,
    CfnOutput,
    RemovalPolicy
)
from constructs import Construct


class AuthStack(Stack):
    """CDK stack for shared authentication resources.

    Creates Cognito User Pool and App Client shared across all API stacks.
    """

    def __init__(self, scope: Construct, construct_id: str, config: dict, **kwargs) -> None:
        """Initialize Auth stack.

        Args:
            scope: CDK app or stage
            construct_id: Unique identifier for this stack
            config: Configuration dictionary loaded from config.json
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

        stage = config["api_gateway"]["stage_name"]

        # Cognito User Pool
        self.user_pool = cognito.UserPool(
            self, "UserPool",
            user_pool_name=f"virtualassist-users-{stage}",
            self_sign_up_enabled=True,
            sign_in_aliases=cognito.SignInAliases(email=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            password_policy=cognito.PasswordPolicy(
                min_length=12,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=True
            ),
            mfa=cognito.Mfa.OPTIONAL if stage == "dev" else cognito.Mfa.REQUIRED,
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            removal_policy=RemovalPolicy.DESTROY if stage == "dev" else RemovalPolicy.RETAIN
        )

        # App Client (no secret for SPA/public clients)
        self.user_pool_client = self.user_pool.add_client(
            "AppClient",
            user_pool_client_name=f"virtualassist-app-{stage}",
            auth_flows=cognito.AuthFlow(
                user_password=True,
                user_srp=True
            ),
            generate_secret=False
        )

        # Outputs
        CfnOutput(
            self, "UserPoolId",
            value=self.user_pool.user_pool_id,
            description="Cognito User Pool ID",
            export_name="VirtualAssistUserPoolId"
        )

        CfnOutput(
            self, "UserPoolArn",
            value=self.user_pool.user_pool_arn,
            description="Cognito User Pool ARN",
            export_name="VirtualAssistUserPoolArn"
        )

        CfnOutput(
            self, "UserPoolClientId",
            value=self.user_pool_client.user_pool_client_id,
            description="Cognito App Client ID",
            export_name="VirtualAssistUserPoolClientId"
        )

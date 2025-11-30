#!/usr/bin/env python3
"""
Script to deploy AgentCore runtime with region-specific configuration
This script handles region-specific Dockerfiles and bedrock_agentcore.yaml files
"""

import boto3
import shutil
import subprocess
import sys
import yaml
from pathlib import Path

def main():
    print("🚀 AgentCore Deployment Script")
    print("=" * 40)
    print()

    # Get region from AWS session (uses AWS profile configuration)
    try:
        session = boto3.Session()
        region = session.region_name

        if not region:
            print("❌ Error: Could not determine AWS region")
            print("   Make sure AWS credentials are configured")
            print("   Run: aws configure")
            sys.exit(1)

        print(f"Using AWS region: {region}")
        print()
    except Exception as e:
        print(f"❌ Error getting AWS region: {e}")
        sys.exit(1)

    # Define file names
    dockerfile_region = f"Dockerfile.{region}"
    bedrock_config_region = f".bedrock_agentcore.{region}.yaml"
    dockerfile = "Dockerfile"
    bedrock_config = ".bedrock_agentcore.yaml"

    # Get script directory (runtime folder)
    script_dir = Path(__file__).parent

    # Dockerfile is in .bedrock_agentcore/order_assistant/
    dockerfile_dir = script_dir / ".bedrock_agentcore" / "order_assistant"
    dockerfile_region_path = dockerfile_dir / dockerfile_region
    dockerfile_path = dockerfile_dir / dockerfile

    # bedrock_agentcore.yaml is in runtime folder
    bedrock_config_region_path = script_dir / bedrock_config_region
    bedrock_config_path = script_dir / bedrock_config

    # Check if region-specific files exist
    if not dockerfile_region_path.exists():
        print(f"❌ Error: Region-specific Dockerfile not found: {dockerfile_region}")
        print(f"   Please create {dockerfile_region} in .bedrock_agentcore/order_assistant/")
        print(f"   Full path: {dockerfile_region_path}")
        sys.exit(1)

    if not bedrock_config_region_path.exists():
        print(f"❌ Error: Region-specific bedrock_agentcore config not found: {bedrock_config_region}")
        print(f"   Please create {bedrock_config_region} for your region")
        sys.exit(1)

    print("✓ Found region-specific files:")
    print(f"  - {dockerfile_region}")
    print(f"  - {bedrock_config_region}")
    print()

    # Copy region-specific files
    print("📋 Copying region-specific files...")
    try:
        shutil.copy(dockerfile_region_path, dockerfile_path)
        print(f"  ✓ Copied {dockerfile_region} → {dockerfile}")

        shutil.copy(bedrock_config_region_path, bedrock_config_path)
        print(f"  ✓ Copied {bedrock_config_region} → {bedrock_config}")
        print()
    except Exception as e:
        print(f"❌ Error copying files: {e}")
        sys.exit(1)

    # Run agentcore deploy
    print("🚢 Running agentcore deploy...")
    print("=" * 40)
    print()

    try:
        # Run agentcore deploy from the runtime directory
        result = subprocess.run(
            ["agentcore", "launch"],
            cwd=script_dir,
            check=True,
            capture_output=False  # Show output in real-time
        )

        print()
        print("=" * 40)
        print("✅ AgentCore deployment complete!")
        print()
        print(f"Region: {region}")
        print(f"Config: {bedrock_config_region}")
        print(f"Dockerfile: {dockerfile_region}")
        print()

    except subprocess.CalledProcessError as e:
        print()
        print(f"❌ Error: agentcore deploy failed with exit code {e.returncode}")
        sys.exit(1)
    except FileNotFoundError:
        print()
        print("❌ Error: 'agentcore' command not found")
        print("   Make sure bedrock_agentcore is installed:")
        print("   pip install bedrock_agentcore_starter_toolkit")
        sys.exit(1)
    except Exception as e:
        print()
        print(f"❌ Error running agentcore deploy: {e}")
        sys.exit(1)
    finally:
        # Extract agent_arn from bedrock_agentcore.yaml and store in SSM
        print()
        print("📝 Storing agent ARN in SSM Parameter Store...")

        try:
            if bedrock_config_path.exists():
                with open(bedrock_config_path, 'r') as f:
                    agentcore_config = yaml.safe_load(f)

                # Extract agent ARN from the YAML structure
                agent_arn = agentcore_config.get('agents', {}).get('order_assistant', {}).get('bedrock_agentcore', {}).get('agent_arn')

                if agent_arn:
                    print(f"  Found agent ARN: {agent_arn}")

                    # Store in SSM Parameter Store
                    ssm_client = session.client('ssm')
                    ssm_client.put_parameter(
                        Name='/order-assistant/agent-runtime-arn',
                        Value=agent_arn,
                        Description='AgentCore Runtime ARN for order assistant',
                        Type='String',
                        Overwrite=True
                    )
                    print(f"  ✓ Stored agent ARN in SSM: /order-assistant/agent-runtime-arn")
                else:
                    print("  ⚠️  Warning: Could not find agent_arn in bedrock_agentcore.yaml")
        except Exception as e:
            print(f"  ⚠️  Warning: Could not store agent ARN in SSM: {e}")

        # Cleanup temporary files
        print()
        print("🧹 Cleaning up temporary files...")

        try:
            if dockerfile_path.exists():
                dockerfile_path.unlink()
                print(f"  ✓ Deleted {dockerfile}")
        except Exception as e:
            print(f"  ⚠️  Could not delete {dockerfile}: {e}")

        try:
            if bedrock_config_path.exists():
                bedrock_config_path.unlink()
                print(f"  ✓ Deleted {bedrock_config}")
        except Exception as e:
            print(f"  ⚠️  Could not delete {bedrock_config}: {e}")

        print("✓ Cleanup complete")


if __name__ == "__main__":
    main()

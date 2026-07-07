import os
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# .env 로드 (mcp-aws-monitor 폴더 기준)
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

mcp = FastMCP(
    "aws-monitor",
    instructions="AWS Infrastructure Monitoring for Logispot",
)

# 각 서비스 도구 등록
from src.cloudwatch import register_tools as register_cloudwatch
from src.sqs import register_tools as register_sqs
from src.rds import register_tools as register_rds
from src.s3 import register_tools as register_s3
from src.ec2 import register_tools as register_ec2

register_cloudwatch(mcp)
register_sqs(mcp)
register_rds(mcp)
register_s3(mcp)
register_ec2(mcp)


def main():
    mcp.run()


if __name__ == "__main__":
    main()

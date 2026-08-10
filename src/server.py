import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# .env 로드 (mcp-aws-monitor 폴더 기준)
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

MODE = os.environ.get("MCP_MODE", "stdio")  # stdio 또는 http
if "--http" in sys.argv:
    MODE = "http"

# HTTP 모드일 때만 OAuth 설정
if MODE == "http":
    from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
    from src.google_oauth import GoogleOAuthProvider

    SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://localhost:8000")
    oauth_provider = GoogleOAuthProvider(server_url=SERVER_URL)

    mcp = FastMCP(
        "aws-monitor",
        instructions="AWS Infrastructure Monitoring for Logispot",
        auth=AuthSettings(
            issuer_url=SERVER_URL,
            resource_server_url=SERVER_URL,
            required_scopes=[],
            client_registration_options=ClientRegistrationOptions(
                enabled=True,
                valid_scopes=[],
                default_scopes=[],
            ),
            revocation_options=RevocationOptions(enabled=True),
        ),
        auth_server_provider=oauth_provider,
    )
else:
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
from src.sns import register_tools as register_sns
from src.lambda_tools import register_tools as register_lambda

register_cloudwatch(mcp)
register_sqs(mcp)
register_rds(mcp)
register_s3(mcp)
register_ec2(mcp)
register_sns(mcp)
register_lambda(mcp)


def main():
    if MODE == "http":
        from starlette.requests import Request
        from starlette.responses import RedirectResponse
        from starlette.routing import Route

        async def google_callback(request: Request):
            code = request.query_params.get("code")
            state = request.query_params.get("state")
            if not code or not state:
                return RedirectResponse("/error?msg=missing_params")
            redirect_url = await oauth_provider.handle_google_callback(code, state)
            return RedirectResponse(redirect_url)

        app = mcp.streamable_http_app()
        app.routes.insert(0, Route("/google/callback", google_callback))

        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=8000)
    else:
        mcp.run()


if __name__ == "__main__":
    main()

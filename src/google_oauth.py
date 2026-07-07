import os
import secrets
import time
import hashlib
import base64
from urllib.parse import urlencode

import httpx
from pydantic import AnyUrl

from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from mcp.server.auth.provider import (
    OAuthAuthorizationServerProvider,
    AuthorizationParams,
    AuthorizationCode,
    RefreshToken,
    AccessToken,
    construct_redirect_uri,
)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

# 토큰 유효기간
ACCESS_TOKEN_TTL = 3600  # 1시간
REFRESH_TOKEN_TTL = 86400 * 30  # 30일
AUTH_CODE_TTL = 300  # 5분


class GoogleOAuthProvider(OAuthAuthorizationServerProvider):
    """Google OAuth를 통한 MCP 인증 Provider."""

    def __init__(self, server_url: str):
        self.server_url = server_url
        self.google_client_id = os.environ["GOOGLE_CLIENT_ID"]
        self.google_client_secret = os.environ["GOOGLE_CLIENT_SECRET"]

        # In-memory 저장소 (프로덕션에서는 Redis/DB 사용 권장)
        self._clients: dict[str, OAuthClientInformationFull] = {}
        self._auth_codes: dict[str, AuthorizationCode] = {}
        self._access_tokens: dict[str, AccessToken] = {}
        self._refresh_tokens: dict[str, RefreshToken] = {}
        # Google OAuth state -> MCP authorization params 매핑
        self._pending_auth: dict[str, dict] = {}

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self._clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        self._clients[client_info.client_id] = client_info

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        # Google OAuth로 리다이렉트할 state 생성
        google_state = secrets.token_urlsafe(32)

        # MCP 인증 정보를 저장 (Google 콜백에서 사용)
        self._pending_auth[google_state] = {
            "client_id": client.client_id,
            "redirect_uri": str(params.redirect_uri),
            "code_challenge": params.code_challenge,
            "scopes": params.scopes or [],
            "state": params.state,
            "redirect_uri_provided_explicitly": params.redirect_uri_provided_explicitly,
        }

        # Google 로그인 페이지로 리다이렉트
        google_params = {
            "client_id": self.google_client_id,
            "redirect_uri": f"{self.server_url}/google/callback",
            "response_type": "code",
            "scope": "openid email profile",
            "state": google_state,
            "access_type": "offline",
            "prompt": "consent",
        }
        return f"{GOOGLE_AUTH_URL}?{urlencode(google_params)}"

    async def handle_google_callback(self, code: str, state: str) -> str:
        """Google OAuth 콜백 처리 -> MCP 클라이언트로 리다이렉트."""
        pending = self._pending_auth.pop(state, None)
        if not pending:
            raise ValueError("Invalid state")

        # Google 토큰 교환
        async with httpx.AsyncClient() as http:
            token_resp = await http.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": self.google_client_id,
                    "client_secret": self.google_client_secret,
                    "redirect_uri": f"{self.server_url}/google/callback",
                    "grant_type": "authorization_code",
                },
            )
            token_resp.raise_for_status()
            google_tokens = token_resp.json()

            # 사용자 정보 조회
            userinfo_resp = await http.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {google_tokens['access_token']}"},
            )
            userinfo_resp.raise_for_status()
            userinfo = userinfo_resp.json()

        # MCP authorization code 생성
        mcp_code = secrets.token_urlsafe(48)
        self._auth_codes[mcp_code] = AuthorizationCode(
            code=mcp_code,
            scopes=pending["scopes"],
            expires_at=time.time() + AUTH_CODE_TTL,
            client_id=pending["client_id"],
            code_challenge=pending["code_challenge"],
            redirect_uri=AnyUrl(pending["redirect_uri"]),
            redirect_uri_provided_explicitly=pending["redirect_uri_provided_explicitly"],
            subject=userinfo.get("email", ""),
        )

        # MCP 클라이언트의 redirect_uri로 리다이렉트
        return construct_redirect_uri(
            pending["redirect_uri"],
            code=mcp_code,
            state=pending.get("state"),
        )

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        code = self._auth_codes.get(authorization_code)
        if code and code.client_id == client.client_id and code.expires_at > time.time():
            return code
        return None

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        # authorization code 삭제 (1회용)
        self._auth_codes.pop(authorization_code.code, None)

        # access token 발급
        access_token = secrets.token_urlsafe(48)
        self._access_tokens[access_token] = AccessToken(
            token=access_token,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            expires_at=int(time.time()) + ACCESS_TOKEN_TTL,
            subject=authorization_code.subject,
        )

        # refresh token 발급
        refresh_token = secrets.token_urlsafe(48)
        self._refresh_tokens[refresh_token] = RefreshToken(
            token=refresh_token,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            expires_at=int(time.time()) + REFRESH_TOKEN_TTL,
            subject=authorization_code.subject,
        )

        return OAuthToken(
            access_token=access_token,
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_TTL,
            refresh_token=refresh_token,
            scope=" ".join(authorization_code.scopes) if authorization_code.scopes else None,
        )

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        token = self._refresh_tokens.get(refresh_token)
        if token and token.client_id == client.client_id:
            if token.expires_at is None or token.expires_at > time.time():
                return token
        return None

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        # 기존 refresh token 삭제
        self._refresh_tokens.pop(refresh_token.token, None)

        # 새 access token 발급
        new_access = secrets.token_urlsafe(48)
        self._access_tokens[new_access] = AccessToken(
            token=new_access,
            client_id=client.client_id,
            scopes=scopes or refresh_token.scopes,
            expires_at=int(time.time()) + ACCESS_TOKEN_TTL,
            subject=refresh_token.subject,
        )

        # 새 refresh token 발급 (rotation)
        new_refresh = secrets.token_urlsafe(48)
        self._refresh_tokens[new_refresh] = RefreshToken(
            token=new_refresh,
            client_id=client.client_id,
            scopes=scopes or refresh_token.scopes,
            expires_at=int(time.time()) + REFRESH_TOKEN_TTL,
            subject=refresh_token.subject,
        )

        return OAuthToken(
            access_token=new_access,
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_TTL,
            refresh_token=new_refresh,
            scope=" ".join(scopes) if scopes else None,
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        access = self._access_tokens.get(token)
        if access and (access.expires_at is None or access.expires_at > time.time()):
            return access
        # 만료된 토큰 정리
        if access:
            del self._access_tokens[token]
        return None

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        if isinstance(token, AccessToken):
            self._access_tokens.pop(token.token, None)
        elif isinstance(token, RefreshToken):
            self._refresh_tokens.pop(token.token, None)

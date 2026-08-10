import io
import json
import zipfile
from urllib.request import urlopen

from mcp.server.fastmcp import FastMCP
from src.aws_client import get_client


def register_tools(mcp: FastMCP):

    @mcp.tool()
    def lambda_get_code(function_name: str) -> str:
        """Lambda 함수 소스 코드 조회.
        function_name: 함수 이름 또는 ARN
        """
        client = get_client("lambda")
        resp = client.get_function(FunctionName=function_name)
        code_url = resp.get("Code", {}).get("Location")
        if not code_url:
            return "코드 URL을 가져올 수 없습니다."

        code_data = urlopen(code_url).read()
        zf = zipfile.ZipFile(io.BytesIO(code_data))

        results = []
        for name in zf.namelist():
            # 소스 파일만 표시 (바이너리/의존성 제외)
            if name.startswith("__pycache__/") or name.startswith("node_modules/"):
                continue
            if any(name.endswith(ext) for ext in (".py", ".js", ".ts", ".mjs", ".json", ".yaml", ".yml", ".txt", ".cfg")):
                try:
                    content = zf.read(name).decode("utf-8")
                    results.append(f"=== {name} ===\n{content}")
                except Exception:
                    results.append(f"=== {name} === (읽기 실패)")
        if not results:
            results.append(f"파일 목록: {', '.join(zf.namelist())}")

        return "\n\n".join(results)

    @mcp.tool()
    def lambda_list_functions() -> str:
        """Lambda 함수 목록 조회."""
        client = get_client("lambda")
        functions = []
        paginator = client.get_paginator("list_functions")
        for page in paginator.paginate():
            for fn in page["Functions"]:
                runtime = fn.get("Runtime", "N/A")
                desc = fn.get("Description", "")
                last_modified = fn.get("LastModified", "")
                line = f"{fn['FunctionName']} ({runtime})"
                if desc:
                    line += f"\n  Description: {desc}"
                line += f"\n  LastModified: {last_modified}"
                functions.append(line)
        return "\n\n".join(functions) if functions else "Lambda 함수 없음"

    @mcp.tool()
    def lambda_get_function(function_name: str) -> str:
        """Lambda 함수 상세 정보 조회.
        function_name: 함수 이름 또는 ARN
        """
        client = get_client("lambda")
        resp = client.get_function(FunctionName=function_name)
        config = resp["Configuration"]

        lines = [
            f"함수명: {config['FunctionName']}",
            f"ARN: {config['FunctionArn']}",
            f"Runtime: {config.get('Runtime', 'N/A')}",
            f"Handler: {config.get('Handler', 'N/A')}",
            f"Memory: {config.get('MemorySize', 'N/A')} MB",
            f"Timeout: {config.get('Timeout', 'N/A')}초",
            f"Description: {config.get('Description', '')}",
            f"LastModified: {config.get('LastModified', '')}",
        ]

        # 환경변수 (키만 표시, 값은 보안상 마스킹)
        env_vars = config.get("Environment", {}).get("Variables", {})
        if env_vars:
            lines.append(f"환경변수 키: {', '.join(env_vars.keys())}")

        # 이벤트 소스 매핑 (SQS, SNS 트리거 등)
        try:
            mappings = client.list_event_source_mappings(FunctionName=function_name)
            for m in mappings.get("EventSourceMappings", []):
                lines.append(
                    f"EventSource: {m.get('EventSourceArn', 'N/A')} "
                    f"(State: {m.get('State', 'N/A')})"
                )
        except Exception:
            pass

        # 리소스 기반 정책 (트리거 확인)
        try:
            policy_resp = client.get_policy(FunctionName=function_name)
            policy = json.loads(policy_resp["Policy"])
            lines.append("\n리소스 정책 (Raw):")
            lines.append(json.dumps(policy, indent=2, default=str))
        except client.exceptions.ResourceNotFoundException:
            lines.append("\n트리거: 리소스 정책 없음")
        except Exception as e:
            lines.append(f"\n트리거 조회 실패: {e}")

        return "\n".join(lines)

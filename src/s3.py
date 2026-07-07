from datetime import datetime, timezone
from mcp.server.fastmcp import FastMCP
from src.aws_client import get_client


def register_tools(mcp: FastMCP):

    @mcp.tool()
    def s3_list_buckets() -> str:
        """S3 버킷 목록 조회."""
        client = get_client("s3")
        resp = client.list_buckets()
        buckets = resp.get("Buckets", [])
        if not buckets:
            return "버킷 없음"

        lines = []
        for b in buckets:
            created = b["CreationDate"].strftime("%Y-%m-%d")
            lines.append(f"{b['Name']} (생성: {created})")
        return "\n".join(lines)

    @mcp.tool()
    def s3_list_objects(
        bucket: str,
        prefix: str = "",
        limit: int = 30,
    ) -> str:
        """S3 버킷 내 객체 목록 조회 (최신순).
        bucket: 버킷 이름
        prefix: 경로 접두사 (예: logs/2024/)
        limit: 결과 수 (기본 30)
        """
        client = get_client("s3")
        kwargs = {"Bucket": bucket, "MaxKeys": limit}
        if prefix:
            kwargs["Prefix"] = prefix

        # 최신 파일을 보려면 전체 조회 후 정렬 필요 — prefix가 좁으면 괜찮음
        resp = client.list_objects_v2(**kwargs)
        objects = resp.get("Contents", [])
        if not objects:
            return "객체 없음"

        objects.sort(key=lambda x: x["LastModified"], reverse=True)
        lines = []
        for obj in objects[:limit]:
            size_kb = obj["Size"] / 1024
            modified = obj["LastModified"].strftime("%Y-%m-%d %H:%M")
            if size_kb > 1024:
                size_str = f"{size_kb / 1024:.1f} MB"
            else:
                size_str = f"{size_kb:.1f} KB"
            lines.append(f"{obj['Key']} ({size_str}, {modified})")
        return "\n".join(lines)

    @mcp.tool()
    def s3_get_bucket_size(bucket: str, prefix: str = "") -> str:
        """S3 버킷(또는 prefix) 총 크기 계산.
        bucket: 버킷 이름
        prefix: 경로 접두사 (선택)
        """
        client = get_client("s3")
        paginator = client.get_paginator("list_objects_v2")
        kwargs = {"Bucket": bucket}
        if prefix:
            kwargs["Prefix"] = prefix

        total_size = 0
        total_count = 0
        for page in paginator.paginate(**kwargs):
            for obj in page.get("Contents", []):
                total_size += obj["Size"]
                total_count += 1

        if total_size > 1024 ** 3:
            size_str = f"{total_size / (1024 ** 3):.2f} GB"
        elif total_size > 1024 ** 2:
            size_str = f"{total_size / (1024 ** 2):.2f} MB"
        else:
            size_str = f"{total_size / 1024:.2f} KB"

        return f"버킷: {bucket}/{prefix}\n파일 수: {total_count:,}\n총 크기: {size_str}"

    @mcp.tool()
    def s3_read_text_file(bucket: str, key: str, max_bytes: int = 10000) -> str:
        """S3 텍스트 파일 내용 읽기 (로그 파일 등).
        bucket: 버킷 이름
        key: 파일 키
        max_bytes: 최대 읽기 바이트 (기본 10KB)
        """
        client = get_client("s3")
        resp = client.get_object(Bucket=bucket, Key=key, Range=f"bytes=0-{max_bytes - 1}")
        body = resp["Body"].read().decode("utf-8", errors="replace")
        content_length = resp.get("ContentLength", 0)

        header = f"파일: s3://{bucket}/{key} (전체 {content_length:,} bytes)\n{'='*60}\n"
        if content_length > max_bytes:
            header += f"(처음 {max_bytes:,} bytes만 표시)\n"
        return header + body

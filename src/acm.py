from mcp.server.fastmcp import FastMCP
from src.aws_client import get_client


def register_tools(mcp: FastMCP):

    @mcp.tool()
    def acm_list_certificates() -> str:
        """ACM 인증서 목록 조회.
        기본 리전과 us-east-1(CloudFront용 인증서)을 함께 조회한다.
        """
        results = []
        for region in [None, "us-east-1"]:
            client = get_client("acm", region)
            label = region or client.meta.region_name
            for page in client.get_paginator("list_certificates").paginate():
                for cert in page["CertificateSummaryList"]:
                    not_after = cert.get("NotAfter")
                    expires = not_after.strftime("%Y-%m-%d") if not_after else "N/A"
                    in_use = cert.get("InUse")
                    results.append(
                        f"{cert['DomainName']} [{label}]\n"
                        f"  상태: {cert.get('Status', 'N/A')}\n"
                        f"  만료일: {expires}\n"
                        f"  사용중: {in_use if in_use is not None else 'N/A'}\n"
                        f"  ARN: {cert['CertificateArn']}"
                    )
        return "\n\n".join(results) if results else "인증서 없음"

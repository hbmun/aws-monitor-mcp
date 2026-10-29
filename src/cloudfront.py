from mcp.server.fastmcp import FastMCP
from src.aws_client import get_client


def register_tools(mcp: FastMCP):

    @mcp.tool()
    def cloudfront_list_distributions() -> str:
        """CloudFront 배포 목록 조회."""
        client = get_client("cloudfront")
        results = []
        for page in client.get_paginator("list_distributions").paginate():
            for dist in page["DistributionList"].get("Items", []):
                aliases = dist.get("Aliases", {}).get("Items", [])
                origins = [o["DomainName"] for o in dist["Origins"]["Items"]]
                cert = dist.get("ViewerCertificate", {})
                results.append(
                    f"{dist['Id']}\n"
                    f"  도메인: {dist['DomainName']}\n"
                    f"  Aliases: {', '.join(aliases) or '없음'}\n"
                    f"  Origins: {', '.join(origins)}\n"
                    f"  상태: {dist['Status']} | Enabled: {dist['Enabled']}\n"
                    f"  인증서: {cert.get('ACMCertificateArn') or cert.get('CertificateSource', 'N/A')}\n"
                    f"  설명: {dist.get('Comment') or '-'}"
                )
        return "\n\n".join(results) if results else "배포 없음"

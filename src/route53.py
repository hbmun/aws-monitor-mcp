from mcp.server.fastmcp import FastMCP
from src.aws_client import get_client


def register_tools(mcp: FastMCP):

    @mcp.tool()
    def route53_list_zones() -> str:
        """Route53 호스팅 존 목록 조회."""
        client = get_client("route53")
        zones = []
        for page in client.get_paginator("list_hosted_zones").paginate():
            for zone in page["HostedZones"]:
                zones.append(
                    f"{zone['Name']}\n"
                    f"  ID: {zone['Id'].split('/')[-1]}\n"
                    f"  Private: {zone['Config']['PrivateZone']}\n"
                    f"  레코드 수: {zone['ResourceRecordSetCount']}"
                )
        return "\n\n".join(zones) if zones else "호스팅 존 없음"

    @mcp.tool()
    def route53_list_records(zone_id: str, name_filter: str = "") -> str:
        """Route53 호스팅 존의 레코드 목록 조회.
        zone_id: 호스팅 존 ID (예: Z1WC3OFCTKF5GV)
        name_filter: 레코드 이름에 포함된 문자열 필터 (선택)
        """
        client = get_client("route53")
        records = []
        for page in client.get_paginator("list_resource_record_sets").paginate(HostedZoneId=zone_id):
            for rr in page["ResourceRecordSets"]:
                if name_filter and name_filter not in rr["Name"]:
                    continue
                if "AliasTarget" in rr:
                    value = f"ALIAS -> {rr['AliasTarget']['DNSName']}"
                else:
                    value = ", ".join(r["Value"] for r in rr.get("ResourceRecords", []))
                ttl = f" (TTL {rr['TTL']})" if "TTL" in rr else ""
                records.append(f"{rr['Name']} {rr['Type']}{ttl}\n  {value}")
        return "\n\n".join(records) if records else "레코드 없음"

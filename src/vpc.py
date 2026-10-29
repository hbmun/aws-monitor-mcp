from mcp.server.fastmcp import FastMCP
from src.aws_client import get_client


def _name_tag(tags: list | None) -> str:
    for tag in tags or []:
        if tag["Key"] == "Name":
            return tag["Value"]
    return ""


def _format_rule(perm: dict) -> list[str]:
    proto = perm.get("IpProtocol", "-1")
    if proto == "-1":
        port = "ALL"
    else:
        from_port, to_port = perm.get("FromPort"), perm.get("ToPort")
        port = f"{proto}/{from_port}" if from_port == to_port else f"{proto}/{from_port}-{to_port}"

    sources = [r["CidrIp"] for r in perm.get("IpRanges", [])]
    sources += [r["CidrIpv6"] for r in perm.get("Ipv6Ranges", [])]
    sources += [r["GroupId"] for r in perm.get("UserIdGroupPairs", [])]
    sources += [r["PrefixListId"] for r in perm.get("PrefixListIds", [])]
    return [f"{port} <- {src}" for src in sources]


def _is_open_to_world(perm: dict) -> bool:
    return any(r["CidrIp"] == "0.0.0.0/0" for r in perm.get("IpRanges", [])) or any(
        r["CidrIpv6"] == "::/0" for r in perm.get("Ipv6Ranges", [])
    )


def register_tools(mcp: FastMCP):

    @mcp.tool()
    def vpc_list() -> str:
        """VPC 및 서브넷 목록 조회."""
        client = get_client("ec2")
        vpcs = client.describe_vpcs()["Vpcs"]
        subnets = []
        for page in client.get_paginator("describe_subnets").paginate():
            subnets.extend(page["Subnets"])

        results = []
        for vpc in vpcs:
            lines = [
                f"{_name_tag(vpc.get('Tags')) or vpc['VpcId']}\n"
                f"  ID: {vpc['VpcId']}\n"
                f"  CIDR: {vpc['CidrBlock']}\n"
                f"  Default: {vpc['IsDefault']}\n"
                f"  서브넷:"
            ]
            for sn in sorted(subnets, key=lambda x: x["AvailabilityZone"]):
                if sn["VpcId"] != vpc["VpcId"]:
                    continue
                lines.append(
                    f"    {sn['SubnetId']} | {sn['AvailabilityZone']} | {sn['CidrBlock']}"
                    f" | Public IP 자동할당: {sn['MapPublicIpOnLaunch']}"
                    f" | {_name_tag(sn.get('Tags')) or '-'}"
                )
            results.append("\n".join(lines))
        return "\n\n".join(results) if results else "VPC 없음"

    @mcp.tool()
    def vpc_list_security_groups(open_to_world_only: bool = False) -> str:
        """보안그룹 목록 및 인바운드 규칙 조회.
        open_to_world_only: True면 0.0.0.0/0 (또는 ::/0) 인바운드 규칙이 있는 그룹만 표시
        """
        client = get_client("ec2")
        groups = []
        for page in client.get_paginator("describe_security_groups").paginate():
            groups.extend(page["SecurityGroups"])

        results = []
        for sg in groups:
            perms = sg.get("IpPermissions", [])
            if open_to_world_only:
                perms = [p for p in perms if _is_open_to_world(p)]
                if not perms:
                    continue
            rules = [r for p in perms for r in _format_rule(p)]
            results.append(
                f"{sg['GroupName']}\n"
                f"  ID: {sg['GroupId']}\n"
                f"  VPC: {sg.get('VpcId', 'N/A')}\n"
                f"  설명: {sg.get('Description', '')}\n"
                f"  인바운드 ({len(rules)}개):\n"
                + "\n".join(f"    {r}" for r in rules)
            )
        return "\n\n".join(results) if results else "보안그룹 없음"

    @mcp.tool()
    def vpc_get_security_group(group_id: str) -> str:
        """보안그룹 상세 조회: 인바운드/아웃바운드 규칙과 이 그룹이 연결된 리소스(ENI).
        group_id: 보안그룹 ID (예: sg-0abc123)
        """
        client = get_client("ec2")
        sg = client.describe_security_groups(GroupIds=[group_id])["SecurityGroups"][0]

        inbound = [r for p in sg.get("IpPermissions", []) for r in _format_rule(p)]
        outbound = [r.replace("<-", "->") for p in sg.get("IpPermissionsEgress", []) for r in _format_rule(p)]

        enis = []
        paginator = client.get_paginator("describe_network_interfaces")
        for page in paginator.paginate(Filters=[{"Name": "group-id", "Values": [group_id]}]):
            enis.extend(page["NetworkInterfaces"])

        attached = []
        for eni in enis:
            instance_id = eni.get("Attachment", {}).get("InstanceId")
            public_ip = eni.get("Association", {}).get("PublicIp", "없음")
            target = instance_id or eni.get("Description") or eni["NetworkInterfaceId"]
            attached.append(f"    [{eni['InterfaceType']}] {target} | Public IP: {public_ip}")

        return (
            f"{sg['GroupName']} ({sg['GroupId']})\n"
            f"  VPC: {sg.get('VpcId', 'N/A')}\n"
            f"  설명: {sg.get('Description', '')}\n"
            f"  인바운드 ({len(inbound)}개):\n" + "\n".join(f"    {r}" for r in inbound) + "\n"
            f"  아웃바운드 ({len(outbound)}개):\n" + "\n".join(f"    {r}" for r in outbound) + "\n"
            f"  연결된 리소스 ({len(attached)}개):\n" + ("\n".join(attached) if attached else "    없음 (미사용)")
        )

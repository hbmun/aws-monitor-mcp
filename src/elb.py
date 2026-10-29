from mcp.server.fastmcp import FastMCP
from src.aws_client import get_client


def register_tools(mcp: FastMCP):

    @mcp.tool()
    def elb_list_load_balancers() -> str:
        """로드밸런서(ALB/NLB) 목록 및 리스너 조회."""
        client = get_client("elbv2")
        lbs = []
        for page in client.get_paginator("describe_load_balancers").paginate():
            lbs.extend(page["LoadBalancers"])
        if not lbs:
            return "로드밸런서 없음"

        results = []
        for lb in lbs:
            listeners = client.describe_listeners(LoadBalancerArn=lb["LoadBalancerArn"])["Listeners"]
            listener_lines = [
                f"    {l['Protocol']}:{l['Port']} -> "
                + ", ".join(a["Type"] for a in l.get("DefaultActions", []))
                for l in listeners
            ]
            results.append(
                f"{lb['LoadBalancerName']}\n"
                f"  타입: {lb['Type']} | Scheme: {lb['Scheme']}\n"
                f"  상태: {lb['State']['Code']}\n"
                f"  DNS: {lb['DNSName']}\n"
                f"  AZ: {', '.join(az['ZoneName'] for az in lb.get('AvailabilityZones', []))}\n"
                f"  보안그룹: {', '.join(lb.get('SecurityGroups', [])) or '없음'}\n"
                f"  리스너:\n" + ("\n".join(listener_lines) if listener_lines else "    없음")
            )
        return "\n\n".join(results)

    @mcp.tool()
    def elb_list_target_groups() -> str:
        """타겟그룹 목록과 타겟 헬스 상태 조회."""
        client = get_client("elbv2")
        tgs = []
        for page in client.get_paginator("describe_target_groups").paginate():
            tgs.extend(page["TargetGroups"])
        if not tgs:
            return "타겟그룹 없음"

        results = []
        for tg in tgs:
            health = client.describe_target_health(TargetGroupArn=tg["TargetGroupArn"])["TargetHealthDescriptions"]
            target_lines = [
                f"    {h['Target']['Id']}:{h['Target'].get('Port', '')} | {h['TargetHealth']['State']}"
                for h in health
            ]
            lb_names = [arn.split("/")[-2] for arn in tg.get("LoadBalancerArns", [])]
            results.append(
                f"{tg['TargetGroupName']}\n"
                f"  {tg.get('Protocol', 'N/A')}:{tg.get('Port', 'N/A')} | 타입: {tg['TargetType']}\n"
                f"  로드밸런서: {', '.join(lb_names) or '없음 (미사용)'}\n"
                f"  헬스체크: {tg.get('HealthCheckPath', 'N/A')}\n"
                f"  타겟:\n" + ("\n".join(target_lines) if target_lines else "    없음")
            )
        return "\n\n".join(results)

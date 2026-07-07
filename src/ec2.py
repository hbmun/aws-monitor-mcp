from datetime import datetime, timedelta, timezone
from mcp.server.fastmcp import FastMCP
from src.aws_client import get_client


def register_tools(mcp: FastMCP):

    @mcp.tool()
    def ec2_list_instances(state_filter: str = "running") -> str:
        """EC2 인스턴스 목록 조회.
        state_filter: running, stopped, all (기본 running)
        """
        client = get_client("ec2")
        filters = []
        if state_filter != "all":
            filters.append({"Name": "instance-state-name", "Values": [state_filter]})

        resp = client.describe_instances(Filters=filters) if filters else client.describe_instances()
        results = []
        for reservation in resp["Reservations"]:
            for inst in reservation["Instances"]:
                name = ""
                for tag in inst.get("Tags", []):
                    if tag["Key"] == "Name":
                        name = tag["Value"]
                        break
                results.append(
                    f"{name or inst['InstanceId']}\n"
                    f"  ID: {inst['InstanceId']}\n"
                    f"  타입: {inst['InstanceType']}\n"
                    f"  상태: {inst['State']['Name']}\n"
                    f"  AZ: {inst['Placement']['AvailabilityZone']}\n"
                    f"  Private IP: {inst.get('PrivateIpAddress', 'N/A')}\n"
                    f"  Public IP: {inst.get('PublicIpAddress', 'N/A')}"
                )
        return "\n\n".join(results) if results else "인스턴스 없음"

    @mcp.tool()
    def ec2_get_cpu(instance_id: str, hours: int = 1) -> str:
        """EC2 인스턴스 CPU 사용률 조회.
        instance_id: EC2 인스턴스 ID
        hours: 조회 시간 (기본 1시간)
        """
        cw = get_client("cloudwatch")
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=hours)
        period = max(300, (hours * 3600) // 60)

        resp = cw.get_metric_statistics(
            Namespace="AWS/EC2",
            MetricName="CPUUtilization",
            Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
            StartTime=start,
            EndTime=end,
            Period=period,
            Statistics=["Average", "Maximum"],
        )
        dps = sorted(resp["Datapoints"], key=lambda x: x["Timestamp"])
        if not dps:
            return "데이터 없음"

        lines = [f"EC2 CPU: {instance_id} (최근 {hours}시간)"]
        for dp in dps:
            ts = dp["Timestamp"].strftime("%H:%M")
            lines.append(f"  {ts}: avg={dp['Average']:.1f}% max={dp['Maximum']:.1f}%")
        return "\n".join(lines)

    @mcp.tool()
    def ecs_list_clusters() -> str:
        """ECS 클러스터 목록 조회."""
        client = get_client("ecs")
        arns = client.list_clusters().get("clusterArns", [])
        if not arns:
            return "ECS 클러스터 없음"

        clusters = client.describe_clusters(clusters=arns)["clusters"]
        results = []
        for c in clusters:
            results.append(
                f"{c['clusterName']}\n"
                f"  상태: {c['status']}\n"
                f"  서비스: {c.get('activeServicesCount', 0)}개\n"
                f"  태스크 (실행중): {c.get('runningTasksCount', 0)}개\n"
                f"  태스크 (대기): {c.get('pendingTasksCount', 0)}개"
            )
        return "\n\n".join(results)

    @mcp.tool()
    def ecs_list_services(cluster: str) -> str:
        """ECS 클러스터 내 서비스 목록 및 상태 조회.
        cluster: 클러스터 이름 또는 ARN
        """
        client = get_client("ecs")
        svc_arns = client.list_services(cluster=cluster).get("serviceArns", [])
        if not svc_arns:
            return "서비스 없음"

        services = client.describe_services(cluster=cluster, services=svc_arns)["services"]
        results = []
        for svc in services:
            results.append(
                f"{svc['serviceName']}\n"
                f"  상태: {svc['status']}\n"
                f"  Desired: {svc.get('desiredCount', 0)} | Running: {svc.get('runningCount', 0)} | Pending: {svc.get('pendingCount', 0)}\n"
                f"  Task Def: {svc.get('taskDefinition', '').split('/')[-1]}"
            )
        return "\n\n".join(results)

    @mcp.tool()
    def autoscaling_list_groups() -> str:
        """Auto Scaling 그룹 목록 및 현황 조회."""
        client = get_client("autoscaling")
        resp = client.describe_auto_scaling_groups()
        groups = resp.get("AutoScalingGroups", [])
        if not groups:
            return "Auto Scaling 그룹 없음"

        results = []
        for g in groups:
            results.append(
                f"{g['AutoScalingGroupName']}\n"
                f"  인스턴스: {len(g.get('Instances', []))}개\n"
                f"  Min: {g['MinSize']} | Max: {g['MaxSize']} | Desired: {g['DesiredCapacity']}\n"
                f"  헬스체크: {g.get('HealthCheckType', 'N/A')}"
            )
        return "\n\n".join(results)

from datetime import datetime, timedelta, timezone
from mcp.server.fastmcp import FastMCP
from src.aws_client import get_client


def register_tools(mcp: FastMCP):

    @mcp.tool()
    def cloudwatch_get_alarms(state_filter: str = "ALL") -> str:
        """CloudWatch 알람 상태 조회.
        state_filter: ALARM, OK, INSUFFICIENT_DATA, ALL (기본값)
        """
        client = get_client("cloudwatch")
        kwargs = {}
        if state_filter != "ALL":
            kwargs["StateValue"] = state_filter

        alarms = client.describe_alarms(**kwargs)
        results = []
        for alarm in alarms.get("MetricAlarms", []):
            results.append(
                f"[{alarm['StateValue']}] {alarm['AlarmName']}\n"
                f"  Metric: {alarm.get('Namespace','')}/{alarm.get('MetricName','')}\n"
                f"  Reason: {alarm.get('StateReason','')[:200]}"
            )
        for alarm in alarms.get("CompositeAlarms", []):
            results.append(
                f"[{alarm['StateValue']}] {alarm['AlarmName']} (composite)\n"
                f"  Reason: {alarm.get('StateReason','')[:200]}"
            )
        return "\n\n".join(results) if results else "알람 없음"

    @mcp.tool()
    def cloudwatch_get_metric(
        namespace: str,
        metric_name: str,
        dimension_name: str,
        dimension_value: str,
        stat: str = "Average",
        hours: int = 1,
    ) -> str:
        """CloudWatch 메트릭 데이터 조회.
        예시: namespace=AWS/EC2, metric_name=CPUUtilization, dimension_name=InstanceId, dimension_value=i-xxx
        stat: Average, Sum, Maximum, Minimum, SampleCount
        hours: 조회할 시간 범위 (기본 1시간)
        """
        client = get_client("cloudwatch")
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=hours)
        period = max(300, (hours * 3600) // 60)  # 최소 5분, 최대 60 데이터포인트

        resp = client.get_metric_statistics(
            Namespace=namespace,
            MetricName=metric_name,
            Dimensions=[{"Name": dimension_name, "Value": dimension_value}],
            StartTime=start,
            EndTime=end,
            Period=period,
            Statistics=[stat],
        )
        datapoints = sorted(resp["Datapoints"], key=lambda x: x["Timestamp"])
        if not datapoints:
            return "데이터 없음"

        lines = [f"{namespace}/{metric_name} ({stat}, 최근 {hours}시간)"]
        for dp in datapoints:
            ts = dp["Timestamp"].strftime("%H:%M")
            val = dp[stat]
            unit = dp.get("Unit", "")
            lines.append(f"  {ts}: {val:.2f} {unit}")
        return "\n".join(lines)

    @mcp.tool()
    def cloudwatch_search_logs(
        log_group: str,
        query: str,
        hours: int = 1,
        limit: int = 50,
    ) -> str:
        """CloudWatch Logs Insights 쿼리 실행.
        log_group: 로그 그룹 이름 (예: /ecs/logispot-api)
        query: Insights 쿼리 (예: 'fields @timestamp, @message | filter @message like /ERROR/')
        hours: 조회 시간 범위 (기본 1시간)
        limit: 결과 수 제한 (기본 50)
        """
        import time

        client = get_client("logs")
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=hours)

        if "limit" not in query.lower():
            query = f"{query} | limit {limit}"

        resp = client.start_query(
            logGroupName=log_group,
            startTime=int(start.timestamp()),
            endTime=int(end.timestamp()),
            queryString=query,
        )
        query_id = resp["queryId"]

        # 쿼리 완료 대기 (최대 30초)
        for _ in range(30):
            result = client.get_query_results(queryId=query_id)
            if result["status"] == "Complete":
                break
            time.sleep(1)

        if not result["results"]:
            return "결과 없음"

        lines = []
        for row in result["results"][:limit]:
            fields = {f["field"]: f["value"] for f in row if not f["field"].startswith("@ptr")}
            lines.append(" | ".join(f"{k}={v[:200]}" for k, v in fields.items()))
        return f"총 {len(result['results'])}건\n\n" + "\n".join(lines)

    @mcp.tool()
    def cloudwatch_list_log_groups(prefix: str = "") -> str:
        """CloudWatch 로그 그룹 목록 조회.
        prefix: 로그 그룹 이름 접두사 필터 (선택)
        """
        client = get_client("logs")
        kwargs = {}
        if prefix:
            kwargs["logGroupNamePrefix"] = prefix

        groups = []
        paginator = client.get_paginator("describe_log_groups")
        for page in paginator.paginate(**kwargs):
            for g in page["logGroups"]:
                size_mb = g.get("storedBytes", 0) / 1024 / 1024
                groups.append(f"{g['logGroupName']} ({size_mb:.1f} MB)")

        return "\n".join(groups) if groups else "로그 그룹 없음"

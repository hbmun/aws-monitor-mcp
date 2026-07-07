from datetime import datetime, timedelta, timezone
from mcp.server.fastmcp import FastMCP
from src.aws_client import get_client


def register_tools(mcp: FastMCP):

    @mcp.tool()
    def rds_list_instances() -> str:
        """RDS 인스턴스 목록 및 상태 조회."""
        client = get_client("rds")
        resp = client.describe_db_instances()

        results = []
        for db in resp["DBInstances"]:
            storage_used = db.get("AllocatedStorage", 0)
            results.append(
                f"{db['DBInstanceIdentifier']}\n"
                f"  상태: {db['DBInstanceStatus']}\n"
                f"  엔진: {db['Engine']} {db.get('EngineVersion', '')}\n"
                f"  클래스: {db['DBInstanceClass']}\n"
                f"  스토리지: {storage_used} GB\n"
                f"  Multi-AZ: {db.get('MultiAZ', False)}\n"
                f"  Endpoint: {db.get('Endpoint', {}).get('Address', 'N/A')}"
            )
        return "\n\n".join(results) if results else "RDS 인스턴스 없음"

    @mcp.tool()
    def rds_get_metrics(
        db_instance_id: str,
        hours: int = 1,
    ) -> str:
        """RDS 인스턴스 주요 메트릭 조회 (CPU, 커넥션, 읽기/쓰기 지연시간).
        db_instance_id: RDS 인스턴스 식별자
        hours: 조회 시간 범위 (기본 1시간)
        """
        cw = get_client("cloudwatch")
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=hours)
        period = max(300, (hours * 3600) // 60)

        metrics = [
            ("CPUUtilization", "Average", "%"),
            ("DatabaseConnections", "Average", "개"),
            ("FreeStorageSpace", "Average", "bytes"),
            ("ReadLatency", "Average", "초"),
            ("WriteLatency", "Average", "초"),
            ("ReadIOPS", "Average", "IOPS"),
            ("WriteIOPS", "Average", "IOPS"),
        ]

        lines = [f"RDS: {db_instance_id} (최근 {hours}시간)"]
        for metric_name, stat, unit_label in metrics:
            resp = cw.get_metric_statistics(
                Namespace="AWS/RDS",
                MetricName=metric_name,
                Dimensions=[{"Name": "DBInstanceIdentifier", "Value": db_instance_id}],
                StartTime=start,
                EndTime=end,
                Period=period,
                Statistics=[stat],
            )
            dps = sorted(resp["Datapoints"], key=lambda x: x["Timestamp"])
            if dps:
                latest = dps[-1][stat]
                if metric_name == "FreeStorageSpace":
                    latest = latest / (1024 ** 3)
                    unit_label = "GB"
                lines.append(f"  {metric_name}: {latest:.2f} {unit_label}")
            else:
                lines.append(f"  {metric_name}: 데이터 없음")

        return "\n".join(lines)

    @mcp.tool()
    def rds_slow_queries(
        db_instance_id: str,
        hours: int = 1,
        limit: int = 10,
    ) -> str:
        """RDS Performance Insights로 슬로우 쿼리 Top N 조회.
        db_instance_id: RDS 인스턴스 식별자
        hours: 조회 시간 범위 (기본 1시간)
        limit: 결과 수 (기본 10)
        """
        pi = get_client("pi")
        rds = get_client("rds")

        # DbiResourceId 조회
        db_info = rds.describe_db_instances(DBInstanceIdentifier=db_instance_id)
        resource_id = db_info["DBInstances"][0]["DbiResourceId"]

        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=hours)

        resp = pi.describe_dimension_keys(
            ServiceType="RDS",
            Identifier=resource_id,
            StartTime=start,
            EndTime=end,
            Metric="db.load.avg",
            GroupBy={"Group": "db.sql", "Limit": limit},
        )

        keys = resp.get("Keys", [])
        if not keys:
            return "슬로우 쿼리 없음 (Performance Insights 활성화 여부 확인)"

        lines = [f"Top {limit} 쿼리 (DB Load 기준, 최근 {hours}시간)"]
        for i, key in enumerate(keys, 1):
            sql = key.get("Dimensions", {}).get("db.sql.statement", "N/A")[:200]
            load = key.get("Total", 0)
            lines.append(f"  [{i}] Load: {load:.4f}\n      SQL: {sql}")

        return "\n".join(lines)

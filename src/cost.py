from datetime import date, timedelta
from mcp.server.fastmcp import FastMCP
from src.aws_client import get_client


def _period(months: int) -> dict:
    """이번 달 포함 최근 N개월. End는 exclusive라 오늘 날짜를 넣으면 어제까지 집계된다."""
    today = date.today()
    start = today.replace(day=1)
    for _ in range(max(months, 1) - 1):
        start = (start - timedelta(days=1)).replace(day=1)
    end = today if today > start else start + timedelta(days=1)
    return {"Start": start.isoformat(), "End": end.isoformat()}


def _format_groups(results: list, min_amount: float) -> str:
    blocks = []
    for r in results:
        rows = []
        for g in r["Groups"]:
            amount = float(g["Metrics"]["UnblendedCost"]["Amount"])
            if amount >= min_amount:
                rows.append((g["Keys"][0], amount))
        rows.sort(key=lambda x: x[1], reverse=True)
        total = sum(float(g["Metrics"]["UnblendedCost"]["Amount"]) for g in r["Groups"])

        period = f"{r['TimePeriod']['Start']} ~ {r['TimePeriod']['End']}"
        estimated = " (추정치)" if r.get("Estimated") else ""
        lines = [f"[{period}]{estimated} 합계: ${total:,.2f}"]
        lines += [f"  ${amount:>10,.2f}  {key}" for key, amount in rows]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) if blocks else "데이터 없음"


def register_tools(mcp: FastMCP):

    @mcp.tool()
    def cost_by_service(months: int = 2, min_amount: float = 1.0) -> str:
        """AWS 서비스별 월 비용 조회 (Cost Explorer, UnblendedCost, USD).
        months: 이번 달 포함 최근 N개월 (기본 2). 이번 달은 어제까지 집계
        min_amount: 이 금액(USD) 미만 서비스는 숨김 (기본 1.0, 합계에는 포함)
        참고: Cost Explorer API는 호출당 $0.01 과금
        """
        client = get_client("ce", "us-east-1")
        resp = client.get_cost_and_usage(
            TimePeriod=_period(months),
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )
        return _format_groups(resp["ResultsByTime"], min_amount)

    @mcp.tool()
    def cost_by_usage_type(service: str, months: int = 1, min_amount: float = 0.01) -> str:
        """특정 서비스의 사용 유형(USAGE_TYPE)별 월 비용 조회.
        service: cost_by_service 결과에 나온 서비스명 그대로 (예: Amazon CloudFront, Amazon Elastic Compute Cloud - Compute)
        months: 이번 달 포함 최근 N개월 (기본 1)
        min_amount: 이 금액(USD) 미만 항목은 숨김 (기본 0.01, 합계에는 포함)
        참고: Cost Explorer API는 호출당 $0.01 과금
        """
        client = get_client("ce", "us-east-1")
        resp = client.get_cost_and_usage(
            TimePeriod=_period(months),
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
            Filter={"Dimensions": {"Key": "SERVICE", "Values": [service]}},
            GroupBy=[{"Type": "DIMENSION", "Key": "USAGE_TYPE"}],
        )
        return _format_groups(resp["ResultsByTime"], min_amount)

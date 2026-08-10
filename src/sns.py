from mcp.server.fastmcp import FastMCP
from src.aws_client import get_client


def register_tools(mcp: FastMCP):

    @mcp.tool()
    def sns_list_topics() -> str:
        """SNS 토픽 목록 조회."""
        client = get_client("sns")
        topics = []
        paginator = client.get_paginator("list_topics")
        for page in paginator.paginate():
            for topic in page["Topics"]:
                arn = topic["TopicArn"]
                name = arn.split(":")[-1]
                topics.append(f"{name}\n  ARN: {arn}")
        return "\n\n".join(topics) if topics else "토픽 없음"

    @mcp.tool()
    def sns_get_topic_subscriptions(topic_arn: str) -> str:
        """SNS 토픽의 구독 목록 조회.
        topic_arn: 토픽 ARN (예: arn:aws:sns:ap-northeast-2:123456:my-topic)
        """
        client = get_client("sns")
        subs = []
        paginator = client.get_paginator("list_subscriptions_by_topic")
        for page in paginator.paginate(TopicArn=topic_arn):
            for sub in page["Subscriptions"]:
                subs.append(
                    f"Protocol: {sub['Protocol']}\n"
                    f"  Endpoint: {sub.get('Endpoint', 'N/A')}\n"
                    f"  SubscriptionArn: {sub.get('SubscriptionArn', 'N/A')}"
                )
        return "\n\n".join(subs) if subs else "구독 없음"

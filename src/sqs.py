from mcp.server.fastmcp import FastMCP
from src.aws_client import get_client


def register_tools(mcp: FastMCP):

    @mcp.tool()
    def sqs_list_queues(prefix: str = "") -> str:
        """SQS 큐 목록과 메시지 수 조회.
        prefix: 큐 이름 접두사 필터 (선택)
        """
        client = get_client("sqs")
        kwargs = {}
        if prefix:
            kwargs["QueueNamePrefix"] = prefix

        resp = client.list_queues(**kwargs)
        urls = resp.get("QueueUrls", [])
        if not urls:
            return "큐 없음"

        results = []
        for url in urls:
            attrs = client.get_queue_attributes(
                QueueUrl=url,
                AttributeNames=[
                    "ApproximateNumberOfMessages",
                    "ApproximateNumberOfMessagesNotVisible",
                    "ApproximateNumberOfMessagesDelayed",
                ],
            )["Attributes"]
            name = url.split("/")[-1]
            visible = attrs.get("ApproximateNumberOfMessages", "0")
            in_flight = attrs.get("ApproximateNumberOfMessagesNotVisible", "0")
            delayed = attrs.get("ApproximateNumberOfMessagesDelayed", "0")
            results.append(
                f"{name}\n"
                f"  대기: {visible} | 처리중: {in_flight} | 지연: {delayed}"
            )
        return "\n\n".join(results)

    @mcp.tool()
    def sqs_queue_detail(queue_name: str) -> str:
        """SQS 큐 상세 정보 조회 (DLQ 연결, 설정 등).
        queue_name: 큐 이름
        """
        client = get_client("sqs")
        url_resp = client.get_queue_url(QueueName=queue_name)
        url = url_resp["QueueUrl"]

        attrs = client.get_queue_attributes(
            QueueUrl=url, AttributeNames=["All"]
        )["Attributes"]

        lines = [f"큐: {queue_name}"]
        lines.append(f"  ARN: {attrs.get('QueueArn', '')}")
        lines.append(f"  대기 메시지: {attrs.get('ApproximateNumberOfMessages', '0')}")
        lines.append(f"  처리중: {attrs.get('ApproximateNumberOfMessagesNotVisible', '0')}")
        lines.append(f"  지연: {attrs.get('ApproximateNumberOfMessagesDelayed', '0')}")
        lines.append(f"  Visibility Timeout: {attrs.get('VisibilityTimeout', '')}초")
        lines.append(f"  Message Retention: {int(attrs.get('MessageRetentionPeriod', 0)) // 86400}일")

        # DLQ 확인
        redrive = attrs.get("RedrivePolicy", "")
        if redrive:
            import json
            policy = json.loads(redrive)
            dlq_arn = policy.get("deadLetterTargetArn", "")
            max_receive = policy.get("maxReceiveCount", "")
            lines.append(f"  DLQ: {dlq_arn.split(':')[-1]} (maxReceive: {max_receive})")
        else:
            lines.append("  DLQ: 없음")

        return "\n".join(lines)

    @mcp.tool()
    def sqs_peek_messages(queue_name: str, count: int = 5) -> str:
        """SQS 큐에서 메시지 미리보기 (삭제하지 않음).
        queue_name: 큐 이름
        count: 조회할 메시지 수 (최대 10)
        """
        client = get_client("sqs")
        url_resp = client.get_queue_url(QueueName=queue_name)
        url = url_resp["QueueUrl"]

        resp = client.receive_message(
            QueueUrl=url,
            MaxNumberOfMessages=min(count, 10),
            VisibilityTimeout=0,  # 즉시 다시 보이게
            WaitTimeSeconds=1,
            MessageAttributeNames=["All"],
        )
        messages = resp.get("Messages", [])
        if not messages:
            return "메시지 없음"

        results = []
        for i, msg in enumerate(messages, 1):
            body = msg["Body"][:500]
            results.append(f"[{i}] ID: {msg['MessageId'][:12]}...\n  Body: {body}")
        return "\n\n".join(results)

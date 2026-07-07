# MCP AWS Monitor

Logispot AWS 인프라 모니터링 MCP 서버.

## 프로젝트 구조

```
mcp-aws-monitor/
├── .env                ← AWS 인증 키 (git 미추적)
├── .env.example        ← .env 템플릿
├── .gitignore
├── pyproject.toml      ← 패키지 정의 (mcp, boto3, python-dotenv)
├── README.md
└── src/
    ├── __init__.py
    ├── server.py       ← MCP 서버 진입점
    ├── aws_client.py   ← boto3 클라이언트 팩토리 (lru_cache)
    ├── cloudwatch.py   ← CloudWatch 도구 4개
    ├── sqs.py          ← SQS 도구 3개
    ├── rds.py          ← RDS 도구 3개
    ├── s3.py           ← S3 도구 4개
    └── ec2.py          ← EC2/ECS/AutoScaling 도구 5개
```

## 아키텍처

### 동작 흐름

```
Claude Code 세션 시작
  → MCP 서버 프로세스 실행 (src/server.py)
    → .env에서 AWS 키 로드 (python-dotenv)
    → FastMCP 인스턴스 생성
    → 각 모듈의 register_tools()로 도구 19개 등록
    → stdio 기반으로 Claude Code와 통신
```

### aws_client.py

boto3 클라이언트를 `lru_cache`로 캐싱하는 팩토리.
동일 서비스에 대해 클라이언트를 한 번만 생성하고 재사용한다.
모든 모듈에서 `get_client("서비스명")`으로 호출.

### 모듈 패턴

모든 도구가 동일한 패턴을 따른다:
1. `get_client()`로 boto3 클라이언트 획득
2. AWS API 호출
3. 응답을 한국어 포맷 문자열로 변환해서 반환

MCP 도구는 반환값이 문자열이어야 하므로 전부 `-> str`.

## 제공 도구 (19개)

### CloudWatch (4개)

#### `cloudwatch_get_alarms`
CloudWatch 알람 상태 조회.
- `state_filter` (str, 기본 "ALL"): ALARM, OK, INSUFFICIENT_DATA, ALL
- MetricAlarms와 CompositeAlarms 모두 조회
- 알람 이름, 연결 메트릭, 상태 변경 사유 반환

#### `cloudwatch_get_metric`
특정 메트릭의 시계열 데이터 조회.
- `namespace` (str): AWS 네임스페이스 (예: AWS/EC2, AWS/RDS)
- `metric_name` (str): 메트릭 이름 (예: CPUUtilization)
- `dimension_name` (str): 차원 이름 (예: InstanceId)
- `dimension_value` (str): 차원 값 (예: i-0abc123)
- `stat` (str, 기본 "Average"): Average, Sum, Maximum, Minimum, SampleCount
- `hours` (int, 기본 1): 조회 시간 범위
- Period는 최소 5분, 최대 60 데이터포인트로 자동 계산

#### `cloudwatch_search_logs`
CloudWatch Logs Insights 쿼리 실행.
- `log_group` (str): 로그 그룹 이름 (예: /ecs/logispot-api)
- `query` (str): Insights 쿼리문
- `hours` (int, 기본 1): 조회 시간 범위
- `limit` (int, 기본 50): 결과 수 제한
- 비동기 쿼리 → 최대 30초 동안 1초 간격으로 폴링해서 완료 대기
- 쿼리에 limit 절이 없으면 자동 추가

#### `cloudwatch_list_log_groups`
CloudWatch 로그 그룹 목록 조회.
- `prefix` (str, 선택): 로그 그룹 이름 접두사 필터
- 페이지네이터로 전체 목록 조회
- 각 로그 그룹의 저장 크기(MB) 표시

### SQS (3개)

#### `sqs_list_queues`
SQS 큐 목록과 메시지 수 조회.
- `prefix` (str, 선택): 큐 이름 접두사 필터
- 큐별로 대기(Visible) / 처리중(NotVisible) / 지연(Delayed) 메시지 수 표시

#### `sqs_queue_detail`
SQS 큐 상세 정보 조회.
- `queue_name` (str): 큐 이름
- ARN, 메시지 수, VisibilityTimeout, MessageRetentionPeriod 표시
- RedrivePolicy가 있으면 DLQ 이름과 maxReceiveCount 파싱해서 표시

#### `sqs_peek_messages`
SQS 큐 메시지 미리보기. 메시지를 삭제하지 않음.
- `queue_name` (str): 큐 이름
- `count` (int, 기본 5): 조회 수 (최대 10)
- VisibilityTimeout=0으로 호출해서 메시지가 즉시 다시 보이게 함
- 메시지 Body 500자까지 표시

### RDS (3개)

#### `rds_list_instances`
RDS 인스턴스 목록 및 상태 조회.
- 파라미터 없음
- 인스턴스별 식별자, 상태, 엔진/버전, 클래스, 스토리지, Multi-AZ, Endpoint 표시

#### `rds_get_metrics`
RDS 인스턴스 주요 메트릭 조회. CloudWatch API 사용.
- `db_instance_id` (str): RDS 인스턴스 식별자
- `hours` (int, 기본 1): 조회 시간 범위
- 조회 메트릭 7개:
  - CPUUtilization (%)
  - DatabaseConnections (개)
  - FreeStorageSpace (GB로 변환)
  - ReadLatency / WriteLatency (초)
  - ReadIOPS / WriteIOPS
- 각 메트릭의 가장 최근 데이터포인트 값 반환

#### `rds_slow_queries`
RDS Performance Insights로 슬로우 쿼리 Top N 조회.
- `db_instance_id` (str): RDS 인스턴스 식별자
- `hours` (int, 기본 1): 조회 시간 범위
- `limit` (int, 기본 10): 결과 수
- RDS API로 DbiResourceId 조회 → PI API로 db.load.avg 기준 쿼리 랭킹
- Performance Insights가 비활성화된 인스턴스에서는 빈 결과 반환

### S3 (4개)

#### `s3_list_buckets`
S3 버킷 목록 조회.
- 파라미터 없음
- 버킷 이름, 생성일 표시

#### `s3_list_objects`
S3 버킷 내 객체 목록 조회.
- `bucket` (str): 버킷 이름
- `prefix` (str, 선택): 경로 접두사 (예: logs/2024/)
- `limit` (int, 기본 30): 결과 수
- MaxKeys로 먼저 자른 후 LastModified 역순 정렬
- 파일 크기 KB/MB 자동 변환

#### `s3_get_bucket_size`
S3 버킷 또는 prefix의 총 크기 계산.
- `bucket` (str): 버킷 이름
- `prefix` (str, 선택): 경로 접두사
- 페이지네이터로 전체 객체 순회하며 합산
- 파일 수, 총 크기(KB/MB/GB 자동 변환) 반환
- 대용량 버킷은 시간이 오래 걸릴 수 있음

#### `s3_read_text_file`
S3 텍스트 파일 내용 읽기.
- `bucket` (str): 버킷 이름
- `key` (str): 파일 키
- `max_bytes` (int, 기본 10000): 최대 읽기 바이트
- Range 헤더로 앞부분만 읽음 (대용량 파일 안전)
- UTF-8 디코딩, 깨진 문자는 replace 처리

### EC2 / ECS / AutoScaling (5개)

#### `ec2_list_instances`
EC2 인스턴스 목록 조회.
- `state_filter` (str, 기본 "running"): running, stopped, all
- Name 태그, 인스턴스 ID, 타입, 상태, AZ, Private/Public IP 표시

#### `ec2_get_cpu`
EC2 인스턴스 CPU 사용률 시계열 조회.
- `instance_id` (str): EC2 인스턴스 ID
- `hours` (int, 기본 1): 조회 시간
- Average와 Maximum 두 통계를 함께 표시

#### `ecs_list_clusters`
ECS 클러스터 목록 조회.
- 파라미터 없음
- 클러스터별 상태, 활성 서비스 수, 실행중/대기 태스크 수 표시

#### `ecs_list_services`
ECS 클러스터 내 서비스 목록 및 상태 조회.
- `cluster` (str): 클러스터 이름 또는 ARN
- 서비스별 상태, Desired/Running/Pending 카운트, Task Definition 표시

#### `autoscaling_list_groups`
Auto Scaling 그룹 목록 및 현황 조회.
- 파라미터 없음
- 그룹별 인스턴스 수, Min/Max/Desired 설정, 헬스체크 타입 표시

## 설치

```bash
cd ~/work/mcp-aws-monitor
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## 설정

`.env` 파일에 AWS 키 입력:

```
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret
AWS_DEFAULT_REGION=ap-northeast-2
```

## Claude Code 연동

```bash
claude mcp add aws-monitor -s user -- /Users/hbmun/work/mcp-aws-monitor/.venv/bin/python -m src.server
```

또는 수동으로 `~/.claude.json`에 추가됨:

```json
{
  "mcpServers": {
    "aws-monitor": {
      "command": "/Users/hbmun/work/mcp-aws-monitor/.venv/bin/python",
      "args": ["-m", "src.server"],
      "cwd": "/Users/hbmun/work/mcp-aws-monitor"
    }
  }
}
```

등록 후 Claude Code 재시작 필요.

## IAM 권한

IAM 유저 생성 시 아래 인라인 정책 연결:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "cloudwatch:Describe*",
        "cloudwatch:Get*",
        "logs:Describe*",
        "logs:StartQuery",
        "logs:GetQueryResults",
        "sqs:List*",
        "sqs:Get*",
        "sqs:ReceiveMessage",
        "rds:Describe*",
        "pi:Describe*",
        "s3:List*",
        "s3:Get*",
        "ec2:Describe*",
        "ecs:List*",
        "ecs:Describe*",
        "autoscaling:Describe*"
      ],
      "Resource": "*"
    }
  ]
}
```

1. AWS 콘솔 → IAM → 사용자 → 사용자 생성
2. 권한 설정 → "직접 정책 연결" → JSON 탭에 위 정책 붙여넣기
3. 사용자 생성 완료 후 액세스 키 발급 (CLI 용도)
4. `.env`에 키 입력

## 알려진 제한사항

- 단일 리전(ap-northeast-2)만 지원. 다중 리전 조회 불가
- EC2, RDS, AutoScaling 목록 조회 시 첫 페이지만 반환 (대량 리소스 시 잘림)
- `s3_list_objects`는 S3 기본 정렬 후 limit 적용이라 진짜 최신 N개가 아닐 수 있음
- `cloudwatch_search_logs` 쿼리가 30초 내 완료되지 않으면 불완전한 결과 반환 가능
- AWS API 에러 시 예외가 그대로 노출됨 (권한 부족, 잘못된 리소스 ID 등)

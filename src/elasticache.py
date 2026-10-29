from mcp.server.fastmcp import FastMCP
from src.aws_client import get_client


def register_tools(mcp: FastMCP):

    @mcp.tool()
    def elasticache_list() -> str:
        """ElastiCache 목록 조회 (Serverless 캐시 + 노드 기반 클러스터)."""
        client = get_client("elasticache")
        results = []

        for cache in client.describe_serverless_caches().get("ServerlessCaches", []):
            endpoint = cache.get("Endpoint", {})
            limits = cache.get("CacheUsageLimits", {})
            storage_max = limits.get("DataStorage", {}).get("Maximum")
            ecpu_max = limits.get("ECPUPerSecond", {}).get("Maximum")
            results.append(
                f"{cache['ServerlessCacheName']} (Serverless)\n"
                f"  엔진: {cache['Engine']} {cache.get('FullEngineVersion', cache.get('MajorEngineVersion', ''))}\n"
                f"  상태: {cache['Status']}\n"
                f"  Endpoint: {endpoint.get('Address', 'N/A')}:{endpoint.get('Port', '')}\n"
                f"  한도: 스토리지 {storage_max or '무제한'} GB | ECPU/s {ecpu_max or '무제한'}\n"
                f"  보안그룹: {', '.join(cache.get('SecurityGroupIds', [])) or '없음'}"
            )

        for page in client.get_paginator("describe_cache_clusters").paginate():
            for c in page["CacheClusters"]:
                results.append(
                    f"{c['CacheClusterId']}\n"
                    f"  엔진: {c['Engine']} {c['EngineVersion']}\n"
                    f"  상태: {c['CacheClusterStatus']}\n"
                    f"  노드: {c['CacheNodeType']} x {c['NumCacheNodes']}\n"
                    f"  Replication Group: {c.get('ReplicationGroupId') or '없음'}"
                )
        return "\n\n".join(results) if results else "ElastiCache 없음"

import boto3
from functools import lru_cache


@lru_cache
def get_client(service: str, region: str | None = None):
    return boto3.client(service, region_name=region)


@lru_cache
def get_resource(service: str):
    return boto3.resource(service)

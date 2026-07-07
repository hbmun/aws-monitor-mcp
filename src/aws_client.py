import boto3
from functools import lru_cache


@lru_cache
def get_client(service: str):
    return boto3.client(service)


@lru_cache
def get_resource(service: str):
    return boto3.resource(service)

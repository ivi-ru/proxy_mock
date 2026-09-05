"""Routes of the proxy-mock API."""

from enum import StrEnum


class Endpoints(StrEnum):
    PROXY_MOCK = "/proxy_mock"
    CONFIGURE_MOCK = "/configure_mock"
    STORAGE_CLEAN = "/storage/clean"
    TRAFFIC_CLEAN = "/traffic/clean"
    CACHE_CLEAN = "/cache/clean"
    TRAFFIC = "/traffic"
    TRAFFIC_SETTINGS = "/traffic/settings"
    STORAGE = "/storage"
    STORAGE_SNAPSHOT = "/storage/snapshot"

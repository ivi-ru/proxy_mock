"""Routes of the proxy-mock API."""

from enum import StrEnum


class Endpoints(StrEnum):
    PROXY_MOCK = ""
    CONFIGURE_MOCK = "/mocks"
    CACHE_CLEAN = "/cache"
    TRAFFIC = "/traffic"
    TRAFFIC_SETTINGS = "/settings"
    STORAGE = "/mocks"
    STORAGE_SNAPSHOT = "/snapshot"
    SEQUENCE_STATE = "/sequence-state"

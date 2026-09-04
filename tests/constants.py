from http import HTTPMethod

MOCK_PATHS = [
    "/test",
    "test",
    "test/",
    "/test/",
    "/test/test",
    "/test/test/",
    "test/test",
    "test/test/",
    "test/1/2/3",
    "test?arg=1",
    "test/{arg}",
    "test/{arg}/test/{arg2}",
]

MOCK_METHODS = [[m.value] for m in HTTPMethod if m != HTTPMethod.CONNECT] + [
    [HTTPMethod.OPTIONS, HTTPMethod.HEAD],
    [HTTPMethod.GET, HTTPMethod.PATCH, HTTPMethod.TRACE],
    None,
]

BYTE_RESPONSE = "Any Proto Object".encode()
EMPTY_BYTE_RESPONSE = b""

EXPECTED_RESPONSE = [
    "test",
    {"test": "test"},
    {},
    ["test"],
    [{"test": "test"}],
    [],
    None,
    BYTE_RESPONSE,
]

EXPECTED_STATUSES = [201, 302, 425, 599]

TEST_CONFIGURE_DATA = {
    "path": "/test",
    "body": {"test_key": "test_value"},
    "headers": {"Test": "Header"},
    "extra_info": {"service": "test_service"},
    "status_code": 201,
    "proxy_host": None,
    "timeout": None,
    "rules": None,
}

PROXY_HOST_DATA = "https://example.com", "/"
INCOMPLETE_PROXY_HOST = "example.com", "/incomplete-proxy-host"
# The .invalid TLD is reserved by RFC 2606 and never resolves, so the DNS error is immediate.
UNREACHABLE_PROXY_HOST = "http://proxy-mock-unreachable.invalid"

TEST_RULES_DATA = [
    {
        "input_data": {"body": {"test_body": "body"}},
        "output_data": {
            "body": {"type": "body"},
            "headers": {"test_header": "body"},
            "status_code": 210,
        },
    },
    {
        "input_data": {"body": BYTE_RESPONSE},
        "output_data": {
            "body": BYTE_RESPONSE,
            "headers": {"test_header": "body"},
            "status_code": 211,
        },
    },
    {
        "input_data": {"headers": {"test_header": "header"}},
        "output_data": {
            "body": {"type": "header"},
            "headers": {"test_header": "header"},
            "status_code": 310,
        },
    },
    {
        "input_data": {"query": {"test_query": "query"}},
        "output_data": {
            "body": {"type": "query"},
            "headers": {"test_header": "query"},
            "status_code": 410,
        },
    },
    {
        "input_data": {
            "methods": [HTTPMethod.DELETE, HTTPMethod.PATCH],
            "body": {"test_body": "body"},
            "headers": {"test_header": "header"},
            "query": {"test_query": "query"},
        },
        "output_data": {"body": {"type": "all"}, "headers": {"test_header": "all"}, "status_code": 510},
    },
    {
        "input_data": {"methods": [HTTPMethod.DELETE, HTTPMethod.PATCH]},
        "output_data": {
            "body": {"type": "methods"},
            "headers": {"test_header": "methods"},
            "status_code": 209,
        },
    },
    {
        "input_data": {"body": {"test_body": "body"}, "timeout": 0.5},
        "output_data": {
            "body": {"type": "body"},
            "headers": {"test_header": "body"},
            "status_code": 210,
        },
    },
    {
        "input_data": {"methods": [HTTPMethod.GET], "proxy_host": PROXY_HOST_DATA[0]},
        "output_data": {
            "body": {"type": "body"},
            "headers": {"test_header": "body"},
            "status_code": 210,
        },
    },
]

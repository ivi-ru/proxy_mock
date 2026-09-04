from fastapi import Request


def get_app(request: Request):
    return request.app

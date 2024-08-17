import copy
import json
import pickle
import time

from flask import Flask
from flask import Response
from flask import jsonify
from flask import request
from pydantic import ValidationError

from proxy_mock.constants import MOCK_PARAMS_STORAGE
from proxy_mock.etc.settings import Config
from proxy_mock.etc.settings import configure_logger
from proxy_mock.etc.settings import get_version_from_pyproject
from proxy_mock.mock_service import cleanup_storage
from proxy_mock.mock_service import create_response
from proxy_mock.mock_service import delete_mock
from proxy_mock.mock_service import find_response
from proxy_mock.mock_service import path_finder
from proxy_mock.mock_service import proxy_request_to_host
from proxy_mock.mock_service import return_storage
from proxy_mock.models import ConfigureMockRequestSchema
from proxy_mock.utils import get_request_data
from proxy_mock.utils import log_request


class MockParams:
    backend: dict = None


class Mock(Flask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.params = {0: MockParams()}
        self.params_storage = copy.deepcopy(MOCK_PARAMS_STORAGE)

    def reset(self, request_id):
        self.params.clear()
        self.params[request_id] = MockParams()


app = Mock(__name__)
app.config.from_object(Config)

configure_logger(app)
version = get_version_from_pyproject(app)


@app.get("/status")
@log_request
def status():
    """Проверка доступности сервера."""
    response = {"success": True, "version": version}

    return jsonify(response)


@app.post("/configure_mock")
@log_request
def configure_mock():
    """Записывает мок в хранилище."""
    try:
        validate_data = ConfigureMockRequestSchema.model_validate(request.json).model_dump()
    except ValidationError as err:
        return jsonify({"success": False, "error": json.loads(err.json())}), 400

    mock_data = create_response(**validate_data)
    response = {
        "success": True,
        "path": validate_data["path"],
        "data": mock_data,
    }

    return jsonify(response), 201


@app.post("/configure_mock/binary")
@log_request
def configure_binary_mock():
    """Записывает мок с бинарным содержимым в хранилище."""
    input_data = pickle.loads(request.data)

    try:
        validate_data = ConfigureMockRequestSchema.model_validate(input_data).model_dump()
    except ValidationError as err:
        return jsonify({"success": False, "error": json.loads(err.json())}), 400

    mock_data = copy.deepcopy(create_response(**validate_data))
    mock_data["mock_data"]["body"] = str(mock_data["mock_data"]["body"])
    response = {
        "success": True,
        "path": validate_data["path"],
        "data": mock_data,
    }

    return jsonify(response), 201


@app.route("/<path:path>", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@log_request
@get_request_data
def catch_all(request_data) -> Response | tuple[Response, int]:
    """Ловит любой запрос, ищет мок в хранилище по ручке,
    проксирует запрос на заданный хост, иначе
    записывает параметры запроса и выводит ответ, если он есть."""
    mock_data = find_response(request.path)

    if mock_data is None:
        app.params_storage.append(request_data)

        app.logger.warning(f"Не найден мок {request.path}")
        return jsonify({"error": f"Не найден мок {request.path}"}), 404

    # Записывает параметры запроса в хранилище параметров
    request_data["extra_info"] = mock_data["extra_info"]
    app.params_storage.append(request_data)

    app.logger.info("Нашли подготовленный ответ")
    # Возвращает ответ от внешнего хоста, если он указан
    if proxy_host := mock_data["proxy_host"]:
        app.logger.info(f"Проксируем запрос {request.path} на {proxy_host}")
        proxy_response = proxy_request_to_host(request, proxy_host)

        app.logger.info("Получен ответ от внешнего хоста")
        return Response(
            response=proxy_response.content,
            status=proxy_response.status_code,
            headers=dict(proxy_response.headers),
        )

    if mock_data["timeout"]:
        app.logger.info(
            f"Для запроса {request.path} установлен таймаут: спим {mock_data['timeout']} секунд перед ответом"
        )
        time.sleep(float(mock_data["timeout"]))

    if mock_data["mock_data"]["body"] is None:
        return Response(
            mock_data["mock_data"]["body"], mock_data["mock_data"]["status_code"], mock_data["mock_data"]["headers"]
        )

    if isinstance(mock_data["mock_data"]["body"], bytes):
        return Response(
            mock_data["mock_data"]["body"],
            mock_data["mock_data"]["status_code"],
            mock_data["mock_data"]["headers"],
            content_type="application/octet-stream"
        )
    return mock_data["mock_data"]["body"], mock_data["mock_data"]["status_code"], mock_data["mock_data"]["headers"]


@app.post("/cleanup_params")
@log_request
def clear_params():
    """Очищает параметры запросов."""
    app.params_storage = copy.deepcopy(MOCK_PARAMS_STORAGE)

    response = {"success": True, "data": app.params_storage}

    return jsonify(response), 200


@app.post("/cleanup_storage")
@log_request
def clear_storage():
    """Очищает хранилище моков.
    Очищает все хранилище или,
    если передан квери-параметр path, то
    удалит только его, если он найден, иначе не удалится ничего
    """
    query_params = dict(request.args)
    path = query_params.get("path")

    result = delete_mock(path) if path else cleanup_storage()

    response = {"success": result, "data": return_storage()}

    return jsonify(response), 200


@app.get("/storage")
@log_request
def get_storage():
    """Выводит все имеющиеся мокированные запросы.
    Выводит все хранилище или,
    если передан квери-параметр path, то
    выведет только его, если он найден, иначе выведет пустой словарь
    """
    query_params = dict(request.args)

    data = return_storage()
    if path := query_params.get("path"):
        if path := path_finder(path):
            data = data.get(path)
        else:
            data = None

    response = {"success": True, "data": data}

    return jsonify(response), 200


@app.get("/mock_params")
@log_request
def get_mock_params():
    """Выводит собранные данные от входящих запросов."""
    response = {"success": True, "data": app.params_storage}

    return jsonify(response), 200


@app.errorhandler(404)
@log_request
@get_request_data
def catch_unknown_path(error, request_data):
    app.logger.warning(f"Путь не найден: {error}")

    # Записывает параметры запроса в хранилище параметров
    app.params_storage.append(request_data)

    return jsonify({"error": "Not found"}), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0")

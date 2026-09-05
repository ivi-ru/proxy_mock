.PHONY: install run docker_run test lint lint_fix bench clean

install:
	uv sync --all-extras

run:
	proxy-mock --host=0.0.0.0 --port=5000 --log-level=info

docker_run:
	docker build -t proxy_mock \
		--build-arg PYTHON_VERSION=3.14-slim \
		--build-arg CMD_ARG="python -m proxy_mock --host=0.0.0.0 --port=5000 --log-level=info" .
	docker run --rm -it --init -p 5000:5000 proxy_mock

test:
	pytest --cov -v

lint:
	ruff check .
	ruff format --check .

lint_fix:
	ruff check . --fix
	ruff format .

bench:
	python scripts/benchmark.py --host http://localhost:5000 --requests 1000 --concurrency 100 --rounds 5

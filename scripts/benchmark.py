"""
More reliable benchmark for proxy_mock.

Usage:
  python scripts/benchmark.py --host http://localhost:5000 --requests 500 --concurrency 100 --rounds 5
"""

import argparse
import asyncio
import statistics
import time
from dataclasses import dataclass

import httpx2


@dataclass
class Result:
    latencies_ms: list[float]
    duration_s: float

    @property
    def rps(self) -> float:
        return len(self.latencies_ms) / self.duration_s if self.duration_s > 0 else 0.0


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    vals = sorted(values)
    k = (len(vals) - 1) * (p / 100)
    f = int(k)
    c = min(f + 1, len(vals) - 1)
    if f == c:
        return vals[f]
    return vals[f] + (vals[c] - vals[f]) * (k - f)


def stats(values: list[float]) -> dict[str, float]:
    return {
        "avg": statistics.mean(values),
        "p50": percentile(values, 50),
        "p95": percentile(values, 95),
        "p99": percentile(values, 99),
        "max": max(values),
    }


async def run_load(
    client: httpx2.AsyncClient,
    method: str,
    path: str,
    requests_count: int,
    concurrency: int,
    json_body: dict | None = None,
) -> Result:
    sem = asyncio.Semaphore(concurrency)
    latencies: list[float] = []

    async def one() -> None:
        async with sem:
            started = time.perf_counter()
            if method == "GET":
                resp = await client.get(path)
            else:
                resp = await client.post(path, json=json_body)
            resp.raise_for_status()
            latencies.append((time.perf_counter() - started) * 1000)

    started_total = time.perf_counter()
    await asyncio.gather(*(one() for _ in range(requests_count)))
    total = time.perf_counter() - started_total
    return Result(latencies_ms=latencies, duration_s=total)


async def prepare_data(client: httpx2.AsyncClient) -> None:
    await client.post("/storage/clean")
    await client.post("/traffic/clean")
    await client.post("/cache/clean")

    base_mock = {
        "path": "/bench/mock",
        "mock_data": {"body": {"ok": True}, "status_code": 200},
    }

    rules_mock = {
        "path": "/bench/rules",
        "mock_data": {"body": {"default": True}, "status_code": 200},
        "rules": [
            {
                "priority": 10,
                "input_data": {"headers": {"x-scenario": "rule"}},
                "output_data": {"body": {"rule": "matched"}, "status_code": 201, "headers": {}},
                "extra_info": {"rule": "h1"},
            }
        ],
    }

    r = await client.post("/configure_mock", json=base_mock)
    r.raise_for_status()
    r = await client.post("/configure_mock", json=rules_mock)
    r.raise_for_status()


async def scenario_round(
    client: httpx2.AsyncClient,
    requests_count: int,
    concurrency: int,
) -> dict[str, Result]:
    # 1) pure mock GET
    mock_res = await run_load(client, "GET", "/bench/mock", requests_count, concurrency)

    # 2) rules path with header
    sem = asyncio.Semaphore(concurrency)
    rule_lat: list[float] = []
    s = time.perf_counter()

    async def one_rule():
        async with sem:
            t0 = time.perf_counter()
            r = await client.post("/bench/rules", headers={"x-scenario": "rule"}, json={"x": 1})
            r.raise_for_status()
            rule_lat.append((time.perf_counter() - t0) * 1000)

    await asyncio.gather(*(one_rule() for _ in range(requests_count)))
    rules_res = Result(rule_lat, time.perf_counter() - s)

    # 3) traffic read
    traffic_res = await run_load(client, "GET", "/traffic", requests_count, concurrency)

    return {"mock": mock_res, "rules": rules_res, "traffic": traffic_res}


def print_result_block(name: str, results: list[Result]) -> None:
    # aggregate across rounds using the median
    avg_lat = [statistics.mean(r.latencies_ms) for r in results]
    p50 = [percentile(r.latencies_ms, 50) for r in results]
    p95 = [percentile(r.latencies_ms, 95) for r in results]
    p99 = [percentile(r.latencies_ms, 99) for r in results]
    rps_vals = [r.rps for r in results]

    print(
        f"{name}: "
        f"rounds={len(results)} "
        f"avg={statistics.median(avg_lat):.2f}ms "
        f"p50={statistics.median(p50):.2f}ms "
        f"p95={statistics.median(p95):.2f}ms "
        f"p99={statistics.median(p99):.2f}ms "
        f"rps={statistics.median(rps_vals):.1f}"
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Reliable benchmark for proxy_mock")
    parser.add_argument("--host", default="http://localhost:5000")
    parser.add_argument("--requests", type=int, default=1000)
    parser.add_argument("--concurrency", type=int, default=100)
    parser.add_argument("--warmup", type=int, default=200)
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()

    limits = httpx2.Limits(
        max_connections=args.concurrency,
        max_keepalive_connections=args.concurrency,
    )

    async with httpx2.AsyncClient(base_url=args.host, timeout=args.timeout, limits=limits) as client:
        await prepare_data(client)

        # warmup
        if args.warmup > 0:
            await run_load(client, "GET", "/bench/mock", args.warmup, args.concurrency)
            await run_load(client, "GET", "/traffic", args.warmup, args.concurrency)

        mock_rounds: list[Result] = []
        rules_rounds: list[Result] = []
        traffic_rounds: list[Result] = []

        for i in range(args.rounds):
            await client.post("/traffic/clean")
            round_res = await scenario_round(client, args.requests, args.concurrency)
            mock_rounds.append(round_res["mock"])
            rules_rounds.append(round_res["rules"])
            traffic_rounds.append(round_res["traffic"])
            print(f"round {i + 1}/{args.rounds} done")

        print_result_block("mock", mock_rounds)
        print_result_block("rules", rules_rounds)
        print_result_block("traffic", traffic_rounds)


if __name__ == "__main__":
    asyncio.run(main())

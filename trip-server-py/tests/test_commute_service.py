"""commute_service 单元测试：mock 高德 Direction 与地理编码，覆盖核心逻辑。"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services import commute_service


# ---------------------------------------------------------------------------
# mock 构造
# ---------------------------------------------------------------------------

def _mock_response(json_data: dict) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=json_data)
    return resp


def _make_async_client(get_side_effect) -> AsyncMock:
    client = AsyncMock()
    client.get = AsyncMock(side_effect=get_side_effect)
    cm = AsyncMock()
    cm.__aenter__.return_value = client
    cm.__aexit__.return_value = False
    return cm


def _driving_json(duration: int, distance: int = 5000) -> dict:
    # 真实 v5 结构：polyline 在各 step 中，path 顶层为 None
    return {
        "status": "1",
        "route": {
            "paths": [
                {
                    "distance": str(distance),
                    "cost": {"duration": duration},
                    "steps": [
                        {"polyline": "116.40,39.90;116.41,39.91"},
                        {"polyline": "116.41,39.91;116.42,39.92"},
                    ],
                }
            ]
        },
    }


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _fake_key(monkeypatch):
    # 避免 _direction 因未配置 API Key 而抛错
    monkeypatch.setattr(commute_service.settings, "amap_maps_api_key", "fake_key")


# ---------------------------------------------------------------------------
# 用例
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_driving_ranking_sorts_by_duration():
    origin = {"lat": 39.90, "lng": 116.40}

    def fake_get(url, params):
        dest = params["destination"]
        dur = 300 if dest == "116.42,39.92" else 600
        return _mock_response(_driving_json(dur))

    async_client = _make_async_client(fake_get)

    with patch("src.services.commute_service.httpx.AsyncClient", return_value=async_client), patch(
        "src.services.commute_service.geocode_spot", new=AsyncMock(return_value={"lat": 39.9, "lng": 116.4})
    ):
        result = await commute_service.compute_optimal_commute(
            origin,
            [
                {"name": "A", "lat": 39.91, "lng": 116.41},
                {"name": "B", "lat": 39.92, "lng": 116.42},
            ],
            "driving",
        )

    assert result["mode"] == "driving"
    assert [r["name"] for r in result["results"]] == ["B", "A"]
    assert result["recommended"]["name"] == "B"
    assert result["recommended"]["duration_sec"] == 300
    # polyline 应由各 step 拼接而成（v5 真实结构）
    assert (
        result["recommended"]["polyline"]
        == "116.40,39.90;116.41,39.91;116.41,39.91;116.42,39.92"
    )
    assert result["errors"] == []


@pytest.mark.asyncio
async def test_transit_parses_transfers_and_subway():
    def fake_get(url, params):
        assert params.get("city") == "北京"  # v3 公交用 city（城市名）
        return _mock_response(
            {
                "status": "1",
                "route": {
                    "transits": [
                        {
                            "distance": "8000",
                            "duration": "1200",
                            "segments": [
                                {
                                    "walking": {"steps": [{"polyline": "116.40,39.90;116.41,39.91"}]},
                                    "bus": {
                                        "buslines": [
                                            {"name": "地铁1号线(苹果园--四惠东)"},
                                            {"name": "公交345路"},
                                        ],
                                    },
                                },
                                {
                                    "walking": {"steps": [{"polyline": "116.42,39.92;116.43,39.93"}]},
                                    "bus": {},
                                },  # 2 段 -> 1 次换乘
                            ],
                        }
                    ]
                },
            }
        )

    async_client = _make_async_client(fake_get)

    with patch("src.services.commute_service.httpx.AsyncClient", return_value=async_client), patch(
        "src.services.commute_service.geocode_spot", new=AsyncMock(return_value={"lat": 39.9, "lng": 116.4})
    ):
        result = await commute_service.compute_optimal_commute(
            {"lat": 39.90, "lng": 116.40},
            [{"name": "T", "lat": 39.99, "lng": 116.49}],
            "transit",
            city="北京",
        )

    item = result["results"][0]
    assert item["duration_sec"] == 1200
    assert item["transfers"] == 1
    assert item["has_subway"] is True
    assert len(item["transit_lines"]) == 2
    assert "地铁1号线" in item["transit_lines"][0]
    assert "公交345路" in item["transit_lines"][1]
    # polyline 应由步行段 steps 拼接而成
    assert item["polyline"] == "116.40,39.90;116.41,39.91;116.42,39.92;116.43,39.93"


@pytest.mark.asyncio
async def test_transit_auto_derives_city_when_missing():
    """transit 未传 city 时，应由起点反查城市再调用 v3 公交。"""
    state = {"regeo_called": False}

    def fake_get(url, params):
        if "regeo" in url:
            state["regeo_called"] = True
            return _mock_response(
                {
                    "status": "1",
                    "regeocode": {
                        "addressComponent": {"city": "南昌市", "province": "江西省"}
                    },
                }
            )
        # transit 请求：city 应被反查为「南昌」
        assert params.get("city") == "南昌"
        return _mock_response(
            {
                "status": "1",
                "route": {
                    "transits": [
                        {"distance": "5000", "duration": "900", "segments": [{}, {}]}
                    ]
                },
            }
        )

    async_client = _make_async_client(fake_get)

    with patch("src.services.commute_service.httpx.AsyncClient", return_value=async_client), patch(
        "src.services.commute_service.geocode_spot", new=AsyncMock(return_value={"lat": 39.9, "lng": 116.4})
    ):
        result = await commute_service.compute_optimal_commute(
            {"lat": 28.708, "lng": 115.876},
            [{"name": "P", "lat": 28.72, "lng": 115.89}],
            "transit",
            city=None,
        )

    assert state["regeo_called"] is True
    assert result["errors"] == []
    assert result["results"][0]["duration_sec"] == 900


@pytest.mark.asyncio
async def test_geocode_fallback_when_no_coords():
    captured = {}

    def fake_get(url, params):
        captured["dest"] = params["destination"]
        return _mock_response(_driving_json(500))

    async_client = _make_async_client(fake_get)

    with patch("src.services.commute_service.httpx.AsyncClient", return_value=async_client), patch(
        "src.services.commute_service.geocode_spot",
        new=AsyncMock(return_value={"lat": 31.23, "lng": 121.47}),
    ):
        result = await commute_service.compute_optimal_commute(
            {"lat": 31.22, "lng": 121.48},
            [{"name": "外滩", "city": "上海"}],  # 无坐标，需地理编码
            "walking",
        )

    assert result["results"][0]["name"] == "外滩"
    assert captured["dest"] == "121.47,31.23"  # 地理编码得到的坐标被使用


@pytest.mark.asyncio
async def test_partial_failure_isolated():
    async_client = _make_async_client(lambda url, params: _mock_response(_driving_json(400)))

    with patch("src.services.commute_service.httpx.AsyncClient", return_value=async_client), patch(
        "src.services.commute_service.geocode_spot", new=AsyncMock(return_value=None)  # 地理编码失败
    ):
        result = await commute_service.compute_optimal_commute(
            {"lat": 39.90, "lng": 116.40},
            [
                {"name": "无坐标无城市"},  # 解析失败 -> error
                {"name": "OK", "lat": 39.91, "lng": 116.41},  # 成功
            ],
            "driving",
        )

    assert len(result["results"]) == 1
    assert result["results"][0]["name"] == "OK"
    assert len(result["errors"]) == 1
    assert result["errors"][0]["name"] == "无坐标无城市"


@pytest.mark.asyncio
async def test_all_failed_recommended_none():
    async_client = _make_async_client(lambda url, params: _mock_response(_driving_json(400)))

    with patch("src.services.commute_service.httpx.AsyncClient", return_value=async_client), patch(
        "src.services.commute_service.geocode_spot", new=AsyncMock(return_value=None)
    ):
        result = await commute_service.compute_optimal_commute(
            {"lat": 39.90, "lng": 116.40},
            [{"name": "X"}, {"name": "Y"}],
            "driving",
        )

    assert result["recommended"] is None
    assert len(result["errors"]) == 2


@pytest.mark.asyncio
async def test_invalid_mode_raises():
    with pytest.raises(ValueError):
        await commute_service.compute_optimal_commute(
            {"lat": 39.90, "lng": 116.40}, [{"name": "A", "lat": 1, "lng": 2}], "flying"
        )

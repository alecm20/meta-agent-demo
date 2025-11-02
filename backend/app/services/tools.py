from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any, Protocol
import httpx
from ..core.config import get_settings
from ..models.agent import ToolConfig, ToolName


class ToolExecutionError(Exception):
    """Raised when a tool fails to execute."""


class Tool(Protocol):
    name: ToolName
    description: str

    async def run(self, query: str) -> str:
        """Execute the tool with the provided query."""


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        return lowered in {"1", "true", "yes", "y", "on"}
    return bool(value)


def validate_and_normalize_parameters(tool_name: ToolName, params: dict[str, Any] | None) -> dict[str, Any]:
    """Validate and normalize tool parameters against simple schemas.

    - Strips unknown keys
    - Coerces types where safe
    - Applies defaults
    """
    params = dict(params or {})
    if tool_name is ToolName.calculator:
        # Calculator currently has no parameters; drop any extras
        return {}
    if tool_name is ToolName.web_search:
        allowed = {"auto_search", "strategy", "search_params"}
        normalized: dict[str, Any] = {}
        if "auto_search" in params:
            normalized["auto_search"] = _coerce_bool(params.get("auto_search"))
        if "strategy" in params:
            val = params.get("strategy")
            if isinstance(val, str):
                normalized["strategy"] = val.strip()[:64]
        if "search_params" in params:
            sp = params.get("search_params")
            if isinstance(sp, dict):
                # keep only simple JSON-serializable primitives
                filtered: dict[str, Any] = {}
                for k, v in sp.items():
                    if isinstance(k, str) and isinstance(v, (str, int, float, bool)):
                        filtered[k] = v
                if filtered:
                    normalized["search_params"] = filtered
        # defaults
        if "auto_search" not in normalized:
            normalized["auto_search"] = False
        return normalized
    if tool_name is ToolName.amap_weather:
        normalized: dict[str, Any] = {}
        mode = (params or {}).get("mode")
        if isinstance(mode, str) and mode.lower() in {"live", "forecast"}:
            normalized["mode"] = mode.lower()
        else:
            normalized["mode"] = "live"
        return normalized
    # Unknown tool: return empty
    return {}


@dataclass
class CalculatorTool:
    name: ToolName = ToolName.calculator
    description: str = "Evaluate arithmetic expressions with +, -, *, /, and parentheses."

    async def run(self, query: str) -> str:
        expression = query.strip()
        if not expression:
            raise ToolExecutionError("Calculator received an empty expression")

        try:
            node = ast.parse(expression, mode="eval")
            value = _eval_ast(node.body)
        except ToolExecutionError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ToolExecutionError(f"Invalid mathematical expression: {expression}") from exc
        return str(value)


@dataclass
class GoogleSearchTool:
    parameters: dict[str, Any] = field(default_factory=dict)
    name: ToolName = ToolName.web_search
    description: str = "调用 Google Programmable Search 获取实时网页信息摘要。"

    async def run(self, query: str) -> str:
        cleaned_query = query.strip()
        if not cleaned_query:
            raise ToolExecutionError("Web search query cannot be empty")

        settings = get_settings()
        api_key = settings.google_search_api_key
        cx = settings.google_search_cx
        if not api_key or not cx:
            raise ToolExecutionError("Google Search API key or CX is not configured.")

        params = {
            "key": api_key,
            "cx": cx,
            "q": cleaned_query,
            "num": 3,
            "safe": "active",
            "hl": "zh-CN",
        }
        extra_params = self.parameters.get("search_params") or {}
        params.update(extra_params)

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                response = await client.get(
                    "https://www.googleapis.com/customsearch/v1", params=params
                )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ToolExecutionError(
                f"Google search failed with status {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except httpx.RequestError as exc:
            raise ToolExecutionError(f"Google search request error: {exc}") from exc

        data = response.json()
        items = data.get("items") or []
        if not items:
            return "Google 搜索未返回结果，请尝试调整关键词。"

        results: list[str] = []
        for item in items:
            title = item.get("title") or "未命名结果"
            snippet = (item.get("snippet") or "").replace("\n", " ")
            link = item.get("link") or ""
            results.append(f"{title}\n{snippet}\n来源: {link}")
        return "\n\n".join(results)


@dataclass
class AmapWeatherTool:
    parameters: dict[str, Any] = field(default_factory=dict)
    name: ToolName = ToolName.amap_weather
    description: str = "查询指定城市的实时或预报天气（高德 Web API）。"

    async def run(self, query: str) -> str:
        city_query = (query or "").strip()
        if not city_query:
            raise ToolExecutionError("Weather query requires a city name, e.g., '上海' or 'Beijing'.")

        settings = get_settings()
        api_key = settings.amap_api_key
        if not api_key:
            raise ToolExecutionError("AMAP_API_KEY is not configured.")

        mode = (self.parameters.get("mode") or "live").lower()
        if mode not in {"live", "forecast"}:
            mode = "live"

        # Step 1: resolve city adcode via district API
        district_params = {
            "key": api_key,
            "keywords": city_query,
            "subdistrict": 0,
        }
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                d_resp = await client.get("https://restapi.amap.com/v3/config/district", params=district_params)
            d_resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ToolExecutionError(
                f"AMap district lookup failed with status {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except httpx.RequestError as exc:
            raise ToolExecutionError(f"AMap district lookup request error: {exc}") from exc

        d_data = d_resp.json()
        status = d_data.get("status")
        districts = (d_data.get("districts") or [])
        if status != "1" or not districts:
            raise ToolExecutionError("未能解析城市编码，请检查城市名称是否正确。")
        adcode = districts[0].get("adcode") or districts[0].get("citycode")
        name = districts[0].get("name") or city_query
        if not adcode:
            raise ToolExecutionError("未能获取城市编码（adcode）。")

        # Step 2: weather by city adcode
        extensions = "base" if mode == "live" else "all"
        weather_params = {
            "key": api_key,
            "city": adcode,
            "extensions": extensions,
        }
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                w_resp = await client.get("https://restapi.amap.com/v3/weather/weatherInfo", params=weather_params)
            w_resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ToolExecutionError(
                f"AMap weather failed with status {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except httpx.RequestError as exc:
            raise ToolExecutionError(f"AMap weather request error: {exc}") from exc

        w_data = w_resp.json()
        if mode == "live":
            lives = w_data.get("lives") or []
            if not lives:
                return f"{name} 的实时天气暂无数据。"
            live = lives[0]
            weather = live.get("weather")
            temp = live.get("temperature")
            wind = f"{live.get('winddirection')}风 {live.get('windpower')}级"
            humidity = live.get("humidity")
            report = live.get("reporttime")
            return f"{name} 实时天气：{weather}，{temp}℃，{wind}，湿度{humidity}%。更新时间：{report}"
        else:
            forecasts = w_data.get("forecasts") or []
            if not forecasts:
                return f"{name} 的预报天气暂无数据。"
            cast = forecasts[0]
            days = cast.get("casts") or []
            lines: list[str] = [f"{name} 天气预报（未来{len(days)}天）："]
            for d in days:
                date = d.get("date")
                day_w = d.get("dayweather")
                day_t = d.get("daytemp")
                night_w = d.get("nightweather")
                night_t = d.get("nighttemp")
                lines.append(f"{date} 白天{day_w} {day_t}℃ / 夜间{night_w} {night_t}℃")
            return "\n".join(lines)


class ToolBox:
    """Factory that wires requested tools into executable objects."""

    def __init__(self, tool_configs: list[ToolConfig]):
        self._tools: dict[ToolName, Tool] = {}
        for config in tool_configs:
            tool = self._instantiate_tool(config)
            self._tools[tool.name] = tool

    def _instantiate_tool(self, config: ToolConfig) -> Tool:
        if config.name is ToolName.calculator:
            return CalculatorTool()
        if config.name is ToolName.web_search:
            normalized = validate_and_normalize_parameters(config.name, config.parameters)
            return GoogleSearchTool(parameters=normalized)
        if config.name is ToolName.amap_weather:
            normalized = validate_and_normalize_parameters(config.name, config.parameters)
            return AmapWeatherTool(parameters=normalized)
        raise ValueError(f"Unsupported tool: {config.name}")

    async def run(self, tool_name: ToolName, query: str) -> str:
        tool = self._tools.get(tool_name)
        if tool is None:
            raise ToolExecutionError(f"Tool '{tool_name}' is not available for this agent")
        return await tool.run(query)

    @property
    def available_tool_names(self) -> list[ToolName]:
        return list(self._tools.keys())


def _eval_ast(node: ast.AST) -> float:
    if isinstance(node, ast.BinOp):
        left = _eval_ast(node.left)
        right = _eval_ast(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.Pow):
            raise ToolExecutionError("Exponentiation is not allowed for safety reasons")
        raise ToolExecutionError(f"Unsupported operator: {type(node.op).__name__}")

    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        operand = _eval_ast(node.operand)
        return operand if isinstance(node.op, ast.UAdd) else -operand

    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)

    if isinstance(node, ast.Expr):
        return _eval_ast(node.value)

    raise ToolExecutionError(f"Unsupported expression: {ast.dump(node)}")

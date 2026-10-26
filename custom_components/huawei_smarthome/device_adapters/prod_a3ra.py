"""User-contributed protocol for Huawei product A3RA (美的挂机空调 KFR-35GW/N8HL1XPro).

设备类型: 挂机空调 (On Hook Air Conditioner), 型号 KFR-35GW/N8HL1XPro
制造商: 美的 (midea), 接入方式: CLOUD

五个核心服务全部 RW, 整合为一个 climate 实体:

  switch.on             bool RW    电源           -> turn_on / turn_off
  mode.mode             enum RW    1自动/2制冷/3制热/4送风/5抽湿  -> hvac_mode
  fan.gear              enum RW    0自动/2低风/3中风/4高风/5强劲风 -> fan_mode
  fan.direction         enum RW    1停止/2左右/3上下/4全面          -> swing_mode
  temperature.target    float RW   17.0~30.0, step 1.0            -> target_temperature

已暴露 (9 个实体):

  climate (1):       空调  (电源+模式+风速+摆风+温度)
  binary_sensor (1): 故障  (commonFaultDetection.status)
  sensor (7):        故障码 / 故障信息 /
                     信号强度 / 信号等级 / Wi-Fi 名称 / IP / BSSID

故意不暴露:
  update.*           OTA

关于 current_temperature / hvac_action:

  Profile 没有 temperature.current (当前室温) 和运行状态字段, 所以
  climate 的 current_temperature 和 hvac_action 返回 None. HA 卡片会
  把当前温度显示为 "--", 这是设备能力的限制, 不是适配器问题.

关于 hvac_modes 的映射:

  HVACMode.AUTO     <- 1 自动
  HVACMode.COOL     <- 2 制冷
  HVACMode.HEAT     <- 3 制热
  HVACMode.FAN_ONLY <- 4 送风
  HVACMode.DRY      <- 5 抽湿

  fan_mode / swing_mode 直接使用 Profile 的中文标签作为选项字符串,
  用户在卡片里看到的就是 "低风" / "左右摆风" 这类文本.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.components.climate import HVACMode

from .api import EntitySpec
from .context import DeviceContext


# ---- Profile 工具函数 ----------------------------------------------------

def _service(profile: Any, sid: str) -> Any:
    if profile is None:
        return None
    for service in profile.get("services", ()):
        if service.get("serviceId") == sid:
            return service
    return None


def _field(profile: Any, sid: str, name: str) -> Mapping[str, Any] | None:
    service = _service(profile, sid)
    if service is None:
        return None
    for characteristic in service.get("characteristics", ()):
        if characteristic.get("characteristicName") == name:
            return characteristic
    return None


# ---- 值转换 --------------------------------------------------------------

def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        token = value.strip().casefold()
        if token in {"1", "true", "on"}:
            return True
        if token in {"0", "false", "off"}:
            return False
        return None
    if isinstance(value, (int, float)):
        if value == 1:
            return True
        if value == 0:
            return False
        return None
    return None


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        return value or None
    return str(value)


def _enum_label(value: Any, options: tuple[tuple[int, str], ...]) -> str | None:
    number = _number(value)
    if number is None:
        return None
    for enum_value, label in options:
        if number == enum_value:
            return label
    return None


# ---- 枚举选项 (来自 Profile enumList, 权威) ------------------------------

_FAN_GEAR_OPTIONS: tuple[tuple[int, str], ...] = (
    (0, "自动"),
    (2, "低风"),
    (3, "中风"),
    (4, "高风"),
    (5, "强劲风"),
)
_FAN_DIRECTION_OPTIONS: tuple[tuple[int, str], ...] = (
    (1, "停止摆风"),
    (2, "左右摆风"),
    (3, "上下摆风"),
    (4, "全面摆风"),
)
_FAULT_CODE_OPTIONS: tuple[tuple[int, str], ...] = (
    (0, "正常"),
    (1, "检测到故障"),
)
_NET_INTENSITY_OPTIONS: tuple[tuple[int, str], ...] = (
    (20, "0格信号"),
    (40, "1格信号"),
    (60, "2格信号"),
    (80, "3格信号"),
    (100, "4格信号"),
)

# HVACMode <-> Profile mode.mode enum
_ENUM_TO_HVAC_MODE: dict[int, HVACMode] = {
    1: HVACMode.AUTO,
    2: HVACMode.COOL,
    3: HVACMode.HEAT,
    4: HVACMode.FAN_ONLY,
    5: HVACMode.DRY,
}
_HVAC_MODE_TO_ENUM: dict[str, int] = {
    hvac.value: enum_value for enum_value, hvac in _ENUM_TO_HVAC_MODE.items()
}
_HVAC_MODES: tuple[HVACMode, ...] = tuple(_ENUM_TO_HVAC_MODE.values())
_FAN_MODES: tuple[str, ...] = tuple(label for _, label in _FAN_GEAR_OPTIONS)
_SWING_MODES: tuple[str, ...] = tuple(label for _, label in _FAN_DIRECTION_OPTIONS)


# ---- climate actions -----------------------------------------------------

async def _set_hvac_mode(context: DeviceContext, data: Mapping[str, Any]) -> None:
    hvac_mode = data.get("hvac_mode")
    if hvac_mode is None:
        return
    key = hvac_mode.value if isinstance(hvac_mode, HVACMode) else str(hvac_mode)
    enum_value = _HVAC_MODE_TO_ENUM.get(key)
    if enum_value is None:
        return
    await context.async_send_service("mode", {"mode": enum_value})


async def _set_fan_mode(context: DeviceContext, data: Mapping[str, Any]) -> None:
    fan_mode = data.get("fan_mode")
    if not isinstance(fan_mode, str):
        return
    lookup = {label: value for value, label in _FAN_GEAR_OPTIONS}
    enum_value = lookup.get(fan_mode)
    if enum_value is None:
        return
    await context.async_send_service("fan", {"gear": enum_value})


async def _set_swing_mode(context: DeviceContext, data: Mapping[str, Any]) -> None:
    swing_mode = data.get("swing_mode")
    if not isinstance(swing_mode, str):
        return
    lookup = {label: value for value, label in _FAN_DIRECTION_OPTIONS}
    enum_value = lookup.get(swing_mode)
    if enum_value is None:
        return
    await context.async_send_service("fan", {"direction": enum_value})


async def _set_temperature(context: DeviceContext, data: Mapping[str, Any]) -> None:
    temperature = data.get("temperature")
    value = _number(temperature)
    if value is None:
        return
    await context.async_send_service("temperature", {"target": value})


async def _turn_on(context: DeviceContext, _data: Mapping[str, Any]) -> None:
    await context.async_send_service("switch", {"on": 1})


async def _turn_off(context: DeviceContext, _data: Mapping[str, Any]) -> None:
    await context.async_send_service("switch", {"on": 0})


# ---- climate state ------------------------------------------------------

def _climate_state(context: DeviceContext) -> Mapping[str, Any]:
    mode_value = _number(context.value("mode", "mode"))
    hvac_mode = (
        _ENUM_TO_HVAC_MODE.get(int(mode_value))
        if mode_value is not None
        else None
    )
    return {
        "hvac_mode": hvac_mode,
        "fan_mode": _enum_label(
            context.value("fan", "gear"), _FAN_GEAR_OPTIONS
        ),
        "swing_mode": _enum_label(
            context.value("fan", "direction"), _FAN_DIRECTION_OPTIONS
        ),
        "target_temperature": _number(
            context.value("temperature", "target")
        ),
        "current_temperature": None,
        "hvac_action": None,
    }


# ---- netInfo 诊断实体 --------------------------------------------------

def _net_info_entities(profile: Any) -> list[EntitySpec]:
    if _service(profile, "netInfo") is None:
        return []
    entities: list[EntitySpec] = []

    if _field(profile, "netInfo", "RSSI") is not None:
        entities.append(EntitySpec(
            platform="sensor",
            key="wifi_rssi",
            name="信号强度",
            state=lambda ctx: {"native_value": _number(ctx.value("netInfo", "RSSI"))},
            metadata={
                "state_class": "measurement",
                "unit": "dBm",
                "entity_category": "diagnostic",
            },
        ))

    if _field(profile, "netInfo", "intensity") is not None:
        entities.append(EntitySpec(
            platform="sensor",
            key="wifi_level",
            name="信号等级",
            state=lambda ctx: {
                "native_value": _enum_label(
                    ctx.value("netInfo", "intensity"), _NET_INTENSITY_OPTIONS
                )
            },
            metadata={"entity_category": "diagnostic"},
        ))

    for field_name, key, label in (
        ("SSID", "wifi_ssid", "Wi-Fi 名称"),
        ("IP", "wifi_ip", "IP 地址"),
        ("BSSID", "wifi_bssid", "BSSID"),
    ):
        if _field(profile, "netInfo", field_name) is None:
            continue
        entities.append(EntitySpec(
            platform="sensor",
            key=key,
            name=label,
            state=lambda ctx, _f=field_name: {
                "native_value": _text(ctx.value("netInfo", _f))
            },
            metadata={"entity_category": "diagnostic"},
        ))

    return entities


# ---- 适配器 ------------------------------------------------------------

class ProductA3RAAdapter:
    """美的挂机空调 KFR-35GW/N8HL1XPro (A3RA) 适配器."""

    prod_id = "A3RA"

    def entities(self, context: DeviceContext) -> tuple[EntitySpec, ...]:
        profile = context.profile
        if profile is None:
            return ()

        entities: list[EntitySpec] = []

        # --- climate: 电源 / 模式 / 风速 / 摆风 / 温度 -------------------
        if (
            context.has_service("switch")
            and _field(profile, "switch", "on") is not None
            and context.has_service("mode")
            and _field(profile, "mode", "mode") is not None
            and context.has_service("fan")
            and _field(profile, "fan", "gear") is not None
            and _field(profile, "fan", "direction") is not None
            and context.has_service("temperature")
            and _field(profile, "temperature", "target") is not None
        ):
            entities.append(EntitySpec(
                platform="climate",
                key="air_conditioner",
                name="空调",
                state=_climate_state,
                actions={
                    "set_hvac_mode": _set_hvac_mode,
                    "set_fan_mode": _set_fan_mode,
                    "set_swing_mode": _set_swing_mode,
                    "set_temperature": _set_temperature,
                    "turn_on": _turn_on,
                    "turn_off": _turn_off,
                },
                metadata={
                    "hvac_modes": list(_HVAC_MODES),
                    "fan_modes": list(_FAN_MODES),
                    "swing_modes": list(_SWING_MODES),
                    "min_temp": 17.0,
                    "max_temp": 30.0,
                },
            ))

        # --- commonFaultDetection.status -> binary_sensor 故障 ----------
        if context.has_service("commonFaultDetection") and _field(
            profile, "commonFaultDetection", "status"
        ) is not None:
            entities.append(EntitySpec(
                platform="binary_sensor",
                key="fault",
                name="故障",
                state=lambda ctx: {
                    "is_on": _as_bool(
                        ctx.value("commonFaultDetection", "status")
                    )
                },
                metadata={"device_class": "problem"},
            ))

        # --- commonFaultDetection.code -> sensor 故障码 -----------------
        if context.has_service("commonFaultDetection") and _field(
            profile, "commonFaultDetection", "code"
        ) is not None:
            entities.append(EntitySpec(
                platform="sensor",
                key="fault_code",
                name="故障码",
                state=lambda ctx: {
                    "native_value": _enum_label(
                        ctx.value("commonFaultDetection", "code"),
                        _FAULT_CODE_OPTIONS,
                    )
                },
                metadata={"entity_category": "diagnostic"},
            ))

        # --- commonFaultDetection.message -> sensor 故障信息 ------------
        if context.has_service("commonFaultDetection") and _field(
            profile, "commonFaultDetection", "message"
        ) is not None:
            entities.append(EntitySpec(
                platform="sensor",
                key="fault_message",
                name="故障信息",
                state=lambda ctx: {
                    "native_value": _text(
                        ctx.value("commonFaultDetection", "message")
                    )
                },
                metadata={"entity_category": "diagnostic"},
            ))

        # --- netInfo 诊断 ------------------------------------------------
        entities.extend(_net_info_entities(profile))

        return tuple(entities)


ADAPTER = ProductA3RAAdapter()
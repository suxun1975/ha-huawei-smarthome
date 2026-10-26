"""User-contributed protocol for Huawei product 2196 (圆和三路智能开关 X9ZK3).

设备类型: 智能开关 (Smart Switch), 型号 X9ZK3
制造商: 鼎力 (DLTN)

4 个开关服务:
  switch.on   -> switch "总开关"  (quickmenu 引用的主控)
  switch1.on  -> switch "回路1"
  switch2.on  -> switch "回路2"
  switch3.on  -> switch "回路3"

switch1-3 额外带 name 字段 (插口名称, 设备侧配置标签). 不暴露为实体:
它是设备侧的命名元数据, 不是状态; HA 侧用户用实体重命名即可. 这与
2MJD 的 customKey.name* 取舍一致.

netInfo.* 暴露为 6 个诊断 sensor.

故意不暴露:
  timer.* / delay.*   array[object], 需要专用定时器/倒计时 UI
  update.*            OTA
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

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
    """严格解析 bool: 只接受 0/1 及等价字符串/布尔, 其它返回 None."""
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


# ---- 枚举选项 ----------------------------------------------------------

_NET_INTENSITY_OPTIONS: tuple[tuple[int, str], ...] = (
    (20, "0格信号"),
    (40, "1格信号"),
    (60, "2格信号"),
    (80, "3格信号"),
    (100, "4格信号"),
)


# ---- 写动作工厂 --------------------------------------------------------

def _power_on(sid: str):
    async def _action(ctx: DeviceContext, _data: Mapping[str, Any]) -> None:
        await ctx.async_send_service(sid, {"on": 1})
    return _action


def _power_off(sid: str):
    async def _action(ctx: DeviceContext, _data: Mapping[str, Any]) -> None:
        await ctx.async_send_service(sid, {"on": 0})
    return _action


# ---- 开关定义 ----------------------------------------------------------

# (sid, key, name)
_SWITCHES: tuple[tuple[str, str, str], ...] = (
    ("switch",  "master",    "总开关"),
    ("switch1", "circuit_1", "回路1"),
    ("switch2", "circuit_2", "回路2"),
    ("switch3", "circuit_3", "回路3"),
)


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

class Product2196Adapter:
    """圆和三路智能开关 X9ZK3 (2196) 适配器."""

    prod_id = "2196"

    def entities(self, context: DeviceContext) -> tuple[EntitySpec, ...]:
        profile = context.profile
        if profile is None:
            return ()

        entities: list[EntitySpec] = []

        for sid, key, name in _SWITCHES:
            if not context.has_service(sid):
                continue
            if _field(profile, sid, "on") is None:
                continue
            entities.append(EntitySpec(
                platform="switch",
                key=key,
                name=name,
                state=lambda ctx, _s=sid: {
                    "is_on": _as_bool(ctx.value(_s, "on"))
                },
                actions={
                    "turn_on": _power_on(sid),
                    "turn_off": _power_off(sid),
                },
            ))

        entities.extend(_net_info_entities(profile))
        return tuple(entities)


ADAPTER = Product2196Adapter()
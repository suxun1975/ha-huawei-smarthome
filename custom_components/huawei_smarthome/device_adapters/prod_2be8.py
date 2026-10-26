"""Product adapter for the MIR-TE100 temperature/humidity sensor (2BE8, Mesh).

Profile: temperature.{current int -100..450, unit ""} /
humidity.{current int 0..100, unit ""} /
battery.{level 0..100, alarm bool}.

No netInfo, no update, no commonFaultDetection in this Profile.

Scaling: the declared ranges look like tenths (-100..450), but the sibling
product 2GB1 (same deviceModel MIR-TE100, same manufacturer, verified against
live hardware) proves the values are reported as-is: temperature.current=38
means 38 °C, humidity.current=33 means 33 %RH.  Values are therefore used
unscaled here too.

Not exposed (宁可不出): temperature.level / humidity.level comfort enums
(device-derived labels duplicating the measured value, opaque thresholds on
the HA side).

Unit: "°C" (U+00B0 + "C"), not "℃" (U+2103).  The sibling 2GB1 adapter uses
"℃", which Home Assistant rejects for SensorDeviceClass.TEMPERATURE and logs
a warning on every entity update.
"""

from __future__ import annotations

from typing import Any, Mapping

from .api import EntitySpec
from .context import DeviceContext


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


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _flag_value(value: Any) -> bool | None:
    """严格解析 bool: 接受 0/1, 字符串 "0"/"1"/"true"/"false"/"on"/"off",
    以及 JSON 布尔 true/false, 其它返回 None.

    这是 2BE8 的 battery.alarm 字段的解析函数. 与 2BE5 / 2BE6 的
    _flag_value 命名和实现完全一致, 三个麦乐克门磁系列适配器风格统一.

    旧版用 int(str(raw).strip()) 转换:
      - "1" / "0" -> 能解析
      - "true" / "false" / "on" / "off" -> int() 抛 ValueError, 返回 None
      - 如果设备上报字符串 "true" (虽然 characteristicType 是 bool,
        但实际协议可能用字符串), battery.alarm 会显示 unknown
    本版用 token 匹配, 兼容所有常见布尔表示.
    """
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


class Product2BE8Adapter:
    """MIR-TE100 temperature/humidity sensor (2BE8)."""

    prod_id = "2BE8"

    def entities(self, context: DeviceContext) -> tuple[EntitySpec, ...]:
        profile = context.profile
        if profile is None:
            return ()

        entities: list[EntitySpec] = []

        if context.has_service("temperature") and _field(
            profile, "temperature", "current"
        ) is not None:
            entities.append(
                EntitySpec(
                    platform="sensor",
                    key="temperature",
                    name="温度",
                    state=lambda ctx: {
                        "native_value": _number(ctx.value("temperature", "current"))
                    },
                    metadata={
                        "device_class": "temperature",
                        "state_class": "measurement",
                        "unit": "°C",
                    },
                )
            )

        if context.has_service("humidity") and _field(
            profile, "humidity", "current"
        ) is not None:
            entities.append(
                EntitySpec(
                    platform="sensor",
                    key="humidity",
                    name="湿度",
                    state=lambda ctx: {
                        "native_value": _number(ctx.value("humidity", "current"))
                    },
                    metadata={
                        "device_class": "humidity",
                        "state_class": "measurement",
                        "unit": "%",
                    },
                )
            )

        if context.has_service("battery") and _field(
            profile, "battery", "level"
        ) is not None:
            entities.append(
                EntitySpec(
                    platform="sensor",
                    key="battery_level",
                    name="电池电量",
                    state=lambda ctx: {
                        "native_value": _number(ctx.value("battery", "level"))
                    },
                    metadata={
                        "device_class": "battery",
                        "state_class": "measurement",
                        "unit": "%",
                    },
                )
            )

        if context.has_service("battery") and _field(
            profile, "battery", "alarm"
        ) is not None:
            entities.append(
                EntitySpec(
                    platform="binary_sensor",
                    key="battery_low",
                    name="低电量告警",
                    state=lambda ctx: {
                        "is_on": _flag_value(ctx.value("battery", "alarm"))
                    },
                    metadata={"device_class": "battery"},
                )
            )

        return tuple(entities)


ADAPTER = Product2BE8Adapter()
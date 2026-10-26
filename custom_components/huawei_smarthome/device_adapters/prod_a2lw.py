"""User-contributed protocol for Huawei product A2LW (酷宅科技温湿度传感器 TH Sensor).

设备类型: 温湿度传感器 (Temperature And Humidity Detector), 型号 TH Sensor
制造商: 酷宅科技 (CoolKit / eWeLink), 接入方式: CLOUD

Profile 只有四个服务:

  temperature.current  int R -100..400 unit ℃   温度
  humidity.current     int R 0..1000   unit %   湿度
  update.*             混合                       OTA, 不暴露
  netInfo.*            R                         诊断, 暴露 5 个 sensor

已暴露 (7 个实体):

  sensor (2):    温度  <- temperature.current  (°C)
                 湿度  <- humidity.current     (%)
  sensor (5):    信号强度 / 信号等级 / Wi-Fi 名称 / IP / BSSID
                 <- netInfo.*, diagnostic

关于缩放:

  temperature.current 的 range 是 -100..400, humidity.current 是
  0..1000, 看起来像"十分之一" (即 -10.0..40.0℃ / 0.0..100.0%RH).

  但是同 deviceTypeId 04E 的 2GB1 (麦乐克 MIR-TE100) Profile 里
  temperature 的 range 是 -100..400, humidity 是 0..1000, 而 2GB1
  的 prod_2gb1.py 注释明确写了真机读数 disprove 十分之一:

    temperature.current=38 -> 38 ℃ (不是 3.8 ℃)
    humidity.current=33    -> 33 %RH (不是 3.3 %RH)

  所以 A2LW 大概率也是原值不缩放. 默认 _TEMPERATURE_SCALE 和
  _HUMIDITY_SCALE 都是 1.0, 与 2GB1 对齐.

  如果实测发现温度显示 380 而不是 38, 把 _TEMPERATURE_SCALE 改成
  10.0; 湿度同理. 只改常量, 不改逻辑.

关于单位 "℃" (U+2103):

  Profile 里 temperature 的 unit 是 "℃" (U+2103), HA 的
  SensorDeviceClass.TEMPERATURE 只接受 "°C" (U+00B0 + "C"),
  用 "℃" 会触发 "native unit not valid" 警告. 所以适配器里
  用 "°C" 而不是 "℃". 这与 prod_2be8.py 的处理一致.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .api import EntitySpec
from .context import DeviceContext


# ---- 缩放常量 (如果实测值与预期差 10 倍, 改成 10.0) ----------------------

_TEMPERATURE_SCALE = 1.0
_HUMIDITY_SCALE = 1.0


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


def _scaled(value: Any, scale: float) -> float | None:
    number = _number(value)
    if number is None or scale == 0:
        return None
    if scale == 1.0:
        return number
    return round(number / scale, 1)


# ---- 枚举选项 ----------------------------------------------------------

_NET_INTENSITY_OPTIONS: tuple[tuple[int, str], ...] = (
    (20, "0格信号"),
    (40, "1格信号"),
    (60, "2格信号"),
    (80, "3格信号"),
    (100, "4格信号"),
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

class ProductA2LWAdapter:
    """酷宅科技温湿度传感器 TH Sensor (A2LW) 适配器."""

    prod_id = "A2LW"

    def entities(self, context: DeviceContext) -> tuple[EntitySpec, ...]:
        profile = context.profile
        if profile is None:
            return ()

        entities: list[EntitySpec] = []

        # --- temperature.current -> sensor 温度 -------------------------
        if context.has_service("temperature") and _field(
            profile, "temperature", "current"
        ) is not None:
            entities.append(EntitySpec(
                platform="sensor",
                key="temperature",
                name="温度",
                state=lambda ctx: {
                    "native_value": _scaled(
                        ctx.value("temperature", "current"),
                        _TEMPERATURE_SCALE,
                    )
                },
                metadata={
                    "device_class": "temperature",
                    "state_class": "measurement",
                    "unit": "°C",
                },
            ))

        # --- humidity.current -> sensor 湿度 ----------------------------
        if context.has_service("humidity") and _field(
            profile, "humidity", "current"
        ) is not None:
            entities.append(EntitySpec(
                platform="sensor",
                key="humidity",
                name="湿度",
                state=lambda ctx: {
                    "native_value": _scaled(
                        ctx.value("humidity", "current"),
                        _HUMIDITY_SCALE,
                    )
                },
                metadata={
                    "device_class": "humidity",
                    "state_class": "measurement",
                    "unit": "%",
                },
            ))

        # --- netInfo 诊断 ------------------------------------------------
        entities.extend(_net_info_entities(profile))

        return tuple(entities)


ADAPTER = ProductA2LWAdapter()
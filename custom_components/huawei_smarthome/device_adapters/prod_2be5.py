"""User-contributed protocol for Huawei product 2BE5 (麦乐克门窗开关传感器 MIR-MC100).

设备类型: 门磁 (Magnetic Switch), 型号 MIR-MC100
制造商: 麦乐克 (Multi IR), 协议: Mesh

Profile 的服务:

  doorEvent.on          bool R+GR   0 关闭 / 1 打开   (事件, 会上报)
  status.status         enum R      0 关闭 / 1 打开   (持续状态)
  battery.{alarm,level} R+GR        低电量告警 / 电量百分比
  temperAlarm.alarm     enum R+GR   0 关闭 / 1 打开   (防拆警报)
  netInfo.*             R+GR        WiFi 诊断
  update.*              OTA         不暴露

已暴露 (10 个实体):

  event (1):          门事件      <- doorEvent.on
                       event_types: opened / closed
                       device_class: door
                       每次开/关门都触发, 不受"值没变不触发"限制

  binary_sensor (3):  门窗        <- status.status    (door)
                      低电量告警  <- battery.alarm    (battery)
                      防拆警报    <- temperAlarm.alarm (tamper)

  sensor (6):         电池电量    <- battery.level    (%)
                      信号强度    <- netInfo.RSSI     (diagnostic)
                      信号等级    <- netInfo.intensity (diagnostic)
                      Wi-Fi 名称  <- netInfo.SSID     (diagnostic)
                      IP 地址     <- netInfo.IP       (diagnostic)
                      BSSID       <- netInfo.BSSID    (diagnostic)

故意不暴露:

  update.*   OTA

"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
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


def _flag_value(value: Any) -> bool | None:

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


# ---- 枚举选项 ----------------------------------------------------------

_NET_INTENSITY_OPTIONS: tuple[tuple[int, str], ...] = (
    (20, "0格信号"),
    (40, "1格信号"),
    (60, "2格信号"),
    (80, "3格信号"),
    (100, "4格信号"),
)


# ---- event decoder ------------------------------------------------------

def _door_event_decoder(
    _context: DeviceContext,
    sid: str,
    data: Mapping[str, Any],
    _timestamp: str | None,
) -> Iterable[tuple[str, Mapping[str, Any]]]:

    if sid != "doorEvent":
        return
    if "on" not in data:
        return
    value = _flag_value(data["on"])
    if value is True:
        yield "opened", {}
    elif value is False:
        yield "closed", {}


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

class Product2BE5Adapter:
    """麦乐克门窗开关传感器 MIR-MC100 (2BE5) 适配器."""

    prod_id = "2BE5"

    def entities(self, context: DeviceContext) -> tuple[EntitySpec, ...]:
        profile = context.profile
        if profile is None:
            return ()

        entities: list[EntitySpec] = []

        # --- doorEvent.on -> event 门事件 -------------------------------
        if context.has_service("doorEvent") and _field(
            profile, "doorEvent", "on"
        ) is not None:
            entities.append(EntitySpec(
                platform="event",
                key="door_event",
                name="门事件",
                state=lambda _ctx: {},
                event_decoder=_door_event_decoder,
                metadata={
                    "device_class": "door",
                    "event_types": ["opened", "closed"],
                },
            ))

        # --- status.status -> binary_sensor 门窗 ------------------------
        if context.has_service("status") and _field(
            profile, "status", "status"
        ) is not None:
            entities.append(EntitySpec(
                platform="binary_sensor",
                key="door",
                name="门窗",
                state=lambda ctx: {
                    "is_on": _flag_value(ctx.value("status", "status"))
                },
                metadata={"device_class": "door"},
            ))

        # --- battery.level -> sensor 电池电量 ---------------------------
        if context.has_service("battery") and _field(
            profile, "battery", "level"
        ) is not None:
            entities.append(EntitySpec(
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
            ))

        # --- battery.alarm -> binary_sensor 低电量告警 ------------------
        if context.has_service("battery") and _field(
            profile, "battery", "alarm"
        ) is not None:
            entities.append(EntitySpec(
                platform="binary_sensor",
                key="battery_alarm",
                name="低电量告警",
                state=lambda ctx: {
                    "is_on": _flag_value(ctx.value("battery", "alarm"))
                },
                metadata={"device_class": "battery"},
            ))

        # --- temperAlarm.alarm -> binary_sensor 防拆警报 ----------------
        if context.has_service("temperAlarm") and _field(
            profile, "temperAlarm", "alarm"
        ) is not None:
            entities.append(EntitySpec(
                platform="binary_sensor",
                key="tamper",
                name="防拆警报",
                state=lambda ctx: {
                    "is_on": _flag_value(
                        ctx.value("temperAlarm", "alarm")
                    )
                },
                metadata={"device_class": "tamper"},
            ))

        # --- netInfo 诊断 ------------------------------------------------
        entities.extend(_net_info_entities(profile))

        return tuple(entities)


ADAPTER = Product2BE5Adapter()
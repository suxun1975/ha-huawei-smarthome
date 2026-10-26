"""User-contributed protocol for Huawei product 2DAD (名豆之约 10A 智能插座).

设备类型: 智能插座 (Socket), 型号 ZCZ007
制造商: 广州万烨 (wanyesw)

可写服务已暴露:
   switch.on                -> switch "电源"
   chargingProtect.status   -> switch "充电保护" (config)
   ElectricalProtect.status -> switch "家电保护" (config)

可写服务不暴露:
   timer.timer / delay.delay  array[object], 需要专用定时器 UI
   delay.action               method:W create/delete/update, 是动作不是状态
   update.action              OTA 触发

只读服务已暴露:
   faultDetection.status    -> binary_sensor "故障" (problem, 主界面)
   faultDetection.code      -> sensor "故障码" (diagnostic,
                               0 正常 / 1 过载告警)
   realPower.current        -> sensor "实时功率" (kW, divisor 1000)
   electricity.totalConsum  -> sensor "用电量" (kWh, divisor 100)
   netInfo.*                -> 诊断传感器

缩放依据 Profile 显式声明的 divisor 字段，不是从范围推断的.

关于故障码归入 diagnostic:

  故障码 (0 正常 / 1 过载告警) 是诊断信息, 不是用户在主界面频繁查看
  的内容. 归入 diagnostic 类别后折叠到"诊断"区域, 主界面只显示
  电源/实时功率/用电量, 更清爽.

  而 "故障" binary_sensor (device_class=problem) 保持主界面, 因为
  故障发生是用户需要立刻看到的告警. 两个实体的定位不同:
    - 故障 (binary_sensor): 用户视角的"有没有问题", 主界面
    - 故障码 (sensor): 诊断视角的"具体是什么问题", 折叠区

  这与 2MJD 的 match_status / 2QEF 的 fault_code / 2BE5 的
  netInfo.* 等诊断字段的处理一致.
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
    """严格解析 bool: 只接受 0/1 及等价字符串/布尔，其它返回 None。"""
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


def _divisor(profile: Any, sid: str, name: str) -> float:
    """读取 Profile 声明的 divisor；缺省时返回 1.0。"""
    field = _field(profile, sid, name)
    if field is None:
        return 1.0
    raw = field.get("divisor")
    if raw is None:
        return 1.0
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 1.0
    return value if value != 0 else 1.0


def _scaled(value: Any, divisor: float) -> float | None:
    number = _number(value)
    if number is None or divisor == 0:
        return None
    return round(number / divisor, 3)


# ---- 枚举选项（来自 Profile enumList） -----------------------------------

_FAULT_CODE_OPTIONS: tuple[tuple[int, str], ...] = (
    (0, "正常"),
    (1, "过载告警"),
)
_NET_INTENSITY_OPTIONS: tuple[tuple[int, str], ...] = (
    (20, "0格信号"),
    (40, "1格信号"),
    (60, "2格信号"),
    (80, "3格信号"),
    (100, "4格信号"),
)


# ---- 写动作 --------------------------------------------------------------

async def _power_on(context: DeviceContext, _data: Mapping[str, Any]) -> None:
    await context.async_send_service("switch", {"on": 1})


async def _power_off(context: DeviceContext, _data: Mapping[str, Any]) -> None:
    await context.async_send_service("switch", {"on": 0})


async def _charging_on(context: DeviceContext, _data: Mapping[str, Any]) -> None:
    await context.async_send_service("chargingProtect", {"status": 1})


async def _charging_off(context: DeviceContext, _data: Mapping[str, Any]) -> None:
    await context.async_send_service("chargingProtect", {"status": 0})


async def _appliance_on(context: DeviceContext, _data: Mapping[str, Any]) -> None:
    await context.async_send_service("ElectricalProtect", {"status": 1})


async def _appliance_off(context: DeviceContext, _data: Mapping[str, Any]) -> None:
    await context.async_send_service("ElectricalProtect", {"status": 0})


# ---- netInfo 诊断实体 ----------------------------------------------------

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

    for char_name, key, label in (
        ("SSID", "wifi_ssid", "Wi-Fi 名称"),
        ("IP", "wifi_ip", "IP 地址"),
        ("BSSID", "wifi_bssid", "BSSID"),
    ):
        if _field(profile, "netInfo", char_name) is None:
            continue
        entities.append(EntitySpec(
            platform="sensor",
            key=key,
            name=label,
            state=lambda ctx, _n=char_name: {
                "native_value": _text(ctx.value("netInfo", _n))
            },
            metadata={"entity_category": "diagnostic"},
        ))

    return entities


# ---- 适配器 --------------------------------------------------------------

class Product2DADAdapter:
    """名豆之约 10A 智能插座 ZCZ007 (2DAD) 适配器。"""

    prod_id = "2DAD"

    def entities(self, context: DeviceContext) -> tuple[EntitySpec, ...]:
        profile = context.profile
        if profile is None:
            return ()

        entities: list[EntitySpec] = []

        # --- switch.on (RW, 电源) --------------------------------------
        if context.has_service("switch") and _field(profile, "switch", "on") is not None:
            entities.append(EntitySpec(
                platform="switch",
                key="power",
                name="电源",
                state=lambda ctx: {"is_on": _as_bool(ctx.value("switch", "on"))},
                actions={"turn_on": _power_on, "turn_off": _power_off},
            ))

        # --- chargingProtect.status (RW, 配置) --------------------------
        if context.has_service("chargingProtect") and _field(
            profile, "chargingProtect", "status"
        ) is not None:
            entities.append(EntitySpec(
                platform="switch",
                key="charging_protect",
                name="充电保护",
                state=lambda ctx: {
                    "is_on": _as_bool(ctx.value("chargingProtect", "status"))
                },
                actions={"turn_on": _charging_on, "turn_off": _charging_off},
                metadata={"entity_category": "config"},
            ))

        # --- ElectricalProtect.status (RW, 配置) -----------------------
        if context.has_service("ElectricalProtect") and _field(
            profile, "ElectricalProtect", "status"
        ) is not None:
            entities.append(EntitySpec(
                platform="switch",
                key="electrical_protect",
                name="家电保护",
                state=lambda ctx: {
                    "is_on": _as_bool(ctx.value("ElectricalProtect", "status"))
                },
                actions={"turn_on": _appliance_on, "turn_off": _appliance_off},
                metadata={"entity_category": "config"},
            ))

        # --- faultDetection.status (只读, 主界面) -----------------------
        if context.has_service("faultDetection") and _field(
            profile, "faultDetection", "status"
        ) is not None:
            entities.append(EntitySpec(
                platform="binary_sensor",
                key="fault",
                name="故障",
                state=lambda ctx: {
                    "is_on": _as_bool(ctx.value("faultDetection", "status"))
                },
                metadata={"device_class": "problem"},
            ))

        # --- faultDetection.code (只读, diagnostic) ---------------------
        if context.has_service("faultDetection") and _field(
            profile, "faultDetection", "code"
        ) is not None:
            entities.append(EntitySpec(
                platform="sensor",
                key="fault_code",
                name="故障码",
                state=lambda ctx: {
                    "native_value": _enum_label(
                        ctx.value("faultDetection", "code"), _FAULT_CODE_OPTIONS
                    )
                },
                metadata={"entity_category": "diagnostic"},
            ))

        # --- realPower.current (只读, ÷1000, kW) ------------------------
        if context.has_service("realPower") and _field(
            profile, "realPower", "current"
        ) is not None:
            divisor = _divisor(profile, "realPower", "current")
            entities.append(EntitySpec(
                platform="sensor",
                key="real_power",
                name="实时功率",
                state=lambda ctx, _d=divisor: {
                    "native_value": _scaled(ctx.value("realPower", "current"), _d)
                },
                metadata={
                    "device_class": "power",
                    "state_class": "measurement",
                    "unit": "kW",
                },
            ))

        # --- electricity.totalConsum (只读, ÷100, kWh) ------------------
        if context.has_service("electricity") and _field(
            profile, "electricity", "totalConsum"
        ) is not None:
            divisor = _divisor(profile, "electricity", "totalConsum")
            entities.append(EntitySpec(
                platform="sensor",
                key="total_energy",
                name="用电量",
                state=lambda ctx, _d=divisor: {
                    "native_value": _scaled(
                        ctx.value("electricity", "totalConsum"), _d
                    )
                },
                metadata={
                    "device_class": "energy",
                    "state_class": "total_increasing",
                    "unit": "kWh",
                },
            ))

        # --- netInfo (诊断) ---------------------------------------------
        entities.extend(_net_info_entities(profile))

        return tuple(entities)


ADAPTER = Product2DADAdapter()
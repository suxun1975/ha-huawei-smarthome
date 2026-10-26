"""User-contributed protocol for Huawei product 210Y (欧井除湿机 OJ-123E).

设备类型: 除湿机 (Dehumidifier), 型号 OJ-123E
制造商: 浙江欧伦电气有限公司 (Zhejiang Oulun Electric)

Profile 的服务:

  switch.on              bool RW  0 关 / 1 开
  childLockSwitch.on     bool RW  0 关 / 1 开
  ION.ION                bool RW  0 关 / 1 开
  mode.mode              enum RW  0 自动 / 1 干衣 / 2 睡眠
  gear.gear              enum RW  100 低风 / 101 高风
  humidity.target        int  RW  20..80, step 5
  humidity.current       int  R   20..90
  temperature.current    int  R   0..100
  faultDetection.status  bool R   0 正常 / 1 异常
  faultDetection.code    enum R   0 正常 / 1 设备异常 / 3 水箱水满
  netInfo.*              R        WiFi 诊断
  update.*               OTA      不暴露

已暴露 (14 个实体):

  switch (3):        电源 / 童锁 (config) / 负离子 (config)
  select (2):        模式 (自动/干衣/睡眠) / 档位 (低风/高风)
  number (1):        目标湿度 (20~80 %, step 5)
  binary_sensor (1): 故障
  sensor (7):        当前湿度 / 当前温度 / 故障码 /
                     信号强度 / 信号等级 / Wi-Fi 名称 / IP

故意不暴露:

  update.*   OTA

三处 Profile 的细节:

  1. gear.gear 的 enumVal 是 100 / 101 而不是 1 / 2:
       100 -> 低风
       101 -> 高风
     select 的选项是中文标签, 写入时反查回 100/101. 这是 Profile 的
     固有设计, 与 "1/2" 只是数值不同, 不影响 select 逻辑.

  2. faultDetection.code 的 enumVal 跳过 2:
       0 -> 正常
       1 -> 设备异常
       3 -> 水箱水满
     2 不在枚举里, 未知值返回 None, HA 显示 unknown. 不猜测.

  3. humidity.target 的 step 是 5:
     20, 25, 30, ..., 80, 共 13 个可选值. number 平台的 min/max/step
     直接传 20/80/5, HA 会自动对齐.

关于湿度单位:

  humidity.target 和 humidity.current 的 unit 是空字符串, 但 min/max
  是 20~80 / 20~90, 明显是百分比. 适配器用 "%" 作为单位, 与 HA 的
  SensorDeviceClass.HUMIDITY 契约一致.

关于温度单位:

  temperature.current 的 unit 也是空字符串, min/max 是 0~100,
  是摄氏度整数. 适配器用 "°C" (U+00B0 + "C") 而不是 "℃" (U+2103),
  与 HA 的 SensorDeviceClass.TEMPERATURE 契约一致, 不触发警告.

关于为何不用 climate:

  除湿机的核心控制是"目标湿度", 不是"目标温度". climate.py 的
  target_temperature 字段无法表达湿度, 而 target_temperature 只能
  是温度. 用 number 表达目标湿度更准确, 也避免了 climate 卡片上
  "温度滑块" 的错误暗示.

关于 ION.ION 的字段名:

  ION 服务的字段名是 "ION" 而不是惯例的 "on". 合并工厂
  _switch_action(sid, field, value) 时, 需要显式传 field="ION":

    ("ION", "ion", "负离子", "ION", True),
                ^^^         ^^^^^
                key        field_name

  这样 _switch_action("ION", "ION", 1) 会发送 {"ION": 1} 到 ION 服务.

关于 _flag_value 的命名:

  与 2BE5 / 2BE6 / 2BE8 / 2GB1 / 2MKS / 2QEF / 20TL / 25I8 / 105G
  / 105M / 107W 的 _flag_value 命名和实现完全一致, 十二个适配器
  风格统一.

  旧版用 _as_bool 命名, 本版改成 _flag_value, 功能完全一样
  (严格解析 0/1 + "true"/"on"/"false"/"off").
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

def _flag_value(value: Any) -> bool | None:
    """严格解析 bool: 接受 0/1, 字符串 "0"/"1"/"true"/"false"/"on"/"off",
    以及 JSON 布尔 true/false, 其它返回 None.

    与 2BE5 / 2BE6 / 2BE8 / 2GB1 / 2MKS / 2QEF / 20TL / 25I8 / 105G
    / 105M / 107W 的 _flag_value 命名和实现完全一致, 十二个适配器
    风格统一.
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

_MODE_OPTIONS: tuple[tuple[int, str], ...] = (
    (0, "自动"),
    (1, "干衣"),
    (2, "睡眠"),
)
_GEAR_OPTIONS: tuple[tuple[int, str], ...] = (
    (100, "低风"),
    (101, "高风"),
)
_FAULT_CODE_OPTIONS: tuple[tuple[int, str], ...] = (
    (0, "正常"),
    (1, "设备异常"),
    (3, "水箱水满"),
)
_NET_INTENSITY_OPTIONS: tuple[tuple[int, str], ...] = (
    (20, "0格信号"),
    (40, "1格信号"),
    (60, "2格信号"),
    (80, "3格信号"),
    (100, "4格信号"),
)


# ---- 写动作工厂 ---------------------------------------------------------

def _switch_action(sid: str, field: str, value: int):
    """生成一个 switch 的 turn_on/turn_off 动作.

    统一处理 3 个 switch:
      ("switch", "on", 1)           -> 发送 {"on": 1}
      ("childLockSwitch", "on", 1)  -> 发送 {"on": 1}
      ("ION", "ION", 1)             -> 发送 {"ION": 1}

    比旧版的 6 个独立函数 (_power_on / _power_off / _child_lock_on /
    _child_lock_off / _ion_on / _ion_off) 更简洁, 与 105G / 2MJD /
    2QEF / 25I8 / 107W 的 _switch_action 风格一致.

    ION 服务的字段名是 "ION" 而不是惯例的 "on", 所以需要显式传
    field="ION".
    """
    async def _action(ctx: DeviceContext, _data: Mapping[str, Any]) -> None:
        await ctx.async_send_service(sid, {field: value})
    return _action


def _select_action(sid: str, field: str, options: tuple[tuple[int, str], ...]):
    lookup = {label: value for value, label in options}

    async def _action(ctx: DeviceContext, data: Mapping[str, Any]) -> None:
        option = data.get("option")
        if not isinstance(option, str):
            return
        value = lookup.get(option)
        if value is None:
            return
        await ctx.async_send_service(sid, {field: value})
    return _action


async def _set_humidity_target(ctx: DeviceContext, data: Mapping[str, Any]) -> None:
    value = data.get("value")
    if value is None:
        return
    try:
        int_value = int(round(float(value)))
    except (TypeError, ValueError):
        return
    if int_value < 20 or int_value > 80:
        return
    await ctx.async_send_service("humidity", {"target": int_value})


# ---- switch 定义表 -----------------------------------------------------

# (sid, key, name, field_name, config)
_SWITCHES: tuple[tuple[str, str, str, str, bool], ...] = (
    ("switch", "power", "电源", "on", False),
    ("childLockSwitch", "child_lock", "童锁", "on", True),
    ("ION", "ion", "负离子", "ION", True),
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

class Product210YAdapter:
    """欧井除湿机 OJ-123E (210Y) 适配器."""

    prod_id = "210Y"

    def entities(self, context: DeviceContext) -> tuple[EntitySpec, ...]:
        profile = context.profile
        if profile is None:
            return ()

        entities: list[EntitySpec] = []

        # --- 3 个 switch: 电源 / 童锁 / 负离子 --------------------------
        for sid, key, name, field_name, is_config in _SWITCHES:
            if not context.has_service(sid):
                continue
            if _field(profile, sid, field_name) is None:
                continue
            metadata: dict[str, Any] = {}
            if is_config:
                metadata["entity_category"] = "config"
            entities.append(EntitySpec(
                platform="switch",
                key=key,
                name=name,
                state=lambda ctx, _s=sid, _f=field_name: {
                    "is_on": _flag_value(ctx.value(_s, _f))
                },
                actions={
                    "turn_on": _switch_action(sid, field_name, 1),
                    "turn_off": _switch_action(sid, field_name, 0),
                },
                metadata=metadata,
            ))

        # --- mode.mode -> select 模式 -----------------------------------
        if context.has_service("mode") and _field(profile, "mode", "mode") is not None:
            entities.append(EntitySpec(
                platform="select",
                key="mode",
                name="模式",
                state=lambda ctx: {
                    "current_option": _enum_label(
                        ctx.value("mode", "mode"), _MODE_OPTIONS
                    )
                },
                actions={
                    "select_option": _select_action("mode", "mode", _MODE_OPTIONS),
                },
                metadata={"options": [label for _, label in _MODE_OPTIONS]},
            ))

        # --- gear.gear -> select 档位 -----------------------------------
        if context.has_service("gear") and _field(profile, "gear", "gear") is not None:
            entities.append(EntitySpec(
                platform="select",
                key="gear",
                name="档位",
                state=lambda ctx: {
                    "current_option": _enum_label(
                        ctx.value("gear", "gear"), _GEAR_OPTIONS
                    )
                },
                actions={
                    "select_option": _select_action("gear", "gear", _GEAR_OPTIONS),
                },
                metadata={"options": [label for _, label in _GEAR_OPTIONS]},
            ))

        # --- humidity.target -> number 目标湿度 -------------------------
        if context.has_service("humidity") and _field(
            profile, "humidity", "target"
        ) is not None:
            entities.append(EntitySpec(
                platform="number",
                key="humidity_target",
                name="目标湿度",
                state=lambda ctx: {
                    "native_value": _number(
                        ctx.value("humidity", "target")
                    )
                },
                actions={"set_value": _set_humidity_target},
                metadata={
                    "min": 20,
                    "max": 80,
                    "step": 5,
                    "unit": "%",
                },
            ))

        # --- humidity.current -> sensor 当前湿度 ------------------------
        if context.has_service("humidity") and _field(
            profile, "humidity", "current"
        ) is not None:
            entities.append(EntitySpec(
                platform="sensor",
                key="humidity",
                name="当前湿度",
                state=lambda ctx: {
                    "native_value": _number(
                        ctx.value("humidity", "current")
                    )
                },
                metadata={
                    "device_class": "humidity",
                    "state_class": "measurement",
                    "unit": "%",
                },
            ))

        # --- temperature.current -> sensor 当前温度 ---------------------
        if context.has_service("temperature") and _field(
            profile, "temperature", "current"
        ) is not None:
            entities.append(EntitySpec(
                platform="sensor",
                key="temperature",
                name="当前温度",
                state=lambda ctx: {
                    "native_value": _number(
                        ctx.value("temperature", "current")
                    )
                },
                metadata={
                    "device_class": "temperature",
                    "state_class": "measurement",
                    "unit": "°C",
                },
            ))

        # --- faultDetection.status -> binary_sensor 故障 ----------------
        if context.has_service("faultDetection") and _field(
            profile, "faultDetection", "status"
        ) is not None:
            entities.append(EntitySpec(
                platform="binary_sensor",
                key="fault",
                name="故障",
                state=lambda ctx: {
                    "is_on": _flag_value(
                        ctx.value("faultDetection", "status")
                    )
                },
                metadata={"device_class": "problem"},
            ))

        # --- faultDetection.code -> sensor 故障码 -----------------------
        if context.has_service("faultDetection") and _field(
            profile, "faultDetection", "code"
        ) is not None:
            entities.append(EntitySpec(
                platform="sensor",
                key="fault_code",
                name="故障码",
                state=lambda ctx: {
                    "native_value": _enum_label(
                        ctx.value("faultDetection", "code"),
                        _FAULT_CODE_OPTIONS,
                    )
                },
                metadata={"entity_category": "diagnostic"},
            ))

        # --- netInfo 诊断 ------------------------------------------------
        entities.extend(_net_info_entities(profile))

        return tuple(entities)


ADAPTER = Product210YAdapter()
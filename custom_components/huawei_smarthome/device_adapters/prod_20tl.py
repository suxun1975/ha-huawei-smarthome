"""User-contributed protocol for Huawei product 20TL (贝昂无耗材空气净化器 X7SH).

设备类型: 空气净化器 (Air Cleaner), 型号 X7S(H)
制造商: 贝昂 (airdog)

Profile 的四处矛盾与特殊声明:

  1. mode.mode 的 descEn 和 descCh 错位:
       enumVal 1: descEn "Auto"  / descCh "睡眠"
       enumVal 2: descEn "Sleep" / descCh "自动"
     以 descCh 为准 (中文产品以中文描述为权威), 与 2GE7 / 2BE8 /
     2MJD / 101N 的处理一致.

  2. fan.gear 同样错位:
       enumVal 1: descEn "Auto" / descCh "低风"
     以 descCh 为准.

  3. pm25.level 的枚举跳过 3 和 5 (1优/2良/4中度污染/6严重污染),
     3 和 5 是非法值, 未知值返回 None.

  4. hcho1.hcho1 有权威 divisor "100", unit "mg/m³". 必须除以 100.
     与 2DAD 的 realPower (divisor 1000) 同理, 按 Profile 声明缩放.

已暴露 (13 个实体):

  switch (2):  电源 / 童锁 (config)
  button (1):  清洁复位   (clean.clean, method:W, 只写)
  select (2):  模式 / 风速档位   (RW enum, 可选)
  sensor (8):  PM2.5 / PM2.5 等级 / 甲醛 /
               信号强度 / 信号等级 / Wi-Fi 名称 / IP / BSSID

故意不暴露:

  timer.* / delay.*   array[object], 需要专用 UI
  update.*            OTA

select 契约来自 custom_components/huawei_smarthome/select.py:
  current_option  = spec.state(ctx).get("current_option")
  async_select_option(option)  ->  action(ctx, {"option": option})
  _attr_options   = list(metadata.get("options", ()))

所以 select 的 state 返回 {"current_option": <标签>}, metadata 里
options 是标签列表, action 里把标签反查回 enum 值.

关于 _flag_value 的命名:

  与 2BE5 / 2BE6 / 2BE8 / 2GB1 / 2MKS / 2QEF 的 _flag_value 命名
  和实现完全一致, 七个适配器风格统一.

  旧版用 _as_bool 命名, 本版改成 _flag_value, 功能完全一样
  (严格解析 0/1 + "true"/"on"/"false"/"off"), 只是名字统一方便
  跨文件阅读和复制.

关于 clean.clean 用 button 而非 switch:

  Profile 里 clean.clean 是 method:"W" (只写), permission:"P"
  (不可读). 设备只接受写入, 不回报状态. 用 button 点击即发送
  {"clean": 1}, 执行一次清洁复位, 与 2MKS 的处理一致.

关于 mode / fan.gear 用 select 而非 switch:

  两个字段都是 RW enum, 有 3 个和 5 个枚举值. switch 只有两态,
  会丢失选项. select 的 options 用中文标签, 写入时反查回 enum 值.
  与 2MKS 的模式/档位处理一致.
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

    与 2BE5 / 2BE6 / 2BE8 / 2GB1 / 2MKS / 2QEF 的 _flag_value 命名
    和实现完全一致, 七个适配器风格统一.

    旧版用 _as_bool 命名, 本版改成 _flag_value, 功能完全一样.
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


def _divisor(profile: Any, sid: str, name: str) -> float:
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
    return round(number / divisor, 4)


# ---- 枚举选项 (descCh 为准, 权威) --------------------------------------

# Profile 里 descEn 和 descCh 错位, 以 descCh 为准
_MODE_OPTIONS: tuple[tuple[int, str], ...] = (
    (0, "手动"),
    (1, "睡眠"),
    (2, "自动"),
)
_FAN_GEAR_OPTIONS: tuple[tuple[int, str], ...] = (
    (1, "低风"),
    (2, "中风"),
    (3, "高风"),
    (4, "强风"),
    (5, "超强风"),
)
# 注意: 3 和 5 不在枚举里, 未知值返回 None
_PM25_LEVEL_OPTIONS: tuple[tuple[int, str], ...] = (
    (1, "优"),
    (2, "良"),
    (4, "中度污染"),
    (6, "严重污染"),
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


async def _child_lock_on(context: DeviceContext, _data: Mapping[str, Any]) -> None:
    await context.async_send_service("childLockSwitch", {"on": 1})


async def _child_lock_off(context: DeviceContext, _data: Mapping[str, Any]) -> None:
    await context.async_send_service("childLockSwitch", {"on": 0})


async def _clean_press(context: DeviceContext, _data: Mapping[str, Any]) -> None:
    await context.async_send_service("clean", {"clean": 1})


def _select_action(
    sid: str,
    field_name: str,
    options: tuple[tuple[int, str], ...],
):
    """把用户选中的中文标签反查回 enum 值, 再写入 ``sid``.

    select.py 的 async_select_option 传给 action 的是 {"option": "<标签>"},
    标签字符串必须与 metadata["options"] 里的一致 (即 options 表的 label).
    """
    lookup = {label: value for value, label in options}

    async def _action(ctx: DeviceContext, data: Mapping[str, Any]) -> None:
        option = data.get("option")
        if not isinstance(option, str):
            return
        value = lookup.get(option)
        if value is None:
            return
        await ctx.async_send_service(sid, {field_name: value})

    return _action


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

class Product20TLAdapter:
    """贝昂无耗材空气净化器 X7SH (20TL) 适配器."""

    prod_id = "20TL"

    def entities(self, context: DeviceContext) -> tuple[EntitySpec, ...]:
        profile = context.profile
        if profile is None:
            return ()

        entities: list[EntitySpec] = []

        # --- switch.on -> switch 电源 ------------------------------------
        if context.has_service("switch") and _field(profile, "switch", "on") is not None:
            entities.append(EntitySpec(
                platform="switch",
                key="power",
                name="电源",
                state=lambda ctx: {"is_on": _flag_value(ctx.value("switch", "on"))},
                actions={"turn_on": _power_on, "turn_off": _power_off},
            ))

        # --- childLockSwitch.on -> switch 童锁 (config) ------------------
        if context.has_service("childLockSwitch") and _field(
            profile, "childLockSwitch", "on"
        ) is not None:
            entities.append(EntitySpec(
                platform="switch",
                key="child_lock",
                name="童锁",
                state=lambda ctx: {
                    "is_on": _flag_value(ctx.value("childLockSwitch", "on"))
                },
                actions={
                    "turn_on": _child_lock_on,
                    "turn_off": _child_lock_off,
                },
                metadata={"entity_category": "config"},
            ))

        # --- clean.clean -> button 清洁复位 ------------------------------
        if context.has_service("clean") and _field(profile, "clean", "clean") is not None:
            entities.append(EntitySpec(
                platform="button",
                key="clean_reset",
                name="清洁复位",
                state=lambda _ctx: {},
                actions={"press": _clean_press},
            ))

        # --- pm25.current -> sensor PM2.5 -------------------------------
        if context.has_service("pm25") and _field(
            profile, "pm25", "current"
        ) is not None:
            entities.append(EntitySpec(
                platform="sensor",
                key="pm25",
                name="PM2.5",
                state=lambda ctx: {
                    "native_value": _number(ctx.value("pm25", "current"))
                },
                metadata={
                    "device_class": "pm25",
                    "state_class": "measurement",
                    "unit": "μg/m³",
                },
            ))

        # --- pm25.level -> sensor PM2.5 等级 ----------------------------
        if context.has_service("pm25") and _field(
            profile, "pm25", "level"
        ) is not None:
            entities.append(EntitySpec(
                platform="sensor",
                key="pm25_level",
                name="PM2.5 等级",
                state=lambda ctx: {
                    "native_value": _enum_label(
                        ctx.value("pm25", "level"), _PM25_LEVEL_OPTIONS
                    )
                },
                metadata={},
            ))

        # --- hcho1.hcho1 -> sensor 甲醛 (÷100) --------------------------
        if context.has_service("hcho1") and _field(
            profile, "hcho1", "hcho1"
        ) is not None:
            divisor = _divisor(profile, "hcho1", "hcho1")
            entities.append(EntitySpec(
                platform="sensor",
                key="hcho",
                name="甲醛",
                state=lambda ctx, _d=divisor: {
                    "native_value": _scaled(ctx.value("hcho1", "hcho1"), _d)
                },
                metadata={
                    "state_class": "measurement",
                    "unit": "mg/m³",
                },
            ))

        # --- mode.mode -> select 模式 (RW enum) --------------------------
        if context.has_service("mode") and _field(
            profile, "mode", "mode"
        ) is not None:
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
                    "select_option": _select_action(
                        "mode", "mode", _MODE_OPTIONS
                    ),
                },
                metadata={"options": [label for _, label in _MODE_OPTIONS]},
            ))

        # --- fan.gear -> select 风速档位 (RW enum) ----------------------
        if context.has_service("fan") and _field(
            profile, "fan", "gear"
        ) is not None:
            entities.append(EntitySpec(
                platform="select",
                key="fan_gear",
                name="风速档位",
                state=lambda ctx: {
                    "current_option": _enum_label(
                        ctx.value("fan", "gear"), _FAN_GEAR_OPTIONS
                    )
                },
                actions={
                    "select_option": _select_action(
                        "fan", "gear", _FAN_GEAR_OPTIONS
                    ),
                },
                metadata={"options": [label for _, label in _FAN_GEAR_OPTIONS]},
            ))

        # --- netInfo 诊断 ------------------------------------------------
        entities.extend(_net_info_entities(profile))

        return tuple(entities)


ADAPTER = Product20TLAdapter()
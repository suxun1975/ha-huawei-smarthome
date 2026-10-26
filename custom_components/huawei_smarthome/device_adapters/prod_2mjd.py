"""User-contributed protocol for Huawei product 2MJD (红外万能遥控中心 YKK-H1025).
设备类型: 万能遥控器 (Universal Remotor), 型号 YKK-H1025
制造商: 深圳遥看科技有限公司 (yaokan)
这是一个红外遥控网关. 核心能力:
  1. 电源/静音开关 (发送红外开关指令)
  2. 模式/档位/扫风/温度控制 (发送空调控制指令)
  3. 频道调整 (发送电视频道指令)
  4. 自定义遥控器 (20 个预存红外码槽位 x 4 组)
  5. WiFi 诊断
已暴露 (106 个实体):
  switch (11):
    电源: 风扇/空调/电视/音响/净化器/机顶盒/投影仪 (7个)
    静音: 电视/机顶盒/投影仪 (3个)
    指示灯 (1个, config)
  select (4):
    空调模式 / 空调档位 / 空调扫风 / 净化器模式
  number (4):
    空调温度 (16~30°C) / 电视频道 (0~9) /
    机顶盒频道 (0~256) / 投影仪频道 (0~9)
  sensor (7):
    匹配状态 (status.status, diagnostic)
    WiFi 诊断: RSSI / intensity / band / SSID / IP / BSSID
  button (80):
    自定义遥控器01  x 20  (mediaKey 的 action 1~20)
    自定义遥控器02  x 20  (mediaKey1 的 action 1~20)
    自定义遥控器03  x 20  (mediaKey2 的 action 1~20)
    自定义遥控器04  x 20  (mediaKey3 的 action 1~20)
故意不暴露:
  TVKey.action / speakerKey.action / STBKey.action / projectorKey.action
                             单个按键动作, 用 select/button 会生成 50+ 个实体,
                             与 mediaKey 的 80 button 重复, 不暴露
  matchedCap.jsonstr       红外码下发, 需要 text 平台, 但 maxLength=12000
                             远超 HA text.py 的 255 限制, 截断后是残码
  customKey.*              按键命名与数量, 语义不明 (name1~5 对应哪些按键
                             Profile 没说清楚), 且没有 action 字段可触发
  delay1.*                 倒计时关机, 动作
  backup / rcList / batchCmd  array[object], 需要专用 UI
  fanMode.mode             风扇控制功能选择, 非状态
  各服务 *.controlSource    内部分析字段
  update.*                 OTA
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

_AIR_MODE_OPTIONS: tuple[tuple[int, str], ...] = (
    (0, "自动"), (1, "除湿"), (2, "送风"), (3, "制热"), (4, "制冷"),
)
_AIR_GEAR_OPTIONS: tuple[tuple[int, str], ...] = (
    (0, "自动"), (1, "低风"), (2, "中风"), (3, "高风"),
)
_AIR_SWING_OPTIONS: tuple[tuple[int, str], ...] = (
    (0, "扫风关"), (1, "扫风开"), (2, "上下开"), (3, "左右开"),
)
_PURIFIER_MODE_OPTIONS: tuple[tuple[int, str], ...] = (
    (0, "负离子"), (1, "风速"), (2, "睡眠"),
    (3, "杀菌"), (4, "定时"), (5, "灯光"),
)
_MATCH_STATUS_OPTIONS: tuple[tuple[int, str], ...] = (
    (0, "匹配中"), (100, "匹配成功"), (200, "匹配失败"),
)
_NET_INTENSITY_OPTIONS: tuple[tuple[int, str], ...] = (
    (20, "0格信号"), (40, "1格信号"), (60, "2格信号"),
    (80, "3格信号"), (100, "4格信号"),
)
_NET_BAND_OPTIONS: tuple[tuple[int, str], ...] = (
    (1, "2.4G"), (2, "5G"),
)

# mediaKey 的 20 个槽位, 顺序与华为智慧生活 App 一致:
#   第1个 = 开 (value=2)
#   第2个 = 关 (value=1)
#   第3~20个 = 按键3~按键20 (value=3~20)
#
# 元组格式: (value, label, key_index)
#   value     发送给设备的 action 值
#   label     显示名, 数字用 02d 补零让 entity_id 按数字序排
#   key_index unique_id 的序号, 与显示顺序一致
_MEDIA_KEY_OPTIONS: tuple[tuple[int, str, int], ...] = (
    (2, "按键01 开", 1),
    (1, "按键02 关", 2),
) + tuple(
    (i, f"按键{i:02d}", i) for i in range(3, 21)
)


# ---- 写动作工厂 ---------------------------------------------------------

def _switch_action(sid: str, field: str, value: int):
    """生成一个 switch 的 turn_on/turn_off 动作.

    统一处理 on 字段 (电源) 和 mute 字段 (静音/音响电源).
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


def _number_action(sid: str, field: str):
    async def _action(ctx: DeviceContext, data: Mapping[str, Any]) -> None:
        value = data.get("value")
        if value is None:
            return
        try:
            int_value = int(round(float(value)))
        except (TypeError, ValueError):
            return
        await ctx.async_send_service(sid, {field: int_value})
    return _action


def _media_key_press(sid: str, value: int):
    async def _action(ctx: DeviceContext, _data: Mapping[str, Any]) -> None:
        await ctx.async_send_service(sid, {"action": value})
    return _action


# ---- 实体定义表 ---------------------------------------------------------

# (sid, key, name, field_name, config)
#   field_name = "on"   -> 电源开关 (发送 {"on": 1/0})
#   field_name = "mute" -> 静音/音响电源 (发送 {"mute": 1/0})
#   config = True       -> 归入 entity_category=config
_SWITCHES: tuple[tuple[str, str, str, str, bool], ...] = (
    ("fanSwitch", "fan_power", "风扇电源", "on", False),
    ("airKey", "air_power", "空调电源", "on", False),
    ("TVKey", "tv_power", "电视电源", "on", False),
    ("speakerKey", "speaker_power", "音响电源", "mute", False),
    ("purifierKey", "purifier_power", "净化器电源", "on", False),
    ("STBKey", "stb_power", "机顶盒电源", "on", False),
    ("projectorKey", "projector_power", "投影仪电源", "on", False),
    ("indicatorSwitch", "indicator", "指示灯", "on", True),
    ("TVKey", "tv_mute", "电视静音", "mute", False),
    ("STBKey", "stb_mute", "机顶盒静音", "mute", False),
    ("projectorKey", "projector_mute", "投影仪静音", "mute", False),
)


_MEDIA_KEY_SERVICES: tuple[tuple[str, str, str], ...] = (
    ("mediaKey", "media_key", "自定义遥控器01"),
    ("mediaKey1", "media_key1", "自定义遥控器02"),
    ("mediaKey2", "media_key2", "自定义遥控器03"),
    ("mediaKey3", "media_key3", "自定义遥控器04"),
)

# (sid, field, key, name, options)
_SELECTS: tuple[
    tuple[str, str, str, str, tuple[tuple[int, str], ...]], ...
] = (
    ("airKey", "mode", "air_mode", "空调模式", _AIR_MODE_OPTIONS),
    ("airKey", "gear", "air_gear", "空调档位", _AIR_GEAR_OPTIONS),
    ("airKey", "airSwing", "air_swing", "空调扫风", _AIR_SWING_OPTIONS),
    ("purifierKey", "mode", "purifier_mode", "净化器模式", _PURIFIER_MODE_OPTIONS),
)

# (sid, field, key, name, min, max, step, unit)
_NUMBERS: tuple[
    tuple[str, str, str, str, float, float, float, str | None], ...
] = (
    ("airKey", "target", "air_target", "空调温度", 16, 30, 1, "°C"),
    ("TVKey", "channel", "tv_channel", "电视频道", 0, 9, 1, None),
    ("STBKey", "channel", "stb_channel", "机顶盒频道", 0, 256, 1, None),
    ("projectorKey", "channel", "projector_channel", "投影仪频道", 0, 9, 1, None),
)


# ---- 实体构建函数 -------------------------------------------------------

def _switch_entities(
    context: DeviceContext, profile: Any
) -> list[EntitySpec]:
    """统一的 switch 构建: 电源 / 静音 / 音响电源 / 指示灯."""
    entities: list[EntitySpec] = []
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
                "is_on": _as_bool(ctx.value(_s, _f))
            },
            actions={
                "turn_on": _switch_action(sid, field_name, 1),
                "turn_off": _switch_action(sid, field_name, 0),
            },
            metadata=metadata,
        ))
    return entities


def _media_key_button_entities(
    context: DeviceContext, profile: Any
) -> list[EntitySpec]:
    """4 个自定义遥控器 x 20 个槽位 = 80 个 button, 全部显示不折叠.

    顺序与华为智慧生活 App 一致: 第1个开, 第2个关, 第3~20个按键3~20.
    key 用 key_index 保证 entity_id 数字序, actions 用 value 保证指令正确.
    """
    entities: list[EntitySpec] = []
    for sid, prefix, display in _MEDIA_KEY_SERVICES:
        if not context.has_service(sid):
            continue
        if _field(profile, sid, "action") is None:
            continue
        for value, label, key_index in _MEDIA_KEY_OPTIONS:
            entities.append(EntitySpec(
                platform="button",
                key=f"{prefix}_key_{key_index:02d}",
                name=f"{display} {label}",
                state=lambda _ctx: {},
                actions={"press": _media_key_press(sid, value)},
            ))
    return entities


def _select_entities(
    context: DeviceContext, profile: Any
) -> list[EntitySpec]:
    entities: list[EntitySpec] = []
    for sid, field, key, name, options in _SELECTS:
        if not context.has_service(sid):
            continue
        if _field(profile, sid, field) is None:
            continue
        entities.append(EntitySpec(
            platform="select",
            key=key,
            name=name,
            state=lambda ctx, _s=sid, _f=field, _o=options: {
                "current_option": _enum_label(ctx.value(_s, _f), _o)
            },
            actions={
                "select_option": _select_action(sid, field, options),
            },
            metadata={"options": [label for _, label in options]},
        ))
    return entities


def _number_entities(
    context: DeviceContext, profile: Any
) -> list[EntitySpec]:
    entities: list[EntitySpec] = []
    for sid, field, key, name, min_v, max_v, step, unit in _NUMBERS:
        if not context.has_service(sid):
            continue
        if _field(profile, sid, field) is None:
            continue
        metadata: dict[str, Any] = {
            "min": min_v,
            "max": max_v,
            "step": step,
        }
        if unit is not None:
            metadata["unit"] = unit
        entities.append(EntitySpec(
            platform="number",
            key=key,
            name=name,
            state=lambda ctx, _s=sid, _f=field: {
                "native_value": _number(ctx.value(_s, _f))
            },
            actions={
                "set_value": _number_action(sid, field),
            },
            metadata=metadata,
        ))
    return entities


def _status_sensor_entities(
    context: DeviceContext, profile: Any
) -> list[EntitySpec]:
    if not context.has_service("status"):
        return []
    if _field(profile, "status", "status") is None:
        return []
    return [EntitySpec(
        platform="sensor",
        key="match_status",
        name="匹配状态",
        state=lambda ctx: {
            "native_value": _enum_label(
                ctx.value("status", "status"), _MATCH_STATUS_OPTIONS
            )
        },
        metadata={"entity_category": "diagnostic"},
    )]


def _net_info_entities(profile: Any) -> list[EntitySpec]:
    if _service(profile, "netInfo") is None:
        return []
    entities: list[EntitySpec] = []

    if _field(profile, "netInfo", "RSSI") is not None:
        entities.append(EntitySpec(
            platform="sensor",
            key="wifi_rssi",
            name="信号强度",
            state=lambda ctx: {
                "native_value": _number(ctx.value("netInfo", "RSSI"))
            },
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

    if _field(profile, "netInfo", "band") is not None:
        entities.append(EntitySpec(
            platform="sensor",
            key="wifi_band",
            name="Wi-Fi 频段",
            state=lambda ctx: {
                "native_value": _enum_label(
                    ctx.value("netInfo", "band"), _NET_BAND_OPTIONS
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

class Product2MJDAdapter:
    """红外万能遥控中心 YKK-H1025 (2MJD) 适配器."""

    prod_id = "2MJD"

    def entities(self, context: DeviceContext) -> tuple[EntitySpec, ...]:
        profile = context.profile
        if profile is None:
            return ()

        entities: list[EntitySpec] = []
        entities.extend(_switch_entities(context, profile))
        entities.extend(_media_key_button_entities(context, profile))
        entities.extend(_select_entities(context, profile))
        entities.extend(_number_entities(context, profile))
        entities.extend(_status_sensor_entities(context, profile))
        entities.extend(_net_info_entities(profile))
        return tuple(entities)


ADAPTER = Product2MJDAdapter()
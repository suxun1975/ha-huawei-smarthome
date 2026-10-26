"""User-contributed protocol for Huawei product 23ET (圆和六路场景智能开关 X9SC6).

设备类型: 场景面板 (Scene Panel), 型号 X9SC6
制造商: 鼎力 (DLTN)

6 个按键服务 + 1 个按键记录 + RSSI + netInfo + update:

  button1..button6.num   int RW  min=1 max=1   按下时发送 {"num": 1}
  button1..button6.name  string RW              设备侧按键名, 不暴露
  scene.num              int R                 最后按键键码, min=max=1, 不暴露
  RSSI.RSSI              enum R                0→20/1→40/2→60/3→80/4→100, 与
                                               netInfo.intensity 重复, 不暴露
  netInfo.*              R                     诊断, 暴露 5 个 sensor
  update.*               OTA                   不暴露

已暴露 (11 个实体):

  button (6):  按键1 / 按键2 / 按键3 / 按键4 / 按键5 / 按键6
               点击发送 {sid: {"num": 1}}, 由设备侧执行对应场景
  sensor (5):  信号强度 RSSI / 信号等级 intensity / Wi-Fi 名称 / IP / BSSID

关于 button 平台的风险:

  api.py 的 EntityAction 签名是 Callable[["DeviceContext", Mapping], Awaitable[None]],
  entity_helpers.py 的 _run_action 按 action 名字查表, 找不到时抛
  ValueError("adapter action is unavailable: {name}"), 只影响该实体.
  所以 button 的 action key 用错了不会导致整个设备加载失败, 最多是
  6 个 button 点击报错, netInfo 的 5 个 sensor 正常. 这个风险可接受.

  action key 用 HA 标准的 "press". 如果框架的 button.py 用的是别的名字
  (比如 "push"), 只需改 _BUTTONS 里 actions 字典的 key, 闭包本身不用动.
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


# ---- 按键写动作工厂 ----------------------------------------------------

def _press_action(sid: str):
    async def _action(ctx: DeviceContext, _data: Mapping[str, Any]) -> None:
        await ctx.async_send_service(sid, {"num": 1})
    return _action


# ---- 按键定义 ----------------------------------------------------------

# (sid, key, name)
_BUTTONS: tuple[tuple[str, str, str], ...] = (
    ("button1", "button_1", "按键1"),
    ("button2", "button_2", "按键2"),
    ("button3", "button_3", "按键3"),
    ("button4", "button_4", "按键4"),
    ("button5", "button_5", "按键5"),
    ("button6", "button_6", "按键6"),
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

class Product23ETAdapter:
    """圆和六路场景智能开关 X9SC6 (23ET) 适配器."""

    prod_id = "23ET"

    def entities(self, context: DeviceContext) -> tuple[EntitySpec, ...]:
        profile = context.profile
        if profile is None:
            return ()

        entities: list[EntitySpec] = []

        # --- 6 个按键 -> button ------------------------------------------
        for sid, key, name in _BUTTONS:
            if not context.has_service(sid):
                continue
            if _field(profile, sid, "num") is None:
                continue
            entities.append(EntitySpec(
                platform="button",
                key=key,
                name=name,
                state=lambda _ctx: {},
                actions={"press": _press_action(sid)},
            ))

        # --- netInfo 诊断 ------------------------------------------------
        entities.extend(_net_info_entities(profile))

        return tuple(entities)


ADAPTER = Product23ETAdapter()
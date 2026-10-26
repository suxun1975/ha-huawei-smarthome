"""User-contributed protocol for Huawei product V0CK (华为智慧屏 KHAN-250S).

设备类型: 华为智慧屏 (HUAWEI Vision), 型号 KHAN-250S
制造商: 华为, 协议: WiFi

已暴露 (6 个实体):

  media_player (1):  智慧屏  <- devicestate.screenState
                     0 熄屏 -> "standby"
                     1 在线 -> "on"
                     2 离线 -> "off"
                     actions: turn_on / turn_off (写入 screenState=1/0)

  binary_sensor (1): 操控开关  <- remotecontrol.switchState
  binary_sensor (1): 遥控有效  <- remotecontrol.valid_time (diagnostic)
  sensor (3):        IP 地址 / 网关 MAC / 遥控器 MAC
                     <- remotecontrol.{ip_addr, gateway_mac, controller_mac}
                     diagnostic

故意不暴露:

  messageboard.*              留言板, sender/message/reply 各 1024 字符,
                              超出 HA sensor state 的 255 字符限制
  remotecontrol.access_token  认证 token, 敏感信息
  autoconfig.hms_login_info   HMS 登录校验信息, 敏感
  generalcommand.*            通用预留命令, 语义未知
  logreport.*                 Beta 日志上报, 调试用

media_player 契约来自 custom_components/huawei_smarthome/media_player.py:

  state  = spec.state(ctx).get("state")
  action = spec.actions.get(name) ->  name in {play, pause, stop, volume,
                                               next, previous, turn_on,
                                               turn_off, select_source}
  仅在 actions 里有对应 key 时才暴露 TURN_ON / TURN_OFF 等 feature

关于 screenState 的三态映射:

  HA 的 MediaPlayerEntity 标准状态有 STATE_ON / STATE_OFF /
  STATE_STANDBY / STATE_IDLE / STATE_PLAYING / STATE_PAUSED /
  STATE_BUFFERING. "熄屏" (0) 不是 "关机", 是屏幕关闭但设备在线,
  对应 STATE_STANDBY 最准确; "离线" (2) 才是 STATE_OFF.

  如果实测发现 "离线" 应该映射成 "unavailable" (让 HA 卡片变灰),
  把 _SCREEN_STATE_TO_MEDIA_STATE 的 2 改成 None 即可, HA 会显示
  为不可用. 但当前保留 "off", 让用户能看到"离线"这个明确状态.

关于 turn_on / turn_off 的保守性:

  screenState 的 permission 是 "RGP" (可写), 但云端是否真的把写入
  转发给智慧屏并改变屏幕状态, 需要实测. 如果点击 "开" 按钮后屏幕
  没反应, 说明写入路径不通, 可以从 actions 里去掉 turn_on / turn_off,
  media_player 卡片会变成纯状态展示 (无电源按钮).

关于 media_player 的 state 为 None 时:

  screenState 未上报时 state 返回 None, HA 会显示为 unavailable.
  这比显示 "off" 更诚实——设备确实还没上报状态, 而不是 "关着".
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


# ---- screenState <-> media_player.state ---------------------------------

# 0 熄屏 -> standby (设备在线但屏幕关闭)
# 1 在线 -> on
# 2 离线 -> off
_SCREEN_STATE_TO_MEDIA_STATE: dict[int, str] = {
    0: "standby",
    1: "on",
    2: "off",
}


def _media_player_state(context: DeviceContext) -> Mapping[str, Any]:
    value = _number(context.value("devicestate", "screenState"))
    if value is None:
        return {"state": None}
    return {"state": _SCREEN_STATE_TO_MEDIA_STATE.get(int(value))}


async def _turn_on(context: DeviceContext, _data: Mapping[str, Any]) -> None:
    await context.async_send_service("devicestate", {"screenState": 1})


async def _turn_off(context: DeviceContext, _data: Mapping[str, Any]) -> None:
    await context.async_send_service("devicestate", {"screenState": 0})


# ---- 适配器 ------------------------------------------------------------

class ProductV0CKAdapter:
    """华为智慧屏 KHAN-250S (V0CK) 适配器."""

    prod_id = "V0CK"

    def entities(self, context: DeviceContext) -> tuple[EntitySpec, ...]:
        profile = context.profile
        if profile is None:
            return ()

        entities: list[EntitySpec] = []

        # --- devicestate.screenState -> media_player 智慧屏 --------------
        if context.has_service("devicestate") and _field(
            profile, "devicestate", "screenState"
        ) is not None:
            entities.append(EntitySpec(
                platform="media_player",
                key="vision",
                name="智慧屏",
                state=_media_player_state,
                actions={
                    "turn_on": _turn_on,
                    "turn_off": _turn_off,
                },
            ))

        # --- remotecontrol.switchState -> binary_sensor 操控开关 ---------
        if context.has_service("remotecontrol") and _field(
            profile, "remotecontrol", "switchState"
        ) is not None:
            entities.append(EntitySpec(
                platform="binary_sensor",
                key="remote_control",
                name="操控开关",
                state=lambda ctx: {
                    "is_on": _as_bool(
                        ctx.value("remotecontrol", "switchState")
                    )
                },
                metadata={},
            ))

        # --- remotecontrol.valid_time -> binary_sensor 遥控有效 ----------
        if context.has_service("remotecontrol") and _field(
            profile, "remotecontrol", "valid_time"
        ) is not None:
            entities.append(EntitySpec(
                platform="binary_sensor",
                key="remote_valid",
                name="遥控有效",
                state=lambda ctx: {
                    "is_on": _as_bool(
                        ctx.value("remotecontrol", "valid_time")
                    )
                },
                metadata={"entity_category": "diagnostic"},
            ))

        # --- remotecontrol 诊断字段 -------------------------------------
        for field_name, key, label in (
            ("ip_addr", "ip_addr", "IP 地址"),
            ("gateway_mac", "gateway_mac", "网关 MAC"),
            ("controller_mac", "controller_mac", "遥控器 MAC"),
        ):
            if not context.has_service("remotecontrol"):
                continue
            if _field(profile, "remotecontrol", field_name) is None:
                continue
            entities.append(EntitySpec(
                platform="sensor",
                key=key,
                name=label,
                state=lambda ctx, _f=field_name: {
                    "native_value": _text(ctx.value("remotecontrol", _f))
                },
                metadata={"entity_category": "diagnostic"},
            ))

        return tuple(entities)


ADAPTER = ProductV0CKAdapter()
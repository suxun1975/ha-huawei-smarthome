"""User-contributed protocol for Huawei product X0A2 (华为AI音箱 2e).

设备类型: 华为AI音箱 2e (HUAWEI AI Speaker 2e), 型号 SKLK-00
制造商: 华为

相比 001T (Myna), 本设备不仅是音箱, 还是蓝牙 Mesh 网关, 多出了
bluetoothnode / discovery / BTIdle 三个服务.

已暴露 (5 个实体):

  binary_sensor (1): 在线        <- hwaccount.activeState
  sensor (1):        音箱状态    <- speakerState.State
  sensor (1):        蓝牙音频状态 <- BTIdle.BTIdle (diagnostic)
  media_player (1):  音箱        <- audioplayer.playState + smartspeaker.playControl
  switch (1):        发现模式    <- discovery.enable (config)

故意不暴露:

  bluetoothnode.*
     蓝牙网关的扫描、添加、配对参数 (scandevicemac / adddevicemac / 
     installcode / enable / stopdevicemac / setting 等). 
     在 HA 里做成实体无法展示扫描到的子设备列表, 也无法完成复杂的
     配对流程. 子设备管理应在智慧生活 App 中完成.

关于 smartspeaker.playControl 的枚举修正:

  官方 Profile 里 "上一首" 和 "下一首" 的 enumVal 都写成了 "2", 
  这明显是官方文档的复制粘贴错误。根据枚举递增规律 (0停/1播/2上), 
  "下一首" 的正确值应为 "3"。
  
  本适配器在 media_player 的 next/previous 动作中：
    - previous -> 发送 {"playControl": 2}
    - next     -> 发送 {"playControl": 3}

关于 BTIdle 的枚举:

  0 -> 空闲状态
  1 -> 音频状态 (蓝牙播放中)
  2 -> 通话忙碌 (蓝牙通话中)
  放在 diagnostic 类别, 方便用户知道当前蓝牙通道被谁占用.

关于 discovery.enable:

  开启后, 音箱进入蓝牙子设备发现模式 (相当于网关配网).
  暴露为 switch (config), 用户可以在 HA 里触发配对状态.
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


def _enum_label(value: Any, options: tuple[tuple[int, str], ...]) -> str | None:
    number = _number(value)
    if number is None:
        return None
    for enum_value, label in options:
        if number == enum_value:
            return label
    return None


# ---- 枚举选项 ----------------------------------------------------------

_SPEAKER_STATE_OPTIONS: tuple[tuple[int, str], ...] = (
    (0, "待机中"),
    (1, "拾音中"),
    (2, "等待响应"),
    (3, "语音播报"),
)

_BT_IDLE_OPTIONS: tuple[tuple[int, str], ...] = (
    (0, "空闲状态"),
    (1, "音频状态"),
    (2, "通话忙碌"),
)

# playState -> media_player.state
_PLAY_STATE_TO_MEDIA_STATE: dict[int, str] = {
    0: "paused",
    1: "playing",
    2: "idle",
}


# ---- 动作工厂 ----------------------------------------------------------

def _audioplayer_action(value: int):
    """生成 audioplayer 的控制动作 (播放/暂停/停止)."""
    async def _action(ctx: DeviceContext, _data: Mapping[str, Any]) -> None:
        await ctx.async_send_service("audioplayer", {"playState": value})
    return _action


def _smartspeaker_action(value: int):
    """生成 smartspeaker.playControl 的控制动作 (上一首/下一首)."""
    async def _action(ctx: DeviceContext, _data: Mapping[str, Any]) -> None:
        await ctx.async_send_service("smartspeaker", {"playControl": value})
    return _action


def _discovery_action(value: int):
    """生成 discovery.enable 的控制动作."""
    async def _action(ctx: DeviceContext, _data: Mapping[str, Any]) -> None:
        await ctx.async_send_service("discovery", {"enable": value})
    return _action


# ---- availability -------------------------------------------------------

def _speaker_available(context: DeviceContext) -> bool:
    """media_player 的可用性: activeState 为 0 或 None 时才可用."""
    value = _number(context.value("hwaccount", "activeState"))
    if value is None:
        return True
    return value == 0


# ---- 适配器 ------------------------------------------------------------

class ProductX0A2Adapter:
    """华为AI音箱 2e (X0A2) 适配器."""

    prod_id = "X0A2"

    def entities(self, context: DeviceContext) -> tuple[EntitySpec, ...]:
        profile = context.profile
        if profile is None:
            return ()

        entities: list[EntitySpec] = []

        # --- hwaccount.activeState -> binary_sensor 在线 -----------------
        if context.has_service("hwaccount") and _field(
            profile, "hwaccount", "activeState"
        ) is not None:
            entities.append(EntitySpec(
                platform="binary_sensor",
                key="online",
                name="在线",
                state=lambda ctx: {
                    "is_on": _number(ctx.value("hwaccount", "activeState")) == 0
                },
                metadata={"device_class": "connectivity"},
            ))

        # --- speakerState.State -> sensor 音箱状态 -----------------------
        if context.has_service("speakerState") and _field(
            profile, "speakerState", "State"
        ) is not None:
            entities.append(EntitySpec(
                platform="sensor",
                key="speaker_state",
                name="音箱状态",
                state=lambda ctx: {
                    "native_value": _enum_label(
                        ctx.value("speakerState", "State"),
                        _SPEAKER_STATE_OPTIONS,
                    )
                },
                metadata={"entity_category": "diagnostic"},
            ))

        # --- BTIdle.BTIdle -> sensor 蓝牙音频状态 ------------------------
        if context.has_service("BTIdle") and _field(
            profile, "BTIdle", "BTIdle"
        ) is not None:
            entities.append(EntitySpec(
                platform="sensor",
                key="bt_idle",
                name="蓝牙音频状态",
                state=lambda ctx: {
                    "native_value": _enum_label(
                        ctx.value("BTIdle", "BTIdle"),
                        _BT_IDLE_OPTIONS,
                    )
                },
                metadata={"entity_category": "diagnostic"},
            ))

        # --- discovery.enable -> switch 发现模式 (config) ----------------
        if context.has_service("discovery") and _field(
            profile, "discovery", "enable"
        ) is not None:
            entities.append(EntitySpec(
                platform="switch",
                key="discovery",
                name="发现模式",
                state=lambda ctx: {
                    "is_on": _number(ctx.value("discovery", "enable")) == 1
                },
                actions={
                    "turn_on": _discovery_action(1),
                    "turn_off": _discovery_action(0),
                },
                metadata={"entity_category": "config"},
            ))

        # --- media_player: audioplayer + smartspeaker -------------------
        if context.has_service("audioplayer") and _field(
            profile, "audioplayer", "playState"
        ) is not None:
            def _media_state(ctx: DeviceContext) -> Mapping[str, Any]:
                value = _number(ctx.value("audioplayer", "playState"))
                if value is None:
                    return {"state": None}
                return {"state": _PLAY_STATE_TO_MEDIA_STATE.get(int(value))}

            # 同时检查 smartspeaker 服务是否存在，以决定是否暴露切歌功能
            has_next_prev = context.has_service("smartspeaker") and _field(
                profile, "smartspeaker", "playControl"
            ) is not None

            actions = {
                "play": _audioplayer_action(1),
                "pause": _audioplayer_action(0),
                "stop": _audioplayer_action(2),
            }
            if has_next_prev:
                # 修正官方定义: 下一首为 3
                actions["previous"] = _smartspeaker_action(2)
                actions["next"] = _smartspeaker_action(3)

            entities.append(EntitySpec(
                platform="media_player",
                key="speaker",
                name="音箱",
                state=_media_state,
                actions=actions,
                availability=_speaker_available,
            ))

        return tuple(entities)


ADAPTER = ProductX0A2Adapter()
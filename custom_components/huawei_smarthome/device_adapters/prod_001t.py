"""User-contributed protocol for Huawei product 001T (华为AI音箱 Myna).

设备类型: 华为AI音箱 (AI Speaker), 型号 BSZHWFA001
制造商: 华为

4 个服务:

  hwaccount.activeState    enum RW  -1/1..7 未授权, 0 在线
  speakerState.State       enum R   0 待机中 / 1 拾音中 / 2 等待响应 / 3 语音播报
  smartspeaker.playControl enum RW  0 停止 / 1 播放 / 2 上一首 / 3 下一首 (修正厂家枚举)
  audioplayer.playState    enum RW  0 暂停 / 1 播放中 / 2 停止

已暴露 (3 个实体):

  binary_sensor (1): 在线      <- hwaccount.activeState  (is_on = value == 0)
                                 device_class: connectivity

  sensor (1):        音箱状态  <- speakerState.State
                                 待机中/拾音中/等待响应/语音播报, diagnostic

  media_player (1):  音箱      <- audioplayer.playState
                                 state: 0 paused / 1 playing / 2 idle
                                 actions: play / pause / stop / next / previous
                                 supported_features: PLAY / PAUSE / STOP / NEXT_TRACK / PREVIOUS_TRACK

关于 smartspeaker.playControl 的枚举修正:

  官方 Profile 里 "上一首" 和 "下一首" 的 enumVal 都写成了 "2", 
  这明显是官方文档的复制粘贴错误。根据枚举递增规律 (0停/1播/2上), 
  "下一首" 的正确值应为 "3"。
  
  本适配器在 media_player 的 next/previous 动作中：
    - previous -> 发送 {"playControl": 2}
    - next     -> 发送 {"playControl": 3}

关于 media_player 的 availability:

  只要 activeState 为 0 或 None 时可用。防止未授权时点按钮无效。

关于 action payload:

  audioplayer:
    play  -> {"playState": 1}
    pause -> {"playState": 0}
    stop  -> {"playState": 2}
  
  smartspeaker:
    previous -> {"playControl": 2}
    next     -> {"playControl": 3}
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

# playState -> media_player.state
_PLAY_STATE_TO_MEDIA_STATE: dict[int, str] = {
    0: "paused",
    1: "playing",
    2: "idle",
}


# ---- media_player 动作 --------------------------------------------------

def _audioplayer_action(value: int):
    """生成 audioplayer 的控制动作."""
    async def _action(ctx: DeviceContext, _data: Mapping[str, Any]) -> None:
        await ctx.async_send_service("audioplayer", {"playState": value})
    return _action


def _smartspeaker_action(value: int):
    """生成 smartspeaker.playControl 的控制动作 (上一首/下一首)."""
    async def _action(ctx: DeviceContext, _data: Mapping[str, Any]) -> None:
        await ctx.async_send_service("smartspeaker", {"playControl": value})
    return _action


# ---- media_player availability -----------------------------------------

def _speaker_available(context: DeviceContext) -> bool:
    """media_player 的可用性: activeState 为 0 或 None 时才可用."""
    value = _number(context.value("hwaccount", "activeState"))
    if value is None:
        return True
    return value == 0


# ---- 适配器 ------------------------------------------------------------

class Product001TAdapter:
    """华为AI音箱 Myna (001T) 适配器."""

    prod_id = "001T"

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


ADAPTER = Product001TAdapter()

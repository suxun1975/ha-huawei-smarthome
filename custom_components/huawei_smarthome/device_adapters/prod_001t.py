"""User-contributed protocol for Huawei product 001T (华为AI音箱 Myna).

设备类型: 华为AI音箱 (AI Speaker), 型号 BSZHWFA001
制造商: 华为

4 个服务:

  hwaccount.activeState    enum RW  -1/1..7 未授权, 0 在线
  speakerState.State       enum R   0 待机中 / 1 拾音中 / 2 等待响应 / 3 语音播报
  smartspeaker.playControl enum RW  0 停止 / 1 播放 / 2 上一首 / 2 下一首 (值重复!)
  audioplayer.playState    enum RW  0 暂停 / 1 播放中 / 2 停止

已暴露 (3 个实体):

  binary_sensor (1): 在线      <- hwaccount.activeState  (is_on = value == 0)
                                 device_class: connectivity

  sensor (1):        音箱状态  <- speakerState.State
                                 待机中/拾音中/等待响应/语音播报, diagnostic

  media_player (1):  音箱      <- audioplayer.playState
                                 state: 0 paused / 1 playing / 2 idle
                                 actions: play (->1) / pause (->0) / stop (->2)
                                 supported_features: PLAY / PAUSE / STOP
                                 availability: activeState in (None, 0)

故意不暴露:

  smartspeaker.playControl   Profile 里"上一首"和"下一首"共用 enumVal "2",
                             适配器无法区分, 只保留 audioplayer.playState
                             做播放/暂停/停止.

关于 media_player 的 state 映射:

  HA 的 MediaPlayerState 标准值有 OFF / ON / IDLE / PLAYING /
  PAUSED / BUFFERING / STANDBY. 三个映射:
    0 暂停   -> "paused"   (PAUSED)
    1 播放中 -> "playing"  (PLAYING)
    2 停止   -> "idle"     (IDLE)

  "停止" 用 "idle" 而不是 "off", 因为音箱本身没有"关机"概念——
  它一直在线待命, 只是没在播放. "off" 会让用户误以为音箱断电.

关于 media_player 的 availability:

  media_player.py 的 AdapterEntityMixin.available 先看 spec.availability,
  有就用它, 没有就用 context.available (设备 online). 音箱有两个层面:
    - 设备 online (context.available): 华为云连接层
    - 账号授权 (hwaccount.activeState == 0): 华为账号授权层

  即使设备 online, 如果 activeState != 0 (未授权), 播放控制指令
  也无法下发到云端. 所以 media_player 的 availability 额外要求
  activeState 为 0 或 None:

    None       -> 设备还没上报 activeState, 保持可用 (避免刚启动全灰)
    0          -> 在线, 可用
    -1/1..7    -> 未授权, 不可用, 卡片变灰

  这样用户看到"音箱已离线"或"账号未授权"时不会点一个必然失败的按钮.
  注意: 只给 media_player 加了 availability, binary_sensor "在线" 和
  sensor "音箱状态" 不加——它们本身就是用来反映"在线/离线"的状态,
  离线时也要显示"离线", 不能变灰.

关于 media_player 的 action payload:

  media_player.py 的 async_media_play / async_media_pause /
  async_media_stop 都调用 _run_action(name, {}), 传入空 dict. 适配器
  的 action 函数忽略 data, 直接发送固定 payload:
    play  -> {"playState": 1}
    pause -> {"playState": 0}
    stop  -> {"playState": 2}

  三个 action 用 _play_state_action(value) 工厂生成, 与 2MJD 的
  _switch_action(sid, field, value) / _media_key_press(sid, value)
  风格统一.

关于 speakerState 保留为 sensor:

  speakerState.State 是只读字段, 描述音箱当前在做什么
  (待机/拾音/等待响应/语音播报), 对用户有诊断价值——能知道音箱
  现在是否在听、是否在回应. 但 media_player 的 state 字段已经被
  playState 占用, 无法同时表达 speakerState, 所以单独做成 sensor.

关于 activeState 的 enumList:

  只有 enumVal 0 是 "在线", 其他 -1/1..7 全部是 "未授权". 做成
  binary_sensor 的 is_on = (value == 0) 比枚举 sensor 更直观——
  用户只关心"在线"还是"未授权", 不需要区分 -1 和 1~7 这 8 种
  未授权子状态.
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


# ---- media_player 动作工厂 ----------------------------------------------

def _play_state_action(value: int):
    """生成一个 media_player 的 play/pause/stop 动作.

    media_player.py 的 async_media_play / async_media_pause /
    async_media_stop 都调用 _run_action(name, {}), 传入空 dict.
    适配器忽略 data, 发送固定 {"playState": value} 到 audioplayer.
    """
    async def _action(ctx: DeviceContext, _data: Mapping[str, Any]) -> None:
        await ctx.async_send_service("audioplayer", {"playState": value})
    return _action


# ---- media_player availability -----------------------------------------

def _speaker_available(context: DeviceContext) -> bool:
    """media_player 的可用性: activeState 为 0 或 None 时才可用.

    None: 设备还没上报 activeState, 保持可用, 避免刚启动时实体全灰
    0:    在线, 可用
    其他: 未授权, 卡片变灰, 用户不会点一个必然失败的操作
    """
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

        # --- audioplayer.playState -> media_player 音箱 -----------------
        if context.has_service("audioplayer") and _field(
            profile, "audioplayer", "playState"
        ) is not None:
            def _media_state(ctx: DeviceContext) -> Mapping[str, Any]:
                value = _number(ctx.value("audioplayer", "playState"))
                if value is None:
                    return {"state": None}
                return {"state": _PLAY_STATE_TO_MEDIA_STATE.get(int(value))}

            entities.append(EntitySpec(
                platform="media_player",
                key="speaker",
                name="音箱",
                state=_media_state,
                actions={
                    "play": _play_state_action(1),
                    "pause": _play_state_action(0),
                    "stop": _play_state_action(2),
                },
                availability=_speaker_available,
            ))

        return tuple(entities)


ADAPTER = Product001TAdapter()
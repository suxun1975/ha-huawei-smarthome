"""User-contributed protocol for Huawei product 2QEF (三诺智能语音开关 SSP-YYK2-2C-AG).

设备类型: 语音面板 (Voice panel), 型号 SSP-YYK2-2C-AG
制造商: 三诺 (3Nod), 协议: WiFi

这是一个"语音中控面板", Profile 约 80 个服务, 覆盖开关/按键/语音助手/
音箱/网关/场景管理/分组/蓝牙/OTA 等几乎所有品类. 按"宁可不出, 也不出
永久空白实体"的原则, 只暴露有明确状态语义、report:1 会上报、且对 HA
用户有实际价值的字段.

已暴露 (28 个实体):

  switch (9):
    开关1 / 开关2              <- switch1.on / switch2.on  (主)
    背光                       <- backlight.on            (config)
    麦克风静音                 <- microphone.mute         (config)
    童锁                       <- childLockSwitch.on      (config)
    环形灯                     <- lightRing.on            (config)
    断电记忆                   <- memorySwitch.on         (config)
    协同唤醒                   <- nearbyWakeup.on         (config)
    静默模式                   <- quietMode.on            (config)

  button (6):
    按键1 单击                 <- button1.on, 发送 {"on": 1}
    按键1 双击                 <- scene.DoubleClick, 发送 {"DoubleClick": 1}
    按键1 长按                 <- scene.LongClick, 发送 {"LongClick": 1}
    按键2 单击                 <- button2.on, 发送 {"on": 1}
    按键2 双击                 <- scene.DoubleClick, 发送 {"DoubleClick": 2}
    按键2 长按                 <- scene.LongClick, 发送 {"LongClick": 2}

  event (1):
    按键事件                   <- scene.num / DoubleClick / LongClick
                                event_types: single_click / double_click / long_click
                                物理按键时触发, 用于"设备 -> HA"方向

  number (3):
    亮度                       <- brightness.brightness   (0~100, config)
    音量                       <- smartspeaker.volume     (0~100, config)
    灯光档位                   <- lightLevel.level        (1~3, config)

  sensor (9):
    静默开始 / 静默结束        <- quietMode.beginTime / endTime
                                分钟数转 HH:MM, diagnostic
    故障码                     <- commonFaultDetection.code
    信号强度 / 信号等级 / Wi-Fi 名称 / IP 地址 / BSSID / Wi-Fi 频段
                                <- netInfo.*, diagnostic

故意不暴露的约 55 个服务 (只列类别, 不逐一展开):

  场景管理 (autoScene/manualScene/sceneManage/sceneOperation/clickedScene)
  批控与分组 (batchCmd/group1~25/groupControl/groupManage)
  蓝牙与子设备 (bluetooth/bt/connectDev/devList/discovery)
  音箱能力 (speaker/speakerAlarm/speakerIfttt/speakerState)
  语音助手 (voiceAssist/voiceAssistDevInfo/wakeUp/wakeupVerifyMode/preWakeUp)
  账号与日志 (hwaccount/logReport)
  内部协议 (mode1/mode2/localCommand/msgRsp/homeGatewayCap/capacity/changeDirection)
  只写字段 (homeBroadcast.text/communication.directive)
  维护动作 (reboot/update)

关于按键的单击 / 双击 / 长按:

  2QEF 有两个按键服务, 职责不同:
    button1 / button2: 只有 on 字段 (RW), 写入 {"on": 1} 触发按键动作.
                       设备按它自己配置的模式 (单击/双击/长按) 执行,
                       但 HA 无法指定是哪一种.
    scene:             按键记录, num / DoubleClick / LongClick 三个字段.
                       设备物理按键时按实际动作上报其中一个.

  本适配器用两种路径实现三种按键:
    单击: 写 button{N}.on = 1     (Profile 明确支持, 可靠)
    双击: 写 scene.DoubleClick = N (permission=RW, 但语义是"按键记录",
                                    写入是否触发设备双击动作需要实测)
    长按: 写 scene.LongClick = N   (同上)

  如果实测发现写入 scene.DoubleClick / scene.LongClick 无效 (设备只
  更新记录, 不执行对应动作), 对应 button 会"点了没反应". 此时有两种
  处理:
    1. 删除 _BUTTON_ACTIONS 里对应的双击/长按记录, 实体数从 28 减少
    2. 保留 button 但改为发送 button{N}.on = 1 (与单击相同), 用户
       如果想用双击/长按, 在物理按键时通过 event.按键事件 的
       event_type 触发自动化

  物理按键时 event.按键事件 会触发 single_click / double_click /
  long_click, 与 HA 主动触发的 button 是两条独立路径:
    - 设备 -> HA: 物理按键 -> event 触发 -> 自动化
    - HA -> 设备: 点 button -> 发送指令 -> 设备执行

关于 button1.on / button2.on 的 characteristicType:

  Profile 里这两个字段的 characteristicType 是 "characteristic.backlight.on",
  但实际语义是"按键" (从 attrName 和服务名看). 适配器不关心
  characteristicType, 只看 characteristicName, 所以不受影响.

关于 scene 的 event:

  scene.num / DoubleClick / LongClick 与 ZG2N 的 scene 服务完全一致,
  复用同样的 event_decoder 逻辑: 单击/双击/长按分别触发 single_click /
  double_click / long_click, event_data 带 button 编号.

关于 quietMode 的时间格式化:

  beginTime / endTime 是"按时间分钟数取值", 0~1439. 直接显示 1410 用户
  不知道是 23:30, 所以格式化成 "HH:MM". sensor 的 native_value 是字符串,
  HA 会显示为文本.

关于 microphone.mute 的语义:

  mute=1 表示静音 (麦克风关闭), is_on=True 表示静音激活.
  turn_on 发送 {"mute": 1}, turn_off 发送 {"mute": 0}.
  与 2MJD 的 mute 处理逻辑一致.

  麦克风静音在 _SWITCHES 表里用 field_name="mute" 标记, 与 on 字段的
  其他 switch 统一处理.

关于 commonFaultDetection.code:

  Profile 里没有 enumList, 是 characteristic.fault.code 类型, 直接显示
  原始值. 如果值是 0 显示 "0", 非 0 显示具体数字.

关于 number 的 min/max:

  brightness / volume 没有声明 min/max, 按 HA 的常见约定给 0~100.
  lightLevel.level 从 attrName "云雀：默认2（高档）火烈鸟：默认1（明亮）"
  推断是 1~3 档, 给 1~3.

关于 _flag_value 的命名:

  与 2BE5 / 2BE6 / 2BE8 / 2GB1 / 2MKS 的 _flag_value 命名和实现
  完全一致, 六个适配器风格统一.
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

def _flag_value(value: Any) -> bool | None:
    """严格解析 bool: 接受 0/1, 字符串 "0"/"1"/"true"/"false"/"on"/"off",
    以及 JSON 布尔 true/false, 其它返回 None.

    与 2BE5 / 2BE6 / 2BE8 / 2GB1 / 2MKS 的 _flag_value 命名和实现
    完全一致, 六个适配器风格统一.
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


def _minutes_to_hhmm(value: Any) -> str | None:
    number = _number(value)
    if number is None:
        return None
    if number < 0 or number >= 24 * 60:
        return None
    hours = int(number) // 60
    minutes = int(number) % 60
    return f"{hours:02d}:{minutes:02d}"


# ---- 枚举选项 ----------------------------------------------------------

_NET_INTENSITY_OPTIONS: tuple[tuple[int, str], ...] = (
    (20, "0格信号"),
    (40, "1格信号"),
    (60, "2格信号"),
    (80, "3格信号"),
    (100, "4格信号"),
)
_NET_BAND_OPTIONS: tuple[tuple[int, str], ...] = (
    (1, "2.4G"),
    (2, "5G"),
)


# ---- event decoder ------------------------------------------------------

# scene 字段名 -> event_type
_SCENE_FIELD_TO_EVENT: tuple[tuple[str, str], ...] = (
    ("num", "single_click"),
    ("DoubleClick", "double_click"),
    ("LongClick", "long_click"),
)


def _scene_event_decoder(
    _context: DeviceContext,
    sid: str,
    data: Mapping[str, Any],
    _timestamp: str | None,
) -> Iterable[tuple[str, Mapping[str, Any]]]:
    """把 scene 服务的上报解码为按键事件."""
    if sid != "scene":
        return
    for field_name, event_type in _SCENE_FIELD_TO_EVENT:
        if field_name not in data:
            continue
        button = _number(data[field_name])
        if button is None:
            continue
        yield event_type, {"button": int(button)}


# ---- 写动作工厂 ---------------------------------------------------------

def _switch_action(sid: str, field: str, value: int):
    """生成一个 switch 的 turn_on/turn_off 动作.

    统一处理 on 字段 (电源/背光/童锁/环形灯/记忆/协同唤醒/静默模式)
    和 mute 字段 (麦克风静音).
    """
    async def _action(ctx: DeviceContext, _data: Mapping[str, Any]) -> None:
        await ctx.async_send_service(sid, {field: value})
    return _action


def _button_action(sid: str, field: str, value: int):
    """生成一个 button 的 press 动作.

    单击: sid="button1", field="on",        value=1 -> 发送 {"on": 1}
    双击: sid="scene",   field="DoubleClick", value=1 -> 发送 {"DoubleClick": 1}
    长按: sid="scene",   field="LongClick",   value=1 -> 发送 {"LongClick": 1}

    双击/长按写入 scene 是否触发设备动作, 需要实测.
    如果实测无效, 删除 _BUTTON_ACTIONS 里对应记录即可.
    """
    async def _action(ctx: DeviceContext, _data: Mapping[str, Any]) -> None:
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


# ---- 实体定义表 ---------------------------------------------------------

# (sid, key, name, field_name, config)
#   field_name = "on"   -> 电源/配置开关 (发送 {"on": 1/0})
#   field_name = "mute" -> 麦克风静音 (发送 {"mute": 1/0})
#   config = True       -> 归入 entity_category=config
_SWITCHES: tuple[tuple[str, str, str, str, bool], ...] = (
    ("switch1", "switch_1", "开关1", "on", False),
    ("switch2", "switch_2", "开关2", "on", False),
    ("backlight", "backlight", "背光", "on", True),
    ("microphone", "microphone_mute", "麦克风静音", "mute", True),
    ("childLockSwitch", "child_lock", "童锁", "on", True),
    ("lightRing", "light_ring", "环形灯", "on", True),
    ("memorySwitch", "memory_switch", "断电记忆", "on", True),
    ("nearbyWakeup", "nearby_wakeup", "协同唤醒", "on", True),
    ("quietMode", "quiet_mode", "静默模式", "on", True),
)

# ---- 按键定义: 每个按键 3 个 button (单击 / 双击 / 长按) -----------------

# 单击: 写 button{N}.on            = 1, 触发按键动作 (Profile 明确支持)
# 双击: 写 scene.DoubleClick       = N, 触发双击动作 (permission=RW, 需实测)
# 长按: 写 scene.LongClick         = N, 触发长按动作 (permission=RW, 需实测)
#
# 如果实测发现写入 scene.DoubleClick / scene.LongClick 无效 (设备只更新
# 记录, 不执行动作), 删除下面两条对应记录, 实体数从 28 减少到 26 或 24.

# (sid, field, value, key, name)
_BUTTON_ACTIONS: tuple[tuple[str, str, int, str, str], ...] = (
    # 按键1
    ("button1", "on",          1, "button_1_single", "按键1 单击"),
    ("scene",   "DoubleClick", 1, "button_1_double", "按键1 双击"),
    ("scene",   "LongClick",   1, "button_1_long",   "按键1 长按"),
    # 按键2
    ("button2", "on",          1, "button_2_single", "按键2 单击"),
    ("scene",   "DoubleClick", 2, "button_2_double", "按键2 双击"),
    ("scene",   "LongClick",   2, "button_2_long",   "按键2 长按"),
)

# (sid, field, key, name, min_v, max_v, step)
_NUMBERS: tuple[tuple[str, str, str, str, float, float, float], ...] = (
    ("brightness", "brightness", "brightness", "亮度", 0, 100, 1),
    ("smartspeaker", "volume", "volume", "音量", 0, 100, 1),
    ("lightLevel", "level", "light_level", "灯光档位", 1, 3, 1),
)


# ---- 实体构建函数 -------------------------------------------------------

def _switch_entities(
    context: DeviceContext, profile: Any
) -> list[EntitySpec]:
    """统一的 switch 构建: 电源 / 背光 / 麦克风静音 / 童锁 / 环形灯 /
    断电记忆 / 协同唤醒 / 静默模式.
    """
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
                "is_on": _flag_value(ctx.value(_s, _f))
            },
            actions={
                "turn_on": _switch_action(sid, field_name, 1),
                "turn_off": _switch_action(sid, field_name, 0),
            },
            metadata=metadata,
        ))
    return entities


def _button_entities(
    context: DeviceContext, profile: Any
) -> list[EntitySpec]:
    """每个按键 3 个 button: 单击 (button{N}.on) +
    双击 (scene.DoubleClick) + 长按 (scene.LongClick)."""
    entities: list[EntitySpec] = []
    for sid, field, value, key, name in _BUTTON_ACTIONS:
        if not context.has_service(sid):
            continue
        if _field(profile, sid, field) is None:
            continue
        entities.append(EntitySpec(
            platform="button",
            key=key,
            name=name,
            state=lambda _ctx: {},
            actions={"press": _button_action(sid, field, value)},
        ))
    return entities


def _event_entity(
    context: DeviceContext, profile: Any
) -> list[EntitySpec]:
    if not context.has_service("scene"):
        return []
    if not any(_field(profile, "scene", n) is not None for n, _ in _SCENE_FIELD_TO_EVENT):
        return []
    return [EntitySpec(
        platform="event",
        key="button_event",
        name="按键事件",
        state=lambda _ctx: {},
        event_decoder=_scene_event_decoder,
        metadata={
            "device_class": "button",
            "event_types": [event for _, event in _SCENE_FIELD_TO_EVENT],
        },
    )]


def _number_entities(
    context: DeviceContext, profile: Any
) -> list[EntitySpec]:
    entities: list[EntitySpec] = []
    for sid, field, key, name, min_v, max_v, step in _NUMBERS:
        if not context.has_service(sid):
            continue
        if _field(profile, sid, field) is None:
            continue
        entities.append(EntitySpec(
            platform="number",
            key=key,
            name=name,
            state=lambda ctx, _s=sid, _f=field: {
                "native_value": _number(ctx.value(_s, _f))
            },
            actions={"set_value": _number_action(sid, field)},
            metadata={
                "min": min_v,
                "max": max_v,
                "step": step,
                "entity_category": "config",
            },
        ))
    return entities


def _quiet_time_sensors(
    context: DeviceContext, profile: Any
) -> list[EntitySpec]:
    if not context.has_service("quietMode"):
        return []
    entities: list[EntitySpec] = []
    for field_name, key, label in (
        ("beginTime", "quiet_begin", "静默开始"),
        ("endTime", "quiet_end", "静默结束"),
    ):
        if _field(profile, "quietMode", field_name) is None:
            continue
        entities.append(EntitySpec(
            platform="sensor",
            key=key,
            name=label,
            state=lambda ctx, _f=field_name: {
                "native_value": _minutes_to_hhmm(ctx.value("quietMode", _f))
            },
            metadata={"entity_category": "diagnostic"},
        ))
    return entities


def _fault_sensor(
    context: DeviceContext, profile: Any
) -> list[EntitySpec]:
    if not context.has_service("commonFaultDetection"):
        return []
    if _field(profile, "commonFaultDetection", "code") is None:
        return []
    return [EntitySpec(
        platform="sensor",
        key="fault_code",
        name="故障码",
        state=lambda ctx: {
            "native_value": _text(ctx.value("commonFaultDetection", "code"))
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

class Product2QEFAdapter:
    """三诺智能语音开关 SSP-YYK2-2C-AG (2QEF) 适配器."""

    prod_id = "2QEF"

    def entities(self, context: DeviceContext) -> tuple[EntitySpec, ...]:
        profile = context.profile
        if profile is None:
            return ()

        entities: list[EntitySpec] = []
        entities.extend(_switch_entities(context, profile))
        entities.extend(_button_entities(context, profile))
        entities.extend(_event_entity(context, profile))
        entities.extend(_number_entities(context, profile))
        entities.extend(_quiet_time_sensors(context, profile))
        entities.extend(_fault_sensor(context, profile))
        entities.extend(_net_info_entities(profile))
        return tuple(entities)


ADAPTER = Product2QEFAdapter()
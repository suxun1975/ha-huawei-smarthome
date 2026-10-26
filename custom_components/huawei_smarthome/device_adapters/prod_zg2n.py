"""User-contributed protocol for Huawei product ZG2N (迈腾智能开关（电池版）2键 PCP-OB2006).

设备类型: 开关 (Switch), 型号 PCP-OB2006
制造商: 华为 (HUAWEI), 协议: 13 (鸿蒙/星闪)

设备是"按键/场景面板", 不是"电源开关". 两个物理按键, 每个按键可绑定
0..20 的场景编号, 支持单击/双击/长按三种操作.

Profile 的完整语义:

  button1.num       int RW 0..20   按键1绑定的场景编号 (0=未绑定)
  button1.name      str RW 16字符  按键1名称
  button2.num       int RW 0..20   按键2绑定的场景编号
  button2.name      str RW 16字符  按键2名称

  scene.num         int RW 0..20   单击上报的按键编号 (即绑定的场景编号)
  scene.DoubleClick int RW 0..20   双击上报的按键编号
  scene.LongClick   int RW 0..20   长按上报的按键编号

已暴露 (11 个实体):

  number (2):   按键1编号 / 按键2编号
                <- button1.num / button2.num
                0..20, 可编辑, 0 表示未绑定, 1..20 绑定到场景 1..20

  sensor (2):   按键1名称 / 按键2名称
                <- button1.name / button2.name
                只读展示设备侧配置的名称, diagnostic

  button (6):   按键1 单击 / 按键1 双击 / 按键1 长按
                按键2 单击 / 按键2 双击 / 按键2 长按
                发送逻辑见"关于按键的单击/双击/长按"

  event (1):    按键事件
                <- scene.num / DoubleClick / LongClick
                event_types: single_click / double_click / long_click
                event_data: {"button": <按键编号>}
                device_class: button
                物理按键时触发, 用于"设备 -> HA"方向

故意不暴露:

  update.*   OTA

关于按键的单击 / 双击 / 长按:

  ZG2N 和 2QEF 的按键服务不同:
    2QEF: button1.on 是 bool, 发送 {"on": 1} 触发单击
    ZG2N: button1.num 是 int 0..20, 发送 {"num": N} 触发按键N的单击

  所以 ZG2N 的"单击"button 发送的是当前绑定的场景编号, 不是固定的 1:

    按键1 单击 -> 读 button1.num (如 5) -> 发送 {"num": 5} 到 button1
    按键1 双击 -> 读 button1.num (如 5) -> 发送 {"DoubleClick": 5} 到 scene
    按键1 长按 -> 读 button1.num (如 5) -> 发送 {"LongClick": 5} 到 scene
    按键2 单击 -> 读 button2.num (如 8) -> 发送 {"num": 8} 到 button2
    按键2 双击 -> 读 button2.num (如 8) -> 发送 {"DoubleClick": 8} 到 scene
    按键2 长按 -> 读 button2.num (如 8) -> 发送 {"LongClick": 8} 到 scene

  这和 scene 服务的上报语义一致: 设备按下按键1 (绑定场景5) 时上报
  scene.num=5 (不是 scene.num=1). 所以 HA 主动触发时也应该发送 5,
  而不是 1.

  为什么双击/长按发送到 scene 而不是 button{N}:
    button{N}.num 只有一个字段, 写入它触发的是"单击"动作.
    要表达"双击"/"长按", 只能写入 scene.DoubleClick / scene.LongClick.

  ⚠️ 重要: 写入 scene.DoubleClick / scene.LongClick 是否真的触发
  设备的双击/长按动作, 需要实测. 两种可能:

    可能 1: 设备固件监听 scene.DoubleClick 的写入, 执行双击逻辑
            -> 方案成立, 6 个 button 全部可用

    可能 2: 设备把 scene 当只读, 写入被忽略或只更新记录
            -> 双击/长按 button 点了没反应, 需要删除

  如果实测发现双击/长按无效, 删除 _BUTTON_ACTIONS 里的 4 条对应
  记录, 退回只保留 2 个单击 button. 实体数从 11 减到 7.

  物理按键时 event.按键事件 会触发 single_click / double_click /
  long_click, 与 HA 主动触发的 button 是两条独立路径:
    - 设备 -> HA: 物理按键 -> event 触发 -> 自动化
    - HA -> 设备: 点 button -> 发送指令 -> 设备执行

关于 _press_action 的兜底行为:

  点击 按键{N} 单击/双击/长按 时, 从 context.value("button{N}", "num")
  读取当前绑定编号. 两种情况会退化为发送 1:

    1. 设备从未上报 button{N}.num (context.value 返回 None)
    2. 设备上报 button{N}.num = 0 (未绑定)

  退化为 1 的理由: 发送 0 对设备没有意义 (0 = 未绑定), 退化为场景 1
  至少能触发一个场景. 但这意味着用户点"按键1 单击"实际触发的是场景 1,
  而不是用户以为的场景 (比如 5).

  为了帮助用户排查, 退化时会在日志里 warning:

    WARNING ... ZG2N button1.num 未上报或为 0 (当前 None),
    退化为发送 5 到 scene.DoubleClick. 请确认设备已上报当前绑定编号.

  如果日志里反复出现这条 warning, 说明:
    - 设备确实不上报 button{N}.num (permission 是 RW, 没有 GR,
      网关可能不订阅)
    - 用户在 App 里把按键设为了"未绑定"

  这是设备/网关行为, 适配器只能提示, 无法修复.

关于 event 平台的 "事件不可见" 现象:

  event 实体在 HA 卡片上不显示"下拉框"或"滑块", 只在事件触发时更新
  时间戳和属性. 用户可能以为"没生效", 实际是:
    1. event 实体需要在 自动化 -> 触发器 -> 状态 里选择, 或
    2. 在 开发者工具 -> 事件 里监听 state_changed 查看 event_type
    3. 在 开发者工具 -> 模板 里查询 states.event.按键事件.attributes

  如果物理按键按下后 event 实体没更新, 说明设备不主动上报 scene
  服务 (permission 是 RW 而非 GR, 网关可能不订阅). 这是设备/网关
  行为, 适配器无法修复.

关于 number 的 range 0..20:

  0 表示"未绑定", 1..20 表示"绑定到场景 1..20". 用户设为 0 相当于
  "解绑按键". 这与 23ET 场景面板 (button{N}.num 固定为 1) 不同,
  ZG2N 的按键编号是真正可配置的.

  _number_action 严格限制在 0..20, 超出范围静默丢弃, 不发到设备.

关于 battery:

  设备名是"智能开关（电池版）", 但 Profile 里没有 battery 服务.
  电池信息可能通过鸿蒙通用的"设备电量"上报 (不在这个 Profile 里),
  或者只在智慧生活 App 里显示. 适配器层无法读取, 不暴露.

关于 button{N}.name 用 sensor 而非 text:

  name 的 permission 是 "RW", 理论上可以用 text 平台让用户编辑.
  但设备侧的按键名称是配置标签, HA 侧用实体重命名即可. 暴露为
  可写 text 会多一个实体, 且需要用户理解"这是设备侧名称, 改了会
  同步到 App"的语义. 与 2MJD / 23ET 的取舍一致.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from typing import Any

from .api import EntitySpec
from .context import DeviceContext

_LOGGER = logging.getLogger(__name__)


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
    """把 scene 服务的上报解码为按键事件.

    data 里可能同时包含 num / DoubleClick / LongClick 中的任意组合
    (设备按实际按键方式只填其中一项). 对每个非 None 字段产生一个事件,
    event_data 带上按键编号, 方便自动化判断"是哪个键".
    """
    if sid != "scene":
        return
    for field_name, event_type in _SCENE_FIELD_TO_EVENT:
        if field_name not in data:
            continue
        button = _number(data[field_name])
        if button is None:
            continue
        yield event_type, {"button": int(button)}


# ---- 写动作 --------------------------------------------------------------

# (source_sid, target_sid, target_field, key, name)
#   source_sid: 从哪个按键的 num 字段读绑定编号
#   target_sid: 发送到哪个服务
#   target_field: 发送的字段名
_BUTTON_ACTIONS: tuple[tuple[str, str, str, str, str], ...] = (
    # 按键1
    ("button1", "button1", "num", "button1_single", "按键1 单击"),
    ("button1", "scene", "DoubleClick", "button1_double", "按键1 双击"),
    ("button1", "scene", "LongClick", "button1_long", "按键1 长按"),
    # 按键2
    ("button2", "button2", "num", "button2_single", "按键2 单击"),
    ("button2", "scene", "DoubleClick", "button2_double", "按键2 双击"),
    ("button2", "scene", "LongClick", "button2_long", "按键2 长按"),
)


def _press_action(source_sid: str, target_sid: str, target_field: str):
    """点击按钮时, 读取 source_sid.num 的当前绑定编号, 发送到 target_sid.

    三种场景:
      单击: 读 button1.num -> 发送 {"num": 5} 到 button1
      双击: 读 button1.num -> 发送 {"DoubleClick": 5} 到 scene
      长按: 读 button1.num -> 发送 {"LongClick": 5} 到 scene

    如果 num 未上报或为 0, 退化为 1, 并在日志里 warning.
    """
    async def _action(ctx: DeviceContext, _data: Mapping[str, Any]) -> None:
        raw = ctx.value(source_sid, "num")
        num = _number(raw)
        if num is None or num < 1:
            _LOGGER.warning(
                "ZG2N %s.num 未上报或为 0 (当前 %r), 退化为发送 "
                "{%r: 1} 到 %s. 请确认设备已上报当前绑定编号.",
                source_sid,
                raw,
                target_field,
                target_sid,
            )
            num = 1
        await ctx.async_send_service(target_sid, {target_field: int(num)})
    return _action


def _number_action(sid: str, field: str):
    """把 number 实体编辑的值写回设备."""
    async def _action(ctx: DeviceContext, data: Mapping[str, Any]) -> None:
        value = data.get("value")
        if value is None:
            return
        try:
            int_value = int(round(float(value)))
        except (TypeError, ValueError):
            return
        # 严格限制在 Profile 的 0..20
        if int_value < 0 or int_value > 20:
            return
        await ctx.async_send_service(sid, {field: int_value})
    return _action


# ---- 适配器 ------------------------------------------------------------

class ProductZG2NAdapter:
    """迈腾智能开关（电池版）2键 PCP-OB2006 (ZG2N) 适配器."""

    prod_id = "ZG2N"

    def entities(self, context: DeviceContext) -> tuple[EntitySpec, ...]:
        profile = context.profile
        if profile is None:
            return ()

        entities: list[EntitySpec] = []

        # --- 按键1 / 按键2 的编号 (number, 可编辑) -----------------------
        for sid, key, label in (
            ("button1", "button1_num", "按键1编号"),
            ("button2", "button2_num", "按键2编号"),
        ):
            if not context.has_service(sid):
                continue
            if _field(profile, sid, "num") is None:
                continue
            entities.append(EntitySpec(
                platform="number",
                key=key,
                name=label,
                state=lambda ctx, _s=sid: {
                    "native_value": _number(ctx.value(_s, "num"))
                },
                actions={"set_value": _number_action(sid, "num")},
                metadata={
                    "min": 0,
                    "max": 20,
                    "step": 1,
                    "entity_category": "config",
                },
            ))

        # --- 按键1 / 按键2 的名称 (sensor, 只读展示) ---------------------
        for sid, key, label in (
            ("button1", "button1_name", "按键1名称"),
            ("button2", "button2_name", "按键2名称"),
        ):
            if not context.has_service(sid):
                continue
            if _field(profile, sid, "name") is None:
                continue
            entities.append(EntitySpec(
                platform="sensor",
                key=key,
                name=label,
                state=lambda ctx, _s=sid: {
                    "native_value": _text(ctx.value(_s, "name"))
                },
                metadata={"entity_category": "diagnostic"},
            ))

        # --- 按键1/2 的单击/双击/长按 (6 个 button) ---------------------
        for source_sid, target_sid, target_field, key, name in _BUTTON_ACTIONS:
            if not context.has_service(source_sid):
                continue
            if _field(profile, source_sid, "num") is None:
                continue
            # 双击/长按需要 scene 服务存在
            if target_sid == "scene":
                if not context.has_service("scene"):
                    continue
                if _field(profile, "scene", target_field) is None:
                    continue
            entities.append(EntitySpec(
                platform="button",
                key=key,
                name=name,
                state=lambda _ctx: {},
                actions={
                    "press": _press_action(source_sid, target_sid, target_field),
                },
            ))

        # --- scene -> event 按键事件 (物理按键, 单击/双击/长按) ---------
        if context.has_service("scene") and any(
            _field(profile, "scene", name) is not None
            for name, _ in _SCENE_FIELD_TO_EVENT
        ):
            entities.append(EntitySpec(
                platform="event",
                key="button_event",
                name="按键事件",
                state=lambda _ctx: {},
                event_decoder=_scene_event_decoder,
                metadata={
                    "device_class": "button",
                    "event_types": [event for _, event in _SCENE_FIELD_TO_EVENT],
                },
            ))

        return tuple(entities)


ADAPTER = ProductZG2NAdapter()
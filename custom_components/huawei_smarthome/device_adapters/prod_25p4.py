"""User-contributed protocol for Huawei product 25P4 (北通智能游戏手柄 BTP-A1N2).

设备类型: 游戏手柄 (Joypad), 型号 BTP-A1N2
制造商: 北通 (Beitong), 协议: BLE

Profile 的服务:

  commonMemorySwitch1.status   enum  RW  GPR  report:1  0 关 / 1 开 / 2 保持上次
  iOSReporting.iOSReporting    str   RW  GPR  report:1  maxLength 1000
  calibrating.calibrating      bool  R   G    report:0  校准状态
  Turbo.Turbo                  str   RW  GP   report:0  maxLength 2
  userDefinedButtons.definedButtons  str RW GPR report:1 maxLength 35
  light.lightset               str   RW  GP   report:0  maxLength 30
  sensitivity.sensitivity      str   R   G    report:0  maxLength 20
  update.update                str   RW  GPR  report:1  maxLength 1000
  quantity.quantity            int   R   GR   report:1  0..100, percent:1
  keymap.handleTest            str   R   G    report:0  maxLength 20
  vibration.vibration          str   RW  GP   report:0  maxLength 1

已暴露 (3 个实体):

  select (1):  断电记忆  <- commonMemorySwitch1.status
               0 关 / 1 开 / 2 保持上次状态, config 类别

  sensor (1):  电量      <- quantity.quantity
               0..100 %, device_class battery

  text (1):    按键自定义 <- userDefinedButtons.definedButtons
               35 字符, config 类别, 会主动上报

故意不暴露:

  iOSReporting.iOSReporting
     string RW GPR report:1, maxLength 1000. 超出 HA text.py 的
     _MAX_LENGTH = 255 限制, 截断后是无效内容. 不做实体.

  calibrating.calibrating
     bool R G report:0, 只读不上报. 初始值来自云端 snapshot, 之后
     不会更新. 做 binary_sensor 会停在初始值, 误导用户.

  Turbo.Turbo
     string RW GP report:0, maxLength 2. GP 表示可查询可写但不可读
     上报. report:0 说明不上报. HA text 平台读不到值, 且 2 字符的
     格式未知 (数字? "1x"? "off"?), 不做实体.

  light.lightset
     string RW GP report:0, maxLength 30. 同上, 灯效设置格式未知,
     不可读, 不做实体.

  sensitivity.sensitivity
     string R G report:0, maxLength 20. 只读不上报, 不做实体.

  update.update
     string RW GPR report:1, maxLength 1000. 固件升级字符串, 超 255
     限制, 且语义是 OTA 动作, 不做实体.

  keymap.handleTest
     string R G report:0, maxLength 20. 手柄测试字符串, 只读不上报,
     不做实体.

  vibration.vibration
     string RW GP report:0, maxLength 1. 震感强度, 单字符, 格式未知
     (数字? 档位?), 不可读, 不做实体.

关于这个设备的定位:

  游戏手柄本质上不是智能家居设备, 它的核心功能是通过蓝牙连接
  手机/PC/主机玩游戏, 而不是被 HA 控制. 这个适配器只暴露 3 个
  有明确语义且 report:1 会上报的字段:

    - 断电记忆: 手柄断电后重新上电的初始状态, 用户可配置
    - 电量: 0-100 % 百分比, 手柄剩余电量
    - 按键自定义: 35 字符的映射字符串, 用户可查看/编辑

  其他的配置项 (连发频率/灯效/灵敏度/震感) 格式未知, 且大多
  report:0 或不可读, 暴露也拿不到值.

关于 _select_action 的反查:

  commonMemorySwitch1.status 的 enumList:
    0 -> 关
    1 -> 开
    2 -> 保持上次状态
  select 平台显示中文标签, 写入时反查回 0/1/2.

关于 _text_action 的 35 字符限制:

  definedButtons 的 maxLength 是 35, metadata["max"] = 35. HA 的
  text.py 会把 _attr_native_max 限制到 min(35, 255) = 35, 用户输入
  超过 35 字符会被前端拒绝. 适配器的 _text_action 也做 35 字符
  截断兜底, 防止通过 service 调用绕过前端限制.

  text.py 的 _last_value 机制: 用户输入后, _last_value 保存输入值,
  下次设备上报会覆盖. 对于 report:1 的字段, 设备上报后 _last_value
  被清空, native_value 用设备上报值. 这符合预期.
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

# commonMemorySwitch1.status 的 enumList (Profile 权威)
_MEMORY_STATUS_OPTIONS: tuple[tuple[int, str], ...] = (
    (0, "关"),
    (1, "开"),
    (2, "保持上次状态"),
)


# ---- 写动作工厂 ---------------------------------------------------------

def _select_action(sid: str, field: str, options: tuple[tuple[int, str], ...]):
    """把 select 选中的中文标签反查回 enum 值, 写入 sid."""
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


def _text_action(sid: str, field: str, max_len: int):
    """把 text 输入的字符串写回设备, 超长截断."""
    async def _action(ctx: DeviceContext, data: Mapping[str, Any]) -> None:
        value = data.get("value")
        if not isinstance(value, str):
            return
        await ctx.async_send_service(sid, {field: value[:max_len]})
    return _action


# ---- 适配器 ------------------------------------------------------------

class Product25P4Adapter:
    """北通智能游戏手柄 BTP-A1N2 (25P4) 适配器."""

    prod_id = "25P4"

    def entities(self, context: DeviceContext) -> tuple[EntitySpec, ...]:
        profile = context.profile
        if profile is None:
            return ()

        entities: list[EntitySpec] = []

        # --- commonMemorySwitch1.status -> select 断电记忆 -------------
        if context.has_service("commonMemorySwitch1") and _field(
            profile, "commonMemorySwitch1", "status"
        ) is not None:
            entities.append(EntitySpec(
                platform="select",
                key="memory_switch",
                name="断电记忆",
                state=lambda ctx: {
                    "current_option": _enum_label(
                        ctx.value("commonMemorySwitch1", "status"),
                        _MEMORY_STATUS_OPTIONS,
                    )
                },
                actions={
                    "select_option": _select_action(
                        "commonMemorySwitch1", "status", _MEMORY_STATUS_OPTIONS
                    ),
                },
                metadata={
                    "options": [label for _, label in _MEMORY_STATUS_OPTIONS],
                    "entity_category": "config",
                },
            ))

        # --- quantity.quantity -> sensor 电量 --------------------------
        if context.has_service("quantity") and _field(
            profile, "quantity", "quantity"
        ) is not None:
            entities.append(EntitySpec(
                platform="sensor",
                key="battery",
                name="电量",
                state=lambda ctx: {
                    "native_value": _number(ctx.value("quantity", "quantity"))
                },
                metadata={
                    "device_class": "battery",
                    "state_class": "measurement",
                    "unit": "%",
                },
            ))

        # --- userDefinedButtons.definedButtons -> text 按键自定义 ------
        if context.has_service("userDefinedButtons") and _field(
            profile, "userDefinedButtons", "definedButtons"
        ) is not None:
            entities.append(EntitySpec(
                platform="text",
                key="defined_buttons",
                name="按键自定义",
                state=lambda ctx: {
                    "native_value": _text(
                        ctx.value("userDefinedButtons", "definedButtons")
                    )
                },
                actions={
                    "set_value": _text_action(
                        "userDefinedButtons", "definedButtons", 35
                    ),
                },
                metadata={
                    "max": 35,
                    "entity_category": "config",
                },
            ))

        return tuple(entities)


ADAPTER = Product25P4Adapter()
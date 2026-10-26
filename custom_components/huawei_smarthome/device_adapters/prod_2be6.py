"""User-contributed protocol for Huawei product 2BE6 (麦乐克红外人体移动传感器 MIR-IR100).

设备类型: 红外人体感应传感器 (PIR Motion Detector), 型号 MIR-IR100
制造商: 麦乐克 (Multi IR), 协议: Mesh

Profile 的四个字段:

  motionDetected.motionDetected  enum R 0/1   移动检测事件 (quickmenu 引用)
  status.status                  enum R 0/1   有无人持续状态
  battery.level                  int  R 0..100 电量百分比
  battery.alarm                  bool R 0/1    低电量告警

已暴露 (4 个实体):

  binary_sensor "移动侦测"   <- motionDetected.motionDetected
                                device_class: motion
                                0 无人移动 / 1 有人移动
  binary_sensor "有人"       <- status.status
                                device_class: occupancy
                                0 无人 / 1 有人
  sensor "电池电量"          <- battery.level
  binary_sensor "低电量告警" <- battery.alarm
                                device_class: battery

关于 motionDetected 和 status 的关系:

  两个字段都是 0/1 enum, 语义有细微差别:
    motionDetected 是"移动检测告警事件", quickmenu 引用它做面板显示
    status         是"有无人持续的状态", 对自动化 (回家开灯/离家关灯) 更有用
  两者都暴露, device_class 分别用 motion 和 occupancy, 让用户在自动化里
  按需选择. 这不是重复, 而是互补.

关于 permission "R" (而非 "GR"):

  两个字段的 permission 都是 "R" 而不是 "GR", 与 2BE5 的 status.status
  一样. report:1 说明设备会变化上报, 但少了 G 意味着网关不一定主动订阅.
  结果: context.value() 可能长期返回 None, binary_sensor 显示 unknown,
  但只要设备 online, available 仍是 True. 这是设备能力的限制, 适配器
  侧无法修复, 只能如实反映.

  严格解析 0/1: 未知值 (比如 2) 返回 None, HA 显示 unknown 而非猜测.

关于 _flag_value 的宽容性:

  motionDetected / status / battery.alarm 三个字段的 characteristicType
  有的是 "enum", 有的是 "bool". 设备实际可能上报三种格式:
    - 数字: 1 / 0
    - 字符串: "1" / "0"
    - JSON 布尔: true / false

  _flag_value 三种都能处理, 统一用它做布尔解析. 这是与 2BE5 统一后的
  命名 (2BE5 也用 _flag_value), 两个适配器的辅助函数风格一致.

  旧版的 _bool + _enum_on_off 两个函数功能完全重复 (_enum_on_off 直接
  return _bool(value)), 本版合并为 _flag_value 一个函数.
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


def _flag_value(value: Any) -> bool | None:
    """严格解析 bool: 接受 0/1, 字符串 "0"/"1"/"true"/"false"/"on"/"off",
    以及 JSON 布尔 true/false, 其它返回 None.

    这是 2BE6 的 motionDetected / status / battery.alarm 三个字段的统一
    解析函数. 与 2BE5 的 _flag_value 命名和实现完全一致, 两个适配器
    风格统一.

    旧版有 _bool + _enum_on_off 两个函数, 功能完全重复
    (_enum_on_off 直接 return _bool(value)), 本版合并为 _flag_value.
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


# ---- 适配器 ------------------------------------------------------------

class Product2BE6Adapter:
    """麦乐克红外人体移动传感器 MIR-IR100 (2BE6) 适配器."""

    prod_id = "2BE6"

    def entities(self, context: DeviceContext) -> tuple[EntitySpec, ...]:
        profile = context.profile
        if profile is None:
            return ()

        entities: list[EntitySpec] = []

        # --- motionDetected -> binary_sensor 移动侦测 (motion) -----------
        if context.has_service("motionDetected") and _field(
            profile, "motionDetected", "motionDetected"
        ) is not None:
            entities.append(EntitySpec(
                platform="binary_sensor",
                key="motion",
                name="移动侦测",
                state=lambda ctx: {
                    "is_on": _flag_value(
                        ctx.value("motionDetected", "motionDetected")
                    )
                },
                metadata={"device_class": "motion"},
            ))

        # --- status.status -> binary_sensor 有人 (occupancy) -------------
        if context.has_service("status") and _field(
            profile, "status", "status"
        ) is not None:
            entities.append(EntitySpec(
                platform="binary_sensor",
                key="occupancy",
                name="有人",
                state=lambda ctx: {
                    "is_on": _flag_value(ctx.value("status", "status"))
                },
                metadata={"device_class": "occupancy"},
            ))

        # --- battery.level -> sensor 电池电量 ---------------------------
        if context.has_service("battery") and _field(
            profile, "battery", "level"
        ) is not None:
            entities.append(EntitySpec(
                platform="sensor",
                key="battery_level",
                name="电池电量",
                state=lambda ctx: {
                    "native_value": _number(ctx.value("battery", "level"))
                },
                metadata={
                    "device_class": "battery",
                    "state_class": "measurement",
                    "unit": "%",
                },
            ))

        # --- battery.alarm -> binary_sensor 低电量告警 ------------------
        if context.has_service("battery") and _field(
            profile, "battery", "alarm"
        ) is not None:
            entities.append(EntitySpec(
                platform="binary_sensor",
                key="battery_alarm",
                name="低电量告警",
                state=lambda ctx: {
                    "is_on": _flag_value(ctx.value("battery", "alarm"))
                },
                metadata={"device_class": "battery"},
            ))

        return tuple(entities)


ADAPTER = Product2BE6Adapter()
"""User-contributed protocol for Huawei product 28A6 (720 冰箱除味器智联版 RC100s).

设备类型: 杀菌除味器 (Deodorizing Sterilizer), 型号 RC100s
制造商: 柒贰零健康科技有限公司 (720), 协议: BLE

Profile 的服务:

  workmode.workmode       enum RW  0 长续航保鲜模式 / 1 快速除味模式
  battery.capacity        int  R   0..100, unit "mA" (笔误, 实为 %)
  connectstate.state      enum R   0 未连接 / 1 连接中 / 2 已连接
  netInfo.*               R        WiFi 诊断 (对 BLE 设备可疑)
  moreset.set             enum W   0 快速指南 / 1 固件更新 (动作)
  update.*                OTA      不暴露

已暴露 (8 个实体):

  select (1):        工作模式   <- workmode.workmode  (RW)
  sensor (1):        电池电量   <- battery.capacity   (%, 主界面)
  sensor (1):        连接状态   <- connectstate.state (diagnostic)
  sensor (5):        信号强度 / 信号等级 / Wi-Fi 名称 / IP / BSSID
                     <- netInfo.*, diagnostic

故意不暴露:

  moreset.set    method:W 快速指南/固件更新的动作, 不是状态
  update.*       OTA

三处 Profile 需要特殊处理的地方:

  1. battery.capacity 的 unit 是 "mA", 但 min 0 / max 100 / step 1.0 /
     descCh "电池总电量". mA 是电流单位, 不是容量单位, 0..100 的电池
     字段在华为体系里就是百分比 (2GE7 / 2BE5 / 2BE6 的 battery.level
     同为此语义). 按 "%" 处理, 与 HA 的 SensorDeviceClass.BATTERY
     契约一致. Profile 的 "mA" 大概率是笔误.

  2. connectstate.state 是 BLE 连接状态, 有三个值:
       0 未连接 / 1 连接中 / 2 已连接
     用 binary_sensor + connectivity 会丢失"连接中"这个中间态, 而 BLE
     重连可能停留在这个状态较久. 用 sensor 枚举保留完整信息, 放在
     diagnostic 类别, 符合"诊断信息完整优先"的原则.

  3. netInfo 整个服务对 BLE 设备是可疑的. BLE 没有 IP/SSID/BSSID,
     这些字段大概率是 Profile 从同厂 WiFi 设备模板复制遗留. 但
     permission "GR" + report:1 又声明了会主动上报. 按"保留比删除
     安全"的原则暴露, 放在 diagnostic 类别——最坏是 unknown, 不占
     主界面. 这与 25I8 里对 netInfo.RSSI 的处理一致.

     如果实测发现 5 个 netInfo 字段全部永久 unknown, 说明 Profile 确实
     是从 WiFi 设备模板复制的, 删除 _net_info_entities 里的对应 block
     即可, 实体数从 8 减少到 3 (工作模式 / 电池电量 / 连接状态).

关于 select 的可写性:

  workmode.workmode 是 permission "GPR" (可设置), 用 select 平台提供
  完整的写能力. select.py 契约:
    current_option  = spec.state(ctx).get("current_option")
    async_select_option(option) -> action(ctx, {"option": option})
    _attr_options   = list(metadata.get("options", ()))

关于 battery.capacity 的 device_class:

  device_class 用 "battery", state_class 用 "measurement", unit 用 "%".
  0..100 的百分比电池字段, 与其他适配器的 battery.level 一致.

  注意: _number 返回 float (87.0), HA 会显示 "87.0 %" 而不是 "87 %".
  这是 2BE5 / 2BE6 / 2BE8 / 2GB1 的统一行为, 不是 28A6 独有的问题.
  如果希望显示整数, 需要改 _number 让它对整数值返回 int, 但这会影响
  所有适配器, 不在本文件单独改.
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


# ---- 枚举选项 (来自 Profile enumList, 权威) ------------------------------

_WORKMODE_OPTIONS: tuple[tuple[int, str], ...] = (
    (0, "长续航保鲜模式"),
    (1, "快速除味模式"),
)
_CONNECT_STATE_OPTIONS: tuple[tuple[int, str], ...] = (
    (0, "未连接"),
    (1, "连接中"),
    (2, "已连接"),
)
_NET_INTENSITY_OPTIONS: tuple[tuple[int, str], ...] = (
    (20, "0格信号"),
    (40, "1格信号"),
    (60, "2格信号"),
    (80, "3格信号"),
    (100, "4格信号"),
)


# ---- 写动作 --------------------------------------------------------------

def _select_action(
    sid: str,
    field_name: str,
    options: tuple[tuple[int, str], ...],
):
    """把用户选中的中文标签反查回 enum 值, 再写入 ``sid``."""
    lookup = {label: value for value, label in options}

    async def _action(ctx: DeviceContext, data: Mapping[str, Any]) -> None:
        option = data.get("option")
        if not isinstance(option, str):
            return
        value = lookup.get(option)
        if value is None:
            return
        await ctx.async_send_service(sid, {field_name: value})

    return _action


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

class Product28A6Adapter:
    """720 冰箱除味器智联版 RC100s (28A6) 适配器."""

    prod_id = "28A6"

    def entities(self, context: DeviceContext) -> tuple[EntitySpec, ...]:
        profile = context.profile
        if profile is None:
            return ()

        entities: list[EntitySpec] = []

        # --- workmode.workmode -> select 工作模式 (RW) -------------------
        if context.has_service("workmode") and _field(
            profile, "workmode", "workmode"
        ) is not None:
            entities.append(EntitySpec(
                platform="select",
                key="workmode",
                name="工作模式",
                state=lambda ctx: {
                    "current_option": _enum_label(
                        ctx.value("workmode", "workmode"), _WORKMODE_OPTIONS
                    )
                },
                actions={
                    "select_option": _select_action(
                        "workmode", "workmode", _WORKMODE_OPTIONS
                    ),
                },
                metadata={"options": [label for _, label in _WORKMODE_OPTIONS]},
            ))

        # --- battery.capacity -> sensor 电池电量 ------------------------
        # Profile 的 unit "mA" 是笔误, 0..100 是百分比
        if context.has_service("battery") and _field(
            profile, "battery", "capacity"
        ) is not None:
            entities.append(EntitySpec(
                platform="sensor",
                key="battery_level",
                name="电池电量",
                state=lambda ctx: {
                    "native_value": _number(ctx.value("battery", "capacity"))
                },
                metadata={
                    "device_class": "battery",
                    "state_class": "measurement",
                    "unit": "%",
                },
            ))

        # --- connectstate.state -> sensor 连接状态 (diagnostic) ---------
        if context.has_service("connectstate") and _field(
            profile, "connectstate", "state"
        ) is not None:
            entities.append(EntitySpec(
                platform="sensor",
                key="connection_state",
                name="连接状态",
                state=lambda ctx: {
                    "native_value": _enum_label(
                        ctx.value("connectstate", "state"),
                        _CONNECT_STATE_OPTIONS,
                    )
                },
                metadata={"entity_category": "diagnostic"},
            ))

        # --- netInfo 诊断 ------------------------------------------------
        entities.extend(_net_info_entities(profile))

        return tuple(entities)


ADAPTER = Product28A6Adapter()
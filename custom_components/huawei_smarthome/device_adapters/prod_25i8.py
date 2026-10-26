"""User-contributed protocol for Huawei product 25I8 (领普 mesh 网关 HWGW01).

设备类型: 中控主机 (Bridge), 型号 HWGW01
制造商: 领普科技 (linptech), 协议: WiFi

这是一个网关 (Bridge), 核心能力是发现/添加子设备、组控制、OTA,
而不是"自身有可观测状态". 12 个服务里绝大多数是管理子设备的动作
(array[object] 或 method:W) 或 report:0 的配置字段.

已暴露 (7 个实体):

  switch (1):        发现模式   <- discovery.enable  (RW PR, 0 关 / 1 开)
  binary_sensor (1): 组操作中   <- groupManage.status (R, 0 正常 / 1 处理中)
  sensor (5):        信号强度 / 信号等级 / Wi-Fi 名称 / IP / BSSID

故意不暴露:

  discovery.productID / sn          R G report:0, 配对上下文, 永不主动上报
  devList.devList                   array[object], HA 无合适平台
  addDevice.devList                 array[object], 添加子设备动作
  groupControl.data / sid           W, 组控动作
  groupControl.groupID              GP report:0, 不上报
  groupManage.action                W, 添加/删除组设备动作
  groupManage.groupID               GP report:0
  groupManage.groupDevList          array[object]
  group1~4.*                        全部 GP report:0, 设备永不主动上报,
                                    任何基于它们的实体都会永久 unknown
  update.*                          OTA

关于 discovery.enable 的 permission "PR":

  P = 可设置, R = 可上报, 无 G = 不可主动查询.
  设备变化时会上报 (report:1), 但 HA 重启后如果设备没主动上报当前值,
  context.value() 会是 None, switch 显示 unknown, 直到用户操作或设备
  再次上报. 这是设备行为, 适配器无法修复.

  这与 2MJD 的 matchedCap.jsonstr (只有 P, 无 R) 不同: 25I8 的
  discovery.enable 至少有 R, 设备变化时会上报. 所以 switch 的状态
  是"变化时可见", 不是"永久 unknown".

关于 group1~4 全部不暴露:

  这 4 个服务的所有字段 (name / groupID / icon / num / groupDevList)
  都是 permission "GP" 且 report:0, 意味着设备永不主动上报这些值.
  context.value() 读的是 _state (只在 MQTT 上报时填充), 所以任何基于
  它们的实体都会永久显示 unknown. 与其暴露一个永远空白的实体, 不如
  不暴露.

关于 netInfo.RSSI 的 permission "GP" + report:0:

  Profile 里 netInfo 有 5 个字段:
    intensity  R   GR  report:1   -> 正常上报
    BSSID      R   GR  report:1   -> 正常上报
    IP         R   GR  report:1   -> 正常上报
    SSID       R   GR  report:1   -> 正常上报
    RSSI      RW  GP  report:0   -> 与上面 4 个不一致

  这大概率是 Profile 的笔误 (把 GR 写成 GP, 把 report:1 写成 0).
  两种处理:
    1. 保守: 不暴露 RSSI, 因为 Profile 声明 report:0, 理论上不会上报
    2. 宽容: 保留 RSSI, 如果实测设备实际上报则有值, 否则永久 unknown

  本适配器选择方案 2 (保留), 理由:
    - 删除后如果设备实际上报 (Profile 笔误), 用户少一个实体
    - 保留最多是永久 unknown, 不占主界面 (归入 diagnostic)
    - 与 2MJD 的 netInfo.RSSI 处理一致 (那里也是保留但标注可能 unknown)

  如果实测发现 RSSI 永久 unknown, 删除下面这 10 行即可:

    if _field(profile, "netInfo", "RSSI") is not None:
        entities.append(EntitySpec(
            platform="sensor",
            key="wifi_rssi",
            ...
        ))

关于 _flag_value 的命名:

  与 2BE5 / 2BE6 / 2BE8 / 2GB1 / 2MKS / 2QEF / 20TL 的 _flag_value
  命名和实现完全一致, 八个适配器风格统一.

  旧版用 _as_bool 命名, 本版改成 _flag_value, 功能完全一样
  (严格解析 0/1 + "true"/"on"/"false"/"off").
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

def _flag_value(value: Any) -> bool | None:
    """严格解析 bool: 接受 0/1, 字符串 "0"/"1"/"true"/"false"/"on"/"off",
    以及 JSON 布尔 true/false, 其它返回 None.

    与 2BE5 / 2BE6 / 2BE8 / 2GB1 / 2MKS / 2QEF / 20TL 的 _flag_value
    命名和实现完全一致, 八个适配器风格统一.
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


# ---- 枚举选项 ----------------------------------------------------------

_NET_INTENSITY_OPTIONS: tuple[tuple[int, str], ...] = (
    (20, "0格信号"),
    (40, "1格信号"),
    (60, "2格信号"),
    (80, "3格信号"),
    (100, "4格信号"),
)


# ---- 写动作工厂 ---------------------------------------------------------

def _discovery_action(value: int):
    """生成 discovery.enable 的 turn_on/turn_off 动作.

    旧版有 _discovery_on / _discovery_off 两个独立函数, 本版合并为
    一个工厂, 与 2MJD 的 _switch_action / 2QEF 的 _switch_action 风格
    统一.
    """
    async def _action(ctx: DeviceContext, _data: Mapping[str, Any]) -> None:
        await ctx.async_send_service("discovery", {"enable": value})
    return _action


# ---- netInfo 诊断实体 --------------------------------------------------

def _net_info_entities(profile: Any) -> list[EntitySpec]:
    if _service(profile, "netInfo") is None:
        return []
    entities: list[EntitySpec] = []

    # RSSI: RW GP report:0, 大概率不上报, 保留但不保证有值.
    # 如果实测永久 unknown, 删除这个 block 即可.
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

class Product25I8Adapter:
    """领普 mesh 网关 HWGW01 (25I8) 适配器."""

    prod_id = "25I8"

    def entities(self, context: DeviceContext) -> tuple[EntitySpec, ...]:
        profile = context.profile
        if profile is None:
            return ()

        entities: list[EntitySpec] = []

        # --- discovery.enable -> switch 发现模式 ------------------------
        if context.has_service("discovery") and _field(
            profile, "discovery", "enable"
        ) is not None:
            entities.append(EntitySpec(
                platform="switch",
                key="discovery",
                name="发现模式",
                state=lambda ctx: {
                    "is_on": _flag_value(ctx.value("discovery", "enable"))
                },
                actions={
                    "turn_on": _discovery_action(1),
                    "turn_off": _discovery_action(0),
                },
            ))

        # --- groupManage.status -> binary_sensor 组操作中 ---------------
        if context.has_service("groupManage") and _field(
            profile, "groupManage", "status"
        ) is not None:
            entities.append(EntitySpec(
                platform="binary_sensor",
                key="group_busy",
                name="组操作中",
                state=lambda ctx: {
                    "is_on": _flag_value(ctx.value("groupManage", "status"))
                },
                metadata={
                    "device_class": "running",
                    "entity_category": "diagnostic",
                },
            ))

        # --- netInfo 诊断 ------------------------------------------------
        entities.extend(_net_info_entities(profile))

        return tuple(entities)


ADAPTER = Product25I8Adapter()
"""User-contributed protocol for Huawei product 107J (遥看小苹果 YKK-1011).

设备类型: 红外网关 (infraredHub), 型号 YKK-1011
制造商: 深圳遥看科技有限公司 (YKK), 协议: WiFi

Profile 的服务:

  ledOnoff.ledOnoff     bool   RW  0 关 / 1 开   LED 指示灯开关
  deviceList.*          mixed  R/W 遥控器列表 (15 个字段, report:0)
  cmdList.*             mixed  R/W 遥控器指令集 (3 个字段, report:0)
  controlKey.controlKey string W   控制指令, 1024 字符, report:0
  netInfo.intensity     enum   R   信号等级 20/40/60/80/100
  netInfo.RSSI          int    R   信号强度
  netInfo.SSID          string R   Wi-Fi 名称
  netInfo.BSSID         string R   路由器 MAC
  netInfo.IP            string RW  IP 地址
  update.*              OTA        不暴露

已暴露 (6 个实体):

  switch (1):   LED  <- ledOnoff.ledOnoff (config)
                0 关 / 1 开, 发送 {"ledOnoff": 1/0}

  sensor (5):   信号强度 / 信号等级 / Wi-Fi 名称 / IP / BSSID
                <- netInfo.*, diagnostic

故意不暴露:

  deviceList.*
     遥控器列表 (number / list / hname / index / hid / beRmodel / bid /
     brand / name / rid / rmodel / tid / type / ui / zip), 全部是
     report:0 + array[object] 或 R/W 混合. 设备只在 App 主动查询时
     返回, 不会主动上报. HA 无合适平台表达 "遥控器列表". 这些应该在
     智慧生活 App 里管理.

  cmdList.*
     遥控器指令集, 同上, report:0 + array[object].

  controlKey.controlKey
     string W (只写), 1024 字符, report:0. 理论上可以用 text 平台让
     用户在 HA 里发红外码, 但:
       1. text.py 的 _MAX_LENGTH = 255, 1024 字符会被截断
       2. 需要用户知道特定指令格式 (src / key / controlKey 的组合)
       3. 这是"红外码下发"动作, 不是状态
     不暴露. 红外控制应该在 App 里用遥控器面板完成.

  update.*
     OTA

关于 ledOnoff 的实体类别:

  LED 是设备的指示灯, 不是用户日常操作的功能. 放在 config 类别
  (折叠到"高级设置"), 避免占用主界面. 这与 2DAD 的"充电保护" /
  "家电保护" 放 config 类别一致.

  如果用户希望 LED 在主界面, 去掉 metadata 里的 entity_category
  即可.

关于 netInfo.intensity 缺少 method:

  Profile 里 netInfo.intensity 只有 max:100 / min:20, 没有
  method 字段. 按华为通用规范, netInfo 的字段都是只读的, 这里
  默认按 R 处理. 如果实测发现这个字段不上报, 删除对应的 sensor.

  这与 101N 的测量值字段类似: Profile 没写 method, 但设备实际上报.
  按"保留比删除安全"的原则暴露, 最坏是 unknown, 不占主界面.

关于 netInfo.IP 的 permission "RW":

  IP 字段是 RW (可写), 但写入 IP 会改变设备的网络配置, 可能导致
  设备失联. HA 不应该暴露这种危险的写入. 只读展示 IP 地址, 不做
  可写 text 实体.

  这与 25I8 的 netInfo.RSSI (RW GP report:0) 处理一致: 保留只读
  展示, 不暴露写入.

关于 _flag_value 的命名:

  与 2BE5 / 2BE6 / 2BE8 / 2GB1 / 2MKS / 2QEF / 20TL / 25I8 / 105G
  / 105M / 107W / 210Y / 2196 / A3RA / V0CK / V0DX / 20KM 的
  _flag_value 命名和实现完全一致, 十八个适配器风格统一.
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
    """严格解析 bool: 接受 0/1, 字符串 "0"/"1"/"true"/"false",
    以及 JSON 布尔 true/false, 其它返回 None.

    与 2BE5 / 2BE6 / 2BE8 / 2GB1 / 2MKS / 2QEF / 20TL / 25I8 / 105G
    / 105M / 107W / 210Y / 2196 / A3RA / V0CK / V0DX / 20KM 的
    _flag_value 命名和实现完全一致, 十八个适配器风格统一.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        token = value.strip().casefold()
        if token in {"1", "true"}:
            return True
        if token in {"0", "false"}:
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

# Profile 里 netInfo.intensity 的 enumList 没有给出, 按华为通用规范
# (20/40/60/80/100) 填写. 与其他适配器的 _NET_INTENSITY_OPTIONS 一致.
_NET_INTENSITY_OPTIONS: tuple[tuple[int, str], ...] = (
    (20, "0格信号"),
    (40, "1格信号"),
    (60, "2格信号"),
    (80, "3格信号"),
    (100, "4格信号"),
)


# ---- 写动作工厂 ---------------------------------------------------------

def _switch_action(sid: str, field: str, value: int):
    """生成一个 switch 的 turn_on/turn_off 动作.

    ledOnoff 的字段名是 ledOnoff (不是惯例的 on), 所以需要显式
    传 field="ledOnoff", 发送 {"ledOnoff": 1/0}.

    与 105G / 2MJD / 2QEF / 25I8 / 107W / 210Y / 2196 / A3RA /
    20KM 的 _switch_action 风格一致.
    """
    async def _action(ctx: DeviceContext, _data: Mapping[str, Any]) -> None:
        await ctx.async_send_service(sid, {field: value})
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

class Product107JAdapter:
    """遥看小苹果 YKK-1011 (107J) 适配器."""

    prod_id = "107J"

    def entities(self, context: DeviceContext) -> tuple[EntitySpec, ...]:
        profile = context.profile
        if profile is None:
            return ()

        entities: list[EntitySpec] = []

        # --- ledOnoff.ledOnoff -> switch LED (config) ------------------
        if context.has_service("ledOnoff") and _field(
            profile, "ledOnoff", "ledOnoff"
        ) is not None:
            entities.append(EntitySpec(
                platform="switch",
                key="led",
                name="LED",
                state=lambda ctx: {
                    "is_on": _flag_value(ctx.value("ledOnoff", "ledOnoff"))
                },
                actions={
                    "turn_on": _switch_action("ledOnoff", "ledOnoff", 1),
                    "turn_off": _switch_action("ledOnoff", "ledOnoff", 0),
                },
                metadata={"entity_category": "config"},
            ))

        # --- netInfo 诊断 ------------------------------------------------
        entities.extend(_net_info_entities(profile))

        return tuple(entities)


ADAPTER = Product107JAdapter()
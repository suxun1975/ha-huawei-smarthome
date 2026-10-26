"""User-contributed protocol for Huawei product 107W (Sonoff POW R2 电量监测插座).

设备类型: 开关控制器 (Receiver Controller), 型号 ITA-GZ1-GL
制造商: 深圳松诺技术有限公司 (Sonoff)

已暴露 (17 个实体):

  switch (2):        电源      <- switch.on
                     单次统计  <- onceStatistics.on (开始/停止统计)

  select (1):        上电状态  <- startup.startup (关/开/保持上次)

  number (4):        最小功率阈值 / 最大功率阈值 / 电压阈值 / 电流阈值
                     <- powerProtect.*, config 类别

  sensor (10):       实时功率 / 实时电压 / 实时电流
                     <- energyConsumtion.*, 分别 ÷100 得到 W/V/A

                     单次统计电量  <- onceStatistics.oneKwhData ÷100, kWh

                     告警类型      <- alarmType.alarmType, 0~10 文本

                     WiFi 诊断: RSSI / intensity / SSID / IP / BSSID

故意不暴露:

  historyConsumption.hundredDaysKwh
      report: 0, 不上报; 600 字节十六进制字符串, HA 无合适平台
  timer.* / delay.*
      array[object], 需要专用定时器/倒计时 UI
  update.*
      OTA

关于缩放:

  energyConsumtion.power   单位 0.01W  -> ÷100 得到 W
  energyConsumtion.voltage 单位 0.01V  -> ÷100 得到 V
  energyConsumtion.current 单位 0.01A  -> ÷100 得到 A
  onceStatistics.oneKwhData 单位 0.01kWh -> ÷100 得到 kWh

  这些字段的 descCh 明确写了单位, 是权威声明, 必须按它缩放.
  与 2DAD 的 realPower (divisor 1000) 同理.

关于 powerProtect 的单位疑点:

  descCh 写的是 "单位0.1KW", min=1 max=33000, 按字面算是
  0.1kW~3300kW. 但 POW R2 最大负载只有 3500W, 3300kW 是荒谬值.

  同 Profile 里 energyConsumtion.power 用 0.01W 单位, max=330000
  = 3300W, 是合理的. 这几乎肯定是 powerProtect 的 descCh 把
  "0.1W" 写成了 "0.1KW".

  处理方式: number 的 min/max/step 和 native_value 全部用 Profile
  原始整数 (不做缩放), unit 写 "0.1kW" (忠实于 descCh). 如果实测
  发现云端实际按 0.1W 处理, 把 unit 改成 "0.1W" 即可, 逻辑不用动.

关于 单次统计 用 switch 而非 button:

  onceStatistics.on 是 bool RW, 语义是 "开始/停止单次电量统计".
  用 switch 的 is_on=True 表示 "正在统计", turn_on 发送 {"on": 1},
  turn_off 发送 {"on": 0}. 这比两个 button 更简洁, 且用户能看到
  "正在统计中" 的状态.
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

def _as_bool(value: Any) -> bool | None:
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


def _scaled(value: Any, divisor: float) -> float | None:
    number = _number(value)
    if number is None or divisor == 0:
        return None
    return round(number / divisor, 3)


# ---- 枚举选项 ----------------------------------------------------------

_STARTUP_OPTIONS: tuple[tuple[int, str], ...] = (
    (0, "关"),
    (1, "开"),
    (2, "保持上次状态"),
)
_ALARM_TYPE_OPTIONS: tuple[tuple[int, str], ...] = (
    (0, "功率上限告警"),
    (1, "电压上限过高"),
    (2, "电流上限过高"),
    (3, "功率上限告警 & 电压上限过高"),
    (4, "功率上限告警 & 电流上限过高"),
    (5, "电压上限过高 & 电流上限过高"),
    (6, "功率上限告警 & 电流上限过高 & 电压上限过高"),
    (7, "功率下限告警"),
    (8, "功率下限告警 & 电压上限过高"),
    (9, "功率下限告警 & 电流上限过高"),
    (10, "功率下限告警 & 电压上限过高 & 电流上限过高"),
)
_NET_INTENSITY_OPTIONS: tuple[tuple[int, str], ...] = (
    (20, "0格信号"),
    (40, "1格信号"),
    (60, "2格信号"),
    (80, "3格信号"),
    (100, "4格信号"),
)


# ---- 写动作 --------------------------------------------------------------

async def _power_on(ctx: DeviceContext, _data: Mapping[str, Any]) -> None:
    await ctx.async_send_service("switch", {"on": 1})


async def _power_off(ctx: DeviceContext, _data: Mapping[str, Any]) -> None:
    await ctx.async_send_service("switch", {"on": 0})


async def _statistics_start(ctx: DeviceContext, _data: Mapping[str, Any]) -> None:
    await ctx.async_send_service("onceStatistics", {"on": 1})


async def _statistics_stop(ctx: DeviceContext, _data: Mapping[str, Any]) -> None:
    await ctx.async_send_service("onceStatistics", {"on": 0})


def _select_action(sid: str, field: str, options: tuple[tuple[int, str], ...]):
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


# ---- number 定义表 -----------------------------------------------------

# (sid, field, key, name, min, max, step, unit)
_NUMBERS: tuple[
    tuple[str, str, str, str, float, float, float, str], ...
] = (
    ("powerProtect", "minPower", "min_power", "最小功率阈值", 1, 33000, 1, "0.1kW"),
    ("powerProtect", "maxPower", "max_power", "最大功率阈值", 10, 33000, 1, "0.1kW"),
    ("powerProtect", "voltage", "protect_voltage", "电压阈值", 1, 3000, 1, "0.1V"),
    ("powerProtect", "current", "protect_current", "电流阈值", 1, 150, 1, "0.1A"),
)


def _number_entities(
    context: DeviceContext, profile: Any
) -> list[EntitySpec]:
    entities: list[EntitySpec] = []
    for sid, field, key, name, min_v, max_v, step, unit in _NUMBERS:
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
                "unit": unit,
                "entity_category": "config",
            },
        ))
    return entities


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

class Product107WAdapter:
    """Sonoff POW R2 电量监测插座 ITA-GZ1-GL (107W) 适配器."""

    prod_id = "107W"

    def entities(self, context: DeviceContext) -> tuple[EntitySpec, ...]:
        profile = context.profile
        if profile is None:
            return ()

        entities: list[EntitySpec] = []

        # --- switch.on -> switch 电源 ------------------------------------
        if context.has_service("switch") and _field(profile, "switch", "on") is not None:
            entities.append(EntitySpec(
                platform="switch",
                key="power",
                name="电源",
                state=lambda ctx: {"is_on": _as_bool(ctx.value("switch", "on"))},
                actions={"turn_on": _power_on, "turn_off": _power_off},
            ))

        # --- startup.startup -> select 上电状态 -------------------------
        if context.has_service("startup") and _field(
            profile, "startup", "startup"
        ) is not None:
            entities.append(EntitySpec(
                platform="select",
                key="startup",
                name="上电状态",
                state=lambda ctx: {
                    "current_option": _enum_label(
                        ctx.value("startup", "startup"), _STARTUP_OPTIONS
                    )
                },
                actions={
                    "select_option": _select_action(
                        "startup", "startup", _STARTUP_OPTIONS
                    ),
                },
                metadata={
                    "options": [label for _, label in _STARTUP_OPTIONS],
                    "entity_category": "config",
                },
            ))

        # --- energyConsumtion -> 实时功率/电压/电流 ---------------------
        if context.has_service("energyConsumtion"):
            for field, key, label, unit, device_class in (
                ("power", "power", "实时功率", "W", "power"),
                ("voltage", "voltage", "实时电压", "V", "voltage"),
                ("current", "current", "实时电流", "A", "current"),
            ):
                if _field(profile, "energyConsumtion", field) is None:
                    continue
                entities.append(EntitySpec(
                    platform="sensor",
                    key=key,
                    name=label,
                    state=lambda ctx, _f=field: {
                        "native_value": _scaled(
                            ctx.value("energyConsumtion", _f), 100
                        )
                    },
                    metadata={
                        "device_class": device_class,
                        "state_class": "measurement",
                        "unit": unit,
                    },
                ))

        # --- alarmType -> sensor 告警类型 -------------------------------
        if context.has_service("alarmType") and _field(
            profile, "alarmType", "alarmType"
        ) is not None:
            entities.append(EntitySpec(
                platform="sensor",
                key="alarm_type",
                name="告警类型",
                state=lambda ctx: {
                    "native_value": _enum_label(
                        ctx.value("alarmType", "alarmType"), _ALARM_TYPE_OPTIONS
                    )
                },
                metadata={"entity_category": "diagnostic"},
            ))

        # --- powerProtect -> number 阈值配置 ----------------------------
        entities.extend(_number_entities(context, profile))

        # --- onceStatistics -> switch 单次统计 + sensor 电量 ------------
        if context.has_service("onceStatistics") and _field(
            profile, "onceStatistics", "on"
        ) is not None:
            entities.append(EntitySpec(
                platform="switch",
                key="statistics",
                name="单次统计",
                state=lambda ctx: {
                    "is_on": _as_bool(ctx.value("onceStatistics", "on"))
                },
                actions={
                    "turn_on": _statistics_start,
                    "turn_off": _statistics_stop,
                },
            ))
        if context.has_service("onceStatistics") and _field(
            profile, "onceStatistics", "oneKwhData"
        ) is not None:
            entities.append(EntitySpec(
                platform="sensor",
                key="statistics_kwh",
                name="单次统计电量",
                state=lambda ctx: {
                    "native_value": _scaled(
                        ctx.value("onceStatistics", "oneKwhData"), 100
                    )
                },
                metadata={
                    "device_class": "energy",
                    "state_class": "total_increasing",
                    "unit": "kWh",
                },
            ))

        # --- netInfo 诊断 ------------------------------------------------
        entities.extend(_net_info_entities(profile))

        return tuple(entities)


ADAPTER = Product107WAdapter()
"""User-contributed protocol for Huawei product 101N (720 环境宝 AirBank3).

设备类型: 空气检测器 (Air Detector), 型号 EM1003
制造商: 720

Profile 只有两个服务:
  airDetector  8 对测量值 + 等级枚举
  update       标准 OTA, 不暴露

关于测量值字段的缩放 (实测确认):

  Profile 里 8 个测量值字段没有声明 unit / divisor, 但实测发现设备
  上报的是缩放后的整数, HA 需要按对应 divisor 还原:

    字段          HA 原始显示    App 显示      设备原始值   divisor
    temperature   201.0 °C      20.1 °C       201         10
    humidity      6.3 %         63 %          63          1
    HCHO          19.0 mg/m³    0.019 mg/m³   19          1000

  这三条是实测确认的. 其他 5 个字段按华为 HiLink 体系常见约定推测,
  标注为"需实测":

    字段         推测 divisor  推测理由
    PM25         1             整数 μg/m³, 不缩放
    PM10         1             整数 μg/m³, 不缩放
    TVOC         1000          与 HCHO 同为 mg/m³, ×1000 上报
    eCO2         1             整数 ppm, 不缩放
    noise        1             整数 dB, 不缩放

  如果实测发现某个字段的显示值与 App 不一致, 只需修改 _MEASUREMENTS
  表里对应行的最后一个数字 (divisor). 例如:
    - TVOC HA 显示 500, App 显示 0.5   -> TVOC divisor 从 1 改成 1000
    - PM2.5 HA 显示 0.012, App 显示 12 -> PM25 divisor 从 1 改成 1000
    - 湿度 HA 显示 6.3, App 显示 63    -> humidity divisor 从 10 改成 1

关于测量值字段的特殊性 (Profile 层面):

  temperature / humidity / PM25 / PM10 / HCHO / TVOC / eCO2 / noise
  这 8 个字段在 Profile 里只有 characteristicName 和全 0 的
  min/max/step, 没有 method / permission / report / unit /
  characteristicType. 这是整个 Profile 里最不寻常的地方.

  三种可能:
    1. 云端计算字段: 设备上报原始值, 云端融合后回填, Profile 只是占位
    2. 简化版 Profile: 文档没写全, 设备实际会正常上报
    3. 仅占位: 字段存在但永不上报

  quickmenu 只引用了等级字段 (PM25Level / PM10Level / TVOCLevel /
  HCHOLevel / eCO2Level), 证明等级字段确实有值. 测量值字段没有被
  quickmenu 引用, 存在"可能不上报"的风险.

  实测表明测量值确实上报, 属于情况 2 (简化版 Profile). 8 个测量值
  全部保留.

关于等级字段:

  8 个等级字段 (温度等级 / 湿度等级 / PM2.5 等级 / PM10 等级 /
  甲醛等级 / TVOC 等级 / eCO2 等级 / 噪音等级) 在 Profile 里有完整
  的 enumList, quickmenu 也引用了其中 5 个, 证明确实会上报. 放在
  主界面, 不加 entity_category, 因为这些标签对用户有实际价值
  (能知道当前环境是"优"还是"轻度污染").

  等级字段不需要缩放, 设备上报的就是 enum 值 (1~6).

device_class 只给 HA 有标准 device_class 的字段赋值:
  temperature  -> "temperature"
  humidity     -> "humidity"
  PM25         -> "pm25"
  PM10         -> "pm10"
  eCO2         -> "carbon_dioxide"
  HCHO / TVOC / noise 没有对应 device_class, 不赋值 (避免 HA 警告).

关于 _scaled 的保留位数:

  round(number / divisor, 4) 保留 4 位小数:
    temperature 201 / 10    = 20.1        (显示 20.1 °C)
    humidity    63  / 1     = 63          (显示 63 %)
    HCHO        19  / 1000  = 0.019       (显示 0.019 mg/m³)
    TVOC        500 / 1000  = 0.5         (显示 0.5 mg/m³)
  HA 的 SensorEntity 会按 float 自动格式化, 不需要手动控制小数位.

  注意: humidity divisor=1 时, _scaled 走短路分支返回原始 float,
  显示为 "63.0 %". 如果希望显示 "63 %" 而不是 "63.0 %", 需要
  在 _number 里对整数值返回 int, 但当前不处理, 与 temperature 的
  "20.1 °C" 保持一致的小数显示风格.
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


def _scaled(value: Any, divisor: float) -> float | None:
    number = _number(value)
    if number is None or divisor == 0:
        return None
    if divisor == 1.0:
        return number
    return round(number / divisor, 4)


# ---- 枚举选项 (来自 Profile enumList, 权威) ------------------------------

_TEMPERATURE_LEVEL_OPTIONS: tuple[tuple[int, str], ...] = (
    (1, "寒冷"), (2, "冷"), (3, "舒适"), (4, "热"), (5, "酷热"),
)
_HUMIDITY_LEVEL_OPTIONS: tuple[tuple[int, str], ...] = (
    (1, "干燥"), (2, "略干"), (3, "舒适"), (4, "潮湿"),
)
_PM25_LEVEL_OPTIONS: tuple[tuple[int, str], ...] = (
    (1, "优"), (2, "良"), (3, "轻度污染"), (4, "中度污染"),
    (5, "重度污染"), (6, "严重污染"),
)
_PM10_LEVEL_OPTIONS: tuple[tuple[int, str], ...] = (
    (1, "优"), (2, "良"), (3, "轻度污染"), (4, "中度污染"),
    (5, "重度污染"), (6, "严重污染"),
)
_HCHO_LEVEL_OPTIONS: tuple[tuple[int, str], ...] = (
    (1, "理想"), (2, "一般"), (3, "有害"), (4, "严重有害"),
)
_TVOC_LEVEL_OPTIONS: tuple[tuple[int, str], ...] = (
    (1, "理想"), (2, "轻度污染"), (3, "中度污染"), (4, "严重污染"),
)
_ECO2_LEVEL_OPTIONS: tuple[tuple[int, str], ...] = (
    (1, "理想"), (2, "正常"), (3, "浑浊"), (4, "中度污染"), (5, "严重污染"),
)
_NOISE_LEVEL_OPTIONS: tuple[tuple[int, str], ...] = (
    (1, "安静"), (2, "正常"), (3, "喧闹"), (4, "有害"),
)


# ---- 测量值字段定义 -----------------------------------------------------

_SID = "airDetector"

# (field, key, name, device_class, unit, divisor)
#   divisor = 1 表示不缩放, >1 表示除以此值
#
# 实测确认的 divisor:
#   temperature  ÷10    (201 -> 20.1 °C)
#   humidity     ÷1     (63  -> 63 %)
#   HCHO         ÷1000  (19  -> 0.019 mg/m³)
#
# 推测的 divisor (需实测确认):
#   PM25         ÷1     整数 μg/m³
#   PM10         ÷1     整数 μg/m³
#   TVOC         ÷1000  与 HCHO 同为 mg/m³
#   eCO2         ÷1     整数 ppm
#   noise        ÷1     整数 dB
#
# 如果实测发现某个字段显示值与 App 不一致, 只改下面对应行的最后一个数字.
_MEASUREMENTS: tuple[tuple[str, str, str, str | None, str, float], ...] = (
    ("temperature", "temperature", "温度",     "temperature",       "°C",    10.0),
    ("humidity",    "humidity",    "湿度",     "humidity",          "%",     1.0),
    ("PM25",        "pm25",        "PM2.5",    "pm25",              "μg/m³", 1.0),
    ("PM10",        "pm10",        "PM10",     "pm10",              "μg/m³", 1.0),
    ("HCHO",        "hcho",        "甲醛",     None,                "mg/m³", 1000.0),
    ("TVOC",        "tvoc",        "TVOC",     None,                "mg/m³", 1000.0),
    ("eCO2",        "eco2",        "eCO2",     "carbon_dioxide",    "ppm",   1.0),
    ("noise",       "noise",       "噪音",     None,                "dB",    1.0),
)

# (field, key, name, options)
_LEVELS: tuple[tuple[str, str, str, tuple[tuple[int, str], ...]], ...] = (
    ("temperatureLevel", "temperature_level", "温度等级", _TEMPERATURE_LEVEL_OPTIONS),
    ("humidityLevel",    "humidity_level",    "湿度等级", _HUMIDITY_LEVEL_OPTIONS),
    ("PM25Level",        "pm25_level",        "PM2.5 等级", _PM25_LEVEL_OPTIONS),
    ("PM10Level",        "pm10_level",        "PM10 等级",  _PM10_LEVEL_OPTIONS),
    ("HCHOLevel",        "hcho_level",        "甲醛等级",   _HCHO_LEVEL_OPTIONS),
    ("TVOCLevel",        "tvoc_level",        "TVOC 等级",  _TVOC_LEVEL_OPTIONS),
    ("eCO2Level",        "eco2_level",        "eCO2 等级",  _ECO2_LEVEL_OPTIONS),
    ("noiseLevel",       "noise_level",       "噪音等级",   _NOISE_LEVEL_OPTIONS),
)


# ---- 实体构建 ----------------------------------------------------------

def _measurement_entities(profile: Any) -> list[EntitySpec]:
    entities: list[EntitySpec] = []
    for field_name, key, name, device_class, unit, divisor in _MEASUREMENTS:
        if _field(profile, _SID, field_name) is None:
            continue
        metadata: dict[str, Any] = {
            "state_class": "measurement",
            "unit": unit,
        }
        if device_class is not None:
            metadata["device_class"] = device_class
        entities.append(EntitySpec(
            platform="sensor",
            key=key,
            name=name,
            state=lambda ctx, _f=field_name, _d=divisor: {
                "native_value": _scaled(ctx.value(_SID, _f), _d)
            },
            metadata=metadata,
        ))
    return entities


def _level_entities(profile: Any) -> list[EntitySpec]:
    entities: list[EntitySpec] = []
    for field_name, key, name, options in _LEVELS:
        if _field(profile, _SID, field_name) is None:
            continue
        entities.append(EntitySpec(
            platform="sensor",
            key=key,
            name=name,
            state=lambda ctx, _f=field_name, _o=options: {
                "native_value": _enum_label(ctx.value(_SID, _f), _o)
            },
            metadata={},
        ))
    return entities


# ---- 适配器 -------------------------------------------------------------

class Product101NAdapter:
    """720 环境宝 AirBank3 (101N) 适配器."""

    prod_id = "101N"

    def entities(self, context: DeviceContext) -> tuple[EntitySpec, ...]:
        profile = context.profile
        if profile is None:
            return ()

        if not context.has_service(_SID):
            return ()

        entities: list[EntitySpec] = []
        entities.extend(_measurement_entities(profile))
        entities.extend(_level_entities(profile))
        return tuple(entities)


ADAPTER = Product101NAdapter()
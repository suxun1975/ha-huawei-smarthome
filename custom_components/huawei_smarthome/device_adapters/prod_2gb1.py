"""User-contributed protocol for Huawei product 2GB1 (麦乐克温湿度传感器 MIR-TE100).

设备类型: 温湿度传感器 (Temperature And Humidity Detector), 型号 MIR-TE100
制造商: 麦乐克 (Multi IR), 协议: Mesh

Profile 的服务:

  temperature.current            int  R  -100..400, unit ""   温度
  temperature.level              enum R  1..5 舒适度等级      (不暴露)
  humidity.current               int  R  0..1000,   unit "%"  湿度
  humidity.level                 enum R  1..4 舒适度等级      (不暴露)
  humidity.target                int  RW 0..100               (不暴露)
  battery.level                  int  R  0..100               电量百分比
  battery.alarm                  bool R  0/1                  低电量告警
  commonFaultDetection.code      enum R  0 正常 / 1 低压故障
  commonFaultDetection.status    bool R  0/1                  故障告警
  netInfo.*                      R                            WiFi 诊断
  update.*                       OTA                          不暴露

已暴露 (11 个实体):

  sensor (8):
    温度           <- temperature.current       (°C, 主界面)
    湿度           <- humidity.current          (%, 主界面)
    电池电量       <- battery.level             (%, 主界面)
    故障状态       <- commonFaultDetection.code (diagnostic)
    信号强度       <- netInfo.RSSI              (diagnostic, dBm)
    信号等级       <- netInfo.intensity         (diagnostic)
    Wi-Fi 名称     <- netInfo.SSID              (diagnostic)
    IP 地址        <- netInfo.IP                (diagnostic)
    BSSID          <- netInfo.BSSID             (diagnostic)

  binary_sensor (3):
    低电量告警     <- battery.alarm             (battery, 主界面)
    故障告警       <- commonFaultDetection.status (problem, 主界面)

故意不暴露:

  temperature.level / humidity.level
     设备派生的舒适度标签, 与测量值重复, HA 侧阈值不透明
  humidity.target
     H5 页面从未引用, 无写入语义
  update.*
     OTA, App 管理

关于温度单位 "°C" (U+00B0 + "C"):

  Profile 里 temperature.current 的 unit 是 "" (空), 但 H5 页面和真机
  读数证明是摄氏度. 适配器用 "°C" 而不是 "℃" (U+2103), 因为 HA 的
  SensorDeviceClass.TEMPERATURE 只接受 "K" / "°C" / "°F", 用 "℃"
  会触发 "native unit not valid" 警告. 这与 2BE8 / A2LW / 210Y 的
  处理一致.

关于缩放:

  temperature.current 的 range 是 -100..400, humidity.current 是 0..1000,
  看起来像"十分之一", 但 H5 页面的真机读数 disprove:
    humidity.current=33  -> 33 %RH (不是 3.3 %RH)
    temperature.current=38 -> 38 °C (不是 3.8 °C)
  所以值原样使用, 不缩放. 这与 2BE8 (同 deviceModel MIR-TE100) 一致.

关于 _flag_value 与 _enum_text:

  _flag_value 是 battery.alarm 和 commonFaultDetection.status 的解析
  函数, 与 2BE5 / 2BE6 / 2BE8 的 _flag_value 命名和实现完全一致,
  支持 bool / "0"/"1"/"true"/"false"/"on"/"off" / 数字.

  _enum_text 是 netInfo.intensity 和 commonFaultDetection.code 的解析
  函数, 从 Profile 的 enumList 读 descCh 标签, 而不是硬编码选项表.
  好处是枚举变化时不需要改适配器; 坏处是每次调用都要遍历 Profile
  (字段数量很少, 性能可忽略).

  两个函数的分工: bool 字段用 _flag_value, enum 字段用 _enum_text.

关于诊断字段的 entity_category:

  故障状态 / 信号强度 / 信号等级 / Wi-Fi 名称 / IP 地址 / BSSID 都
  归入 diagnostic 类别, 折叠到"诊断"区域. 主界面只保留温度 / 湿度 /
  电池电量 / 低电量告警 / 故障告警 5 个.

  故障告警 (binary_sensor, problem) 保持主界面, 因为故障发生是用户
  需要立刻看到的告警. 与 2DAD 的 fault / fault_code 分工一致.
"""

from __future__ import annotations

from typing import Any, Mapping

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


def _flag_value(value: Any) -> bool | None:
    """严格解析 bool: 接受 0/1, 字符串 "0"/"1"/"true"/"false"/"on"/"off",
    以及 JSON 布尔 true/false, 其它返回 None.

    这是 2GB1 的 battery.alarm 和 commonFaultDetection.status 的解析
    函数, 与 2BE5 / 2BE6 / 2BE8 的 _flag_value 命名和实现完全一致,
    四个麦乐克适配器风格统一.

    旧版用 int(str(raw).strip()) 转换:
      - "1" / "0" -> 能解析
      - "true" / "false" / "on" / "off" -> int() 抛 ValueError, 返回 None
      - 1.0 (float) -> int("1.0") 抛 ValueError, 返回 None
    本版用 token 匹配 + 数字比较, 兼容所有常见布尔表示.
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


def _enum_text(context: DeviceContext, sid: str, name: str) -> str | None:
    """Map a reported enum value onto its Profile descCh label.

    与 _flag_value 分工: bool 字段用 _flag_value, enum 字段用 _enum_text.
    _enum_text 从 Profile 的 enumList 读 descCh 标签, 而不是硬编码选项表.

    旧版用 int(str(raw).strip()) 转换, 如果设备上报 20.0 (float), 会走
    except 分支返回 _text(20.0) = "20.0", 不匹配 enumList 里的 "20",
    导致显示 "20.0" 而不是 "4格信号". 本版用 _number 转换, 支持 float.
    """
    raw = context.value(sid, name)
    if raw is None or isinstance(raw, bool):
        return None
    # 先尝试数字转换, 支持 int / float / 数字字符串
    number = _number(raw)
    if number is None:
        # 非数字, 直接返回原始字符串 (设备可能上报枚举字符串)
        # 这比返回 None 让用户看到原始值更有信息量
        return _text(raw)
    key = str(int(number))
    field = _field(context.profile, sid, name)
    if field is None:
        return None
    for option in field.get("enumList", ()) or ():
        if str(option.get("enumVal")) == key:
            return str(option.get("descCh") or option.get("enumVal"))
    return None


# ---- netInfo 诊断实体 ----------------------------------------------------

def _net_info_entities(context: DeviceContext, profile: Any) -> list[EntitySpec]:
    if not context.has_service("netInfo"):
        return []
    entities: list[EntitySpec] = []

    if _field(profile, "netInfo", "RSSI") is not None:
        entities.append(
            EntitySpec(
                platform="sensor",
                key="wifi_rssi",
                name="信号强度",
                state=lambda ctx: {
                    "native_value": _number(ctx.value("netInfo", "RSSI"))
                },
                metadata={
                    "state_class": "measurement",
                    "unit": "dBm",
                    "entity_category": "diagnostic",
                },
            )
        )

    if _field(profile, "netInfo", "intensity") is not None:
        entities.append(
            EntitySpec(
                platform="sensor",
                key="wifi_level",
                name="信号等级",
                state=lambda ctx: {
                    "native_value": _enum_text(ctx, "netInfo", "intensity")
                },
                metadata={"entity_category": "diagnostic"},
            )
        )

    for char_name, key, label in (
        ("SSID", "wifi_ssid", "Wi-Fi 名称"),
        ("IP", "wifi_ip", "IP 地址"),
        ("BSSID", "wifi_bssid", "BSSID"),
    ):
        if _field(profile, "netInfo", char_name) is None:
            continue
        entities.append(
            EntitySpec(
                platform="sensor",
                key=key,
                name=label,
                state=lambda ctx, _n=char_name: {
                    "native_value": _text(ctx.value("netInfo", _n))
                },
                metadata={"entity_category": "diagnostic"},
            )
        )
    return entities


# ---- 适配器 --------------------------------------------------------------

class Product2GB1Adapter:
    """麦乐克温湿度传感器 MIR-TE100 (2GB1) 适配器."""

    prod_id = "2GB1"

    def entities(self, context: DeviceContext) -> tuple[EntitySpec, ...]:
        profile = context.profile
        if profile is None:
            return ()

        entities: list[EntitySpec] = []

        # --- temperature.current -> sensor 温度 -------------------------
        if context.has_service("temperature") and _field(
            profile, "temperature", "current"
        ) is not None:
            entities.append(
                EntitySpec(
                    platform="sensor",
                    key="temperature",
                    name="温度",
                    state=lambda ctx: {
                        "native_value": _number(ctx.value("temperature", "current"))
                    },
                    metadata={
                        "device_class": "temperature",
                        "state_class": "measurement",
                        "unit": "°C",
                    },
                )
            )

        # --- humidity.current -> sensor 湿度 ----------------------------
        if context.has_service("humidity") and _field(
            profile, "humidity", "current"
        ) is not None:
            entities.append(
                EntitySpec(
                    platform="sensor",
                    key="humidity",
                    name="湿度",
                    state=lambda ctx: {
                        "native_value": _number(ctx.value("humidity", "current"))
                    },
                    metadata={
                        "device_class": "humidity",
                        "state_class": "measurement",
                        "unit": "%",
                    },
                )
            )

        # --- battery.level -> sensor 电池电量 ---------------------------
        if context.has_service("battery") and _field(
            profile, "battery", "level"
        ) is not None:
            entities.append(
                EntitySpec(
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
                )
            )

        # --- battery.alarm -> binary_sensor 低电量告警 ------------------
        if _field(profile, "battery", "alarm") is not None:
            entities.append(
                EntitySpec(
                    platform="binary_sensor",
                    key="battery_low",
                    name="低电量告警",
                    state=lambda ctx: {
                        "is_on": _flag_value(ctx.value("battery", "alarm"))
                    },
                    metadata={"device_class": "battery"},
                )
            )

        # --- commonFaultDetection.code -> sensor 故障状态 ---------------
        if context.has_service("commonFaultDetection"):
            if _field(profile, "commonFaultDetection", "code") is not None:
                entities.append(
                    EntitySpec(
                        platform="sensor",
                        key="fault_state",
                        name="故障状态",
                        state=lambda ctx: {
                            "native_value": _enum_text(
                                ctx, "commonFaultDetection", "code"
                            )
                        },
                        metadata={"entity_category": "diagnostic"},
                    )
                )

            # --- commonFaultDetection.status -> binary_sensor 故障告警 --
            if _field(profile, "commonFaultDetection", "status") is not None:
                entities.append(
                    EntitySpec(
                        platform="binary_sensor",
                        key="fault_problem",
                        name="故障告警",
                        state=lambda ctx: {
                            "is_on": _flag_value(
                                ctx.value("commonFaultDetection", "status")
                            )
                        },
                        metadata={"device_class": "problem"},
                    )
                )

        # --- netInfo 诊断 ------------------------------------------------
        entities.extend(_net_info_entities(context, profile))
        return tuple(entities)


ADAPTER = Product2GB1Adapter()
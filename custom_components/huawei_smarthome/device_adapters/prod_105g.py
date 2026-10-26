"""User-contributed protocol for Huawei product 105G (BroadLink 智能排插 MP1-1K4S).

设备类型: 智能插排 (MultiSocket), 型号 MP1-1K4S
制造商: 杭州古北电子科技有限公司 (BroadLink)

4 个并列的开关服务, 每个只有 on 字段 (bool RW, 0 关 / 1 开):

  switch.on   -> switch "插座1"
  switch1.on  -> switch "插座2"
  switch2.on  -> switch "插座3"
  switch3.on  -> switch "插座4"

故意不暴露:

  timer.*     array, 需要专用定时器 UI
  delay.*     array, 需要专用倒计时 UI
  update.*    OTA

注意: quickmenu 只引用 switch/on, 但 services 里 4 个开关是并列声明的,
说明是 4 孔独立控制排插. 每个插孔都能单独开关, 所以 4 个全部暴露.
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
    """严格解析 bool: 只接受 0/1 及等价字符串/布尔, 其它返回 None."""
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


# ---- 写动作工厂 (4 个插孔 x 2 个动作 = 8 个, 工厂更简洁) ---------------

def _power_on(sid: str):
    async def _action(ctx: DeviceContext, _data: Mapping[str, Any]) -> None:
        await ctx.async_send_service(sid, {"on": 1})
    return _action


def _power_off(sid: str):
    async def _action(ctx: DeviceContext, _data: Mapping[str, Any]) -> None:
        await ctx.async_send_service(sid, {"on": 0})
    return _action


# ---- 插孔定义 ----------------------------------------------------------

# (sid, key, name)
_SOCKETS: tuple[tuple[str, str, str], ...] = (
    ("switch",  "socket_1", "插座1"),
    ("switch1", "socket_2", "插座2"),
    ("switch2", "socket_3", "插座3"),
    ("switch3", "socket_4", "插座4"),
)


# ---- 适配器 -------------------------------------------------------------

class Product105GAdapter:
    """BroadLink 智能排插 MP1-1K4S (105G) 适配器."""

    prod_id = "105G"

    def entities(self, context: DeviceContext) -> tuple[EntitySpec, ...]:
        profile = context.profile
        if profile is None:
            return ()

        entities: list[EntitySpec] = []
        for sid, key, name in _SOCKETS:
            if not context.has_service(sid):
                continue
            if _field(profile, sid, "on") is None:
                continue
            entities.append(EntitySpec(
                platform="switch",
                key=key,
                name=name,
                state=lambda ctx, _s=sid: {
                    "is_on": _as_bool(ctx.value(_s, "on"))
                },
                actions={
                    "turn_on": _power_on(sid),
                    "turn_off": _power_off(sid),
                },
            ))

        return tuple(entities)


ADAPTER = Product105GAdapter()
"""The Konke (控客小K) integration.

Rewritten as a config-entry integration so that:
  * the device shows up in the UI under Settings -> Devices & services,
  * it can be assigned to an area (room) from the UI,
  * HA no longer warns about attaching a device without a config entry.
"""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_AREA, DOMAIN, MANUFACTURER, format_mac
from .protocol import firmware_from_status, probe_device

_LOGGER = logging.getLogger(__name__)

KonkeConfigEntry = ConfigEntry


async def async_setup_entry(hass: HomeAssistant, entry: KonkeConfigEntry) -> bool:
    """Set up a Konke device from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    await hass.config_entries.async_forward_entry_setups(entry, ["switch"])

    # Register the device in the device registry so it can be placed in a room.
    # Config-entry integrations are allowed to attach devices; YAML platform
    # integrations are not.
    registry = dr.async_get(hass)
    mac = entry.data.get("mac")
    area_id = entry.data.get(CONF_AREA) or None
    sw_version = entry.data.get("sw_version") or None

    if sw_version is None:
        # The firmware version only appears in the raw lan_phone reply, not in
        # pykonkeio's fetch_info()/update(). Probe once and remember it.
        # The device may be offline — that must not break the setup, the
        # firmware version is optional.
        try:
            reply = await hass.async_add_executor_job(
                probe_device, entry.data["host"], 2.0
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug(
                "Could not probe firmware for %s: %s", entry.data["host"], err
            )
            reply = None
        sw_version = firmware_from_status((reply or {}).get("status"))
        if sw_version:
            hass.config_entries.async_update_entry(
                entry, data={**entry.data, "sw_version": sw_version}
            )

    device = registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, mac or entry.data["host"])},
        name=entry.title,
        manufacturer=MANUFACTURER,
        model=entry.data.get("model"),
        sw_version=sw_version,
        connections={(dr.CONNECTION_NETWORK_MAC, format_mac(mac))} if mac else None,
        suggested_area=area_id,
    )
    # suggested_area 只在设备「首次创建」时生效，已存在的设备不会被覆盖
    # （见 homeassistant/helpers/device_registry.py 的 _async_get_or_create：
    #   suggested_area 仅在新建分支里用来 async_get_or_create 区域）。
    #
    # 曾经这里还有一刀「强制刷回配置项里的 area」：
    #     if area_id and device.area_id != area_id:
    #         device = registry.async_update_device(device.id, area_id=area_id)
    # 但它无法区分「设备还没落位」和「用户在 UI 里手动改过房间」，于是每次
    # HA 重启都会把用户刚拖到别的房间的设备强行拽回配置的默认房间。
    #
    # 现在只在设备「完全没有区域」时才补一次，之后完全尊重用户在 UI 的选择。
    if area_id and device.area_id is None:
        device = registry.async_update_device(device.id, area_id=area_id)
    hass.data[DOMAIN][entry.entry_id] = device
    _LOGGER.info(
        "Konke device registered: id=%s name=%s mac=%s area=%s",
        device.id,
        device.name,
        mac,
        device.area_id,
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: KonkeConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, ["switch"])
    if unloaded:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unloaded

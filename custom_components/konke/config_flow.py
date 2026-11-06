"""Config flow for the Konke (控客小K) integration.

The device is identified by its IP address on the local network; the user
enters that once, together with a name and the room it belongs to.
"""

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.helpers.selector import AreaSelector

from .const import CONF_AREA, CONF_MODEL, DOMAIN, MODELS
from .protocol import firmware_from_status, probe_device

try:
    from pykonkeio.error import DeviceNotSupport, DeviceOffline
except ImportError:  # pragma: no cover - dependency not installed yet
    # The dependency is installed by Home Assistant from manifest.json before
    # the config flow module is ever imported. These placeholders only exist so
    # the module can be parsed in isolation.
    class DeviceNotSupport(Exception):  # noqa: N818
        """Placeholder for pykonkeio.error.DeviceNotSupport."""

    class DeviceOffline(Exception):  # noqa: N818
        """Placeholder for pykonkeio.error.DeviceOffline."""

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_MODEL, default="minik"): vol.In(MODELS),
        vol.Optional(CONF_NAME, default=""): str,
        vol.Optional(CONF_AREA): AreaSelector(),
    }
)


async def _probe_device(host: str, model: str) -> dict:
    """Talk to the device and return its identity.

    Raises TimeoutError when the device does not answer, DeviceOffline when
    the device is unreachable and DeviceNotSupport for an unknown model.
    """
    from pykonkeio import manager
    from pykonkeio.error import DeviceNotSupport, DeviceOffline

    device = manager.get_device(host, model)
    try:
        await device.fetch_info()
        await device.update()
    except DeviceNotSupport:
        raise
    except DeviceOffline:
        raise
    if not device.mac:
        raise TimeoutError(f"no answer from {host}")

    # fetch_info()/update() only report 'on'/'off' — the firmware version only
    # shows up in the raw lan_phone reply.
    raw = probe_device(host)
    status = (raw or {}).get("status")
    return {
        "mac": device.mac,
        "status": status,
        "sw_version": firmware_from_status(status),
    }


class KonkeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the Konke (控客小K) integration."""

    VERSION = 2

    async def async_step_user(
        self, user_input: dict[str, str] | None = None
    ) -> ConfigFlowResult:
        """Ask for the device IP, model, name and room."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            model = user_input[CONF_MODEL].lower()
            name = (user_input.get(CONF_NAME) or "").strip() or f"控客小K {host}"

            try:
                info = await _probe_device(host, model)
            except TimeoutError:
                errors[CONF_HOST] = "device_not_found"
            except DeviceOffline:
                errors[CONF_HOST] = "device_offline"
            except DeviceNotSupport:
                errors[CONF_MODEL] = "unsupported_model"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error probing %s", host)
                errors[CONF_HOST] = "cannot_connect"
            else:
                await self.async_set_unique_id(info["mac"])
                self._abort_if_unique_id_configured()
                self.context["title_placeholders"] = {"name": name}
                return self.async_create_entry(
                    title=name,
                    data={
                        CONF_HOST: host,
                        CONF_MODEL: model,
                        CONF_NAME: name,
                        "mac": info["mac"],
                        "sw_version": info.get("sw_version"),
                        CONF_AREA: user_input.get(CONF_AREA),
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )

    async def async_step_import(
        self, import_data: dict[str, str]
    ) -> ConfigFlowResult:
        """Import from configuration.yaml (keeps YAML users working)."""
        return self.async_create_entry(
            title=import_data.get(CONF_NAME) or f"控客小K {import_data[CONF_HOST]}",
            data={
                CONF_HOST: import_data[CONF_HOST],
                CONF_MODEL: import_data.get(CONF_MODEL, "minik").lower(),
                CONF_NAME: import_data.get(CONF_NAME, ""),
            },
        )

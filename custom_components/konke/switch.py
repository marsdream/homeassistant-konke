"""
Support for the Konke outlet.

For more details about this platform, please refer to the documentation at
https://github.com/marsdream/homeassistant-konke
"""

import logging
import time

import voluptuous as vol

from datetime import timedelta

from homeassistant.components.switch import PLATFORM_SCHEMA, SwitchEntity
from homeassistant.const import CONF_NAME, CONF_HOST
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import homeassistant.helpers.config_validation as cv

from .const import MANUFACTURER, format_mac

REQUIREMENTS = ['pykonkeio>=2.1.7']

_LOGGER = logging.getLogger(__name__)

DOMAIN = "konke"

# HA 的 EntityComponent 靠平台模块的 SCAN_INTERVAL 决定是否轮询
# (entity_component.py: scan_interval=getattr(platform, "SCAN_INTERVAL", None))。
# 上游 5high/konke 未声明该常量 -> 平台拿到 None -> 实体完全不轮询 ->
# 状态永远停在启动时的快照。补上 30 秒轮询，状态才能持续跟随设备实际通断。
SCAN_INTERVAL = timedelta(seconds=30)

DEFAULT_NAME = 'Konke Outlet'

CONF_MODEL = 'model'
MODEL_K1 = ['smart plugin', 'k1']
MODEL_K2 = ['k2', 'k2 pro']
MODEL_MINIK = ['minik', 'minik pro']
MODEL_MUL = ['mul']
MODEL_MICMUL = ['micmul']

MODEL_SWITCH = MODEL_K1 + MODEL_K2 + MODEL_MINIK
MODEL_POWER_STRIP = MODEL_MUL + MODEL_MICMUL

UPDATE_DEBONCE = 0.3

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST): cv.string,
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Optional(CONF_MODEL): vol.In(MODEL_SWITCH + MODEL_POWER_STRIP)
})


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Legacy YAML platform setup (kept for configuration.yaml users)."""
    from pykonkeio.manager import get_device
    from pykonkeio.error import DeviceNotSupport, DeviceOffline
    name = config[CONF_NAME]
    host = config[CONF_HOST]
    model = config[CONF_MODEL].lower()
    entities = []

    try:
        device = get_device(host, model)
    except DeviceNotSupport:
        _LOGGER.error(
            'Unsupported device found! Please create an issue at '
            'https://github.com/marsdream/homeassistant-konke/issues '
            'and provide the following data: %s', model)
        return False

    # 原上游只 await device.update()，但 update() 走 send_message('check')，
    # 仅在 is_online 为 False 时才调 fetch_info()。
    # pykonkeio 的 device 对象 is_online 默认 True -> mac 从未被填充 ->
    # 实体构造时 identifiers={(DOMAIN, None)} -> 设备注册失败，
    # UI 里「此设备无法通过用户界面添加」、也加不进房间。
    # fetch_info() 会显式走 manager.get_device_info()，确保 mac/password 就位。
    #
    # 设备离线时这两个调用都会抛 DeviceOffline，但不该让整个平台 setup 失败。
    try:
        await device.fetch_info()
        await device.update()
    except DeviceOffline:
        _LOGGER.warning(
            'Konke device %s at %s is offline — creating entities anyway',
            model,
            host,
        )

    if hasattr(device, 'socket_count'):
        powerstrip = KonkePowerStrip(device, name)
        for i in range(device.socket_count):
            entities.append(KonkePowerStripOutlet(powerstrip, name, i))

        for i in range(device.usb_count or 0):
            entities.append(KonkePowerStripUSB(powerstrip, name, i))
    else:
        entities.append(KonkeOutlet(name, device, model))
        if hasattr(device, 'usb_status'):
            entities.append(KonkeUsbSwitch(name, device))

    async_add_entities(entities)


async def async_setup_entry(
    hass, entry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the switch entities for a config entry."""
    from pykonkeio.error import DeviceNotSupport, DeviceOffline
    from pykonkeio.manager import get_device

    data = entry.data
    name = data.get(CONF_NAME) or entry.title
    host = data[CONF_HOST]
    model = data.get(CONF_MODEL, "minik").lower()
    entities = []

    try:
        device = get_device(host, model)
    except DeviceNotSupport:
        _LOGGER.error(
            "Unsupported Konke model %s at %s — please report the exact model",
            model,
            host,
        )
        return

    # update() 仅在 is_online 为 False 时才调 fetch_info()，
    # 而 pykonkeio 的 device 对象 is_online 默认 True -> mac 永远不被填充。
    # 显式 fetch_info() 保证 mac/password 就位（unique_id 与设备注册依赖它）。
    #
    # 设备离线时这两个调用都会抛 DeviceOffline，但不该让整个平台 setup 失败，
    # 否则实体都建不出来。继续建实体，状态由 available 属性标记为 unavailable。
    try:
        await device.fetch_info()
        await device.update()
    except DeviceOffline:
        _LOGGER.warning(
            "Konke device %s at %s is offline — creating entities anyway",
            model,
            host,
        )

    if hasattr(device, "socket_count"):
        powerstrip = KonkePowerStrip(device, name)
        for i in range(device.socket_count):
            entities.append(KonkePowerStripOutlet(powerstrip, name, i))
        for i in range(device.usb_count or 0):
            entities.append(KonkePowerStripUSB(powerstrip, name, i))
    else:
        entities.append(
            KonkeOutlet(
                name,
                device,
                model,
                entry.entry_id,
                unique_id=data.get("mac") or host,
            )
        )
        if hasattr(device, "usb_status"):
            entities.append(
                KonkeUsbSwitch(
                    name, device, entry.entry_id, unique_id=data.get("mac") or host
                )
            )

    async_add_entities(entities)


class KonkeOutlet(SwitchEntity):

    _attr_has_entity_name = False

    def __init__(self, name, device, model=None, entry_id=None, unique_id=None):
        self._name = name
        self._device = device
        self._model = model
        self._current_power_w = None
        self._entry_id = entry_id
        # A stable identifier. The MAC is only known once the device answers,
        # so the config entry passes the MAC it recorded at discovery time.
        # Falling back to the host keeps the entity usable (and unique) even
        # while the device is offline.
        self._unique_id = unique_id or getattr(device, "mac", None) or name
        # device_info 只在「有 config entry」的集成里生效。
        # YAML 平台集成（无 config entry）会被 HA 强制丢弃设备对象
        # (entity_platform.py: device = None)，所以这里仅在 entry_id
        # 存在时提供 device_info。
        if entry_id is not None:
            mac = getattr(device, "mac", None)
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, self._unique_id)},
                name=name,
                manufacturer=MANUFACTURER,
                model=model,
                sw_version=self._firmware_version(),
                connections={(CONNECTION_NETWORK_MAC, format_mac(mac))}
                if mac
                else None,
            )

    def _firmware_version(self):
        """Best-effort firmware string from the device status field."""
        status = getattr(self._device, "status", None) or ""
        # status looks like 'close#<hw-version>#<sw-version>'
        parts = [p for p in str(status).split("#") if p.startswith(("hv", "sv"))]
        return " / ".join(parts) if parts else None

    @property
    def should_poll(self) -> bool:
        """Poll the plug."""
        return True

    @property
    def available(self) -> bool:
        """Return True if outlet is available."""
        return self._device.is_online

    @property
    def unique_id(self):
        """Return unique ID for light."""
        return self._unique_id

    @property
    def name(self):
        """Return the display name of this outlet."""
        return self._name

    @property
    def is_on(self):
        """Instruct the outlet to turn on."""
        return self._device.status == 'open'

    @property
    def current_power_w(self):
        """Return the current power usage in W."""
        return self._current_power_w

    async def async_turn_on(self, **kwargs):
        """Instruct the outlet to turn on."""
        await self._device.turn_on()
        _LOGGER.debug("Turn on outlet %s", self.unique_id)

    async def async_turn_off(self, **kwargs):
        """Instruct the outlet to turn off."""
        await self._device.turn_off()
        _LOGGER.debug("Turn off outlet %s", self.unique_id)

    async def async_update(self):
        """Synchronize state with outlet."""
        from pykonkeio.error import DeviceOffline
        prev_available = self.available
        try:
            await self._device.update(type='relay')

            if self._model in MODEL_K2:
                self._current_power_w = await self._device.get_power()
        except DeviceOffline:
            if prev_available:
                _LOGGER.warning('Device is offline %s', self.entity_id)


class KonkeUsbSwitch(SwitchEntity):
    def __init__(self, name, device, entry_id=None, unique_id=None):
        self._name = name
        self._device = device
        self._entry_id = entry_id
        self._unique_id = unique_id or getattr(device, "mac", None) or name

    @property
    def should_poll(self) -> bool:
        """Poll the plug."""
        return True

    @property
    def available(self) -> bool:
        """Return True if outlet is available."""
        return self._device.is_online

    @property
    def unique_id(self):
        """Return unique ID for light."""
        return '%s:usb' % self._unique_id

    @property
    def name(self):
        """Return the display name of this outlet."""
        return '%s_usb' % self._name

    @property
    def is_on(self):
        """Instruct the outlet to turn on."""
        return self._device.usb_status == 'open'

    async def async_turn_on(self, **kwargs):
        """Instruct the outlet to turn on."""
        await self._device.turn_on_usb()
        _LOGGER.debug("Turn on usb %s", self.unique_id)

    async def async_turn_off(self, **kwargs):
        """Instruct the outlet to turn off."""
        await self._device.turn_off_usb()
        _LOGGER.debug("Turn off usb %s", self.unique_id)

    async def async_update(self):
        """Synchronize state with outlet."""
        from pykonkeio.error import DeviceOffline
        prev_available = self.available
        try:
            await self._device.update(type='usb')
        except DeviceOffline:
            if prev_available:
                _LOGGER.warning('Device is offline %s', self.entity_id)



class KonkePowerStrip(object):

    def __init__(self, device, name: str):
        """Initialize the power strip."""
        self._name = name
        self._device = device
        self._last_update = 0

    @property
    def available(self) -> bool:
        """Return True if outlet is available."""
        return self._device.is_online

    @property
    def unique_id(self):
        """Return unique ID for outlet."""
        return self._device.mac

    @property
    def name(self):
        """Return the display name of this outlet."""
        return self._name

    def get_status(self, index):
        """Return true if outlet is on."""
        return self._device.status[index] == 'open'

    def get_usb_status(self, index):
        """Return true if usb is on."""
        return self._device.usb_status[index] == 'open'

    async def async_turn_on(self, index):
        """Instruct the outlet to turn on."""
        await self._device.turn_on(index)

    async def async_turn_off(self, index):
        """Instruct the outlet to turn off."""
        await self._device.turn_off(index)

    async def async_turn_on_usb(self, index):
        """Instruct the usb to turn on."""
        await self._device.turn_on_usb(index)

    async def async_turn_off_usb(self, index):
        """Instruct the outlet to turn off."""
        await self._device.turn_off_usb(index)

    async def async_update(self):
        """Synchronize state with power strip."""
        from pykonkeio.error import DeviceOffline
        prev_available = self.available
        if time.time() - self._last_update >= UPDATE_DEBONCE:
            self._last_update = time.time()
            try:
                await self._device.update()
            except DeviceOffline:
                if prev_available:
                    _LOGGER.warning('Device is offline %s', self.unique_id)


class KonkePowerStripOutlet(SwitchEntity):
    """Outlet in Konke Power Strip."""

    def __init__(self, powerstrip: KonkePowerStrip, name: str, index: int):
        """Initialize the outlet."""
        self._powerstrip = powerstrip
        self._index = index
        self._name = name
        self._is_on = False

    @property
    def should_poll(self) -> bool:
        """Poll the plug."""
        return True

    @property
    def available(self) -> bool:
        """Return True if outlet is available."""
        return self._powerstrip.available

    @property
    def unique_id(self):
        """Return unique ID for outlet."""
        return "%s:%s" % (self._powerstrip.unique_id, self._index + 1)

    @property
    def name(self):
        """Return the display name of this outlet."""
        return '%s_%s' % (self._name, self._index + 1)

    @property
    def is_on(self):
        """Return true if outlet is on."""
        return self._powerstrip.get_status(self._index)

    async def async_turn_on(self, **kwargs):
        """Instruct the outlet to turn on."""
        await self._powerstrip.async_turn_on(self._index)
        _LOGGER.debug("Turn on outlet %s", self.unique_id)

    async def async_turn_off(self, **kwargs):
        """Instruct the outlet to turn off."""
        await self._powerstrip.async_turn_off(self._index)
        _LOGGER.debug("Turn off outlet %s", self.unique_id)

    async def async_update(self):
        """Synchronize state with power strip."""
        await self._powerstrip.async_update()


class KonkePowerStripUSB(SwitchEntity):
    """Outlet in Konke Power Strip."""

    def __init__(self, powerstrip: KonkePowerStrip, name: str, index: int):
        """Initialize the outlet."""
        self._powerstrip = powerstrip
        self._index = index
        self._name = name

    @property
    def should_poll(self) -> bool:
        """Poll the plug."""
        return True

    @property
    def available(self) -> bool:
        """Return True if outlet is available."""
        return self._powerstrip.available

    @property
    def unique_id(self):
        """Return unique ID for outlet."""
        return "%s:usb_%s" % (self._powerstrip.unique_id, self._index + 1)

    @property
    def name(self):
        """Return the display name of this outlet."""
        return '%s_usb%s' % (self._name, self._index + 1)

    @property
    def is_on(self):
        """Return true if outlet is on."""
        return self._powerstrip.get_usb_status(self._index)

    async def async_turn_on(self, **kwargs):
        """Instruct the outlet to turn on."""
        await self._powerstrip.async_turn_on_usb(self._index)
        _LOGGER.debug("Turn on outlet %s", self.unique_id)

    async def async_turn_off(self, **kwargs):
        """Instruct the outlet to turn off."""
        await self._powerstrip.async_turn_off_usb(self._index)
        _LOGGER.debug("Turn off outlet %s", self.unique_id)

    async def async_update(self):
        """Synchronize state with power strip."""
        await self._powerstrip.async_update()

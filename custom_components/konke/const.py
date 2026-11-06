"""Constants for the Konke (控客小K) integration."""

DOMAIN = "konke"

CONF_MODEL = "model"
CONF_AREA = "area"

MODEL_K1 = ["smart plugin", "k1"]
MODEL_K2 = ["k2", "k2 pro"]
MODEL_MINIK = ["minik", "minik pro"]
MODEL_MUL = ["mul"]
MODEL_MICMUL = ["micmul"]

MODEL_SWITCH = MODEL_K1 + MODEL_K2 + MODEL_MINIK
MODEL_POWER_STRIP = MODEL_MUL + MODEL_MICMUL

MODELS = MODEL_SWITCH + MODEL_POWER_STRIP

MANUFACTURER = "Hangzhou Konke Technology"


def format_mac(mac: str) -> str:
    """Normalise a MAC address to HA's colon-separated form.

    pykonkeio reports MACs like 'aa-bb-cc-dd-ee-ff'; the device registry
    requires 'aa:bb:cc:dd:ee:ff'.
    """
    return str(mac).replace("-", ":").replace(".", ":").lower()

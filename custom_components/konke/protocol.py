"""Low-level Konke UDP protocol helpers shared by the config flow and setup.

The vendor protocol talks to the device over UDP 27431 with AES-encrypted
payloads. The `lan_phone` probe is the only request that returns the full
device identity (mac / password / status / type) in one shot — `fetch_info()`
and `update()` in pykonkeio do not expose the firmware version.
"""

import socket
import time

# The device only answers UDP 27431.
KONKE_PORT = 27431


def probe_device(host: str, timeout: float = 2.0) -> dict | None:
    """Send one `lan_phone` probe and return the parsed reply.

    Returns None when the device does not answer within `timeout`.
    """
    try:
        from pykonkeio import utils
    except ImportError:
        return None

    # NOTE: build the payload with the same field layout the vendor app uses:
    #   lan_phone%mac%nopassword%<timestamp>%heart
    # Do NOT use %-formatting on the literal — the protocol itself uses '%' as
    # a field separator, so "%mac%" would be parsed as a format spec.
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    cmd = f"lan_phone%mac%nopassword%{stamp}%heart"
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(utils.encrypt(cmd), (host, KONKE_PORT))
        data, _ = sock.recvfrom(512)
        msg = utils.decrypt(data)
    except Exception:  # noqa: BLE001 - any failure means "no answer"
        return None
    finally:
        sock.close()

    parts = msg.split("%")
    # lan_device%mac%password%status%type
    if len(parts) < 4 or parts[0] != "lan_device":
        return None
    return {
        "mac": parts[1],
        "password": parts[2] if len(parts) > 2 else None,
        "status": parts[3],
        "type": parts[4] if len(parts) > 4 else None,
    }


def firmware_from_status(status: str | None) -> str | None:
    """Extract a firmware string from a status payload.

    Status looks like 'close#<hw-version>#<sw-version>' — keep only the hv/sv parts.
    """
    if not status:
        return None
    parts = [p for p in str(status).split("#") if p.startswith(("hv", "sv"))]
    return " / ".join(parts) if parts else None

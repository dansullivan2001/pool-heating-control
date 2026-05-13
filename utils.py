# utils.py
__version__ = "0.1.1"

# Maximum log lines held in memory.
# Keeps RAM usage bounded on long-running Pico deployments.
_MAX_BUFFER = 50

_debug_buffer = []


def log(msg):
    """
    Print msg and append to the in-memory debug buffer.
    Oldest entries are dropped when the buffer is full.
    """
    print(msg)
    if len(_debug_buffer) >= _MAX_BUFFER:
        _debug_buffer.pop(0)
    _debug_buffer.append(msg)


def flush_debug(mqtt_publish_fn, topic):
    """
    Publish buffered log lines to an MQTT topic and clear the buffer.

    Args:
        mqtt_publish_fn:  callable matching MQTTManager.publish(topic, msg)
        topic:            the feed topic string to publish to

    Call this periodically (e.g. from the controller's publish cycle)
    when MQTT is connected. Lines are joined with newlines into one message
    to minimise publish calls.
    """
    if not _debug_buffer:
        return
    try:
        payload = "\n".join(_debug_buffer[-20:])   # send last 20 lines at most
        mqtt_publish_fn(topic, payload)
        _debug_buffer.clear()
    except Exception as e:
        print(f"⚠️ utils.flush_debug failed: {e}")


def get_buffer():
    """Return a copy of the current debug buffer (for testing/inspection)."""
    return list(_debug_buffer)


def clear_buffer():
    """Clear the debug buffer (e.g. after a simulated restart)."""
    _debug_buffer.clear()
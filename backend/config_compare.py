import re


_VOLATILE_CISCO_LINES = (
    re.compile(r"^! Last configuration change.*$"),
    re.compile(r"^! NVRAM config last updated.*$"),
)


def normalize_config_for_comparison(config):
    normalized_lines = []
    for line in config.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = line.rstrip()
        if any(pattern.match(line) for pattern in _VOLATILE_CISCO_LINES):
            continue
        normalized_lines.append(line)
    while normalized_lines and not normalized_lines[-1]:
        normalized_lines.pop()
    return "\n".join(normalized_lines)

"""Atmos 智能气象台启动入口。"""

import os
import re
import socket
import subprocess
import sys

from weather_app.factory import create_app


app = create_app()


def get_lan_addresses() -> list[str]:
    """读取带默认网关的网卡地址，并优先返回真实家庭局域网。"""

    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["ipconfig"],
                capture_output=True,
                check=False,
                timeout=5,
            )
            output = result.stdout.decode("mbcs", errors="replace")
            addresses: list[str] = []
            for block in re.split(r"\r?\n\r?\n", output):
                if "default gateway" not in block.lower():
                    continue
                found = re.findall(r"IPv4 Address[^\n]*:\s*([0-9.]+)", block, flags=re.I)
                gateway_part = re.split(r"Default Gateway[^\n]*:", block, flags=re.I)[-1]
                if not found or re.search(r"\b(?!0\.0\.0\.0)\d+\.\d+\.\d+\.\d+\b", gateway_part):
                    private = [address for address in found if _is_private_ipv4(address)]
                    addresses.extend(private)
            unique = list(dict.fromkeys(addresses))
            if unique:
                return sorted(
                    unique,
                    key=lambda address: (
                        not address.startswith("192.168."),
                        not address.startswith("10."),
                    ),
                )
        except (OSError, subprocess.SubprocessError):
            pass

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # UDP 连接不会真正发送数据，只用于让系统选择当前出口网卡。
        sock.connect(("8.8.8.8", 80))
        address = sock.getsockname()[0]
        return [address] if _is_private_ipv4(address) else []
    except OSError:
        return []
    finally:
        sock.close()


def _is_private_ipv4(address: str) -> bool:
    """判断地址是否属于常见局域网网段。"""

    if address.startswith("192.168.") or address.startswith("10."):
        return True
    if address.startswith("172."):
        parts = address.split(".")
        return len(parts) == 4 and 16 <= int(parts[1]) <= 31
    return False


if __name__ == "__main__":
    host = os.getenv("WEATHER_HOST", "127.0.0.1")
    port = int(os.getenv("WEATHER_PORT", "5000"))
    if host in {"0.0.0.0", "::"}:
        lan_addresses = get_lan_addresses()
        print("\n网站已生成，可通过以下地址访问：")
        print(f"  本机访问：http://127.0.0.1:{port}")
        if lan_addresses:
            print(f"  朋友访问：http://{lan_addresses[0]}:{port}")
        else:
            print(f"  朋友访问：请先在 ipconfig 中确认本机局域网 IPv4 地址，端口为 {port}")
        print("  分享条件：朋友需要与你在同一局域网，并保持本窗口运行。\n")
    app.run(host=host, port=port, debug=False)

"""CLI entrypoint for CoALA Agent."""

from __future__ import annotations

import os

import colorama
from colorama import Fore, Style

from core.agent import CognitiveAgent


def main() -> None:
    # Always bypass proxy for local inference endpoint.
    os.environ["NO_PROXY"] = "localhost,127.0.0.1"
    os.environ["no_proxy"] = "localhost,127.0.0.1"

    colorama.init(autoreset=True)

    print(Fore.CYAN + "=== Qwen CoALA Agent ===")
    print(Fore.YELLOW + "正在初始化...")

    try:
        agent = CognitiveAgent()
    except Exception as exc:  # noqa: BLE001
        print(Fore.RED + f"[致命错误] 启动失败: {exc}")
        return

    print(Fore.GREEN + "已就绪。输入 'exit' 或 'quit' 退出。\n")

    while True:
        try:
            user_input = input(Fore.BLUE + "User: " + Style.RESET_ALL)
            if user_input.strip().lower() in {"exit", "quit"}:
                print("再见！")
                break
            if not user_input.strip():
                continue

            answer = agent.run(user_input)
            print(Fore.MAGENTA + f"Agent: {answer}")

        except KeyboardInterrupt:
            print("\n正在退出...")
            break
        except Exception as exc:  # noqa: BLE001
            print(Fore.RED + f"运行时错误: {exc}")


if __name__ == "__main__":
    main()

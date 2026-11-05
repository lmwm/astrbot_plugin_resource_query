# 生成默认 option.yml
#
# 用法（在插件根目录执行）：
#   python Scripts/gen_option.py                      # 写 modules/jm/option.default.yml
#   python Scripts/gen_option.py <输出路径>
#   python Scripts/gen_option.py --stdout             # 只打印
#   python Scripts/gen_option.py --base-dir D:/JM     # 指定 base_dir
#
# 默认值只来自 modules/jm/option_default.py，与运行时 option.ensure_file 同源；
# 只依赖 pyyaml，不需要 jmcomic。

from __future__ import annotations

import argparse
import copy
import importlib.util
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = PLUGIN_ROOT / "modules" / "jm" / "option_default.py"
DEFAULT_OUTPUT = PLUGIN_ROOT / "modules" / "jm" / "option.default.yml"

# 与运行时一致：下载根固定在 plugin_data/<插件目录名>/JMDownload
DEFAULT_BASE_DIR = f"plugin_data/{PLUGIN_ROOT.name}/JMDownload"


def load_defaults():
    # 按文件路径加载 option_default.py（它没有包内相对导入）
    spec = importlib.util.spec_from_file_location(
        "jm_option_default", DEFAULT_SOURCE
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载默认值：{DEFAULT_SOURCE}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def render(module, base_dir: str) -> str:
    import yaml

    payload = copy.deepcopy(module.DEFAULT_OPTION)
    payload["dir_rule"]["base_dir"] = base_dir
    return module.HEADER + yaml.safe_dump(
        payload, allow_unicode=True, sort_keys=False, default_flow_style=False
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="生成默认 option.yml（下载参数）"
    )
    parser.add_argument(
        "output",
        nargs="?",
        default=str(DEFAULT_OUTPUT),
        help=f"输出路径，默认 {DEFAULT_OUTPUT.relative_to(PLUGIN_ROOT)}",
    )
    parser.add_argument(
        "--base-dir",
        default=DEFAULT_BASE_DIR,
        help=f"写入 dir_rule.base_dir 的相对路径（相对 AstrBot 数据根），默认 {DEFAULT_BASE_DIR}",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="只打印到标准输出，不写文件",
    )
    args = parser.parse_args(argv)

    try:
        module = load_defaults()
        text = render(module, args.base_dir)
    except ImportError as e:
        print(f"缺少依赖：{e}；请先安装 pyyaml（pip install pyyaml）")
        return 1

    if args.stdout:
        print(text, end="")
        return 0

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    print(f"已生成：{output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
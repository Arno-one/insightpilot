import logging


def setup_logging() -> None:
    """初始化基础日志格式，后续可扩展为文件日志和 JSON 日志。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

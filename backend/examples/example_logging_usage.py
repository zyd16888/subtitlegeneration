"""
日志系统使用示例

演示如何在项目中使用日志系统
"""
from backend.utils.logger import setup_logger, get_logger
import time


def example_basic_logging():
    """基本日志使用示例"""
    print("=== 基本日志使用示例 ===\n")
    
    # 配置日志
    logger = setup_logger(
        name="example",
        log_level="DEBUG",
        log_file="logs/example.log"
    )
    
    # 记录不同级别的日志
    logger.debug("这是调试信息")
    logger.info("这是一般信息")
    logger.warning("这是警告信息")
    logger.error("这是错误信息")
    
    print("日志已写入 logs/example.log\n")


def example_task_logging():
    """任务处理日志示例"""
    print("=== 任务处理日志示例 ===\n")
    
    logger = get_logger("example")
    
    task_id = "task_12345"
    
    # 记录任务开始
    logger.info(f"开始处理任务: {task_id}")
    start_time = time.time()
    
    try:
        # 模拟任务处理
        logger.debug(f"任务 {task_id}: 提取音频")
        time.sleep(0.1)
        
        logger.debug(f"任务 {task_id}: 语音识别")
        time.sleep(0.1)
        
        logger.debug(f"任务 {task_id}: 翻译文本")
        time.sleep(0.1)
        
        # 记录任务完成
        elapsed = time.time() - start_time
        logger.info(f"任务完成: {task_id}, 耗时: {elapsed:.3f}s")
        
    except Exception as e:
        logger.error(f"任务失败: {task_id}", exc_info=True)
        raise
    
    print(f"任务处理完成，耗时: {elapsed:.3f}s\n")


def example_error_logging():
    """错误日志示例"""
    print("=== 错误日志示例 ===\n")
    
    logger = get_logger("example")
    
    try:
        # 模拟错误
        result = 10 / 0
    except ZeroDivisionError as e:
        # 记录错误堆栈
        logger.error("发生除零错误", exc_info=True)
        print("错误已记录到日志文件\n")


def example_api_request_logging():
    """API 请求日志示例"""
    print("=== API 请求日志示例 ===\n")
    
    logger = get_logger("example")
    
    # 模拟 API 请求
    request_id = id({})
    method = "POST"
    path = "/api/tasks"
    client_ip = "127.0.0.1"
    
    # 记录请求开始
    start_time = time.time()
    logger.info(
        f"请求开始 [ID: {request_id}] {method} {path} "
        f"客户端: {client_ip}"
    )
    
    # 模拟处理
    time.sleep(0.05)
    
    # 记录请求完成
    process_time = time.time() - start_time
    status_code = 200
    logger.info(
        f"请求完成 [ID: {request_id}] {method} {path} "
        f"状态码: {status_code} 耗时: {process_time:.3f}s"
    )
    
    print(f"API 请求处理完成，耗时: {process_time:.3f}s\n")


def example_multiple_loggers():
    """多个日志记录器示例"""
    print("=== 多个日志记录器示例 ===\n")
    
    # 配置不同的日志记录器
    api_logger = setup_logger(
        name="api",
        log_level="INFO",
        log_file="logs/api.log"
    )
    
    task_logger = setup_logger(
        name="task",
        log_level="DEBUG",
        log_file="logs/task.log"
    )
    
    # 使用不同的日志记录器
    api_logger.info("API 服务启动")
    task_logger.debug("任务队列初始化")
    
    api_logger.info("收到新请求")
    task_logger.debug("创建新任务")
    
    print("不同的日志已写入不同的文件\n")


if __name__ == "__main__":
    print("日志系统使用示例\n")
    print("=" * 50 + "\n")
    
    # 运行示例
    example_basic_logging()
    example_task_logging()
    example_error_logging()
    example_api_request_logging()
    example_multiple_loggers()
    
    print("=" * 50)
    print("\n所有示例运行完成！")
    print("请查看 logs/ 目录下的日志文件")

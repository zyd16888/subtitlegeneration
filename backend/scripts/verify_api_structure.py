"""
API 结构验证脚本

验证所有 API 端点是否正确注册
"""
from backend.main import app


def verify_api_structure():
    """验证 API 结构"""
    print("=" * 60)
    print("Emby AI 中文字幕生成服务 - API 端点验证")
    print("=" * 60)
    print()
    
    # 获取所有路由
    routes = []
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            for method in route.methods:
                if method != "HEAD":  # 忽略 HEAD 方法
                    routes.append((method, route.path, route.name))
    
    # 按路径排序
    routes.sort(key=lambda x: (x[1], x[0]))
    
    # 分组显示
    print("📋 根路径端点:")
    print("-" * 60)
    for method, path, name in routes:
        if path in ["/", "/health"]:
            print(f"  {method:8s} {path:40s} ({name})")
    print()
    
    print("📚 媒体库相关 API:")
    print("-" * 60)
    for method, path, name in routes:
        if path.startswith("/api/libraries") or path.startswith("/api/media"):
            print(f"  {method:8s} {path:40s} ({name})")
    print()
    
    print("📝 任务相关 API:")
    print("-" * 60)
    for method, path, name in routes:
        if path.startswith("/api/tasks"):
            print(f"  {method:8s} {path:40s} ({name})")
    print()
    
    print("⚙️  配置相关 API:")
    print("-" * 60)
    for method, path, name in routes:
        if path.startswith("/api/config"):
            print(f"  {method:8s} {path:40s} ({name})")
    print()
    
    print("📊 统计相关 API:")
    print("-" * 60)
    for method, path, name in routes:
        if path.startswith("/api/stats"):
            print(f"  {method:8s} {path:40s} ({name})")
    print()
    
    print("=" * 60)
    print(f"✅ 总计: {len(routes)} 个 API 端点")
    print("=" * 60)
    print()
    
    # 验证必需的端点
    required_endpoints = [
        ("GET", "/api/libraries"),
        ("GET", "/api/media"),
        ("POST", "/api/tasks"),
        ("GET", "/api/tasks"),
        ("GET", "/api/tasks/{task_id}"),
        ("POST", "/api/tasks/{task_id}/cancel"),
        ("POST", "/api/tasks/{task_id}/retry"),
        ("GET", "/api/config"),
        ("PUT", "/api/config"),
        ("POST", "/api/config/test-emby"),
        ("POST", "/api/config/test-translation"),
        ("GET", "/api/stats"),
    ]
    
    print("🔍 验证必需端点:")
    print("-" * 60)
    
    all_present = True
    for method, path in required_endpoints:
        found = any(r[0] == method and r[1] == path for r in routes)
        status = "✅" if found else "❌"
        print(f"  {status} {method:8s} {path}")
        if not found:
            all_present = False
    
    print()
    if all_present:
        print("✅ 所有必需端点都已实现！")
    else:
        print("❌ 有端点缺失，请检查实现。")
    print()
    
    # API 文档链接
    print("📖 API 文档:")
    print("-" * 60)
    print("  Swagger UI: http://localhost:8000/api/docs")
    print("  ReDoc:      http://localhost:8000/api/redoc")
    print()


if __name__ == "__main__":
    verify_api_structure()

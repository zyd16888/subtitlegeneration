"""
测试 Emby API 修复

验证 Emby 连接器能够正确获取媒体库和媒体项
"""
import asyncio
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.emby_connector import EmbyConnector
from services.config_manager import ConfigManager
from models.base import SessionLocal


async def test_emby_connection():
    """测试 Emby 连接"""
    print("=" * 60)
    print("测试 Emby API 修复")
    print("=" * 60)
    
    # 从数据库获取配置
    db = SessionLocal()
    try:
        config_manager = ConfigManager(db)
        config = await config_manager.get_config()
        
        if not config.emby_url or not config.emby_api_key:
            print("❌ Emby 未配置，请先在设置中配置 Emby URL 和 API Key")
            return
        
        print(f"\n📡 连接到 Emby: {config.emby_url}")
        
        # 创建 Emby 连接器
        emby = EmbyConnector(config.emby_url, config.emby_api_key)
        
        async with emby:
            # 测试连接
            print("\n1️⃣ 测试连接...")
            success = await emby.test_connection()
            if success:
                print("✅ 连接成功")
            else:
                print("❌ 连接失败")
                return
            
            # 获取媒体库列表
            print("\n2️⃣ 获取媒体库列表...")
            libraries = await emby.get_libraries()
            print(f"✅ 获取到 {len(libraries)} 个媒体库:")
            for lib in libraries:
                print(f"   - {lib.name} (ID: {lib.id}, 类型: {lib.type})")
            
            if not libraries:
                print("⚠️  没有找到媒体库")
                return
            
            # 测试获取第一个媒体库的媒体项
            first_lib = libraries[0]
            print(f"\n3️⃣ 获取媒体库 '{first_lib.name}' 的媒体项...")
            items = await emby.get_media_items(library_id=first_lib.id)
            print(f"✅ 获取到 {len(items)} 个媒体项")
            
            # 显示前5个媒体项
            if items:
                print("\n前5个媒体项:")
                for item in items[:5]:
                    subtitle_status = "✓" if item.has_subtitles else "✗"
                    print(f"   [{subtitle_status}] {item.name} (类型: {item.type})")
            
            # 测试按类型筛选
            print(f"\n4️⃣ 测试按类型筛选 (Movie)...")
            movies = await emby.get_media_items(
                library_id=first_lib.id,
                item_type="Movie"
            )
            print(f"✅ 获取到 {len(movies)} 个电影")
            
            print("\n" + "=" * 60)
            print("✅ 所有测试通过！")
            print("=" * 60)
            
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(test_emby_connection())

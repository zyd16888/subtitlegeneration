"""
直接测试 Emby API 原始响应

用于调试和查看 Emby API 的实际返回数据
"""
import asyncio
import httpx
import json
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.config_manager import ConfigManager
from models.base import SessionLocal


async def test_raw_emby_api():
    """测试原始 Emby API"""
    print("=" * 60)
    print("测试 Emby API 原始响应")
    print("=" * 60)
    
    # 从数据库获取配置
    db = SessionLocal()
    try:
        config_manager = ConfigManager(db)
        config = await config_manager.get_config()
        
        if not config.emby_url or not config.emby_api_key:
            print("❌ Emby 未配置")
            return
        
        base_url = config.emby_url.rstrip("/")
        api_key = config.emby_api_key
        
        print(f"\n📡 Emby URL: {base_url}")
        print(f"🔑 API Key: {api_key[:10]}...")
        
        headers = {
            "X-Emby-Token": api_key,
            "Accept": "application/json"
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # 1. 测试系统信息
            print("\n" + "=" * 60)
            print("1️⃣ 测试 /System/Info")
            print("=" * 60)
            try:
                url = f"{base_url}/System/Info"
                print(f"请求: GET {url}")
                response = await client.get(url, headers=headers)
                print(f"状态码: {response.status_code}")
                if response.status_code == 200:
                    data = response.json()
                    print(f"✅ 服务器名称: {data.get('ServerName')}")
                    print(f"✅ 版本: {data.get('Version')}")
                else:
                    print(f"❌ 错误: {response.text}")
            except Exception as e:
                print(f"❌ 异常: {e}")
            
            # 2. 测试 VirtualFolders
            print("\n" + "=" * 60)
            print("2️⃣ 测试 /Library/VirtualFolders")
            print("=" * 60)
            try:
                url = f"{base_url}/Library/VirtualFolders"
                print(f"请求: GET {url}")
                response = await client.get(url, headers=headers)
                print(f"状态码: {response.status_code}")
                if response.status_code == 200:
                    data = response.json()
                    print(f"✅ 返回数据类型: {type(data)}")
                    print(f"✅ 媒体库数量: {len(data) if isinstance(data, list) else 'N/A'}")
                    print("\n原始响应数据:")
                    print(json.dumps(data, indent=2, ensure_ascii=False))
                    
                    if isinstance(data, list) and len(data) > 0:
                        print("\n第一个媒体库的字段:")
                        first_lib = data[0]
                        for key in first_lib.keys():
                            print(f"  - {key}: {first_lib[key]}")
                else:
                    print(f"❌ 错误: {response.text}")
            except Exception as e:
                print(f"❌ 异常: {e}")
                import traceback
                traceback.print_exc()
            
            # 3. 测试 Items (不带参数)
            print("\n" + "=" * 60)
            print("3️⃣ 测试 /Items (不带参数)")
            print("=" * 60)
            try:
                url = f"{base_url}/Items"
                params = {
                    "Recursive": "true",
                    "Limit": "5"
                }
                print(f"请求: GET {url}")
                print(f"参数: {params}")
                response = await client.get(url, headers=headers, params=params)
                print(f"状态码: {response.status_code}")
                if response.status_code == 200:
                    data = response.json()
                    print(f"✅ 返回数据类型: {type(data)}")
                    items = data.get("Items", [])
                    print(f"✅ 媒体项数量: {len(items)}")
                    print(f"✅ 总记录数: {data.get('TotalRecordCount')}")
                    
                    if items:
                        print("\n第一个媒体项的字段:")
                        first_item = items[0]
                        for key in ["Id", "Name", "Type", "Path", "MediaStreams"]:
                            if key in first_item:
                                value = first_item[key]
                                if key == "MediaStreams":
                                    print(f"  - {key}: {len(value)} streams")
                                else:
                                    print(f"  - {key}: {value}")
                else:
                    print(f"❌ 错误: {response.text}")
            except Exception as e:
                print(f"❌ 异常: {e}")
                import traceback
                traceback.print_exc()
            
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(test_raw_emby_api())

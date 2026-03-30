"""
直接测试 Emby API（不依赖数据库）

使用方法：
python backend/tests/test_emby_direct.py <EMBY_URL> <API_KEY>

例如：
python backend/tests/test_emby_direct.py http://localhost:8096 your_api_key_here
"""
import asyncio
import httpx
import json
import sys


async def test_emby_api(base_url: str, api_key: str):
    """测试 Emby API"""
    print("=" * 60)
    print("测试 Emby API 原始响应")
    print("=" * 60)
    
    base_url = base_url.rstrip("/")
    
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
                return
        except Exception as e:
            print(f"❌ 异常: {e}")
            return
        
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
                
                print("\n📋 原始响应数据:")
                print(json.dumps(data, indent=2, ensure_ascii=False))
                
                if isinstance(data, list) and len(data) > 0:
                    print("\n🔍 第一个媒体库的所有字段:")
                    first_lib = data[0]
                    for key, value in first_lib.items():
                        print(f"  - {key}: {value}")
                    
                    # 检查关键字段
                    print("\n🔑 关键字段检查:")
                    print(f"  - 有 'Id' 字段: {'Id' in first_lib}")
                    print(f"  - 有 'ItemId' 字段: {'ItemId' in first_lib}")
                    print(f"  - 有 'Name' 字段: {'Name' in first_lib}")
                    print(f"  - 有 'CollectionType' 字段: {'CollectionType' in first_lib}")
                    
                    if 'Id' in first_lib:
                        print(f"  - Id 值: {first_lib['Id']}")
                    if 'ItemId' in first_lib:
                        print(f"  - ItemId 值: {first_lib['ItemId']}")
            else:
                print(f"❌ 错误响应:")
                print(f"   状态码: {response.status_code}")
                print(f"   内容: {response.text}")
                return
        except Exception as e:
            print(f"❌ 异常: {e}")
            import traceback
            traceback.print_exc()
            return
        
        # 3. 测试 Items (不带参数)
        print("\n" + "=" * 60)
        print("3️⃣ 测试 /Items (获取前5个)")
        print("=" * 60)
        try:
            url = f"{base_url}/Items"
            params = {
                "Recursive": "true",
                "Limit": "5",
                "Fields": "Path,MediaStreams"
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
                    print("\n🔍 第一个媒体项的关键字段:")
                    first_item = items[0]
                    for key in ["Id", "Name", "Type", "Path", "MediaStreams"]:
                        if key in first_item:
                            value = first_item[key]
                            if key == "MediaStreams":
                                print(f"  - {key}: {len(value)} streams")
                                if value:
                                    subtitle_streams = [s for s in value if s.get("Type") == "Subtitle"]
                                    print(f"    - 字幕流数量: {len(subtitle_streams)}")
                            else:
                                print(f"  - {key}: {value}")
            else:
                print(f"❌ 错误响应:")
                print(f"   状态码: {response.status_code}")
                print(f"   内容: {response.text}")
        except Exception as e:
            print(f"❌ 异常: {e}")
            import traceback
            traceback.print_exc()
        
        # 4. 如果有媒体库，测试获取特定媒体库的内容
        if isinstance(data, list) and len(data) > 0:
            first_lib = data[0]
            lib_id = first_lib.get('ItemId') or first_lib.get('Id')
            lib_name = first_lib.get('Name')
            
            if lib_id:
                print("\n" + "=" * 60)
                print(f"4️⃣ 测试获取媒体库 '{lib_name}' 的内容")
                print("=" * 60)
                try:
                    url = f"{base_url}/Items"
                    params = {
                        "ParentId": lib_id,
                        "Recursive": "true",
                        "Limit": "5",
                        "Fields": "Path,MediaStreams"
                    }
                    print(f"请求: GET {url}")
                    print(f"参数: {params}")
                    response = await client.get(url, headers=headers, params=params)
                    print(f"状态码: {response.status_code}")
                    
                    if response.status_code == 200:
                        data = response.json()
                        items = data.get("Items", [])
                        print(f"✅ 媒体项数量: {len(items)}")
                        print(f"✅ 总记录数: {data.get('TotalRecordCount')}")
                        
                        if items:
                            print("\n📋 媒体项列表:")
                            for i, item in enumerate(items[:5], 1):
                                has_subs = False
                                if "MediaStreams" in item:
                                    has_subs = any(s.get("Type") == "Subtitle" for s in item["MediaStreams"])
                                sub_icon = "✓" if has_subs else "✗"
                                print(f"  {i}. [{sub_icon}] {item.get('Name')} (类型: {item.get('Type')})")
                    else:
                        print(f"❌ 错误响应:")
                        print(f"   状态码: {response.status_code}")
                        print(f"   内容: {response.text}")
                except Exception as e:
                    print(f"❌ 异常: {e}")
                    import traceback
                    traceback.print_exc()
        
        print("\n" + "=" * 60)
        print("✅ 测试完成")
        print("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("使用方法:")
        print("  python backend/tests/test_emby_direct.py <EMBY_URL> <API_KEY>")
        print("\n例如:")
        print("  python backend/tests/test_emby_direct.py http://localhost:8096 your_api_key")
        sys.exit(1)
    
    emby_url = sys.argv[1]
    api_key = sys.argv[2]
    
    asyncio.run(test_emby_api(emby_url, api_key))

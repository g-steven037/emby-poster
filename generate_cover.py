import os
import random
import requests
import base64
from datetime import datetime
from PIL import Image, ImageFilter, ImageDraw, ImageFont

from config import UPLOAD_TO_EMBY, LIBRARY_MAP, CONFIG, EMBY_CONFIG

# ================= 1. Emby 数据自动拉取核心 =================

def get_emby_item_id(library_name):
    url = f"{EMBY_CONFIG['url']}/emby/Items"
    params = {
        "api_key": EMBY_CONFIG["api_key"],
        "Recursive": "true",
        "IncludeItemTypes": "CollectionFolder,BoxSet"
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            items = response.json().get("Items", [])
            for item in items:
                if item.get("Name") == library_name:
                    return item.get("Id")
    except Exception as e:
        print(f"❌ 连接 Emby API 失败: {e}")
    return None

def download_image(url, save_path):
    try:
        response = requests.get(url, stream=True, timeout=15)
        if response.status_code == 200:
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            return True
        else:
            print(f"❌ 下载失败，状态码: {response.status_code}")
    except Exception as e:
        print(f"❌ 下载网络异常: {e}")
    return False

def fetch_latest_emby_images(library_name):
    print(f"🔍 正在 Emby 中查找媒体库: [{library_name}]...")
    lib_id = get_emby_item_id(library_name)
    if not lib_id:
        print(f"❌ 未找到媒体库 [{library_name}]。")
        return False, None, []

    url = f"{EMBY_CONFIG['url']}/emby/Items"
    params = {
        "api_key": EMBY_CONFIG["api_key"],
        "ParentId": lib_id,
        "Recursive": "true",
        "IncludeItemTypes": "Movie,Series,Episode", 
        "SortBy": "DateCreated",            
        "SortOrder": "Descending",          
        "Limit": 1000,                        # 🌟 [关键修复]: 提高到 300，防止单集更新刷屏霸 "Fields": "BackdropImageTags,SeriesId,SeriesName"  
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        raw_items = response.json().get("Items", [])
    except Exception as e:
        print(f"❌ 请求 Emby 数据失败: {e}")
        return False, None, []

    print(f"📥 成功获取到 {len(raw_items)} 条原始入库记录，正在进行深度去重筛选...")

    # === 核心去重与“单集反查剧集”逻辑 ===
    unique_items = []
    seen_names = set()
    
    for item in raw_items:
        item_type = item.get("Type")
        
        if item_type == "Episode":
            series_name = item.get("SeriesName")
            series_id = item.get("SeriesId")
            
            if not series_name or not series_id:
                continue 
                
            if series_name not in seen_names:
                seen_names.add(series_name)
                unique_items.append({
                    "Id": series_id,
                    "Name": series_name,
                    "BackdropImageTags": item.get("BackdropImageTags") 
                })
                
        elif item_type in ["Movie", "Series"]:
            name = item.get("Name", "未知")
            if name not in seen_names:
                seen_names.add(name)
                unique_items.append(item)

        # 只要严格凑齐 7 个不重复的项目，立刻停止筛选，后面的不再耗费性能处理
        if len(unique_items) == 7:
            break

    print(f"✨ 深度过滤完成！成功筛选出 {len(unique_items)} 个完全不重复的有效影视项目。")

    if len(unique_items) < 7:
        print(f"❌ 警告: 即使扫描了 300 条记录，该媒体库中不重复的项目依然不足 7 个，跳过该库。")
        return False, None, []

    os.makedirs("./input", exist_ok=True)
    bg_path = "./input/auto_bg.jpg"
    poster_paths = []

    # 1. 第 1 个不重复项目 -> 用作横版背景
    bg_item = unique_items[0]
    bg_url = f"{EMBY_CONFIG['url']}/emby/Items/{bg_item['Id']}/Images/Backdrop/0?api_key={EMBY_CONFIG['api_key']}&maxWidth=1920"
    print(f"🖼️ 尝试获取主背景 (横版): [{bg_item.get('Name')}]")
    
    if not download_image(bg_url, bg_path):
        bg_url = f"{EMBY_CONFIG['url']}/emby/Items/{bg_item['Id']}/Images/Primary?api_key={EMBY_CONFIG['api_key']}&maxWidth=1920"
        print(f"🖼️ 降级获取主背景 (竖版): [{bg_item.get('Name')}]")
        if not download_image(bg_url, bg_path):
            print("❌ 背景图下载彻底失败，终止当前库处理。")
            return False, None, []

    # 2. 第 2 到 7 个不重复项目 -> 用作 6 张底部海报墙
    for i, item in enumerate(unique_items[1:7]):
        p_path = f"./input/auto_poster_{i+1}.jpg"
        p_url = f"{EMBY_CONFIG['url']}/emby/Items/{item['Id']}/Images/Primary?api_key={EMBY_CONFIG['api_key']}&maxWidth=600"
        
        if download_image(p_url, p_path):
            poster_paths.append(p_path)
            print(f"🎞️ 海报 {i+1}: [{item.get('Name')}] -> 下载完成")
        else:
            print(f"❌ 海报 [{item.get('Name')}] 下载失败，终止当前库处理。")
            return False, None, []

    return True, bg_path, poster_paths

# ================= 2. 图像处理核心 =================

def add_rounded_corners(im, rad):
    circle = Image.new('L', (rad * 2, rad * 2), 0)
    draw = ImageDraw.Draw(circle)
    draw.ellipse((0, 0, rad * 2 - 1, rad * 2 - 1), fill=255)
    alpha = Image.new('L', im.size, 255)
    w, h = im.size
    alpha.paste(circle.crop((0, 0, rad, rad)), (0, 0))
    alpha.paste(circle.crop((0, rad, rad, rad * 2)), (0, h - rad))
    alpha.paste(circle.crop((rad, 0, rad * 2, rad)), (w - rad, 0))
    alpha.paste(circle.crop((rad, rad, rad * 2, rad * 2)), (w - rad, h - rad))
    im.putalpha(alpha)
    return im

def apply_snow_effect(bg_image):
    if not CONFIG.get("snow_enable", False):
        return bg_image

    print("❄️ 正在添加雪花点缀效果...")
    snow_layer = Image.new('RGBA', bg_image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(snow_layer)
    width, height = bg_image.size
    
    density = CONFIG.get("snow_density", 200)
    min_r, max_r = CONFIG.get("snow_size_range", (1, 4))
    min_a, max_a = CONFIG.get("snow_alpha_range", (50, 200))

    for _ in range(density):
        x = random.randint(0, width)
        y = random.randint(0, height)
        r = random.randint(min_r, max_r)
        a = random.randint(min_a, max_a)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, a))

    return Image.alpha_composite(bg_image, snow_layer)

def create_library_cover(bg_path, poster_paths, lib_key, output_path):
    print("🎨 开始合成最终封面...")
    try:
        bg = Image.open(bg_path).convert("RGBA")
        bg = bg.resize(CONFIG["output_size"], Image.Resampling.LANCZOS)
    except Exception as e:
        print(f"❌ 背景图处理失败: {e}")
        return False

    blur_radius = max(0, min(100, CONFIG["blur_percent"])) / 100.0 * 30
    if blur_radius > 0:
        bg = bg.filter(ImageFilter.GaussianBlur(blur_radius))

    bg = apply_snow_effect(bg)

    gradient = Image.new('RGBA', bg.size, (0, 0, 0, 0))
    draw_grad = ImageDraw.Draw(gradient)
    fade_width = CONFIG.get("gradient_width", 1000)
    max_alpha = CONFIG.get("gradient_max_alpha", 180)

    for x in range(fade_width):
        alpha = int(max_alpha * (1 - (x / fade_width)))
        draw_grad.line((x, 0, x, bg.size[1]), fill=(0, 0, 0, alpha))
    
    bg = Image.alpha_composite(bg, gradient)

    draw = ImageDraw.Draw(bg)
    lib_names = LIBRARY_MAP.get(lib_key, {"zh": "未知媒体库", "en": "UNKNOWN"})
    
    try:
        font_zh = ImageFont.truetype(CONFIG["font_zh_path"], CONFIG["font_zh_size"])
        font_en = ImageFont.truetype(CONFIG["font_en_path"], CONFIG["font_en_size"])
    except IOError:
        print("⚠️ 警告: 未在 fonts 目录找到字体文件，将使用系统默认字体！")
        font_zh = ImageFont.load_default()
        font_en = ImageFont.load_default()

    draw.text(CONFIG["text_pos_zh"], lib_names["zh"], font=font_zh, fill=(255, 255, 255, 255))
    draw.text(CONFIG["text_pos_en"], lib_names["en"], font=font_en, fill=(255, 255, 255, 255), spacing=15)

    total_posters_width = (CONFIG["poster_size"][0] * 6) + (CONFIG["poster_spacing"] * 5)
    start_x = (CONFIG["output_size"][0] - total_posters_width) // 2 

    for i, poster_path in enumerate(poster_paths):
        try:
            poster = Image.open(poster_path).convert("RGBA")
            poster = poster.resize(CONFIG["poster_size"], Image.Resampling.LANCZOS)
            poster = add_rounded_corners(poster, rad=15) 
            x_offset = start_x + i * (CONFIG["poster_size"][0] + CONFIG["poster_spacing"])
            bg.paste(poster, (x_offset, CONFIG["poster_y_pos"]), poster) 
        except Exception as e:
            print(f"❌ 海报 {poster_path} 处理失败: {e}")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    bg.convert("RGB").save(output_path, quality=90)
    print(f"✅ 封面合成成功: {output_path}")
    return True

# ================= 3. API 上传核心 =================

def upload_cover_to_emby(item_id, image_path):
    url = f"{EMBY_CONFIG['url']}/emby/Items/{item_id}/Images/Primary"
    params = {"api_key": EMBY_CONFIG["api_key"]}
    content_type = "image/jpeg" if image_path.lower().endswith(".jpg") else "image/png"
    
    print(f"☁️ 正在同步封面至 Emby (ItemID: {item_id})...")
    try:
        with open(image_path, "rb") as img_file:
            b64_data = base64.b64encode(img_file.read())
            
        headers = {"Content-Type": content_type}
        response = requests.post(url, params=params, headers=headers, data=b64_data, timeout=30)
        
        if response.status_code in [200, 204]:
            print("✅ 成功同步封面至 Emby！")
        else:
            print(f"❌ 图片上传失败，状态码: {response.status_code}, 详情: {response.text}")
    except Exception as e:
        print(f"❌ 同步过程发生异常: {e}")

# ================= 4. 任务执行主干 =================

def run_job():
    mode_text = "完整模式 (生成并自动上传 Emby)" if UPLOAD_TO_EMBY else "预览模式 (仅生成本地图片不上传)"
    print(f"\n========== Emby Cover Generator [{mode_text}] ==========")
    print(f"当前任务开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    if EMBY_CONFIG["api_key"] == "YOUR_API_KEY_HERE":
        print("❌ 请先在 docker-compose.yml (或 .env) 中配置真实的 EMBY_URL 和 EMBY_API_KEY！")
        return

    target_keys = list(LIBRARY_MAP.keys())
    for lib_key in target_keys:
        print(f"\n>>> 开始处理媒体库: [{lib_key}] <<<")
        target_zh_name = LIBRARY_MAP[lib_key]["zh"]
        output_img = f"./output/cover_{lib_key}.jpg"
        
        success, bg_img, poster_imgs = fetch_latest_emby_images(target_zh_name)
        
        if success:
            if create_library_cover(bg_img, poster_imgs, lib_key, output_img):
                if not UPLOAD_TO_EMBY:
                    print(f"⚠️ 【预览模式】 {output_img} 已保存在 output 文件夹中。")
                else:
                    lib_id = get_emby_item_id(target_zh_name)
                    if lib_id:
                        upload_cover_to_emby(lib_id, output_img)
                        
    print("\n================ 全部任务执行完毕 ================\n")

if __name__ == "__main__":
    run_job()

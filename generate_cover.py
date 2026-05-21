import os
import requests
import base64
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

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
        response = requests.get(url, stream=True, timeout=(10, 20))
        if response.status_code == 200:
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            return True
    except Exception as e:
        print(f"❌ 网络异常/超时: {e}")
    return False

def fetch_latest_posters(library_name):
    print(f"🔍 正在检索媒体库: [{library_name}]...")
    lib_id = get_emby_item_id(library_name)
    if not lib_id:
        return False, []

    url = f"{EMBY_CONFIG['url']}/emby/Items"
    params = {
        "api_key": EMBY_CONFIG["api_key"],
        "ParentId": lib_id,
        "Recursive": "true",
        "IncludeItemTypes": "Movie,Series", 
        "SortBy": "DateCreated",            
        "SortOrder": "Descending",          
        "Limit": 25  # 扩大备用池，只需抓取竖版海报
    }
    
    response = requests.get(url, params=params, timeout=10)
    items = response.json().get("Items", [])
    
    target_count = CONFIG["poster_count"]
    if len(items) < target_count:
        print(f"❌ 媒体库影视不足 {target_count} 个，跳过。")
        return False, []

    os.makedirs("./input", exist_ok=True)
    poster_paths = []

    # 仅抓取竖版海报 (Primary)，支持顺延
    for item in items:
        if len(poster_paths) >= target_count:
            break 
            
        p_path = f"./input/auto_poster_{len(poster_paths)+1}.jpg"
        p_url = f"{EMBY_CONFIG['url']}/emby/Items/{item['Id']}/Images/Primary?api_key={EMBY_CONFIG['api_key']}&maxWidth=600"
        
        if download_image(p_url, p_path):
            poster_paths.append(p_path)
            print(f"🎞️ 海报 {len(poster_paths)}: [{item.get('Name')}] -> 下载完成")

    if len(poster_paths) < target_count:
        print(f"❌ 备用海报耗尽，不足 {target_count} 张。")
        return False, []

    return True, poster_paths

# ================= 2. 图像处理与排版核心 =================

def get_dominant_color(image_path):
    """自动提取图片主色调，并压暗处理作为背景"""
    try:
        img = Image.open(image_path).convert('RGB')
        # 缩小至 1x1 像素，强制计算整图平均色
        img = img.resize((1, 1)) 
        color = img.getpixel((0, 0))
        # 降低 30% 亮度，防止背景太亮导致白色文字不可见
        darkened_color = tuple(max(0, int(c * 0.7)) for c in color)
        return darkened_color
    except:
        return CONFIG["bg_default_color"]

def add_rounded_corners(im, rad):
    """为海报添加圆角"""
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

def create_staggered_cover(poster_paths, lib_key, output_path):
    print("🎨 开始生成倾斜阶梯风封面...")
    
    # 1. 提取动态背景色
    bg_color = get_dominant_color(poster_paths[0]) if CONFIG["bg_auto_color"] else CONFIG["bg_default_color"]
    
    # 2. 创建主画布
    canvas = Image.new("RGBA", CONFIG["output_size"], bg_color + (255,))
    
    # 3. 构建超大海报墙图层 (用于整体旋转)
    wall_layer = Image.new("RGBA", (3000, 3000), (0, 0, 0, 0))
    
    p_w, p_h = CONFIG["poster_size"]
    s_x = CONFIG["poster_spacing_x"]
    s_y = CONFIG["poster_spacing_y"]
    stagger = CONFIG["poster_stagger"]
    
    # 将海报拼接入 3x3 矩阵，并加入阶梯错位
    for i, path in enumerate(poster_paths):
        col = i // 3  # 第几列
        row = i % 3   # 第几行
        
        try:
            poster = Image.open(path).convert("RGBA")
            poster = poster.resize((p_w, p_h), Image.Resampling.LANCZOS)
            poster = add_rounded_corners(poster, rad=25)
            
            # 计算写入坐标
            x = col * (p_w + s_x)
            y = row * (p_h + s_y) + (col * stagger)
            
            wall_layer.paste(poster, (x, y), poster)
        except Exception as e:
            print(f"❌ 海报合成失败: {e}")

    # 对整个海报墙图层进行旋转 (开启平滑抗锯齿)
    rotated_wall = wall_layer.rotate(CONFIG["poster_rotation"], expand=True, resample=Image.Resampling.BICUBIC)
    
    # 将旋转后的海报墙贴入主画布的指定位置
    canvas.paste(rotated_wall, CONFIG["poster_grid_pos"], rotated_wall)

    # 4. 绘制左侧排版文字
    draw = ImageDraw.Draw(canvas)
    lib_names = LIBRARY_MAP.get(lib_key, {"zh": "未知媒体库", "en": "UNKNOWN"})
    
    try:
        font_zh = ImageFont.truetype(CONFIG["font_zh_path"], CONFIG["font_size_zh"])
        font_en = ImageFont.truetype(CONFIG["font_en_path"], CONFIG["font_size_en"])
    except IOError:
        print("⚠️ 警告: 未找到字体文件，将使用系统默认字体！")
        font_zh = ImageFont.load_default()
        font_en = ImageFont.load_default()

    tx, ty = CONFIG["text_pos"]
    
    # 绘制中文主标题
    draw.text((tx, ty), lib_names["zh"], font=font_zh, fill=(255, 255, 255, 255))
    
    # 计算英文副标题位置
    en_y = ty + CONFIG["font_size_zh"] + 25
    
    # 绘制装饰条与英文标题
    if CONFIG["accent_bar_enable"]:
        bar_width = 15
        bar_height = CONFIG["font_size_en"] - 5
        # 画竖条
        draw.rectangle([tx, en_y + 10, tx + bar_width, en_y + 10 + bar_height], fill=CONFIG["accent_bar_color"])
        # 画英文 (向右偏移，避开装饰条)
        draw.text((tx + bar_width + 25, en_y), lib_names["en"], font=font_en, fill=(255, 255, 255, 255))
    else:
        draw.text((tx, en_y), lib_names["en"], font=font_en, fill=(255, 255, 255, 255))

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    canvas.convert("RGB").save(output_path, quality=92)
    print(f"✅ 封面合成成功: {output_path}")
    return True

# ================= 3. API 上传核心 =================

def upload_cover_to_emby(item_id, image_path):
    url = f"{EMBY_CONFIG['url']}/emby/Items/{item_id}/Images/Primary"
    params = {"api_key": EMBY_CONFIG["api_key"]}
    content_type = "image/jpeg"
    
    print(f"☁️ 正在同步封面至 Emby...")
    try:
        with open(image_path, "rb") as img_file:
            b64_data = base64.b64encode(img_file.read())
            
        headers = {"Content-Type": content_type}
        response = requests.post(url, params=params, headers=headers, data=b64_data, timeout=30)
        
        if response.status_code in [200, 204]:
            print("✅ 成功同步封面！")
        else:
            print(f"❌ 上传失败，状态码: {response.status_code}")
    except Exception as e:
        print(f"❌ 同步异常: {e}")

# ================= 4. 任务执行主干 =================

def run_job():
    print(f"\n========== Emby Cover Generator (阶梯矩阵版) ==========")
    print(f"当前任务开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    if EMBY_CONFIG["api_key"] == "YOUR_API_KEY_HERE":
        print("❌ 请先配置真实的 EMBY_URL 和 EMBY_API_KEY！")
        return

    target_keys = list(LIBRARY_MAP.keys())
    for lib_key in target_keys:
        print(f"\n>>> 处理媒体库: [{lib_key}] <<<")
        target_zh_name = LIBRARY_MAP[lib_key]["zh"]
        output_img = f"./output/cover_{lib_key}.jpg"
        
        success, poster_imgs = fetch_latest_posters(target_zh_name)
        
        if success:
            if create_staggered_cover(poster_imgs, lib_key, output_img):
                if not UPLOAD_TO_EMBY:
                    print(f"⚠️ 【预览模式】 {output_img} 已保存。")
                else:
                    lib_id = get_emby_item_id(target_zh_name)
                    if lib_id:
                        upload_cover_to_emby(lib_id, output_img)
                        
    print("\n================ 全部任务执行完毕 ================\n")

if __name__ == "__main__":
    run_job()

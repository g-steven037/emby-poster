import os
import random
import requests
import base64
from datetime import datetime
from PIL import Image, ImageFilter, ImageDraw, ImageFont

from config import UPLOAD_TO_EMBY, COVER_STYLE, LIBRARY_MAP, CONFIG, EMBY_CONFIG

def get_emby_item_id(library_name):
    url = f"{EMBY_CONFIG['url']}/emby/Items"
    params = {"api_key": EMBY_CONFIG["api_key"], "Recursive": "true", "IncludeItemTypes": "CollectionFolder,BoxSet"}
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            for item in response.json().get("Items", []):
                if item.get("Name") == library_name: return item.get("Id")
    except Exception as e: print(f"❌ 连接 Emby API 失败: {e}")
    return None

def download_image(url, save_path):
    try:
        response = requests.get(url, stream=True, timeout=(10, 20))
        if response.status_code == 200:
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk: f.write(chunk)
            return True
    except Exception: pass
    return False

def get_unique_items(lib_id, limit=300):
    """深度去重 & 最新集溯源逻辑"""
    url = f"{EMBY_CONFIG['url']}/emby/Items"
    params = {
        "api_key": EMBY_CONFIG["api_key"], 
        "ParentId": lib_id, 
        "Recursive": "true",
        "IncludeItemTypes": "Movie,Episode", 
        "SortBy": "DateCreated", 
        "SortOrder": "Descending",
        "Limit": limit       
    }
    print(f"📥 正在获取最新入库记录（支持解析最新集），并进行深度去重筛选...")
    raw_items = requests.get(url, params=params, timeout=10).json().get("Items", [])
    
    unique_items = []
    seen_names = set()
    
    for item in raw_items:
        item_type = item.get("Type")
        if item_type == "Episode":
            name = item.get("SeriesName", "")
            target_id = item.get("SeriesId")
        else:
            name = item.get("Name", "")
            target_id = item.get("Id")

        if name and target_id and name not in seen_names:
            seen_names.add(name)
            unique_items.append({"Id": target_id, "Name": name})
            
    print(f"✨ 深度过滤完成！从 {len(raw_items)} 条原始记录中筛选出 {len(unique_items)} 个完全不重复的影视项目。")
    return unique_items

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

def get_dominant_color(image_path):
    try:
        c = Image.open(image_path).convert('RGB').resize((1,1)).getpixel((0,0))
        return tuple(max(0, int(v * 0.7)) for v in c)
    except:
        return CONFIG.get("s2_bg_default_color", (30,30,35))

def get_font(path_key, size_key, default_size):
    try:
        return ImageFont.truetype(CONFIG.get(path_key, ""), CONFIG.get(size_key, default_size))
    except:
        return ImageFont.load_default()

def render_s1_cover(items, lib_key, output_path):
    target_count = CONFIG.get("s1_poster_count", 6)
    if len(items) < target_count:
        print(f"❌ 影视数量不足 {target_count} 个，跳过。")
        return False

    os.makedirs("./input", exist_ok=True)
    bg_path = "./input/s1_bg.jpg"
    poster_paths = []
    
    used_bg_id = None
    for item in items:
        url_backdrop = f"{EMBY_CONFIG['url']}/emby/Items/{item['Id']}/Images/Backdrop/0?api_key={EMBY_CONFIG['api_key']}&maxWidth=1920"
        url_primary = f"{EMBY_CONFIG['url']}/emby/Items/{item['Id']}/Images/Primary?api_key={EMBY_CONFIG['api_key']}&maxWidth=1920"
        
        if download_image(url_backdrop, bg_path) or download_image(url_primary, bg_path):
            used_bg_id = item['Id']
            break 
            
    if not used_bg_id: return False

    for item in [it for it in items if it['Id'] != used_bg_id]:
        if len(poster_paths) >= target_count: break 
        p_path = f"./input/s1_p_{len(poster_paths)+1}.jpg"
        p_url = f"{EMBY_CONFIG['url']}/emby/Items/{item['Id']}/Images/Primary?api_key={EMBY_CONFIG['api_key']}&maxWidth=600"
        if download_image(p_url, p_path): poster_paths.append(p_path)

    if len(poster_paths) < target_count: return False

    print("🎨 正在渲染 [Style 1] 经典平铺封面...")
    bg = Image.open(bg_path).convert("RGBA").resize(CONFIG.get("output_size", (1920, 1080)), Image.Resampling.LANCZOS)
    
    blur_rad = max(0, min(100, CONFIG.get("s1_blur_percent", CONFIG.get("blur_percent", 40)))) / 100.0 * 30
    if blur_rad > 0: bg = bg.filter(ImageFilter.GaussianBlur(blur_rad))

    if CONFIG.get("s1_snow_enable", True):
        snow = Image.new('RGBA', bg.size, (0,0,0,0))
        d_snow = ImageDraw.Draw(snow)
        for _ in range(CONFIG.get("s1_snow_density", 200)):
            x, y = random.randint(0, bg.size[0]), random.randint(0, bg.size[1])
            r = random.randint(1, 4)
            a = random.randint(50, 200)
            d_snow.ellipse((x-r, y-r, x+r, y+r), fill=(255,255,255,a))
        bg = Image.alpha_composite(bg, snow)

    grad = Image.new('RGBA', bg.size, (0,0,0,0))
    d_grad = ImageDraw.Draw(grad)
    f_w = CONFIG.get("s1_gradient_width", 1000)
    m_a = CONFIG.get("s1_gradient_max_alpha", 180)
    for x in range(f_w):
        d_grad.line((x, 0, x, bg.size[1]), fill=(0,0,0, int(m_a*(1-(x/f_w)))))
    bg = Image.alpha_composite(bg, grad)

    draw = ImageDraw.Draw(bg)
    lib_n = LIBRARY_MAP.get(lib_key, {"zh": "未知", "en": "UNKNOWN"})
    f_zh = get_font("font_zh_path", "s1_font_size_zh", 150)
    f_en = get_font("font_en_path", "s1_font_size_en", 70)
    
    draw.text(CONFIG.get("s1_text_pos_zh", (100, 100)), lib_n["zh"], font=f_zh, fill=(255,255,255,255))
    draw.text(CONFIG.get("s1_text_pos_en", (110, 260)), lib_n["en"], font=f_en, fill=(255,255,255,255), spacing=15)

    p_size = CONFIG.get("s1_poster_size", (280, 420))
    p_space = CONFIG.get("s1_poster_spacing", 40)
    start_x = (bg.size[0] - (p_size[0]*target_count + p_space*(target_count-1))) // 2
    
    for i, p in enumerate(poster_paths):
        img = add_rounded_corners(Image.open(p).convert("RGBA").resize(p_size, Image.Resampling.LANCZOS), 15)
        bg.paste(img, (start_x + i*(p_size[0]+p_space), CONFIG.get("s1_poster_y_pos", 560)), img)
        
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    bg.convert("RGB").save(output_path, quality=92)
    return True

def render_s2_cover(items, lib_key, output_path):
    target_count = CONFIG.get("s2_poster_count", 9)
    if len(items) < target_count:
        print(f"❌ 影视数量不足 {target_count} 个，跳过。")
        return False

    os.makedirs("./input", exist_ok=True)
    poster_paths = []
    
    for item in items:
        if len(poster_paths) >= target_count: break 
        p_path = f"./input/s2_p_{len(poster_paths)+1}.jpg"
        p_url = f"{EMBY_CONFIG['url']}/emby/Items/{item['Id']}/Images/Primary?api_key={EMBY_CONFIG['api_key']}&maxWidth=600"
        if download_image(p_url, p_path): poster_paths.append(p_path)

    if len(poster_paths) < target_count: return False

    print("🎨 正在渲染 [Style 2] 动态大画幅阶梯封面...")
    bg_c = CONFIG.get("s2_bg_default_color", (30, 30, 35))
    if CONFIG.get("s2_bg_auto_color", True):
        bg_c = get_dominant_color(poster_paths[0])

    cv = Image.new("RGBA", CONFIG.get("output_size", (1920, 1080)), bg_c + (255,))
    
    p_w, p_h = CONFIG.get("s2_poster_size", (380, 560))
    s_x = CONFIG.get("s2_poster_spacing_x", 40)
    s_y = CONFIG.get("s2_poster_spacing_y", 40)
    stagger = CONFIG.get("s2_poster_stagger", 180)
    
    wall_w = 3 * p_w + 2 * s_x
    wall_h = 3 * p_h + 2 * s_y + 2 * stagger
    wl = Image.new("RGBA", (wall_w, wall_h), (0,0,0,0))

    for i, path in enumerate(poster_paths):
        col, row = i // 3, i % 3
        try:
            img = add_rounded_corners(Image.open(path).convert("RGBA").resize((p_w, p_h), Image.Resampling.LANCZOS), 25)
            x = col * (p_w + s_x)
            y = row * (p_h + s_y) + (col * stagger)
            wl.paste(img, (x, y), img)
        except: pass

    rt = wl.rotate(CONFIG.get("s2_poster_rotation", -15), expand=True, resample=Image.Resampling.BICUBIC)
    
    target_center_x, target_center_y = CONFIG.get("s2_poster_center", (1450, 540))
    paste_x = int(target_center_x - rt.width / 2)
    paste_y = int(target_center_y - rt.height / 2)
    
    cv.paste(rt, (paste_x, paste_y), rt)

    d = ImageDraw.Draw(cv)
    lib_n = LIBRARY_MAP.get(lib_key, {"zh": "未知", "en": "UNKNOWN"})
    
    f_zh = get_font("font_zh_path", "s2_font_size_zh", 180)
    f_en = get_font("font_en_path", "s2_font_size_en", 70)
    
    tx, ty = CONFIG.get("s2_text_pos", (100, 420))
    d.text((tx, ty), lib_n["zh"], font=f_zh, fill=(255,255,255,255))
    
    en_y = ty + CONFIG.get("s2_font_size_zh", 180) + 25
    
    if CONFIG.get("s2_accent_bar_enable", True):
        bw, bh = 15, CONFIG.get("s2_font_size_en", 70) - 5
        bar_color = CONFIG.get("s2_accent_bar_color", (255, 140, 0))
        d.rectangle([tx, en_y+10, tx+bw, en_y+10+bh], fill=bar_color)
        d.text((tx+bw+25, en_y), lib_n["en"], font=f_en, fill=(255,255,255,255))
    else:
        d.text((tx, en_y), lib_n["en"], font=f_en, fill=(255,255,255,255))

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    cv.convert("RGB").save(output_path, quality=92)
    return True

def upload_cover_to_emby(item_id, image_path):
    url = f"{EMBY_CONFIG['url']}/emby/Items/{item_id}/Images/Primary"
    params = {"api_key": EMBY_CONFIG["api_key"]}
    print(f"☁️ 正在同步封面至 Emby...")
    try:
        with open(image_path, "rb") as f:
            b64_data = base64.b64encode(f.read())
        resp = requests.post(url, params=params, headers={"Content-Type": "image/jpeg"}, data=b64_data, timeout=30)
        if resp.status_code in [200, 204]: print("✅ 成功同步封面！")
        else: print(f"❌ 上传失败，状态码: {resp.status_code}")
    except Exception as e: print(f"❌ 同步异常: {e}")

def run_job():
    mode_text = "自动上传模式" if UPLOAD_TO_EMBY else "本地预览模式"
    print(f"\n========== Emby Cover Generator [{mode_text}] ==========")
    print(f"当前排版: [{COVER_STYLE}] | 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    if EMBY_CONFIG["api_key"] == "YOUR_API_KEY_HERE":
        print("❌ 请配置真实的 EMBY_URL 和 EMBY_API_KEY！")
        return

    for lib_key, lib_info in LIBRARY_MAP.items():
        print(f"\n>>> 处理媒体库: [{lib_key}] <<<")
        lib_id = get_emby_item_id(lib_info["zh"])
        if not lib_id:
            print(f"❌ 未在 Emby 中找到名为 [{lib_info['zh']}] 的媒体库。")
            continue

        unique_items = get_unique_items(lib_id)
        out_img = f"./output/cover_{lib_key}.jpg"
        success = False

        if COVER_STYLE == "style_1":
            success = render_s1_cover(unique_items, lib_key, out_img)
        elif COVER_STYLE == "style_2":
            success = render_s2_cover(unique_items, lib_key, out_img)
        else:
            print(f"❌ 未知的排版样式: {COVER_STYLE}")

        if success:
            if UPLOAD_TO_EMBY: upload_cover_to_emby(lib_id, out_img)
            else: print(f"⚠️ [预览] {out_img} 已保存在 output 目录中。")

    print("\n================ 全部任务执行完毕 ================\n")

if __name__ == "__main__":
    run_job()
